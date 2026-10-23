#!/usr/bin/env python3
"""stack-watch proposal ranking.

Turns the proposals Claude drafted into a scored, graded, sorted table.
Claude supplies the judgment fields; this script does the arithmetic the
same way every run.

Usage:
    python3 rank.py <proposals.json> [--today YYYY-MM-DD] [--format md|json|both] [--pretty]

Input: a JSON array of proposals, each with
    vendor, severity        Security | Breaking | Deprecation | Pricing or limits | Opportunity
    impact                  severe | major | moderate | minor   (what happens if ignored)
    advisory_severity       critical | high | moderate | low     (Security only; overrides impact)
    exposure                confirmed | likely | unclear         (does it apply to this repo)
    deadline                YYYY-MM-DD or null                   (vendor-stated date)
    fix_available           true when a fixed version or replacement already exists
    pricing_direction       increase | favorable | neutral       (Pricing only)
    effort                  S | M | L
    confidence              high | moderate | low | unknown
    change, impact_text, action, source, note                   (table prose)
    items                   optional list of ledger hashes the row covers

Score (0 to 10) = severity base + impact + exposure + urgency - effort cost.
    base:     Security 4, Breaking 3.5, Deprecation 3, Pricing increase 2.5,
              Pricing neutral 2, Pricing favorable 1.5, Opportunity 1
    impact:   severe/critical 3, major/high 2, moderate 1, minor/low 0
    exposure: confirmed 2, likely 1, unclear 0
    urgency:  deadline past or within 14 days 2; within 90 days, or a
              security or deprecation fix already available 1; else 0
    effort:   Pricing and Opportunity only: S 0, M -0.5, L -1
Grade: A >= 8, B >= 6, C >= 4, D below. Low or unknown confidence adds "?".
Default: A and B -> ticket, C -> ticket (backlog), D -> watch.
Sort: score desc, then effort asc, then earliest deadline.
Standard library only.
"""

import argparse
import datetime
import json
import sys

BASE = {"Security": 4.0, "Breaking": 3.5, "Deprecation": 3.0, "Opportunity": 1.0}
PRICING_BASE = {"increase": 2.5, "neutral": 2.0, "favorable": 1.5}
IMPACT = {"severe": 3, "major": 2, "moderate": 1, "minor": 0}
ADVISORY = {"critical": 3, "high": 2, "moderate": 1, "medium": 1, "low": 0}
EXPOSURE = {"confirmed": 2, "likely": 1, "unclear": 0}
EFFORT_COST = {"S": 0.0, "M": 0.5, "L": 1.0}
EFFORT_ORDER = {"S": 0, "M": 1, "L": 2}
GRADES = [(8.0, "A"), (6.0, "B"), (4.0, "C"), (0.0, "D")]
DEFAULTS = {"A": "ticket", "B": "ticket", "C": "ticket (backlog)", "D": "watch"}
COLUMNS = ["#", "Grade", "Score", "Vendor", "Severity", "Change", "Impact on this project",
           "Proposed action", "Effort", "Deadline", "Source", "Confidence", "Default", "Note"]


def days_until(deadline, today):
    if not deadline:
        return None
    try:
        return (datetime.date.fromisoformat(deadline) - datetime.date.fromisoformat(today)).days
    except ValueError:
        return None


def deadline_text(deadline, today):
    d = days_until(deadline, today)
    if deadline and d is None:
        return deadline
    if d is None:
        return "none stated"
    if d < -1:
        return f"{deadline} ({-d} days ago)"
    if d == -1:
        return f"{deadline} (yesterday)"
    if d == 0:
        return f"{deadline} (today)"
    if d == 1:
        return f"{deadline} (tomorrow)"
    return f"{deadline} ({d} days)"


def severity_label(p):
    sev = p.get("severity", "")
    if sev == "Pricing or limits" and p.get("pricing_direction") in PRICING_BASE:
        return f"Pricing ({p['pricing_direction']})"
    return sev


