---
name: stack-watch
description: Discover a project's technology stack, maintain a STACK.md reference, probe every vendor's public changelog and release notes for changes that affect the stack, and propose tickets for the ones that matter. Use this skill whenever the user asks to check vendor updates, review the stack, look for deprecations or breaking changes, asks what changed at a vendor in the stack (Vercel, Next.js, Neon, Drizzle, Google Analytics, and so on), wants to build or refresh STACK.md, or says "run stack-watch". Also use it when the user was surprised by a vendor change and wants to catch the next one earlier.
---

# stack-watch

Give a project a proactive posture on vendor changes: deprecations, sunsets, breaking API or SDK changes, pricing or limit changes, security advisories, and new features worth adopting. The typical failure this prevents: a vendor changes something (an analytics collect endpoint, a free-tier limit, a default), the change is announced in a changelog nobody reads, and the team finds out weeks later from broken data.

All paths to `scripts/`, `references/`, and `assets/` below are relative to this skill's directory.

## Requirements

1. Python 3.9 or newer (standard library only; the scripts have no dependencies).
2. Web access for probing vendor sources.
3. Optional: access to an issue tracker (Asana, Linear, or GitHub Issues through MCP tools or the `gh` CLI). Without one, tickets are written to a markdown file in the repo.
4. A JavaScript or TypeScript project with a `package.json`. Other ecosystems are not scanned yet.
5. One repo per run. The repo path is an argument; default is the current working directory.

## Operating rules

1. Manual trigger only. The skill never schedules itself.
2. Public web sources only: changelogs, release notes, engineering blogs, GitHub releases and security advisories, package-manager advisories. Email notices are out of scope; this is an accepted gap and every report says so.
3. STACK.md is a starting hypothesis, not the truth. Other people change the repo. Every run rescans and diffs.
4. Ticket creation is never automatic. Present the proposal table, stop, and wait for the user to select item numbers. Only then write tickets.
5. Never read `.env`, `.env.local`, or any other real env file. Env var names only, from example files and source references. `scan_repo.py` enforces this; do not work around it.
6. Track only technology that exists in the stack: a vendor belongs in sources.json and gets probed only when the scan detects it or a hand-confirmed STACK.md row names it. Ignore vendors that appear only in docs, notes, roadmaps, or `references/vendor-sources.md`. Example: an auth vendor the team plans to adopt is not tracked until its package is installed.

## Files this skill owns in the target repo

All are meant to be committed so every contributor can read and correct them.

| # | Path | Purpose | Written by |
|---|---|---|---|
| 1 | `STACK.md` (repo root) | Stack reference. Structure: `references/stack-md-template.md` | Skill, except the hand-confirmed section |
| 2 | `stack-watch/config.json` | Ticket tracker settings | The user (skill creates it on bootstrap) |
| 3 | `stack-watch/sources.json` | Vendor to source-URL map | Skill on discovery; the user by hand for corrections |
| 4 | `stack-watch/ledger.json` | Every item ever seen, with decisions, plus run history | Skill only, via `scripts/ledger.py` |
| 5 | `stack-watch/reports/YYYY-MM-DD.md` | Per-run report, kept for audit | Skill only |
| 6 | `stack-watch/tickets.md` | Tickets, only when the tracker is `markdown` | Skill |

If the repo's `.gitignore` would exclude any of these, tell the user. Do not silently change `.gitignore`.

### config.json

```json
{
  "tracker": {
    "type": "markdown",
    "project": null
  }
}
```

`type` is one of `asana`, `linear`, `github`, `markdown`. `project` names the target: the Asana project name, the Linear team or project name, or `owner/repo` for GitHub. It is ignored for `markdown`. When the file is missing, use `markdown`. `references/ticket-conventions.md` describes what each tracker type writes.

## Mode selection

Bootstrap mode when the repo has no `STACK.md`, or when invoked with `--bootstrap`. Probe mode otherwise.

## Bootstrap mode

Build the stack reference, present it, stop. Do not probe on a bootstrap run.

