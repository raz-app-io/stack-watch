# Known vendor sources

Read this file during bootstrap (step 5) and during probe (step 6) when a detected vendor needs a `sources.json` entry. Copy the matching entry into `sources.json`. If a vendor is not listed here, search the web for "<vendor> changelog" and "<vendor> release notes", prefer the vendor's own domain, and add the result with status `unverified`.

A vendor listed here is copied into `sources.json` only when the scan detects it or a hand-confirmed STACK.md row names it (SKILL.md operating rule 6).

How to read an entry: `matches` are the package names, config files, or script domains that identify the vendor in a scan. Each source has a `type`, a `url` (the page a person reads), and a `feed` (what `fetch_sources.py` fetches: RSS, Atom, or a GitHub releases page, which the script reads through the GitHub API). A source with `feed: null` is an HTML page; `fetch_sources.py` reports it as `unparsed` and you read it yourself. An optional `url_filter` (regular expression) keeps only items whose URL matches, for feeds that mix a blog with a changelog. GitHub releases pages are always machine-readable, so they count as feeds.

Verification: every URL below was fetched directly on 2026-10-22 and returned the expected content type. Re-verify on first use if the date is more than six months old, and update the `verified` field in `sources.json`. Corrections and new vendors are welcome as pull requests.

## sources.json shape

```json
{
  "schema_version": 1,
  "vendors": [
    {
      "vendor": "Vercel",
      "matches": ["vercel", "@vercel/*", "vercel.json"],
      "sources": [
        {"type": "changelog", "url": "https://vercel.com/changelog", "feed": "https://vercel.com/atom", "url_filter": "/changelog/", "verified": "2026-10-22"}
      ],
      "status": "verified"
    }
  ]
}
```

`status` is `verified`, `unverified`, or `retired`. Retired vendors are kept for history and skipped by the fetcher.

## Hosting and platform

### Vercel

- matches: `vercel`, `@vercel/*`, `vercel.json`
- source: type changelog, url https://vercel.com/changelog, feed https://vercel.com/atom (Atom; one feed for the blog and the changelog. Set `"url_filter": "/changelog/"` on the source so blog posts are dropped; https://vercel.com/changelog/feed redirects here). Expect 50 to 100 changelog posts a month, most about AI Gateway models.

### Netlify

- matches: `@netlify/*`, `netlify-cli`, `netlify.toml`
- source: type changelog, url https://www.netlify.com/changelog/, feed https://www.netlify.com/changelog/feed.xml (RSS)

### Cloudflare

- matches: `wrangler`, `@cloudflare/*`, `wrangler.toml`, `wrangler.jsonc`
- source: type changelog, url https://developers.cloudflare.com/changelog/, feed https://developers.cloudflare.com/changelog/rss/index.xml (RSS, covers all products including Workers and Pages)

## Frameworks and languages

### Next.js

- matches: `next`, `next.config.*`, `eslint-config-next`, `@next/*`
- source 1: type github-releases, url https://github.com/vercel/next.js/releases, feed https://github.com/vercel/next.js/releases.atom
- source 2: type blog, url https://nextjs.org/blog, feed https://nextjs.org/feed.xml (RSS)
- note: canary releases are frequent and arrive as prereleases. The rubric treats them as Noise unless they carry a security note.

### React

- matches: `react`, `react-dom`
- source 1: type github-releases, url https://github.com/facebook/react/releases, feed https://github.com/facebook/react/releases.atom
- source 2: type blog, url https://react.dev/blog, feed https://react.dev/rss.xml (RSS)

### Astro

- matches: `astro`, `@astrojs/*`, `astro.config.*`
- source: type github-releases, url https://github.com/withastro/astro/releases, feed https://github.com/withastro/astro/releases.atom

### Node.js

