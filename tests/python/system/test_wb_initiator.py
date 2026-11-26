"""The Wishbone initiator in Pattern 1 (sync-task-domains.md X7):
examples/wb_initiator. test_sim runs its bench under Verilator: §4's table
with back-to-back accesses, random wait states and gaps, and a mutant the
table check must catch. test_lower_equiv lowers the sync core, checks the
checked-in rtl/gen/wb_init_core.sv is current, and proves it equivalent to
fw-proto-wb's wb_initiator_xtor_core (vendored in ref/), unbounded.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_EX = Path(__file__).resolve().parents[3] / "examples" / "wb_initiator"


def _sh(tmp_path, script, *args):
    r = subprocess.run(["sh", f"scripts/{script}", *args], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout + r.stderr


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_sim(tmp_path):
    rc, out = _sh(tmp_path, "run_sim.sh")
    assert rc == 0, out[-3000:]
    assert "PASS: wb_init: 12 accesses in 24 edges" in out, out[-3000:]
    assert "PASS: wb_init +rand: 12 accesses" in out, out[-3000:]
    assert "FAIL: wb_init: access 0: called 0, returned 3" in out, out[-3000:]


@pytest.mark.skipif(shutil.which("yosys") is None or shutil.which("sv2v") is None,
                    reason="yosys or sv2v not installed")
def test_lower_equiv(tmp_path):
    from fw.hdl.emit.sync import emit_sync
    root = _EX.parents[1]
    files = [f"{root}/src/fw_clock_xtor_if.sv", f"{root}/src/fw_clock_period_xtor_if.sv",
             f"{root}/src/fw_hdl_pkg.sv", f"{_EX}/ref/wb_types_pkg.sv",
             f"{_EX}/src/wb_init_core_pkg.sv", f"{_EX}/rtl/wb_init_emit_top.sv"]
    text = emit_sync(files, "wb_init_emit_top", incdirs=[f"{root}/src", f"{_EX}/src"],
                     parameterized=True)["core"]
    checked_in = (_EX / "rtl" / "gen" / "wb_init_core.sv").read_text()
    assert checked_in.split("\n", 1)[1] == text, "rtl/gen/wb_init_core.sv is stale: run scripts/gen_rtl.py"
    gen = tmp_path / "wb_init_core.sv"
    gen.write_text(text)
    rc, out = _sh(tmp_path, "equiv.sh", str(gen))
    assert rc == 0 and "proven (unbounded)" in out, out[-3000:]
