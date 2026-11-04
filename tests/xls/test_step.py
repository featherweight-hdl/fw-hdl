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


def rr_stall_ref(sched, cycles, stalls):
    """rr_ref with out back-pressured in the *stalls* cycles: a cycle whose
    grant finds out not ready has no effect at all (no refill either)."""
    pend = [list(sched.get(f"in{k}", [])) for k in range(4)]
    full, hold, nxt, out = [False] * 4, [0] * 4, 0, []
    for cyc in range(cycles):
        g = next((i for i in ((nxt + k) % 4 for k in range(4)) if full[i]), None)
        if g is not None and cyc in stalls:
            continue
        if g is not None:
            out.append((cyc, (g << 8) | hold[g]))
            full[g], nxt = False, (g + 1) % 4
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


# Out back-pressured in runs, and while inputs are still arriving.
RR_STALLS = {2, 3, 4, 7, 11, 12, 13, 14, 18}


@needs_sim
@pytest.mark.parametrize("stalls", [set(), RR_STALLS], ids=["ready", "stalled"])
def test_rr_stall_cycle_exact(tmp_path, stalls):
    """An all-or-nothing step: model and RTL cycle for cycle under the same
    back-pressure, and both match the reference. With out always ready it
    is f6_rr."""
    got = check_step([PKG], "micro_f6_pkg", "f6_rr_stall", RR_IN, 28, tmp_path,
                     stalls={"out": sorted(stalls)})
    assert got == rr_stall_ref(RR_IN, 28, stalls)
    if not stalls:
        assert got == rr_ref(RR_IN, 28)
    assert not any(c in stalls for c, _ in got["out"])
    assert sorted(v & 0xFF for _, v in got["out"]) == \
        sorted(v for s in RR_IN.values() for _, v in s)


def tee2_ref(sched, cycles, stalls):
    """Each value to a and b, tagged with the count before it. An output
    that is ready takes the value, once; the cycle commits (takes the input,
    counts) only when both have it."""
    pend, n, sent, out = list(sched["in"]), 0, set(), {"a": [], "b": []}
    for cyc in range(cycles):
        if not pend or pend[0][0] > cyc:
            continue
        v = (n << 8) | pend[0][1]
        for o in ("a", "b"):
            if o not in sent and cyc not in stalls[o]:
                out[o].append((cyc, v))
                sent.add(o)
        if sent == {"a", "b"}:
            pend.pop(0)
            n, sent = n + 1, set()
    return out


TEE_IN = {"in": [(c, 0x40 + c) for c in range(0, 24, 2)] + [(c, 0x80 + c) for c in range(3, 9)]}
TEE_IN["in"].sort()
TEE_STALLS = {"a": [2, 3, 4, 9, 10, 15], "b": [0, 1, 4, 5, 6, 11, 15, 16, 17, 18]}


def test_tee2_ref_sends_once():
    """a is ready in cycle 0 and b is not: the value goes to a in cycle 0
    and to b in cycle 2, and the next value is taken in cycle 3."""
    got = tee2_ref({"in": [(0, 1), (0, 2)]}, 6, {"a": [], "b": [0, 1]})
    assert got == {"a": [(0, 0x001), (3, 0x102)], "b": [(2, 0x001), (3, 0x102)]}


@needs_sim
def test_tee2_cycle_exact(tmp_path):
    """Two stalling outputs, back-pressured independently: model and RTL
    cycle for cycle, and both match the reference. XLS sends to an output
    that is ready and marks it done, as the model does."""
    got = check_step([PKG], "micro_f6_pkg", "f6_tee2", TEE_IN, 40, tmp_path,
                     stalls=TEE_STALLS)
    assert got == tee2_ref(TEE_IN, 40, TEE_STALLS)
    assert [v & 0xFF for _, v in got["a"]] == [v for _, v in TEE_IN["in"]]


def test_atomic_step_lowers_to_one_blocking_send():
    """put_or_stall is the proc's one send, which blocks (a stall stalls the
    activation); every receive stays non-blocking and unordered."""
    txt = _ir("f6_rr_stall")
    recvs = re.findall(r"receive\((\w+)[^)]*blocking=false", txt)
    assert len(recvs) == 4 and "blocking=true" not in txt
    assert all(t.startswith("after_all") for t in recvs), recvs
    sends = re.findall(r"= send\(([^)]*)\)", txt)
    assert len(sends) == 1 and "predicate=" in sends[0] and "channel=out" in sends[0]


def test_step_receives_share_a_stage():
    """A step is one cycle, so codegen keeps its streaming receives in one
    stage; a process (run()) leaves XLS free to spread them."""
    from zuspec.be.xls.lower_proc import codegen_flags, lower_component
    comp = sv_to_component([PKG], "f6_rr")
    assert codegen_flags(comp, lower_component(comp)) == [
        "--io_constraints=" + ",".join(f"in0:recv:in{k}:recv:0:0" for k in (1, 2, 3))]
    proc = sv_to_component([str(HERE / "micro" / "micro_proc_pkg.sv")], "p_pred")
    assert codegen_flags(proc, lower_component(proc)) == []
    # Channels are named as the IR names them: `ret` is a keyword (ret_).
    dep = sv_to_component([str(HERE / "lib" / "lib_dep_pkg.sv")], "dep_4_4")
    assert codegen_flags(dep, lower_component(dep)) == ["--io_constraints=ent:recv:ret_:recv:0:0"]


def test_put_or_stall_needs_an_atomic_step():
    with pytest.raises(FwHdlError, match=r"micro_f6_pkg.sv:\d+:\d+: .*put_or_stall\(\) "
                                         r"stalls the whole step"):
        sv_to_component([PKG], "f6_bad_stall")


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


BAD_PUT = '''`include "fw_std_macros.svh"
package bad_put_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class bad_put extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0]))    out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual function void step();
            bit [7:0] x;
            if (in.t.try_get(x))
                out.t.put(x);
        endfunction
    endclass
endpackage
'''


def test_blocking_put_in_a_step_rejected(tmp_path):
    """A put that waits for ready is a task, so it cannot be called from
    step(): rejected at its line."""
    (tmp_path / "bad_put.sv").write_text(BAD_PUT)
    with pytest.raises(Exception, match=r"bad_put.sv:19:\d+: error: cannot invoke a task"):
        sv_to_component([str(tmp_path / "bad_put.sv")], "bad_put")
