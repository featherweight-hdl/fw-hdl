"""M8: formal proof of the generated regblock's contract (SymbiYosys / BMC).

A compact block covering every field profile is emitted with embedded, mask-driven
SVA, and SymbiYosys proves the register contract holds for *all* legal input
sequences: software write to a RO field never changes it, a hardware write wins
over a concurrent software write, a read-clear field clears only on an accepted
read, and decode does not alias registers.
"""
import os
import subprocess
from pathlib import Path

import pytest

from fw.hdl.emit.regblock import emit_regblock
from fw.hdl.regmap import RegBlock, Register, RegField

REPO = Path(__file__).resolve().parents[3]
YOSYS_BIN = REPO / "packages" / "yosys" / "bin"
SBY = YOSYS_BIN / "sby"


def _block():
    ctrl = Register("ctrl", 0x0, 32, sw_wmask=0x1, fields=[
        RegField("cfg", 0, 1, sw_write=True, hw_write=False, rclr=False)])      # config
    stat = Register("stat", 0x4, 32, hw_wmask=0x3, rclr_mask=0x2, fields=[
        RegField("ro",  0, 1, sw_write=False, hw_write=True, rclr=False),       # RO
        RegField("irq", 1, 1, sw_write=False, hw_write=True, rclr=True)])       # sticky
    mix = Register("mix", 0x8, 32, sw_wmask=0x1, hw_wmask=0x1, fields=[
        RegField("ov", 0, 1, sw_write=True, hw_write=True, rclr=False)])        # overlap
    return RegBlock("fv_dev", registers=[ctrl, stat, mix], size=0xc)


_SBY = """[options]
mode bmc
depth 10

[engines]
smtbmc boolector

[script]
read_verilog -sv -formal {rb}
prep -top fv_dev_regblock
"""
# `-formal` is essential: it defines the FORMAL macro (enabling the `ifdef FORMAL`
# SVA) -- without it the proof would be vacuous (no properties, always passes).


def _run_sby(tmp_path, sv_text, name):
    (tmp_path / f"{name}.sv").write_text(sv_text)
    (tmp_path / f"{name}.sby").write_text(_SBY.format(rb=tmp_path / f"{name}.sv"))
    env = dict(os.environ, PATH=f"{YOSYS_BIN}:{os.environ['PATH']}")
    # sby's `env python3` may resolve to a click-less interpreter; run it under a
    # python that has click (system python3 here), with yosys/boolector on PATH.
    return subprocess.run(
        ["/usr/bin/python3", str(SBY), "-f", f"{name}.sby"],
        cwd=tmp_path, env=env, capture_output=True, text=True).stdout


@pytest.mark.skipif(not SBY.exists(), reason="sby not available")
def test_regblock_contract_formal(tmp_path):
    sv = emit_regblock(_block(), formal=True)
    out = _run_sby(tmp_path, sv, "rb")
    assert "DONE (PASS" in out, out


@pytest.mark.skipif(not SBY.exists(), reason="sby not available")
def test_formal_has_teeth(tmp_path):
    """Guard against a vacuous proof: a tampered RTL where software can write a RO
    field must be caught by the embedded contract (RO immutability)."""
    sv = emit_regblock(_block(), formal=True)
    bad = sv.replace(
        "    if (reset) field_stat__ro <= 1'h0;",
        "    if (reset) field_stat__ro <= 1'h0;\n"
        "    else if ((reg_sel == 2'd1) && s_wr) field_stat__ro <= s_wdata[0:0];")
    assert bad != sv, "tamper did not apply"
    out = _run_sby(tmp_path, bad, "bad")
    assert "DONE (FAIL" in out, out
