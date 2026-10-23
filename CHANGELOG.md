# Changelog

## Unreleased

## 1.1.0 (2026-10-22)

- Deterministic pipeline: `render_stack.py` writes and merges STACK.md, `fetch_sources.py` reads feeds and GitHub releases, `audit.py` normalizes package-manager audits, `ledger.py filter` dedupes
- 27 verified vendor sources; `url_filter` for feeds that mix a blog with a changelog
- `/stack-watch [bootstrap|probe] [path]` plugin command
- `examples/sample-next-app` input project and `samples/` with one complete run's output and a walkthrough
- Markdown tracker writes tickets as rows in one table
- Fixes: pnpm, Yarn and bun lockfile versions; Atom `xhtml` bodies; 308 redirects; Analytics rows no longer drift every run

## 1.0.0 (2026-10-22)

- First public release: STACK.md scanner and differ, severity rubric, ledger, tracker-agnostic ticket conventions (Asana, Linear, GitHub Issues, markdown)
