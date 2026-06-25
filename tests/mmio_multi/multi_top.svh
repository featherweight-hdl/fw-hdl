
// Class-level assembly: ONE register model shared by TWO FSMs (for elaboration;
// the generated RTL top is produced by the fw-hdl front end).
class multi_top extends fw_component;
    multi_regs                         m_regs;
    fw_export #(fw_reg_block_if #(32)) regs;
    multi_fsm_a                        fsm_a;
    multi_fsm_b                        fsm_b;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        m_regs = new("regs");
        regs   = new("regs", this, m_regs);   // one register model...
        fsm_a  = new("fsm_a", this, m_regs);  // ...shared by both FSMs
        fsm_b  = new("fsm_b", this, m_regs);
    endfunction
endclass