def score(p, today):
    sev = p.get("severity", "")
    if sev == "Pricing or limits":
        base = PRICING_BASE.get(p.get("pricing_direction", "neutral"), 2.0)
    else:
        base = BASE.get(sev)
    if base is None:
        raise ValueError(f"unknown severity: {sev!r}")
    if sev == "Security" and p.get("advisory_severity"):
        impact = ADVISORY.get(str(p["advisory_severity"]).lower())
        if impact is None:
            raise ValueError(f"unknown advisory_severity: {p['advisory_severity']!r}")
    else:
        impact = IMPACT.get(str(p.get("impact", "")).lower())
        if impact is None:
            raise ValueError(f"unknown impact: {p.get('impact')!r}")
    exposure = EXPOSURE.get(str(p.get("exposure", "")).lower())
    if exposure is None:
        raise ValueError(f"unknown exposure: {p.get('exposure')!r}")
    d = days_until(p.get("deadline"), today)
    if d is not None and d <= 14:
        urgency = 2
    elif (d is not None and d <= 90) or (sev in ("Security", "Deprecation") and p.get("fix_available")):
        urgency = 1
    else:
        urgency = 0
    effort = str(p.get("effort", "M")).upper()
    if effort not in EFFORT_COST:
        raise ValueError(f"unknown effort: {p.get('effort')!r}")
    cost = EFFORT_COST[effort] if sev in ("Pricing or limits", "Opportunity") else 0.0
    total = min(10.0, max(0.0, base + impact + exposure + urgency - cost))
    return round(total, 1), {"base": base, "impact": impact, "exposure": exposure,
                             "urgency": urgency, "effort_cost": cost}


def grade_for(value, confidence):
    letter = next(g for floor, g in GRADES if value >= floor)
    if str(confidence or "").lower() in ("low", "unknown"):
        letter += "?"
    return letter


def rank(proposals, today=None):
    today = today or datetime.date.today().isoformat()
    rows = []
    for p in proposals:
        value, parts = score(p, today)
        letter = grade_for(value, p.get("confidence"))
        rows.append(dict(p, score=value, score_parts=parts, grade=letter,
                         default=DEFAULTS[letter[0]],
                         deadline_text=deadline_text(p.get("deadline"), today),
                         severity_label=severity_label(p)))
    rows.sort(key=lambda r: (-r["score"], EFFORT_ORDER.get(str(r.get("effort", "M")).upper(), 1),
                             r.get("deadline") or "9999-12-31", r.get("vendor", "")))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def summary(rows):
    counts = {g: 0 for g in "ABCD"}
    for r in rows:
        counts[r["grade"][0]] += 1
    tickets = sum(1 for r in rows if r["default"].startswith("ticket"))
    watch = sum(1 for r in rows if r["default"] == "watch")
    parts = [f"{counts[g]} {g}" for g in "ABCD" if counts[g]]
    return (f"{len(rows)} proposals: {', '.join(parts) or 'none'}. Defaults create {tickets} ticket(s)"
            f" and watch {watch}. Reply with item numbers to ticket, W plus item number to watch,"
            f" D plus item number to dismiss, or `defaults` to accept the Default column.")


def cell(v):
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def markdown(rows):
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for r in rows:
        lines.append("| " + " | ".join(cell(x) for x in [
            r["rank"], r["grade"], f"{r['score']:.1f}", r.get("vendor"), r["severity_label"],
            r.get("change"), r.get("impact_text"), r.get("action"), str(r.get("effort", "")).upper(),
            r["deadline_text"], r.get("source"), r.get("confidence"), r["default"], r.get("note")]) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="stack-watch proposal ranking")
    ap.add_argument("proposals_json")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--format", choices=["md", "json", "both"], default="both")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    try:
        with open(args.proposals_json, encoding="utf-8") as f:
            proposals = json.load(f)
        if isinstance(proposals, dict):
            proposals = proposals.get("proposals", [])
        rows = rank(proposals, args.today)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    if args.format in ("md", "both"):
        print(summary(rows))
        print()
        print(markdown(rows))
    if args.format == "both":
        print()
    if args.format in ("json", "both"):
        print(json.dumps(rows, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
