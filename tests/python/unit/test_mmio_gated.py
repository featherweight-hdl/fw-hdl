"""read() + conditional (if) update in an MMIO FSM.

`if (m_regs.<reg>.read().<field>) <update>` maps the read to a `hwif_out` input
the regblock drives, and the `if` gates the Mealy drives.  Because the readback is
a registered value, the lowering registers the change pulse (`armed`) and fires
the gated update the cycle after — so the read samples a settled value."""
import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.mmio import build_mmio_components
from fw.hdl.lower.spl2rtl import lower_component


def _files():
    from pathlib import Path
    d = Path(__file__).resolve().parents[2] / "mmio_gated"
    return [str(d / "mmio_gated_pkg.sv"), str(d / "mmio_gated_tb.sv")]


def _component():
    rep = ErrorReporter()
    comps = build_mmio_components(_files(), FlowConfig(), rep)
    assert not rep.has_errors(), rep.report()
    return comps["gated_fsm"]


def test_read_injects_hwif_out_input():
    m = _component()
    byname = {f.name: f for f in m.spl.fields}
    # the read of ctrl.go becomes a hwif_out input pin, tagged fw_read
    go = byname["hwif_out_ctrl__go"]
    assert isinstance(go, ir.FieldInOut) and not go.is_out
    assert go.pragmas.get("fw_read") is True
    # it is a wiring connection (regblock -> FSM)
    by_pin = {c.pin: c.direction for c in m.wiring.connections}
    assert by_pin["hwif_out_ctrl__go"] == "in"
    # the run body wraps the drives in an if(read)
    loop = m.spl.proc_processes[0].body[0].body
    cond_if = next(s for s in loop if isinstance(s, ir.StmtIf))
    assert cond_if.test.index == {f.name: i for i, f in enumerate(m.spl.fields)}["hwif_out_ctrl__go"]


def test_read_gated_update_registers_change_pulse():
    rep = ErrorReporter()
    rtl = lower_component(_component().spl, FlowConfig(), rep)
    assert rtl is not None and not rep.has_errors(), rep.report()
    names = {f.name for f in rtl.fields}
    # a registered `armed` flop is introduced (delays the change pulse a cycle)
    assert "armed" in names
    # sync process registers armed <= m_set_changed; comb gates the drive on armed
    assert len(rtl.sync_processes) == 1 and len(rtl.comb_processes) == 1
    comb = rtl.comb_processes[0].body
    idx = {f.name: i for i, f in enumerate(rtl.fields)}
    outer = next(s for s in comb if isinstance(s, ir.StmtIf))
    assert outer.test.index == idx["armed"]                 # gate on armed, not raw pulse
    inner = next(s for s in outer.body if isinstance(s, ir.StmtIf))
    assert inner.test.index == idx["hwif_out_ctrl__go"]     # then the read-gate