1. Print the absolute repo path. Confirm it contains a `package.json`. Stop if not, and tell the user only JS and TS projects are supported.
2. Run `python3 scripts/scan_repo.py <repo> --pretty > <tmp>/scan.json`. It reads package.json, the lockfile (npm, pnpm, yarn, bun text lock), vercel.json, netlify.toml, wrangler config, next.config.*, drizzle.config.*, middleware.*, layout files for third-party script tags, env example files, and `process.env` / `import.meta.env` references. Every item carries a `detected_from` path.
3. Review the `analytics` and `external_domain` items: third-party services found by script-tag and snippet patterns (Google Analytics, Calendly, Plausible, PostHog, Sentry, Hotjar, Clarity, Segment, Meta Pixel, and any external script src in a layout file). Report each external domain found.
4. Write `STACK.md` at the repo root. Read `references/stack-md-template.md` first and copy its structure exactly; section titles and column headers are parsed by `diff_stack.py`, and the first column of every detected row must be the scan item's `name`, copied verbatim. Populate the detected sections from the scan JSON. In the hand-confirmed section, leave the prompt row from the template so the user knows to fill it.
5. Build `stack-watch/sources.json`. For each detected vendor, look it up in `references/vendor-sources.md` and copy the entry with status `verified`. For a vendor not listed there, search the web for "<vendor> changelog" and "<vendor> release notes", pick the most authoritative result (the vendor's own domain first), and add it with status `unverified`. Entry shape:

```json
{
  "vendor": "Vercel",
  "matches": ["vercel", "@vercel/*"],
  "sources": [
    {"type": "changelog", "url": "https://vercel.com/changelog", "feed": null, "verified": "2026-08-29"}
  ],
  "status": "verified"
}
```

   Prefer feed URLs (RSS or Atom) over HTML pages when one exists; set `feed` to null when none does. `status` is `verified`, `unverified`, or `retired`.
6. Create `stack-watch/config.json` with the markdown tracker default if it does not exist, and ask the user which tracker they want.
7. Run `python3 scripts/ledger.py stack-watch/ledger.json record-run bootstrap null 0 0`.
8. Show STACK.md and sources.json in full. Ask the user to confirm, correct, and fill the hand-confirmed section. Stop. Do not probe.

## Probe mode

1. Load STACK.md, `stack-watch/config.json`, `stack-watch/sources.json`, `stack-watch/ledger.json`. If config.json, sources.json, or ledger.json is missing, create an empty or default one and say so.
2. Run `scan_repo.py` again; the stack may have changed since the last run.
3. Read git history since `last_scanned` from STACK.md frontmatter: `git log --since=<last_scanned> --name-only` filtered to dependency and config files (package.json, lockfiles, `*.config.*`, vercel.json, middleware.*). Summarize which files changed, how many commits, and which authors. This surfaces changes made by other contributors.
4. Run `python3 scripts/diff_stack.py <scan.json> STACK.md --pretty`. Exit code 0 means no drift, 3 means drift was found (both are success), 1 or 2 is an error. Output keys: `added`, `version_changed`, `missing_first_time`, `missing_second_time`, `hand_confirmed_overlap`, `summary`.
5. Update STACK.md: apply `added` and `version_changed` rows; append `(not found in repo, first missed YYYY-MM-DD)` to the Detected from cell of `missing_first_time` rows; remove `missing_second_time` rows. Never touch the hand-confirmed section. Update `last_scanned`.
6. Add sources.json entries for new vendors (same lookup as bootstrap step 5). New vendors get status `unverified` and a callout in the report.
7. Decide the lookback window from `python3 scripts/ledger.py stack-watch/ledger.json last-probed`. The ledger is the only record of probe dates. If it prints `null`, use 90 days. Otherwise start 3 days before that date (ledger dedupe absorbs the overlap).
8. Fetch each source in sources.json. Prefer the feed URL, fall back to the HTML page, and for GitHub use the releases feed or API. Collect title, date, URL, and body text per item within the window. Skip status `retired`. Fetch status `unverified` sources too, but mark their items "from unverified source". If a source is unreachable, note it in the report and continue.
9. Run the package manager's audit for the detected lockfile: `npm audit --json`, `pnpm audit --json`, `yarn npm audit --json` (Yarn 2+) or `yarn audit --json` (Yarn 1), `bun audit --json` where supported. Each advisory is an item with severity Security.
10. Dedupe against the ledger. The hash is sha256 of `vendor|url|title` (`ledger.py <ledger> hash <vendor> <url> <title>`). Drop items whose ledger decision is `ticketed`, `dismissed`, or `auto-dismissed`. Re-show `watch` items with the note "previously watched" and `pending` items with "previously proposed, awaiting decision".
11. Classify each new item. Read `references/severity-rubric.md` and follow it. Severities: Security, Breaking, Deprecation, Pricing or limits, Opportunity, Noise.
12. Map each non-Noise item to the stack: which STACK.md row it touches, which repo files or routes are affected (grep the repo for the package import, config key, or script domain), and the vendor-stated deadline, if any. An item that touches nothing in STACK.md is downgraded to Noise, unless it is Security.
13. Write the report to `stack-watch/reports/YYYY-MM-DD.md` using `assets/report-template.md`: run metadata, drift table, unverified sources needing review, proposal table, accepted-gap reminder.
14. Record the run and every collected item in the ledger: `ledger.py <ledger> record-run probe <lookback_from> <items_seen> <items_proposed>`, then pipe a JSON array of all items to `ledger.py <ledger> add`. Noise items get `"decision": "auto-dismissed"`; proposed items default to `pending`. Doing this before waiting on the user means an interrupted session still leaves an accurate ledger.
15. Print the proposal table in chat, sorted Security, Breaking, Deprecation, Pricing or limits, Opportunity, and by earliest deadline within a severity. Then say: "Reply with item numbers to ticket, W plus item number to watch, D plus item number to dismiss." Stop and wait.
16. On selection, read `references/ticket-conventions.md` and write the tickets it prescribes for the configured tracker, one item at a time. Confirm each ticket URL (or tickets.md anchor) back in chat.
17. Update decisions: `ledger.py <ledger> set-decision <hash> ticketed <ticket_url>`, `watch`, or `dismissed` per the user's reply. Unselected items stay `pending`.

## Proposal table columns

In order: #, Vendor, Severity, Change (one or two plain sentences), Impact on this project (what breaks, changes, or becomes possible; name affected files or routes), Proposed action (imperative, matches the ticket title), Effort (S under 2 hours, M half a day to a day, L multi-day), Deadline (vendor-stated date or "none stated"), Source (URL), Confidence (high, moderate, low, unknown; confidence in the impact assessment, not in whether the vendor change is real), Note ("from unverified source", "previously watched", or "previously proposed, awaiting decision", else blank). Numbering restarts at 1 each run; the report filename gives the run context.

## Reference files

| # | File | Read when |
|---|---|---|
| 1 | `references/stack-md-template.md` | Writing or rewriting STACK.md |
| 2 | `references/vendor-sources.md` | Building or extending sources.json |
| 3 | `references/severity-rubric.md` | Classifying probe items |
| 4 | `references/ticket-conventions.md` | Writing any ticket |
| 5 | `assets/report-template.md` | Writing the per-run report |
