---
project: sample-next-app
repo_path: examples/sample-next-app
last_scanned: 2026-10-22
schema_version: 1
---

# Technology Stack

This file is maintained by the stack-watch skill. It is a starting hypothesis, not the truth: every run rescans the repo and diffs against this file. Contributors: correct anything wrong here, and add services the scan cannot see to the last section.

## Runtime

| Name | Version | Detected from | Last verified |
|---|---|---|---|
| Node.js | 20.11.1 | .nvmrc | 2026-10-22 |

## Framework

| Name | Version | Detected from | Last verified |
|---|---|---|---|
| next | 14.2.21 | package.json + package-lock.json | 2026-10-22 |
| Next.js config | n/a | next.config.mjs | 2026-10-22 |
| react | 18.3.1 | package.json + package-lock.json | 2026-10-22 |
| react-dom | 18.3.1 | package.json + package-lock.json | 2026-10-22 |

## Hosting and deployment

| Vendor | Plan or tier | Detected from | Last verified |
|---|---|---|---|
| Vercel | unknown | vercel.json | 2026-10-22 |

## Database

| Vendor | Driver package | Driver version | Detected from | Last verified |
|---|---|---|---|---|
| Neon | @neondatabase/serverless | 0.10.4 | package.json + package-lock.json | 2026-10-22 |

## ORM and data layer

| Name | Version | Detected from | Last verified |
|---|---|---|---|
| Drizzle config | n/a | drizzle.config.ts | 2026-10-22 |
| drizzle-kit | 0.30.1 | package.json + package-lock.json | 2026-10-22 |
| drizzle-orm | 0.38.3 | package.json + package-lock.json | 2026-10-22 |

## Authentication

| Vendor | SDK package | SDK version | Detected from | Last verified |
|---|---|---|---|---|
| none detected |  |  |  |  |

## Analytics and search

| Name | Integration method | Detected from | Last verified |
|---|---|---|---|
| @vercel/analytics | npm package | package.json + package-lock.json | 2026-10-22 |
| Google Analytics | script tag or client snippet | app/layout.tsx | 2026-10-22 |

## Key packages

| Package | Pinned version | Category | Detected from |
|---|---|---|---|
| @types/node | 22.10.2 | build | package.json + package-lock.json |
| eslint-config-next | 14.2.21 | build | package.json + package-lock.json |
| stripe | 17.5.0 | payments | package.json + package-lock.json |
| tailwindcss | 3.4.17 | build | package.json + package-lock.json |
| typescript | 5.7.2 | build | package.json + package-lock.json |
| zod | 3.24.1 | data | package.json + package-lock.json |

## Environment variable names

Names only. Values are never recorded here.

| Name | Detected from |
|---|---|
| DATABASE_URL | .env.example, lib/db.ts |
| NEXT_PUBLIC_GA_ID | .env.example, app/layout.tsx |
| STRIPE_SECRET_KEY | .env.example, lib/stripe.ts |

## Hand-confirmed external services

Maintained by hand. The scan never edits this section. Add services here that the scan cannot detect (analytics accounts, DNS, email, booking, hosting plan or tier).

| Vendor | Purpose | Integration method | Source | Last verified |
|---|---|---|---|---|
| none yet | add services the scan cannot see |  |  |  |
