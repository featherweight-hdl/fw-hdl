"""fw.hdl.api (xls-examples.md G-9, TB-2): the call API generated from SV
function signatures, and its XLS binding generated from XLS's signature."""
from pathlib import Path

import pytest

from fw.hdl import fn_api
from fw.hdl.spl_flow import module_name
from fw.hdl.xls_flow import XlsFlowError, _find_functions, _parse, sv_to_functions
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter

HERE = Path(__file__).resolve().parent
CRC32 = str(HERE.parents[1] / "examples" / "xls" / "crc32" / "crc32_pkg.sv")

TYPES_SV = """\
package types_pkg;
  typedef struct packed { bit [31:0] a; bit [31:0] b; } pair_t;
  typedef bit signed [31:0] s32_t;
  function automatic pair_t f(bit [7:0] x, s32_t z, bit [31:0] arr [8], pair_t p);
    return p;
  endfunction
  function automatic s32_t g(s32_t a [4]);
    return a[0];
  endfunction
endpackage
"""

SIG = """\
module_name: "crc32_pkg__main"
data_ports {
  direction: PORT_DIRECTION_INPUT
  name: "message"
  width: 8
}
data_ports {
  direction: PORT_DIRECTION_OUTPUT
  name: "out"
  width: 32
}
clock_name: "clk"
reset {
  name: "rst"
  asynchronous: false
  active_low: false
}
pipeline {
  latency: 3
  initiation_interval: 1
  pipeline_control {
    valid {
      input_name: "input_valid"
      output_name: "output_valid"
    }
  }
}
"""


def _api(files, names, name=None):
    parser = _parse(files, FlowConfig(), ErrorReporter())
    subs = _find_functions(parser, names)
    mods = {s.hierarchicalPath: module_name(n) for s, n in zip(subs, names)}
    return fn_api.api_from_subroutines(
        name or fn_api.default_api_name([s.hierarchicalPath for s in subs]), subs,
        lambda s: mods[s.hierarchicalPath])


def test_crc32_api():
    api = _api([CRC32], ["crc32_pkg::main"])
    assert api.name == "crc32_pkg_api"
    (f,) = api.functions
    assert (f.name, f.path, f.module) == ("main", "crc32_pkg::main", "crc32_pkg__main")
    assert [a.decl() for a in f.args] == ["bit[7:0] message"]
    sv = fn_api.api_pkg_sv(api)
    assert "pure virtual task main(input bit[7:0] message, output bit[31:0] result);" in sv
    assert "result = crc32_pkg::main(message);" in sv


def test_types_are_spelled_as_declared(tmp_path):
    p = tmp_path / "types_pkg.sv"
    p.write_text(TYPES_SV)
    api = _api([str(p)], ["types_pkg::f", "types_pkg::g"])
    f, g = api.functions
    assert [a.decl() for a in f.args] == [
        "bit[7:0] x", "types_pkg::s32_t z", "bit[31:0] arr[0:7]", "types_pkg::pair_t p"]
    assert f.ret.decl() == "types_pkg::pair_t result"
    assert g.args[0].decl() == "types_pkg::s32_t a[0:3]"


def test_api_round_trips_through_its_file(tmp_path):
    api = _api([CRC32], ["crc32_pkg::main"])
    api.save(str(tmp_path / "a.json"))
    assert fn_api.FnApi.load(str(tmp_path / "a.json")) == api


def test_binding_from_the_xls_signature():
    m = fn_api.fn_module_from_signature(SIG)
    assert (m.module, m.inputs, m.output, m.latency) == (
        "crc32_pkg__main", [("message", 8)], ("out", 32), 3)
    assert (m.input_valid, m.output_valid, m.reset) == ("input_valid", "output_valid", "rst")
    sv = fn_api.xls_binding_sv(_api([CRC32], ["crc32_pkg::main"]), {m.module: m})
    assert "interface crc32_pkg__main_xtor_if (input bit clk, input bit rst);" in sv
    assert ".input_valid(main_if.input_valid)" in sv and ".rst(rst)" in sv
    assert "module crc32_pkg_api_harness;" in sv


def test_binding_needs_the_valid_signals():
    m = fn_api.fn_module_from_signature(SIG.replace("input_name", "x_name").replace(
        "output_name", "y_name"))
    with pytest.raises(ValueError, match="input_valid_signal"):
        fn_api.xls_binding_sv(_api([CRC32], ["crc32_pkg::main"]), {m.module: m})


def test_a_proc_signature_is_not_a_function():
    with pytest.raises(ValueError, match="proc"):
        fn_api.fn_module_from_signature('module_name: "p"\nclock_name: "clk"\n')


def test_function_lookup_by_path_and_ambiguity(tmp_path):
    p = tmp_path / "two.sv"
    p.write_text("package a; function automatic bit f(bit x); return x; endfunction endpackage\n"
                 "package b; function automatic bit f(bit x); return !x; endfunction endpackage\n")
    with pytest.raises(XlsFlowError, match="ambiguous.*a::f.*b::f"):
        sv_to_functions([str(p)], ["f"])
    (fn,) = sv_to_functions([str(p)], ["b::f"], rename={"b::f": "b__f"})
    assert fn.name == "b__f"


def test_arrays_cross_the_binding_element_0_low(tmp_path):
    # XLS flattens an array onto a port with element 0 in the low bits
    # (its codegen unflattens `values[15:0]` into element 0).
    p = tmp_path / "arr_pkg.sv"
    p.write_text("package arr_pkg;\n  typedef bit [15:0] v_t [4];\n"
                 "  function automatic v_t f(v_t a); return a; endfunction\nendpackage\n")
    api = _api([str(p)], ["arr_pkg::f"])
    m = fn_api.fn_module_from_signature(
        SIG.replace("crc32_pkg__main", "arr_pkg__f").replace('"message"\n  width: 8',
                                                              '"a"\n  width: 64')
        .replace('width: 32', 'width: 64'))
    sv = fn_api.xls_binding_sv(api, {m.module: m})
    assert "p_a[k*16 +: 16] = a[k];" in sv
    assert "result[k] = r[k*16 +: 16];" in sv
    assert "{>>" not in sv
    assert "module arr_pkg_api_harness;" in sv and "package arr_pkg_api_xls_pkg;" in sv
