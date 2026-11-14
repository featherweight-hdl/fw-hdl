"""Static elaboration of a sync composite (plan-sync-rtl E10, S6.2s1):
hier.elaborate_tree runs new()/build()/connect() at compile time and records
the children and the sync-port wiring (connect, connect_up)."""
from __future__ import annotations

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab import hier
from fw.hdl.fe.elab.sync import find_class_var, sync_component
from fw.hdl.fe.parser import Parser

SV = '''
class rv2 extends fw_hdl_pkg::fw_component;
    typedef bit [7:0] T;
    fw_std_pkg::fw_rv_slice #(T) a;
    fw_std_pkg::fw_rv_pass  #(T) b;
    fw_hdl_pkg::fw_rv_sp_in  #(T) in;
    fw_hdl_pkg::fw_rv_sp_out #(T) out;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
        in  = new(null, "in", this);
        out = new(null, "out", this);
    endfunction
    virtual function void build();
        a = new("a", this);
        b = new("b", this);
    endfunction
    virtual function void connect();
        a.in.connect_up(in);
        b.in.connect(a.out);
        b.out.connect_up(out);
    endfunction
endclass

module t;
    rv2 c;
endmodule
'''


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    d = tmp_path_factory.mktemp("sync_tree")
    f = d / "t.sv"
    f.write_text(SV)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="t"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    return p        # keeps the compilation alive


def test_children_and_connects(parsed):
    cls = find_class_var(parsed.compilation, "t", "c")
    top = hier.elaborate_tree(parsed.compilation, cls, "c")
    assert {k: hier._generic(n.cls) for k, n in top.children.items()} \
        == {"a": "fw_rv_slice", "b": "fw_rv_pass"}
    assert top.sync_connects == [
        ("connect_up", "c.a.in", ["c.in"]),
        ("connect", "c.b.in", ["c.a.out"]),
        ("connect_up", "c.b.out", ["c.out"]),
    ]
    # each child is a leaf the sync front end lowers
    for k, n in top.children.items():
        assert not n.children
        assert sync_component(n.cls, f"rv2_{k}").fields


def test_composite_emits_hierarchy(parsed, tmp_path):
    import shutil
    import subprocess
    import zuspec.ir.core as ir
    from fw.hdl.emit.be_sv import emit_sv
    from fw.hdl.fe.elab.sync_tree import composite_components

    cls = find_class_var(parsed.compilation, "t", "c")
    top = hier.elaborate_tree(parsed.compilation, cls, "c")
    comps = composite_components(top)
    assert list(comps)[-1] == "c"
    sv = emit_sv(ir.Context(type_m=comps))
    assert "module c(" in sv
    for k, n in top.children.items():
        assert f"{n.spelling()} {k} (" in sv
    # a.out feeds b.in through internal wires; own ports reach the children
    assert ".in_valid(in_valid)" in sv and ".out_valid(out_valid)" in sv
    assert ".in_valid(a_out_valid)" in sv
    if shutil.which("verilator") is None:
        pytest.skip("no verilator")
    f = tmp_path / "c.sv"
    f.write_text(sv)
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "-Wno-DECLFILENAME", "--top-module", "c", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_emit_sync_composite(tmp_path):
    from fw.hdl.emit.sync import emit_sync
    f = tmp_path / "t.sv"
    f.write_text(SV)
    out = emit_sync([str(f)], "t")
    assert list(out) == ["c"]
    assert out["c"].count("endmodule") == 3 and "module c(" in out["c"]
