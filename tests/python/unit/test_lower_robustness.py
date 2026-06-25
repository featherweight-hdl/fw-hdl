"""Lowering robustness — error paths (SplLowerError) and a multi-state FSM
(>2 beats, multiple ticks sharing one counter), which the blinky/@zdc tests
don't exercise.  Builds SPL components directly against the contract."""
import pytest
import zuspec.ir.core as ir
import zuspec.synth.spl as spl
import zuspec.synth.spl.builders as b
from zuspec.synth.spl import SplLowerError, lower_component

S = b.sref


def _while(body):
    return ir.StmtWhile(test=ir.ExprConstant(value=True), body=body, orelse=[])


def _tick(n):
    return ir.StmtExpr(expr=ir.ExprAwait(value=ir.ExprCall(
        func=ir.ExprAttribute(value=ir.TypeExprRefSelf(), attr="cycles"),
        args=[b.const(n)], keywords=[])))


# -- error paths -------------------------------------------------------------
def test_no_run_process_raises():
    comp = ir.DataTypeComponent(name="c", super=None, fields=[b.in_port("clock")])
    with pytest.raises(SplLowerError, match="run process"):
        lower_component(comp)


def test_no_clock_raises():
    run = ir.Function(name="run", body=[_while([])])
    comp = ir.DataTypeComponent(name="c", super=None, fields=[], proc_processes=[run])
    with pytest.raises(SplLowerError, match="clock"):
        lower_component(comp)


def test_no_beats_raises():
    clk = b.in_port("clock")
    run = ir.Function(name="run", body=[_while([])], metadata={"clock": S(0)})
    comp = ir.DataTypeComponent(name="c", super=None, fields=[clk], sync_processes=[run])
    with pytest.raises(SplLowerError, match="no awaited beats"):
        lower_component(comp)


def test_unsupported_beat_raises():
    clk = b.in_port("clock")
    port = ir.Field(name="p", datatype=b.int_t(1))   # no fw_protocol pragma
    frob = ir.StmtExpr(expr=ir.ExprAwait(value=ir.ExprCall(
        func=ir.ExprAttribute(value=S(1), attr="frob"), args=[], keywords=[])))
    run = ir.Function(name="run", body=[_while([frob])], metadata={"clock": S(0)})
    comp = ir.DataTypeComponent(name="c", super=None, fields=[clk, port],
                                sync_processes=[run])
    with pytest.raises(SplLowerError, match="unsupported beat"):
        lower_component(comp)


# -- multi-state FSM: two ticks (5, 3) sharing one down-counter --------------
def _two_phase():
    clk, rst = b.in_port("clock"), b.in_port("reset")
    a = ir.FieldInOut(name="a", datatype=b.int_t(1), is_out=True); a.reset_value = 0
    bb = ir.FieldInOut(name="b", datatype=b.int_t(1), is_out=True); bb.reset_value = 0
    body = [b.assign(S(2), b.const(1)), _tick(5),
            b.assign(S(3), b.const(1)), _tick(3),
            b.assign(S(2), b.const(0)), b.assign(S(3), b.const(0))]
    run = ir.Function(name="run", body=[_while(body)],
                      metadata={"clock": S(0), "reset": S(1)})
    comp = ir.DataTypeComponent(name="twophase", super=None,
                                fields=[clk, rst, a, bb], sync_processes=[run])
    return lower_component(comp)


def test_two_tick_fsm_structure():
    comp = _two_phase()
    by = {f.name: f for f in comp.fields}
    assert {"clock", "reset", "a", "b", "state", "count"} <= set(by)
    assert by["state"].datatype.bits == 1   # 2 beats -> 1-bit state
    # counter sized for max tick (5) -> 3 value bits + 1 borrow = 4? (5-1=4 -> 3 bits)
    assert by["count"].datatype.bits == _expected_count_bits(5)
    assert spl.builders.validate_rtl_component(comp) == []


def _expected_count_bits(n):
    return (max(1, (n - 1).bit_length())) + 1


def test_two_tick_emits_both_states():
    from pathlib import Path
    import tempfile
    from zuspec.be.sv import SVGenerator
    sv = SVGenerator(Path(tempfile.mkdtemp())).generate(
        b.context([_two_phase()]))[0].read_text()
    assert "state == 0" in sv           # FSM chain present
    assert "count <= 4" in sv and "count <= 2" in sv   # per-tick reloads (5-1, 3-1)
    assert "always @(posedge clock)" in sv
