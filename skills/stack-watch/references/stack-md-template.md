# STACK.md template

`scripts/render_stack.py` writes STACK.md in this exact structure, from a scan and (on later runs) the existing file. Read this when you need to understand or explain the file, or when editing it by hand. The section titles and column headers are a contract: `scripts/diff_stack.py` parses them by name. Do not rename sections or columns.

Rules that keep the file trustworthy:

1. The first column of a detected row is the scan item's `name`, copied verbatim (for example `@vercel/analytics`, `Google Analytics`, `Vercel (inferred)`). `diff_stack.py` matches rows on that value. Edit the other columns freely; `render_stack.py` keeps hand edits to `Plan or tier`, `Integration method`, and the derived `Vendor` of a driver or SDK.
2. Every detected row carries a `Detected from` path so a reader can audit the claim.
3. Every row carries a `Last verified` date so stale rows are visible.
4. The "Hand-confirmed external services" section is protected. The skill reads it and reports overlaps with the scan, but never deletes or rewrites rows there. Only people edit it. Until someone fills it, it holds the prompt row `none yet`.
5. Versions in detected sections are the exact locked versions from the lockfile when available, otherwise the declared range. Config-file rows (for example `Next.js config`) show `n/a`.
6. A row in a detected section that the scan cannot find is flagged with `(not found in repo, first missed YYYY-MM-DD)` appended to its `Detected from` cell. `render_stack.py` removes the row only after it has been missing for two consecutive runs.

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

Notes:

7. Empty sections keep their heading and header row so the structure stays diffable, with a single row `| none detected | ... |` padded to the column count.
8. In the Database and Authentication sections the vendor is derived from the driver or SDK package (`@neondatabase/serverless` means Neon, `pg` alone means "Postgres (host unknown)"). When no rule matches, the vendor is `unknown`; correct it by hand and the correction is kept.
9. Probe dates are not stored here. `stack-watch/ledger.json` is the only record of when the last probe ran.
