
// Register model for the read-gated FSM: CTRL has two software-writable bits
// (`go` and `arm`) so a write can change CTRL while leaving `go` clear -- which
// lets the testbench prove the FSM's read-gate actually blocks. STATUS.flag is
// hardware-owned.
class gated_regs extends fw_reg_block #(32);
    fw_reg #(gctrl_t)   ctrl;     // 0x0  sw RW (go, arm)
    fw_reg #(gstatus_t) status;   // 0x4  hw-owned (flag)

    function new(string name);
        super.new(name);
        ctrl   = new("ctrl",   .sw_wmask('{go:1, arm:1, default:'0}));
        status = new("status", .sw_wmask('0), .hw_wmask('{flag:1, default:'0}));
        add(ctrl);     // 0x0
        add(status);   // 0x4
    endfunction
endclass
