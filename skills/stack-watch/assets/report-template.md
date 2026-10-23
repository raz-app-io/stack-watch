# stack-watch run report: <YYYY-MM-DD>

<!-- Copy this skeleton to stack-watch/reports/YYYY-MM-DD.md and fill every section. Keep the section order. -->

## Run metadata

| # | Field | Value |
|---|---|---|
| 1 | Run date | <ISO date> |
| 2 | Mode | probe or bootstrap |
| 3 | Repo | <repo path> |
| 4 | Lookback window | <start date> to <run date> (<basis: first probe 90 days, or last_probed minus 3 days overlap>) |
| 5 | Sources probed | <n> ok, <n> read directly (HTML), <n> skipped (retired or command), <n> unreachable; <n> prereleases left out |
| 6 | Items collected | <n> collected (<n> from feeds, <n> read directly, <n> advisories via <OSV.dev or package manager>, <n> lifecycle), <n> new after ledger dedupe, <n> re-shown, <n> auto-dismissed as Noise, <n> proposed |

## Stack drift since last scan

<!-- Output of diff_stack.py plus the git history summary (probe step 3). If no drift, say "No drift detected." and keep the git summary. -->

| # | Change type | Section | Item | Detail |
|---|---|---|---|---|

Git activity on dependency and config files since last scan: <n> commits by <authors>. <One sentence on what changed, or "none".>

## Lifecycle

<!-- The eol and versions tables from lifecycle.py. Keep the rows; add nothing. -->

| # | Product | Pinned | Cycle | Status | End of life | Latest in cycle | Supported newer lines |
|---|---|---|---|---|---|---|---|

| # | Package | Pinned | Latest in major | Latest | Majors behind | Deprecated on npm |
|---|---|---|---|---|---|---|

## Unverified sources needing review

<!-- Sources fetched with status "unverified". Ask the user to confirm or correct each. If none, say "None." -->

| # | Vendor | URL | Why unverified |
|---|---|---|---|

## Proposals

<!-- Paste rank.py's summary line and table as printed: sorted by score, then effort, then deadline. Numbering restarts at 1 every run. -->

<summary line from rank.py>

| # | Grade | Score | Vendor | Severity | Change | Impact on this project | Proposed action | Effort | Deadline | Source | Confidence | Default | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Reply with item numbers to ticket, W plus item number to watch, D plus item number to dismiss, or `defaults`. Example: `1, 3, W2, D4`.

### Classified as Noise (auto-dismissed, <n> items)

<!-- One or two sentences per vendor: what kind of items were dropped, and any notable item a reader might expect to see and why it did not qualify. -->

## Accepted gap reminder

This run probed public web sources only: changelogs, release notes, engineering blogs, GitHub releases and advisories, npm advisories. Email-first vendor notices are not covered. Some vendors announce sunsets by email before or instead of posting publicly.
