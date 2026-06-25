"""P1 integration: blinky FW-SV -> SPL IR shape (DESIGN §5)."""
import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.context import build_spl_context


def _blinky(blinky_files):
    reporter = ErrorReporter()
    cfg = FlowConfig(top="blinky")
    ctxt = build_spl_context(blinky_files, cfg, reporter)
    assert ctxt is not None, reporter.report()
    return ctxt.type_m["blinky"]


def test_blinky_component_present(blinky_files):
    comp = _blinky(blinky_files)
    assert isinstance(comp, ir.DataTypeComponent)
    assert comp.name == "blinky"


def test_blinky_has_port_and_state(blinky_files):
    comp = _blinky(blinky_files)
    names = {f.name for f in comp.fields}
    assert {"out", "v"} <= names
    out = next(f for f in comp.fields if f.name == "out")
    assert out.kind is ir.FieldKind.Port
    v = next(f for f in comp.fields if f.name == "v")
    assert v.is_reg and v.datatype.bits == 1
    # hoisted local keeps its initializer
    assert isinstance(v.initial_value, ir.ExprConstant) and v.initial_value.value == 0


def test_blinky_run_is_forever_loop(blinky_files):
    comp = _blinky(blinky_files)
    assert len(comp.proc_processes) == 1
    run = comp.proc_processes[0]
    assert run.name == "run" and run.is_async
    assert len(run.body) == 1 and isinstance(run.body[0], ir.StmtWhile)
    assert run.body[0].test.value is True


def test_blinky_loop_has_two_awaited_beats(blinky_files):
    comp = _blinky(blinky_files)
    loop_body = comp.proc_processes[0].body[0].body
    awaits = [s for s in loop_body
              if isinstance(s, ir.StmtExpr) and isinstance(s.expr, ir.ExprAwait)]
    # the put beat and the tick beat (DESIGN §1: two cycle-consuming beats)
    assert len(awaits) == 2
    methods = {a.expr.value.func.attr for a in awaits}
    assert methods == {"put", "tick"}


def test_blinky_toggle_is_invert(blinky_files):
    comp = _blinky(blinky_files)
    loop_body = comp.proc_processes[0].body[0].body
    toggle = next(s for s in loop_body if isinstance(s, ir.StmtAssign))
    assert isinstance(toggle.value, ir.ExprUnary)
    assert toggle.value.op is ir.UnaryOp.Invert


def test_tick_count_folded(blinky_files):
    comp = _blinky(blinky_files)
    loop_body = comp.proc_processes[0].body[0].body
    tick = next(s for s in loop_body
                if isinstance(s, ir.StmtExpr) and isinstance(s.expr, ir.ExprAwait)
                and s.expr.value.func.attr == "tick")
    arg = tick.expr.value.args[0]
    assert isinstance(arg, ir.ExprConstant) and arg.value == 100  # BLINK_TICKS
