"""F-A3: the update->hwif Mealy pulse (D1).

The register-update drives lower to a *combinational* process so the hwif `we` is
high for exactly one cycle (the cycle the watched change pulse arrives), not a
registered output that would stay asserted.  The minimal wait+update FSM has no
registered state at all, so it lowers to a pure-comb module."""
import zuspec.ir.core as ir

from fw.hdl import ir_build as b
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.mmio import build_mmio_components
from fw.hdl.lower.spl2rtl import lower_component
from fw.hdl.emit.be_sv import emit_sv


def _fsm_rtl(files):
    rep = ErrorReporter()
    spl = build_mmio_components(files, FlowConfig(), rep)["mmio_fsm"].spl
    rtl = lower_component(spl, FlowConfig(), rep)
    assert rtl is not None and not rep.has_errors(), rep.report()
    return rtl


def test_mealy_drives_are_combinational(mmio_files):
    rtl = _fsm_rtl(mmio_files)
    # the update drives go into a comb process, never the (absent) sync process
    assert len(rtl.comb_processes) == 1
    assert rtl.sync_processes == []           # no registered state -> pure comb
    body = rtl.comb_processes[0].body
    names = {f.name: i for i, f in enumerate(rtl.fields)}
    we = names["hwif_in_status__flag_we"]
    nxt = names["hwif_in_status__flag_next"]
    # defaults: both Mealy outputs driven low first
    defaults = {s.targets[0].index: s.value.value
                for s in body if isinstance(s, ir.StmtAssign)}
    assert defaults == {nxt: 0, we: 0}
    # then, gated by set_changed, both asserted
    guarded = [s for s in body if isinstance(s, ir.StmtIf)]
    assert len(guarded) == 1
    gate = guarded[0]
    assert gate.test.index == names["m_set_changed"]
    fired = {s.targets[0].index: s.value.value for s in gate.body}
    assert fired == {nxt: 1, we: 1}


def test_mealy_outputs_not_in_reset(mmio_files):
    """A Mealy output must not be registered/reset (no sync driver) — that would be
    a multiple-driver conflict with the comb process."""
    rtl = _fsm_rtl(mmio_files)
    sv = emit_sv(b.context([rtl]))
    assert "always @(*)" in sv
    assert "always @(posedge" not in sv            # nothing clocked here
    # the one-cycle pulse shape is present
    assert "hwif_in_status__flag_we = 0" in sv
    assert "if (m_set_changed)" in sv
    assert "hwif_in_status__flag_we = 1" in sv
