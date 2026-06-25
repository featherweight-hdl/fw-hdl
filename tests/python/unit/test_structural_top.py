"""F-A4: structural top assembly via IR (Decision D2 — the IR route).

The top is a DataTypeComponent carrying ``module_instances`` (the ir-core
structural node), emitted by the same be-sv back end as the FSM — not a text
emitter.  It must expose the bus, declare the FSM<->regblock nets from the wiring
spec, and instantiate both modules with matching port maps."""
import zuspec.ir.core as ir

from fw.hdl import ir_build as b
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.mmio import build_mmio_components
from fw.hdl.emit.structural import build_top_component
from fw.hdl.emit.be_sv import emit_sv


def _component(files):
    rep = ErrorReporter()
    m = build_mmio_components(files, FlowConfig(), rep)["mmio_fsm"]
    assert not rep.has_errors(), rep.report()
    return m


def test_top_instances_and_nets(mmio_files):
    m = _component(mmio_files)
    top = build_top_component(m.block, m.usage, [("u_fsm", m.wiring)],
                              top_name="mmio_top")

    # two structural instances: regblock + FSM
    insts = {i.name: i for i in top.module_instances}
    assert set(insts) == {"u_regs", "u_fsm"}
    assert insts["u_regs"].module == "mmio_regs_regblock"
    assert insts["u_fsm"].module == "mmio_fsm"

    # internal nets: the FSM<->regblock wires + the readback hwif_out nets
    net_names = {f.name for f in top.fields if not isinstance(f, ir.FieldInOut)}
    assert {"m_set_changed", "hwif_in_status__flag_next",
            "hwif_in_status__flag_we"} <= net_names
    assert {"hwif_out_ctrl__go", "hwif_out_status__flag"} <= net_names   # readbacks

    # bus + clock/reset are ports
    port_names = {f.name for f in top.fields if isinstance(f, ir.FieldInOut)}
    assert port_names == {"clock", "reset", "s_addr", "s_wr", "s_wdata",
                          "s_rd", "s_rdata"}

    # every wiring connection appears on BOTH instances, on its regblock-port net
    rb = {pc.port: pc.signal for pc in insts["u_regs"].connections}
    fsm = {pc.port: pc.signal for pc in insts["u_fsm"].connections}
    for c in m.wiring.connections:
        assert rb[c.regblock_port] == c.regblock_port
        assert fsm[c.pin] == c.regblock_port


def test_top_emits_structural_sv(mmio_files):
    m = _component(mmio_files)
    top = build_top_component(m.block, m.usage, [("u_fsm", m.wiring)],
                              top_name="mmio_top")
    sv = emit_sv(b.context([top]))

    assert "module mmio_top(" in sv
    assert "input logic [2:0] s_addr" in sv          # AW = clog2(0x8) = 3
    assert "output logic [31:0] s_rdata" in sv       # W = 32
    assert "logic m_set_changed;" in sv              # internal net
    assert "mmio_regs_regblock u_regs (" in sv
    assert "mmio_fsm u_fsm (" in sv
    assert ".hwif_in_status__flag_we(hwif_in_status__flag_we)" in sv
    # readback outputs go to (unused) nets so the pin is connected, not empty
    assert ".hwif_out_status__flag(hwif_out_status__flag)" in sv
