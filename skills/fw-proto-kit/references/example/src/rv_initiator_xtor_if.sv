// Initiator transactor-interface: ready/valid PRODUCER on the internal link, with
// an internal DEPTH-deep send FIFO so the caller can PIPELINE. send() merely
// queues a beat (blocking only when the FIFO is full), so the caller is not
// serialized by the per-beat link/bus round-trip time; it can run ahead by up to
// DEPTH beats. A clocked always block DRAINS the FIFO onto the link as fast as
// the downstream accepts.
//
// The interface<->core link is ALWAYS a plain ready/valid channel (up_valid/
// up_data/up_ready); it never adopts the external protocol's language. Both
// endpoints are CLOCKED -- a combinational drive into an interface input port is
// lost to a delta-cycle race in this flow.
interface rv_initiator_xtor_if (
    input             clock,
    input             reset,
    output bit [31:0] up_data,             // iface -> core (ready/valid link)
    output bit        up_valid,            // iface -> core
    input             up_ready             // core  -> iface
);
    // FIFO depth is a fixed property of this protocol, so it is an internal
    // localparam rather than a port parameter. A parameter would be legal, but it
    // mangles the interface type (rv_initiator_xtor_if__D4), which then must be
    // carried SYMMETRICALLY by every element that names it -- the bridge's
    // `virtual` handle, the bridge class, the wrapper. Keeping it internal avoids
    // threading that parameter everywhere. (See design rule 5 in SKILL.md.)
    localparam int unsigned DEPTH = 4;
    logic [31:0] fifo[$];                  // send queue (caller pushes, drain pops)

    // Caller side: queue a beat; block only while the FIFO is full.
    task automatic send(input logic [31:0] t);
        while (fifo.size() >= DEPTH) @(posedge clock);
        fifo.push_back(t);
    endtask

    // Drain side: present the FIFO head on the link; pop on each accepted beat.
    always @(posedge clock) begin
        if (reset) begin
            up_valid <= 1'b0;
            up_data  <= '0;
        end else begin
            if (up_valid && up_ready)
                void'(fifo.pop_front());   // accepted beat leaves the FIFO
            if (fifo.size() != 0) begin    // (re)present head after any pop
                up_valid <= 1'b1;
                up_data  <= fifo[0];
            end else begin
                up_valid <= 1'b0;
            end
        end
    end
endinterface
