"""M8d: end-to-end sim of a wait-beat FSM (SPL IR -> RTL -> Verilog -> sim).

The hand-built `waiter` (forever { wait_until(trig); done=1; wait_until(!trig);
done=0 }) lowers to a clocked FSM and is emitted to Verilog; the sim confirms the
wait-states actually hold until the condition and then advance.
"""
import subprocess
from pathlib import Path

import pytest
import zuspec.ir.core as ir

from fw.hdl import ir_build as b
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.lower.spl2rtl import lower_context
from fw.hdl.emit.be_sv import emit_sv

REPO = Path(__file__).resolve().parents[3]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"


def _waiter_spl():
    i1 = ir.DataTypeInt(bits=1, signed=False)
    clock = ir.FieldInOut(name="clock", datatype=i1, is_out=False)
    clock.pragmas.update({"fw_role": "clock"})
    reset = ir.FieldInOut(name="reset", datatype=i1, is_out=False)
    reset.pragmas.update({"fw_role": "reset"})
    trig = ir.FieldInOut(name="trig", datatype=i1, is_out=False)
    done = ir.FieldInOut(name="done", datatype=i1, is_out=True)
    sref = lambda i: ir.ExprRefField(base=ir.TypeExprRefSelf(), index=i)
    wait = lambda c: ir.StmtExpr(expr=ir.ExprAwait(value=ir.ExprCall(
        func=ir.ExprAttribute(value=ir.TypeExprRefSelf(), attr="wait_until"),
        args=[c], keywords=[])))
    loop = ir.StmtWhile(test=ir.ExprConstant(value=True), body=[
        wait(sref(2)),
        ir.StmtAssign(targets=[sref(3)], value=ir.ExprConstant(value=1)),
        wait(ir.ExprUnary(op=ir.UnaryOp.Not, operand=sref(2))),
        ir.StmtAssign(targets=[sref(3)], value=ir.ExprConstant(value=0)),
    ], orelse=[])
    run = ir.Function(name="run", body=[loop], is_async=True)
    return b.component("waiter", [clock, reset, trig, done], proc_processes=[run])


_TB = """
module tb;
  logic clock = 0, reset = 1; always #5 clock = ~clock;
  logic trig = 0, done;
  waiter dut (.clock, .reset, .trig, .done);
  int errors = 0;
  task automatic chk(bit c, string m); if (!c) begin $display("FAIL: %s", m); errors++; end endtask
  initial begin
    repeat (3) @(posedge clock); reset = 0; @(posedge clock);
    chk(done === 1'b0, "idle: done low");
    trig <= 1; repeat (3) @(posedge clock); chk(done === 1'b1, "trig high -> done high");
    trig <= 0; repeat (3) @(posedge clock); chk(done === 1'b0, "trig low -> done low");
    // a second pulse proves the FSM loops back through both wait-states
    trig <= 1; repeat (3) @(posedge clock); chk(done === 1'b1, "second pulse");
    trig <= 0; repeat (3) @(posedge clock); chk(done === 1'b0, "second release");
    if (errors == 0) $display("[wait_beat_sim] PASS"); else $display("[wait_beat_sim] FAIL");
    $finish;
  end
  initial begin #10000; $display("[wait_beat_sim] TIMEOUT"); $finish; end
endmodule
"""


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_wait_beat_fsm_behaves(tmp_path):
    rep = ErrorReporter()
    rtl = lower_context(b.context([_waiter_spl()]), FlowConfig(), rep)
    assert rtl is not None, rep.report()
    (tmp_path / "waiter.sv").write_text(emit_sv(rtl))
    (tmp_path / "tb.sv").write_text(_TB)

    build = subprocess.run(
        [str(VERILATOR), "--binary", "--timing", "-j", "0", "-Wno-fatal",
         "--top-module", "tb", "-o", "simv", "waiter.sv", "tb.sv"],
        cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "obj_dir" / "simv")],
                         cwd=tmp_path, capture_output=True, text=True)
    assert "[wait_beat_sim] PASS" in run.stdout, run.stdout + run.stderr
