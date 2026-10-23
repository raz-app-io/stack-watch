# Severity rubric

Read this when classifying probe items (probe step 12). Every non-Noise item goes forward to the proposal table. Noise is dropped and logged to the ledger as `auto-dismissed`.

## Severities

| # | Severity | Assign when | Example |
|---|---|---|---|
| 1 | Security | A vulnerability advisory names a package or version present in STACK.md, or a vendor announces a security incident affecting the service tier in use | npm audit high finding on a pinned dependency; a framework release note that says "critical security fix" for the major version in use |
| 2 | Breaking | A change requires code or config edits to keep current behavior, with or without a deadline | Framework major version removes an API the repo imports; a vendor changes a default that the repo relies on |
| 3 | Deprecation | A feature, API, SDK, tag, or plan in use will stop working on a stated or unstated future date | Analytics vendor retires a tag format the site's layout loads; an SDK is announced end-of-life |
| 4 | Pricing or limits | A cost, quota, rate limit, or free-tier boundary changes for a service in use | Database vendor lowers free-tier compute hours; tile provider starts requiring an API key |
| 5 | Opportunity | A new feature or capability could improve performance, SEO, cost, developer speed, or user experience for this specific project | Hosting vendor ships a caching primitive relevant to the site's data-fetch pattern |
| 6 | Noise | None of the above, or the item touches nothing in STACK.md | Vendor blog post about a customer case study; a release that only touches platforms or features the repo does not use |

## Scoring, grading, and ranking

Severity says what kind of change it is. The grade says how urgently this project should act. `scripts/rank.py` computes it from five fields you set per proposal, so the arithmetic is identical every run and the table is sorted the same way for every reader.

| Field | Values | How to choose |
|---|---|---|
| `impact` | severe, major, moderate, minor | What happens if nobody acts: severe = outage, data loss, or exploitable; major = a feature or integration stops working, or a cost jump; moderate = degraded, noisier, slower, or a modest cost; minor = cosmetic or informational. For Security, set `advisory_severity` (critical, high, moderate, low) from the advisory instead |
| `exposure` | confirmed, likely, unclear | confirmed = the affected package, config, route, or plan is in STACK.md or the repo (name the file); likely = probably applies but a detail is unknown (plan tier, region, feature flag); unclear = cannot tell, or a precondition the repo does not meet (the Windows-only RCE on a Linux deploy is `unclear`) |
| `deadline` | YYYY-MM-DD or null | Only a vendor-stated date. Urgency is derived: past or within 14 days counts most, within 90 days counts some |
| `fix_available` | true, false | Security and Deprecation only: a fixed version or replacement exists today. Counts as urgency when there is no date |
| `pricing_direction` | increase, favorable, neutral | Pricing items only. A favorable change still goes in the table (people should know) but ranks low |
| `effort` | S, M, L | Unchanged meaning. Lowers the score only for Pricing and Opportunity; for the top three severities it only breaks ties |

Score = base (Security 4, Breaking 3.5, Deprecation 3, Pricing increase 2.5, neutral 2, favorable 1.5, Opportunity 1) + impact (0 to 3) + exposure (0 to 2) + urgency (0 to 2) - effort cost (Pricing and Opportunity: S 0, M 0.5, L 1), capped at 10.

| Grade | Score | Meaning | Default |
|---|---|---|---|
| A | 8 or more | Act this week | ticket |
| B | 6 to 7.9 | Before the deadline, within the sprint | ticket |
| C | 4 to 5.9 | Schedule it | ticket (backlog) |
| D | below 4 | Worth knowing, not worth a ticket yet | watch |

Low or unknown confidence appends `?` to the grade (`B?`) and changes nothing else: the recall rule above still applies. Rows sort by score, then smaller effort first, then earliest deadline. The Default column is a suggestion; the user's reply decides.

## Tie-breaks and judgment calls

1. When two severities could apply, pick the higher one in the order listed above (Security highest).
2. When in doubt between Opportunity and Noise, pick Noise and log it. Precision matters more for Opportunity.
3. Recall matters more for the top four severities (Security, Breaking, Deprecation, Pricing or limits). If unsure whether one of those touches the stack, keep it and mark Confidence low rather than dropping it.
4. An item that touches nothing in STACK.md is downgraded to Noise, with one exception: Security items stay Security even when the affected package is a transitive dependency not listed in STACK.md.
5. A change that is breaking only on a version the repo does not run (for example a breaking change in v3 while the repo pins v2 and v2 is still supported) is Opportunity at most, usually Noise. But if the vendor pairs it with an end-of-support date for the pinned version, that is a Deprecation.
6. Canary, beta, and release-candidate items are Noise unless they carry a security note or announce a deprecation that will land in stable.

## Worked examples

7. Google changed gtag collect endpoints remotely, and a site's Content Security Policy allowlist silently blocked every analytics hit. Classify a "collect endpoint change" item as Breaking (the CSP is config the repo must edit), not Opportunity.
8. A map tile provider started watermarking unauthenticated tiles. Classify "API key now required" as Pricing or limits, and note the stated date.
9. A Next.js stable release fixing "Unauthenticated RCE on Windows-hosted servers" when the project deploys on Linux: still Security (recall over precision for the top severities), with the impact note saying the deployment platform is not Windows and Confidence high.
