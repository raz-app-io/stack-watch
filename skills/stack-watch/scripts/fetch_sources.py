#!/usr/bin/env python3
"""stack-watch source fetcher.

Reads stack-watch/sources.json, fetches every RSS or Atom feed and every
GitHub releases source, and prints the items published since a date in the
common item shape. HTML-only pages are not parsed; they are reported with
status "unparsed" so the caller can read them another way.

Usage:
    python3 fetch_sources.py <sources.json> --since YYYY-MM-DD
                             [--timeout 20] [--max-body 1500] [--pretty]

Output:
    {
      "since": "...", "fetched_at": "...",
      "items": [{"vendor", "title", "url", "date", "body", "source_type",
                 "source_status", "prerelease", "hash"}],
      "sources": [{"vendor", "url", "status", "count", "error"}]
    }

A source may carry "url_filter", a regular expression; items whose URL does
not match it are dropped (for feeds that mix a blog with a changelog).

Source status values: ok, unreachable, unparsed, skipped. Items with no
parseable date are kept with "date": null. Prereleases (GitHub prerelease
flag, or a canary/alpha/beta/rc title) are left out unless
--include-prereleases is given; each source reports how many it skipped.
Set GITHUB_TOKEN to raise the GitHub API rate limit. Standard library only.
"""

import argparse
import datetime
import email.utils
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

USER_AGENT = "stack-watch/1.1 (+https://github.com/raz-app-io/stack-watch)"
ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"
GITHUB_RELEASES_RE = re.compile(
    r"^https?://github\.com/([\w.-]+)/([\w.-]+)/releases(?:\.atom)?/?$")
PRERELEASE_RE = re.compile(
    r"(canary|alpha|beta|rc[.\-]?\d*|next\.\d|preview|nightly|experimental)\b", re.I)
REDIRECT_CODES = {301, 302, 303, 307, 308}
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def fetch(url, timeout, headers=None, _hops=0):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # Python < 3.11 does not follow 308 on its own.
        target = e.headers.get("Location") if e.headers else None
        if e.code in REDIRECT_CODES and target and _hops < 5:
            return fetch(urllib.parse.urljoin(url, target), timeout, headers, _hops + 1)
        raise


def clean_text(s, max_body):
    s = html.unescape(TAG_RE.sub(" ", s or ""))
    s = WS_RE.sub(" ", s).strip()
    return s[:max_body]


def parse_date(s):
    """RFC 2822 or ISO 8601 -> YYYY-MM-DD, else None."""
    if not s:
        return None
    s = s.strip()
    try:
        return email.utils.parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def text_of(el, *names):
    """Text of the first non-empty child. Atom `<content type="xhtml">` wraps
    markup in child elements, so those are serialized too."""
    for n in names:
        child = el.find(n)
        if child is None:
            continue
        text = (child.text or "") + "".join(ET.tostring(c, encoding="unicode") for c in child)
        if text.strip():
            return text
    return ""


def parse_feed(xml_text, vendor, source, max_body=2000):
    """Parse RSS 2.0 or Atom into items. Raises ET.ParseError on bad XML."""
    root = ET.fromstring(xml_text)
    items = []
    if root.tag == ATOM + "feed":
        for entry in root.findall(ATOM + "entry"):
            link = ""
            for l in entry.findall(ATOM + "link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            items.append({
                "title": clean_text(text_of(entry, ATOM + "title"), 300),
                "url": link or text_of(entry, ATOM + "id"),
                "date": parse_date(text_of(entry, ATOM + "published", ATOM + "updated")),
                "body": clean_text(text_of(entry, ATOM + "content", ATOM + "summary"),
                                   max_body),
            })
            items[-1]["prerelease"] = bool(PRERELEASE_RE.search(items[-1]["title"]))
    else:
        channel = root.find("channel")
        if channel is None:
            raise ET.ParseError("not an RSS or Atom document")
        for it in channel.findall("item"):
            items.append({
                "title": clean_text(text_of(it, "title"), 300),
                "url": text_of(it, "link", "guid").strip(),
                "date": parse_date(text_of(it, "pubDate", DC_NS + "date")),
                "body": clean_text(text_of(it, CONTENT_NS + "encoded", "description"),
                                   max_body),
            })
            items[-1]["prerelease"] = bool(PRERELEASE_RE.search(items[-1]["title"]))
    for i in items:
        i.update({"vendor": vendor, "source_type": source.get("type", "feed"),
                  "source_status": source.get("_status", "verified")})
    return items


