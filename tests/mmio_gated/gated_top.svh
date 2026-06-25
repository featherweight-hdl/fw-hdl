
// Class-level assembly (for elaboration; the generated RTL top comes from the
// fw-hdl front end).
class gated_top extends fw_component;
    gated_regs                         m_regs;
    fw_export #(fw_reg_block_if #(32)) regs;
    gated_fsm                          fsm;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        m_regs = new("regs");
        regs   = new("regs", this, m_regs);
        fsm    = new("fsm", this, m_regs);
    endfunction
endclass
