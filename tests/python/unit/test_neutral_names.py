"""Neutral-name rule: code, tests, examples and user docs carry no names from
the deny list.

The deny list is a local data file (docs/research/neutral-names.deny) that is
not committed, so neither the repo nor this test holds the names. Without it
the tree check skips. docs/research/ is exempt: it cites the source
requirements.
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DENY = REPO_ROOT / "docs" / "research" / "neutral-names.deny"
TREES = ("src", "python", "tests", "examples", "docs")
EXEMPT = ("docs/research/",)


def load_patterns(path=DENY):
    pats = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pats.append(re.compile(line))
    return pats


def tracked_files(root=REPO_ROOT):
    """Tracked plus untracked-but-not-ignored files under TREES."""
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", *TREES],
        cwd=root, check=True, capture_output=True, text=True).stdout
    return [p for p in out.splitlines() if not p.startswith(EXEMPT)]


def find_hits(files, patterns, root=REPO_ROOT):
    hits = []
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for pat in patterns:
                if pat.search(line):
                    hits.append(f"{rel}:{n}: /{pat.pattern}/")
    return hits


needs_deny = pytest.mark.skipif(not DENY.exists(), reason=f"no local deny list ({DENY})")


@needs_deny
def test_deny_list_loads():
    assert len(load_patterns()) > 0


@needs_deny
def test_tree_has_no_denied_names():
    hits = find_hits(tracked_files(), load_patterns())
    assert not hits, "denied names found:\n" + "\n".join(hits)


def test_checker_catches_a_hit(tmp_path):
    # Build the offending word from the deny list itself, so it never
    # appears in this file.
    deny = tmp_path / "deny"
    deny.write_text("# test\n" + r"\bQZX" + "VQ\\b\n")
    (tmp_path / "f.sv").write_text("module m; // QZX" + "VQ here\nendmodule\n")
    hits = find_hits(["f.sv"], load_patterns(deny), root=tmp_path)
    assert hits == [r"f.sv:1: /\bQZXVQ\b/"]