- matches: the Runtime row `Node.js`, `.nvmrc`, `engines.node`
- source 1: type release-notes, url https://nodejs.org/en/blog/release, feed https://nodejs.org/en/feed/releases.xml (RSS)
- source 2: type security, url https://nodejs.org/en/blog/vulnerability, feed https://nodejs.org/en/feed/vulnerability.xml (RSS; security release announcements)
- note: both feeds carry titles only, no body. Read a security-release post directly to learn which release lines were fixed; end-of-life lines are never fixed and the post says so.

### TypeScript

- matches: `typescript`
- source 1: type github-releases, url https://github.com/microsoft/TypeScript/releases, feed https://github.com/microsoft/TypeScript/releases.atom
- source 2: type blog, url https://devblogs.microsoft.com/typescript/, feed https://devblogs.microsoft.com/typescript/feed/ (RSS)

### Tailwind CSS

- matches: `tailwindcss`, `@tailwindcss/*`
- source 1: type github-releases, url https://github.com/tailwindlabs/tailwindcss/releases, feed https://github.com/tailwindlabs/tailwindcss/releases.atom
- source 2: type blog, url https://tailwindcss.com/blog, feed null

## Databases and data layer

### Neon

- matches: `@neondatabase/*` (the scan never reads env values, so a `DATABASE_URL` name alone does not identify Neon)
- source: type changelog, url https://neon.com/docs/changelog, feed https://neon.com/docs/changelog/rss.xml (RSS)

### Supabase

- matches: `@supabase/*`, `supabase` (CLI)
- source 1: type changelog, url https://supabase.com/changelog, feed null
- source 2: type github-releases, url https://github.com/supabase/supabase-js/releases, feed https://github.com/supabase/supabase-js/releases.atom

### PlanetScale

- matches: `@planetscale/*`
- source: type changelog, url https://planetscale.com/changelog, feed https://planetscale.com/changelog/rss.xml (Atom)

### Upstash

- matches: `@upstash/*`
- source: type github-releases, url https://github.com/upstash/redis-js/releases, feed https://github.com/upstash/redis-js/releases.atom
- note: covers the Redis SDK only. Upstash platform announcements are on https://upstash.com/blog (HTML, not verified as a changelog).

### Drizzle ORM

- matches: `drizzle-orm`, `drizzle-kit`, `drizzle.config.*`
- source 1: type github-releases, url https://github.com/drizzle-team/drizzle-orm/releases, feed https://github.com/drizzle-team/drizzle-orm/releases.atom
- source 2: type github-releases, url https://github.com/drizzle-team/drizzle-kit-mirror/releases, feed https://github.com/drizzle-team/drizzle-kit-mirror/releases.atom (drizzle-kit release notes are published here; add only when drizzle-kit is detected)

### Prisma

- matches: `prisma`, `@prisma/*`
- source: type github-releases, url https://github.com/prisma/prisma/releases, feed https://github.com/prisma/prisma/releases.atom

### Firebase

- matches: `firebase`, `firebase-admin`
- source: type release-notes, url https://firebase.google.com/support/release-notes/js, feed null

## Authentication

### Clerk

- matches: `@clerk/*`
- source 1: type changelog, url https://clerk.com/changelog, feed null
- source 2: type changelog-markdown, url https://clerk.com/changelog/changelog.md, feed null (a plain-markdown index of every changelog entry, cheap to read directly)

### Auth.js (NextAuth)

- matches: `next-auth`, `@auth/*`
- source: type github-releases, url https://github.com/nextauthjs/next-auth/releases, feed https://github.com/nextauthjs/next-auth/releases.atom

### Auth0

- matches: `auth0`, `@auth0/*`
- source: type changelog, url https://auth0.com/changelog, feed https://auth0.com/changelog/rss.xml (RSS)

## Payments and email

### Stripe

- matches: `stripe`, `@stripe/*`
- source 1: type changelog, url https://docs.stripe.com/changelog, feed null (API version changelog; read directly)
- source 2: type github-releases, url https://github.com/stripe/stripe-node/releases, feed https://github.com/stripe/stripe-node/releases.atom

### Resend

