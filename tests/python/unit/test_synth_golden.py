"""P3: full-flow golden — generated blinky RTL matches the checked-in golden.

Set ``FW_UPDATE_GOLDEN=1`` to rewrite the golden on an intentional change.
"""
import os
from pathlib import Path

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl import flow

GOLDEN = Path(__file__).parent / "golden" / "blinky.rtl.sv"


def _synth(blinky_files) -> str:
    reporter = ErrorReporter()
    cfg = FlowConfig(top="blinky", top_module="blinky_top")
    result = flow.synth(blinky_files, cfg, reporter)
    assert result is not None, reporter.report()
    sv = result.sv
    return sv if sv.endswith("\n") else sv + "\n"


def test_blinky_rtl_matches_golden(blinky_files):
    sv = _synth(blinky_files)
    if os.environ.get("FW_UPDATE_GOLDEN") or not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(sv)
    assert sv == GOLDEN.read_text(), (
        "generated RTL differs from golden; set FW_UPDATE_GOLDEN=1 if intended")
