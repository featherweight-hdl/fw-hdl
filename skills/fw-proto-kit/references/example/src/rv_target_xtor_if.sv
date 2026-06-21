// Target transactor-interface: ready/valid CONSUMER on the internal link, with an
// internal DEPTH-deep receive FIFO so the caller can PIPELINE. A clocked always
// block FILLS the FIFO from the link (asserting up_ready whenever there is room),
// so beats keep flowing while the caller is busy. recv() merely pops a beat
// (blocking only when the FIFO is empty), decoupled from the link/bus round-trip.
//
// Same conventions as rv_initiator_xtor_if: the link is plain ready/valid, both
// endpoints are clocked, and DEPTH is an internal localparam (not a port param).
interface rv_target_xtor_if (
    input             clock,
    input             reset,
    input  [31:0]     up_data,             // core  -> iface (ready/valid link)
    input             up_valid,            // core  -> iface
    output bit        up_ready             // iface -> core
);
    // Internal localparam, not a port parameter -- see rv_initiator_xtor_if.
    localparam int unsigned DEPTH = 4;
    logic [31:0] fifo[$];                  // receive queue (fill pushes, caller pops)

    // Caller side: pop a beat; block only while the FIFO is empty.
    task automatic recv(output logic [31:0] t);
        while (fifo.size() == 0) @(posedge clock);
        t = fifo.pop_front();
    endtask

    // Fill side: capture link beats into the FIFO; assert up_ready when there is
    // room (computed after this cycle's capture, so it never overflows).
    always @(posedge clock) begin
        if (reset) begin
            up_ready <= 1'b0;
        end else begin
            if (up_valid && up_ready)
                fifo.push_back(up_data);   // captured beat enters the FIFO
            up_ready <= (fifo.size() < DEPTH);
        end
    end
endinterface
