"""Parameterized lowering (fe/elab/sync_param.py + be-sv sync_param.py,
examples/rr_merge/LOWERING.md L9): one module per class with the class's
parameters, symbolic widths, array ports, loops kept, next-state step()."""
from __future__ import annotations

import shutil
import subprocess

import pytest

import zuspec.ir.core as ir
from fw.hdl.config import FlowConfig
from fw.hdl.emit.be_sv import emit_sv
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab import hier
from fw.hdl.fe.elab.sync import SyncElabError, find_class_var
from fw.hdl.fe.elab.sync_param import _Types, composite_param, sync_component_param
from fw.hdl.fe.parser import Parser

SV = '''
package p_pkg;
typedef struct packed { logic [6:0] v; logic last; } beat_t;

// A FIFO: a type and a value parameter, widths from the parameter, a state
// array at a computed index, a reset-forced output read back in step().
class q #(type T = beat_t, int DEPTH = 2) extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in  #(T) in;
    fw_hdl_pkg::fw_rv_sp_out #(T) out;
    T                         mem[DEPTH];
    bit [$clog2(DEPTH)-1:0]   wr, rd;
    bit [$clog2(DEPTH+1)-1:0] count;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
        in  = new(null, "in", this);
        out = new(null, "out", this);
    endfunction
    virtual function void comb();
        in.set_ready(count < DEPTH || out.get_ready());
    endfunction
    virtual function void step();
        bit push, pop;
        if (in_reset()) begin
            wr = 0; rd = 0; count = 0;
            out.set_valid(0);
            return;
        end
        push = in.get_valid() && in.get_ready();
        pop  = out.get_valid() && out.get_ready();
        if (push) begin
            mem[wr] = in.get_data();
            wr = (wr + 1) % DEPTH;
        end
        if (pop) rd = (rd + 1) % DEPTH;
        count = count + push - pop;
        out.set_valid(count != 0);
        if (count != 0) out.set_data(mem[rd]);
    endfunction
endclass

// A port array, a function with a return in a loop, foreach.
class pick #(type T = beat_t, int N = 3) extends fw_hdl_pkg::fw_component;
    typedef bit [$clog2(N)-1:0] idx_t;
    fw_hdl_pkg::fw_rv_sp_in  #(T) in[N];
    fw_hdl_pkg::fw_rv_sp_out #(T) out;
    idx_t last_g;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out = new(null, "out", this);
    endfunction
    function int first();
        for (int i = 0; i < N; i++)
            if (in[i].get_valid()) return i;
        return 0;
    endfunction
    virtual function void comb();
        int g = first();
        out.set_valid(in[g].get_valid());
        out.set_data(in[g].get_data());
        foreach (in[i]) in[i].set_ready(i == g && out.get_ready());
    endfunction
    virtual function void step();
        if (in_reset()) last_g = 0;
        else begin
            last_g = 1;
            if (out.get_valid()) last_g = first();
        end
    endfunction
endclass

class top #(type T = beat_t, int N = 3, int DEPTH = 2) extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in  #(T) in[N];
    fw_hdl_pkg::fw_rv_sp_out #(T) out;
    pick #(T, N)  p;
    q #(T, DEPTH) f;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out = new(null, "out", this);
    endfunction
    virtual function void build();
        p = new("p", this);
        f = new("f", this);
    endfunction
    virtual function void connect();
        foreach (in[i]) p.in[i].connect_up(in[i]);
        p.out.connect(f.in);
        f.out.connect_up(out);
    endfunction
endclass

// Port array elements crossed: not expressible as one array connection.
class crossed extends fw_hdl_pkg::fw_component;
    fw_hdl_pkg::fw_rv_sp_in  #(beat_t) in[2];
    fw_hdl_pkg::fw_rv_sp_out #(beat_t) out;
    pick #(beat_t, 2) p;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
        foreach (in[i]) in[i] = new(null, $sformatf("in[%0d]", i), this);
        out = new(null, "out", this);
    endfunction
    virtual function void build();
        p = new("p", this);
    endfunction
    virtual function void connect();
        p.in[0].connect_up(in[1]);
        p.in[1].connect_up(in[0]);
        p.out.connect_up(out);
    endfunction
endclass

// An array written from two places: next-state copied element by element.
class two_w extends fw_hdl_pkg::fw_component;
    bit [3:0] r[4];
    bit [1:0] a;
    virtual function void step();
        r[a] = 1;
        r[a + 1] = r[a];
    endfunction
endclass

class bad_ret extends fw_hdl_pkg::fw_component;
    bit [3:0] x;
    virtual function void step();
        for (int i = 0; i < 4; i++) begin
            if (x == i) return;
            x = x + 1;
        end
    endfunction
endclass

class bad_fn extends fw_hdl_pkg::fw_component;
    bit [3:0] x;
    function int bump();
        x = x + 1;
        return x;
    endfunction
    virtual function void step();
        x = bump();
    endfunction
endclass

class bad_for extends fw_hdl_pkg::fw_component;
    bit [3:0] x;
    virtual function void step();
        for (int i = 4; i > 0; i--) x = x + 1;
    endfunction
endclass
endpackage

module t;
    import p_pkg::*;
    q #(beat_t, 4) fq;
    pick           fp;
    top            ft;
    crossed        fc;
    two_w          fw;
    bad_ret        xr;
    bad_fn         xf;
    bad_for        xl;
endmodule
'''


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    d = tmp_path_factory.mktemp("sync_param")
    f = d / "t.sv"
    f.write_text(SV)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="t"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    return p        # keeps the compilation alive


