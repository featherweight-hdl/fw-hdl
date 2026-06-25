"""M8d: a wait-for-condition beat lowers to an FSM wait-state.

`forever { wait_until(trig); done=1; wait_until(!trig); done=0 }` — the consumer
process model the register watch-set lowers to (wait_change is a wait on the
set_changed condition). Built as SPL IR by hand and lowered to RTL."""
import zuspec.ir.core as ir

from fw.hdl import ir_build as b
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.lower.spl2rtl import lower_component


def _sref(i):
    return ir.ExprRefField(base=ir.TypeExprRefSelf(), index=i)


def _wait(cond):
    return ir.StmtExpr(expr=ir.ExprAwait(value=ir.ExprCall(
        func=ir.ExprAttribute(value=ir.TypeExprRefSelf(), attr="wait_until"),
        args=[cond], keywords=[])))


def _waiter_spl():
    i1 = ir.DataTypeInt(bits=1, signed=False)
    clock = ir.FieldInOut(name="clock", datatype=i1, is_out=False)
    clock.pragmas.update({"fw_role": "clock"})
    reset = ir.FieldInOut(name="reset", datatype=i1, is_out=False)
    reset.pragmas.update({"fw_role": "reset"})
    trig = ir.FieldInOut(name="trig", datatype=i1, is_out=False)        # input
    done = ir.FieldInOut(name="done", datatype=i1, is_out=True)         # output
    # indices: 0 clock, 1 reset, 2 trig, 3 done
    loop = ir.StmtWhile(test=ir.ExprConstant(value=True), body=[
        _wait(_sref(2)),                                                # wait trig high
        ir.StmtAssign(targets=[_sref(3)], value=ir.ExprConstant(value=1)),
        _wait(ir.ExprUnary(op=ir.UnaryOp.Not, operand=_sref(2))),       # wait trig low
        ir.StmtAssign(targets=[_sref(3)], value=ir.ExprConstant(value=0)),
    ], orelse=[])
    run = ir.Function(name="run", body=[loop], is_async=True)
    return b.component("waiter", [clock, reset, trig, done], proc_processes=[run])


def _rtl():
    rep = ErrorReporter()
    rtl = lower_component(_waiter_spl(), FlowConfig(), rep)
    assert rtl is not None, rep.report()
    return rtl


def test_wait_lowers_to_fsm_with_state():
    comp = _rtl()
    by = {f.name: f for f in comp.fields}
    assert {"clock", "reset", "trig", "done"} <= set(by)
    assert "state" in by and by["state"].datatype.bits == 1   # 2 wait beats -> 2 states
    assert isinstance(by["trig"], ir.FieldInOut) and not by["trig"].is_out
    assert isinstance(by["done"], ir.FieldInOut) and by["done"].is_out


def test_single_clocked_process_and_contract():
    comp = _rtl()
    assert len(comp.sync_processes) == 1
    assert b.validate_rtl_component(comp) == []


def test_no_counter_for_pure_wait():
    comp = _rtl()
    assert "count" not in {f.name for f in comp.fields}   # waits need no down-counter
