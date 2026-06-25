"""Unit tests for fw.hdl.fe.stmt_mapper (via the class mapper)."""
import pytest
import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter, FwHdlError
from fw.hdl.fe.astdump import collect_user_classes
from fw.hdl.fe.class_mapper import ClassMapper
from fw.hdl.fe.parser import Parser

from _fe_helpers import spl_component, run_body, parse_text


def test_forever_becomes_while_true():
    comp = spl_component(
        "package p; class c; bit x; task run(); forever x = 0; endtask endclass endpackage", "c")
    body = run_body(comp)
    assert len(body) == 1 and isinstance(body[0], ir.StmtWhile)
    assert isinstance(body[0].test, ir.ExprConstant) and body[0].test.value is True


def test_if_else_becomes_stmtif():
    comp = spl_component(
        "package p; class c; bit x; task run(); forever if (x) x = 0; else x = 1; endtask endclass endpackage", "c")
    inner = run_body(comp)[0].body[0]
    assert isinstance(inner, ir.StmtIf)
    assert len(inner.body) == 1 and len(inner.orelse) == 1


def test_compound_assign_expands():
    comp = spl_component(
        "package p; class c; bit [7:0] n; task run(); forever n += 2; endtask endclass endpackage", "c")
    assign = run_body(comp)[0].body[0]
    assert isinstance(assign, ir.StmtAssign)
    assert isinstance(assign.value, ir.ExprBin) and assign.value.op is ir.BinOp.Add


def test_increment_expands():
    comp = spl_component(
        "package p; class c; bit [7:0] n; task run(); forever n++; endtask endclass endpackage", "c")
    assign = run_body(comp)[0].body[0]
    assert isinstance(assign, ir.StmtAssign) and assign.value.op is ir.BinOp.Add


def test_task_call_is_awaited_beat():
    comp = spl_component(
        "package p; class c; bit x; task run(); forever beat(); endtask "
        "task beat(); endtask endclass endpackage", "c")
    stmt = run_body(comp)[0].body[0]
    assert isinstance(stmt, ir.StmtExpr)
    assert isinstance(stmt.expr, ir.ExprAwait)
    assert isinstance(stmt.expr.value, ir.ExprCall)


def test_function_call_not_awaited():
    comp = spl_component(
        "package p; class c; bit x; task run(); forever x = f(); endtask "
        "function bit f(); return 1'b0; endfunction endclass endpackage", "c")
    assign = run_body(comp)[0].body[0]
    # RHS is a plain call (a function), not an await
    assert isinstance(assign, ir.StmtAssign)
    assert isinstance(assign.value, ir.ExprCall)


def test_unsupported_statement_is_hard_error():
    # a `case` statement is outside the v1 envelope -> FwHdlError
    text = ("package p; class c; bit [1:0] s; task run(); forever "
            "case (s) 0: s = 1; default: s = 0; endcase endtask endclass endpackage")
    parser, reporter = parse_text(text)
    cls = next(c for c in collect_user_classes(parser.get_root()) if c.name == "c")
    with pytest.raises(FwHdlError):
        ClassMapper(FlowConfig(), reporter).map_component(cls)
