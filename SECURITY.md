# Security

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: open the **Security** tab of this repository and choose **Report a vulnerability**. Please do not open a public issue for anything exploitable. You should hear back within a week.

## What is in scope

stack-watch reads untrusted input by design: vendor changelogs and release feeds, npm registry records, endoflife.date, OSV.dev, and the `package.json` and lockfile of the repository it scans. In headless mode it runs unattended in GitHub Actions with a token that can write issues. Reports are welcome on anything that lets that input:

- read a file or reach a host the tool should not (the scripts accept http(s) only, refuse credentials in URLs, refuse private and link-local addresses unless `--allow-private-hosts` is given, and cap response sizes);
- run code (the scripts never use a shell; the only subprocesses are `git rev-parse` and, outside headless mode, the package manager's own `audit` command);
- leak a token (the `GITHUB_TOKEN` is sent to `api.github.com` only and dropped on any redirect to another host);
- put text in front of a person that looks like it came from the tool (digests and reports quote vendor text as data; mentions and markdown in titles are neutralized).

Out of scope: vulnerabilities in the vendors whose changelogs stack-watch reads, and the fixture project under `examples/`, which intentionally pins old versions with known advisories so the sample output has something to show. Its `package.json` and lockfile are generated locally rather than committed, so those pins do not appear as Dependabot alerts on this repository.

## Supply chain

The scheduled workflow template pins stack-watch to a release tag and the actions it uses to commit SHAs. Dependabot keeps the action pins current. Releases are tagged; the plugin manifests carry the same version.
