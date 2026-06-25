"""M6: regblock RTL emission — structural assertions on the generated core.

Every assertion is about generic, mask/offset-driven structure — never a
user-chosen field name's *meaning*. (Field names appear only as signal labels.)
"""
from collections import Counter

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_mapper import build_reg_blocks
from fw.hdl.emit.regblock import emit_regblock, classify, flop_bits


def _channel(reg_dma_files):
    rep = ErrorReporter()
    blocks = build_reg_blocks(reg_dma_files, FlowConfig(), rep)
    assert not rep.has_errors(), rep.report()
    return blocks["dma_channel_regs"]


def test_classification_is_mask_driven(reg_dma_files):
    csr = next(r for r in _channel(reg_dma_files).registers if r.name == "csr")
    profiles = Counter(classify(f) for f in csr.fields)
    # 15 sw-writable config, 4 read-clear sticky (the ROC bits), 2 hw-only RO
    # (no provider yet), 1 reserved — all decided from the masks, no names.
    assert profiles == {"config": 15, "sticky": 4, "ro_latched": 2, "reserved": 1}


def test_reserved_costs_no_storage(reg_dma_files):
    ch = _channel(reg_dma_files)
    # 8 regs * 32 bits == 256; csr.reserved is the only sw=hw=0 field (9 bits).
    assert flop_bits(ch) == 256 - 9
    sv = emit_regblock(ch)
    assert "field_csr__reserved" not in sv          # reserved field: no flop
    assert "hwif_out_csr__reserved" not in sv        # and no hwif port


def test_aligned_bank_decodes_without_address_comparator(reg_dma_files):
    sv = emit_regblock(_channel(reg_dma_files))
    # stride 4, 8 regs -> reg_sel = s_addr[4:2]; case over reg_sel; no `s_addr ==`.
    assert "reg_sel = s_addr[4:2]" in sv
    assert "unique case (reg_sel)" in sv
    assert "s_addr ==" not in sv                     # no wide address comparator


def test_hw_only_field_has_no_software_write(reg_dma_files):
    """A hw-writable, non-sw field (RO) updates only from its hwif port."""
    sv = emit_regblock(_channel(reg_dma_files))
    block = _field_block(sv, "field_csr__busy")
    assert "hwif_in_csr__busy_we" in block
    assert "s_wdata" not in block                    # software cannot write it


def test_sticky_field_priority_hw_then_readclear(reg_dma_files):
    """A read-clear field: hardware set-update takes priority over the read-clear,
    and the clear is gated by an accepted software read."""
    sv = emit_regblock(_channel(reg_dma_files))
    block = _field_block(sv, "field_csr__int_done")
    we = block.index("hwif_in_csr__int_done_we")
    clr = block.index("s_rd")
    assert we < clr                                  # hw update precedes read-clear
    assert "s_wdata" not in block                    # not software-writable


def test_config_field_software_writable(reg_dma_files):
    sv = emit_regblock(_channel(reg_dma_files))
    block = _field_block(sv, "field_csr__ch_en")
    assert "s_wr" in block and "s_wdata[0:0]" in block
    assert "hwif_in_csr__ch_en_we" not in block      # not hardware-writable


def _field_block(sv: str, signal: str) -> str:
    """Return the always_ff block text for a field's storage signal."""
    lines = sv.splitlines()
    # the field's always_ff follows its `logic ... field_x;` / assign lines
    start = next(i for i, l in enumerate(lines)
                 if f"always_ff" in l and any(signal in lines[j]
                                              for j in range(max(0, i - 3), i)))
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "end")
    return "\n".join(lines[start:end + 1])
