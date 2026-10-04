"""Formal SVUnit (formal-svunit.md, F0/F1): SVUnit tests proven for every input.

The crc32 example's own test file must prove; the fixtures in
formal/crc32_formal_unit_test.sv have known results, and every counterexample
is checked against zlib, which knows nothing of our pipeline.
"""
from __future__ import annotations

import json
import os
import shutil
import zlib
from pathlib import Path

import pytest

from fw.hdl.formal import prove

_ROOT = Path(__file__).resolve().parents[2]
_CRC = _ROOT / "examples" / "xls" / "crc32"
_FIXTURES = Path(__file__).resolve().parent / "formal" / "crc32_formal_unit_test.sv"


def _solvers():
    out = []
    dvs = os.environ.get("DV_SOLVE_SMT2") or shutil.which("dv-solve-smt2")
    if dvs is None:
        cand = Path.home() / "projects" / "fvutils" / "dv-solve" / "build" / "dv-solve-smt2"
        dvs = str(cand) if cand.is_file() else None
    out.append(pytest.param(
        [dvs, "--engine=bitblast"] if dvs else None, id="dv-solve",
        marks=[] if dvs else pytest.mark.skip(reason="dv-solve-smt2 not found")))
    for name, cmd in (("z3", ["z3", "-smt2"]), ("boolector", ["boolector", "--smt2"])):
        exe = shutil.which(cmd[0]) or (str(_ROOT / "packages" / "yosys" / "bin" / cmd[0])
                                        if (_ROOT / "packages" / "yosys" / "bin" / cmd[0]).is_file()
                                        else None)
        out.append(pytest.param([exe] + cmd[1:] if exe else None, id=name,
                                marks=[] if exe else pytest.mark.skip(reason=f"{name} not found")))
    return out


@pytest.fixture(params=_solvers())
def solver(request):
    return prove.Solver(request.param, timeout=120)


def _prove(tmp_path, design, test_file, solver, **kw):
    api, pkg = prove.make_api([str(design)], ["crc32_pkg::main"], str(tmp_path))
    return {r.test: r for r in prove.prove_files(
        [str(design), pkg, str(test_file)], api=api, solver=solver, workdir=str(tmp_path),
        **kw)}


def _crc(m: int) -> int:
    return zlib.crc32(bytes([m]))


def test_crc32_example_proves(tmp_path, solver):
    """The example's test file, unchanged, proves: each test for every input."""
    rs = _prove(tmp_path, _CRC / "crc32_pkg.sv", _CRC / "crc32_unit_test.sv", solver)
    assert {n: r.status for n, r in rs.items()} == {
        "crc32_one_char": "proven", "crc32_affine": "proven",
        "crc32_printable_nonzero": "proven", "crc32_alpha_distinct": "proven"}


def test_fixtures(tmp_path, solver):
    rs = _prove(tmp_path, _CRC / "crc32_pkg.sv", _FIXTURES, solver)
    status = {n: r.status for n, r in rs.items()}
    assert status == {
        "f_one_char_collides": "counterexample", "p_one_char_excluded": "proven",
        "v_contradiction": "vacuous", "f_second_check": "counterexample",
        "f_fatal": "counterexample", "p_class_inherited": "proven",
        "f_class_edge": "counterexample", "p_class_override": "proven",
        "p_dist": "proven", "p_implication": "proven",
        "n_carried": "not-formal", "n_for_loop": "not-formal"}

    def value(r, name="m"):
        (site,) = r.inputs
        return {v["name"]: v["value"] for v in site["vars"]}[name]

    def line(text):
        return 1 + _FIXTURES.read_text().splitlines().index(
            next(x for x in _FIXTURES.read_text().splitlines() if text in x))

    r = rs["f_one_char_collides"]
    assert _crc(value(r)) == 0x83DCEFB7 and r.obligation.kind == "fail_if"
    assert r.obligation.line == line("`FAIL_IF(crc == 32'h83DCEFB7)")
    assert Path(r.obligation.file).resolve() == _FIXTURES

    # The first check holds for every input; the second fails, and only past '7'.
    r = rs["f_second_check"]
    m = value(r)
    assert 0x38 <= m <= 0x39 and _crc(m) & 1 == 1
    assert r.obligation.kind == "fail_unless" and r.obligation.line == line("crc[0] == 1'b0")

    r = rs["f_fatal"]
    assert _crc(value(r)) == 0x83DCEFB7 and r.obligation.kind == "$fatal"

    assert value(rs["f_class_edge"], "s.m") == 0x5A

    assert "'prev' is carried" in rs["n_carried"].message
    assert "for/while loop" in rs["n_for_loop"].message

    # A counterexample is written as a replay file: randomize() values in order.
    cex = json.loads((tmp_path / "f_one_char_collides.cex.json").read_text())
    assert cex["format"] == "fw.hdl.formal-cex"
    assert cex["randomize"][0]["vars"] == [
        {"name": "m", "width": 8, "signed": False, "value": 0x31}]


