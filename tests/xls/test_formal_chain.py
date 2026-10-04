"""The equivalence chain (formal-svunit.md §6, F5): proven at the model, and
equal at each step down to a level.

* the design IR that ``Prove`` writes is the design as proven, and XLS's
  ``check_ir_equivalence_main`` takes it;
* ``codegen_equiv`` checks an IR function against a pipelined Verilog
  module (hand-written here, with mutants it must catch);
* ``fw.hdl.formal.Chain`` through dv-flow: a chain that passes, one whose
  proof fails, one whose IR link is about another proof's design, and one
  that skips steps.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fw.hdl.formal import codegen_equiv as ce
from fw.hdl.formal import prove

from test_formal_svunit import _CRC, _FIXTURES, _ROOT, _e2e_solver, solver  # noqa: F401

_YOSYS_BIN = _ROOT / "packages" / "yosys" / "bin"


def _yosys():
    return shutil.which("yosys") or (str(_YOSYS_BIN / "yosys")
                                     if (_YOSYS_BIN / "yosys").is_file() else None)


needs_yosys = pytest.mark.skipif(_yosys() is None, reason="yosys not found")


@pytest.fixture(autouse=True)
def _yosys_on_path(monkeypatch):
    if _yosys() and not shutil.which("yosys"):
        monkeypatch.setenv("PATH", str(_YOSYS_BIN) + os.pathsep + os.environ.get("PATH", ""))


# ---------------------------------------------------------------------------
# The first link: the design as proven
# ---------------------------------------------------------------------------

def test_design_ir_is_the_api_function_named_as_its_module(tmp_path, solver):
    from zuspec.be.xls.testing.parser import parse_package
    api, pkg = prove.make_api([str(_CRC / "crc32_pkg.sv")], ["crc32_pkg::main"], str(tmp_path))
    out = []
    rs = prove.prove_files([str(_CRC / "crc32_pkg.sv"), pkg, str(_CRC / "crc32_unit_test.sv")],
                           api=api, solver=solver, workdir=str(tmp_path), design_ir=out)
    assert all(r.status == prove.PROVEN for r in rs)
    assert [os.path.basename(p) for p in out] == ["crc32_pkg__main.formal.ir"]
    p = parse_package(Path(out[0]).read_text())        # XLS's text, as our reader takes it
    top = next(f for f in p.functions if f.name == p.top)
    assert p.top == "crc32_pkg__main"
    assert [(a.name, a.type.width) for a in top.params] == [("message", 8)]
    assert top.ret.type.width == 32
    from zuspec.be.xls.testing.xlstools import find_tool
    eq = find_tool("check_ir_equivalence_main")
    if eq:
        # the same function as fw.hdl.xls.IR writes for the rtl level
        from fw.hdl.xls_flow import sv_function_package
        from zuspec.be.xls.printer import format_package
        ref = tmp_path / "ref.ir"
        ref.write_text(format_package(sv_function_package(
            [str(_CRC / "crc32_pkg.sv")], "crc32_pkg::main", "crc32_pkg__main")))
        r = subprocess.run([eq, out[0], str(ref)], capture_output=True, text=True)
        assert "Verified equivalent" in r.stdout + r.stderr


# ---------------------------------------------------------------------------
# The codegen link, on a hand-written module
# ---------------------------------------------------------------------------

_IR = """\
package mix

top fn mix(a: bits[8] id=1, b: bits[8] id=2) -> bits[8] {
  add.3: bits[8] = add(a, b, id=3)
  ret xor.4: bits[8] = xor(add.3, a, id=4)
}
"""

#: One register stage after the input flops: latency 2.
_SV = """\
module mix(
  input wire clk,
  input wire rst,
  input wire input_valid,
  input wire [7:0] a,
  input wire [7:0] b,
  output wire output_valid,
  output wire [7:0] out
);
  reg v0, v1;
  reg [7:0] a0, b0, r1;
  always @(posedge clk) begin
    if (rst) begin v0 <= 1'b0; v1 <= 1'b0; end
    else begin v0 <= input_valid; v1 <= v0; end
    a0 <= a;
    b0 <= b;
    r1 <= EXPR;
  end
  assign output_valid = v1;
  assign out = r1;
