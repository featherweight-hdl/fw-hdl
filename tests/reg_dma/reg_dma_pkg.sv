
// M4 DMA worked example -- class layer. Realizes register-model-design.md §4 on
// the actual register model: the channel CSR/SZ/ADDR packed-struct layouts, a
// 31-channel register file, a hardware engine that polls a watch-set of CSRs,
// and a software host that drives a channel through the bus. This is the
// ergonomics & scale proof for the register model. fw_hdl_pkg supplies the
// component/port/export machinery and the register model.
package reg_dma_pkg;
    import fw_hdl_pkg::*;

    localparam int DMA_NCH = 31;

    // ---- field layouts as packed structs (2-state, MSB-first; Table 6/7/8) ----
    typedef struct packed {
        bit [8:0] reserved;       // 31:23 RO
        bit       int_chk_done;   // 22 ROC
        bit       int_done;       // 21 ROC
        bit       int_err;        // 20 ROC
        bit       ine_chk_done;   // 19 RW
        bit       ine_done;       // 18 RW
        bit       ine_err;        // 17 RW
        bit       rest_en;        // 16 RW
        bit [2:0] prio;           // 15:13 RW
        bit       err;            // 12 ROC
        bit       done;           // 11 RO
        bit       busy;           // 10 RO
        bit       stop;           //  9 WO
        bit       sz_wb;          //  8 RW
        bit       use_ed;         //  7 RW
        bit       ars;            //  6 RW
        bit       mode;           //  5 RW
        bit       inc_src;        //  4 RW
        bit       inc_dst;        //  3 RW
        bit       src_sel;        //  2 RW
        bit       dst_sel;        //  1 RW
        bit       ch_en;          //  0 RW
    } dma_ch_csr_t;

    typedef struct packed {
        bit [6:0]  reserved1;     // 31:25 RO
        bit [8:0]  chk_sz;        // 24:16 RW
        bit [3:0]  reserved0;     // 15:12 RO
        bit [11:0] tot_sz;        // 11:0  RW
    } dma_ch_sz_t;

    typedef struct packed {
        bit [29:0] addr;          // 31:2 RW
        bit [1:0]  reserved;      // 1:0  RO
    } dma_addr_t;

    `include "dma_regmap.svh"   // dma_channel_regs, dma_regs
    `include "dma_engine.svh"   // dma_engine (hardware side)
    `include "dma_top.svh"      // dma_dev, dma_host, dma_top
endpackage
