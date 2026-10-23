# STACK.md template

Read this when writing or rewriting a STACK.md. Copy the structure below exactly. The section titles and column headers are a contract: `scripts/diff_stack.py` parses them by name. Do not rename sections or columns.

Rules that keep the file trustworthy:

1. The first column of every detected row is the scan item's `name`, copied verbatim (for example `@vercel/analytics`, `Google Analytics`, `Vercel (inferred)`). `diff_stack.py` matches rows on that value, so a friendlier label would show up as drift on every run. Put human-friendly context in the other columns.
2. Every detected row carries a `Detected from` path so a reader can audit the claim.
3. Every row carries a `Last verified` date so stale rows are visible.
4. The "Hand-confirmed external services" section is protected. The skill reads it and reports overlaps with the scan, but never deletes or rewrites rows there. Only people edit it.
5. Versions in detected sections are the exact locked versions from the lockfile when available, otherwise the declared range.
6. A row in a detected section that the scan cannot find is flagged with `(not found in repo, first missed YYYY-MM-DD)` appended to its `Detected from` cell. Remove the row only after it has been missing for two consecutive runs.

Template starts below the rule.

---

```markdown
---
project: <repo name>
repo_path: <path the scan ran against>
last_scanned: <ISO date>
schema_version: 1
---

# Technology Stack

This file is maintained by the stack-watch skill. It is a starting hypothesis, not the truth: every run rescans the repo and diffs against this file. Contributors: correct anything wrong here, and add services the scan cannot see to the last section.

## Runtime

| Name | Version | Detected from | Last verified |
|---|---|---|---|

## Framework

| Name | Version | Detected from | Last verified |
|---|---|---|---|

## Hosting and deployment

| Vendor | Plan or tier | Detected from | Last verified |
|---|---|---|---|

## Database

| Vendor | Driver package | Driver version | Detected from | Last verified |
|---|---|---|---|---|

## ORM and data layer

| Name | Version | Detected from | Last verified |
|---|---|---|---|

## Authentication

| Vendor | SDK package | SDK version | Detected from | Last verified |
|---|---|---|---|---|

## Analytics and search

| Name | Integration method | Detected from | Last verified |
|---|---|---|---|

## Key packages

| Package | Pinned version | Category | Detected from |
|---|---|---|---|

## Environment variable names

Names only. Values are never recorded here.

| Name | Detected from |
|---|---|

## Hand-confirmed external services

Maintained by hand. The scan never edits this section. Add services here that the scan cannot detect (analytics accounts, DNS, email, booking, hosting plan or tier).

| Vendor | Purpose | Integration method | Source | Last verified |
|---|---|---|---|---|
```

Notes for the writer:

7. Empty sections keep their heading and header row so the structure stays diffable. Put a single row `| none detected | | | |` (padded to the column count) when a section has no entries.
8. In the Database section, derive the vendor from the driver package (`@neondatabase/serverless` means Neon, `pg` alone means "Postgres (host unknown)").
9. In the Authentication section, when nothing is detected write the `none detected` row. Do not guess a vendor.
10. Probe dates are not stored here. `stack-watch/ledger.json` is the only record of when the last probe ran.
