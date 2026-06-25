"""System tests — the *behavioral* proof, automated.

The unit suite verifies the generated RTL's structure/text; these verify it is
**synthesizable** (Verilator compiles it) and **correct** (it passes the
unmodified ``tests/blinky/blinky_tb.sv``).  Both front ends — fw-hdl SV and
zuspec-dataclasses Python — go through the same `zuspec.synth.spl` lowering, so a
PASS from each is the end-to-end multi-language proof.

Skipped when Verilator is not installed.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

requires_verilator = pytest.mark.skipif(
    shutil.which("verilator") is None, reason="verilator not installed")

_LED_T_STUB = "package blinky_pkg;\n  typedef logic led_t;\nendpackage\n"


def _lint(sv_text: str, work: Path) -> None:
    """Verilator --lint-only as a strict synthesizability check."""
    work.mkdir(parents=True, exist_ok=True)
    f = work / "blinky.sv"
    f.write_text(sv_text)
    r = subprocess.run(["verilator", "--lint-only", "-Wall", str(f)],
                       cwd=work, capture_output=True, text=True)
    assert r.returncode == 0, f"lint failed:\n{r.stdout}\n{r.stderr}"


def _run_blinky_tb(sv_text: str, blinky_dir: Path, work: Path) -> str:
    """Compile the generated RTL (renamed to blinky_top) + the real TB, run it."""
    work.mkdir(parents=True, exist_ok=True)
    (work / "blinky_top.sv").write_text(sv_text.replace("module blinky(", "module blinky_top("))
    (work / "blinky_pkg_stub.sv").write_text(_LED_T_STUB)
    (work / "blinky_tb.sv").write_text((blinky_dir / "blinky_tb.sv").read_text())
    build = subprocess.run(
        ["verilator", "--binary", "--timing", "-Wno-DECLFILENAME", "-Wno-WIDTH",
         "--top-module", "blinky_tb",
         "blinky_pkg_stub.sv", "blinky_top.sv", "blinky_tb.sv", "-o", "sim"],
        cwd=work, capture_output=True, text=True)
    assert build.returncode == 0, f"verilate failed:\n{build.stderr[-3000:]}"
    run = subprocess.run([str(work / "obj_dir" / "sim")],
                         cwd=work, capture_output=True, text=True)
    return run.stdout + run.stderr


def _fwhdl_blinky_sv(blinky_files):
    from fw.hdl.config import FlowConfig
    from fw.hdl.errors import ErrorReporter
    from fw.hdl import flow
    rep = ErrorReporter()
    cfg = FlowConfig(top="blinky", top_module="blinky_top")
    res = flow.synth(blinky_files, cfg, rep)
    assert res is not None, rep.report()
    return res.sv


def _zdc_blinky_sv():
    import zuspec.dataclasses as zdc
    import zuspec.synth.spl as spl
    from zuspec.be.sv import SVGenerator
    import tempfile
    from _zdc_blinky import blinky
    rtl = spl.lower_context(zdc.DataModelFactory().build(blinky))
    return SVGenerator(Path(tempfile.mkdtemp())).generate(rtl)[0].read_text()


@requires_verilator
def test_fwhdl_blinky_lints_and_passes_tb(blinky_files, blinky_dir, tmp_path):
    sv = _fwhdl_blinky_sv(blinky_files)
    _lint(sv, tmp_path / "lint")
    out = _run_blinky_tb(sv, blinky_dir, tmp_path / "sim")
    assert "[blinky] PASS" in out, out


@requires_verilator
def test_zdc_blinky_lints_and_passes_tb(blinky_dir, tmp_path):
    # second front end, SAME lowering — proves language-independence end-to-end
    sv = _zdc_blinky_sv()
    _lint(sv, tmp_path / "lint")
    out = _run_blinky_tb(sv, blinky_dir, tmp_path / "sim")
    assert "[blinky] PASS" in out, out
