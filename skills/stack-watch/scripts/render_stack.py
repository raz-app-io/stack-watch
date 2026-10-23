#!/usr/bin/env python3
"""stack-watch STACK.md renderer.

Writes STACK.md from scan_repo.py output. With --existing it merges into the
current file instead of starting over:

  * the "Hand-confirmed external services" section is copied verbatim
  * rows the scan no longer finds are flagged "(not found in repo, first
    missed YYYY-MM-DD)" once, and removed on the second consecutive miss
  * versions and "Detected from" paths are refreshed, "Last verified" is today
  * context columns people may have edited by hand (Plan or tier,
    Integration method, the Vendor derived from a driver or SDK) are kept

Usage:
    python3 render_stack.py <scan.json> [--existing STACK.md] [--out STACK.md]
                            [--project NAME] [--repo-path PATH]

Without --out the result is printed to stdout. Section titles and column
headers follow references/stack-md-template.md; diff_stack.py parses them by
name. Standard library only.
"""

import argparse
import datetime
import fnmatch
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diff_stack  # noqa: E402  (shared section contract)

SCHEMA_VERSION = 1

COLUMNS = {
    "Runtime": ["Name", "Version", "Detected from", "Last verified"],
    "Framework": ["Name", "Version", "Detected from", "Last verified"],
    "Hosting and deployment": ["Vendor", "Plan or tier", "Detected from", "Last verified"],
    "Database": ["Vendor", "Driver package", "Driver version", "Detected from", "Last verified"],
    "ORM and data layer": ["Name", "Version", "Detected from", "Last verified"],
    "Authentication": ["Vendor", "SDK package", "SDK version", "Detected from", "Last verified"],
    "Analytics and search": ["Name", "Integration method", "Detected from", "Last verified"],
    "Key packages": ["Package", "Pinned version", "Category", "Detected from"],
    "Environment variable names": ["Name", "Detected from"],
}
HAND_SECTION = diff_stack.HAND_SECTION
HAND_COLUMNS = ["Vendor", "Purpose", "Integration method", "Source", "Last verified"]

# Columns whose value a person may have corrected by hand. When the row
# already exists, the existing value wins over the derived one.
KEEP_EXISTING = {"Plan or tier", "Integration method", "Vendor"}

# Older STACK.md files used "Vendor" as the Analytics key column.
HEADER_ALIASES = {"Name": ["Vendor"]}

# Driver or SDK package -> vendor shown in the Database and Authentication
# sections. First match wins.
VENDOR_HINTS = [
    ("@neondatabase/*", "Neon"),
    ("@planetscale/*", "PlanetScale"),
    ("@upstash/*", "Upstash"),
    ("@libsql/*", "Turso (libSQL)"),
    ("@supabase/*", "Supabase"),
    ("pg", "Postgres (host unknown)"),
    ("postgres", "Postgres (host unknown)"),
    ("mysql2", "MySQL (host unknown)"),
    ("better-sqlite3", "SQLite (local file)"),
    ("mongodb", "MongoDB"),
    ("redis", "Redis (host unknown)"),
    ("@clerk/*", "Clerk"),
    ("next-auth", "Auth.js"),
    ("@auth/*", "Auth.js"),
    ("auth0", "Auth0"),
    ("@auth0/*", "Auth0"),
    ("firebase-admin", "Firebase"),
    ("lucia", "Lucia"),
    ("@workos-inc/*", "WorkOS"),
    ("passport", "Passport"),
]

INTRO = ("This file is maintained by the stack-watch skill. It is a starting "
         "hypothesis, not the truth: every run rescans the repo and diffs against "
         "this file. Contributors: correct anything wrong here, and add services "
         "the scan cannot see to the last section.")
ENV_NOTE = "Names only. Values are never recorded here."
HAND_NOTE = ("Maintained by hand. The scan never edits this section. Add services "
             "here that the scan cannot detect (analytics accounts, DNS, email, "
             "booking, hosting plan or tier).")
HAND_PROMPT_ROW = ["none yet", "add services the scan cannot see", "", "", ""]
MISSED_FLAG = "(not found in repo, first missed {date})"


def vendor_hint(pkg):
    for pat, vendor in VENDOR_HINTS:
        if fnmatch.fnmatch(pkg, pat) if any(c in pat for c in "*?[") else pkg == pat:
            return vendor
    return "unknown"


def cell(row, col):
    """Read a column from a parsed existing row, honoring header aliases."""
    for name in [col] + HEADER_ALIASES.get(col, []):
        if row.get(name):
            return row[name].strip()
    return ""


def version_text(v):
    return str(v) if v not in (None, "") else "n/a"


def derive_row(section, item, today):
    """Build {column: value} for one scan item."""
    name = item["name"]
    ver = version_text(item.get("version"))
    src = item.get("detected_from", "")
    if section == "Hosting and deployment":
        return {"Vendor": name, "Plan or tier": "unknown", "Detected from": src,
                "Last verified": today}
    if section == "Database":
        return {"Vendor": vendor_hint(name), "Driver package": name,
                "Driver version": ver, "Detected from": src, "Last verified": today}
    if section == "Authentication":
        return {"Vendor": vendor_hint(name), "SDK package": name, "SDK version": ver,
                "Detected from": src, "Last verified": today}
    if section == "Analytics and search":
        method = item.get("integration") or ("npm package (dev)" if item.get("dev")
                                             else "npm package")
        return {"Name": name, "Integration method": method, "Detected from": src,
                "Last verified": today}
    if section == "Key packages":
        return {"Package": name, "Pinned version": ver,
                "Category": item.get("category", "other"), "Detected from": src}
    if section == "Environment variable names":
        return {"Name": name, "Detected from": src}
    return {"Name": name, "Version": ver, "Detected from": src, "Last verified": today}


