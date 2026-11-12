// Monitor transactor interface: the consumer on the internal link, with a
// receive FIFO deeper than the data path's, since a passive monitor cannot
// backpressure the pins.
//   get(t)                     the next completed transfer (blocking)
//   get_ev(t, first, xfer)     the next pin event: the first valid cycle of a
//                              transfer (first), its completion (xfer), or both
// Use one or the other: get() discards the first-valid-only events.
//
// Run-time knob: depth, 1..MAX_DEPTH (default 8).
interface fw_rv_monitor_xtor_if #(type T = logic [31:0]) (
    input      clock,
    input      reset,
    input  T   up_data,
    input      up_valid,
    input      up_first,
    input      up_xfer,
    output bit up_ready
);
    localparam int unsigned MAX_DEPTH = 16;
    int unsigned depth = 8;
    // A ring buffer, not a queue: Verilator 5.052 rejects a queue in a
    // parameterized interface reached through a virtual handle ("virtual
    // interface trigger on ... $[$]"). Each counter has one writer: n_in the
    // producer side, n_out the consumer side.
    typedef logic [$bits(T)-1:0] bits_t;
    bits_t       mem[MAX_DEPTH];
    bit          mem_first[MAX_DEPTH];
    bit          mem_xfer[MAX_DEPTH];
    int unsigned n_in = 0, n_out = 0;

    function automatic int unsigned cur_depth();
        return (depth == 0) ? 1 : (depth > MAX_DEPTH) ? MAX_DEPTH : depth;
    endfunction

    task automatic get_ev(output T t, output bit first, output bit xfer);
        while (n_in == n_out) @(posedge clock);
        t     = T'(mem[n_out % MAX_DEPTH]);
        first = mem_first[n_out % MAX_DEPTH];
        xfer  = mem_xfer[n_out % MAX_DEPTH];
        n_out++;
    endtask

    task automatic get(output T t);
        /* verilator lint_off UNUSEDSIGNAL */
        bit first;                         // get() reports transfers only
        /* verilator lint_on UNUSEDSIGNAL */
        bit xfer;
        do get_ev(t, first, xfer); while (!xfer);
    endtask

    // Capture link beats; up_ready is computed after this cycle's capture, so
    // the buffer never overflows.
    always @(posedge clock) begin : fill
        int unsigned i;
        if (reset) begin
            up_ready <= 1'b0;
        end else begin
            i = n_in;
            if (up_valid && up_ready) begin
                mem[i % MAX_DEPTH]       <= bits_t'(up_data);
                mem_first[i % MAX_DEPTH] <= up_first;
                mem_xfer[i % MAX_DEPTH]  <= up_xfer;
                i++;
            end
            n_in <= i;
            up_ready <= (i - n_out < cur_depth());
        end
    end
endinterface
