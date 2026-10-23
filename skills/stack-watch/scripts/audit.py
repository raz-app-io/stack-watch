#!/usr/bin/env python3
"""stack-watch dependency audit.

Finds known vulnerabilities in the repo's locked dependency versions and
prints each advisory in the common item shape with severity "Security".

Default source is the OSV.dev database (https://osv.dev), queried with the
exact versions from the lockfile. It needs no package manager installed and
works the same for npm, pnpm, Yarn and bun lockfiles. When OSV is
unreachable, the package manager's own audit command is used instead.

Usage:
    python3 audit.py <repo> [--source auto|osv|pm] [--pretty]
    python3 audit.py --input <saved-output> [--format npm|v6|berry|osv] [--pretty]

--input parses a saved audit response instead of running one. Formats: npm
(npm 7+ and bun), v6 (pnpm, Yarn 1 `auditAdvisory` lines), berry (Yarn 2+
`yarn npm audit --json`), osv (an OSV `/v1/query` response or a list of
them). --format is detected from the content when omitted.

Output:
    {"source", "package_manager", "command", "packages_checked",
     "items": [...], "error"}

Item fields: vendor (the package name), title, url, date (null), body,
severity "Security", advisory_severity, package, vulnerable_range, direct,
fix, source_type "advisory", hash. Titles and GitHub advisory URLs are the
same whichever source produced them, so the ledger hash is stable.
Standard library only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import scan_repo  # noqa: E402

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_QUERY = "https://api.osv.dev/v1/query"
OSV_BATCH_SIZE = 500
USER_AGENT = "stack-watch/1.2 (+https://github.com/raz-app-io/stack-watch)"

COMMANDS = {
    "npm": ["npm", "audit", "--json"],
    "pnpm": ["pnpm", "audit", "--json"],
    "yarn": ["yarn", "audit", "--json"],
    "yarn-berry": ["yarn", "npm", "audit", "--json", "--all"],
    "bun": ["bun", "audit", "--json"],
}
FORMAT_FOR = {"npm": "npm", "bun": "npm", "pnpm": "v6", "yarn": "v6",
              "yarn-berry": "berry"}


def make_item(package, title, url, adv_severity, vulnerable, fix, direct):
    title = (title or "").strip() or f"advisory for {package}"
    body = f"Vulnerable versions: {vulnerable or 'unknown'}."
    if fix:
        body += f" Fix: {fix}."
    item = {
        "vendor": package, "title": f"{adv_severity} severity: {title}",
        "url": url or "", "date": None, "body": body, "severity": "Security",
        "advisory_severity": adv_severity, "package": package,
        "vulnerable_range": vulnerable, "direct": direct,
        "source_type": "advisory",
    }
    item["hash"] = ledger.item_hash(item["vendor"], item["url"], item["title"])
    return item


# ---------------------------------------------------------------- OSV

def post_json(url, payload, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def locked_packages(repo):
    """{name: exact version} for every package the lockfile pins, plus the
    set of direct dependency names. Declared ranges without a locked version
    are returned separately as unresolved."""
    pkg = scan_repo.read_json(os.path.join(repo, "package.json")) or {}
    direct = set(pkg.get("dependencies") or {}) | set(pkg.get("devDependencies") or {})
    lockfile = next((lf for lf, _ in scan_repo.LOCKFILES
                     if os.path.isfile(os.path.join(repo, lf))), None)
    locked = scan_repo.lockfile_versions(repo, lockfile) if lockfile else {}
    for name, declared in {**(pkg.get("dependencies") or {}),
                           **(pkg.get("devDependencies") or {})}.items():
        if name not in locked and re.fullmatch(r"\d+\.\d+\.\d+[\w.\-+]*", str(declared)):
            locked[name] = str(declared)  # an exact pin counts as locked
    unresolved = sorted(n for n in direct if n not in locked)
    return locked, direct, unresolved


def osv_range(vuln, package, pinned=None):
    """'>=a <b' style range and the recommended fixed version for one package:
    the lowest stable fix above the pinned version, else the highest fix."""
    parts, fixed = [], []
    for aff in vuln.get("affected") or []:
        p = aff.get("package") or {}
        if p.get("ecosystem") != "npm" or p.get("name") != package:
            continue
        for r in aff.get("ranges") or []:
            intro = fix = None
            for ev in r.get("events") or []:
                intro = ev.get("introduced", intro)
                if ev.get("fixed"):
                    fix = ev["fixed"]
                    fixed.append(fix)
                if ev.get("last_affected"):
                    parts.append(f"{lower(intro)}<={ev['last_affected']}")
            if fix:
                parts.append(f"{lower(intro)}<{fix}")
            elif intro is not None and not any(ev.get("last_affected") for ev in r.get("events") or []):
                parts.append(f">={intro}")
    if not fixed:
        return ", ".join(parts) or None, None
    above = [f for f in fixed if pinned and version_key(f) > version_key(pinned) and "-" not in f]
    best = min(above, key=version_key) if above else max(fixed, key=version_key)
    return ", ".join(parts) or None, best


def lower(intro):
    return "" if intro in (None, "0") else f">={intro} "


def version_key(v):
    return [int(x) if x.isdigit() else -1 for x in re.split(r"[.\-+]", str(v))]


def osv_severity(vuln):
    sev = (vuln.get("database_specific") or {}).get("severity")
    if sev:
        return str(sev).lower()
    for s in vuln.get("severity") or []:
        m = re.search(r"CVSS:\d\.\d/.*?/", s.get("score", ""))
        if m:
            return "unknown"
    return "unknown"


def osv_url(vuln):
    vid = vuln.get("id", "")
    if vid.startswith("GHSA-"):
        return f"https://github.com/advisories/{vid}"
    for alias in vuln.get("aliases") or []:
        if alias.startswith("GHSA-"):
            return f"https://github.com/advisories/{alias}"
    for ref in vuln.get("references") or []:
        if ref.get("type") == "ADVISORY" and ref.get("url"):
            return ref["url"]
    return f"https://osv.dev/vulnerability/{vid}"


def parse_osv(responses, direct=frozenset()):
    """responses: list of {"package": name, "version": v, "vulns": [...]} or
    raw /v1/query responses with "vulns". Returns items."""
    items = []
    if isinstance(responses, dict):
        responses = [responses]
    for resp in responses:
        package = resp.get("package")
        pinned = resp.get("version")
        for vuln in resp.get("vulns") or []:
            pkg = package
            if not pkg:
                for aff in vuln.get("affected") or []:
                    if (aff.get("package") or {}).get("ecosystem") == "npm":
                        pkg = aff["package"]["name"]
                        break
            if not pkg:
                continue
            rng, fixed = osv_range(vuln, pkg, pinned)
            fix = f"upgrade {pkg} to {fixed}" if fixed else None
            items.append(make_item(pkg, vuln.get("summary") or vuln.get("id"), osv_url(vuln),
                                   osv_severity(vuln), rng, fix, pkg in direct))
    return items


def osv_audit(repo, timeout=30):
    locked, direct, unresolved = locked_packages(repo)
    if not locked:
        return {"source": "osv", "package_manager": None, "command": None,
                "packages_checked": 0, "items": [], "error": "no lockfile and no exact pins"}
    names = sorted(locked)
    hits = []
    for i in range(0, len(names), OSV_BATCH_SIZE):
        chunk = names[i:i + OSV_BATCH_SIZE]
        batch = {"queries": [{"package": {"name": n, "ecosystem": "npm"},
                              "version": locked[n]} for n in chunk]}
        result = post_json(OSV_BATCH, batch, timeout)
        for name, res in zip(chunk, result.get("results") or []):
            if res.get("vulns"):
                hits.append(name)
    responses = []
    for name in hits:
        full = post_json(OSV_QUERY, {"package": {"name": name, "ecosystem": "npm"},
                                     "version": locked[name]}, timeout)
        responses.append({"package": name, "version": locked[name],
                          "vulns": full.get("vulns") or []})
    out = {"source": "osv", "package_manager": None, "command": "OSV.dev querybatch",
           "packages_checked": len(names), "items": dedupe(parse_osv(responses, direct)),
           "error": None}
    if unresolved:
        out["unresolved"] = unresolved
    return out


# --------------------------------------------------- package manager audits

def parse_npm(data):
    """npm 7+ (and bun) `audit --json`."""
    items = []
    for pkg, v in (data.get("vulnerabilities") or {}).items():
        fix = v.get("fixAvailable")
        if isinstance(fix, dict):
            fix = f"upgrade {fix.get('name')} to {fix.get('version')}" + (
                " (semver major)" if fix.get("isSemVerMajor") else "")
        elif fix is True:
            fix = "npm audit fix"
        else:
            fix = None
        for via in v.get("via") or []:
            if not isinstance(via, dict):
                continue  # a string means "through this package", not an advisory
            items.append(make_item(via.get("name", pkg), via.get("title"), via.get("url"),
                                   via.get("severity", v.get("severity", "unknown")),
                                   via.get("range", v.get("range")), fix,
                                   bool(v.get("isDirect"))))
    return items


def parse_v6_advisory(adv):
    pkg = adv.get("module_name", "unknown")
    direct = any(p and ">" not in p for f in adv.get("findings") or []
                 for p in f.get("paths") or [])
    return make_item(pkg, adv.get("title"), adv.get("url"), adv.get("severity", "unknown"),
                     adv.get("vulnerable_versions"), adv.get("recommendation"), direct)


def parse_v6(data):
    """npm 6 format: pnpm `audit --json`, and the `advisories` document."""
    return [parse_v6_advisory(a) for a in (data.get("advisories") or {}).values()]


def parse_berry_line(line):
    ch = line.get("children") or {}
    deps = ch.get("Dependents") or []
    direct = any("@workspace:" in str(d) for d in deps)
    return make_item(line.get("value", "unknown"), ch.get("Issue"), ch.get("URL"),
                     str(ch.get("Severity", "unknown")).lower(),
                     ch.get("Vulnerable Versions"), None, direct)


def parse_lines(text):
    """NDJSON from Yarn 1 (`auditAdvisory` records) or Yarn 2+."""
    items = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if line.get("type") == "auditAdvisory":
            items.append(parse_v6_advisory(line["data"]["advisory"]))
        elif "children" in line and "value" in line:
            items.append(parse_berry_line(line))
        elif "vulnerabilities" in line:
            items.extend(parse_npm(line))
        elif "advisories" in line:
            items.extend(parse_v6(line))
    return items


def parse_output(text, fmt=None):
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if data is None or fmt == "berry":
        return parse_lines(text)
    if fmt == "osv" or (fmt is None and (isinstance(data, list) or "vulns" in data)):
        return parse_osv(data)
    if fmt == "npm" or (fmt is None and "vulnerabilities" in data):
        return parse_npm(data)
    if fmt == "v6" or (fmt is None and "advisories" in data):
        return parse_v6(data)
    return []


def dedupe(items):
    seen, out = set(), []
    for it in items:
        key = (it["package"], it["url"], it["title"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def detect_pm(repo):
    for lf, name in scan_repo.LOCKFILES:
        if os.path.isfile(os.path.join(repo, lf)):
            if name == "yarn":
                head = scan_repo.read_text(os.path.join(repo, lf))[:2000]
                if "__metadata" in head or os.path.isfile(os.path.join(repo, ".yarnrc.yml")):
                    return "yarn-berry"
            return name
    return None


def pm_audit(repo, timeout=300):
    pm = detect_pm(repo)
    base = {"source": "pm", "package_manager": pm, "command": None, "packages_checked": None,
            "items": [], "error": None}
    if not pm:
        return dict(base, error="no lockfile found")
    cmd = COMMANDS[pm]
    base["command"] = " ".join(cmd)
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return dict(base, error=f"{cmd[0]} is not installed")
    except subprocess.TimeoutExpired:
        return dict(base, error=f"timed out after {timeout}s")
    # Audits exit non-zero when they find anything; judge by the output.
    items = dedupe(parse_output(proc.stdout, FORMAT_FOR[pm]))
    error = None if proc.stdout.strip() else (proc.stderr.strip() or "no output")[:500]
    return dict(base, items=items, error=error)


def run_audit(repo, source="auto", timeout=300):
    if source in ("auto", "osv"):
        try:
            return osv_audit(repo, timeout=min(timeout, 60))
        except (urllib.error.URLError, OSError, ValueError) as e:
            if source == "osv":
                return {"source": "osv", "package_manager": None, "command": "OSV.dev querybatch",
                        "packages_checked": 0, "items": [], "error": f"OSV unreachable: {str(e)[:200]}"}
    result = pm_audit(repo, timeout)
    if source == "auto":
        result["note"] = "OSV.dev was unreachable; used the package manager's audit"
    return result


def main():
    ap = argparse.ArgumentParser(description="stack-watch dependency audit")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--source", choices=["auto", "osv", "pm"], default="auto")
    ap.add_argument("--input", help="parse a saved audit output instead of running one")
    ap.add_argument("--format", choices=["npm", "v6", "berry", "osv"])
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    if args.input:
        try:
            with open(args.input, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        out = {"source": "input", "package_manager": None, "command": f"--input {args.input}",
               "packages_checked": None, "items": dedupe(parse_output(text, args.format)),
               "error": None}
    else:
        out = run_audit(os.path.abspath(args.repo), args.source)
    print(json.dumps(out, indent=2 if args.pretty else None, ensure_ascii=False))
    sys.exit(0 if out["error"] is None else 1)


if __name__ == "__main__":
    main()
