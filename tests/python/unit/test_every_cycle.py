"""C4: tick(1)/cycles(1) is a pure per-cycle boundary (loop body runs every
cycle), NOT a multi-cycle wait — so it must NOT synthesize a down-counter."""
from pathlib import Path
import tempfile

import zuspec.dataclasses as zdc
import zuspec.ir.core as ir
import zuspec.synth.spl as spl
from zuspec.be.sv import SVGenerator

from _zdc_ticker import ticker


def _rtl():
    return spl.lower_context(zdc.DataModelFactory().build(ticker))


def test_no_down_counter_for_cycles1():
    comp = next(v for v in _rtl().type_m.values() if isinstance(v, ir.DataTypeComponent))
    names = {f.name for f in comp.fields}
    # only clock/reset/count — NO internal down-counter / state register
    assert names == {"clock", "reset", "count"}
    assert spl.builders.validate_rtl_component(comp) == []


def test_emits_free_running_counter():
    sv = SVGenerator(Path(tempfile.mkdtemp())).generate(_rtl())[0].read_text()
    assert "count <= (count + 1)" in sv     # increments every cycle
    assert "count[" not in sv               # no underflow-bit terminal
    assert "always @(posedge clock)" in sv
    assert "if (reset)" in sv and "count <= 0" in sv
