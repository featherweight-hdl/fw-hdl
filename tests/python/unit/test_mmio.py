"""F-A1 / F-A2: MMIO-driven FSM recognition and run-body lowering.

A runnable fw_component that uses a register block (mmio_fsm) is recognized, its
RegBlock + RegUsage attached (F-A1), and its run body lowered to an FSM SPL + a
wiring spec (F-A2): a wait_until(set_changed) beat, injected pins, and per-field
hwif update drives tagged Mealy.  The wiring spec must match the regblock's actual
ports (the contract the structural top assembly relies on)."""
import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.mmio import build_mmio_components
from fw.hdl.fe.reg_mapper import build_reg_blocks
from fw.hdl.fe.reg_consumer import analyze_consumer
from fw.hdl.emit.regblock import emit_regblock


def _components(files):
    rep = ErrorReporter()
    comps = build_mmio_components(files, FlowConfig(), rep)
    assert not rep.has_errors(), rep.report()
    return comps


# -- F-A1: recognition --------------------------------------------------------
def test_mmio_component_recognized_with_block_and_usage(mmio_files):
    comps = _components(mmio_files)
    assert list(comps) == ["mmio_fsm"]
    m = comps["mmio_fsm"]
    assert m.regs_member == "m_regs"
    # block: ctrl@0x0 (sw go), status@0x4 (hw flag)
    offs = {q: off for (off, q, _r) in m.block.flat_registers()}
    assert offs == {"ctrl": 0x0, "status": 0x4}
    # usage: a single watch-set over CTRL
    assert m.usage.change_sets == {"m_set": [0x0]}
    assert m.usage.observers == [] and m.usage.providers == []


# -- F-A2: FSM SPL ------------------------------------------------------------
def test_mmio_spl_injected_pins(mmio_files):
    spl = _components(mmio_files)["mmio_fsm"].spl
    byname = {f.name: f for f in spl.fields}
    # clock/reset with role tags
    assert byname["clock"].pragmas.get("fw_role") == "clock"
    assert byname["reset"].pragmas.get("fw_role") == "reset"
    # the watch-set change input
    sc = byname["m_set_changed"]
    assert isinstance(sc, ir.FieldInOut) and not sc.is_out
    # per-field hwif update outputs, tagged Mealy (one-cycle we pulse, D1)
    for pin, w in (("hwif_in_status__flag_next", 1), ("hwif_in_status__flag_we", 1)):
        f = byname[pin]
        assert isinstance(f, ir.FieldInOut) and f.is_out
        assert f.datatype.bits == w and f.pragmas.get("fw_mealy") is True
    # no spurious drive for the reserved field
    assert "hwif_in_status__rsvd_we" not in byname


def test_mmio_spl_run_is_wait_then_drives(mmio_files):
    spl = _components(mmio_files)["mmio_fsm"].spl
    idx = {f.name: i for i, f in enumerate(spl.fields)}
    body = spl.proc_processes[0].body
    assert len(body) == 1 and isinstance(body[0], ir.StmtWhile)
    loop = body[0].body
    # forever { wait_until(set_changed); next=1; we=1 }
    assert isinstance(loop[0], ir.StmtExpr) and isinstance(loop[0].expr, ir.ExprAwait)
    call = loop[0].expr.value
    assert call.func.attr == "wait_until"
    assert call.args[0].index == idx["m_set_changed"]
    drives = {s.targets[0].index: s.value.value for s in loop[1:]}
    assert drives == {idx["hwif_in_status__flag_next"]: 1,
                      idx["hwif_in_status__flag_we"]: 1}


# -- F-A2: wiring spec matches the regblock ports -----------------------------
def test_wiring_spec_matches_regblock_ports(mmio_files):
    rep = ErrorReporter()
    m = _components(mmio_files)["mmio_fsm"]
    blks = build_reg_blocks(mmio_files, FlowConfig(), rep)
    usage = analyze_consumer(mmio_files, "mmio_fsm", FlowConfig(), rep)
    sv = emit_regblock(blks["mmio_regs"], usage=usage)

    w = m.wiring
    assert w.component_module == "mmio_fsm"
    assert w.regblock_module == "mmio_regs_regblock"
    assert w.shared == ["clock", "reset"]
    # every connection's regblock_port must be a real port, with matching direction
    for c in w.connections:
        if c.direction == "out":
            assert f"input  logic [{c.width-1}:0] {c.regblock_port}" in sv \
                or f"input  logic            {c.regblock_port}" in sv, c.regblock_port
        else:
            assert f"output logic            {c.regblock_port}" in sv \
                or f"output logic [{c.width-1}:0] {c.regblock_port}" in sv, c.regblock_port
    # the three expected nets: set-change in, flag next/we out
    by_pin = {c.pin: c.direction for c in w.connections}
    assert by_pin == {"m_set_changed": "in",
                      "hwif_in_status__flag_next": "out",
                      "hwif_in_status__flag_we": "out"}
