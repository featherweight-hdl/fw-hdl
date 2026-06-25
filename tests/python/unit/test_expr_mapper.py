"""Unit tests for fw.hdl.fe.expr_mapper (via the class mapper)."""
import zuspec.ir.core as ir

from _fe_helpers import spl_component, run_body


def _find(stmts, pred):
    for s in stmts:
        if pred(s):
            return s
        for attr in ("body", "orelse"):
            got = _find(getattr(s, attr, []) or [], pred)
            if got is not None:
                return got
    return None


_REL = """
package p;
  class c;
    bit [7:0] count;
    task run();
      forever if (count == 8'd9) count = 0; else count = count + 1;
    endtask
  endclass
endpackage
"""


def test_relational_maps_to_exprcompare():
    comp = spl_component(_REL, "c")
    if_stmt = _find(run_body(comp), lambda s: isinstance(s, ir.StmtIf))
    assert if_stmt is not None
    # the spike trap: '==' must be ExprCompare, never ExprBin(BinOp.Eq)
    assert isinstance(if_stmt.test, ir.ExprCompare)
    assert if_stmt.test.ops[0] is ir.CmpOp.Eq
    assert not isinstance(if_stmt.test, ir.ExprBin)


def test_arithmetic_maps_to_exprbin():
    comp = spl_component(_REL, "c")
    add = _find(run_body(comp),
                lambda s: isinstance(s, ir.StmtAssign)
                and isinstance(s.value, ir.ExprBin))
    assert add is not None and add.value.op is ir.BinOp.Add


_LITERALS = """
package p;
  class c;
    bit [31:0] r;
    task run();
      forever begin
        r = 32'hFF;
        r = 8'b1010;
        r = 100;
      end
    endtask
  endclass
endpackage
"""


def test_sized_literals_fold_to_constants():
    comp = spl_component(_LITERALS, "c")
    consts = [s.value.value for s in run_body(comp)[0].body
              if isinstance(s, ir.StmtAssign) and isinstance(s.value, ir.ExprConstant)]
    assert consts == [0xFF, 0b1010, 100]


_UNARY = """
package p;
  class c;
    logic v;
    task run(); forever v = ~v; endtask
  endclass
endpackage
"""


def test_unary_invert():
    comp = spl_component(_UNARY, "c")
    assign = run_body(comp)[0].body[0]
    assert isinstance(assign.value, ir.ExprUnary)
    assert assign.value.op is ir.UnaryOp.Invert


_BITSEL = """
package p;
  class c;
    bit [21:0] cnt;
    task run(); forever cnt[0] = cnt[21]; endtask
  endclass
endpackage
"""


def test_bit_select_maps_to_subscript():
    comp = spl_component(_BITSEL, "c")
    assign = run_body(comp)[0].body[0]
    # RHS cnt[21] -> ExprSubscript(value=ref, slice=ExprConstant(21))
    assert isinstance(assign.value, ir.ExprSubscript)
    assert isinstance(assign.value.slice, ir.ExprConstant)
    assert assign.value.slice.value == 21
    # LHS cnt[0] is also a subscript
    assert isinstance(assign.targets[0], ir.ExprSubscript)
