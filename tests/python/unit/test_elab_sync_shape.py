"""IR shape of the S3 sync classes (fe/elab/sync.py): fw_rv_slice (step)
and fw_rv_pass (comb) as flattened Zuspec IR components."""
from __future__ import annotations

import warnings

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab.sync import (SyncElabError, SyncLintWarning, _check,
                                 find_class_var, sync_component)
from fw.hdl.fe.parser import Parser
from zuspec.ir.core.data_type import ProcessKind
from zuspec.ir.core.expr import (ExprBin, ExprBool, ExprCompare, ExprConstant,
                                 ExprIfExp, ExprRefField, ExprUnary,
                                 TypeExprRefSelf)
from zuspec.ir.core.fields import FieldInOut
from zuspec.ir.core.stmt import StmtAssign, StmtIf

SV = '''
class bad_loop extends fw_hdl_pkg::fw_component;
    bit [3:0] n;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void step();
        while (n < 2) n = n + 1;
    endfunction
endclass

class bad_call extends fw_hdl_pkg::fw_component;
    bit [3:0] n;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void step();
        n = $urandom;
    endfunction
endclass

class ssa_rbw extends fw_hdl_pkg::fw_component;
    bit [3:0] x, y;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void step();
        y = x;
        x = x + 1;
    endfunction
endclass

class ssa_raw extends fw_hdl_pkg::fw_component;
    bit [3:0] x, y;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void step();
        x = x + 1;
        y = x;
        x = y + 2;
        if (x == 3) y = x;
    endfunction
endclass

class ssa_branch extends fw_hdl_pkg::fw_component;
    bit       c;
    bit [3:0] x, y, z, w;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void step();
        if (c) begin
            x = 1;
            z = 3;
        end else
            x = 2;
        y = x;
        w = z;
    endfunction
endclass

class bad_fn extends fw_hdl_pkg::fw_component;
    bit [3:0] n;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    function bit [3:0] f(); return n + 1; endfunction
    virtual function void step();
        n = f();
    endfunction
endclass

class bad_cstate extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in  #(bit) in;
    fw_hdl_pkg::fw_rv_sp_out #(bit) out;
    bit t;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void comb();
        t = in.get_valid();
        out.set_valid(t);
        out.set_data(in.get_data());
        in.set_ready(out.get_ready());
    endfunction
endclass

class bad_latch extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in  #(bit) in;
    fw_hdl_pkg::fw_rv_sp_out #(bit) out;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void comb();
        if (in.get_valid()) out.set_valid(1);
        out.set_data(in.get_data());
        in.set_ready(out.get_ready());
    endfunction
endclass

class lint_ported extends fw_hdl_pkg::fw_component;
    bit c;
    bit [3:0] x, y;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    (* fw_ported *) virtual function void step();
        if (c) x = 1;
        y = x;
    endfunction
endclass

module t;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    bad_fn                    bf;
    bad_cstate                bs;
    bad_latch                 bt;
    lint_ported               lp;
    fw_rv_slice #(bit [36:0]) s;
    fw_rv_pass  #(bit [7:0])  p;
    fw_component              c;
    bad_loop                  bl;
    bad_call                  bc;
    ssa_rbw                   sr;
    ssa_raw                   sa;
    ssa_branch                sb;
endmodule
'''


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    d = tmp_path_factory.mktemp("sync_shape")
    f = d / "t.sv"
    f.write_text(SV)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="t"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    return p        # keeps the compilation alive


def _shape(comp):
    return {f.name: (f.datatype.bits,
                     ("out" if f.is_out else "in") if isinstance(f, FieldInOut) else "state",
                     f.drive, f.reset_force, f.no_reset) for f in comp.fields}


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


def test_slice_shape(parsed):
    comp = sync_component(find_class_var(parsed.compilation, "t", "s"), "fw_rv_slice_w37")
    S = ProcessKind.SYNC
    assert comp.name == "fw_rv_slice_w37"
    assert _shape(comp) == {
        "clock":      (1, "in", None, None, False),
        "reset":      (1, "in", None, None, False),
        "in_valid":   (1, "in", None, None, False),
        "in_ready":   (1, "out", S, 0, False),
        "in_data":    (37, "in", None, None, False),
        "out_valid":  (1, "out", S, 0, False),
        "out_ready":  (1, "in", None, None, False),
        "out_data":   (37, "out", S, None, False),
        "skid_valid": (1, "state", S, None, False),
        "skid_data":  (37, "state", S, None, True),
    }
    assert [f.name for f in comp.sync_processes] == ["step"]
    assert comp.comb_processes == []
    md = comp.sync_processes[0].metadata
    assert (md["clock"].index, md["reset"].index) == (0, 1)
    assert _body(comp, comp.sync_processes[0].body) == [
        ("if reset",
         ["out_valid = 0", "skid_valid = 0", "in_ready = 1"],
         [("if Or(out_ready, Not(out_valid))",
           [("if skid_valid",
             ["out_valid = 1", "out_data = skid_data", "skid_valid = 0"],
             ["out_valid = in_valid",
              ("if in_valid", ["out_data = in_data"], [])]),
            "in_ready = 1"],
           [("if And(in_valid, in_ready)",
             ["skid_valid = 1", "skid_data = in_data", "in_ready = 0"],
             [])])])]


