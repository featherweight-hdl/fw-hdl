"""fw_channel between steps: the class model keeps fw_rv_fifo's timing.

lib_chan_pkg's chan_top: a step that passes each arriving value into the
channel (put_or_stall), and a step that passes each offered value on to
``out`` (try_get, then put_or_stall), with ``out`` back-pressured at random.

* A Python model of the per-cycle rules (fw_channel.svh's header) against
  the class model, and the class model against the RTL (the two steps'
  blocks and fw_rv_fifo, as Integrate wires them) cycle for cycle.
* Rate: DEPTH 1 runs at half rate (no pass-through when full); DEPTH 2 at
  full rate.
* At 2 stages: lossless and in order (the contract), timing free.
* A step on a DEPTH 0 channel (a wire) is rejected by partition and stops
  the class model.
"""
import random
from pathlib import Path

import pytest
import yaml

from fw.hdl.errors import FwHdlError
from fw.hdl.verif.canon import Event, Rule, check
from fw.hdl.xls_flow import sv_to_structure
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main
from xls_harness import (REPO, VerilatorError, _trace, have_verilator, rtl_step_testbench,
                         run_verilator, step_testbench)

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "lib_chan_pkg.sv")
RTL_LIB = [REPO / "src" / "rtl" / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv")]
CONTRACT = yaml.safe_load((REPO / "src" / "std" / "fw_channel.yaml").read_text())
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")

TOPS = {1: "chan_d1", 2: "chan_d2", 3: "chan_d3"}
CYCLES = 80


# --- the per-cycle rules ------------------------------------------------------
def chan_ref(depth, sched, cycles, stalls):
    """Each cycle, from the values held at its start: the consumer takes the
    oldest and offers it on out, unless out stalls (then nothing is taken);
    the producer puts the next arrival if fewer than *depth* were held. A
    value put is held from the next cycle."""
    pend, q, out = list(sched.get("a", [])), [], []
    for cyc in range(cycles):
        held = len(q)
        if q and cyc not in stalls:
            out.append((cyc, q.pop(0)))
        if pend and pend[0][0] <= cyc and held < depth:
            q.append(pend.pop(0)[1])
    return out


def gen(seed):
    """Random arrivals (bursts and gaps) and the cycles out stalls."""
    rng = random.Random(seed)
    c, xs, gap = 0, [], rng.choice([1, 2, 4])
    while True:
        c += rng.randint(0, gap)
        if c >= CYCLES - 30:
            break
        xs.append((c, rng.randrange(256)))
    p = (0.0, 0.2, 0.5)[seed % 3]
    return {"a": xs}, sorted(c for c in range(CYCLES) if rng.random() < p)


def contract_errors(sched, out):
    ev = [Event("in", "in", at, i, data=v) for i, (at, v) in enumerate(sched["a"][:len(out)])]
    ev += [Event("out", "out", c, i, data=v) for i, (c, v) in enumerate(out)]
    ev.sort(key=lambda e: (e.cyc, e.ev != "in"))
    return check(ev, Rule.from_dict(CONTRACT["order"]))


def test_ref_rates():
    """A value every cycle from cycle 0, out always ready: DEPTH 1 passes
    one every other cycle, DEPTH 2 one a cycle, each from cycle 1."""
    sched = {"a": [(c, c) for c in range(10)]}
    assert [c for c, _ in chan_ref(1, sched, 10, set())] == [1, 3, 5, 7, 9]
    assert [c for c, _ in chan_ref(2, sched, 10, set())] == list(range(1, 10))


def test_ref_full_refuses_a_put_while_taking():
    """DEPTH 1, full at the start of cycle 1 and taken in it: the put
    waiting from cycle 0 is accepted in cycle 2, not 1."""
    sched = {"a": [(0, 5), (0, 6)]}
    assert chan_ref(1, sched, 6, set()) == [(1, 5), (3, 6)]


# --- class model and RTL ------------------------------------------------------
def _model(d, top, sched, stalls):
    comp = sv_to_structure([PKG], top).component
    d.mkdir(parents=True, exist_ok=True)
    (d / "xh_step_tb.sv").write_text(step_testbench("lib_chan_pkg", top, comp, sched, CYCLES,
                                                    {"out": stalls}))
    return _trace(run_verilator([PKG, d / "xh_step_tb.sv"], "xh_step_tb", d / "model"))


def _rtl(d, top, sched, stalls, stages, cycles=CYCLES):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl([PKG], top, ["chan_pass"], stages=stages)
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in design.files.items():
        (d / name).write_text(text)
        paths.append(d / name)
    (d / "xh_rtl_step_tb.sv").write_text(rtl_step_testbench(design.signature, sched,
                                                            cycles + 4 * stages,
                                                            {"out": stalls}))
    return _trace(run_verilator(paths + RTL_LIB + [d / "xh_rtl_step_tb.sv"], "xh_rtl_step_tb",
                                d / "rtl", with_lib=False,
                                extra=["--assert", "+define+ASSERT_ON"]))


@needs_sim
@needs_xls
@pytest.mark.parametrize("depth", sorted(TOPS))
def test_model_and_rtl(tmp_path, depth):
    """Seed 3 has out always ready; seeds 1, 2, 4 and 5 stall it at random."""
    for seed in (1, 2, 3, 4, 5):
        sched, stalls = gen(seed)
        want = chan_ref(depth, sched, CYCLES, set(stalls))
        model = _model(tmp_path / f"s{seed}", TOPS[depth], sched, stalls).get("out", [])
        assert model == want, f"seed {seed}"
        rtl = _rtl(tmp_path / f"s{seed}", TOPS[depth], sched, stalls, 1).get("out", [])
        assert [x for x in rtl if x[0] < CYCLES] == model, f"seed {seed}"
        assert contract_errors(sched, model) == [], f"seed {seed}"


@needs_sim
@needs_xls
@pytest.mark.parametrize("depth", sorted(TOPS))
def test_two_stages_keep_the_contract(tmp_path, depth):
    """At 2 stages each block adds latency, so timing differs from the
    model; every value still leaves once, in order."""
    for seed in (1, 3):
        sched, stalls = gen(seed)
        rtl = _rtl(tmp_path / f"s{seed}", TOPS[depth], sched, stalls, 2,
                   cycles=4 * CYCLES).get("out", [])
        assert [v for _, v in rtl] == [v for _, v in sched["a"]], f"seed {seed}"
        assert contract_errors(sched, rtl) == [], f"seed {seed}"


@needs_sim
def test_full_rate_needs_depth_2(tmp_path):
    """The class model, a value every cycle, out always ready."""
    sched = {"a": [(c, c) for c in range(20)]}
    for depth, rate in ((1, 2), (2, 1), (3, 1)):
        got = _model(tmp_path / f"d{depth}", TOPS[depth], sched, []).get("out", [])
        assert [c for c, _ in got][:6] == [1 + rate * i for i in range(6)], depth


# --- DEPTH 0 ------------------------------------------------------------------
def test_step_on_a_wire_is_rejected(tmp_path):
    from fw.hdl.spl_flow import partition
    with pytest.raises(FwHdlError, match=r"lib_chan_pkg.sv:\d+:\d+: .*channel 'ch' has "
                                         r"DEPTH 0 .*src\.out is a step's port"):
        partition([PKG], "chan_d0", ["chan_pass"])


@needs_sim
def test_step_on_a_wire_stops_the_model(tmp_path):
    with pytest.raises(VerilatorError, match="a step cannot use a DEPTH 0 channel"):
        _model(tmp_path, "chan_d0", {"a": [(0, 1)]}, [])
