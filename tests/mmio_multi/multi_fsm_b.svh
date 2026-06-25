
// FSM B: driven by the B control/status pair of the same shared register model.
class multi_fsm_b extends fw_component implements fw_runnable;
    multi_regs       m_regs;
    fw_reg_set #(32) m_set;

    function new(string name, fw_component parent, multi_regs regs);
        super.new(name, parent);
        m_regs = regs;
        add_runnable(this);
    endfunction

    function void build();
        m_set = new();
        m_set.add(m_regs.ctrl_b);             // watch CTRL_B only
    endfunction

    virtual task run();
        forever begin
            fw_reg_base #(32) which;
            m_set.wait_change(which);
            m_regs.status_b.update('{flag:1, default:'0},
                                   '{flag:1, default:'0});
        end
    endtask
endclass