def test_pass_shape(parsed):
    comp = sync_component(find_class_var(parsed.compilation, "t", "p"))
    C = ProcessKind.COMB
    assert _shape(comp) == {
        "in_valid":  (1, "in", None, None, False),
        "in_ready":  (1, "out", C, None, False),
        "in_data":   (8, "in", None, None, False),
        "out_valid": (1, "out", C, None, False),
        "out_ready": (1, "in", None, None, False),
        "out_data":  (8, "out", C, None, False),
    }
    assert [f.name for f in comp.comb_processes] == ["comb"]
    assert _body(comp, comp.comb_processes[0].body) == [
        "out_valid = in_valid", "out_data = in_data", "in_ready = out_ready"]
    assert comp.sync_processes == []


def test_no_process_is_an_error(parsed):
    with pytest.raises(SyncElabError, match="neither step"):
        sync_component(find_class_var(parsed.compilation, "t", "c"))


@pytest.mark.parametrize("var,msg", [("bl", "unsupported statement WhileLoop"),
                                     ("bc", "unsupported call")])
def test_unsupported_body_is_an_error(parsed, var, msg):
    with pytest.raises(SyncElabError, match=msg):
        sync_component(find_class_var(parsed.compilation, "t", var))


# SSA (plan S5.2b): a state read after a write in the same step() reads the
# written value; writes stay in place (nonblocking, last write wins). Loops
# are rejected by the front end (bad_loop above).
@pytest.mark.parametrize("var,body", [
    ("sr", ["y = x", "x = Add(x, 1)"]),
    ("sa", ["x = Add(x, 1)", "y = Add(x, 1)", "x = Add(Add(x, 1), 2)",
            ("if Eq(Add(Add(x, 1), 2), 3)", ["y = Add(Add(x, 1), 2)"], [])]),
    ("sb", [("if c", ["x = 1", "z = 3"], ["x = 2"]),
            "y = (c ? 1 : 2)", "w = (c ? 3 : z)"]),
])
def test_ssa(parsed, var, body):
    comp = sync_component(find_class_var(parsed.compilation, "t", var))
    assert _body(comp, comp.sync_processes[0].body) == body


# Static checks (plan S5.2c): each fires on a negative case.
@pytest.mark.parametrize("var,msg", [
    ("bf", "unsupported call"),                     # no opaque calls
    ("bs", "writes state 't'"),                     # comb() has no state
    ("bt", r"output\(s\) out_valid not assigned on every path"),
])
def test_static_check(parsed, var, msg):
    with pytest.raises(SyncElabError, match=msg):
        sync_component(find_class_var(parsed.compilation, "t", var))


def test_writes_input_is_an_error(parsed):
    # The port views have no set_ for input fields, so SV cannot express
    # this; check the IR rule directly on the slice with a forged body.
    comp = sync_component(find_class_var(parsed.compilation, "t", "s"))
    fn = comp.sync_processes[0]
    ix = [f.name for f in comp.fields].index("in_valid")
    bad = [StmtAssign(targets=[ExprRefField(base=TypeExprRefSelf(), index=ix)],
                      value=ExprConstant(value=1))]
    with pytest.raises(SyncElabError, match="writes input 'in_valid'"):
        _check(find_class_var(parsed.compilation, "t", "s"), comp, fn, bad)


def test_ported_raw_lint(parsed):
    with pytest.warns(SyncLintWarning, match=r"fw_ported.*: x "):
        comp = sync_component(find_class_var(parsed.compilation, "t", "lp"))
    assert len(comp.sync_processes[0].metadata["lint"]) == 1
    # SSA still applies: y reads the value written on the path
    assert _body(comp, comp.sync_processes[0].body) == [
        ("if c", ["x = 1"], []), "y = (c ? 1 : x)"]


def test_no_lint_without_ported(parsed):
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyncLintWarning)
        comp = sync_component(find_class_var(parsed.compilation, "t", "sa"))
    assert comp.sync_processes[0].metadata["lint"] == []


def _names(comp, ix):
    return sorted(comp.fields[i].name for i in ix)


def test_read_write_sets(parsed):
    comp = sync_component(find_class_var(parsed.compilation, "t", "s"))
    md = comp.sync_processes[0].metadata
    assert _names(comp, md["reads"]) == ["in_data", "in_ready", "in_valid", "out_ready",
                                         "out_valid", "reset", "skid_data", "skid_valid"]
    assert _names(comp, md["writes"]) == ["in_ready", "out_data", "out_valid",
                                          "skid_data", "skid_valid"]
    comp = sync_component(find_class_var(parsed.compilation, "t", "p"))
    md = comp.comb_processes[0].metadata
    assert _names(comp, md["reads"]) == ["in_data", "in_valid", "out_ready"]
    assert _names(comp, md["writes"]) == ["in_ready", "out_data", "out_valid"]
