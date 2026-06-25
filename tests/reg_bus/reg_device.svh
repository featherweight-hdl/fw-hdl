
// The "device": owns a register block and exposes it on the bus as an
// fw_export #(fw_reg_block_if). Because fw_reg_block already implements
// fw_reg_block_if, the block itself IS the export's imp -- no adapter class is
// needed. The device's HARDWARE side reaches its registers through direct
// handles (m_ctrl/m_status): it sleeps on a watch-set over CTRL and, when
// software sets CTRL.go, drives STATUS through the masked hardware update path.
class reg_device extends fw_component implements fw_runnable;
    // bus-facing provider: a CPU port connects here
    fw_export #(fw_reg_block_if #(32)) regs;

    // hardware-owned register state
    fw_reg_block #(32)   m_block;
    fw_reg #(ctrl_t)     m_ctrl;     // RW @ 0x00 (software drives `go`)
    fw_reg #(status_t)   m_status;   // RO @ 0x04 (hardware drives done/payload)
    fw_reg_set #(32)     m_watch;    // wake the engine when CTRL changes

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    function void build();
        m_block  = new("regs");
        m_ctrl   = new("ctrl");                                  // RW (defaults)
        m_status = new("status", .sw_wmask('0), .hw_wmask('1));  // RO to sw, hw owns
        m_block.add(m_ctrl);     // 0x00
        m_block.add(m_status);   // 0x04

        regs = new("regs", this, m_block);   // export imp == the block

        m_watch = new();
        m_watch.add(m_ctrl);                 // subscribe before run() (safe)
    endfunction

    virtual task run();
        forever begin
            fw_reg_base #(32) which;
            m_watch.wait_change(which);       // sleep until CTRL moves
            if (m_ctrl.read().go)             // hardware reads its own reg
                // drive STATUS via the masked hardware update path
                m_status.update('{done:1, payload:31'h0AB, default:'0});
        end
    endtask
endclass
