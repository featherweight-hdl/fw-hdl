"""P3: spl2rtl — lower bound SPL IR to RTL IR."""
import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl import ir_build as b
from fw.hdl.fe.context import build_spl_context
from fw.hdl.lower.spl2rtl import lower_context


def _rtl(blinky_files):
    reporter = ErrorReporter()
    cfg = FlowConfig(top="blinky", top_module="blinky_top")
    spl = build_spl_context(blinky_files, cfg, reporter)
    assert spl is not None, reporter.report()
    rtl = lower_context(spl, cfg, reporter)
    assert rtl is not None, reporter.report()
    return rtl.type_m["blinky"]


def test_pins_and_regs_present(blinky_files):
    comp = _rtl(blinky_files)
    names = [f.name for f in comp.fields]
    assert names[:3] == ["clock", "reset", "led"]
    assert {"v", "state", "count"} <= set(names)


def test_abstract_put_port_dropped(blinky_files):
    comp = _rtl(blinky_files)
    assert "out" not in {f.name for f in comp.fields}   # abstraction, not a pin


def test_internal_regs_are_plain_fields(blinky_files):
    comp = _rtl(blinky_files)
    by = {f.name: f for f in comp.fields}
    for nm in ("v", "state", "count"):
        assert isinstance(by[nm], ir.Field)
        assert not isinstance(by[nm], ir.FieldInOut)   # the spike trap
        assert by[nm].is_reg


def test_pins_are_fieldinout(blinky_files):
    comp = _rtl(blinky_files)
    by = {f.name: f for f in comp.fields}
    assert isinstance(by["clock"], ir.FieldInOut) and not by["clock"].is_out
    assert isinstance(by["led"], ir.FieldInOut) and by["led"].is_out


def test_two_beats_two_states(blinky_files):
    comp = _rtl(blinky_files)
    by = {f.name: f for f in comp.fields}
    assert by["state"].datatype.bits == 1   # 2 states -> 1-bit state reg


def test_tick_becomes_counter(blinky_files):
    comp = _rtl(blinky_files)
    by = {f.name: f for f in comp.fields}
    # down-counter: 7 value bits (to hold 99) + 1 underflow/borrow bit
    assert by["count"].datatype.bits == 8


def test_single_clocked_process_with_reset(blinky_files):
    comp = _rtl(blinky_files)
    assert len(comp.sync_processes) == 1
    proc = comp.sync_processes[0]
    assert isinstance(proc.metadata["clock"], ir.ExprRefField)
    assert isinstance(proc.metadata["reset"], ir.ExprRefField)


def test_rtl_honours_contract(blinky_files):
    comp = _rtl(blinky_files)
    assert b.validate_rtl_component(comp) == []
