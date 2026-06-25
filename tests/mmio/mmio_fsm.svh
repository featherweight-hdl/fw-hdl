
// The minimal MMIO-driven FSM. A plain fw_component that *uses* a memory-mapped
// register block: it gathers a watched register into a set, sleeps on it, and
// pulses a hardware-owned status field on every change:
//
//   forever { wait_change; update }
//
// No control flow, no helper calls, no arrays -- the smallest fully
// front-end-driven MMIO component. (A DMA channel, a UART, or a SPI controller is
// the same shape with more registers and real control flow.)
//
//   m_set.wait_change(which)      -> wait_until(set_changed)   (FSM wait beat)
//   m_regs.status.update(v, mask) -> hwif we/next pulse        (Mealy, D1)
class mmio_fsm extends fw_component implements fw_runnable;
    mmio_regs        m_regs;       // the register model it is driven by
    fw_reg_set #(32) m_set;        // watch-set over CTRL

    function new(string name, fw_component parent, mmio_regs regs);
        super.new(name, parent);
        m_regs = regs;
        add_runnable(this);
    endfunction

    function void build();
        m_set = new();
        m_set.add(m_regs.ctrl);              // wake when software writes CTRL
    endfunction

    virtual task run();
        forever begin
            fw_reg_base #(32) which;
            m_set.wait_change(which);                       // sleep until CTRL moves
            m_regs.status.update('{flag:1, default:'0},     // pulse STATUS.flag
                                 '{flag:1, default:'0});
        end
    endtask
endclass
