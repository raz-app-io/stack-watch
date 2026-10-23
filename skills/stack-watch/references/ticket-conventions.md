# Ticket conventions

Read this before writing any ticket (probe step 16). The general rules apply to every tracker. The tracker sections say where those rules land in each tool. The tracker comes from `stack-watch/config.json` (`tracker.type`, `tracker.project`); default is `markdown`.

## General rules

| # | Rule |
|---|---|
| 1 | Write tickets only for the item numbers the user selected from this run's proposal table. Never create tickets on your own. |
| 2 | Ticket types: work, risk, question. Work tickets have no title prefix. Risk tickets are prefixed `RISK:`. Question tickets are prefixed `Q:`. |
| 3 | Work ticket title: imperative verb + object + qualifier. Example: "Update analytics CSP allowlist for new collect endpoint before 2026-11-01". |
| 4 | A work ticket's description is its definition of done: state what must be true when the ticket is complete. |
| 5 | Every ticket description ends with two lines: `Source: <URL>` and `Confidence: high | moderate | low | unknown`. |
| 6 | Breaking, Deprecation, and Security items create two tickets: a `RISK:` ticket describing the exposure and a work ticket describing the fix. Create the work ticket first, then the RISK ticket, then add each ticket's URL to the other's description. |
| 7 | Pricing or limits and Opportunity items create one work ticket. |
| 8 | The skill never records decisions on the user's behalf. If a vendor change forces a choice (upgrade or migrate, pay or downgrade), create a `Q:` ticket that states the options. |
| 9 | Deadline: if the vendor stated a date, set the ticket due date to 14 days before it. If the tracker has no due dates, put `Due: YYYY-MM-DD` as the first description line. |
| 10 | After creating each ticket, confirm its URL in chat and record it with `ledger.py <ledger> set-decision <hash> ticketed <url>`. For rule 6 pairs, record the work ticket URL. |
| 11 | If the target project, team, or repo named in config.json cannot be found, stop and ask. Do not create a new project. |

## Tracker: markdown (default)

Append to `stack-watch/tickets.md` in the target repo, creating it with a `# stack-watch tickets` heading if missing. One `##` heading per ticket, using the ticket title. Under it: a `- [ ]` checkbox line `Status: open`, then `Severity`, `Effort`, and `Due` lines, then the description. The "URL" for the ledger is `stack-watch/tickets.md#<heading-slug>`.

## Tracker: asana

Use the Asana MCP tools. Look up the project named in `tracker.project`.

1. Work tickets go to a section named `Backlog`. Risk and question tickets go to a section named `Decisions & Risks`. If either section is missing, ask the user which existing section to use; do not create sections.
2. Set the Asana due date per rule 9.
3. Rule 6 links go in the task descriptions as task URLs.

## Tracker: linear

Use the Linear MCP tools. `tracker.project` names the team, or `Team/Project`.

1. Create issues in the team's default triage or backlog state.
2. Apply a label matching the severity if one exists; do not create labels without asking.
3. Map Effort to Linear estimate only when the team uses estimates: S=1, M=2, L=3.
4. Use Linear's issue relation ("related") for rule 6 pairs in addition to the description links.

## Tracker: github

Use the `gh` CLI or the GitHub MCP tools. `tracker.project` is `owner/repo`.

1. Create issues with `gh issue create --repo <owner/repo> --title ... --body ...`.
2. Apply a `stack-watch` label and a severity label (`security`, `breaking`, `deprecation`, `pricing`, `opportunity`) when those labels exist. Ask before creating labels.
3. GitHub issues have no due date; follow rule 9's description fallback, or set a milestone if the user asks for one.
