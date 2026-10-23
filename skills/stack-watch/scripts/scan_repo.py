#!/usr/bin/env python3
"""stack-watch repo scanner.

Deterministic stack detection for a JavaScript/TypeScript repo. Reads
package.json, the lockfile, framework and hosting config files, layout files
for third-party script tags, and env-var NAMES (never values). Prints one JSON
document to stdout.

Usage:
    python3 scan_repo.py [repo_path] [--pretty]

Safety rule: this script never opens .env or .env.local (or any other real
.env* file). Env var names come from example files (.env.example,
.env.local.example, .env.sample, .env.template) and from `process.env.NAME` /
`import.meta.env.NAME` references in source. Values are never read or printed.

Standard library only.
"""

import argparse
import datetime
import fnmatch
import json
import os
import re
import sys

SCHEMA_VERSION = 1

# Package name -> section classification. First match wins, checked in order.
# Glob patterns allowed. Everything unmatched lands in key_packages.
SECTION_RULES = [
    ("framework", ["next", "react", "react-dom", "remix", "@remix-run/*",
                   "astro", "nuxt", "svelte", "@sveltejs/*", "vue", "gatsby"]),
    ("database", ["@neondatabase/*", "pg", "postgres", "mysql2",
                  "better-sqlite3", "@planetscale/*", "mongodb", "redis",
                  "@upstash/*", "@libsql/*"]),
    ("orm", ["drizzle-orm", "drizzle-kit", "prisma", "@prisma/*", "typeorm",
             "sequelize", "kysely", "mongoose"]),
    ("auth", ["@clerk/*", "next-auth", "@auth/*", "@supabase/auth-*",
              "firebase-admin", "lucia", "@workos-inc/*", "passport"]),
    ("analytics", ["@vercel/analytics", "@vercel/speed-insights",
                   "posthog-js", "posthog-node",
                   "@sentry/*", "plausible-tracker", "@google-analytics/*",
                   "react-ga*", "@next/third-parties"]),
    ("hosting", ["@vercel/*", "@netlify/*", "wrangler", "@cloudflare/*"]),
]

# key_packages category rules. First match wins; fallback is "other".
CATEGORY_RULES = [
    ("build", ["typescript", "eslint*", "@eslint/*", "tailwindcss",
               "@tailwindcss/*", "postcss*", "@types/*", "tsx", "ts-node",
               "prettier*", "turbo", "vite", "webpack", "@babel/*", "dotenv",
               "autoprefixer", "eslint-config-*"]),
    ("UI", ["leaflet", "react-leaflet", "sharp", "framer-motion", "clsx",
            "class-variance-authority", "lucide-react", "@radix-ui/*",
            "@headlessui/*", "recharts", "d3*"]),
    ("data", ["minisearch", "zod", "date-fns", "lodash*", "papaparse",
              "csv-*", "gray-matter"]),
    ("SEO", ["next-sitemap", "next-seo", "schema-dts", "rss"]),
]

# Third-party script/beacon domains worth naming explicitly.
KNOWN_SERVICE_PATTERNS = [
    ("Google Analytics", ["googletagmanager.com", "google-analytics.com",
                          r"gtag\("]),
    ("Calendly", ["calendly.com"]),
    ("Plausible", ["plausible.io"]),
    ("PostHog", ["posthog.com", r"posthog\.init"]),
    ("Sentry", ["sentry.io", "ingest.sentry"]),
    ("Hotjar", ["hotjar.com"]),
    ("Microsoft Clarity", ["clarity.ms"]),
    ("Segment", ["cdn.segment.com", "api.segment.io"]),
    ("Meta Pixel", ["connect.facebook.net"]),
]

