"""Multi-FSM: several FSMs driven from one shared register model.

The design assembler emits the regblock once with the *union* of the FSMs' usages
and wires each FSM to it; watch-set names shared by multiple FSMs are qualified
per FSM instance so the regblock ports stay unique."""
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.mmio import build_mmio_components
from fw.hdl.mmio_synth import synth_mmio_design


def _files(d):
    return [str(d / "mmio_multi_pkg.sv"), str(d / "mmio_multi_tb.sv")]


def _multi_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "mmio_multi"


def test_both_fsms_recognized_on_one_model():
    rep = ErrorReporter()
    comps = build_mmio_components(_files(_multi_dir()), FlowConfig(), rep)
    assert not rep.has_errors(), rep.report()
    assert set(comps) == {"multi_fsm_a", "multi_fsm_b"}
    # both are driven by the SAME register model
    assert comps["multi_fsm_a"].block.name == comps["multi_fsm_b"].block.name == "multi_regs"
    # each watches a different control register
    assert comps["multi_fsm_a"].usage.change_sets == {"m_set": [0x0]}
    assert comps["multi_fsm_b"].usage.change_sets == {"m_set": [0x8]}


def test_design_shares_one_regblock_and_qualifies_sets():
    rep = ErrorReporter()
    d = synth_mmio_design(_files(_multi_dir()), FlowConfig(), rep, top_name="multi_top")
    assert d is not None and not rep.has_errors(), rep.report()

    # one regblock, two distinct FSM modules, one top
    assert d.regblock_module == "multi_regs_regblock"
    assert {m for m, _sv in d.fsms} == {"multi_fsm_a", "multi_fsm_b"}

    # the regblock is emitted ONCE and exposes BOTH FSMs' (qualified) change ports
    assert "output logic            u_multi_fsm_a__m_set_changed" in d.regblock_sv
    assert "output logic            u_multi_fsm_b__m_set_changed" in d.regblock_sv

    # the top instantiates the regblock once and each FSM, wiring the qualified nets
    assert d.top_sv.count("multi_regs_regblock u_regs (") == 1
    assert "multi_fsm_a u_multi_fsm_a (" in d.top_sv
    assert "multi_fsm_b u_multi_fsm_b (" in d.top_sv
    # each FSM's local m_set_changed pin connects to its own qualified net
    assert ".m_set_changed(u_multi_fsm_a__m_set_changed)" in d.top_sv
    assert ".m_set_changed(u_multi_fsm_b__m_set_changed)" in d.top_sv
