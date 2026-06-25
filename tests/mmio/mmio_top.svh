
// Class-level assembly for elaboration (the generated *RTL* top is produced by
// the fw-hdl front end; this class top exists so the package elaborates under
// fw_root during sv2ir parsing). It owns the register model and the MMIO FSM that
// is driven by it, exposing the block on the bus as an export for completeness.
class mmio_top extends fw_component;
    mmio_regs                          m_regs;
    fw_export #(fw_reg_block_if #(32)) regs;
    mmio_fsm                           fsm;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        m_regs = new("regs");
        regs   = new("regs", this, m_regs);   // export imp == the block
        fsm    = new("fsm", this, m_regs);
    endfunction
endclass
