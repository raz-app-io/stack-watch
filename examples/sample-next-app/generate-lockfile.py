#!/usr/bin/env python3
"""Write package-lock.json for the sample project from locked-versions.json.

The lockfile is not committed: it pins deliberately old versions so the
sample output has real findings, and a committed lockfile would make
GitHub's dependency graph raise Dependabot alerts against this repository
for a fixture. Run this before scanning the sample by hand; the tests run
it into a temporary copy.

Usage:
    python3 examples/sample-next-app/generate-lockfile.py [target-dir]
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def build(target=HERE):
    with open(os.path.join(HERE, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    with open(os.path.join(HERE, "locked-versions.json"), encoding="utf-8") as f:
        versions = json.load(f)
    packages = {"": {"name": pkg.get("name", "sample-next-app")}}
    for name in {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}:
        version = versions[name]
        tarball = name.split("/")[-1]
        packages["node_modules/" + name] = {
            "version": version,
            "resolved": f"https://registry.npmjs.org/{name}/-/{tarball}-{version}.tgz",
        }
    lock = {"name": pkg.get("name", "sample-next-app"), "lockfileVersion": 3,
            "requires": True, "packages": packages}
    path = os.path.join(target, "package-lock.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2)
        f.write("\n")
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else HERE))
