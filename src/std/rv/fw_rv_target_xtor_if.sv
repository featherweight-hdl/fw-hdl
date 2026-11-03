// Target transactor interface: the ready/valid consumer on the internal link,
// with a DEPTH-deep receive FIFO. A clocked block fills it from the link while
// there is room; recv() pops a beat, blocking while it is empty. When the
// caller stops taking beats the FIFO fills and ready drops on the pins.
interface fw_rv_target_xtor_if #(type T = logic [31:0]) (
    input      clock,
    input      reset,
    input  T   up_data,
    input      up_valid,
    output bit up_ready
);
    localparam int unsigned DEPTH = 4;
    // A ring buffer, not a queue: Verilator 5.052 rejects a queue in a
    // parameterized interface reached through a virtual handle ("virtual
    // interface trigger on ... $[$]"). Each counter has one writer: n_in the
    // producer side, n_out the consumer side.
    typedef logic [$bits(T)-1:0] bits_t;
    bits_t       mem[DEPTH];
    int unsigned n_in = 0, n_out = 0;

    task automatic recv(output T t);
        while (n_in == n_out) @(posedge clock);
        t = T'(mem[n_out % DEPTH]);
        n_out++;
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
                mem[i % DEPTH] <= bits_t'(up_data);
                i++;
            end
            n_in <= i;
            up_ready <= (i - n_out < DEPTH);
        end
    end
endinterface
