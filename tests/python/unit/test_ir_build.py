"""Unit tests for fw.hdl.ir_build — the IR contract chokepoint (PLAN.md §0).

These tests pin the two traps the §9.1 spike caught:
  - internal registers are plain ``Field``, never ``FieldInOut``
  - equality/relational ops are ``ExprCompare``, never ``ExprBin(BinOp.Eq)``
"""
import pytest
import zuspec.ir.core as ir

from fw.hdl import ir_build as b


# -- contracted node types ---------------------------------------------------
def test_in_port_is_input_fieldinout():
    f = b.in_port("clock")
    assert isinstance(f, ir.FieldInOut)
    assert f.is_out is False
    assert f.datatype.bits == 1


def test_out_reg_is_output_fieldinout():
    f = b.out_reg("led")
    assert isinstance(f, ir.FieldInOut)
    assert f.is_out is True


def test_reg_is_plain_field_not_port():
    f = b.reg("count", 32)
    assert isinstance(f, ir.Field)
    assert not isinstance(f, ir.FieldInOut)   # <-- the trap
    assert f.is_reg is True
    assert f.datatype.bits == 32


def test_cmp_eq_is_exprcompare_not_exprbin():
    e = b.cmp_eq(b.sref(0), b.const(0))
    assert isinstance(e, ir.ExprCompare)       # <-- the trap
    assert not isinstance(e, ir.ExprBin)
    assert e.ops[0] is ir.CmpOp.Eq


def test_add_is_exprbin():
    e = b.add(b.sref(0), b.const(1))
    assert isinstance(e, ir.ExprBin)
    assert e.op is ir.BinOp.Add


def test_sync_proc_carries_clock_reset_metadata():
    proc = b.sync_proc("_p", [], clock_index=0, reset_index=1)
    assert isinstance(proc.metadata["clock"], ir.ExprRefField)
    assert proc.metadata["clock"].index == 0
    assert proc.metadata["reset"].index == 1


def test_sync_proc_reset_optional():
    proc = b.sync_proc("_p", [], clock_index=0)
    assert "reset" not in proc.metadata


# -- negative paths ----------------------------------------------------------
def test_binop_rejects_comparison_ops():
    with pytest.raises(ValueError):
        b.binop(ir.BinOp.Eq, b.const(1), b.const(2))


def test_validate_flags_exprbin_comparison():
    # Hand-build an illegal component (bypassing the helpers) to prove the
    # validator catches an ExprBin comparison that be-sv would render as '?'.
    bad = ir.ExprBin(lhs=b.sref(0), op=ir.BinOp.Eq, rhs=b.const(0))
    comp = b.component(
        "bad",
        [b.in_port("clock"), b.reg("x")],
        sync_processes=[b.sync_proc("_p", [b.assign(b.sref(1), bad)], clock_index=0)],
    )
    problems = b.validate_rtl_component(comp)
    assert any("ExprCompare" in p for p in problems)


def test_validate_clean_component_has_no_problems():
    comp = b.component(
        "ok",
        [b.in_port("clock"), b.in_port("reset"), b.reg("x")],
        sync_processes=[b.sync_proc(
            "_p",
            [b.if_(b.cmp_eq(b.sref(2), b.const(0)),
                   [b.assign(b.sref(2), b.const(1))],
                   [b.assign(b.sref(2), b.add(b.sref(2), b.const(1)))])],
            clock_index=0, reset_index=1)],
    )
    assert b.validate_rtl_component(comp) == []


def test_field_index_lookup():
    comp = b.component("c", [b.in_port("clock"), b.out_reg("led")])
    assert b.field_index(comp, "led") == 1
    with pytest.raises(KeyError):
        b.field_index(comp, "nope")


# -- end-to-end: helpers -> be-sv emit (pure Python, no simulator) -----------
def test_blinky_fsm_emits_clean_rtl(tmp_path):
    from pathlib import Path
    from zuspec.be.sv import SVGenerator

    N = 100
    fields = [b.in_port("clock"), b.in_port("reset"),
              b.out_reg("led"), b.reg("state"), b.reg("count", 32)]
    CLK, RST, LED, ST, CNT = 0, 1, 2, 3, 4
    wait = b.if_(
        b.cmp_eq(b.sref(CNT), b.const(N - 1)),
        [b.assign(b.sref(LED), b.inv(b.sref(LED))),
         b.assign(b.sref(ST), b.const(0)),
         b.assign(b.sref(CNT), b.const(0))],
        [b.assign(b.sref(CNT), b.add(b.sref(CNT), b.const(1)))])
    els = [b.if_(b.cmp_eq(b.sref(ST), b.const(0)),
                 [b.assign(b.sref(ST), b.const(1)), b.assign(b.sref(CNT), b.const(0))],
                 [wait])]
    body = [b.if_(b.lognot(b.sref(RST)),
                  [b.assign(b.sref(ST), b.const(0)),
                   b.assign(b.sref(CNT), b.const(0)),
                   b.assign(b.sref(LED), b.const(0))],
                  els)]
    comp = b.component("blinky", fields,
                       sync_processes=[b.sync_proc("_blink", body,
                                                   clock_index=CLK, reset_index=RST)])
    assert b.validate_rtl_component(comp) == []

    sv = SVGenerator(Path(tmp_path)).generate(b.context([comp]))[0].read_text()
    assert "input logic clock" in sv
    assert "output logic led" in sv
    assert "logic [31:0] count" in sv          # internal reg, NOT a port
    assert "input logic count" not in sv        # the trap: count must not be a port
    assert "always @(posedge clock)" in sv
    assert "count == 99" in sv                  # ExprCompare rendered, not '?'
    assert "led <= ~led" in sv
