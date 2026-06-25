
// A read-gated MMIO FSM: on each change to CTRL it *reads* CTRL.go and only
// pulses STATUS.flag when go is set. This is the reg_device shape and a ubiquitous
// MMIO idiom (act only when a control bit is asserted):
//
//   forever begin
//     wait_change;
//     if (ctrl.read().go) status.update(...);   // read-gated hardware update
//   end
//
//   m_regs.ctrl.read().go -> hwif_out_ctrl__go (an input the regblock drives)
class gated_fsm extends fw_component implements fw_runnable;
    gated_regs       m_regs;
    fw_reg_set #(32) m_set;

    function new(string name, fw_component parent, gated_regs regs);
        super.new(name, parent);
        m_regs = regs;
        add_runnable(this);
    endfunction

    function void build();
        m_set = new();
        m_set.add(m_regs.ctrl);              // wake on any CTRL write
    endfunction

    virtual task run();
        forever begin
            fw_reg_base #(32) which;
            m_set.wait_change(which);
            if (m_regs.ctrl.read().go)        // only act when go is set
                m_regs.status.update('{flag:1, default:'0},
                                     '{flag:1, default:'0});
        end
    endtask
endclass
