"""fw_arbiter: an all-or-nothing cycle step, mapped from its step().

* A Python model of the per-cycle rules (fw_arbiter.svh's header) against the
  class model, and the class model against XLS's RTL, cycle for cycle, with
  out back-pressured at random.
* The class against the ``rr_arb`` XLS IR template (fw.hdl.lib.xls_ir), cycle
  for cycle under the same back-pressure: the hand-built proc the class
  replaces.
* The arbiter as a child of a structural component: model and RTL under the
  class's contract.
"""
import random
from pathlib import Path

import pytest
import yaml

from fw.hdl.lib import xls_ir
from fw.hdl.verif.canon import Event, Rule, check, compare
from fw.hdl.xls_flow import sv_to_structure
from zuspec.be.xls.testing.xlstools import CodegenOptions, codegen_main, opt_main, run_codegen
from xls_harness import (REPO, _trace, check_step, have_verilator, proc_testbench,
                         rtl_step_testbench, rtl_testbench, run_verilator)

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "lib_arb_pkg.sv")
FILES = [PKG]
RTL_LIB = [REPO / "src" / "rtl" / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv")]
CONTRACT = yaml.safe_load((REPO / "src" / "std" / "arb" / "fw_arbiter.yaml").read_text())
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")

# typedef in lib_arb_pkg.sv: (width, N, fixed priority)
CLASSES = {"arb_3r": (8, 3, False), "arb_3p": (8, 3, True), "arb_5r": (6, 5, False),
           "arb_1": (8, 1, False)}
CYCLES = 80


# --- the per-cycle rules ------------------------------------------------------
def arb_ref(w, n, prio, sched, cycles, stalls):
    """Grant over the holds full at the start of the cycle, by policy; if out
    is not ready, the cycle has no effect. Then refill every hold that was
    empty or was granted. Round robin looks first at the input after the
    last winner, input 0 first."""
    pend = [list(sched.get(f"in_{k}", [])) for k in range(n)]
    full, hold, nxt, out = [False] * n, [0] * n, 0, []
    for cyc in range(cycles):
        order = range(n) if prio else [(nxt + j) % n for j in range(n)]
        g = next((k for k in order if full[k]), None)
        if g is not None and cyc in stalls:
            continue
        if g is not None:
            out.append((cyc, (g << w) | hold[g]))
            full[g], nxt = False, (g + 1) % n
        for k in range(n):
            if not full[k] and pend[k] and pend[k][0][0] <= cyc:
                hold[k], full[k] = pend[k].pop(0)[1], True
    return out


def gen(w, n, seed):
    """Random arrivals (busy and sparse inputs) and the cycles out stalls."""
    rng = random.Random(seed)
    sched = {}
    for k in range(n):
        c, xs, gap = 0, [], rng.choice([1, 3, 6])
        while True:
            c += rng.randint(0, gap)
            if c >= CYCLES - 20:
                break
            xs.append((c, rng.randrange(1 << w)))
        sched[f"in_{k}"] = xs
    p = rng.choice([0.2, 0.5]) if seed % 3 else 0.0
    return sched, sorted(c for c in range(CYCLES) if rng.random() < p)


def contract_errors(w, sched, out):
    """Values leave in order per input (the contract): each output, the i-th
    from input k, carries the i-th value input k offered."""
    ev, n = [], {}
    for c, v in out:
        k = v >> w
        i = n[k] = n.get(k, -1) + 1
        at, x = sched[f"in_{k}"][i]
        ev.append(Event("in", "in", at, (k << 16) | i, key=k, data=x))
        ev.append(Event("out", "out", c, (k << 16) | i, key=k, data=v & ((1 << w) - 1)))
    ev.sort(key=lambda e: (e.cyc, e.ev != "in"))
    return check(ev, Rule.from_dict(CONTRACT["order"]))


def test_ref_tie_rule():
    """Every input waiting from cycle 0, out always ready: one grant per
    cycle from cycle 1 (a value is held before it can win), by policy."""
    sched = {f"in_{k}": [(0, b + i) for i in range(4)] for k, b in enumerate((0x10, 0x20, 0x30))}
    g = lambda k, v: (k << 8) | v
    assert [v for _, v in arb_ref(8, 3, False, sched, 6, set())] == \
        [g(0, 0x10), g(1, 0x20), g(2, 0x30), g(0, 0x11), g(1, 0x21)]
    assert [v for _, v in arb_ref(8, 3, True, sched, 6, set())] == \
        [g(0, 0x10), g(0, 0x11), g(0, 0x12), g(0, 0x13), g(1, 0x20)]
    assert arb_ref(8, 3, False, sched, 2, set())[0][0] == 1


def test_ref_stall_freezes_everything():
    """Input 1's value is held in cycle 0; out stalls in cycles 1-3. Input
    0's value, offered from cycle 2, is not taken while out stalls (no hold
    fills), so the grant is not re-made: input 1 leaves in cycle 4 and input
    0 in cycle 5, under both policies."""
    sched = {"in_1": [(0, 0x21)], "in_0": [(2, 0x05)]}
    for prio in (False, True):
        assert arb_ref(8, 3, prio, sched, 8, {1, 2, 3}) == [(4, 0x121), (5, 0x005)]


# --- class model and RTL ------------------------------------------------------
@needs_sim
@pytest.mark.parametrize("name", sorted(CLASSES))
def test_model_and_rtl(tmp_path, name):
    """Seed 3 has out always ready, at 1 and 2 stages; seeds 1 and 2 stall
    out at random (1 stage: back-pressure is per cycle, so a later stage
    would see it in other cycles)."""
    w, n, prio = CLASSES[name]
    for seed in (1, 2, 3):
        sched, stalls = gen(w, n, seed)
        got = check_step([PKG], "lib_arb_pkg", name, sched, CYCLES, tmp_path / f"s{seed}",
                         rtl_stages=(1, 2) if not stalls else (1,),
                         stalls={"out": stalls})
        want = arb_ref(w, n, prio, sched, CYCLES, set(stalls))
        assert got.get("out", []) == want, f"seed {seed}"
        assert contract_errors(w, sched, want) == [], f"seed {seed}"


@needs_sim
@needs_xls
@pytest.mark.parametrize("prio", [False, True], ids=["rr", "prio"])
def test_matches_the_template(tmp_path, prio):
    """Three inputs: the class and the rr_arb template, cycle for cycle,
    under the same back-pressure."""
    name = "arb_3p" if prio else "arb_3r"
    for seed in (1, 2, 4):
        sched, stalls = gen(8, 3, seed)
        d = tmp_path / f"s{seed}"
        got = check_step([PKG], "lib_arb_pkg", name, sched, CYCLES, d, stalls={"out": stalls})
        ins = [f"in_{k}" for k in range(3)]
        pkg = xls_ir.package("t", xls_ir.rr_arb(3, 8, name="t", ins=ins, out="out", prio=prio))
        res = run_codegen(pkg, CodegenOptions(), stages=1,
                          extra=["--flop_inputs=false", "--flop_outputs=false"])
        (d / "t.sv").write_text(res.verilog)
        (d / "tb.sv").write_text(rtl_step_testbench(res.signature, sched, CYCLES,
                                                    {"out": stalls}))
        tmpl = _trace(run_verilator([d / "t.sv", d / "tb.sv"], "xh_rtl_step_tb", d / "tmpl",
                                    with_lib=False))
        assert tmpl.get("out", []) == got.get("out", []), f"seed {seed}"


# --- as a child ---------------------------------------------------------------
# top: (width, input ports)
TOPS = {"arb3_rr": (8, "abc"), "arb3_prio": (8, "abc"), "arb5_rr": (6, "abcde")}


def _rtl(tmp_path, top, inputs, seed, stages):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, ["fw_arbiter"], stages=stages)
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, inputs, seed))
    out = run_verilator(paths + RTL_LIB + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    return [int(l.split()[3], 16) for l in out if l.startswith("O out ")]


def _model(tmp_path, top, inputs):
    comp = sv_to_structure(FILES, top).component
    tb = tmp_path / "xh_proc_tb.sv"
    tb.write_text(proc_testbench(["lib_arb_pkg"], top, comp, inputs, clocked=True))
    out = run_verilator(FILES + [tb], "xh_proc_tb", tmp_path / "model")
    return [int(l.split()[3], 16) for l in out if l.startswith("O out ")]


def _events(w, ins, outs):
    """In events per input in order, out events in output order; key = input."""
    ev = [Event("in", "in", n, (k << 16) | i, key=k, data=x)
          for n, (k, i, x) in enumerate((k, i, x) for k, xs in enumerate(ins)
                                         for i, x in enumerate(xs))]
    seen = {}
    for j, v in enumerate(outs):
        k = v >> w
        i = seen.get(k, 0)
        seen[k] = i + 1
        ev.append(Event("out", "out", 10_000 + j, (k << 16) | i, key=k, data=v & ((1 << w) - 1)))
    return ev


@needs_xls
@needs_sim
@pytest.mark.parametrize("top", sorted(TOPS))
@pytest.mark.parametrize("stages", [1, 2])
def test_child_keeps_the_contract(tmp_path, top, stages):
    """In a structural parent, with the testbenches' own timing: model and
    RTL lose nothing and keep each input's order."""
    w, names = TOPS[top]
    rng = random.Random(stages * 31 + len(top))
    ins = [[rng.randrange(1 << w) for _ in range(rng.randint(20, 40))] for _ in names]
    inputs = dict(zip(names, ins))
    rule = Rule.from_dict(CONTRACT["order"])
    rtl = _rtl(tmp_path, top, inputs, seed=stages, stages=stages)
    model = _model(tmp_path, top, inputs)
    n = sum(map(len, ins))
    assert len(rtl) == len(model) == n                         # lossless
    assert check(_events(w, ins, rtl), rule) == []
    assert compare(_events(w, ins, model), _events(w, ins, rtl), rule,
                   names=("model", "rtl")) == []
