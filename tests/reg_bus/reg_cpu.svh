
// The "CPU": a software actor that reaches the device's registers purely by
// byte offset through an fw_port #(fw_reg_block_if) -- it holds no register
// handles. It writes CTRL.go, then polls STATUS (ticking the clock between
// polls) until the device reports done, recording the outcome for the testbench.
class reg_cpu extends fw_component implements fw_runnable;
    fw_port #(fw_reg_block_if #(32)) regs_p;

    // results, read by the testbench
    bit       finished;
    bit       ok;
    status_t  seen;
    ctrl_t    ctrl_rb;   // CTRL read back (proves the RW software path)

    localparam int unsigned CTRL   = 32'h00;
    localparam int unsigned STATUS = 32'h04;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    function void build();
        regs_p = new("regs", this);
    endfunction

    virtual task run();
        automatic ctrl_t go_cmd = '{go:1, default:'0};
        ok = 1'b1;
        this.tick();                                   // let the device reach its wait

        // software write of CTRL.go via the bus
        regs_p.t.write_val(CTRL, 32'(go_cmd));

        // read CTRL back: the RW software path round-trips
        ctrl_rb = ctrl_t'(regs_p.t.read_val(CTRL));
        if (!ctrl_rb.go) ok = 1'b0;

        // poll STATUS until the device drives done (ticking between polls)
        begin
            automatic int guard = 0;
            do begin
                this.tick();
                seen = status_t'(regs_p.t.read_val(STATUS));
                guard++;
            end while (!seen.done && guard < 20);
        end

        if (!seen.done || seen.payload !== 31'h0AB) ok = 1'b0;
        finished = 1'b1;
    endtask
endclass
