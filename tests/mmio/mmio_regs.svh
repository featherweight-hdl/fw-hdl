
// The minimal memory-mapped register block: a software-written CTRL (watched by
// the FSM) and a hardware-driven STATUS. CTRL.go is sw RW; STATUS.flag is
// hardware-owned (RO to software). Auto-offsets at stride 4 -> ctrl@0x0, status@0x4.
class mmio_regs extends fw_reg_block #(32);
    fw_reg #(mmio_ctrl_t)   ctrl;     // 0x0  sw RW (go)
    fw_reg #(mmio_status_t) status;   // 0x4  hw-owned (flag)

    function new(string name);
        super.new(name);
        ctrl   = new("ctrl",   .sw_wmask('{go:1,   default:'0}));   // sw RW: go only
        status = new("status", .sw_wmask('0),
                               .hw_wmask('{flag:1, default:'0}));    // hw owns flag only
        add(ctrl);     // 0x0
        add(status);   // 0x4
    endfunction
endclass
