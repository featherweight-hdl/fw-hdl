"""fw_arbiter: the registry's lowering (the rr_arb template, round robin or
fixed priority) against the class model under the class's contract, and the
RTL's per-cycle rules directly (fw_arbiter.svh's header).

The class model is a process, so model and RTL are compared per input (the
contract), not cycle for cycle. The per-cycle rules are checked on the RTL.
"""
import random
from pathlib import Path

import pytest
import yaml

from fw.hdl.errors import FwHdlError
from fw.hdl.lib import xls_ir
from fw.hdl.verif.canon import Event, Rule, check, compare
from fw.hdl.xls_flow import sv_to_structure
from zuspec.be.xls.testing.xlstools import CodegenOptions, codegen_main, opt_main, run_codegen
from xls_harness import REPO, proc_testbench, rtl_testbench, run_verilator

HERE = Path(__file__).resolve().parent
FILES = [str(HERE / "lib_arb_pkg.sv")]
RTL_LIB = [REPO / "src" / "rtl" / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv")]
CONTRACT = yaml.safe_load((REPO / "src" / "std" / "arb" / "fw_arbiter.yaml").read_text())
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")

# top: (width, input ports)
TOPS = {"arb3_rr": (8, "abc"), "arb3_prio": (8, "abc"), "arb5_rr": (6, "abcde")}


def _rtl(tmp_path, top, inputs, seed, stages):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, [], stages=stages)
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


def _trace(w, ins, outs):
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
@pytest.mark.verilator
@pytest.mark.parametrize("top", sorted(TOPS))
@pytest.mark.parametrize("stages", [1, 2])
def test_model_and_rtl_keep_the_contract(tmp_path, top, stages):
    w, names = TOPS[top]
    rng = random.Random(stages * 31 + len(top))
    ins = [[rng.randrange(1 << w) for _ in range(rng.randint(20, 40))] for _ in names]
    inputs = dict(zip(names, ins))
    rule = Rule.from_dict(CONTRACT["order"])
    rtl = _rtl(tmp_path, top, inputs, seed=stages, stages=stages)
    model = _model(tmp_path, top, inputs)
    n = sum(map(len, ins))
    assert len(rtl) == len(model) == n                         # lossless
    assert check(_trace(w, ins, rtl), rule) == []
    assert compare(_trace(w, ins, model), _trace(w, ins, rtl), rule,
                   names=("model", "rtl")) == []


# --- the RTL's per-cycle rules ------------------------------------------------
def _cycle_tb(n, queues, rdy):
    """A cycle-scripted testbench for rr_arb(n). *queues* maps input k to
    [(cycle, value)]: each value is offered from its cycle (and after the
    one before it is taken) until taken. *rdy* is out's ready per cycle.
    Prints ``G <cycle> <out>`` for each cycle out is valid, sampled before
    the rising edge."""
    ib = max(1, (n - 1).bit_length())
    L = ["module xh_tb;", "  logic clk = 0, rst = 1;",
         f"  logic [{8 + ib - 1}:0] arb_out; logic arb_out_vld, arb_out_rdy = 0;"]
    for k in range(n):
        q = queues.get(k, [])
        L += [f"  logic [7:0] in{k} = 0; logic in{k}_vld = 0, in{k}_rdy;",
              f"  int at{k}[{max(len(q), 1)}]; logic [7:0] q{k}[{max(len(q), 1)}];",
              f"  int n{k} = {len(q)}, i{k} = 0;"]
        L += ["  initial begin"] + [f"    at{k}[{i}] = {c}; q{k}[{i}] = 8'h{v:02x};"
                                    for i, (c, v) in enumerate(q)] + ["  end"]
    L += [f"  bit t{k};" for k in range(n)]
    L += ["  rr_arb dut(.*);", "  initial begin",
          "    repeat (3) begin #5 clk = 1; #5 clk = 0; end", "    rst = 0;"]
    for c, r in enumerate(rdy):
        for k in range(n):
            L.append(f"    if (!in{k}_vld && i{k} < n{k} && at{k}[i{k}] <= {c}) begin "
                     f"in{k}_vld = 1; in{k} = q{k}[i{k}]; end")
        L += [f"    arb_out_rdy = {int(r)};", "    #1;",
              f'    if (arb_out_vld) $display("G {c} %0h", arb_out);']
        # Handshakes are sampled before the edge and applied a step after it,
        # so the flops never see the testbench's next values.
        L += [f"    t{k} = in{k}_vld && in{k}_rdy;" for k in range(n)]
        L += ["    #4 clk = 1;", "    #1;"]
        L += [f"    if (t{k}) begin in{k}_vld = 0; i{k}++; end" for k in range(n)]
        L += ["    #4 clk = 0;"]
    L += ['    $display("X done");', "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def _run_cycles(tmp_path, n, prio, queues, rdy):
    """{cycle: out} for each cycle out is valid (no I/O flops)."""
    res = run_codegen(xls_ir.package("rr_arb", xls_ir.rr_arb(n, 8, prio=prio)),
                      CodegenOptions(), stages=1,
                      extra=["--flop_inputs=false", "--flop_outputs=false"])
    (tmp_path / "rr_arb.sv").write_text(res.verilog)
    (tmp_path / "tb.sv").write_text(_cycle_tb(n, queues, rdy))
    out = run_verilator([tmp_path / "rr_arb.sv", tmp_path / "tb.sv"], "xh_tb", tmp_path / "sim",
                        with_lib=False)
    return {int(p[1]): int(p[2], 16) for p in (l.split() for l in out) if p and p[0] == "G"}


def _g(k, v):
    return (k << 8) | v


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("prio,want", [
    (False, [_g(0, 0x10), _g(1, 0x20), _g(2, 0x30), _g(0, 0x11), _g(1, 0x21)]),   # rotate
    (True, [_g(0, 0x10), _g(0, 0x11), _g(0, 0x12), _g(0, 0x13), _g(1, 0x20)]),    # lowest wins
])
def test_tie_rule(tmp_path, prio, want):
    """Every input waiting from cycle 0, out always ready: one grant per
    cycle, by POLICY, from cycle 1 (a value is held before it can win)."""
    queues = {k: [(0, b + i) for i in range(4)] for k, b in ((0, 0x10), (1, 0x20), (2, 0x30))}
    grants = _run_cycles(tmp_path, 3, prio, queues, [True] * 8)
    assert grants.get(0) is None
    assert [grants.get(c) for c in range(1, 6)] == want


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("prio", [False, True])
def test_grant_held_under_backpressure(tmp_path, prio):
    """Input 1's value is held in cycle 0 and offered from cycle 1 on a
    stalled out; input 0's arrives in cycle 2 (it would win under both
    policies if the grant were re-made). Out stays input 1's value, unchanged,
    until accepted in cycle 4; input 0's goes next."""
    queues = {1: [(0, 0x21)], 0: [(2, 0x05)]}
    grants = _run_cycles(tmp_path, 3, prio, queues, [False] * 4 + [True] * 3)
    assert [grants.get(c) for c in range(6)] == [None] + [_g(1, 0x21)] * 4 + [_g(0, 0x05)]


def test_out_of_range_rejected_at_the_child():
    from fw.hdl.spl_flow import partition
    with pytest.raises(FwHdlError) as e:
        partition(FILES, "arb_one", [])
    msg = str(e.value)
    assert "lib_arb_pkg.sv:" in msg and "N=1" in msg, msg
