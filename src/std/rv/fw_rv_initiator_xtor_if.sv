// Initiator transactor interface: the ready/valid producer on the internal link
// to the core, with a send FIFO so the caller can run ahead of the pins by up
// to `depth` beats. send() only queues (blocking while full); a clocked block
// drains the FIFO onto the link.
//
// The interface-to-core link is always plain ready/valid (up_*), whatever the
// pin protocol, and both ends are clocked. MAX_DEPTH is a localparam: a
// parameter would have to be carried by every element that names this type.
//
// Run-time knobs, set from the class side (defaults: today's behaviour):
//   depth    FIFO depth, 1..MAX_DEPTH (default 4)
//   max_gap  before presenting each beat, idle a random 0..max_gap cycles in
//            which the core could have taken it, so valid stays low that long
//            on the pins (default 0: full throughput)
interface fw_rv_initiator_xtor_if #(type T = logic [31:0]) (
    input      clock,
    input      reset,
    output T   up_data,
    output bit up_valid,
    input      up_ready
);
    localparam int unsigned MAX_DEPTH = 16;
    int unsigned depth   = 4;
    int unsigned max_gap = 0;
    // A ring buffer, not a queue: Verilator 5.052 rejects a queue in a
    // parameterized interface reached through a virtual handle ("virtual
    // interface trigger on ... $[$]"). Each counter has one writer: n_in the
    // producer side, n_out the consumer side.
    typedef logic [$bits(T)-1:0] bits_t;
    bits_t       mem[MAX_DEPTH];
    int unsigned n_in = 0, n_out = 0;
    int unsigned gap_left;
    bit          drawn;                // the next head has drawn its gap (2-state: 0 at start)

    function automatic int unsigned cur_depth();
        return (depth == 0) ? 1 : (depth > MAX_DEPTH) ? MAX_DEPTH : depth;
    endfunction

    function automatic int unsigned draw_gap();
        return (max_gap == 0) ? 0 : $urandom_range(max_gap, 0);
    endfunction

    task automatic send(input T t);
        while (n_in - n_out >= cur_depth()) @(posedge clock);
        mem[n_in % MAX_DEPTH] = bits_t'(t);
        n_in++;
    endtask

    // Present the head on the link; advance past each accepted beat. Each
    // beat draws its gap when it becomes the head; the gap counts down only
    // while the core is ready, so it shows on the pins as cycles without valid.
    always @(posedge clock) begin : drain
        int unsigned o, g;
        bit          nd;
        if (reset) begin
            up_valid  <= 1'b0;
            up_data   <= '0;
            gap_left  <= 0;
            drawn     <= 1'b0;
        end else begin
            o  = n_out;
            nd = !drawn;
            if (up_valid && up_ready) begin
                o++;
                nd = 1'b1;
            end
            n_out <= o;
            if (up_valid && !up_ready) begin
                // hold the presented beat
            end else if (n_in == o) begin
                up_valid  <= 1'b0;
                drawn     <= !nd;
            end else begin
                g = nd ? draw_gap() : gap_left;
                drawn     <= 1'b1;
                if (g == 0) begin
                    up_valid <= 1'b1;
                    up_data  <= T'(mem[o % MAX_DEPTH]);
                    gap_left <= 0;
                end else begin
                    up_valid <= 1'b0;
                    gap_left <= up_ready ? g - 1 : g;
                end
            end
        end
    end
endinterface
