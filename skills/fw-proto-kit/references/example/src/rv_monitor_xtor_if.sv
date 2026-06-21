// Monitor transactor-interface: ready/valid CONSUMER on the internal link, with a
// receive FIFO. get() is a BLOCKING task the monitor bridge calls; the bridge then
// fans the beat out through the (non-blocking) monitor API. Same shape as the
// target transactor-interface.
interface rv_monitor_xtor_if (
    input             clock,
    input             reset,
    input  [31:0]     up_data,             // core  -> iface (ready/valid link)
    input             up_valid,            // core  -> iface
    output bit        up_ready             // iface -> core
);
    // Deeper than the data path: a passive monitor cannot backpressure the bus,
    // so size the FIFO to absorb bursts while the bridge drains it.
    localparam int unsigned DEPTH = 8;
    logic [31:0] fifo[$];                  // observed-beat queue

    // Caller side (monitor bridge): pop the next observed beat; block if empty.
    task automatic get(output logic [31:0] t);
        while (fifo.size() == 0) @(posedge clock);
        t = fifo.pop_front();
    endtask

    // Fill side: capture link beats into the FIFO; assert up_ready when room.
    always @(posedge clock) begin
        if (reset) begin
            up_ready <= 1'b0;
        end else begin
            if (up_valid && up_ready)
                fifo.push_back(up_data);
            up_ready <= (fifo.size() < DEPTH);
        end
    end
endinterface
