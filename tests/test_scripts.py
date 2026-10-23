"""Tests for the stack-watch scripts. Standard library only.

Run from the repo root: python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "skills", "stack-watch", "scripts")
TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "skills", "stack-watch",
                        "references", "stack-md-template.md")


def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          input=stdin, capture_output=True, text=True)


def write(root, rel, content):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))


def items_by_name(scan):
    return {i["name"]: i for i in scan["items"]}


PACKAGE_JSON = json.dumps({
    "dependencies": {"next": "^14.2.0", "@vercel/analytics": "^1.0.0",
                     "@neondatabase/serverless": "^0.9.0", "drizzle-orm": "^0.30.0"},
    "devDependencies": {"typescript": "^5.4.0"},
})


class ScanRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        write(self.repo, "package.json", PACKAGE_JSON)

    def tearDown(self):
        self.tmp.cleanup()

    def scan(self):
        r = run("scan_repo.py", self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_no_package_json(self):
        os.remove(os.path.join(self.repo, "package.json"))
        r = run("scan_repo.py", self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("error", json.loads(r.stdout))

    def test_sections_and_declared_versions(self):
        items = items_by_name(self.scan())
        self.assertEqual(items["next"]["section"], "framework")
        self.assertEqual(items["@vercel/analytics"]["section"], "analytics")
        self.assertEqual(items["@neondatabase/serverless"]["section"], "database")
        self.assertEqual(items["drizzle-orm"]["section"], "orm")
        self.assertEqual(items["typescript"]["section"], "key_package")
        self.assertEqual(items["typescript"]["category"], "build")
        self.assertTrue(items["typescript"]["dev"])
        self.assertEqual(items["next"]["version"], "^14.2.0")
        self.assertEqual(items["Vercel (inferred)"]["section"], "hosting")

    def test_npm_lockfile(self):
        write(self.repo, "package-lock.json", json.dumps({
            "lockfileVersion": 3,
            "packages": {"": {}, "node_modules/next": {"version": "14.2.3"},
                         "node_modules/foo/node_modules/next": {"version": "1.0.0"}},
        }))
        scan = self.scan()
        self.assertEqual(scan["package_manager"]["name"], "npm")
        self.assertEqual(items_by_name(scan)["next"]["version"], "14.2.3")

    def test_pnpm_v9_lockfile(self):
        write(self.repo, "pnpm-lock.yaml", """\
            lockfileVersion: '9.0'
            importers:
              .:
                dependencies:
                  next:
                    specifier: ^14.2.0
                    version: 14.2.3(react@18.3.1)
            packages:
              next@14.2.3:
                resolution: {integrity: sha512-x}
              '@neondatabase/serverless@0.9.4':
                resolution: {integrity: sha512-y}
            """)
        items = items_by_name(self.scan())
        self.assertEqual(items["next"]["version"], "14.2.3")
        self.assertEqual(items["@neondatabase/serverless"]["version"], "0.9.4")

    def test_pnpm_v6_lockfile(self):
        write(self.repo, "pnpm-lock.yaml", """\
            lockfileVersion: '6.0'
            packages:
              /next@14.2.3(react@18.3.1):
                resolution: {integrity: sha512-x}
              /@neondatabase/serverless@0.9.4:
                resolution: {integrity: sha512-y}
            """)
        items = items_by_name(self.scan())
        self.assertEqual(items["next"]["version"], "14.2.3")
        self.assertEqual(items["@neondatabase/serverless"]["version"], "0.9.4")

    def test_yarn_v1_lockfile(self):
        write(self.repo, "yarn.lock", """\
            # yarn lockfile v1


            "@neondatabase/serverless@^0.9.0":
              version "0.9.4"
              resolved "https://registry.yarnpkg.com/x"

            next@^14.2.0, next@^14:
              version "14.2.3"
            """)
        items = items_by_name(self.scan())
        self.assertEqual(items["next"]["version"], "14.2.3")
        self.assertEqual(items["@neondatabase/serverless"]["version"], "0.9.4")

    def test_yarn_berry_lockfile(self):
        write(self.repo, "yarn.lock", """\
            __metadata:
              version: 8

            "next@npm:^14.2.0":
              version: 14.2.3
              resolution: "next@npm:14.2.3"
            """)
        self.assertEqual(items_by_name(self.scan())["next"]["version"], "14.2.3")

    def test_bun_text_lockfile(self):
        write(self.repo, "bun.lock", """\
            {
              "lockfileVersion": 1,
              "packages": {
                "next": ["next@14.2.3", "", {}, "sha512-x"],
                "@neondatabase/serverless": ["@neondatabase/serverless@0.9.4", "", {}, "sha512-y"],
              }
            }
            """)
        items = items_by_name(self.scan())
        self.assertEqual(items["next"]["version"], "14.2.3")
        self.assertEqual(items["@neondatabase/serverless"]["version"], "0.9.4")

    def test_runtime_prefers_version_file(self):
        write(self.repo, "package.json", json.dumps({"engines": {"node": ">=18"}}))
        write(self.repo, ".nvmrc", "20.11.1\n")
        runtime = [i for i in self.scan()["items"] if i["section"] == "runtime"]
        self.assertEqual(len(runtime), 1)
        self.assertEqual(runtime[0]["version"], "20.11.1")

    def test_services_script_domains_and_config(self):
        write(self.repo, "src/app/layout.tsx", """\
            export default function Layout() {
              return <script src={`https://www.googletagmanager.com/gtag/js?id=G-1`} />;
            }
            """)
        write(self.repo, "src/middleware.ts", "export function middleware() {}\n")
        write(self.repo, "vercel.json", "{}")
        items = items_by_name(self.scan())
        self.assertEqual(items["Google Analytics"]["section"], "analytics")
        self.assertEqual(items["www.googletagmanager.com"]["section"], "external_domain")
        self.assertEqual(items["Middleware"]["detected_from"], "src/middleware.ts")
        self.assertEqual(items["Vercel"]["detected_from"], "vercel.json")
        self.assertNotIn("Vercel (inferred)", items)

    def test_env_names_only_never_values(self):
        secret = "sk_live_DO_NOT_LEAK_123"
        write(self.repo, ".env", f"SECRET_KEY={secret}\n")
        write(self.repo, ".env.local", f"LOCAL_ONLY={secret}\n")
        write(self.repo, ".env.example", "DATABASE_URL=\nNEXT_PUBLIC_GA_ID=placeholder\n")
        write(self.repo, ".env.sample", "SAMPLE_VAR=\n")
        write(self.repo, "lib/db.ts", """\
            const a = process.env.DATABASE_URL;
            const b = process.env["BRACKET_VAR"];
            const c = import.meta.env.VITE_THING;
            """)
        r = run("scan_repo.py", self.repo)
        self.assertNotIn(secret, r.stdout)
        env = {i["name"] for i in json.loads(r.stdout)["items"] if i["section"] == "env_var"}
        self.assertEqual(env, {"DATABASE_URL", "NEXT_PUBLIC_GA_ID", "SAMPLE_VAR",
                               "BRACKET_VAR", "VITE_THING"})
        self.assertNotIn("SECRET_KEY", env)
        self.assertNotIn("LOCAL_ONLY", env)


def stack_md(rows_by_section):
    """Build a STACK.md from the real template, filling rows per section."""
    with open(TEMPLATE, encoding="utf-8") as f:
        text = f.read()
    body = text.split("```markdown\n", 1)[1].rsplit("```", 1)[0]
    lines = body.splitlines()
    out = []
    section = None
    for i, line in enumerate(lines):
        out.append(line)
        if line.startswith("## "):
            section = line[3:].strip()
        if (section in rows_by_section and line.startswith("|---")
                and lines[i - 1].startswith("|")):
            out.extend(rows_by_section[section])
    return "\n".join(out) + "\n"


class DiffStackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.scan_path = os.path.join(self.tmp.name, "scan.json")
        self.stack_path = os.path.join(self.tmp.name, "STACK.md")

    def tearDown(self):
        self.tmp.cleanup()

    def diff(self, scan_items, rows):
        with open(self.scan_path, "w") as f:
            json.dump({"items": scan_items}, f)
        with open(self.stack_path, "w") as f:
            f.write(stack_md(rows))
        r = run("diff_stack.py", self.scan_path, self.stack_path)
        return r.returncode, json.loads(r.stdout) if r.stdout else None

    def test_no_drift(self):
        code, out = self.diff(
            [{"section": "framework", "name": "next", "version": "14.2.3"},
             {"section": "analytics", "name": "@vercel/analytics", "version": "1.3.1"},
             {"section": "hosting", "name": "Vercel (inferred)", "version": None}],
            {"Framework": ["| next | 14.2.3 | package.json | 2026-10-01 |"],
             "Analytics and search": ["| @vercel/analytics | npm package | package.json | 2026-10-01 |"],
             "Hosting and deployment": ["| Vercel | unknown | package.json | 2026-10-01 |"]})
        self.assertEqual(code, 0, out)
        self.assertEqual(sum(out["summary"].values()), 0)

    def test_added_and_version_changed(self):
        code, out = self.diff(
            [{"section": "framework", "name": "next", "version": "15.0.0"},
             {"section": "orm", "name": "drizzle-orm", "version": "0.30.0"}],
            {"Framework": ["| next | 14.2.3 | package.json | 2026-10-01 |"]})
        self.assertEqual(code, 3)
        self.assertEqual(out["added"][0]["item"], "drizzle-orm")
        self.assertEqual(out["version_changed"][0],
                         {"section": "Framework", "item": "next",
                          "stack_md": "14.2.3", "repo": "15.0.0"})

    def test_missing_first_then_second_time(self):
        code, out = self.diff([], {"Framework": ["| next | 14.2.3 | package.json | 2026-10-01 |"]})
        self.assertEqual(code, 3)
        self.assertEqual(out["missing_first_time"][0]["item"], "next")
        code, out = self.diff([], {"Framework": [
            "| next | 14.2.3 | package.json (not found in repo, first missed 2026-10-01) | 2026-10-01 |"]})
        self.assertEqual(out["missing_second_time"][0]["first_missed"], "2026-10-01")
        self.assertEqual(out["missing_first_time"], [])

    def test_none_detected_rows_ignored(self):
        code, out = self.diff([], {"Authentication": ["| none detected | | | | |"]})
        self.assertEqual(code, 0, out)

    def test_hand_confirmed_overlap(self):
        code, out = self.diff(
            [{"section": "analytics", "name": "Google Analytics", "version": None}],
            {"Analytics and search": ["| Google Analytics | gtag | app/layout.tsx | 2026-10-01 |"],
             "Hand-confirmed external services": [
                 "| Google Analytics | traffic | gtag | GA admin | 2026-10-01 |"]})
        self.assertEqual(out["hand_confirmed_overlap"], [{"vendor": "Google Analytics"}])

    def test_scan_error_exits_1(self):
        with open(self.scan_path, "w") as f:
            json.dump({"error": "no package.json found"}, f)
        with open(self.stack_path, "w") as f:
            f.write(stack_md({}))
        self.assertEqual(run("diff_stack.py", self.scan_path, self.stack_path).returncode, 1)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "stack-watch", "ledger.json")

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, *args, stdin=None):
        r = run("ledger.py", self.path, *args, stdin=stdin)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_hash_is_stable(self):
        import hashlib
        expected = hashlib.sha256(b"Vercel|https://x|Title").hexdigest()
        self.assertEqual(self.ledger("hash", "Vercel", "https://x", "Title"), expected)

    def test_add_dedupe_and_decisions(self):
        item = {"vendor": "Vercel", "url": "https://x", "title": "T", "severity": "Breaking"}
        added = json.loads(self.ledger("add", stdin=json.dumps(item)))
        self.assertEqual(added["decision"], "pending")
        h = added["hash"]
        self.assertEqual(self.ledger("seen", h), "pending")
        self.ledger("add", stdin=json.dumps(item))
        self.assertEqual(len(json.loads(self.ledger("list"))), 1)
        self.ledger("set-decision", h, "ticketed", "https://tracker/1")
        stored = json.loads(self.ledger("list", "ticketed"))[0]
        self.assertEqual(stored["ticket_url"], "https://tracker/1")
        self.assertEqual(self.ledger("seen", "nope"), "no")

    def test_bulk_add(self):
        items = [{"vendor": "A", "url": "u1", "title": "t1"},
                 {"vendor": "B", "url": "u2", "title": "t2", "decision": "auto-dismissed"},
                 {"vendor": "A", "url": "u1", "title": "t1"}]
        self.ledger("add", stdin=json.dumps(items))
        self.assertEqual(len(json.loads(self.ledger("list"))), 2)
        self.assertEqual(len(json.loads(self.ledger("list", "auto-dismissed"))), 1)

    def test_invalid_decision_rejected(self):
        r = run("ledger.py", self.path, "add",
                stdin=json.dumps({"vendor": "A", "url": "u", "title": "t", "decision": "maybe"}))
        self.assertNotEqual(r.returncode, 0)

    def test_last_probed(self):
        self.assertEqual(self.ledger("last-probed"), "null")
        self.ledger("record-run", "bootstrap", "null", "0", "0")
        self.assertEqual(self.ledger("last-probed"), "null")
        run_rec = json.loads(self.ledger("record-run", "probe", "2026-07-01", "12", "3"))
        self.assertEqual(self.ledger("last-probed"), run_rec["date"])


if __name__ == "__main__":
    unittest.main()
