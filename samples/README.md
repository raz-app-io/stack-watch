# stack-watch in one run

Everything in this folder came out of one bootstrap and one probe run on [examples/sample-next-app](../examples/sample-next-app), a small Next.js 14 project with Vercel, Neon, Drizzle, Stripe, and a Google Analytics tag. Read this page to see what stack-watch produces before you run it on your own repo. Dates are from the run on 2026-10-22.

| File | Written by | What it is |
|---|---|---|
| [STACK.md](STACK.md) | bootstrap, refreshed by every probe | The stack reference that lives at your repo root |
| [sources.json](sources.json) | bootstrap | Which changelog or feed to read for each vendor |
| [config.json](config.json) | bootstrap | Ticket tracker setting |
| [report-2026-10-22.md](report-2026-10-22.md) | probe | The run report, with the graded proposal table |
| [proposals.json](proposals.json) | probe | The structured fields behind each proposal; `rank.py` turns them into the table |
| [tickets.md](tickets.md) | after you reply to the proposal table | Tickets, when the tracker is `markdown` |
| [ledger.json](ledger.json) | probe | Every item seen, your decision on it, run history |

In your repo these live at `STACK.md` and `stack-watch/{config,sources,ledger}.json`, `stack-watch/reports/YYYY-MM-DD.md`, `stack-watch/tickets.md`.

## 1. Bootstrap: STACK.md

The scanner reads `package.json`, the lockfile, config files, layout script tags, and env var names (never values). The renderer turns that into STACK.md. Two sections from the sample:

```markdown
## Database

| Vendor | Driver package | Driver version | Detected from | Last verified |
|---|---|---|---|---|
| Neon | @neondatabase/serverless | 0.10.4 | package.json + package-lock.json | 2026-10-22 |

## Analytics and search

| Name | Integration method | Detected from | Last verified |
|---|---|---|---|
| @vercel/analytics | npm package | package.json + package-lock.json | 2026-10-22 |
| Google Analytics | script tag or client snippet | app/layout.tsx | 2026-10-22 |
```

Every row says where it was found. The last section, **Hand-confirmed external services**, is yours: the skill never edits it. Put DNS, email, analytics accounts, and your hosting plan there; the skill probes those vendors too.

Full file: [STACK.md](STACK.md).

## 2. Bootstrap: sources.json

One entry per vendor in the stack. `feed` is what the fetcher reads (RSS, Atom, or a GitHub releases page). `feed: null` means an HTML page that Claude reads directly. `url_filter` narrows a feed that mixes a blog with a changelog.

```json
{
  "vendor": "Vercel",
  "matches": ["vercel", "@vercel/*", "vercel.json"],
  "sources": [
    {"type": "changelog", "url": "https://vercel.com/changelog", "feed": "https://vercel.com/atom", "url_filter": "/changelog/", "verified": "2026-10-22"}
  ],
  "status": "verified"
}
```

Vendors are added only when the scan finds them. The sample has ten: Vercel, Next.js, React, Node.js, Neon, Drizzle ORM, Stripe, Google Analytics, Tailwind CSS, TypeScript. Full file: [sources.json](sources.json).

## 3. Probe: the report

The probe rescans the repo, diffs it against STACK.md, fetches every source for the lookback window (90 days on the first run, then from three days before the last probe), runs `npm audit`, drops everything already in the ledger, classifies what is left, and writes a report. The sample run collected **375 items**, dismissed **315** as Noise, and proposed **7**. Each proposal is scored and graded by `rank.py` from five fields Claude sets (impact, exposure, deadline, fix available, effort); the fields for this run are in [proposals.json](proposals.json).

| # | Grade | Score | Vendor | Severity | Change | Proposed action | Effort | Deadline | Default |
|---|---|---|---|---|---|---|---|---|---|
| 1 | A | 10.0 | Next.js | Security | 33 advisories against `next` 14.2.21, 4 Critical; the 14.x line gets no more fixes | Upgrade next to 15.5.28 and React to 19 | L | none stated | ticket |
| 2 | A | 9.0 | Node.js | Security | Node 20 is end-of-life and unpatched for the October 2026 High CVEs | Move to Node.js 24 LTS | S | none stated | ticket |
| 3 | A | 9.0 | Drizzle ORM | Security | SQL injection advisory on `drizzle-orm` below 0.45.2 | Upgrade drizzle-orm to 0.45.4 | M | none stated | ticket |
| 4 | B | 6.5 | Vercel | Pricing (increase) | Deployment Storage billing starts, retention drops to 30 days on 2026-10-23 | Set a retention policy before 2026-10-23 | S | 2026-10-23 (tomorrow) | ticket |
| 5 | C | 4.0 | Google Analytics | Opportunity | Hostname Include filters (domain allowlist) now available | Add an Include filter for the production domain | S | none stated | ticket (backlog) |
| 6 | D | 3.5 | Stripe | Opportunity | stripe-node 23 and API version Endive with breaking changes; nothing breaks while the API version stays pinned | Plan the SDK upgrade | M | none stated | watch |
| 7 | D? | 2.5 | Neon | Pricing (favorable) | Free plan storage per project 0.5 GB to 1 GB | Record the Neon plan in STACK.md | S | none stated | watch |

7 proposals: 3 A, 1 B, 1 C, 2 D. Defaults create 5 ticket(s) and watch 2.

The report has the full table with an "Impact on this project" column naming the affected files, a drift section, a list of unverified sources, a one-paragraph-per-vendor summary of what was dismissed as Noise, and a reminder that email-only vendor notices are not covered. Full file: [report-2026-10-22.md](report-2026-10-22.md).

Then the skill prints the table in chat and stops:

> Reply with item numbers to ticket, W plus item number to watch, D plus item number to dismiss.

Nothing is ticketed until you reply.

## 4. Your reply: tickets

The sample reply was `1, 2, 3, 4, D5, D6, D7` (close to the defaults, which would have watched 6 and 7 instead of dismissing them). With the `markdown` tracker, tickets are rows in one table. Security, Breaking, and Deprecation items produce a linked pair: a `RISK:` row describing the exposure and a work row describing the fix.

| ID | Status | Title | Severity | Effort | Due | Linked |
|---|---|---|---|---|---|---|
| SW-001 | open | Upgrade next to 15.5.28 and React to 19 | Security | L | | SW-002 |
| SW-002 | open | RISK: Next.js 14.2.21 carries 4 Critical advisories with no 14.x fix | Security | | | SW-001 |
| SW-003 | open | Move the runtime to Node.js 24 LTS | Security | S | | SW-004 |
| SW-004 | open | RISK: Node.js 20 is end-of-life and unpatched for the October 2026 High CVEs | Security | | | SW-003 |
| SW-005 | open | Upgrade drizzle-orm to 0.45.4 and drizzle-kit to 0.31.11 | Security | M | | SW-006 |
| SW-006 | open | RISK: drizzle-orm 0.38.3 allows SQL injection through unescaped identifiers | Security | | | SW-005 |
| SW-007 | open | Set a Vercel deployment retention policy and review Deployment Storage before 2026-10-23 | Pricing or limits | S | 2026-10-23 | |

The real table also has Definition of done, Source, Confidence, and Created columns. You close a ticket by changing Status to `done 2026-11-05`. Full file: [tickets.md](tickets.md).

With `asana`, `linear`, or `github` in [config.json](config.json), the same tickets go to that tracker instead.

## 4b. Lifecycle signals

Two checks need no changelog at all. `lifecycle.py` asks endoflife.date for the pinned release line of each runtime and framework, and the npm registry for the state of each pinned version. From the sample:

| Product | Pinned | Status | End of life | Supported newer lines |
|---|---|---|---|---|
| Node.js | 20.11.1 | end-of-life | 2026-04-30 | 26, 24, 22 |
| next | 14.2.21 | end-of-life | 2025-10-26 | 16 |
| react | 18.3.1 | supported | none stated | 19 |

The registry also says `next@14.2.21` is deprecated ("This version has a security vulnerability") and that `stripe` 17.5.0 is six majors behind. Each end-of-life or deprecated pin becomes a Deprecation item; the version table goes into the report as context. The full tables are in the [report](report-2026-10-22.md).

## 5. Memory: ledger.json

The ledger is why the next probe will not show you these 375 items again. Each item is hashed on vendor, URL, and title, and carries your decision:

```json
{
  "vendor": "drizzle-orm",
  "title": "high severity: Drizzle ORM has SQL injection via improperly escaped SQL identifiers",
  "url": "https://github.com/advisories/GHSA-gpj5-g38j-94v9",
  "severity": "Security",
  "proposal": 3,
  "decision": "ticketed",
  "ticket_url": "stack-watch/tickets.md#SW-005",
  "first_seen": "2026-10-22",
  "decided_on": "2026-10-22"
}
```

Decisions: `ticketed`, `watch` (shown again next run), `dismissed`, `auto-dismissed` (Noise), `pending` (you have not replied yet). The `runs` list records each probe's date and lookback, which is how the next probe knows where to start. Full file: [ledger.json](ledger.json).

## What this run shows about the rules

- **Nothing happens without you.** The bootstrap stops after writing STACK.md. The probe stops after the proposal table. Tickets exist only for the numbers you typed.
- **Env values are never read.** STACK.md lists `DATABASE_URL`, `STRIPE_SECRET_KEY`, and `NEXT_PUBLIC_GA_ID` by name, from `.env.example` and source references. The scanner does not open `.env`.
- **Only the stack is tracked.** Ten vendors were found, so ten were probed. Clerk, Supabase, and the other 17 vendors the skill knows about were ignored because the project does not use them.
- **Noise is kept out of your way, but kept.** 252 of the 256 Vercel changelog posts were AI Gateway model launches and features this project does not use. They are in the ledger as `auto-dismissed` and summarized in one paragraph of the report.
- **The first run is the big one.** 90 days of feeds is several hundred items. A weekly or monthly probe is a few dozen.

## Notes from this run for stack-watch maintainers

1. Vercel's single Atom feed mixes blog and changelog and uses `<content type="xhtml">`; both the `url_filter` and the xhtml parsing in `fetch_sources.py` came out of this run.
2. `npm audit` reports one item per advisory; 33 of 34 pointed at the same `next` upgrade. Grouping advisories by package into one proposal is now a rule in SKILL.md.
3. Node.js release feed entries have no body; the security post had to be read directly.
4. A first 90-day probe of a 13-dependency project produced 339 feed items, 256 of them from Vercel.

## Reproduce it

From the repository root:

```bash
python3 examples/sample-next-app/generate-fixture.py    # writes the sample's package.json and lockfile (not committed)
python3 skills/stack-watch/scripts/scan_repo.py examples/sample-next-app --pretty > /tmp/scan.json
python3 skills/stack-watch/scripts/diff_stack.py /tmp/scan.json samples/STACK.md --pretty
python3 skills/stack-watch/scripts/fetch_sources.py samples/sources.json --since 2026-10-01 --pretty
python3 skills/stack-watch/scripts/audit.py examples/sample-next-app --pretty
```

Or install the plugin and run `/stack-watch` inside `examples/sample-next-app` to go through the whole flow with Claude.
