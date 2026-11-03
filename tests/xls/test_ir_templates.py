"""RQ-T0: the hand-written XLS IR templates (tests/xls/templates/) parse, generate
RTL, and keep their contracts on Verilator.

  credit_tx   every value arrives, in order; the receiver never holds more
              than CREDITS values; with a slow receiver the buffer fills
  rr_arb      every value arrives, in per-input order, tagged with its input;
              with all inputs always valid the grants rotate 0,1,2,3,...
  arb_credit  the two under one top proc (multi-proc codegen, an in-package
              depth-2 chan): the arbiter's contract through the credit link
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from xls_harness import run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "templates"))
import xls_templates as T  # noqa: E402

needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


def build(workdir: Path, name: str, text: str, stages: int = 1, multi: bool = False,
          extra=()) -> Path:
    """opt_main + codegen_main on *text*; returns the generated SV."""
    workdir.mkdir(parents=True, exist_ok=True)
    src = workdir / f"{name}.ir"
    src.write_text(text)
    opt = workdir / f"{name}.opt.ir"
    r = subprocess.run([opt_main(), str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    opt.write_text(r.stdout)
    sv = workdir / f"{name}.sv"
    args = [codegen_main(), "--generator=pipeline", "--delay_model=unit",
            f"--pipeline_stages={stages}", "--reset=rst", "--use_system_verilog",
            f"--output_verilog_path={sv}"]
    args += ["--multi_proc", "--materialize_internal_fifos"] if multi else \
        [f"--module_name={name}"]
    r = subprocess.run(args + list(extra) + [str(opt)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return sv


# ---------------------------------------------------------------------------
# Testbench pieces. Each cycle: drive, settle (#1), sample both sides of every
# handshake, clock, then retire what fired.
# ---------------------------------------------------------------------------
def _receiver_decl():
    return """\
  logic [OW-1:0] q[$], od;
  int got = 0, owed = 0, maxheld = 0;
  logic cred_in = 1'b1, cred_in_vld = 0, cred_in_rdy;
  logic [OW-1:0] data_out; logic data_out_vld, data_out_rdy = 1;"""


def _receiver_pre():
    # The receiver drains its buffer at random and owes one credit per drain.
    return """\
    if (q.size() > 0 && ($urandom % DRAIN) == 0) begin
      $display("O %0d", q.pop_front()); got++; owed++;
    end
    cred_in_vld = owed > 0;"""


def _receiver_post():
    return """\
    if (f_out) begin
      q.push_back(od);
      if (q.size() > maxheld) maxheld = q.size();
    end
    if (f_cred) owed--;"""


def credit_tb(n: int, drain: int, seed: int) -> str:
    return f"""\
module xh_tb;
  localparam int OW = 8, DRAIN = {drain};
  logic clk = 0, rst = 1;
  logic [7:0] data_in; logic data_in_vld = 0, data_in_rdy;
{_receiver_decl()}
  int sent = 0, cyc = 0;
  credit_tx dut(.*);
  initial begin
    bit f_in, f_out, f_cred;
    void'($urandom({seed}));
    repeat (3) begin #5 clk = 1; #5 clk = 0; end
    rst = 0;
    while (got < {n} && cyc < 50000) begin
      if (!data_in_vld && sent < {n} && ($urandom % 4) != 0) begin
        data_in_vld = 1; data_in = 8'(sent * 7 + 3);
      end
{_receiver_pre()}
      #1;
      f_in = data_in_vld && data_in_rdy;
      f_out = data_out_vld && data_out_rdy; od = data_out;
      f_cred = cred_in_vld && cred_in_rdy;
      #4 clk = 1; #5 clk = 0;
{_receiver_post()}
      if (f_in) begin sent++; data_in_vld = 0; end
      cyc++;
    end
    $display("M %0d", maxheld);
    $display("X done");
    $finish;
  end
