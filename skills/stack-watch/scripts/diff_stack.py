#!/usr/bin/env python3
"""stack-watch drift detector.

Compares a scan_repo.py JSON output against an existing STACK.md and prints a
drift table as JSON. STACK.md section titles and column headers are a contract
(see references/stack-md-template.md); this script parses them by name.

Usage:
    python3 diff_stack.py <scan.json> <STACK.md> [--pretty]

Output keys:
    added               in the scan, not in STACK.md
    version_changed     same item, different version
    missing_first_time  in a detected STACK.md section, not in the scan,
                        not previously flagged: flag it, do not delete
    missing_second_time in STACK.md, not in the scan, already flagged from a
                        prior run: eligible for removal
    hand_confirmed_overlap  hand-entered vendor that the scan also detected
                        (informational; the hand section is never edited)
    summary             count per key

Exit codes: 0 no drift, 3 drift found (both success), 1 or 2 error.

Standard library only.
"""

import argparse
import json
import re
import sys

# Section title -> (key column, version column or None)
SECTION_SPECS = {
    "Runtime": ("Name", "Version"),
    "Framework": ("Name", "Version"),
    "Hosting and deployment": ("Vendor", None),
    "Database": ("Driver package", "Driver version"),
    "ORM and data layer": ("Name", "Version"),
    "Authentication": ("SDK package", "SDK version"),
    "Analytics and search": ("Name", None),
    "Key packages": ("Package", "Pinned version"),
    "Environment variable names": ("Name", None),
}
HAND_SECTION = "Hand-confirmed external services"

SCAN_TO_SECTION = {
    "runtime": "Runtime",
    "framework": "Framework",
    "hosting": "Hosting and deployment",
    "database": "Database",
    "orm": "ORM and data layer",
    "auth": "Authentication",
    "analytics": "Analytics and search",
    "key_package": "Key packages",
    "env_var": "Environment variable names",
    # external_domain items are context for the analytics rows, not diffed
}

MISSED_FLAG_RE = re.compile(r"\(not found in repo, first missed (\d{4}-\d{2}-\d{2})\)")
EMPTY_ROW_VALUES = {"", "none detected", "none yet", "n/a"}


def norm(s):
    s = (s or "").strip()
    s = s.replace(" (inferred)", "")
    return s.lower()


def parse_stack_md(path):
    """Return {section: {norm_key: row_dict}} for known sections."""
    with open(path, encoding="utf-8") as f:
        return parse_stack_md_text(f.read())


def parse_stack_md_text(text):
    lines = text.splitlines()
    sections = {}
    current = None
    header = None
    for line in lines:
        h = re.match(r"^##\s+(.*)$", line)
        if h:
            title = h.group(1).strip()
            current = title if (title in SECTION_SPECS or title == HAND_SECTION) else None
            header = None
            if current:
                sections.setdefault(current, {})
            continue
        if current is None or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        row = dict(zip(header, cells + [""] * (len(header) - len(cells))))
        key_col = (SECTION_SPECS.get(current) or ("Vendor", None))[0]
        key = row.get(key_col, "")
        if norm(key) in EMPTY_ROW_VALUES:
            continue
        flag = MISSED_FLAG_RE.search(" ".join(row.values()))
        row["_first_missed"] = flag.group(1) if flag else None
        sections[current][norm(key)] = row
    return sections


def scan_to_rows(scan):
    """Return {section: {norm_key: (name, version)}} from scan JSON."""
    out = {}
    for item in scan.get("items", []):
        section = SCAN_TO_SECTION.get(item.get("section"))
        if not section:
            continue
        version = item.get("version")
        out.setdefault(section, {})[norm(item["name"])] = (item["name"], version)
    return out


def main():
    ap = argparse.ArgumentParser(description="stack-watch drift detector")
    ap.add_argument("scan_json")
    ap.add_argument("stack_md")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    try:
        with open(args.scan_json, encoding="utf-8") as f:
            scan = json.load(f)
        stack = parse_stack_md(args.stack_md)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    if "error" in scan:
        print(f"error: scan failed: {scan['error']}", file=sys.stderr)
        sys.exit(1)

    scan_rows = scan_to_rows(scan)
    drift = {"added": [], "version_changed": [], "missing_first_time": [],
             "missing_second_time": [], "hand_confirmed_overlap": []}

    for section, (key_col, ver_col) in SECTION_SPECS.items():
        stack_rows = stack.get(section, {})
        srows = scan_rows.get(section, {})
        for k, (name, version) in srows.items():
            if k not in stack_rows:
                drift["added"].append({"section": section, "item": name,
                                       "version": version})
            elif ver_col:
                stack_ver = stack_rows[k].get(ver_col, "").strip()
                if stack_ver and version and stack_ver != str(version):
                    drift["version_changed"].append(
                        {"section": section, "item": name,
                         "stack_md": stack_ver, "repo": version})
        for k, row in stack_rows.items():
            if k not in srows:
                entry = {"section": section, "item": row.get(key_col, k)}
                if row.get("_first_missed"):
                    entry["first_missed"] = row["_first_missed"]
                    drift["missing_second_time"].append(entry)
                else:
                    drift["missing_first_time"].append(entry)

    # Hand-confirmed overlap: hand vendor names that also show up anywhere in
    # the scan (any section). Informational only.
    scan_names = {norm(i["name"]) for i in scan.get("items", [])}
    for k, row in stack.get(HAND_SECTION, {}).items():
        if k in scan_names:
            drift["hand_confirmed_overlap"].append({"vendor": row.get("Vendor", k)})

    drift["summary"] = {k: len(v) for k, v in drift.items() if isinstance(v, list)}
    print(json.dumps(drift, indent=2 if args.pretty else None))
    has_drift = any(drift[k] for k in ("added", "version_changed",
                                       "missing_first_time", "missing_second_time"))
    sys.exit(0 if not has_drift else 3)


if __name__ == "__main__":
    main()
