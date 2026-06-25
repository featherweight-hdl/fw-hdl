
// The DMA register map, straight from register-model-design.md §4: a per-channel
// register file (dma_channel_regs) and the top file (dma_regs) holding the
// globals plus an array of DMA_NCH identical channel files at stride 0x20. The
// 31-channel array is an ordinary `for` loop -- exactly the ergonomics win over
// hand-authoring a register file (or maintaining a separate SystemRDL source).

// A single channel's register file (offsets auto-assign at stride 4 -> 0x20 span).
class dma_channel_regs extends fw_reg_block #(32);
    fw_reg #(dma_ch_csr_t) csr;
    fw_reg #(dma_ch_sz_t)  sz;
    fw_reg #(dma_addr_t)   a0, am0, a1, am1;
    fw_reg #(bit [31:0])   desc, swptr;

    function new(string name);
        super.new(name);
        csr = new("csr", .sw_wmask(csr_sw_wmask()),
                         .hw_wmask(csr_hw_wmask()),
                         .rclr_mask(csr_rclr()));
        sz  = new("sz");
        a0  = new("a0");
        am0 = new("am0", .reset(32'hFFFF_FFFC));
        a1  = new("a1");
        am1 = new("am1", .reset(32'hFFFF_FFFC));
        desc = new("desc");  swptr = new("swptr");

        add(csr);    // 0x00
        add(sz);     // 0x04
        add(a0);     // 0x08
        add(am0);    // 0x0c
        add(a1);     // 0x10
        add(am1);    // 0x14
        add(desc);   // 0x18
        add(swptr);  // 0x1c  -> size() == 0x20
    endfunction

    // bits hardware drives: status + interrupt-source (ROC) bits
    static function dma_ch_csr_t csr_hw_wmask();
        return '{ busy:1, done:1, err:1,
                  int_chk_done:1, int_done:1, int_err:1, default:'0 };
    endfunction
    // bits software may write: all the RW config + the WO STOP pulse
    static function dma_ch_csr_t csr_sw_wmask();
        return '{ ine_chk_done:1, ine_done:1, ine_err:1, rest_en:1, prio:'1,
                  stop:1, sz_wb:1, use_ed:1, ars:1, mode:1,
                  inc_src:1, inc_dst:1, src_sel:1, dst_sel:1, ch_en:1, default:'0 };
    endfunction
    // ROC bits cleared on a software read of the CSR
    static function dma_ch_csr_t csr_rclr();
        return '{ int_chk_done:1, int_done:1, int_err:1, err:1, default:'0 };
    endfunction
endclass

// The top register file: globals + a channel array.
class dma_regs extends fw_reg_block #(32);
    fw_reg #(bit [31:0]) csr;                       // PAUSE etc.
    fw_reg #(bit [31:0]) int_msk_a, int_msk_b;
    fw_reg #(bit [31:0]) int_src_a, int_src_b;      // hw-set, read-to-clear
    dma_channel_regs     ch[DMA_NCH];

    function new(string name);
        super.new(name);
        csr       = new("csr");
        int_msk_a = new("int_msk_a");  int_msk_b = new("int_msk_b");
        int_src_a = new("int_src_a", .hw_wmask('1), .rclr_mask('1));
        int_src_b = new("int_src_b", .hw_wmask('1), .rclr_mask('1));

        add(csr);        // 0x00
        add(int_msk_a);  // 0x04
        add(int_msk_b);  // 0x08
        add(int_src_a);  // 0x0c
        add(int_src_b);  // 0x10
        // channel files start at 0x20, stride 0x20 (gap 0x14..0x1f).
        for (int i = 0; i < DMA_NCH; i++) begin
            ch[i] = new($sformatf("ch%0d", i));
            add_block(ch[i], 32 + i*32);
        end
    endfunction
endclass
