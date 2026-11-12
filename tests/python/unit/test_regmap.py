"""M5: RegMap recognition — the register-block object graph is elaborated into a
flat field table (offsets, bit placement, sw/hw/rclr access, reset) recovered
from the SystemVerilog declarations + constructor of the DMA register classes."""
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_mapper import build_reg_blocks


def _blocks(reg_dma_files):
    reporter = ErrorReporter()
    blocks = build_reg_blocks(reg_dma_files, FlowConfig(), reporter)
    assert not reporter.has_errors(), reporter.report()
    return blocks


# ---- the per-channel register file ------------------------------------------
def test_channel_block_shape(reg_dma_files):
    ch = _blocks(reg_dma_files)["dma_channel_regs"]
    assert ch.size == 0x20
    names = [r.name for r in ch.registers]
    assert names == ["csr", "sz", "a0", "am0", "a1", "am1", "desc", "swptr"]
    offs = {r.name: r.offset for r in ch.registers}
    assert offs == {"csr": 0x00, "sz": 0x04, "a0": 0x08, "am0": 0x0c,
                    "a1": 0x10, "am1": 0x14, "desc": 0x18, "swptr": 0x1c}


def test_csr_field_layout(reg_dma_files):
    ch = _blocks(reg_dma_files)["dma_channel_regs"]
    csr = next(r for r in ch.registers if r.name == "csr")
    f = {fld.name: fld for fld in csr.fields}
    # bit placement recovered from the packed struct
    assert (f["ch_en"].lsb, f["ch_en"].width) == (0, 1)
    assert (f["prio"].lsb, f["prio"].width) == (13, 3)
    assert (f["int_chk_done"].lsb, f["int_chk_done"].width) == (22, 1)
    assert (f["reserved"].lsb, f["reserved"].width) == (23, 9)


def test_csr_masks_from_helper_functions(reg_dma_files):
    """The CSR sw/hw/rclr masks come from single-return struct-literal helpers
    (csr_*_wmask) and must be constant-folded exactly."""
    ch = _blocks(reg_dma_files)["dma_channel_regs"]
    csr = next(r for r in ch.registers if r.name == "csr")
    assert csr.sw_wmask == 0x000FE3FF
    assert csr.hw_wmask == 0x00701C00
    assert csr.rclr_mask == 0x00701000
    assert not csr.unresolved


def test_csr_field_access_classification(reg_dma_files):
    ch = _blocks(reg_dma_files)["dma_channel_regs"]
    csr = next(r for r in ch.registers if r.name == "csr")
    f = {fld.name: fld for fld in csr.fields}
    assert f["ch_en"].access() == "RW"
    assert f["busy"].access() == "RO"        # hw-set status, sw reads
    assert f["int_done"].access() == "ROC"   # hw-set, read-to-clear
    assert f["reserved"].access() == "RESERVED"


def test_addr_mask_reset(reg_dma_files):
    """am0/am1 reset 0xFFFFFFFC -> the 30-bit addr field resets to 0x3FFFFFFF."""
    ch = _blocks(reg_dma_files)["dma_channel_regs"]
    am0 = next(r for r in ch.registers if r.name == "am0")
    assert am0.reset == 0xFFFFFFFC
    addr = next(fld for fld in am0.fields if fld.name == "addr")
    assert addr.reset == 0x3FFFFFFF


# ---- the top file: globals + a 31-channel array (for-loop unrolled) ---------
def test_top_block_channel_array(reg_dma_files):
    top = _blocks(reg_dma_files)["dma_regs"]
    assert len(top.subblocks) == 31
    bases = [off for off, _ in top.subblocks]
    assert bases[0] == 0x20 and bases[1] == 0x40 and bases[-1] == 0x3E0
    assert top.size == 0x400


def test_top_global_int_src_is_read_clear(reg_dma_files):
    top = _blocks(reg_dma_files)["dma_regs"]
    isrc = next(r for r in top.registers if r.name == "int_src_a")
    assert isrc.hw_wmask == 0xFFFFFFFF and isrc.rclr_mask == 0xFFFFFFFF


def test_flatten_absolute_offsets(reg_dma_files):
    """Channel 2's CSR.ch_en lands at absolute byte offset 0x60 (spec CH2_CSR)."""
    top = _blocks(reg_dma_files)["dma_regs"]
    flat = top.flatten()
    ch2_ch_en = [ff for ff in flat
                 if ff.abs_offset == 0x60 and ff.field == "ch_en"]
    assert len(ch2_ch_en) == 1
    assert ch2_ch_en[0].access == "RW"
    # every flattened field has a concrete absolute offset and width
    assert all(ff.width >= 1 for ff in flat)


# ---- the constructor forms ----------------------------------------------------
_FORMS = """
package forms_pkg;
    import fw_hdl_pkg::*;
    typedef struct packed { bit [30:0] rsv; bit go; } ctl_t;
    class forms_regs extends fw_reg_block #(32);
        fw_reg #(ctl_t)      ctl;
        fw_reg #(bit [31:0]) tx, rx, gap;
        function new(string name);
            super.new(name);
            ctl = new("ctl", this, .pulse_mask('{go:1, default:'0}));  // 0x0, cursor
            tx  = new("tx",  this, 8, .access(FW_REG_WO));              // explicit offset
            rx  = new("rx",  this, 8, .sw_wmask('0), .hw_wmask('1),
                      .access(FW_REG_RO));                              // shares 0x8
            gap = new("gap", this);                                     // cursor: 0xc
        endfunction
    endclass
    class forms_top extends fw_component;
        forms_regs regs;
        function new(string name, fw_component parent);
            super.new(name, parent);
            regs = new("regs");
        endfunction
    endclass
endpackage

module forms_tb;    // binds fw_root's Tbind so the library elaborates
    logic clock = 1'b0, reset = 1'b1;
    fw_root #(.Tbind(fw_hdl_pkg::fw_component_root #(forms_pkg::forms_top))) u_root (
        .clock(clock), .reset(reset));
endmodule
"""


def _forms(tmp_path, src):
    f = tmp_path / "forms_pkg.sv"
    f.write_text(src)
    reporter = ErrorReporter()
    blocks = build_reg_blocks([str(f)], FlowConfig(), reporter)
    return blocks, reporter


def test_self_registering_offsets_access_and_pulse(tmp_path):
    """`r = new(name, this, ...)` adds r in source order at `offset` (or the
    cursor); access and pulse_mask are read, and marked unresolved since the RTL
    emitter does not honour them yet."""
    blocks, reporter = _forms(tmp_path, _FORMS)
    assert not reporter.has_errors(), reporter.report()
    regs = {r.name: r for r in blocks["forms_regs"].registers}
    assert [r.name for r in blocks["forms_regs"].registers] == ["ctl", "tx", "rx", "gap"]
    assert {n: r.offset for n, r in regs.items()} == {"ctl": 0, "tx": 8, "rx": 8, "gap": 0xc}
    assert (regs["tx"].access, regs["rx"].access, regs["gap"].access) == ("WO", "RO", "RW")
    assert regs["ctl"].pulse_mask == 1 and "pulse_mask" in regs["ctl"].unresolved
    assert "access" in regs["tx"].unresolved and not regs["gap"].unresolved


def test_add_after_self_registering_is_an_error(tmp_path):
    """fw_reg_block.add() of a register `new(.., this)` already added is a
    $fatal at run time; the recognizer reports it."""
    src = _FORMS.replace("gap = new(\"gap\", this);", "gap = new(\"gap\", this); add(gap);")
    _, reporter = _forms(tmp_path, src)
    assert reporter.has_errors() and "twice" in reporter.report()
