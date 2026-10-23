# Known vendor sources

Read this file during bootstrap (step 5) and during probe (step 6) when a detected vendor needs a sources.json entry. Copy the matching entry into sources.json. If a vendor is not listed here, search the web for "<vendor> changelog" and "<vendor> release notes", prefer the vendor's own domain, and add the result to sources.json with status "unverified".

A vendor listed here is copied into sources.json only when the scan detects it or a hand-confirmed STACK.md row names it (SKILL.md operating rule 6).

Verification method note: entries below were last verified on 2026-08-29. Entries marked "fetch" were fetched directly and confirmed. Entries marked "search" were confirmed through web search results that showed the page title and dated entries, without a direct fetch. Re-verify any "search" entry on first successful direct fetch and update its verified date. Corrections and new vendors are welcome as pull requests.

## Vercel

- matches: `vercel`, `@vercel/*`, `vercel.json`
- source 1: type changelog, url https://vercel.com/changelog, feed: none confirmed (https://vercel.com/atom is the blog feed, not the changelog feed; a community report from 2024 says it can break), verified 2026-08-29 (search)
- status: verified

## Next.js

- matches: `next`, `next.config.*`, `eslint-config-next`
- source 1: type github-releases, url https://github.com/vercel/next.js/releases, feed https://github.com/vercel/next.js/releases.atom, verified 2026-08-29 (fetch)
- source 2: type blog, url https://nextjs.org/blog, feed https://nextjs.org/feed.xml, verified: not yet (add as unverified if used)
- status: verified
- note: canary releases are frequent. Filter to stable releases unless a canary carries a security note.

## Neon

- matches: `@neondatabase/*`, `neon`, `DATABASE_URL` pointing at neon.tech
- source 1: type changelog, url https://neon.com/docs/changelog, feed: the docs resources section advertises RSS; candidate url https://neon.com/docs/changelog/rss.xml is unconfirmed, verified 2026-08-29 (search, dated entries seen through 2026-08-21)
- status: verified

## Drizzle ORM

- matches: `drizzle-orm`, `drizzle-kit`, `drizzle.config.*`
- source 1: type github-releases, url https://github.com/drizzle-team/drizzle-orm/releases, feed https://github.com/drizzle-team/drizzle-orm/releases.atom, verified 2026-08-29 (fetch)
- source 2: type github-releases, url https://github.com/drizzle-team/drizzle-kit-mirror/releases, feed https://github.com/drizzle-team/drizzle-kit-mirror/releases.atom, verified: not yet (drizzle-kit release notes are published there; add as unverified if drizzle-kit is detected)
- status: verified

## Clerk

- matches: `@clerk/*`, `clerk`
- source 1: type changelog, url https://clerk.com/changelog, feed: none confirmed, verified 2026-08-29 (search)
- source 2: type changelog-markdown, url https://clerk.com/changelog/changelog.md, feed null, verified 2026-08-29 (search; a plain-markdown mirror of the changelog, cheap to parse when reachable)
- status: verified

## Google Analytics

- matches: script domains `googletagmanager.com`, `google-analytics.com`, `gtag` snippets, env names containing `GA_` or `GTAG`
- source 1: type release-notes, url https://support.google.com/analytics/answer/9164320 ("What's new in Google Analytics"), feed null, verified 2026-08-29 (search)
- source 2: type announcements, url https://support.google.com/analytics/announcements/10707884, feed null, verified 2026-08-29 (search)
- status: verified
- note: Google also changes gtag collect endpoints remotely with no announcement. Pair this source with a check of the repo's Content Security Policy allowlist when a GA item appears.

## Google Search Console

- matches: hand-entered service (scan cannot detect Search Console use), `google-site-verification` meta tags
- source 1: type blog, url https://developers.google.com/search/blog (Search Central Blog, where Search Console announcements land), feed: candidate https://developers.google.com/search/blog/rss.xml unconfirmed, verified 2026-08-29 (search)
- source 2: type release-notes, url https://developers.google.com/search/updates (Search documentation updates), feed null, verified 2026-08-29 (search)
- status: verified

## Calendly

- matches: script or link domains `calendly.com`, `assets.calendly.com`, `react-calendly`
- source 1: type release-notes, url https://calendly.com/release-notes (product), feed null, verified 2026-08-29 (search)
- source 2: type api-release-notes, url https://developer.calendly.com/release-notes, feed https://developer.calendly.com/rss.xml (Atom variant https://developer.calendly.com/atom.xml), verified 2026-08-29 (search; feed URLs were advertised in the search result)
- status: verified

## npm ecosystem

- matches: any `package.json` project
- source 1: type advisories, command `npm audit --json` run in the repo (use the pnpm or yarn equivalent when the lockfile says so), verified 2026-08-29 (local command, no URL)
- source 2: type advisories, url https://github.com/advisories, feed null, verified 2026-08-29 (fetchable domain; query per-package when a pinned package needs a lookup)
- status: verified

## Unresolved vendors

Every vendor listed above resolved to a working source as of 2026-08-29. Open follow-ups: confirm the Neon changelog RSS URL and whether Vercel publishes a changelog feed, then fill in the feed fields above.