endmodule
"""

_SIG = """\
module_name: "mix"
data_ports { direction: PORT_DIRECTION_INPUT name: "a" width: 8 type { type_enum: BITS bit_count: 8 } }
data_ports { direction: PORT_DIRECTION_INPUT name: "b" width: 8 type { type_enum: BITS bit_count: 8 } }
data_ports { direction: PORT_DIRECTION_OUTPUT name: "out" width: 8 type { type_enum: BITS bit_count: 8 } }
clock_name: "clk"
reset { name: "rst" asynchronous: false active_low: false }
pipeline {
  latency: LATENCY
  initiation_interval: 1
  pipeline_control { valid { input_name: "input_valid" output_name: "output_valid" } }
}
"""


def test_signature_is_read():
    s = ce.parse_signature(_SIG.replace("LATENCY", "2"))
    assert (s.module, s.clock, s.reset, s.reset_active_low, s.latency) == \
        ("mix", "clk", "rst", False, 2)
    assert [(p.name, p.width) for p in s.inputs] == [("a", 8), ("b", 8)]
    assert [(p.name, p.width) for p in s.outputs] == [("out", 8)]
    assert (s.input_valid, s.output_valid) == ("input_valid", "output_valid")


def _check(tmp_path, solver, expr="(a0 + b0) ^ a0", latency=2):
    (tmp_path / "mix.opt.ir").write_text(_IR)
    (tmp_path / "mix.sv").write_text(_SV.replace("EXPR", expr))
    (tmp_path / "mix.sig.textproto").write_text(_SIG.replace("LATENCY", str(latency)))
    return ce.check(str(tmp_path / "mix.opt.ir"), [str(tmp_path / "mix.sv")],
                    str(tmp_path / "mix.sig.textproto"), solver, tmp_path / "work")


@needs_yosys
def test_codegen_equivalent(tmp_path, solver):
    r = _check(tmp_path, solver)
    assert r.verdict == ce.EQUIVALENT, r.detail


@needs_yosys
def test_codegen_wrong_operator_is_a_counterexample(tmp_path, solver):
    r = _check(tmp_path, solver, expr="(a0 - b0) ^ a0")
    assert r.verdict == ce.NOT_EQUIVALENT, r.detail
    a, b = r.counterexample["in.a"], r.counterexample["in.b"]
    # both results are what each side computes for those inputs
    assert r.counterexample["out.ir"] == ((a + b) & 0xff) ^ a
    assert r.counterexample["out.rtl"] == ((a - b) & 0xff) ^ a
    assert r.counterexample["out.ir"] != r.counterexample["out.rtl"]


@needs_yosys
@pytest.mark.parametrize("latency", [1, 3])
def test_codegen_wrong_latency_is_a_counterexample(tmp_path, solver, latency):
    r = _check(tmp_path, solver, latency=latency)
    assert r.verdict == ce.NOT_EQUIVALENT, r.detail


@needs_yosys
def test_codegen_port_mismatch_is_an_error(tmp_path, solver):
    (tmp_path / "mix.opt.ir").write_text(_IR.replace("b: bits[8]", "c: bits[8]")
                                         .replace("add(a, b", "add(a, c"))
    (tmp_path / "mix.sv").write_text(_SV.replace("EXPR", "a0"))
    (tmp_path / "mix.sig.textproto").write_text(_SIG.replace("LATENCY", "2"))
    r = ce.check(str(tmp_path / "mix.opt.ir"), [str(tmp_path / "mix.sv")],
                 str(tmp_path / "mix.sig.textproto"), solver, tmp_path / "work")
    assert r.verdict == ce.ERROR and "argument c" in r.detail


# ---------------------------------------------------------------------------
# fw.hdl.formal.Chain, through dv-flow
# ---------------------------------------------------------------------------

_CHAIN_FLOW = """\
package:
  name: chain_e2e
  imports: [hdltest.svunit, synth.xls, synth.yosys, fw.hdl.xls, fw.hdl.api, fw.hdl.formal]
  tasks:
  - name: svunit
    uses: hdltest.svunit.Lib
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {crc}, include: [crc32_pkg.sv]}}
  - name: api
    uses: fw.hdl.api.Functions
    needs: [src]
    with: {{functions: [crc32_pkg::main]}}
  - name: tests-ok
    uses: std.FileSet
    with: {{type: svunitTest, base: {crc}, include: [crc32_unit_test.sv]}}
  - name: tests-bad
    uses: std.FileSet
    with: {{type: svunitTest, base: {fixtures}, include: [crc32_formal_unit_test.sv]}}
  - name: prove-ok
    uses: fw.hdl.formal.Prove
    needs: [svunit, src, api, tests-ok]
    with: {{solver: "{solver}"}}
  - name: prove-bad
    uses: fw.hdl.formal.Prove
    needs: [svunit, src, api, tests-bad]
    with: {{solver: "{solver}"}}
  - name: ir
    uses: fw.hdl.xls.IR
    needs: [src]
    with: {{top: [crc32_pkg::main]}}
  - name: rtl
    uses: synth.xls.Codegen
    needs: [ir]
    with: {{pipeline_stages: 2, input_valid_signal: input_valid, output_valid_signal: output_valid}}
  - name: equiv-ir
    uses: synth.xls.Equiv
    needs: [prove-ok, rtl]
  - name: equiv-ir-bad
    uses: synth.xls.Equiv
    needs: [prove-bad, rtl]
  - name: equiv-codegen
    uses: fw.hdl.formal.CodegenEquiv
    needs: [rtl]
    with: {{solver: "{solver}"}}
  - name: syn
    uses: synth.yosys.Synth
    needs: [rtl]
  - name: equiv-netlist
    uses: synth.yosys.Equiv
    needs: [rtl, syn]
  - name: chain-ok
    uses: fw.hdl.formal.Chain
    needs: [prove-ok, equiv-ir, equiv-codegen, equiv-netlist]
    with: {{name: ok, level: gates}}
  - name: chain-bad
    uses: fw.hdl.formal.Chain
    needs: [prove-bad, equiv-ir-bad, equiv-codegen, equiv-netlist]
    with: {{name: bad}}
  - name: chain-other
    uses: fw.hdl.formal.Chain
    needs: [prove-bad, equiv-ir, equiv-codegen, equiv-netlist]
    with: {{name: other}}
  - name: chain-broken
    uses: fw.hdl.formal.Chain
    needs: [prove-ok, equiv-netlist]
    with: {{name: broken}}
  - name: all
    passthrough: all
    needs: [chain-ok, chain-bad, chain-other, chain-broken]