def merge_rows(section, scan_rows, existing_rows, today):
    """scan_rows: {norm_key: item}; existing_rows: {norm_key: parsed row}.
    Returns an ordered list of {column: value} rows."""
    cols = COLUMNS[section]
    key_col = cols[0] if section not in ("Database", "Authentication") else cols[1]
    out = []
    for key in sorted(scan_rows):
        row = derive_row(section, scan_rows[key], today)
        old = existing_rows.get(key)
        if old:
            for col in cols:
                if col in KEEP_EXISTING and col != key_col and cell(old, col):
                    row[col] = cell(old, col)
        out.append(row)
    for key, old in existing_rows.items():
        if key in scan_rows:
            continue
        if old.get("_first_missed"):
            continue  # second consecutive miss: remove the row
        row = {col: cell(old, col) for col in cols}
        row[key_col] = row[key_col] or old.get(key_col, key)
        row["Detected from"] = (row["Detected from"] + " "
                                + MISSED_FLAG.format(date=today)).strip()
        out.append(row)
    return out


def table(cols, rows):
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    if not rows:
        rows = [{cols[0]: "none detected"}]
    for r in rows:
        if isinstance(r, list):
            vals = r
        else:
            vals = [str(r.get(c, "") or "") for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def hand_section_text(existing_text):
    """Return the hand-confirmed section verbatim (heading included), or None."""
    if not existing_text:
        return None
    m = re.search(r"^## " + re.escape(HAND_SECTION) + r"\s*$", existing_text, re.M)
    if not m:
        return None
    rest = existing_text[m.start():]
    nxt = re.search(r"^## ", rest[3:], re.M)
    block = rest[: nxt.start() + 3] if nxt else rest
    return block.rstrip() + "\n"


def default_hand_section():
    return "## {}\n\n{}\n\n{}\n".format(
        HAND_SECTION, HAND_NOTE, table(HAND_COLUMNS, [HAND_PROMPT_ROW]))


def relative_repo_path(abs_path):
    """Path of the scanned repo relative to its git toplevel ("." at the root),
    so STACK.md never records a contributor's home directory. Falls back to
    the directory name when git is unavailable."""
    if not abs_path:
        return "."
    try:
        top = subprocess.run(["git", "-C", abs_path, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if top.returncode == 0 and top.stdout.strip():
            rel = os.path.relpath(os.path.realpath(abs_path), os.path.realpath(top.stdout.strip()))
            return rel.replace(os.sep, "/")
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.basename(abs_path.rstrip("/")) or "."


def render(scan, existing_text=None, project=None, today=None, repo_path=None):
    today = today or datetime.date.today().isoformat()
    existing = diff_stack.parse_stack_md_text(existing_text) if existing_text else {}
    fm = parse_frontmatter(existing_text) if existing_text else {}
    scan_rows = {}
    for item in scan.get("items", []):
        section = diff_stack.SCAN_TO_SECTION.get(item.get("section"))
        if section:
            scan_rows.setdefault(section, {})[diff_stack.norm(item["name"])] = item

    scan_path = scan.get("repo_path", "")
    repo_path = repo_path or fm.get("repo_path") or relative_repo_path(scan_path)
    project = (project or fm.get("project")
               or os.path.basename(scan_path.rstrip("/")) or "project")
    parts = ["---",
             f"project: {project}",
             f"repo_path: {repo_path}",
             f"last_scanned: {today}",
             f"schema_version: {fm.get('schema_version', SCHEMA_VERSION)}",
             "---", "", "# Technology Stack", "", INTRO, ""]
    for section, cols in COLUMNS.items():
        rows = merge_rows(section, scan_rows.get(section, {}), existing.get(section, {}), today)
        parts.append(f"## {section}")
        parts.append("")
        if section == "Environment variable names":
            parts.extend([ENV_NOTE, ""])
        parts.append(table(cols, rows))
        parts.append("")
    parts.append(hand_section_text(existing_text) or default_hand_section())
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description="stack-watch STACK.md renderer")
    ap.add_argument("scan_json")
    ap.add_argument("--existing", help="current STACK.md to merge into")
    ap.add_argument("--out", help="write here instead of stdout")
    ap.add_argument("--project", help="project name for the frontmatter")
    ap.add_argument("--repo-path", help="repo_path for the frontmatter (default: the existing "
                    "value, else the scanned directory relative to its git toplevel)")
    args = ap.parse_args()

    try:
        with open(args.scan_json, encoding="utf-8") as f:
            scan = json.load(f)
        existing_text = None
        if args.existing and os.path.isfile(args.existing):
            with open(args.existing, encoding="utf-8") as f:
                existing_text = f.read()
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    if "error" in scan:
        print(f"error: scan failed: {scan['error']}", file=sys.stderr)
        sys.exit(1)

    text = render(scan, existing_text, args.project, repo_path=args.repo_path)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
