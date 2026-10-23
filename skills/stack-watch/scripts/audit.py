#!/usr/bin/env python3
"""stack-watch dependency audit.

Runs the package manager's audit for the lockfile found in the repo and
prints each advisory in the common item shape with severity "Security".

Usage:
    python3 audit.py <repo> [--pretty]
    python3 audit.py --input <saved-audit-output> [--format FORMAT] [--pretty]

Formats: npm (npm 7+ and bun), v6 (pnpm, Yarn 1 `auditAdvisory` lines),
berry (Yarn 2+ `yarn npm audit --json`). --format is detected from the
content when omitted.

Output:
    {"package_manager", "command", "items": [...], "error"}

Item fields: vendor (the package name), title, url, date (null), body,
severity "Security", advisory_severity, package, vulnerable_range, direct,
fix, source_type "advisory", hash. Standard library only.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import scan_repo  # noqa: E402

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
    if data is None or fmt in ("berry",):
        return parse_lines(text)
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
                try:
                    with open(os.path.join(repo, lf), encoding="utf-8", errors="replace") as f:
                        head = f.read(2000)
                except OSError:
                    head = ""
                if "__metadata" in head or os.path.isfile(os.path.join(repo, ".yarnrc.yml")):
                    return "yarn-berry"
            return name
    return None


def run_audit(repo, timeout=300):
    pm = detect_pm(repo)
    if not pm:
        return {"package_manager": None, "command": None, "items": [],
                "error": "no lockfile found"}
    cmd = COMMANDS[pm]
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"package_manager": pm, "command": " ".join(cmd), "items": [],
                "error": f"{cmd[0]} is not installed"}
    except subprocess.TimeoutExpired:
        return {"package_manager": pm, "command": " ".join(cmd), "items": [],
                "error": f"timed out after {timeout}s"}
    # Audits exit non-zero when they find anything; judge by the output.
    items = dedupe(parse_output(proc.stdout, FORMAT_FOR[pm]))
    error = None
    if not proc.stdout.strip():
        error = (proc.stderr.strip() or "no output")[:500]
    return {"package_manager": pm, "command": " ".join(cmd), "items": items, "error": error}


def main():
    ap = argparse.ArgumentParser(description="stack-watch dependency audit")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--input", help="parse a saved audit output instead of running one")
    ap.add_argument("--format", choices=["npm", "v6", "berry"])
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    if args.input:
        try:
            with open(args.input, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        out = {"package_manager": None, "command": f"--input {args.input}",
               "items": dedupe(parse_output(text, args.format)), "error": None}
    else:
        out = run_audit(os.path.abspath(args.repo))
    print(json.dumps(out, indent=2 if args.pretty else None, ensure_ascii=False))
    sys.exit(0 if out["error"] is None else 1)


if __name__ == "__main__":
    main()