endmodule
"""


def arb_tb(module: str, n: int, per: int, full: bool, seed: int, credited: bool) -> str:
    ib = max(1, (n - 1).bit_length())
    L = ["module xh_tb;", f"  localparam int OW = {8 + ib}, DRAIN = 2;",
         "  logic clk = 0, rst = 1;", "  int cyc = 0;", f"  int s[{n}];"]
    for k in range(n):
        L.append(f"  logic [7:0] in{k}; logic in{k}_vld = 0, in{k}_rdy;")
    if credited:
        L.append(_receiver_decl())
    else:
        L += ["  logic [OW-1:0] arb_out; logic arb_out_vld, arb_out_rdy = 0;", "  int got = 0;"]
    L += [f"  {module} dut(.*);", "  initial begin", f"    bit f_in[{n}];",
          "    bit f_out, f_cred;", f"    void'($urandom({seed}));",
          "    repeat (3) begin #5 clk = 1; #5 clk = 0; end", "    rst = 0;",
          f"    while (got < {n * per} && cyc < 50000) begin"]
    for k in range(n):
        go = "1" if full else "($urandom % 2) == 0"
        L.append(f"      if (!in{k}_vld && s[{k}] < {per} && {go}) begin "
                 f"in{k}_vld = 1; in{k} = {{2'd{k}, 6'(s[{k}])}}; end")
    if credited:
        L.append(_receiver_pre())
    else:
        L.append(f"      arb_out_rdy = {'1' if full else '($urandom % 3) != 0'};")
    L.append("      #1;")
    for k in range(n):
        L.append(f"      f_in[{k}] = in{k}_vld && in{k}_rdy;")
    if credited:
        L += ["      f_out = data_out_vld && data_out_rdy; od = data_out;",
              "      f_cred = cred_in_vld && cred_in_rdy;"]
    else:
        L += ["      f_out = arb_out_vld && arb_out_rdy;",
              "      if (f_out) begin $display(\"O %0d\", arb_out); got++; end"]
    L.append("      #4 clk = 1; #5 clk = 0;")
    if credited:
        L.append(_receiver_post())
    for k in range(n):
        L.append(f"      if (f_in[{k}]) begin s[{k}]++; in{k}_vld = 0; end")
    L += ["      cyc++;", "    end"]
    if credited:
        L.append("    $display(\"M %0d\", maxheld);")
    L += ["    $display(\"X done\");", "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def _outs(lines):
    return [int(m[1]) for l in lines if (m := re.match(r"O (\d+)$", l))]


def _maxheld(lines):
    (m,) = [int(m[1]) for l in lines if (m := re.match(r"M (\d+)$", l))]
    return m


def _check_arb(outs, n, per):
    """Each output is {idx, {idx, seq}}: per-input order, nothing lost."""
    ib = max(1, (n - 1).bit_length())
    seen = {k: [] for k in range(n)}
    for v in outs:
        idx, data = v >> 8, v & 0xff
        assert data >> 6 == idx, f"value {data:#x} tagged with input {idx}"
        seen[idx].append(data & 0x3f)
    assert seen == {k: list(range(per)) for k in range(n)}
    return [v >> 8 for v in outs]


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("stages,drain,seed", [(1, 3, 1), (2, 2, 2), (1, 1, 3), (2, 8, 4)])
def test_credit_tx(workdir, stages, drain, seed):
    sv = build(workdir, "credit_tx", T.package("credit_tx", T.credit_tx(credits=4)), stages)
    tb = workdir / "xh_tb.sv"
    tb.write_text(credit_tb(300, drain, seed))
    out = run_verilator([sv, tb], "xh_tb", workdir / "sim", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    assert _outs(out) == [(i * 7 + 3) & 0xff for i in range(300)]
    held = _maxheld(out)
    assert held <= 4, "receiver overrun: more values than credits"
    if drain >= 8:
        assert held == 4, "a slow receiver should be sent every credit's worth"


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("stages,seed", [(1, 1), (2, 2)])
def test_rr_arb_random(workdir, stages, seed):
    sv = build(workdir, "rr_arb", T.package("rr_arb", T.rr_arb(4)), stages)
    tb = workdir / "xh_tb.sv"
    tb.write_text(arb_tb("rr_arb", 4, 50, full=False, seed=seed, credited=False))
    out = run_verilator([sv, tb], "xh_tb", workdir / "sim", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    _check_arb(_outs(out), 4, 50)


@needs_xls
@pytest.mark.verilator
def test_rr_arb_rotates_when_all_valid(workdir):
    sv = build(workdir, "rr_arb", T.package("rr_arb", T.rr_arb(4)), 1)
    tb = workdir / "xh_tb.sv"
    tb.write_text(arb_tb("rr_arb", 4, 30, full=True, seed=1, credited=False))
    out = run_verilator([sv, tb], "xh_tb", workdir / "sim", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    order = _check_arb(_outs(out), 4, 30)
    assert order == [i % 4 for i in range(120)]


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("seed", [1, 2])
def test_arb_credit_multi_proc(workdir, seed):
    sv = build(workdir, "arb_credit", T.package("arb_credit", T.arb_credit(4, credits=4)),
               1, multi=True)
    tb = workdir / "xh_tb.sv"
    tb.write_text(arb_tb("arb_credit", 4, 40, full=False, seed=seed, credited=True))
    out = run_verilator([sv, tb], "xh_tb", workdir / "sim", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    _check_arb(_outs(out), 4, 40)
    assert _maxheld(out) <= 4
