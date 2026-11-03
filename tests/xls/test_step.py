"""Cycle-step components (fw_steppable).

Each step-form class is checked three ways: its class model against an
independent Python model of what each cycle does, XLS's RTL against the class
model cycle for cycle, and the lowering rules (one activation at II=1, every
receive non-blocking, effects on different channels unordered).
"""
import re
from pathlib import Path

import pytest

from fw.hdl.errors import FwHdlError
from fw.hdl.xls_flow import sv_to_component, sv_to_xls
from zuspec.be.xls.printer import format_package
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main
from xls_harness import check_step, have_verilator

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "micro" / "micro_f6_pkg.sv")

needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


def _ir(cls):
    return format_package(sv_to_xls([PKG], cls))


# --- reference models: what one cycle does ------------------------------------
def count_ref(inc):
    total, out = 0, []
    for c, v in inc:
        total = (total + v) & 0xFFFF
        out.append((c, total))
    return {"out": out}


def rr_ref(sched, cycles):
    """Grant over the slots full at the start of the cycle, from the slot
    after the last grant; then refill every empty slot whose input offers."""
    pend = [list(sched.get(f"in{k}", [])) for k in range(4)]
    full, hold, last, out = [False] * 4, [0] * 4, 3, []
    for cyc in range(cycles):
        for k in range(1, 5):
            i = (last + k) % 4
            if full[i]:
                out.append((cyc, (i << 8) | hold[i]))
                full[i], last = False, i
                break
        for i in range(4):
            if not full[i] and pend[i] and pend[i][0][0] <= cyc:
                hold[i], full[i] = pend[i].pop(0)[1], True
    return {"out": out}


COUNT_IN = {"inc": [(0, 3), (1, 4), (3, 250), (4, 1), (5, 7), (9, 9), (10, 2)]}
RR_IN = {
    "in0": [(0, 0x10), (0, 0x11), (1, 0x12), (6, 0x13)],
    "in1": [(0, 0x20), (2, 0x21)],
    "in2": [(1, 0x30), (1, 0x31), (1, 0x32)],
    "in3": [(4, 0x40), (12, 0x41)],
}


@needs_sim
def test_count_cycle_exact(tmp_path):
    got = check_step([PKG], "micro_f6_pkg", "f6_count", COUNT_IN, 16, tmp_path,
                     rtl_stages=(1, 2))
    assert got == count_ref(COUNT_IN["inc"])


@needs_sim
def test_rr_cycle_exact(tmp_path):
    got = check_step([PKG], "micro_f6_pkg", "f6_rr", RR_IN, 24, tmp_path, rtl_stages=(1, 2))
    want = rr_ref(RR_IN, 24)
    assert got == want
    # Every input value is granted once, and contention rotates the grant.
    assert sorted(v & 0xFF for _, v in got["out"]) == \
        sorted(v for s in RR_IN.values() for _, v in s)


def test_step_lowers_to_nonblocking_unordered_proc():
    txt = _ir("f6_rr")
    recvs = re.findall(r"receive\((\w+)[^)]*blocking=false", txt)
    assert len(recvs) == 4 and "blocking=true" not in txt
    # Different channels: no receive takes the send's token or another's.
    assert all(t.startswith("after_all") for t in recvs), recvs
    assert re.search(r"send\(after_all", txt)


def test_run_and_step_rejected():
    with pytest.raises(FwHdlError, match="has both run\\(\\) and step\\(\\)"):
        sv_to_component([PKG], "f6_bad_both")
