
// Device, host, and top for the DMA worked example.
//
// dma_dev owns the register map and the engine, and exposes the map on the bus
// as an fw_export #(fw_reg_block_if). dma_host is the software actor: it programs
// a channel's CSR (CH_EN) by offset through the bus and polls that CSR until the
// engine reports DONE, then proves the ROC interrupt-source bit read-clears.

class dma_dev extends fw_component;
    fw_export #(fw_reg_block_if #(32)) regs;   // bus-facing provider
    dma_regs    m_regs;
    dma_engine  m_engine;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        m_regs   = new("regs");
        regs     = new("regs", this, m_regs);          // export imp == the map
        m_engine = new("engine", this, m_regs);        // hardware side
    endfunction
endclass

class dma_host extends fw_component implements fw_runnable;
    fw_port #(fw_reg_block_if #(32)) regs_p;

    // results read by the testbench
    bit          finished;
    bit          ok;
    dma_ch_csr_t first_seen;    // CSR value when DONE first observed
    dma_ch_csr_t second_seen;   // the next read (int_done must have cleared)

    // program channel 2: CSR @ 0x20 + 2*0x20 == 0x60 (matches the spec's CH2_CSR)
    localparam int unsigned CH2_CSR = 32'h60;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    function void build();
        regs_p = new("regs", this);
    endfunction

    virtual task run();
        automatic dma_ch_csr_t enable = '{ch_en:1, default:'0};
        automatic int guard = 0;
        ok = 1'b1;
        this.tick();                                    // let the engine reach its wait

        // software enables the channel
        regs_p.t.write_val(CH2_CSR, 32'(enable));

        // poll the CSR until DONE; each read also read-clears the ROC int bits
        do begin
            this.tick();
            first_seen = dma_ch_csr_t'(regs_p.t.read_val(CH2_CSR));
            guard++;
        end while (!first_seen.done && guard < 40);

        // a second read: DONE persists (RO sticky), int_done has been cleared (ROC)
        second_seen = dma_ch_csr_t'(regs_p.t.read_val(CH2_CSR));

        if (!first_seen.done)        ok = 1'b0;   // engine completed
        if (!first_seen.int_done)    ok = 1'b0;   // interrupt source was set
        if (!second_seen.done)       ok = 1'b0;   // DONE is sticky
        if ( second_seen.int_done)   ok = 1'b0;   // int_done read-cleared
        finished = 1'b1;
    endtask
endclass

class dma_top extends fw_component;
    dma_dev  dev;
    dma_host host;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        dev  = new("dev", this);
        host = new("host", this);
    endfunction

    function void connect();
        host.regs_p.connect(dev.regs);
    endfunction
endclass
