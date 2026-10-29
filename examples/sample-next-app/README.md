# sample-next-app

A small Next.js project used to demonstrate and test stack-watch. It is not a
runnable app (there is no `node_modules`), but it has everything the scanner
looks at: `package.json` and a lockfile, Next.js and Vercel config, a Drizzle
config, a layout with a Google Analytics tag, and `process.env` references.

The output of running stack-watch on this project is in [samples/](../../samples),
with a walkthrough in [samples/README.md](../../samples/README.md).

The lockfile is generated, not committed, because it pins deliberately old
versions and GitHub would otherwise raise Dependabot alerts against this
repository for a fixture. `locked-versions.json` holds the pins. From the
repository root:

```bash
python3 examples/sample-next-app/generate-lockfile.py
python3 skills/stack-watch/scripts/scan_repo.py examples/sample-next-app --pretty
```
