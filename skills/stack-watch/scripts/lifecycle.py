#!/usr/bin/env python3
"""stack-watch lifecycle check.

Two deterministic signals that changelogs announce late or never:

  * End of life. For runtimes and frameworks that https://endoflife.date
    tracks (Node.js, Next.js, React, Vue, Nuxt, Svelte, Angular, Express,
    Bun, Electron, Tailwind CSS, ...), the pinned major's EOL date, support
    end, and latest patch.
  * Registry deprecation. For every npm package in the scan, whether the
    pinned version is marked deprecated on the registry, the latest version,
    the latest patch within the pinned major, and how many majors behind.

Usage:
    python3 lifecycle.py <scan.json> [--soon-days 120] [--timeout 20] [--pretty]

Output:
    {"checked_at", "items": [...], "eol": [rows], "versions": [rows], "errors": [...]}

`items` are in the common item shape with severity "Deprecation": one per
end-of-life (or ending within --soon-days) product, one per deprecated
pinned version. `eol` and `versions` are tables for the report. Items hash
on vendor, URL and a title that names the cycle or version, so they dedupe
across runs. Standard library only.
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import safe_http  # noqa: E402

USER_AGENT = safe_http.USER_AGENT
DOC_LIMIT = 2_000_000       # bytes per endoflife.date document
REGISTRY_LIMIT = 30_000_000  # the abbreviated record of a package with thousands of versions is several MB
# npm's own naming rule; anything else is not looked up (it would be a URL injection)
NPM_NAME_RE = re.compile(r"^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")
EOL_API = "https://endoflife.date/api/{slug}.json"
EOL_PAGE = "https://endoflife.date/{slug}"
REGISTRY = "https://registry.npmjs.org/{name}"
REGISTRY_ACCEPT = "application/vnd.npm.install-v1+json"  # abbreviated metadata

# scan item name -> endoflife.date product slug
EOL_PRODUCTS = {
    "Node.js": "nodejs", "next": "nextjs", "react": "react", "react-native": "react-native",
    "vue": "vue", "nuxt": "nuxt", "svelte": "svelte", "@sveltejs/kit": "svelte",
    "@angular/core": "angular", "express": "express", "bun": "bun", "electron": "electron",
    "tailwindcss": "tailwind-css", "typescript": None,  # not tracked by endoflife.date
}
PACKAGE_SECTIONS = {"framework", "database", "orm", "auth", "analytics", "key_package"}


def get_json(url, timeout, accept=None):
    headers = {"Accept": accept} if accept else None
    limit = REGISTRY_LIMIT if url.startswith(REGISTRY.format(name="")) else DOC_LIMIT
    text, _ = safe_http.open_url(url, timeout, headers, limit=limit)
    return json.loads(text)


def registry_url(name):
    """Registry document URL for a valid npm package name, else None."""
    if not NPM_NAME_RE.match(name or "") or len(name) > 214:
        return None
    return REGISTRY.format(name=urllib.parse.quote(name, safe="@/"))


def exact_version(text):
    """'14.2.21' from '14.2.21'; None for a range like '^14.2.0' or '>=20'."""
    m = re.fullmatch(r"v?(\d+\.\d+\.\d+(?:[-+][\w.]+)?)", str(text or "").strip())
    return m.group(1) if m else None


def major_of(text):
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else None


def version_key(v):
    return [int(x) if x.isdigit() else -1 for x in re.split(r"[.\-+]", str(v))]


def is_stable(v):
    return "-" not in str(v)


# ------------------------------------------------------------- end of life

def eol_row(product, slug, pinned, cycles, today, soon_days):
    """One table row for a product given the endoflife.date cycle list."""
    major = major_of(pinned)
    cycle = match_cycle(cycles, pinned)
    row = {"product": product, "pinned": pinned,
           "cycle": str(cycle.get("cycle")) if cycle else (str(major) if major is not None else None),
           "latest_in_cycle": None, "eol": None, "support": None, "lts": None,
           "status": "unknown cycle", "url": EOL_PAGE.format(slug=slug)}
    if cycle is None:
        return row
    eol = cycle.get("eol")
    row.update({"latest_in_cycle": cycle.get("latest"), "eol": eol if isinstance(eol, str) else None,
                "support": cycle.get("support") if isinstance(cycle.get("support"), str) else None,
                "lts": cycle.get("lts") if isinstance(cycle.get("lts"), bool) else bool(cycle.get("lts"))})
    if eol is True or (isinstance(eol, str) and eol <= today):
        row["status"] = "end-of-life"
    elif isinstance(eol, str):
        days = (datetime.date.fromisoformat(eol) - datetime.date.fromisoformat(today)).days
        row["status"] = "ending soon" if days <= soon_days else "supported"
    else:
        row["status"] = "supported"
    newer = [str(c.get("cycle")) for c in cycles
             if version_key(c.get("cycle")) > version_key(cycle.get("cycle"))
             and not (isinstance(c.get("eol"), str) and c["eol"] <= today)]
    row["supported_newer_cycles"] = newer
    return row


def match_cycle(cycles, pinned):
    """endoflife.date cycles are majors ("20") for most products and
    major.minor ("3.4") for a few. Prefer an exact major.minor match, then
    the plain major, then the highest cycle sharing the major."""
    major = major_of(pinned)
    if major is None:
        return None
    mm = re.match(r"v?(\d+\.\d+)", str(pinned))
    by = {str(c.get("cycle")): c for c in cycles}
    if mm and mm.group(1) in by:
        return by[mm.group(1)]
    if str(major) in by:
        return by[str(major)]
    same = [c for k, c in by.items() if major_of(k) == major]
    return max(same, key=lambda c: version_key(c.get("cycle"))) if same else None


def eol_item(row):
    if row["status"] not in ("end-of-life", "ending soon"):
        return None
    verb = "reached" if row["status"] == "end-of-life" else "reaches"
    when = row["eol"] or "an unstated date"
    title = f"{row['product']} {row['cycle']} {verb} end of life on {when}"
    body = (f"Pinned {row['pinned']}; the {row['cycle']} line {verb} end of life on {when}"
            f" and receives no security fixes after that."
            + (f" Latest {row['cycle']}.x release: {row['latest_in_cycle']}." if row.get("latest_in_cycle") else "")
            + (f" Supported newer lines: {', '.join(row['supported_newer_cycles'])}."
               if row.get("supported_newer_cycles") else ""))
    item = {"vendor": row["product"], "title": title, "url": row["url"], "date": row["eol"],
            "body": body, "severity": "Deprecation", "source_type": "end-of-life",
            "source_status": "verified", "prerelease": False}
    item["hash"] = ledger.item_hash(item["vendor"], item["url"], item["title"])
    return item


# ----------------------------------------------------------- npm registry

def version_row(name, declared, doc):
    """One table row from an npm registry document (full or abbreviated)."""
    versions = doc.get("versions") or {}
    tags = doc.get("dist-tags") or {}
    latest = tags.get("latest")
    pinned = exact_version(declared)
    row = {"package": name, "pinned": pinned or declared, "exact": pinned is not None,
           "latest": latest, "latest_in_major": None, "majors_behind": None,
           "deprecated": None, "url": f"https://www.npmjs.com/package/{name}"}
    major = major_of(pinned or declared)
    if major is not None:
        same = [v for v in versions if is_stable(v) and major_of(v) == major]
        if same:
            row["latest_in_major"] = max(same, key=version_key)
        if latest and major_of(latest) is not None:
            row["majors_behind"] = max(0, major_of(latest) - major)
    if pinned and pinned in versions:
        dep = versions[pinned].get("deprecated")
        if dep:
            row["deprecated"] = dep if isinstance(dep, str) else "deprecated"
    return row


def deprecation_item(row):
    if not row.get("deprecated") or not row.get("exact"):
        return None
    msg = row["deprecated"].strip()
    title = f"{row['package']}@{row['pinned']} is deprecated on npm: {msg[:100]}"
    body = (f"The npm registry marks {row['package']} {row['pinned']} deprecated: {msg}"
            + (f" Latest in the {major_of(row['pinned'])}.x line: {row['latest_in_major']}." if row.get("latest_in_major") else "")
            + (f" Latest overall: {row['latest']}." if row.get("latest") else ""))
    item = {"vendor": row["package"], "title": title,
            "url": f"https://www.npmjs.com/package/{row['package']}/v/{row['pinned']}",
            "date": None, "body": body, "severity": "Deprecation", "source_type": "registry",
            "source_status": "verified", "prerelease": False}
    item["hash"] = ledger.item_hash(item["vendor"], item["url"], item["title"])
    return item


# ------------------------------------------------------------------ driver

def check(scan, today=None, soon_days=120, timeout=20, fetch=get_json, workers=8):
    today = today or datetime.date.today().isoformat()
    out = {"checked_at": today, "items": [], "eol": [], "versions": [], "errors": []}
    items = scan.get("items", [])

    eol_targets = []
    for it in items:
        slug = EOL_PRODUCTS.get(it.get("name"))
        if slug and it.get("version") and it["section"] in PACKAGE_SECTIONS | {"runtime"}:
            eol_targets.append((it["name"], slug, str(it["version"])))
    pkg_targets = [(it["name"], str(it["version"])) for it in items
                   if it.get("section") in PACKAGE_SECTIONS and it.get("version")
                   and re.match(r"^[@a-z0-9]", it["name"])]

    def do_eol(t):
        name, slug, pinned = t
        try:
            return eol_row(name, slug, pinned, fetch(EOL_API.format(slug=slug), timeout), today, soon_days), None
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return None, f"endoflife.date {slug}: {str(e)[:120]}"

    def do_pkg(t):
        name, declared = t
        url = registry_url(name)
        if not url:
            return None, f"npm registry: skipped invalid package name {name[:60]!r}"
        try:
            return version_row(name, declared, fetch(url, timeout, REGISTRY_ACCEPT)), None
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return None, f"npm registry {name}: {str(e)[:120]}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for row, err in ex.map(do_eol, eol_targets):
            if err:
                out["errors"].append(err)
            elif row:
                out["eol"].append(row)
                item = eol_item(row)
                if item:
                    out["items"].append(item)
        for row, err in ex.map(do_pkg, pkg_targets):
            if err:
                out["errors"].append(err)
            elif row:
                out["versions"].append(row)
                item = deprecation_item(row)
                if item:
                    out["items"].append(item)
    out["versions"].sort(key=lambda r: r["package"])
    return out


def main():
    ap = argparse.ArgumentParser(description="stack-watch lifecycle check")
    ap.add_argument("scan_json")
    ap.add_argument("--soon-days", type=int, default=120,
                    help="flag end-of-life dates within this many days (default 120)")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--allow-private-hosts", action="store_true")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    safe_http.ALLOW_PRIVATE = args.allow_private_hosts
    try:
        with open(args.scan_json, encoding="utf-8") as f:
            scan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    out = check(scan, soon_days=args.soon_days, timeout=args.timeout)
    print(json.dumps(out, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