def test_mutant_design(tmp_path, solver):
    """A wrong polynomial: the directed test finds it, with the input it uses.
    The affine property holds for any polynomial, so it still proves -- a
    property proves only what it says."""
    src = (_CRC / "crc32_pkg.sv").read_text()
    assert "32'hEDB88320" in src
    mutant = tmp_path / "crc32_pkg.sv"
    mutant.write_text(src.replace("32'hEDB88320", "32'hEDB88321"))
    rs = _prove(tmp_path, mutant, _CRC / "crc32_unit_test.sv", solver,
                tests=["crc32_one_char", "crc32_affine"])
    assert rs["crc32_one_char"].status == "counterexample"
    assert rs["crc32_one_char"].inputs == []          # no free inputs: evaluation
    assert rs["crc32_affine"].status == "proven"


# ---------------------------------------------------------------------------
# F4: a counterexample replayed as a directed run of the same test file.
# ---------------------------------------------------------------------------
def test_replay_keeps_lines(tmp_path):
    """The replay of a call that spans lines keeps every later line's number,
    and names the original file for the simulator's messages."""
    from fw.hdl.formal import replay
    src = _FIXTURES.read_text()
    call = "std::randomize(a, b)"
    start = src.index(call)
    line = src[:start].count("\n") + 1
    cex = {"format": replay.FORMAT, "test": "p_implication", "randomize": [{
        "site": 0, "file": str(_FIXTURES), "line": line, "start": start,
        "end": start + len(call), "vars": [
            {"name": "a", "width": 8, "signed": False, "value": 0x11},
            {"name": "b", "width": 8, "signed": False, "value": 0x1}]}]}
    out = replay.replay_source(str(_FIXTURES), [cex]).splitlines()
    assert out[0] == f'`line 1 "{_FIXTURES}" 0'
    body, orig = out[1:], src.splitlines()
    # The with clause's second line is empty but for what followed the call.
    assert body[line - 1].strip() == "`FAIL_UNLESS(__fw_replay_p_implication_0(a, b)"
    assert body[line].strip() == ")"
    n = len(orig) - 1                                  # endmodule
    assert body[line + 1:n] == orig[line + 1:n]
    fn = "\n".join(body[n:])
    assert "function automatic bit __fw_replay_p_implication_0(output bit [7:0] v0, " \
           "output bit [7:0] v1);" in fn and "v0 = 8'h11; v1 = 8'h1;" in fn


