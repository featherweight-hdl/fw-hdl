"""P2: binding elaboration — the class->module boundary."""
import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.bind.elaborate import elaborate_binding
from fw.hdl.fe.bind import protocols
from fw.hdl.fe.context import build_spl_context
from fw.hdl.fe.parser import Parser


# -- elaborator (structural extraction) --------------------------------------
def _bound(blinky_files):
    reporter = ErrorReporter()
    parser = Parser(FlowConfig(), reporter)
    assert parser.parse(blinky_files), reporter.report()
    bd = elaborate_binding(parser.get_root(), "blinky", reporter,
                           top_module="blinky_top")
    assert not reporter.has_errors(), reporter.report()
    return bd


def test_clock_reset_pins_identified(blinky_files):
    bd = _bound(blinky_files)
    assert bd.clock_pin == "clock"
    assert bd.reset_pin == "reset"


def test_put_binding_resolved_to_led(blinky_files):
    bd = _bound(blinky_files)
    assert len(bd.bindings) == 1
    b = bd.bindings[0]
    assert b.class_port == "out"
    assert b.protocol == "put"
    assert b.pin == "led"
    assert b.width == 1
    assert b.pin_dir == "output" and b.registered is True


def test_protocols_table_has_put_bridge():
    spec = protocols.lookup("fw_put_xtor_bridge")
    assert spec is not None and spec.protocol == "put" and spec.data_port == "out"
    assert protocols.lookup("not_a_bridge") is None


# -- integration: bound SPL component ----------------------------------------
def _blinky(blinky_files):
    reporter = ErrorReporter()
    cfg = FlowConfig(top="blinky", top_module="blinky_top")
    ctxt = build_spl_context(blinky_files, cfg, reporter)
    assert ctxt is not None, reporter.report()
    return ctxt.type_m["blinky"]


def test_pins_injected_as_fieldinout(blinky_files):
    comp = _blinky(blinky_files)
    by_name = {f.name: f for f in comp.fields}
    for name, is_out in (("clock", False), ("reset", False), ("led", True)):
        f = by_name[name]
        assert isinstance(f, ir.FieldInOut)
        assert f.is_out is is_out


def test_clock_reset_pins_tagged(blinky_files):
    comp = _blinky(blinky_files)
    by_name = {f.name: f for f in comp.fields}
    assert by_name["clock"].pragmas.get("fw_role") == "clock"
    assert by_name["reset"].pragmas.get("fw_role") == "reset"


def test_led_pin_links_back_to_put_port(blinky_files):
    comp = _blinky(blinky_files)
    by_name = {f.name: f for f in comp.fields}
    led = by_name["led"]
    assert led.pragmas.get("fw_role") == "pin"
    assert led.pragmas.get("fw_protocol") == "put"
    assert led.pragmas.get("fw_source_port") == "out"


def test_put_port_tagged_with_pin(blinky_files):
    comp = _blinky(blinky_files)
    out = next(f for f in comp.fields if f.name == "out")
    assert out.pragmas.get("fw_protocol") == "put"
    assert out.pragmas.get("fw_pin") == "led"


def test_existing_field_indices_preserved(blinky_files):
    # pins are appended, so the run process's refs to out(#0)/v(#1) stay valid
    comp = _blinky(blinky_files)
    assert comp.fields[0].name == "out"
    assert comp.fields[1].name == "v"
    put = comp.proc_processes[0].body[0].body[0]   # await out.t.put(v)
    receiver = put.expr.value.func.value           # out.t  -> ExprAttribute(out).value
    # the put receiver chain bottoms out at ExprRefField index 0 (out)
    base = receiver.value if isinstance(receiver, ir.ExprAttribute) else receiver
    assert isinstance(base, ir.ExprRefField) and base.index == 0
