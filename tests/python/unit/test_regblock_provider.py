"""M8b: provider storage-elimination (RO-reflect).

A register with a read provider is reflected: its readback is the provider's
whole-word output and its hw-only fields lose their flops. rclr + a provider are
mutually exclusive (register-model-design.md §3), so a register with any
read-clear field is left as storage (and noted)."""
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_mapper import build_reg_blocks
from fw.hdl.emit.regblock import emit_regblock, flop_bits
from fw.hdl.regmap import RegBlock, Register, RegField, RegUsage


def _clean_block():
    """ctrl (sw RW) + status (hw-only: flag + code) — a clean provider candidate."""
    ctrl = Register("ctrl", 0x0, 32, sw_wmask=0x1, fields=[
        RegField("en", 0, 1, sw_write=True, hw_write=False, rclr=False)])
    status = Register("status", 0x4, 32, hw_wmask=0xff, fields=[
        RegField("flag", 0, 1, sw_write=False, hw_write=True, rclr=False),
        RegField("code", 1, 7, sw_write=False, hw_write=True, rclr=False)])
    return RegBlock("dev", registers=[ctrl, status], size=0x8)


def test_provider_register_reflects_and_drops_storage():
    blk = _clean_block()
    base = flop_bits(blk)                            # 1 (en) + 8 (flag+code) = 9
    sv = emit_regblock(blk, usage=RegUsage(providers=[0x4]))
    assert "input  logic [31:0] hwif_in_status_rdata" in sv   # whole-word provider
    assert "field_status__flag" not in sv and "field_status__code" not in sv
    assert "s_rdata = hwif_in_status_rdata;" in sv            # readback = provider
    assert "field_ctrl__en" in sv                            # sw register untouched
    assert flop_bits(blk, providers=[0x4]) == base - 8       # 8 hw-only bits gone


def test_rclr_register_is_not_reflected():
    sticky = Register("status", 0x0, 32, hw_wmask=0x1, rclr_mask=0x1, fields=[
        RegField("irq", 0, 1, sw_write=False, hw_write=True, rclr=True)])
    blk = RegBlock("dev", registers=[sticky], size=0x4)
    sv = emit_regblock(blk, usage=RegUsage(providers=[0x0]))
    assert "not reflected" in sv                     # noted, not silently ignored
    assert "field_status__irq" in sv                 # storage kept
    assert "hwif_in_status_rdata" not in sv


def test_dma_csr_with_provider_keeps_storage(reg_dma_files):
    """The DMA csr mixes read-clear int_* with reflectable status, so a provider
    on it cannot reflect — storage is preserved (matching the equivalence test)."""
    rep = ErrorReporter()
    ch = build_reg_blocks(reg_dma_files, FlowConfig(), rep)["dma_channel_regs"]
    sv = emit_regblock(ch, usage=RegUsage(providers=[0x0]))
    assert "not reflected" in sv
    assert flop_bits(ch, providers=[0x0]) == 247
