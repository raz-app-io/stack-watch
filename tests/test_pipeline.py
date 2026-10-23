"""Tests for render_stack.py, fetch_sources.py, audit.py, ledger filter, and
the sample project. Standard library only.

Run from the repo root: python3 -m unittest discover -s tests
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILL = os.path.join(ROOT, "skills", "stack-watch")
SCRIPTS = os.path.join(SKILL, "scripts")
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(ROOT, "examples", "sample-next-app")
SAMPLES = os.path.join(ROOT, "samples")

sys.path.insert(0, SCRIPTS)
import audit  # noqa: E402
import diff_stack  # noqa: E402
import fetch_sources  # noqa: E402
import ledger  # noqa: E402
import render_stack  # noqa: E402

TODAY = datetime.date.today().isoformat()


def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          input=stdin, capture_output=True, text=True)


def read_fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


SCAN = {
    "repo_path": "/x/app",
    "items": [
        {"section": "runtime", "name": "Node.js", "version": "20.11.1", "detected_from": ".nvmrc"},
        {"section": "framework", "name": "next", "version": "14.2.3", "detected_from": "package.json"},
        {"section": "hosting", "name": "Vercel", "version": None, "detected_from": "vercel.json"},
        {"section": "database", "name": "@neondatabase/serverless", "version": "0.9.4",
         "detected_from": "package.json"},
        {"section": "orm", "name": "drizzle-orm", "version": "0.30.0", "detected_from": "package.json"},
        {"section": "auth", "name": "some-unknown-auth", "version": "1.0.0", "detected_from": "package.json"},
        {"section": "analytics", "name": "Google Analytics", "version": None,
         "integration": "script tag or client snippet", "detected_from": "app/layout.tsx"},
        {"section": "analytics", "name": "@vercel/analytics", "version": "1.3.1", "dev": False,
         "detected_from": "package.json"},
        {"section": "key_package", "name": "zod", "version": "3.23.0", "category": "data",
         "detected_from": "package.json"},
        {"section": "env_var", "name": "DATABASE_URL", "detected_from": ".env.example"},
        {"section": "external_domain", "name": "www.googletagmanager.com", "detected_from": "app/layout.tsx"},
    ],
}


class RenderStackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def drift(self, scan, text):
        sp = os.path.join(self.tmp.name, "scan.json")
        mp = os.path.join(self.tmp.name, "STACK.md")
        with open(sp, "w") as f:
            json.dump(scan, f)
        with open(mp, "w") as f:
            f.write(text)
        r = run("diff_stack.py", sp, mp)
        return r.returncode, json.loads(r.stdout)

    def test_fresh_render_has_no_drift(self):
        text = render_stack.render(SCAN)
        code, out = self.drift(SCAN, text)
        self.assertEqual(code, 0, out)
        self.assertIn("| Neon | @neondatabase/serverless | 0.9.4 |", text)
        self.assertIn("| unknown | some-unknown-auth | 1.0.0 |", text)
        self.assertIn("| Google Analytics | script tag or client snippet |", text)
        self.assertIn("| @vercel/analytics | npm package |", text)
        self.assertIn("| none yet |", text)
        self.assertIn("project: app\n", text)
        self.assertIn(f"last_scanned: {TODAY}\n", text)
        self.assertNotIn("www.googletagmanager.com", text)

    def test_merge_keeps_hand_edits_and_flags_then_removes_missing_rows(self):
        first = render_stack.render(SCAN, today="2026-09-01")
        edited = first.replace("| Vercel | unknown |", "| Vercel | Pro |")
        edited = edited.replace("| none yet | add services the scan cannot see |  |  |  |",
                                "| Cloudflare DNS | DNS | dashboard | ops notes | 2026-09-01 |")
        scan2 = {"repo_path": "/x/app",
                 "items": [i for i in SCAN["items"] if i["name"] != "drizzle-orm"]}
        for i in scan2["items"]:
            if i["name"] == "next":
                i["version"] = "15.0.0"
        second = render_stack.render(scan2, existing_text=edited, today="2026-10-01")
        self.assertIn("| Vercel | Pro | vercel.json | 2026-10-01 |", second)
        self.assertIn("| next | 15.0.0 |", second)
        self.assertIn("| Cloudflare DNS | DNS | dashboard | ops notes | 2026-09-01 |", second)
        self.assertIn("| drizzle-orm | 0.30.0 | package.json (not found in repo, first missed 2026-10-01) | 2026-09-01 |",
                      second)
        code, out = self.drift(scan2, second)
        self.assertEqual(out["missing_second_time"][0]["item"], "drizzle-orm")
        third = render_stack.render(scan2, existing_text=second, today="2026-11-01")
        self.assertNotIn("drizzle-orm", third)
        self.assertIn("| Cloudflare DNS |", third)
        self.assertIn("project: app\n", third)

    def test_repo_path_is_never_absolute_and_is_preserved(self):
        fresh = render_stack.render(SCAN)
        self.assertNotIn("/x/app", fresh)
        self.assertRegex(fresh, r"repo_path: (app|\.)\n")
        existing = fresh.replace("project: app", "project: My App").replace(
            "repo_path: app", "repo_path: apps/web").replace("repo_path: .", "repo_path: apps/web")
        merged = render_stack.render(SCAN, existing_text=existing)
        self.assertIn("project: My App\nrepo_path: apps/web\n", merged)

    def test_inferred_hosting_label_is_replaced_once_config_appears(self):
        inferred = dict(SCAN, items=[dict(i, name="Vercel (inferred)") if i["name"] == "Vercel" else i
                                     for i in SCAN["items"]])
        first = render_stack.render(inferred).replace("| Vercel (inferred) | unknown |", "| Vercel (inferred) | Pro |")
        second = render_stack.render(SCAN, existing_text=first)
        self.assertIn("| Vercel | Pro | vercel.json |", second)
        self.assertNotIn("(inferred)", second)

    def test_cli_writes_file(self):
        sp = os.path.join(self.tmp.name, "scan.json")
        out = os.path.join(self.tmp.name, "STACK.md")
        with open(sp, "w") as f:
            json.dump(SCAN, f)
        r = run("render_stack.py", sp, "--out", out, "--project", "demo", "--repo-path", ".")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as f:
            text = f.read()
        self.assertIn("project: demo\nrepo_path: .\n", text)

    def test_columns_match_template(self):
        with open(os.path.join(SKILL, "references", "stack-md-template.md"), encoding="utf-8") as f:
            body = f.read().split("```markdown\n", 1)[1].split("```", 1)[0]
        headers = {}
        section = None
        for line in body.splitlines():
            if line.startswith("## "):
                section = line[3:].strip()
            elif line.startswith("| ") and section and section not in headers:
                headers[section] = [c.strip() for c in line.strip().strip("|").split("|")]
        expected = dict(render_stack.COLUMNS)
        expected[render_stack.HAND_SECTION] = render_stack.HAND_COLUMNS
        self.assertEqual(headers, expected)
        self.assertEqual(set(diff_stack.SECTION_SPECS), set(render_stack.COLUMNS))


class FetchSourcesTest(unittest.TestCase):
    SRC = {"type": "feed", "_status": "verified"}

    def test_parse_atom(self):
        items = fetch_sources.parse_feed(read_fixture("feed_atom.xml"), "Example", self.SRC)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[2]["body"], "Deployments older than 30 days will be deleted. Read more")
        self.assertEqual(items[0]["title"], "v15.0.0")
        self.assertEqual(items[0]["date"], "2026-10-15")
        self.assertEqual(items[0]["url"], "https://github.com/example/repo/releases/tag/v15.0.0")
        self.assertEqual(items[0]["body"], "Breaking: removed the legacy API.")
        self.assertFalse(items[0]["prerelease"])
        self.assertEqual(items[1]["body"], "Old patch release.")
        self.assertEqual(items[1]["vendor"], "Example")

    def test_parse_rss(self):
        items = fetch_sources.parse_feed(read_fixture("feed_rss.xml"), "Example", self.SRC)
        self.assertEqual(items[0]["date"], "2026-10-20")
        self.assertEqual(items[0]["body"], "Starting 2026-12-01 the free plan includes 50 hours.")
        self.assertIsNone(items[1]["date"])
        self.assertEqual(items[1]["body"], "No date on this one.")

    def test_parse_feed_rejects_html(self):
        with self.assertRaises(fetch_sources.ET.ParseError):
            fetch_sources.parse_feed("<!DOCTYPE html><html><body>x</body></html>", "V", self.SRC)

    def test_parse_github_releases(self):
        rel = [
            {"name": "v15.0.0", "html_url": "u1", "published_at": "2026-10-15T10:00:00Z", "body": "# Notes",
             "prerelease": False, "draft": False},
            {"name": "", "tag_name": "v15.1.0-canary.3", "html_url": "u2", "published_at": "2026-10-16T10:00:00Z",
             "body": "", "prerelease": False, "draft": False},
            {"name": "draft", "html_url": "u3", "published_at": None, "created_at": "2026-10-17T00:00:00Z",
             "prerelease": False, "draft": True},
            {"name": "v16.0.0-beta.1", "html_url": "u4", "published_at": "2026-10-18T10:00:00Z",
             "prerelease": True, "draft": False},
        ]
        items = fetch_sources.parse_github_releases(rel, "Lib", {"type": "github-releases"})
        self.assertEqual([i["title"] for i in items], ["v15.0.0", "v15.1.0-canary.3", "v16.0.0-beta.1"])
        self.assertEqual([i["prerelease"] for i in items], [False, True, True])
        self.assertEqual(items[0]["body"], "# Notes")

    def test_prerelease_regex_is_version_shaped(self):
        rx = fetch_sources.PRERELEASE_RE
        for t in ["v16.5.0-canary.24", "2.0.0-beta.1", "v3.0.0-rc.2", "1.0.0-next.5", "rc2 of 4.0"]:
            self.assertTrue(rx.search(t), t)
        for t in ["Neon Realtime in public beta", "Step 5 Preview now available", "Vercel Daemons is now in public beta",
                  "Canary deployments explained", "v15.0.0"]:
            self.assertFalse(rx.search(t), t)

    def test_parse_date(self):
        pd = fetch_sources.parse_date
        self.assertEqual(pd("Mon, 20 Oct 2026 09:00:00 GMT"), "2026-10-20")
        self.assertEqual(pd("2026-10-15T12:00:00Z"), "2026-10-15")
        self.assertEqual(pd("2026-10-15T12:00:00.000+02:00"), "2026-10-15")
        self.assertEqual(pd("2026-10-15"), "2026-10-15")
        self.assertIsNone(pd("yesterday"))
        self.assertIsNone(pd(""))

    def test_collect_filters_and_summarizes(self):
        def fake_fetcher(vendor, source, timeout, max_body):
            if vendor == "Down":
                return [], "unreachable", "HTTP 503", source["url"]
            if vendor == "Page":
                return [], "unparsed", "HTML page; read it directly", source["url"]
            items = [
                {"title": "new", "url": "https://v/new", "date": "2026-10-20", "body": "", "prerelease": False},
                {"title": "old", "url": "https://v/old", "date": "2026-01-01", "body": "", "prerelease": False},
                {"title": "undated", "url": "https://v/undated", "date": None, "body": "", "prerelease": False},
                {"title": "v2-canary.1", "url": "https://v/canary", "date": "2026-10-21", "body": "",
                 "prerelease": True},
            ]
            for i in items:
                i.update({"vendor": vendor, "source_type": source["type"],
                          "source_status": source["_status"]})
            return items, "ok", None, source["url"]

        doc = {"vendors": [
            {"vendor": "Feed", "status": "unverified", "sources": [
                {"type": "changelog", "url": "https://v/changelog", "feed": "https://v/feed.xml"},
                {"type": "mirror", "url": "https://v/mirror", "feed": "https://v/mirror.xml"}]},
            {"vendor": "Down", "status": "verified", "sources": [{"type": "changelog", "url": "https://d"}]},
            {"vendor": "Page", "status": "verified", "sources": [{"type": "changelog", "url": "https://p"}]},
            {"vendor": "Gone", "status": "retired", "sources": [{"type": "changelog", "url": "https://g"}]},
            {"vendor": "npm ecosystem", "status": "verified",
             "sources": [{"type": "advisories", "command": "audit.py", "url": None, "feed": None}]},
        ]}
        out = fetch_sources.collect(doc, "2026-10-01", fetcher=fake_fetcher)
        titles = sorted(i["title"] for i in out["items"])
        self.assertEqual(titles, ["new", "undated"])  # mirror source deduped by hash
        self.assertTrue(all(i["hash"] for i in out["items"]))
        self.assertEqual(out["items"][0]["source_status"], "unverified")
        by_vendor = {}
        for s in out["sources"]:
            by_vendor.setdefault(s["vendor"], []).append(s)
        self.assertEqual([s["status"] for s in by_vendor["Feed"]], ["ok", "ok"])
        self.assertEqual(by_vendor["Feed"][0]["count"], 2)
        self.assertEqual(by_vendor["Feed"][0]["prereleases_skipped"], 1)
        self.assertEqual(by_vendor["Feed"][1]["count"], 0)
        self.assertEqual(by_vendor["Down"][0]["status"], "unreachable")
        self.assertEqual(by_vendor["Page"][0]["status"], "unparsed")
        self.assertEqual(by_vendor["Gone"][0]["status"], "skipped")
        self.assertEqual(by_vendor["npm ecosystem"][0]["status"], "skipped")
        with_pre = fetch_sources.collect(doc, "2026-10-01", fetcher=fake_fetcher, include_prereleases=True)
        self.assertIn("v2-canary.1", [i["title"] for i in with_pre["items"]])
        doc["vendors"][0]["sources"] = [{"type": "changelog", "url": "https://v/c", "feed": "https://v/f",
                                         "url_filter": "/undated$"}]
        filtered = fetch_sources.collect(doc, "2026-10-01", fetcher=fake_fetcher)
        self.assertEqual([i["title"] for i in filtered["items"]], ["undated"])

    def test_cli_rejects_bad_since(self):
        r = run("fetch_sources.py", os.path.join(FIXTURES, "feed_rss.xml"), "--since", "last-week")
        self.assertEqual(r.returncode, 2)


class AuditTest(unittest.TestCase):
    def parse(self, name, fmt=None):
        args = ["--input", os.path.join(FIXTURES, name)] + (["--format", fmt] if fmt else [])
        r = run("audit.py", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["items"]

    def check_two(self, items):
        self.assertEqual([i["package"] for i in items], ["next", "ws"])
        self.assertEqual([i["direct"] for i in items], [True, False])
        self.assertTrue(all(i["severity"] == "Security" for i in items))
        self.assertTrue(all(i["vendor"] == i["package"] for i in items))
        self.assertTrue(all(i["hash"] for i in items))
        self.assertIn("GHSA-fr5h-rqp8-mj6g", items[0]["url"])
        self.assertIn(">=13.4.0 <14.1.1", items[0]["body"])

    def test_npm7_format(self):
        items = self.parse("audit_npm7.json")
        self.check_two(items)
        self.assertIn("upgrade next to 14.2.3", items[0]["body"])
        self.assertIn("npm audit fix", items[1]["body"])

    def test_v6_format(self):
        items = self.parse("audit_v6.json")
        self.check_two(items)
        self.assertIn("Upgrade to version 14.1.1", items[0]["body"])

    def test_yarn1_ndjson(self):
        items = self.parse("audit_yarn1.ndjson")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["package"], "next")
        self.assertTrue(items[0]["direct"])

    def test_yarn_berry_ndjson(self):
        self.check_two(self.parse("audit_berry.ndjson", "berry"))

    def test_empty_output(self):
        self.assertEqual(audit.parse_output("", "npm"), [])
        self.assertEqual(audit.parse_output('{"vulnerabilities": {}}'), [])

    def test_detect_pm_and_missing_lockfile(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(audit.detect_pm(d))
            self.assertEqual(audit.run_audit(d, source="pm")["error"], "no lockfile found")
            self.assertEqual(audit.run_audit(d, source="osv")["error"], "no lockfile and no exact pins")
            with open(os.path.join(d, "yarn.lock"), "w") as f:
                f.write("# yarn lockfile v1\n")
            self.assertEqual(audit.detect_pm(d), "yarn")
            with open(os.path.join(d, "yarn.lock"), "w") as f:
                f.write("__metadata:\n  version: 8\n")
            self.assertEqual(audit.detect_pm(d), "yarn-berry")
            with open(os.path.join(d, "pnpm-lock.yaml"), "w") as f:
                f.write("lockfileVersion: '9.0'\n")
            self.assertEqual(audit.detect_pm(d), "pnpm")


class LedgerFilterTest(unittest.TestCase):
    def test_filter_splits_new_reshow_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.json")
            prior = [{"vendor": "A", "url": "u1", "title": "t1", "decision": "ticketed"},
                     {"vendor": "A", "url": "u2", "title": "t2", "decision": "watch"},
                     {"vendor": "A", "url": "u3", "title": "t3", "decision": "pending"},
                     {"vendor": "A", "url": "u4", "title": "t4", "decision": "auto-dismissed"}]
            prior[0]["body"] = "x" * 500
            prior[3]["body"] = "noise body that should not be stored"
            ledger.add_many(path, prior)
            with open(path) as f:
                stored = json.load(f)["items"]
            self.assertEqual(len(stored[0]["body"]), 203)
            self.assertNotIn("body", stored[3])  # auto-dismissed entries are compact
            incoming = [{"vendor": "A", "url": f"u{n}", "title": f"t{n}"} for n in range(1, 6)]
            r = run("ledger.py", path, "filter", stdin=json.dumps({"items": incoming}))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertEqual([i["title"] for i in out["new"]], ["t5"])
            self.assertEqual([(i["title"], i["note"]) for i in out["reshow"]],
                             [("t2", "previously watched"),
                              ("t3", "previously proposed, awaiting decision")])
            self.assertEqual(out["dropped"], 2)
            self.assertTrue(all(i["hash"] for i in out["new"] + out["reshow"]))


class SampleProjectTest(unittest.TestCase):
    """The committed samples stay in sync with the scripts and the example project."""

    def test_sample_stack_md_has_no_drift(self):
        scan = run("scan_repo.py", EXAMPLE)
        self.assertEqual(scan.returncode, 0, scan.stderr)
        with tempfile.TemporaryDirectory() as d:
            scan_path = os.path.join(d, "scan.json")
            with open(scan_path, "w") as f:
                f.write(scan.stdout)
            r = run("diff_stack.py", scan_path, os.path.join(SAMPLES, "STACK.md"))
        self.assertEqual(r.returncode, 0, r.stdout)
        items = {i["name"]: i for i in json.loads(scan.stdout)["items"]}
        self.assertEqual(items["next"]["version"], "14.2.21")
        self.assertEqual(items["Google Analytics"]["section"], "analytics")
        self.assertEqual(items["stripe"]["category"], "payments")
        self.assertEqual(items["Node.js"]["version"], "20.11.1")

    def test_sample_sources_json_is_well_formed(self):
        with open(os.path.join(SAMPLES, "sources.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["schema_version"], 1)
        for v in doc["vendors"]:
            self.assertIn(v["status"], {"verified", "unverified", "retired"})
            for s in v["sources"]:
                self.assertTrue(s.get("url") or s.get("command"))
                self.assertRegex(s["verified"], r"^\d{4}-\d{2}-\d{2}$")

    def test_example_env_file_is_names_only(self):
        with open(os.path.join(EXAMPLE, ".env.example"), encoding="utf-8") as f:
            for line in f:
                self.assertRegex(line.strip(), r"^[A-Z_]+=$")


if __name__ == "__main__":
    unittest.main()


class AuditOsvTest(unittest.TestCase):
    def test_parse_osv_matches_npm_audit_hashes(self):
        with open(os.path.join(FIXTURES, "osv_query.json"), encoding="utf-8") as f:
            resp = json.load(f)
        items = audit.parse_osv([resp], direct={"drizzle-orm"})
        self.assertEqual(len(items), 2)
        ghsa = items[0]
        self.assertEqual(ghsa["url"], "https://github.com/advisories/GHSA-gpj5-g38j-94v9")
        self.assertEqual(ghsa["title"],
                         "high severity: Drizzle ORM has SQL injection via improperly escaped SQL identifiers")
        self.assertEqual(ghsa["vulnerable_range"], "<0.45.2, >=1.0.0-beta.2 <1.0.0-beta.20")
        self.assertIn("Fix: upgrade drizzle-orm to 0.45.2.", ghsa["body"])  # lowest stable fix above 0.38.3
        self.assertTrue(ghsa["direct"])
        # same hash as the npm-audit item for this advisory
        npm_items = audit.parse_output(read_fixture("audit_npm7.json"), "npm")
        self.assertEqual(ghsa["hash"], audit.make_item(
            "drizzle-orm", ghsa["title"].split(": ", 1)[1], ghsa["url"], "high", None, None, True)["hash"])
        self.assertTrue(all(i["hash"] for i in npm_items))
        mal = items[1]
        self.assertEqual(mal["url"], "https://github.com/advisories/GHSA-aaaa-bbbb-cccc")  # alias wins
        self.assertEqual(mal["advisory_severity"], "unknown")
        self.assertEqual(mal["vulnerable_range"], ">=0.38.0 <=0.38.9")

    def test_parse_output_detects_osv(self):
        items = audit.parse_output(read_fixture("osv_query.json"))
        self.assertEqual(len(items), 2)

    def test_locked_packages_from_example(self):
        locked, direct, unresolved = audit.locked_packages(EXAMPLE)
        self.assertEqual(locked["next"], "14.2.21")
        self.assertIn("typescript", direct)
        self.assertEqual(unresolved, [])


class LifecycleTest(unittest.TestCase):
    NODE_CYCLES = [
        {"cycle": "26", "eol": "2029-04-30", "latest": "26.12.1", "lts": "2026-10-28"},
        {"cycle": "24", "eol": "2028-04-30", "latest": "24.22.1", "lts": "2025-10-28"},
        {"cycle": "22", "eol": "2027-04-30", "latest": "22.23.4", "lts": True},
        {"cycle": "20", "eol": "2026-04-30", "latest": "20.20.2", "lts": True},
    ]
    TW_CYCLES = [{"cycle": "4.1", "eol": False, "latest": "4.1.9"}, {"cycle": "3.4", "eol": "2028-01-01", "latest": "3.4.19"}]

    def test_eol_row_end_of_life(self):
        import lifecycle
        row = lifecycle.eol_row("Node.js", "nodejs", "20.11.1", self.NODE_CYCLES, "2026-10-22", 120)
        self.assertEqual(row["status"], "end-of-life")
        self.assertEqual(row["latest_in_cycle"], "20.20.2")
        self.assertEqual(row["supported_newer_cycles"], ["26", "24", "22"])
        item = lifecycle.eol_item(row)
        self.assertEqual(item["title"], "Node.js 20 reached end of life on 2026-04-30")
        self.assertEqual(item["severity"], "Deprecation")
        self.assertEqual(item["url"], "https://endoflife.date/nodejs")

    def test_eol_row_soon_and_supported(self):
        import lifecycle
        soon = lifecycle.eol_row("Node.js", "nodejs", "22.1.0", self.NODE_CYCLES, "2027-02-01", 120)
        self.assertEqual(soon["status"], "ending soon")
        self.assertIn("reaches end of life on 2027-04-30", lifecycle.eol_item(soon)["title"])
        ok = lifecycle.eol_row("Node.js", "nodejs", ">=24", self.NODE_CYCLES, "2026-10-22", 120)
        self.assertEqual(ok["status"], "supported")
        self.assertIsNone(lifecycle.eol_item(ok))

    def test_minor_cycles_and_unknown(self):
        import lifecycle
        row = lifecycle.eol_row("tailwindcss", "tailwind-css", "3.4.17", self.TW_CYCLES, "2026-10-22", 120)
        self.assertEqual(row["cycle"], "3.4")
        self.assertEqual(row["status"], "supported")
        self.assertEqual(row["supported_newer_cycles"], ["4.1"])
        unknown = lifecycle.eol_row("tailwindcss", "tailwind-css", "2.0.0", self.TW_CYCLES, "2026-10-22", 120)
        self.assertEqual(unknown["status"], "unknown cycle")

    def test_version_row_and_deprecation(self):
        import lifecycle
        doc = {"dist-tags": {"latest": "16.4.2", "canary": "16.5.0-canary.1"},
               "versions": {"14.2.21": {"deprecated": "This version has a security vulnerability."},
                            "14.2.35": {}, "15.5.28": {}, "16.4.2": {}, "16.5.0-canary.1": {}}}
        row = lifecycle.version_row("next", "14.2.21", doc)
        self.assertEqual((row["latest"], row["latest_in_major"], row["majors_behind"]), ("16.4.2", "14.2.35", 2))
        item = lifecycle.deprecation_item(row)
        self.assertTrue(item["title"].startswith("next@14.2.21 is deprecated on npm: This version"))
        self.assertEqual(item["url"], "https://www.npmjs.com/package/next/v/14.2.21")
        ranged = lifecycle.version_row("next", "^14.2.0", doc)
        self.assertFalse(ranged["exact"])
        self.assertIsNone(lifecycle.deprecation_item(ranged))

    def test_check_with_injected_fetch(self):
        import lifecycle
        def fake(url, timeout, accept=None):
            if "endoflife" in url:
                return self.NODE_CYCLES
            return {"dist-tags": {"latest": "2.0.0"}, "versions": {"1.0.0": {"deprecated": "use 2"}, "2.0.0": {}}}
        scan = {"items": [{"section": "runtime", "name": "Node.js", "version": "20.11.1"},
                          {"section": "key_package", "name": "zod", "version": "1.0.0"},
                          {"section": "framework", "name": "Next.js config", "version": None}]}
        out = lifecycle.check(scan, today="2026-10-22", fetch=fake)
        self.assertEqual([i["severity"] for i in out["items"]], ["Deprecation", "Deprecation"])
        self.assertEqual(len(out["versions"]), 1)
        self.assertEqual(out["errors"], [])


class DiscoverSourcesTest(unittest.TestCase):
    def test_parse_repository_shapes(self):
        import discover_sources as ds
        for v in ["git+https://github.com/vercel/next.js.git", "git@github.com:vercel/next.js.git",
                  "github:vercel/next.js", "vercel/next.js", {"type": "git", "url": "https://github.com/vercel/next.js"},
                  "git+ssh://git@github.com/vercel/next.js.git#main"]:
            self.assertEqual(ds.parse_repository(v), ("vercel", "next.js"), v)
        self.assertIsNone(ds.parse_repository("https://gitlab.com/o/r.git"))
        self.assertIsNone(ds.parse_repository(""))
        self.assertIsNone(ds.parse_repository(None))

    def test_feed_and_changelog_links(self):
        import discover_sources as ds
        page = '''<html><head>
          <link rel="alternate" type="application/rss+xml" title="Changelog" href="/changelog/rss.xml">
          <link rel='alternate' type='application/atom+xml' href='https://example.com/atom.xml'/>
          <link rel="stylesheet" href="/x.css"></head>
          <body><a href="/changelog">Changelog</a><a href="https://other.com/changelog">x</a>
          <a href="/docs/release-notes">Release notes</a></body></html>'''
        self.assertEqual(ds.feed_links_in_html(page, "https://www.example.com/"),
                         ["https://www.example.com/changelog/rss.xml", "https://example.com/atom.xml"])
        self.assertEqual(ds.changelog_links_in_html(page, "https://www.example.com/"),
                         ["https://www.example.com/changelog", "https://www.example.com/docs/release-notes"])
        self.assertTrue(ds.looks_like_feed('<?xml version="1.0"?><rss version="2.0">'))
        self.assertFalse(ds.looks_like_feed("<!DOCTYPE html><html>"))

    def test_group_by_vendor(self):
        import discover_sources as ds
        recs = [{"package": "react", "repository": "github:facebook/react", "homepage": "https://react.dev/"},
                {"package": "react-dom", "repository": "https://github.com/facebook/react.git", "homepage": "https://react.dev/"},
                {"package": "@types/node", "repository": "https://github.com/DefinitelyTyped/DefinitelyTyped.git", "homepage": None},
                {"package": "mystery", "repository": None, "homepage": "https://www.mystery.dev/docs"},
                {"package": "lonely", "repository": None, "homepage": "https://github.com/x/lonely#readme"}]
        groups = ds.group_by_vendor(recs)
        self.assertEqual(sorted(groups), ["DefinitelyTyped/DefinitelyTyped", "facebook/react", "lonely", "mystery.dev"])
        self.assertEqual(groups["facebook/react"]["packages"], ["react", "react-dom"])
        self.assertEqual(groups["facebook/react"]["repository"], "https://github.com/facebook/react")

    def test_probe_and_discover_with_fakes(self):
        import discover_sources as ds
        def fake_fetch(url, timeout, limit=0):
            if url.endswith("/releases.atom"):
                return '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry/><entry/></feed>', url
            if url == "https://acme.dev/":
                return '<html><head><link rel="alternate" type="application/rss+xml" href="/changelog/rss.xml"></head>' \
                       '<body><a href="/changelog">Changelog</a></body></html>', url
            if url == "https://acme.dev/changelog/rss.xml":
                return '<rss version="2.0"><channel/></rss>', url
            raise ds.urllib.error.URLError("404")
        def fake_json(url, timeout):
            name = url.split("registry.npmjs.org/")[1].rsplit("/latest", 1)[0]
            return {"acme-sdk": {"repository": "github:acme/acme-js", "homepage": "https://acme.dev/"},
                    "@types/node": {"repository": "https://github.com/DefinitelyTyped/DefinitelyTyped.git"},
                    "next": {"repository": "vercel/next.js"}}[name]
        scan = {"items": [{"section": "key_package", "name": "acme-sdk", "version": "1.0.0"},
                          {"section": "key_package", "name": "@types/node", "version": "22.0.0"},
                          {"section": "framework", "name": "next", "version": "14.2.21"},
                          {"section": "framework", "name": "Next.js config", "version": None}]}
        existing = {"vendors": [{"vendor": "Next.js", "matches": ["next", "next.config.*"], "sources": [], "status": "verified"}]}
        out = ds.discover(scan, existing, fetch=fake_fetch, fetch_json_fn=fake_json, today="2026-10-22")
        self.assertEqual(out["already_covered"], ["next"])
        self.assertEqual(out["errors"], [])
        vendors = {v["vendor"]: v for v in out["vendors"]}
        acme = vendors["acme-js"]
        self.assertEqual(acme["matches"], ["acme-sdk"])
        self.assertEqual(acme["status"], "unverified")
        types = [s["type"] for s in acme["sources"]]
        self.assertEqual(types, ["github-releases", "changelog"])
        self.assertEqual(acme["sources"][0]["feed"], "https://github.com/acme/acme-js/releases.atom")
        self.assertIn("2 release(s)", acme["sources"][0]["note"])
        self.assertEqual(acme["sources"][1]["feed"], "https://acme.dev/changelog/rss.xml")
        self.assertEqual(acme["sources"][1]["url"], "https://acme.dev/changelog")
        self.assertEqual(vendors["DefinitelyTyped"]["sources"], [])  # type stubs are not a vendor


class HeadlessTest(unittest.TestCase):
    def test_build_digest(self):
        import headless
        filtered = {"new": [{"vendor": "next", "title": "critical severity: RCE | pipes", "url": "https://u1",
                             "date": None, "source_type": "advisory"},
                            {"vendor": "Vercel", "title": "Retention changes", "url": "https://u2",
                             "date": "2026-10-09", "source_type": "changelog"}],
                    "reshow": [{"vendor": "Neon", "title": "Free plan storage", "url": "https://u3",
                                "date": "2026-10-02", "source_type": "changelog", "note": "previously watched"}],
                    "dropped": 7}
        feed = {"sources": [{"vendor": "Stripe", "url": "https://s", "status": "unparsed"},
                            {"vendor": "Down", "url": "https://d", "status": "unreachable", "error": "HTTP 503"}]}
        drift = {"added": [{"section": "Key packages", "item": "zod", "version": "4.0.0"}],
                 "version_changed": [{"section": "Framework", "item": "next", "stack_md": "14.2.21", "repo": "15.5.28"}],
                 "missing_first_time": [], "missing_second_time": [],
                 "summary": {"added": 1, "version_changed": 1, "missing_first_time": 0, "missing_second_time": 0}}
        md = headless.build_digest("app", "2026-10-01", "2026-10-22", filtered, feed,
                                   drift, {"error": None}, {"errors": ["endoflife.date nuxt: HTTP 404"]})
        self.assertTrue(md.startswith("# stack-watch: 2 new item(s) for app"))
        self.assertIn("## Stack drift (2)", md)
        self.assertIn("version changed: Framework / next 14.2.21 -> 15.5.28", md)
        rows = [l for l in md.splitlines() if l.startswith("| ") and "|---" not in l and "Date" not in l]
        self.assertEqual(len(rows), 3)
        self.assertIn("advisory", rows[0])  # advisories sort first
        self.assertIn("critical severity: RCE \\| pipes", rows[0])
        self.assertIn("changelog (previously watched)", md)
        self.assertIn("- Stripe: https://s", md)
        self.assertIn("(HTTP 503)", md)
        self.assertIn("- endoflife.date nuxt: HTTP 404", md)

    def test_headless_requires_sources(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("headless.py", d, "--out", os.path.join(d, "out"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("run a bootstrap first", r.stdout)