def parse_github_releases(releases, vendor, source, max_body=2000):
    items = []
    for r in releases:
        if r.get("draft"):
            continue
        items.append({
            "vendor": vendor,
            "title": clean_text(r.get("name") or r.get("tag_name") or "", 300),
            "url": r.get("html_url", ""),
            "date": parse_date(r.get("published_at") or r.get("created_at")),
            "body": clean_text(r.get("body") or "", max_body),
            "source_type": source.get("type", "github-releases"),
            "source_status": source.get("_status", "verified"),
            "prerelease": bool(r.get("prerelease")) or bool(
                PRERELEASE_RE.search(r.get("name") or r.get("tag_name") or "")),
        })
    return items


def fetch_github(owner, repo, vendor, source, timeout, max_body):
    api = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=100"
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        data = json.loads(fetch(api, timeout, headers))
        if isinstance(data, list):
            return parse_github_releases(data, vendor, source, max_body), api
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        pass
    # Rate limited or unreachable: fall back to the public Atom feed.
    atom = f"https://github.com/{owner}/{repo}/releases.atom"
    return parse_feed(fetch(atom, timeout), vendor, source, max_body), atom


def fetch_source(vendor, source, timeout, max_body):
    """Return (items, status, error, url_used)."""
    url = source.get("feed") or source.get("url")
    if not url:
        return [], "skipped", "no url (command source, see audit.py)", None
    m = GITHUB_RELEASES_RE.match(source.get("url") or "") or GITHUB_RELEASES_RE.match(url)
    try:
        if m:
            items, used = fetch_github(m.group(1), m.group(2), vendor, source,
                                       timeout, max_body)
            return items, "ok", None, used
        body = fetch(url, timeout)
        try:
            return parse_feed(body, vendor, source, max_body), "ok", None, url
        except ET.ParseError:
            if source.get("feed"):
                return [], "unparsed", "feed URL did not return RSS or Atom", url
            return [], "unparsed", "HTML page; read it directly", url
    except urllib.error.HTTPError as e:
        return [], "unreachable", f"HTTP {e.code}", url
    except (urllib.error.URLError, OSError, ValueError) as e:
        return [], "unreachable", str(e)[:200], url


def collect(sources_doc, since, timeout=20, max_body=2000, fetcher=fetch_source,
            include_prereleases=False):
    """Fetch everything in a sources.json document. `fetcher` is injectable
    for tests. Returns the output document."""
    vendors = sources_doc if isinstance(sources_doc, list) else sources_doc.get("vendors", [])
    out_items, summary, seen = [], [], set()
    for v in vendors:
        vendor = v.get("vendor", "unknown")
        status = v.get("status", "verified")
        for s in v.get("sources", []):
            url = s.get("feed") or s.get("url")
            if status == "retired" or not url:
                summary.append({"vendor": vendor, "url": url, "status": "skipped",
                                "count": 0, "prereleases_skipped": 0,
                                "error": "vendor status retired" if status == "retired"
                                else "no url (command source, see audit.py)"})
                continue
            s = dict(s, _status=status)
            items, st, err, used = fetcher(vendor, s, timeout, max_body)
            url_filter = re.compile(s["url_filter"]) if s.get("url_filter") else None
            kept = pre = 0
            for it in items:
                if it["date"] and it["date"] < since:
                    continue
                if url_filter and not url_filter.search(it.get("url", "")):
                    continue
                if it.get("prerelease") and not include_prereleases:
                    pre += 1
                    continue
                it["hash"] = ledger.item_hash(vendor, it["url"], it["title"])
                if it["hash"] in seen:
                    continue
                seen.add(it["hash"])
                out_items.append(it)
                kept += 1
            summary.append({"vendor": vendor, "url": used or url, "status": st,
                            "count": kept, "prereleases_skipped": pre, "error": err})
    out_items.sort(key=lambda i: (i["date"] or "9999", i["vendor"]), reverse=True)
    return {"since": since, "fetched_at": datetime.date.today().isoformat(),
            "items": out_items, "sources": summary}


def main():
    ap = argparse.ArgumentParser(description="stack-watch source fetcher")
    ap.add_argument("sources_json")
    ap.add_argument("--since", required=True, help="YYYY-MM-DD, inclusive")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--max-body", type=int, default=1500)
    ap.add_argument("--include-prereleases", action="store_true")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.since):
        print("error: --since must be YYYY-MM-DD", file=sys.stderr)
        sys.exit(2)
    try:
        with open(args.sources_json, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    out = collect(doc, args.since, args.timeout, args.max_body,
                  include_prereleases=args.include_prereleases)
    print(json.dumps(out, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
