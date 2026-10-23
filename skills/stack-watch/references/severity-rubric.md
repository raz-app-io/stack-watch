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
