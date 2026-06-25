"""C2: the multi-language proof — the SAME centralized lowering
(``zuspec.synth.spl``) lowers a zuspec-dataclasses (@zdc) front end to correct
RTL, using NO fw-hdl code.  Together with the fw-hdl golden test, this shows
language lives in the front end and hardware in the shared middle.
"""
import zuspec.dataclasses as zdc
import zuspec.ir.core as ir
import zuspec.synth.spl as spl

from _zdc_blinky import blinky


def _rtl_component():
    spl_ctxt = zdc.DataModelFactory().build(blinky)        # @zdc → SPL ir.core
    rtl = spl.lower_context(spl_ctxt)                       # shared lowering
    return next(v for v in rtl.type_m.values()
                if isinstance(v, ir.DataTypeComponent))


def test_zdc_blinky_lowers_via_shared_lowering():
    comp = _rtl_component()
    names = {f.name for f in comp.fields}
    assert {"clock", "reset", "led", "count"} <= names
    # honours the RTL contract (no internal-reg FieldInOut, no ExprBin compares)
    assert spl.builders.validate_rtl_component(comp) == []
    assert len(comp.sync_processes) == 1


def test_zdc_blinky_clock_reset_from_metadata():
    # the @zdc front end carries clock/reset in Function.metadata (the standard);
    # the shared lowering resolves them without any fw-hdl pragmas.
    comp = _rtl_component()
    proc = comp.sync_processes[0]
    assert isinstance(proc.metadata["clock"], ir.ExprRefField)
    assert isinstance(proc.metadata["reset"], ir.ExprRefField)


def test_zdc_blinky_emits_synthesizable_sv():
    from pathlib import Path
    import tempfile
    from zuspec.be.sv import SVGenerator
    spl_ctxt = zdc.DataModelFactory().build(blinky)
    rtl = spl.lower_context(spl_ctxt)
    sv = SVGenerator(Path(tempfile.mkdtemp())).generate(rtl)[0].read_text()
    assert "module blinky(" in sv
    assert "output logic led" in sv
    assert "logic [7:0] count" in sv          # down-counter (cycles(100))
    assert "led <= ~led" in sv                # toggle
    assert "count[7]" in sv                   # underflow terminal
    assert "count == 99" not in sv            # no wide comparator
