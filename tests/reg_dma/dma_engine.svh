
// The DMA engine's HARDWARE side, per register-model-design.md §4.4-4.5: it
// gathers every channel's CSR into a watch-set and sleeps on it. When a CSR
// changes it re-arbitrates with pick_channel(); on the winner it runs a transfer
// (here abstracted) and drives status through the masked hardware update path.
//
// This is the design's hierarchical wait-for-change in action -- and per the
// lowering doc the `for` loops over register reads (pick_channel) lower to
// combinational logic, while wait_change lowers to an FSM wait-state.
class dma_engine extends fw_component implements fw_runnable;
    dma_regs          m_regs;
    fw_reg_set #(32)  m_csrs;
    int               serviced;   // observable count for the testbench

    function new(string name, fw_component parent, dma_regs regs);
        super.new(name, parent);
        m_regs = regs;
        add_runnable(this);
    endfunction

    function void build();
        m_csrs = new();
        for (int i = 0; i < DMA_NCH; i++)
            m_csrs.add(m_regs.ch[i].csr);          // hierarchical set over all CSRs
    endfunction

    // combinational: scan channels, pick the first enabled one needing service
    function int pick_channel();
        for (int i = 0; i < DMA_NCH; i++) begin
            dma_ch_csr_t c = m_regs.ch[i].csr.read();
            if (c.ch_en && !c.busy && !c.done)
                return i;
        end
        return -1;
    endfunction

    virtual task run();
        forever begin
            int idx = pick_channel();
            while (idx == -1) begin
                fw_reg_base #(32) which;
                m_csrs.wait_change(which);          // sleep until some CSR moves
                idx = pick_channel();
            end
            service(idx);
        end
    endtask

    task service(int i);
        // mark BUSY (hardware status update)
        m_regs.ch[i].csr.update('{busy:1, default:'0}, '{busy:1, default:'0});
        // ... a real engine would read source / write dest here ...
        // complete: clear BUSY, set DONE + interrupt source, in one masked update
        m_regs.ch[i].csr.update('{done:1, busy:0, int_done:1, default:'0},
                                '{done:1, busy:1, int_done:1, default:'0});
        serviced++;
    endtask
endclass
