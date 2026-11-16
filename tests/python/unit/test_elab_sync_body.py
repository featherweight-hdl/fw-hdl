"""Process bodies beyond straight-line code (fe/elab/sync.py, _Body):
locals and their wires, unrolled loops, early returns, inlined functions,
element selects with a non-constant index, packed struct members, port and
state arrays, and a class with both step() and comb()."""
from __future__ import annotations

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab.sync import SyncElabError, find_class_var, sync_component
from fw.hdl.fe.parser import Parser
from zuspec.ir.core.data_type import ProcessKind
from zuspec.ir.core.expr import (ExprBin, ExprBool, ExprCompare, ExprConstant,
                                 ExprIfExp, ExprRefField, ExprSlice, ExprSubscript,
                                 ExprUnary, TypeExprRefSelf)
from zuspec.ir.core.fields import FieldInOut
from zuspec.ir.core.stmt import StmtAssign, StmtIf

SV = '''
typedef struct packed { logic [6:0] v; logic last; } beat_t;

// A local: one wire `t`, read by both writes.
class b_local extends fw_hdl_pkg::fw_component;
    bit [3:0] a, b;
    virtual function void step();
        bit [3:0] t = a + 3;
        a = t;
        b = t;
    endfunction
endclass

// A loop with a static bound, unrolled; a constant index after unrolling.
class b_for extends fw_hdl_pkg::fw_component;
    bit [3:0] r[3];
    virtual function void step();
        for (int k = 0; k < 3; k++) r[k] = k + 1;
    endfunction
endclass

// An early return: the rest of the body is the else branch.
class b_return extends fw_hdl_pkg::fw_component;
    bit [3:0] a, b;
    virtual function void step();
        if (in_reset()) begin
            a = 0;
            return;
        end
        a = a + 1;
        b = a;
    endfunction
endclass

// A function with a return in a loop (priority pick), inlined; foreach over
// a port array; a read of a port array element at a computed index.
class b_pick #(int N = 3) extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in  #(beat_t) in[N];
    fw_hdl_pkg::fw_rv_sp_out #(beat_t) out;
    function int pick();
        for (int i = 0; i < N; i++)
            if (in[i].get_valid()) return i;
        return 0;
    endfunction
    virtual function void comb();
        int g = pick();
        out.set_valid(in[g].get_valid());
        out.set_data(in[g].get_data());
        foreach (in[i]) in[i].set_ready(i == g && out.get_ready());
    endfunction
endclass

// State array: a write and a read at computed indices; a struct member.
class b_mem extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in #(beat_t) in;
    beat_t    mem[2];
    bit       wr, rd;
    bit       last;
    virtual function void step();
        mem[wr] = in.get_data();
        last = mem[rd].last;
    endfunction
endclass

// step() and comb() in one class: comb drives ready, step the rest.
class b_both extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in  #(bit [3:0]) in;
    fw_hdl_pkg::fw_rv_sp_out #(bit [3:0]) out;
    bit full;
    virtual function void comb();
        in.set_ready(!full);
    endfunction
    virtual function void step();
        if (in_reset()) begin
            full = 0;
            out.set_valid(0);
        end else begin
            full = in.get_valid();
            out.set_valid(full);
            out.set_data(in.get_data());
        end
    endfunction
endclass

class bad_both extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_out #(bit) out;
    virtual function void comb();
        out.set_valid(1);
        out.set_data(0);
    endfunction
    virtual function void step();
        out.set_valid(0);
    endfunction
endclass

class bad_bound extends fw_hdl_pkg::fw_component;
    bit [3:0] n, x;
    virtual function void step();
        for (int k = 0; k < n; k++) x = x + 1;
    endfunction
endclass

class bad_port_write extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in #(bit) in[2];
    bit s;
    virtual function void comb();
        in[s].set_ready(1);
    endfunction
endclass

module t;
    b_local        bl;
    b_for          bf;
    b_return       br;
    b_pick #(3)    bp;
    b_mem          bm;
    b_both         bb;
    bad_both       xb;
    bad_bound      xn;
    bad_port_write xp;
endmodule
'''


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    d = tmp_path_factory.mktemp("sync_body")
    f = d / "t.sv"
    f.write_text(SV)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="t"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    return p        # keeps the compilation alive


def _comp(parsed, var):
    return sync_component(find_class_var(parsed.compilation, "t", var))


def _e(comp, e) -> str:
    if isinstance(e, ExprRefField):
        assert isinstance(e.base, TypeExprRefSelf)
        return comp.fields[e.index].name
    if isinstance(e, ExprConstant):
        return str(e.value)
    if isinstance(e, ExprUnary):
        return f"{e.op.name}({_e(comp, e.operand)})"
    if isinstance(e, ExprBool):
        return f"{e.op.name}(" + ", ".join(_e(comp, v) for v in e.values) + ")"
    if isinstance(e, ExprCompare):
        return f"{e.ops[0].name}({_e(comp, e.left)}, {_e(comp, e.comparators[0])})"
    if isinstance(e, ExprBin):
        return f"{e.op.name}({_e(comp, e.lhs)}, {_e(comp, e.rhs)})"
    if isinstance(e, ExprIfExp):
        return f"({_e(comp, e.test)} ? {_e(comp, e.body)} : {_e(comp, e.orelse)})"
    if isinstance(e, ExprSubscript):
        s = e.slice
        if isinstance(s, ExprSlice):
            return f"{_e(comp, e.value)}[{_e(comp, s.lower)}:{_e(comp, s.upper)}]"
        return f"{_e(comp, e.value)}[{_e(comp, s)}]"
    raise AssertionError(e)