_E2E_FLOW = """\
package:
  name: formal_e2e
  imports: [hdlsim, hdlsim.vlt, hdltest.svunit, synth.xls, fw.hdl.xls, fw.hdl.api, fw.hdl.formal]
  tasks:
  - name: svunit
    uses: hdltest.svunit.Lib
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {crc}, include: [crc32_pkg.sv]}}
  - name: unit-tests
    uses: std.FileSet
    with: {{type: svunitTest, base: {fixtures}, include: [crc32_formal_unit_test.sv]}}
  - name: api
    uses: fw.hdl.api.Functions
    needs: [src]
    with: {{functions: [crc32_pkg::main]}}
  - name: prove
    uses: fw.hdl.formal.Prove
    needs: [svunit, src, api, unit-tests]
    with: {{solver: "{solver}", name: fixtures-formal}}
  - name: replay
    uses: fw.hdl.formal.Replay
    needs: [unit-tests, prove]
    with: {{tests: [f_one_char_collides, f_second_check, f_class_edge]}}
  - name: runner
    uses: hdltest.svunit.TestRunner
    needs: [replay]
    with: {{harness: [crc32_pkg_api_harness]}}
  # level model
  - name: dut-model
    uses: fw.hdl.api.ModelBinding
    needs: [api]
  - name: img-model
    uses: hdlsim.vlt.SimImage
    needs: [svunit, src, api, dut-model, runner]
    with: {{top: [testrunner]}}
  - name: run-model
    uses: hdlsim.vlt.SimRun
    needs: [img-model, replay]
    with: {{mode: test}}
  - name: check-model
    uses: hdltest.svunit.Check
    needs: [run-model]
    with: {{name: replay-model}}
  # level rtl
  - name: ir
    uses: fw.hdl.xls.IR
    needs: [src]
    with: {{top: [crc32_pkg::main]}}
  - name: rtl
    uses: synth.xls.Codegen
    needs: [ir]
    with: {{pipeline_stages: 2, input_valid_signal: input_valid, output_valid_signal: output_valid}}
  - name: bind-rtl
    uses: fw.hdl.api.XlsBinding
    needs: [api, rtl]
  - name: img-rtl
    uses: hdlsim.vlt.SimImage
    needs: [svunit, src, api, rtl, bind-rtl, runner]
    with: {{top: [testrunner]}}
  - name: run-rtl
    uses: hdlsim.vlt.SimRun
    needs: [img-rtl, replay]
    with: {{mode: test}}
  - name: check-rtl
    uses: hdltest.svunit.Check
    needs: [run-rtl]
    with: {{name: replay-rtl}}
"""


def _e2e_solver():
    for name in ("boolector", "z3"):
        if shutil.which(name) or (_ROOT / "packages" / "yosys" / "bin" / name).is_file():
            return name
    return None


@pytest.mark.verilator
@pytest.mark.skipif(_e2e_solver() is None, reason="needs boolector or z3")
def test_flow_prove_and_replay(tmp_path):
    """Through dv-flow: fw.hdl.formal.Prove on the fixtures, then Replay of
    three counterexamples, run by Verilator at level model and, with XLS, at
    level rtl. Each replayed test fails at the line Prove reported."""
    import subprocess
    from zuspec.be.xls.testing.xlstools import codegen_main, opt_main
    (tmp_path / "flow.yaml").write_text(_E2E_FLOW.format(
        crc=_CRC, fixtures=_FIXTURES.parent, solver=_e2e_solver()))
    levels = ["model"] + (["rtl"] if codegen_main() and opt_main() else [])
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(_ROOT / "packages" / "yosys" / "bin"),
                                   env.get("PATH", "")])
    if codegen_main():
        env["PATH"] = os.path.dirname(codegen_main()) + os.pathsep + env["PATH"]
    dfm = _ROOT / "packages" / "python" / "bin" / "dfm"
    for lv in levels:                  # one task per dfm run; the second reuses the first
        r = subprocess.run([str(dfm), "run", f"check-{lv}"], cwd=tmp_path, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]

    rd = tmp_path / "rundir"
    data = json.loads((rd / "formal_e2e.prove" / "formal_e2e.prove.exec_data.json").read_text())
    (tr,) = [o for o in data["output"]["output"] if o.get("type") == "hdlsim.TestResult"]
    assert tr["status"] == "fail" and not tr["passed"]
    assert {k: tr["stats"][k] for k in ("tests_proven", "tests_counterexample",
                                        "tests_vacuous", "tests_not_formal")} == {
        "tests_proven": 5, "tests_counterexample": 4, "tests_vacuous": 1,
        "tests_not_formal": 2}
    results = {x["test"]: x for x in json.loads(
        (rd / "formal_e2e.prove" / "results.json").read_text())["results"]}

    for lv in levels:
        log = (rd / f"formal_e2e.run-{lv}" / "sim.log").read_text()
        for t in ("f_one_char_collides", "f_second_check", "f_class_edge"):
            o = results[t]["obligation"]
            assert f"replay {t} line" in log, (lv, t)
            assert f"(at {o['file']} line:{o['line']})" in log, (lv, t)
            assert f"{t}::FAILED" in log, (lv, t)
        assert "FAILED (0 of 3 tests passing)" in log, lv    # the filter: only these
