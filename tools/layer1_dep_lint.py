#!/usr/bin/env python3
"""Dependency lint for the layer-1 repos (docs/design/core-layer1.md §2).

- Nothing in fw-hdl-spec names anything outside it: no tool repo, no
  fw.hdl Python package, nothing of this repo's src/ or python/.
- fw-hdl-rt-sv and fw-hdl-fe-sv name nothing in this repo's src/ or
  python/, and nothing in each other.

Scans the repos' tracked-or-new text files (git ls-files, skipping
rundir/ and caches). Exit status 1 on any finding.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKGS = os.path.join(ROOT, "packages")

# (repo, forbidden patterns)
UMBRELLA = [r"fw-hdl-sync/(src|python)/", r"\.\./\.\./\.\./(src|python)/",
            r"\bfrom fw\.hdl\.(?!fe\.sv|rt\.sv|gen)\w", r"\bimport fw\.hdl\.(?!fe\.sv|rt\.sv|gen)\w",
            r"\bfw_root\b", r"\bfw_extern_impl\b"]
RULES = {
    "fw-hdl-spec": UMBRELLA + [r"fw-hdl-(rt|fe)-sv", r"\bfw\.hdl\.(rt|fe)\.sv\b"],
    "fw-hdl-rt-sv": UMBRELLA + [r"fw-hdl-fe-sv", r"\bfw\.hdl\.fe\.sv\b"],
    "fw-hdl-fe-sv": UMBRELLA + [r"fw-hdl-rt-sv", r"\bfw\.hdl\.rt\.sv\b"],
}
# Code and flows; prose (.md, .rst) may mention other repos.
TEXT = (".py", ".sv", ".svh", ".yaml", ".dv", ".toml", ".json", ".f")


def files(repo):
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=repo, capture_output=True, text=True, check=True).stdout
    for f in out.splitlines():
        if f.startswith(("rundir/", "docs/_build/")) or "/__pycache__/" in f:
            continue
        if f.endswith(TEXT):
            yield f


def main():
    bad = 0
    for name, pats in RULES.items():
        repo = os.path.join(PKGS, name)
        rx = [re.compile(p) for p in pats]
        for f in files(repo):
            with open(os.path.join(repo, f), errors="replace") as fp:
                for n, line in enumerate(fp, 1):
                    for r in rx:
                        if r.search(line):
                            print(f"{name}/{f}:{n}: names {r.pattern!r}: {line.strip()[:100]}")
                            bad += 1
    print(f"layer-1 dependency lint: {bad} finding(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
