// Target transactor interface: the ready/valid consumer on the internal link,
// with a receive FIFO. A clocked block fills it from the link while there is
// room; recv() pops a beat, blocking while it is empty. When the caller stops
// taking beats the FIFO fills and ready drops on the pins.
//
// Run-time knobs, set from the class side (defaults: today's behaviour):
//   depth    FIFO depth, 1..MAX_DEPTH (default 4)
//   max_gap  before taking each beat, hold the link's ready low a random
//            0..max_gap cycles (default 0). The core's 1-deep buffer still
//            takes one beat, so on the pins ready drops from the next beat.
interface fw_rv_target_xtor_if #(type T = logic [31:0]) (
    input      clock,
    input      reset,
    input  T   up_data,
    input      up_valid,
    output bit up_ready
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
    bit          drawn;                // the next beat has drawn its gap (2-state: 0 at start)

    function automatic int unsigned cur_depth();
        return (depth == 0) ? 1 : (depth > MAX_DEPTH) ? MAX_DEPTH : depth;
    endfunction

    function automatic int unsigned draw_gap();
        return (max_gap == 0) ? 0 : $urandom_range(max_gap, 0);
    endfunction

    task automatic recv(output T t);
        while (n_in == n_out) @(posedge clock);
        t = T'(mem[n_out % MAX_DEPTH]);
        n_out++;
    endtask

    // Capture link beats; up_ready is computed after this cycle's capture, so
    // the buffer never overflows. Each beat draws its gap after the previous
    // one is taken; ready stays low until the gap has run out.
    always @(posedge clock) begin : fill
        int unsigned i, g;
        if (reset) begin
            up_ready  <= 1'b0;
            gap_left  <= 0;
            drawn     <= 1'b0;
        end else begin
            i = n_in;
            g = !drawn ? draw_gap() : gap_left;
            if (up_valid && up_ready) begin
                mem[i % MAX_DEPTH] <= bits_t'(up_data);
                i++;
                g = draw_gap();
            end
            n_in      <= i;
            drawn     <= 1'b1;
            if (g == 0) begin
                up_ready <= (i - n_out < cur_depth());
                gap_left <= 0;
            end else begin
                up_ready <= 1'b0;
                gap_left <= g - 1;
            end
        end
    end
endinterface
