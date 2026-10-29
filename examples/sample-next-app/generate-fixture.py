#!/usr/bin/env python3
"""Write package.json and package-lock.json for the sample project.

Neither file is committed. The sample pins deliberately old versions so its
output has real findings, and GitHub's dependency graph reads any committed
package.json or lockfile and raises Dependabot alerts against this
repository for a fixture. package.sample.json holds the manifest and
locked-versions.json the exact versions. Run this before scanning the
sample by hand; the tests run it into a temporary copy.

Usage:
    python3 examples/sample-next-app/generate-fixture.py [target-dir]
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def build(target=HERE):
    with open(os.path.join(HERE, "package.sample.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    os.makedirs(target, exist_ok=True)
    with open(os.path.join(target, "package.json"), "w", encoding="utf-8") as f:
        json.dump(pkg, f, indent=2)
        f.write("\n")
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