- matches: `resend`
- source: type changelog, url https://resend.com/changelog, feed https://resend.com/changelog/rss.xml (RSS)

## Analytics, monitoring, and search

### Google Analytics

- matches: script domains `googletagmanager.com`, `google-analytics.com`, `gtag` snippets, `@next/third-parties` GoogleAnalytics, env names containing `GA_` or `GTAG`
- source 1: type release-notes, url https://support.google.com/analytics/answer/9164320 ("What's new in Google Analytics"), feed null
- source 2: type announcements, url https://support.google.com/analytics/announcements/10707884, feed null
- note: Google also changes gtag collect endpoints remotely with no announcement. When a GA item appears, pair it with a check of the repo's Content Security Policy allowlist.

### Google Search Console

- matches: hand-entered service (the scan cannot detect Search Console use), `google-site-verification` meta tags
- source 1: type blog, url https://developers.google.com/search/blog, feed https://feeds.feedburner.com/blogspot/amDG (RSS; the Search Central blog feed. On first probe confirm the newest entry is recent)
- source 2: type release-notes, url https://developers.google.com/search/updates, feed null

### Sentry

- matches: `@sentry/*`, script domain `sentry.io`
- source 1: type changelog, url https://sentry.io/changelog/, feed null
- source 2: type github-releases, url https://github.com/getsentry/sentry-javascript/releases, feed https://github.com/getsentry/sentry-javascript/releases.atom

### PostHog

- matches: `posthog-js`, `posthog-node`, script domain `posthog.com`
- source 1: type changelog, url https://posthog.com/changelog, feed null
- source 2: type github-releases, url https://github.com/PostHog/posthog-js/releases, feed https://github.com/PostHog/posthog-js/releases.atom

### Calendly

- matches: script or link domains `calendly.com`, `assets.calendly.com`, `react-calendly`
- source 1: type release-notes, url https://calendly.com/release-notes, feed null
- source 2: type api-release-notes, url https://developer.calendly.com/release-notes, feed null

## Package advisories

Advisories need no `sources.json` entry. Probe step 9 runs `scripts/audit.py`, which queries the OSV.dev database (and the package manager's own audit as a fallback) for every locked version. For a manual lookup, https://github.com/advisories accepts `?ecosystem=npm&query=<package>`.

## Aggregators the scripts use

These are not vendors; they are machine-readable databases the scripts query directly, so they need no `sources.json` entry.

| Aggregator | Used by | What it answers | Limits |
|---|---|---|---|
| OSV.dev (https://osv.dev) | `audit.py` | Known vulnerabilities for an exact package version, across npm and most other ecosystems | None published; batch of 500 queries per request |
| endoflife.date (https://endoflife.date) | `lifecycle.py` | End-of-life and support dates per release line for 480+ products, including nodejs, nextjs, react, vue, nuxt, svelte, angular, express, bun, electron, tailwind-css | Community-maintained; not every framework is listed (TypeScript is not) |
| npm registry (https://registry.npmjs.org) | `lifecycle.py`, `discover_sources.py` | Deprecation flags per version, latest version, repository and homepage of a package | None for anonymous reads |
| GitHub releases Atom feeds | `fetch_sources.py`, `discover_sources.py` | Release notes for any public repository, with no API quota | Prereleases are left out by default |
| GitHub REST API | `fetch_sources.py` | Richer release bodies and the prerelease flag | 60 requests an hour unauthenticated; set `GITHUB_TOKEN` |

Considered and not used: GitHub Advisory Database REST (same data as OSV, shares the 60/hour quota), deps.dev (same data as OSV plus the registry), newreleases.io (an account-based aggregator of GitHub, npm and PyPI releases; useful for email alerts, redundant here), Libraries.io (API key required).

## Unresolved

Vendors whose public changelog could not be confirmed on 2026-10-22: none. Feeds that were looked for and do not exist: Supabase changelog RSS, PostHog changelog RSS, Stripe changelog RSS, Calendly developer RSS and Atom, Google Search Central `rss.xml`.