LOCKFILES = [
    ("package-lock.json", "npm"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
]

SOURCE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
SCAN_DIRS = ["app", "pages", "src", "components", "lib"]
SKIP_DIRS = {"node_modules", ".next", ".git", ".vercel", "dist", "build",
             "coverage", ".turbo"}

ENV_REF_RE = re.compile(
    r"""(?:process\.env|import\.meta\.env)(?:\.([A-Z][A-Z0-9_]*)|\[["']([A-Z][A-Z0-9_]*)["']\])""")
ENV_EXAMPLE_SUFFIXES = (".example", ".sample", ".template")
# Matches src="https://..." and the JSX template-literal form src={`https://...`}
SCRIPT_SRC_RE = re.compile(r"""src=\{?["'`](https://[^"'`\s]+)["'`]\}?""")
ENV_NAME_LINE_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


def match_any(name, patterns):
    return any(fnmatch.fnmatch(name, p) if any(c in p for c in "*?[") else name == p
               for p in patterns)


def classify_section(pkg):
    for section, patterns in SECTION_RULES:
        if match_any(pkg, patterns):
            return section
    return "key_package"


def classify_category(pkg):
    for cat, patterns in CATEGORY_RULES:
        if match_any(pkg, patterns):
            return cat
    return "other"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def find_first(repo, patterns):
    """Return the first file matching any glob pattern (relative to the repo
    root, one directory level allowed, e.g. "src/middleware.ts"), else None."""
    for p in patterns:
        subdir, pat = os.path.split(p)
        try:
            entries = sorted(os.listdir(os.path.join(repo, subdir)))
        except OSError:
            continue
        for e in entries:
            if fnmatch.fnmatch(e, pat):
                return os.path.join(subdir, e).replace(os.sep, "/")
    return None


# pnpm lockfile package keys: `next@14.2.3:` (v9), `/next@14.2.3:` (v6-v8),
# `/next/14.2.3:` (v5), optionally quoted and with a peer suffix `(react@18)`.
PNPM_KEY_RE = re.compile(
    r"""^\s+['"]?/?(@?[^@\s'"/(][^@\s'"(]*?)[@/](\d[\w.\-+]*)[('":]""", re.M)
# bun.lock (text, JSONC): `"next": ["next@14.2.3", ...]`
BUN_ENTRY_RE = re.compile(r'"(@?[^"@]+)":\s*\["(?:@?[^"@]+)@(\d[^"]*)"')


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def yarn_versions(text):
    """Yarn 1 and Yarn 2+ lockfiles: a non-indented spec header followed by an
    indented `version "x"` (v1) or `version: x` (v2+) line."""
    versions = {}
    name = None
    for line in text.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            spec = line.rstrip()[:-1].split(",")[0].strip().strip('"')
            at = spec.rfind("@")
            name = spec[:at] if at > 0 else None
        elif name:
            m = re.match(r"""^\s+version:?\s+["']?([^"'\s]+)""", line)
            if m:
                versions.setdefault(name, m.group(1))
                name = None
    return versions


def lockfile_versions(repo, lockfile):
    """Exact installed versions from the lockfile. npm v2/v3, pnpm v5-v9,
    Yarn 1 and 2+, bun text lock. bun.lockb is binary and yields nothing."""
    versions = {}
    path = os.path.join(repo, lockfile)
    if lockfile == "package-lock.json":
        data = read_json(path) or {}
        for key, meta in (data.get("packages") or {}).items():
            if key.startswith("node_modules/") and isinstance(meta, dict):
                name = key[len("node_modules/"):]
                if "node_modules/" not in name and meta.get("version"):
                    versions[name] = meta["version"]
    elif lockfile == "pnpm-lock.yaml":
        text = read_text(path)
        start = text.find("\npackages:")
        for m in PNPM_KEY_RE.finditer(text, start if start >= 0 else 0):
            versions.setdefault(m.group(1), m.group(2))
    elif lockfile == "yarn.lock":
        versions = yarn_versions(read_text(path))
    elif lockfile == "bun.lock":
        for m in BUN_ENTRY_RE.finditer(read_text(path)):
            versions.setdefault(m.group(1), m.group(2))
    return versions


def detect_runtime(repo, pkg_json):
    """One Node.js item. A version file (.nvmrc, .node-version) is what the
    toolchain actually uses, so it wins over package.json engines.node."""
    for f in (".nvmrc", ".node-version"):
        v = read_text(os.path.join(repo, f)).strip()
        if v:
            return [{"name": "Node.js", "version": v, "detected_from": f}]
    engines = (pkg_json or {}).get("engines") or {}
    if engines.get("node"):
        return [{"name": "Node.js", "version": engines["node"],
                 "detected_from": "package.json (engines.node)"}]
    return [{"name": "Node.js", "version": "unpinned",
             "detected_from": "package.json (no engines field)"}]


def iter_source_files(repo):
    for d in SCAN_DIRS:
        base = os.path.join(repo, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for fn in files:
                if os.path.splitext(fn)[1] in SOURCE_EXTS:
                    yield os.path.join(root, fn)


def scan_source(repo):
    """One pass over source files: known service patterns, external script
    srcs, and process.env names. Returns (services, script_srcs, env_refs)."""
    services = {}
    script_srcs = {}
    env_refs = {}
    layout_globs = ["app/layout.*", "pages/_app.*", "pages/_document.*",
                    "src/app/layout.*", "src/pages/_app.*",
                    "src/pages/_document.*"]
    for path in iter_source_files(repo):
        rel = os.path.relpath(path, repo)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for svc, pats in KNOWN_SERVICE_PATTERNS:
            for p in pats:
                found = (re.search(p, text) if any(ch in p for ch in "\\(")
                         else p in text)
                if found:
                    services.setdefault(svc, set()).add(rel)
                    break
        is_layoutish = any(fnmatch.fnmatch(rel.replace(os.sep, "/"), g)
                           for g in layout_globs)
        if is_layoutish:
            for m in SCRIPT_SRC_RE.finditer(text):
                url = m.group(1)
                dom = re.sub(r"^https://([^/]+).*", r"\1", url)
                script_srcs.setdefault(dom, set()).add(rel)
        for m in ENV_REF_RE.finditer(text):
            env_refs.setdefault(m.group(1) or m.group(2), set()).add(rel)
    return services, script_srcs, env_refs


def scan_env_example_files(repo):
    """Names only, from example files. Never opens .env or .env.local."""
    names = {}
    try:
        entries = os.listdir(repo)
    except OSError:
        return names
    for e in entries:
        if e.startswith(".env") and e.endswith(ENV_EXAMPLE_SUFFIXES):
            try:
                with open(os.path.join(repo, e), encoding="utf-8") as f:
                    for line in f:
                        m = ENV_NAME_LINE_RE.match(line)
                        if m:
                            names.setdefault(m.group(1), set()).add(e)
            except OSError:
                pass
    return names


def main():
    ap = argparse.ArgumentParser(description="stack-watch repo scanner")
    ap.add_argument("repo", nargs="?", default=".", help="repo path")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)

    pkg_path = os.path.join(repo, "package.json")
    pkg_json = read_json(pkg_path)
    if pkg_json is None:
        print(json.dumps({"error": "no package.json found", "repo_path": repo}))
        sys.exit(1)

    lockfile, pm = None, None
    for lf, name in LOCKFILES:
        if os.path.isfile(os.path.join(repo, lf)):
            lockfile, pm = lf, name
            break
    locked = lockfile_versions(repo, lockfile) if lockfile else {}

    items = []
    for it in detect_runtime(repo, pkg_json):
        it["section"] = "runtime"
        items.append(it)

    deps = dict(pkg_json.get("dependencies") or {})
    dev_deps = dict(pkg_json.get("devDependencies") or {})
    for name, declared in sorted({**deps, **dev_deps}.items()):
        section = classify_section(name)
        item = {
            "section": section,
            "name": name,
            "declared": declared,
            "version": locked.get(name) or declared,
            "dev": name in dev_deps and name not in deps,
            "detected_from": "package.json"
            + (f" + {lockfile}" if name in locked else ""),
        }
        if section == "key_package":
            item["category"] = classify_category(name)
        items.append(item)

    # Hosting and tool config files at repo root.
    config_signals = [
        ("hosting", "Vercel", ["vercel.json", ".vercel"]),
        ("hosting", "Netlify", ["netlify.toml"]),
        ("hosting", "Cloudflare", ["wrangler.toml", "wrangler.jsonc"]),
        ("framework", "Next.js config", ["next.config.*"]),
        ("orm", "Drizzle config", ["drizzle.config.*"]),
        ("framework", "Middleware", ["middleware.ts", "middleware.js"]),
        ("framework", "Middleware", ["src/middleware.ts", "src/middleware.js"]),
    ]
    seen_labels = set()
    for section, label, pats in config_signals:
        hit = find_first(repo, pats)
        if hit and label not in seen_labels:
            seen_labels.add(label)
            items.append({"section": section, "name": label,
                          "version": None, "detected_from": hit})
    # A Next.js repo deploys somewhere even without vercel.json; note the
    # signal packages so hosting is never silently empty.
    if not any(i["section"] == "hosting" for i in items):
        vercel_pkgs = [n for n in {**deps, **dev_deps} if n.startswith("@vercel/")]
        if vercel_pkgs:
            items.append({"section": "hosting", "name": "Vercel (inferred)",
                          "version": None,
                          "detected_from": "package.json (" + ", ".join(sorted(vercel_pkgs)) + ")"})

    services, script_srcs, env_refs = scan_source(repo)
    for svc, paths in sorted(services.items()):
        items.append({"section": "analytics", "name": svc, "version": None,
                      "integration": "script tag or client snippet",
                      "detected_from": ", ".join(sorted(paths)[:3])})
    for dom, paths in sorted(script_srcs.items()):
        items.append({"section": "external_domain", "name": dom,
                      "detected_from": ", ".join(sorted(paths)[:3])})

    env_names = scan_env_example_files(repo)
    for name, paths in env_refs.items():
        env_names.setdefault(name, set()).update(paths)
    for name, paths in sorted(env_names.items()):
        items.append({"section": "env_var", "name": name,
                      "detected_from": ", ".join(sorted(paths)[:3])})

    out = {
        "schema_version": SCHEMA_VERSION,
        "scanned_at": datetime.date.today().isoformat(),
        "repo_path": repo,
        "package_manager": {"name": pm, "lockfile": lockfile},
        "items": items,
    }
    print(json.dumps(out, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
