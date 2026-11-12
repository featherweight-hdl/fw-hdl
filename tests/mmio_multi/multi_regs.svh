
// A register model shared by TWO FSMs (the smallest stand-in for "an FSM per DMA
// channel"): two independent control/status pairs. FSM A is driven by the A pair,
// FSM B by the B pair, both from this one register block.
class multi_regs extends fw_reg_block #(32);
    fw_reg #(mm_ctrl_t)   ctrl_a;     // 0x0  sw RW (go)
    fw_reg #(mm_status_t) status_a;   // 0x4  hw-owned (flag)
    fw_reg #(mm_ctrl_t)   ctrl_b;     // 0x8  sw RW (go)
    fw_reg #(mm_status_t) status_b;   // 0xc  hw-owned (flag)

    function new(string name);
        super.new(name);
        ctrl_a   = new("ctrl_a",   this, .sw_wmask('{go:1,   default:'0}));
        status_a = new("status_a", this, .sw_wmask('0), .hw_wmask('{flag:1, default:'0}));
        ctrl_b   = new("ctrl_b",   this, .sw_wmask('{go:1,   default:'0}));
        status_b = new("status_b", this, .sw_wmask('0), .hw_wmask('{flag:1, default:'0}));
    endfunction
endclass
