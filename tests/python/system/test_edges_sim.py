"""Edge drivers, groups and release (sync-task-domains.md §6.5, step X2a):
builds tests/edges/edges_tb.sv under Verilator and runs it. The bench checks
derived-domain phase from time 0, the group edge (a ÷2 step() reads its
source's register from before the edge), release after the update, period
edges at k * period (3.3 ns at 1 ps too), a delay ending at a period edge,
and a clock that starts at X.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from fw.hdl.fe.parser import FW_LIB_FILES, FW_LIB_INCDIRS

requires_verilator = pytest.mark.skipif(
    shutil.which("verilator") is None, reason="verilator not installed")

_EDGES = Path(__file__).resolve().parents[2] / "edges"


@requires_verilator
def test_edges(tmp_path):
    files = list(FW_LIB_FILES) + [str(_EDGES / "edges_tb.sv")]
    inc = [f"+incdir+{d}" for d in FW_LIB_INCDIRS]
    b = subprocess.run(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-lint",
                        "-Wno-style", "--timescale", "1ns/1ps", "--top-module", "edges_tb",
                        "-o", "sim", *inc, *files],
                       cwd=tmp_path, capture_output=True, text=True)
    assert b.returncode == 0, f"verilate failed:\n{b.stdout[-3000:]}\n{b.stderr[-3000:]}"
    r = subprocess.run([str(tmp_path / "obj_dir" / "sim")], cwd=tmp_path,
                       capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    assert "PASS: edges" in out, out[-3000:]
