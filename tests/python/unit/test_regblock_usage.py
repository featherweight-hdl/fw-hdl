"""M7: usage-driven emission — the watch-set change pulse and observer strobes.

The change pulse wakes the arbiter on SOFTWARE writes to set members only: the
engine drives the members' hardware side itself, so ORing its own hw updates would
just self-wake (register-model-rtl-lowering.md §9.4)."""
import re

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_consumer import analyze_consumer
from fw.hdl.fe.reg_mapper import build_reg_blocks
from fw.hdl.emit.regblock import emit_regblock
from fw.hdl.regmap import RegUsage


def test_set_changed_is_software_write_only(reg_dma_files):
    rep = ErrorReporter()
    usage = analyze_consumer(reg_dma_files, "dma_engine", FlowConfig(), rep)
    top = build_reg_blocks(reg_dma_files, FlowConfig(), rep)["dma_regs"]
    assert not rep.has_errors(), rep.report()
    sv = emit_regblock(top, usage=usage)

    assert "output logic            m_csrs_changed" in sv
    expr = re.search(r"assign m_csrs_changed = (.*?);", sv, re.S).group(1)
    # one software-write term per member CSR (31 channels), OR'd — and crucially
    # NO hardware-write strobes (those would be engine self-wakes).
    assert expr.count("&& s_wr") == 31
    assert expr.count("||") == 30
    assert "hwif_in" not in expr and "_we" not in expr


def test_observer_emits_software_write_strobe(reg_dma_files):
    rep = ErrorReporter()
    ch = build_reg_blocks(reg_dma_files, FlowConfig(), rep)["dma_channel_regs"]
    # csr is at offset 0 (reg_sel == 0) in the channel block
    sv = emit_regblock(ch, usage=RegUsage(observers=[0x00]))
    assert "output logic            csr__sw_wstrobe" in sv
    assert "assign csr__sw_wstrobe = ((reg_sel == 3'd0) && s_wr);" in sv


def test_no_usage_emits_no_consumer_signals(reg_dma_files):
    rep = ErrorReporter()
    ch = build_reg_blocks(reg_dma_files, FlowConfig(), rep)["dma_channel_regs"]
    sv = emit_regblock(ch)                       # usage=None
    assert "_changed" not in sv and "_sw_wstrobe" not in sv
