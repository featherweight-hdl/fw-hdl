"""Micro-pipelining D0 spikes (docs/design/micro-pipelining-feasibility.md):
F5a, channel roles on the flattened port fields of parameterized sync IR;
F5b, recognizing a map (python/fw/hdl/spikes/dataflow.py) and saying why a
component is not one."""
from __future__ import annotations

import os
import sys

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab.sync import find_class_var
from fw.hdl.fe.elab.sync_param import _Types, sync_component_param
from fw.hdl.fe.parser import Parser
from fw.hdl.spikes.dataflow import MapMatch, NoMatch, channels, match_map

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
EX = os.path.join(ROOT, "examples", "rr_merge_pipe")


@pytest.fixture(scope="module")
def pipe_ir():
    """The parameterized IR of rr_merge_pipe (v0) and of its stall-1 variant."""
    sys.path.insert(0, os.path.join(EX, "scripts"))
    try:
        from gen_rtl import FILES, INCDIRS
    finally:
        sys.path.pop(0)
    from fw.hdl.emit.sync import elab_sync_param
    return elab_sync_param(FILES, "rr_merge_pipe_emit_top", incdirs=INCDIRS,
                           vars=["rr_merge_pipe", "rr_merge_pipe_stall1"])


def _roles(comp):
    return {f.name: (f.pragmas["channel"], f.pragmas["channel_role"], f.pragmas["channel_side"])
            for f in comp.fields if f.pragmas.get("channel_kind") == "rv"}


def test_roles_map(pipe_ir):
    r = _roles(pipe_ir["rr_merge_pipe"]["pipe_map_in"])
    assert r == {"in_valid": ("in", "valid", "in"), "in_ready": ("in", "ready", "in"),
                 "in_data": ("in", "data", "in"), "out_valid": ("out", "valid", "out"),
                 "out_ready": ("out", "ready", "out"), "out_data": ("out", "data", "out")}


def test_roles_arbiter_fifo(pipe_ir):
    m = pipe_ir["rr_merge_pipe"]
    for k in ("rr_arbiter", "rr_fifo"):
        ch = channels(m[k])
        assert set(ch) == {"in", "out"}
        assert ch["in"].side == "in" and ch["out"].side == "out"
    assert channels(m["rr_arbiter"])["in"].lanes is not None     # in[N]
    assert channels(m["rr_fifo"])["in"].lanes is None
    # state is not a channel
    assert "ptr" not in _roles(m["rr_arbiter"])


def test_match_map_lanes(pipe_ir):
    r = match_map(pipe_ir["rr_merge_pipe"]["pipe_map_in"])
    assert isinstance(r, MapMatch), r
    assert r.lane is not None and r.calls == ["f"]
    assert r.inp.name == "in" and r.out.name == "out"


def test_match_map_scalar(pipe_ir):
    r = match_map(pipe_ir["rr_merge_pipe"]["pipe_map_out"])
    assert isinstance(r, MapMatch), r
    assert r.lane is None and r.calls == ["f"]


@pytest.mark.parametrize("var,mod,why", [
    ("rr_merge_pipe", "rr_arbiter", "step()"),
    ("rr_merge_pipe", "rr_fifo", "step()"),
    ("rr_merge_pipe", "rr_merge", "composite"),
    ("rr_merge_pipe_stall1", "pipe_map_in_stall1", "step()"),
])
def test_rejects(pipe_ir, var, mod, why):
    r = match_map(pipe_ir[var][mod])
    assert isinstance(r, NoMatch) and why in r.reason, r


NEAR = '''
package nm_pkg;
typedef struct packed { logic [7:0] v; logic last; } beat_t;

// valid depends on the data: a filter
class filt extends fw_hdl_pkg::fw_component implements fw_hdl_pkg::fw_combinational;
    fw_hdl_pkg::fw_rv_sp_in  #(beat_t) in;
    fw_hdl_pkg::fw_rv_sp_out #(beat_t) out;
    virtual function void comb();
        beat_t x;
        out.set_valid(in.get_valid() && in.get_data().v != 0);
        out.set_data(in.get_data());
        in.set_ready(out.get_ready());
    endfunction
endclass

// ready depends on the input's data
class rdy extends fw_hdl_pkg::fw_component implements fw_hdl_pkg::fw_combinational;
    fw_hdl_pkg::fw_rv_sp_in  #(beat_t) in;
    fw_hdl_pkg::fw_rv_sp_out #(beat_t) out;
    virtual function void comb();
        out.set_valid(in.get_valid());
        out.set_data(in.get_data());
        in.set_ready(out.get_ready() || in.get_data().last);
    endfunction
endclass

// the data depends on out.ready
class dready extends fw_hdl_pkg::fw_component implements fw_hdl_pkg::fw_combinational;
    fw_hdl_pkg::fw_rv_sp_in  #(beat_t) in;
    fw_hdl_pkg::fw_rv_sp_out #(beat_t) out;
    virtual function void comb();
        beat_t y;
        out.set_valid(in.get_valid());
        out.set_data(out.get_ready() ? in.get_data() : y);
        in.set_ready(out.get_ready());
    endfunction
endclass

// two inputs: a join, not a map
class join2 extends fw_hdl_pkg::fw_component implements fw_hdl_pkg::fw_combinational;
    fw_hdl_pkg::fw_rv_sp_in  #(beat_t) a, b;
    fw_hdl_pkg::fw_rv_sp_out #(beat_t) out;
    virtual function void comb();
        out.set_valid(a.get_valid() && b.get_valid());
        out.set_data(a.get_data() ^ b.get_data());
        a.set_ready(out.get_ready() && b.get_valid());
        b.set_ready(out.get_ready() && a.get_valid());
    endfunction
endclass

// a map written with an if: not a straight assignment per field
class cond extends fw_hdl_pkg::fw_component implements fw_hdl_pkg::fw_combinational;
    fw_hdl_pkg::fw_rv_sp_in  #(beat_t) in;
    fw_hdl_pkg::fw_rv_sp_out #(beat_t) out;
    virtual function void comb();
        out.set_valid(in.get_valid());
        if (in.get_valid()) out.set_data(in.get_data());
        else out.set_data(in.get_data());
        in.set_ready(out.get_ready());
    endfunction
endclass
endpackage

module nm;
    import nm_pkg::*;
    filt   xf;
    rdy    xr;
    dready xd;
    join2  xj;
    cond   xi;
endmodule
'''


@pytest.fixture(scope="module")
def near(tmp_path_factory):
    d = tmp_path_factory.mktemp("pipe_near")
    f = d / "nm.sv"
    f.write_text(NEAR)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="nm"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    return p


@pytest.mark.parametrize("var,why", [
    ("xf", "a filter"),
    ("xr", "in.ready depends on the input"),
    ("xd", "out.data reads out_ready"),
    ("xj", "2 input and 1 output channels"),
    ("xi", "StmtIf"),
])
def test_near_misses(near, var, why):
    comp = sync_component_param(find_class_var(near.compilation, "nm", var), None,
                                _Types("nm_types"))
    r = match_map(comp)
    assert isinstance(r, NoMatch) and why in r.reason, r
