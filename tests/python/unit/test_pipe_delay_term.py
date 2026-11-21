"""Micro-pipelining D0 spike F5c route (i) (python/fw/hdl/spikes/delay_term.py):
a sync-IR function of packed structs to a zuspec-synth Term, and its delay
with timing.analyze. Values are checked by substituting constants for the
input (Terms fold constants as they are built)."""
from __future__ import annotations

import dataclasses as dc

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab.sync import find_class_var
from fw.hdl.fe.elab.sync_param import _Types, sync_component_param
from fw.hdl.fe.parser import Parser
from fw.hdl.spikes.delay_term import estimate, f_term
from zuspec.ir.core.data_type import DataTypeInt
from zuspec.synth.proc import term as T
from zuspec.synth.proc.delay import DelayModel

SV = '''
package dt_pkg;
typedef struct packed { logic [7:0] tag; logic [7:0] a, b, c; logic last; } in_t;
typedef struct packed { logic [7:0] tag; logic [15:0] y; logic last; } mid_t;

class m #(type TI = in_t, type TM = mid_t) extends fw_hdl_pkg::fw_component
        implements fw_hdl_pkg::fw_combinational;
    fw_hdl_pkg::fw_rv_sp_in  #(TI) in;
    fw_hdl_pkg::fw_rv_sp_out #(TM) out;
    function TM f(TI x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.a * x.b + x.c;
        y.last = x.last;
        return y;
    endfunction
    function TM g(TM x);
        TM y;
        y.tag  = x.tag;
        y.y    = x.y ^ (x.y >> 3);
        y.last = x.last;
        return y;
    endfunction
    virtual function void comb();
        out.set_valid(in.get_valid());
        out.set_data(g(f(in.get_data())));
        in.set_ready(out.get_ready());
    endfunction
endclass
endpackage

module dt;
    import dt_pkg::*;
    m xm;
endmodule
'''


@pytest.fixture(scope="module")
def comp_types(tmp_path_factory):
    d = tmp_path_factory.mktemp("pipe_dt")
    f = d / "dt.sv"
    f.write_text(SV)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="dt"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    types = _Types("dt_types")
    comp = sync_component_param(find_class_var(p.compilation, "dt", "xm"), None, types)
    ti, tm = types.structs["dt_types::in_t"], types.structs["dt_types::mid_t"]
    return p, comp, ti, tm


def _scale(st, W):
    fs = [dc.replace(f, datatype=DataTypeInt(bits={"a": W, "b": W, "c": W, "y": 2 * W}.get(
        f.name, f.datatype.bits), signed=False)) for f in st.fields]
    return dc.replace(st, fields=fs)


def _in(tag, a, b, c, last, W):
    return (((((tag << W | a) << W | b) << W) | c) << 1) | last


@pytest.mark.parametrize("W", [8, 16, 32])
def test_f_value(comp_types, W):
    _, comp, ti, tm = comp_types
    t, wi = f_term(comp, "f", {"TI": _scale(ti, W), "TM": _scale(tm, W)})
    assert wi == 8 + 3 * W + 1 and t.w == 8 + 2 * W + 1
    a, b, c = (1 << W) - 1, (1 << W) - 3, (1 << W) - 5      # a * b + c overflows W bits
    x = _in(0x5a, a, b, c, 1, W)
    v = T.substitute(t, {T.var("in_x", wi): T.const(x, wi)})
    assert v.op == "const"
    y = (a * b + c) & ((1 << 2 * W) - 1)
    assert v.val == ((0x5a << 2 * W | y) << 1) | 1


def test_g_shift_xor(comp_types):
    _, comp, _, tm = comp_types
    t, wi = f_term(comp, "g", {"TM": tm})
    x = (0x33 << 17) | (0xbeef << 1)
    v = T.substitute(t, {T.var("in_x", wi): T.const(x, wi)})
    assert v.val == (0x33 << 17) | ((0xbeef ^ (0xbeef >> 3)) << 1)


def test_unit_model_depth(comp_types):
    _, comp, ti, tm = comp_types
    unit = DelayModel.load("unit")
    t, wi = f_term(comp, "f", {"TI": ti, "TM": tm})
    assert estimate(t, wi, unit) == 2                 # mul, then add
    t, wi = f_term(comp, "g", {"TM": tm})
    assert estimate(t, wi, unit) == 1                 # xor (a shift by a constant is wiring)
