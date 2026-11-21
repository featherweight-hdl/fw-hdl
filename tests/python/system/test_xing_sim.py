"""Crossing ports (sync-task-domains.md §6.6, step X3):
builds tests/xing/xing_tb.sv under Verilator and runs it. The bench checks
that task code at an edge reads the value from before it and that its
writes land at once (C2, C3), FW-E-XING-DRIVE-TWICE (C5), and a step()'s
default overridden by a task's put at the same edge (C5). test_rv_ep runs
tests/xing/rv_ep_tb.sv, the put and get endpoints of X4, and its mutants.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from fw.hdl.fe.parser import FW_LIB_FILES, FW_LIB_INCDIRS

requires_verilator = pytest.mark.skipif(
    shutil.which("verilator") is None, reason="verilator not installed")

_XING = Path(__file__).resolve().parents[2] / "xing"


def _build(tmp_path, top):
    files = list(FW_LIB_FILES) + [str(_XING / (top + ".sv"))]
    inc = [f"+incdir+{d}" for d in FW_LIB_INCDIRS]
    b = subprocess.run(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-lint",
                        "-Wno-style", "--timescale", "1ns/1ps", "--top-module", top,
                        "-o", "sim", *inc, *files],
                       cwd=tmp_path, capture_output=True, text=True)
    assert b.returncode == 0, f"verilate failed:\n{b.stdout[-3000:]}\n{b.stderr[-3000:]}"


def _sim(tmp_path, *args):
    r = subprocess.run([str(tmp_path / "obj_dir" / "sim"), *args], cwd=tmp_path,
                       capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    return out


@requires_verilator
def test_xing(tmp_path):
    _build(tmp_path, "xing_tb")
    out = _sim(tmp_path)
    assert "PASS: xing" in out, out[-3000:]


@requires_verilator
def test_rv_ep(tmp_path):
    _build(tmp_path, "rv_ep_tb")
    out = _sim(tmp_path)
    assert "PASS: rv_ep: 40 beats, 7 back to back" in out, out[-3000:]   # as rt-sv's rv_ep
    for m in ("+mut_put", "+mut_get"):
        out = _sim(tmp_path, m)
        assert "FAIL: rv_ep" in out and "(C5 default)" in out, (m, out[-3000:])
