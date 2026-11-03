// Initiator transactor interface: the ready/valid producer on the internal link
// to the core, with a DEPTH-deep send FIFO so the caller can run ahead of the
// pins by up to DEPTH beats. send() only queues (blocking while full); a clocked
// block drains the FIFO onto the link.
//
// The interface-to-core link is always plain ready/valid (up_*), whatever the
// pin protocol, and both ends are clocked. DEPTH is a localparam: a parameter
// would have to be carried by every element that names this type.
interface fw_rv_initiator_xtor_if #(type T = logic [31:0]) (
    input      clock,
    input      reset,
    output T   up_data,
    output bit up_valid,
    input      up_ready
);
    localparam int unsigned DEPTH = 4;
    // A ring buffer, not a queue: Verilator 5.052 rejects a queue in a
    // parameterized interface reached through a virtual handle ("virtual
    // interface trigger on ... $[$]"). Each counter has one writer: n_in the
    // producer side, n_out the consumer side.
    typedef logic [$bits(T)-1:0] bits_t;
    bits_t       mem[DEPTH];
    int unsigned n_in = 0, n_out = 0;

    task automatic send(input T t);
        while (n_in - n_out >= DEPTH) @(posedge clock);
        mem[n_in % DEPTH] = bits_t'(t);
        n_in++;
    endtask

    // Present the head on the link; advance past each accepted beat.
    always @(posedge clock) begin : drain
        int unsigned o;
        if (reset) begin
            up_valid <= 1'b0;
            up_data  <= '0;
        end else begin
            o = n_out + ((up_valid && up_ready) ? 1 : 0);
            n_out <= o;
            if (n_in != o) begin
                up_valid <= 1'b1;
                up_data  <= T'(mem[o % DEPTH]);
            end else begin
                up_valid <= 1'b0;
            end
        end
    end
endinterface
