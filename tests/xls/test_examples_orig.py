"""The XLS examples' upstream copies are what UPSTREAM says they are.

examples/xls/*/orig/ holds XLS files byte for byte; UPSTREAM records the sha256
of each. gcd/dslx_top/gcd_tops.x is gcd.x plus appended wrappers: the copy must
stay identical to orig/ above its marker line.
"""
import hashlib
from pathlib import Path

import pytest

XLS = Path(__file__).resolve().parents[2] / "examples" / "xls"
ORIGS = sorted(XLS.glob("*/orig/UPSTREAM"))


@pytest.mark.parametrize("upstream", ORIGS, ids=lambda p: p.parent.parent.name)
def test_orig_matches_upstream_sha256(upstream):
    entries = [l.split() for l in upstream.read_text().splitlines() if l.startswith("  ")]
    assert entries, upstream
    for digest, rel in entries:
        data = (upstream.parent / rel).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, rel


def test_gcd_tops_holds_gcd_x_verbatim():
    orig = (XLS / "gcd/orig/xls/examples/gcd.x").read_text()
    tops = (XLS / "gcd/dslx_top/gcd_tops.x").read_text()
    head, sep, _ = tops.partition("\n// ---- appended")
    assert sep and head.rstrip("\n").endswith(orig.rstrip("\n")) and orig in tops