def _body(comp, stmts) -> list:
    """Statements as text: ``"x = e"`` or ``("if c", [then], [else])``."""
    out = []
    for s in stmts:
        if isinstance(s, StmtAssign):
            out.append(f"{_e(comp, s.targets[0])} = {_e(comp, s.value)}")
        else:
            assert isinstance(s, StmtIf), s
            out.append((f"if {_e(comp, s.test)}", _body(comp, s.body), _body(comp, s.orelse)))
    return out


def _proc(comp, name):
    for fn in comp.sync_processes + comp.comb_processes:
        if fn.name == name:
            return _body(comp, fn.body)
    raise AssertionError(f"no process {name}")


def test_local_is_a_wire(parsed):
    comp = _comp(parsed, "bl")
    assert _proc(comp, "wires") == ["t = Add(a, 3)"]
    assert _proc(comp, "step") == ["a = t", "b = t"]
    t = comp.fields[[f.name for f in comp.fields].index("t")]
    assert (t.datatype.bits, t.drive) == (4, ProcessKind.COMB)
    assert [f.name for f in comp.comb_processes] == ["wires"]


def test_for_is_unrolled(parsed):
    comp = _comp(parsed, "bf")
    assert [f.name for f in comp.fields if not isinstance(f, FieldInOut)] == ["r_0", "r_1", "r_2"]
    assert _proc(comp, "step") == ["r_0 = 1", "r_1 = 2", "r_2 = 3"]


def test_return_ends_the_path(parsed):
    comp = _comp(parsed, "br")
    # b reads the a written before it (SSA), only on the non-reset path
    assert _proc(comp, "step") == [
        ("if reset", ["a = 0"], ["a = Add(a, 1)", "b = Add(a, 1)"])]
    assert {f.name: f.no_reset for f in comp.fields if not isinstance(f, FieldInOut)} == \
        {"a": False, "b": True}


def test_function_inlined_and_port_array(parsed):
    comp = _comp(parsed, "bp")
    names = [f.name for f in comp.fields]
    assert names[:9] == ["in_0_valid", "in_0_ready", "in_0_data", "in_1_valid", "in_1_ready",
                         "in_1_data", "in_2_valid", "in_2_ready", "in_2_data"]
    # The function's value is one wire; the return in the loop is a ?: chain.
    assert _proc(comp, "wires") == [
        "pick = (in_0_valid ? 0 : (in_1_valid ? 1 : (in_2_valid ? 2 : 0)))"]
    assert _proc(comp, "comb") == [
        "out_valid = (Eq(pick, 0) ? in_0_valid : (Eq(pick, 1) ? in_1_valid : in_2_valid))",
        "out_data = (Eq(pick, 0) ? in_0_data : (Eq(pick, 1) ? in_1_data : in_2_data))",
        "in_0_ready = And(Eq(0, pick), out_ready)",
        "in_1_ready = And(Eq(1, pick), out_ready)",
        "in_2_ready = And(Eq(2, pick), out_ready)"]
    assert comp.sync_processes == []


def test_state_array_and_struct_member(parsed):
    comp = _comp(parsed, "bm")
    assert _proc(comp, "step") == [
        ("if Eq(wr, 0)", ["mem_0 = in_data"], []),
        ("if Eq(wr, 1)", ["mem_1 = in_data"], []),
        # the read sees the write before it (SSA); `.last` is bit 0, selected
        # in each arm (a bit select of a `?:` is not legal Verilog)
        "last = (Eq(rd, 0) ? (Eq(wr, 0) ? in_data[0] : mem_0[0]) "
        ": (Eq(wr, 1) ? in_data[0] : mem_1[0]))"]


def test_step_and_comb(parsed):
    comp = _comp(parsed, "bb")
    drive = {f.name: f.drive for f in comp.fields}
    force = {f.name: f.reset_force for f in comp.fields}
    S, C = ProcessKind.SYNC, ProcessKind.COMB
    assert drive == {"clock": None, "reset": None, "in_valid": None, "in_ready": C,
                     "in_data": None, "out_valid": S, "out_ready": None, "out_data": S,
                     "full": S}
    # reset-force only on what step() drives
    assert (force["in_ready"], force["out_valid"]) == (None, 0)
    assert _proc(comp, "comb") == ["in_ready = Not(full)"]
    assert [f.name for f in comp.sync_processes] == ["step"]


@pytest.mark.parametrize("var,msg", [
    ("xb", r"'out_valid' is written by both comb\(\) and step\(\)"),
    ("xn", "loop bound is not static"),
    ("xp", "a port write needs a constant index"),
])
def test_body_errors(parsed, var, msg):
    with pytest.raises(SyncElabError, match=msg):
        _comp(parsed, var)
