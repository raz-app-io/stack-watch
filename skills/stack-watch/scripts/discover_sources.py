#!/usr/bin/env python3
"""stack-watch source discovery.

Proposes sources.json entries for the packages in a scan without any web
search. For each npm package it reads the registry record to find the
GitHub repository (whose releases feed is always machine-readable) and the
project homepage, then looks for a changelog feed on that site: RSS and Atom
autodiscovery links in the page, then a short list of conventional paths
(/changelog/rss.xml, /changelog/feed, /changelog.rss, /feed.xml, ...).

Usage:
    python3 discover_sources.py <scan.json> [--existing sources.json]
                                [--timeout 15] [--pretty]

Output:
    {"vendors": [{"vendor", "matches", "sources": [...], "status": "unverified",
                  "evidence": {"packages", "repository", "homepage"}}],
     "already_covered": [package, ...], "errors": [...]}

Every proposed vendor has status "unverified": a person (or Claude, following
references/vendor-sources.md) confirms the feed is the vendor's changelog
before it is probed for real. Packages that match an existing sources.json
entry are skipped. Standard library only.
"""

import argparse
import concurrent.futures
import datetime
import fnmatch
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "stack-watch/1.2 (+https://github.com/raz-app-io/stack-watch)"
REGISTRY_LATEST = "https://registry.npmjs.org/{name}/latest"
PACKAGE_SECTIONS = {"framework", "database", "orm", "auth", "analytics", "key_package"}
SKIP_HOMEPAGE_HOSTS = {"github.com", "www.github.com", "www.npmjs.com", "npmjs.com",
                       "gitlab.com", "bitbucket.org"}
# Hosts whose packages are not "vendors" with changelogs worth probing.
SKIP_REPO_OWNERS = {"DefinitelyTyped"}
FEED_PATHS = ["/changelog/rss.xml", "/changelog/feed", "/changelog/feed.xml", "/changelog.rss",
              "/changelog/rss", "/changelog/atom.xml", "/releases.rss", "/feed.xml", "/rss.xml",
              "/atom.xml", "/blog/rss.xml", "/blog/feed", "/blog/feed.xml"]
CHANGELOG_PATHS = ["/changelog", "/changelog/", "/releases", "/release-notes", "/whats-new"]
LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def fetch_text(url, timeout, limit=300_000):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final = resp.geturl()
        return resp.read(limit).decode("utf-8", errors="replace"), final


def fetch_json(url, timeout):
    text, _ = fetch_text(url, timeout)
    return json.loads(text)


def parse_repository(value):
    """(owner, repo) from the many shapes npm's repository field takes
    (git+https://github.com/o/r.git, git@github.com:o/r.git, github:o/r,
    o/r, a dict with "url"), or None when it is not on GitHub."""
    if isinstance(value, dict):
        value = value.get("url") or ""
    value = str(value or "").strip()
    if not value:
        return None
    if value.startswith("github:"):
        value = "github.com/" + value[len("github:"):]
    elif re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        value = "github.com/" + value  # npm shorthand "owner/repo"
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?].*)?$", value, re.I)
    return (m.group(1), m.group(2)) if m else None


def feed_links_in_html(text, base_url):
    """Absolute URLs of <link rel="alternate" type="application/rss+xml|atom+xml">."""
    out = []
    for tag in LINK_RE.findall(text):
        attrs = {k.lower(): html.unescape(v1 or v2 or v3) for k, v1, v2, v3 in ATTR_RE.findall(tag)}
        if "alternate" in attrs.get("rel", "").lower() and re.search(
                r"application/(rss|atom)\+xml", attrs.get("type", ""), re.I) and attrs.get("href"):
            out.append(urllib.parse.urljoin(base_url, attrs["href"]))
    return list(dict.fromkeys(out))


