"""Unit tests for fw.hdl.fe.type_mapper."""
from pyslang import ast

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.type_mapper import TypeMapper

from _fe_helpers import get_class

_SNIPPET = """
package p;
  class c;
    bit [7:0] a;
    int       b;
    logic     x;
    logic [3:0] y;
  endclass
endpackage
"""


def _field_types(name="c"):
    cls = get_class(_SNIPPET, name)
    return {m.name: m.type for m in cls if m.kind == ast.SymbolKind.ClassProperty}


def test_2state_widths_and_sign():
    tm = TypeMapper(FlowConfig(), ErrorReporter())
    types = _field_types()
    a = tm.map_type(types["a"])
    assert a.bits == 8 and a.signed is False
    b = tm.map_type(types["b"])
    assert b.bits == 32 and b.signed is True


def test_1bit_logic_carveout_allowed():
    tm = TypeMapper(FlowConfig(), ErrorReporter())
    x = tm.map_type(_field_types()["x"])
    assert x is not None and x.bits == 1


def test_wide_4state_rejected():
    reporter = ErrorReporter()
    tm = TypeMapper(FlowConfig(), reporter)
    y = tm.map_type(_field_types()["y"], what="field y")
    assert y is None
    assert reporter.has_errors()