def _leaf(parsed, var):
    types = _Types("t_types")
    comp = sync_component_param(find_class_var(parsed.compilation, "t", var), None, types)
    return comp, types


def _sv(comp, types) -> str:
    return emit_sv(ir.Context(type_m={**types.structs, comp.name: comp}))


def _lint(tmp_path, sv: str, top: str):
    if shutil.which("verilator") is None:
        pytest.skip("no verilator")
    f = tmp_path / f"{top}.sv"
    f.write_text(sv)
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "-Wno-DECLFILENAME",
                        "-Wno-WIDTH", "-Wno-UNUSEDSIGNAL", "--top-module", top, str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_params_and_widths(parsed):
    comp, types = _leaf(parsed, "fq")
    # the class's parameters and declared defaults, not the specialization's (4)
    tps = {tp.name: tp for tp in comp.template_params}
    assert tps["T"].default_value.ref_name == "t_types::beat_t"
    assert tps["DEPTH"].default_value.value == 2
    dt = {f.name: f.datatype for f in comp.fields}
    assert dt["in_data"].ref_name == "T"
    assert dt["mem"].element_type.ref_name == "T"
    assert dt["mem"].size_expr.name == "DEPTH"
    assert dt["wr"].width_expr.func.name == "clog2"
    assert list(types.structs) == ["t_types::beat_t"]


def test_fifo_emits_next_state(parsed, tmp_path):
    comp, types = _leaf(parsed, "fq")
    sv = _sv(comp, types)
    assert "package t_types;" in sv
    assert "module q #(\n  parameter type T = t_types::beat_t,\n  parameter int DEPTH = 2\n)" \
        in sv
    assert "logic [$clog2(DEPTH)-1:0] wr;" in sv
    assert "logic [$clog2(DEPTH+1)-1:0] count;" in sv
    assert "T mem [DEPTH];" in sv
    # step(): next state in class order; the forced output read past the reset
    # branch is its next value
    # mem has one write site: an enabled write, and the read after it bypasses
    assert "mem_we = 1'b1;\n        mem_wa = wr_n;\n        mem_wd = in_data;" in sv
    assert "pop = out_valid_n && out_ready;" in sv
    assert "out_data_n = (mem_we && mem_wa == rd_n) ? mem_wd : mem[rd_n];" in sv
    assert "assign out_valid = reset ? '0 : out_valid_q;" in sv
    assert "if (mem_we) mem[mem_wa] <= mem_wd;" in sv and "mem_n" not in sv
    _lint(tmp_path, sv, "q")


def test_port_array_loop_function(parsed, tmp_path):
    comp, types = _leaf(parsed, "fp")
    dt = {f.name: f.datatype for f in comp.fields}
    assert dt["in_valid"].size_expr.name == "N"
    sv = _sv(comp, types)
    assert "input  logic [N-1:0] in_valid," in sv
    assert "input  T [N-1:0] in_data," in sv
    assert "logic [$clog2(N)-1:0] last_g;" in sv
    assert "for (int i = 0; i < N; i++) begin\n      in_ready[i] = (i == g) && out_ready;" \
        in sv
    assert "function automatic int first();" in sv
    # first() takes no arguments and is read on current values: one value
    # per cycle, read where it is called
    assert "always_comb first_v = first();" in sv
    assert "last_g_n = first_v;" in sv and "first_n" not in sv
    _lint(tmp_path, sv, "pick")


def test_composite(parsed, tmp_path):
    cls = find_class_var(parsed.compilation, "t", "ft")
    tree = hier.elaborate_tree(parsed.compilation, cls, "ft")
    types = _Types("ft_types")
    comps = composite_param(tree, types)
    assert list(comps) == ["pick", "q", "ft"]
    sv = emit_sv(ir.Context(type_m={**types.structs, **comps}))
    assert sv.count("endmodule") == 3 and sv.count("package ft_types;") == 1
    assert "pick #(.T(T), .N(N)) p (" in sv and "q #(.T(T), .DEPTH(DEPTH)) f (" in sv
    assert ".in_valid(in_valid)" in sv and ".in_data(in_data)" in sv
    assert ".in_valid(p_out_valid)" in sv and "T p_out_data;" in sv
    _lint(tmp_path, sv, "ft")


def test_composite_crossed_elements(parsed):
    cls = find_class_var(parsed.compilation, "t", "fc")
    tree = hier.elaborate_tree(parsed.compilation, cls, "fc")
    with pytest.raises(SyncElabError, match="element by element"):
        composite_param(tree)


def test_array_two_writes(parsed, tmp_path):
    comp, types = _leaf(parsed, "fw")
    sv = _sv(comp, types)
    assert "for (int j = 0; j < 4; j++) r_n[j] = r[j];" in sv
    assert "r_n[a_n] = 1;" in sv and "r_n[a_n + 1] = r_n[a_n];" in sv
    assert "for (int j = 0; j < 4; j++) r[j] <= r_n[j];" in sv
    _lint(tmp_path, sv, "two_w")


@pytest.mark.parametrize("var,msg", [
    ("xr", "a return inside a loop of a process"),
    ("xf", "a function writes 'x'"),
    ("xl", r"only 'for \(int k = a; k < b; k\+\+\)' loops"),
])
def test_errors(parsed, var, msg):
    with pytest.raises(SyncElabError, match=msg):
        _leaf(parsed, var)