def changelog_links_in_html(text, base_url):
    """Same-site links whose path mentions changelog, release notes, or what's new."""
    origin = urllib.parse.urlsplit(base_url)
    out = []
    for href in HREF_RE.findall(text):
        url = urllib.parse.urljoin(base_url, html.unescape(href))
        parts = urllib.parse.urlsplit(url)
        if parts.netloc.lower().replace("www.", "") != origin.netloc.lower().replace("www.", ""):
            continue
        if re.search(r"\.(xml|rss|json)$|/(feed|rss|atom)/?$", parts.path, re.I):
            continue  # a feed, not a page
        if re.search(r"changelog|release-?notes|whats-?new|/releases/?$", parts.path, re.I):
            out.append(urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")))
    return list(dict.fromkeys(out))


def looks_like_feed(text):
    head = text.lstrip()[:600].lower()
    return head.startswith("<?xml") and ("<rss" in head or "<feed" in head) or head.startswith(("<rss", "<feed"))


def group_by_vendor(records):
    """records: [{package, repository, homepage}] -> {key: {packages, repository, homepage}}.
    Key is the GitHub owner/repo when known, else the homepage host, else the package."""
    groups = {}
    for r in records:
        repo = parse_repository(r.get("repository"))
        home = r.get("homepage") or ""
        host = urllib.parse.urlsplit(home).netloc.lower().replace("www.", "") if home else ""
        if repo:
            key = f"{repo[0]}/{repo[1]}"
        elif host and host not in SKIP_HOMEPAGE_HOSTS:
            key = host
        else:
            key = r["package"]
        g = groups.setdefault(key, {"packages": [], "repository": None, "homepage": None})
        g["packages"].append(r["package"])
        if repo and not g["repository"]:
            g["repository"] = f"https://github.com/{repo[0]}/{repo[1]}"
        if home and host not in SKIP_HOMEPAGE_HOSTS and not g["homepage"]:
            g["homepage"] = home
    return groups


def covered_by(existing, package):
    for v in (existing or {}).get("vendors", []):
        for pat in v.get("matches", []):
            if fnmatch.fnmatch(package, pat) if any(c in pat for c in "*?[") else package == pat:
                return v.get("vendor")
    return None


def probe_vendor(key, group, timeout, fetch=fetch_text, today=None):
    """Build one proposed vendor entry. Network: 1 GET for the releases feed,
    1 for the homepage, up to ~6 for conventional feed paths."""
    today = today or datetime.date.today().isoformat()
    sources, notes = [], []
    repo = group.get("repository")
    if repo:
        owner = repo.rstrip("/").split("/")[-2]
        if owner not in SKIP_REPO_OWNERS:
            atom = repo + "/releases.atom"
            try:
                text, _ = fetch(atom, timeout)
                if looks_like_feed(text):
                    entries = text.count("<entry")
                    sources.append({"type": "github-releases", "url": repo + "/releases", "feed": atom,
                                    "verified": today,
                                    "note": "auto-discovered; %d release(s) in feed" % entries})
                    if entries == 0:
                        notes.append("repository publishes no GitHub releases")
            except (urllib.error.URLError, OSError, ValueError) as e:
                notes.append(f"releases feed: {str(e)[:80]}")
    home = group.get("homepage")
    if home:
        try:
            page, final = fetch(home, timeout)
            origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(final))
            feeds = feed_links_in_html(page, final)
            pages = changelog_links_in_html(page, final)
            seen = set(s["feed"] for s in sources if s.get("feed"))
            for f in feeds[:3]:
                if f in seen:
                    continue
                try:
                    body, _ = fetch(f, timeout)
                    if looks_like_feed(body):
                        kind = "changelog" if re.search(r"changelog|release", f, re.I) else "blog"
                        sources.append({"type": kind, "url": pages[0] if pages else home, "feed": f,
                                        "verified": today, "note": "auto-discovered from <link rel=alternate>"})
                        seen.add(f)
                except (urllib.error.URLError, OSError, ValueError):
                    pass
            if not any(s["type"] == "changelog" for s in sources):
                # Conventional paths, first under the changelog page itself
                # (neon.com/docs/changelog/rss.xml), then at the site root.
                candidates = []
                for page in pages[:1]:
                    base = page.rstrip("/")
                    candidates += [base + suffix for suffix in
                                   ("/rss.xml", "/feed", "/feed.xml", "/atom.xml", ".rss", "/rss")]
                candidates += [origin + path for path in FEED_PATHS]
                tried = 0
                for url in candidates:
                    if tried >= 8:
                        break
                    if url in seen:
                        continue
                    tried += 1
                    try:
                        body, _ = fetch(url, timeout)
                        if looks_like_feed(body):
                            sources.append({"type": "changelog" if re.search(r"changelog|release", url, re.I) else "blog",
                                            "url": pages[0] if pages else origin + "/changelog",
                                            "feed": url, "verified": today,
                                            "note": "auto-discovered at a conventional path"})
                            break
                    except (urllib.error.URLError, OSError, ValueError):
                        pass
            if pages and not any(s["type"] == "changelog" for s in sources):
                sources.append({"type": "changelog", "url": pages[0], "feed": None, "verified": today,
                                "note": "HTML changelog page linked from the homepage; no feed found"})
        except (urllib.error.URLError, OSError, ValueError) as e:
            notes.append(f"homepage: {str(e)[:80]}")
    vendor = key.split("/")[-1] if "/" in key else key
    return {"vendor": vendor, "matches": sorted(group["packages"]), "sources": sources,
            "status": "unverified",
            "evidence": {"packages": sorted(group["packages"]), "repository": repo,
                         "homepage": home, "notes": notes}}


def discover(scan, existing=None, timeout=15, fetch=fetch_text, fetch_json_fn=fetch_json,
             workers=6, today=None):
    out = {"vendors": [], "already_covered": [], "errors": []}
    packages = sorted({it["name"] for it in scan.get("items", [])
                       if it.get("section") in PACKAGE_SECTIONS and it.get("version")
                       and re.match(r"^[@a-z0-9]", it["name"])})
    todo = []
    for p in packages:
        if covered_by(existing, p):
            out["already_covered"].append(p)
        else:
            todo.append(p)

    def meta(p):
        try:
            d = fetch_json_fn(REGISTRY_LATEST.format(name=p), timeout)
            return {"package": p, "repository": d.get("repository"), "homepage": d.get("homepage")}, None
        except (urllib.error.URLError, OSError, ValueError) as e:
            return None, f"registry {p}: {str(e)[:100]}"

    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for rec, err in ex.map(meta, todo):
            if err:
                out["errors"].append(err)
            elif rec:
                records.append(rec)
        groups = group_by_vendor(records)
        for entry in ex.map(lambda kv: probe_vendor(kv[0], kv[1], timeout, fetch, today), groups.items()):
            out["vendors"].append(entry)
    out["vendors"].sort(key=lambda v: v["vendor"].lower())
    return out


def main():
    ap = argparse.ArgumentParser(description="stack-watch source discovery")
    ap.add_argument("scan_json")
    ap.add_argument("--existing", help="current sources.json; packages it covers are skipped")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    try:
        with open(args.scan_json, encoding="utf-8") as f:
            scan = json.load(f)
        existing = None
        if args.existing and os.path.isfile(args.existing):
            with open(args.existing, encoding="utf-8") as f:
                existing = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    out = discover(scan, existing, args.timeout)
    print(json.dumps(out, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