"""


@pytest.mark.skipif(_e2e_solver() is None, reason="needs boolector or z3")
@needs_yosys
def test_flow_chain(tmp_path):
    from zuspec.be.xls.testing.xlstools import codegen_main, opt_main
    if not (codegen_main() and opt_main()):
        pytest.skip("XLS (opt_main, codegen_main) not found")
    (tmp_path / "flow.yaml").write_text(_CHAIN_FLOW.format(
        crc=_CRC, fixtures=_FIXTURES.parent, solver=_e2e_solver()))
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(_YOSYS_BIN), os.path.dirname(codegen_main()),
                                   env.get("PATH", "")])
    dfm = _ROOT / "packages" / "python" / "bin" / "dfm"
    r = subprocess.run([str(dfm), "run", "all"], cwd=tmp_path, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    rd = tmp_path / "rundir"

    def result(task):
        data = json.loads((rd / f"chain_e2e.{task}" / f"chain_e2e.{task}.exec_data.json")
                          .read_text())
        (tr,) = [o for o in data["output"]["output"] if o.get("type") == "hdlsim.TestResult"]
        return tr, (rd / f"chain_e2e.{task}" / "chain.log").read_text()

    tr, log = result("chain-ok")
    assert tr["status"] == "pass" and tr["sim"] == "formal-chain"
    assert tr["stats"]["links"] == 3 and tr["stats"]["links_equivalent"] == 3
    assert [c["step"] for c in tr["runinfo"]["chain"]] == ["model", "XLS IR", "RTL", "netlist"]
    assert "formal chain to level gates: pass" in log

    tr, log = result("chain-bad")                 # every link holds; the proof does not
    assert tr["status"] == "fail" and tr["stats"]["links_equivalent"] == 3
    assert tr["runinfo"]["chain"][0]["verdict"] == "fail"

    assert "broken" not in log

    tr, log = result("chain-other")               # the IR link is about another proof's design
    assert tr["status"] == "error"
    assert [ln.split(":")[1].split()[0] for ln in log.splitlines()
            if ln.strip().startswith("broken:")] == ["xlsEquivReport"]

    tr, log = result("chain-broken")              # the netlist does not start at the design IR
    assert tr["status"] == "error"
    assert "broken: yosysEquivReport" in log
