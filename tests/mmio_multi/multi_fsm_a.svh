
// FSM A: driven by the A control/status pair of the shared register model. Its
// watch-set name (`m_set`) deliberately matches FSM B's, to exercise the design
// assembler's per-FSM change-set qualification.
class multi_fsm_a extends fw_component implements fw_runnable;
    multi_regs       m_regs;
    fw_reg_set #(32) m_set;

    function new(string name, fw_component parent, multi_regs regs);
        super.new(name, parent);
        m_regs = regs;
        add_runnable(this);
    endfunction

    function void build();
        m_set = new();
        m_set.add(m_regs.ctrl_a);             // watch CTRL_A only
    endfunction

    virtual task run();
        forever begin
            fw_reg_base #(32) which;
            m_set.wait_change(which);
            m_regs.status_a.update('{flag:1, default:'0},
                                   '{flag:1, default:'0});
        end
    endtask
endclass
