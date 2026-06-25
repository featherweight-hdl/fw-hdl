// Ready/valid transactor layer for the rv_proto demo: the SV interfaces
// and modules that bridge the class-level API to the signal-level
// handshake. These are compilation units (an interface/module cannot live
// in a package); the class layer lives in rv_proto_pkg.sv.

// ======================================================================
// Initiator role -- three components. Concrete data type (see note (b)).
// ======================================================================

// The interface <-> core link is ALWAYS a plain ready/valid channel -- it never
// adopts the external protocol's language. The transactor-interface and core are
// each a ready/valid endpoint on this internal link; the core is the only place
// that knows the actual pin-level protocol. Signals are `up_valid`/`up_data`/
// `up_ready` ("up" = the link up toward the transactor-interface/API).
//
// The link being a real (clocked) ready/valid handshake -- not a bare registered
// passthrough -- is what makes the clocked-core split correct. A passthrough
// merely delays the signals, and the latency lets the consumer re-sample a beat
// the producer has not advanced past yet (duplicated beats). A proper ready/valid
// handshake transfers exactly one beat per (valid && ready) cycle on each side.

// 1. Transactor-interface: ready/valid PRODUCER on the internal link, with an
//    internal DEPTH-deep send FIFO so the caller can PIPELINE. send() merely
//    queues a beat (blocking only when the FIFO is full), so the caller is not
//    serialized by the per-beat link/bus round-trip time; it can run ahead by up
//    to DEPTH beats. A clocked always block DRAINS the FIFO onto the link as
//    fast as the downstream accepts, sustaining transfer.
interface rv_initiator_xtor_if (
    input             clock,
    input             reset,
    output bit [31:0] up_data,             // iface -> core (ready/valid link)
    output bit        up_valid,            // iface -> core
    input             up_ready             // core  -> iface
);
    // FIFO depth is a fixed property of this protocol, so it is an internal
    // localparam rather than a port parameter. A parameter would be legal but
    // must then be carried SYMMETRICALLY by every element naming the (now mangled,
    // rv_initiator_xtor_if__D4) type -- the vif handle, bridge, wrapper. Keeping
    // it internal avoids threading it everywhere.
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

// 2. Core: ready/valid CONSUMER on the internal link, protocol PRODUCER on the
//    pins. It accepts a beat (up_valid && up_ready), drives it onto the bus, and
//    waits for the bus handshake (valid && ready) before accepting the next. A
//    richer protocol (e.g. wishbone) elaborates a larger pin-level FSM here; the
//    internal ready/valid link contract is unchanged.
module rv_initiator_xtor_core (
    input             clock,
    input             reset,
    input      [31:0] up_data,             // ready/valid link (from xtor_if)
    input             up_valid,
    output bit        up_ready,
    output bit [31:0] data,                // ready/valid bus pins
    output bit        valid,
    input             ready
);
    typedef enum bit [0:0] {ACCEPT, DRIVE} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= ACCEPT; up_ready <= 1'b1; valid <= 1'b0; data <= '0;
        end else case (st)
            ACCEPT: if (up_valid && up_ready) begin  // link transfer happened
                        data <= up_data; valid <= 1'b1; up_ready <= 1'b0;
                        st <= DRIVE;
                    end
            DRIVE:  if (valid && ready) begin         // bus transfer happened
                        valid <= 1'b0; up_ready <= 1'b1; st <= ACCEPT;
                    end
            default: ;
        endcase
    end
endmodule

// 3. Transactor module: interface + core wired by the plain ready/valid link.
module rv_initiator_xtor (
    input             clock,
    input             reset,
    output bit [31:0] data,
    output bit        valid,
    input         ready
);
    bit [31:0] up_data;
    bit        up_valid;
    bit        up_ready;

    rv_initiator_xtor_if u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    rv_initiator_xtor_core u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .data(data), .valid(valid), .ready(ready)
    );
endmodule

// ======================================================================
// Target role -- three components.
// ======================================================================

// 1. Transactor-interface: ready/valid CONSUMER on the internal link, with an
//    internal DEPTH-deep receive FIFO so the caller can PIPELINE. A clocked
//    always block FILLS the FIFO from the link (asserting up_ready whenever there
//    is room), so beats keep flowing while the caller is busy. recv() merely pops
//    a beat (blocking only when the FIFO is empty), decoupled from the link/bus
//    round-trip.
interface rv_target_xtor_if (
    input             clock,
    input             reset,
    input  [31:0]     up_data,             // core  -> iface (ready/valid link)
    input             up_valid,            // core  -> iface
    output bit        up_ready             // iface -> core
);
    // Receive-FIFO depth is a fixed property of this transactor, set internally
    // (see note on rv_initiator_xtor_if -- not a port parameter).
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

// 2. Core: protocol CONSUMER on the pins, ready/valid PRODUCER on the internal
//    link. It accepts a bus beat (valid && ready) into a 1-deep buffer, presents
//    it on the link, and waits for the link handshake (up_valid && up_ready)
//    before accepting the next bus beat.
module rv_target_xtor_core (
    input             clock,
    input             reset,
    output bit [31:0] up_data,             // ready/valid link (to xtor_if)
    output bit        up_valid,
    input             up_ready,
    input             valid,               // ready/valid bus pins
    output bit        ready,
    input  [31:0]     data
);
    typedef enum bit [0:0] {ACCEPT, PRESENT} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= ACCEPT; ready <= 1'b1; up_valid <= 1'b0; up_data <= '0;
        end else case (st)
            ACCEPT:  if (valid && ready) begin        // bus transfer happened
                         up_data <= data; up_valid <= 1'b1; ready <= 1'b0;
                         st <= PRESENT;
                     end
            PRESENT: if (up_valid && up_ready) begin  // link transfer happened
                         up_valid <= 1'b0; ready <= 1'b1; st <= ACCEPT;
                     end
            default: ;
        endcase
    end
endmodule

// 3. Transactor module: core + interface wired by the plain ready/valid link.
module rv_target_xtor (
    input             clock,
    input             reset,
    input         valid,
    output bit        ready,
    input  [31:0] data
);
    bit [31:0] up_data;
    bit        up_valid;
    bit        up_ready;

    rv_target_xtor_if u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    rv_target_xtor_core u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .valid(valid), .ready(ready), .data(data)
    );
endmodule

// ======================================================================
// Monitor role -- three components. A monitor is PASSIVE: it taps the bus
// (valid/ready/data are all inputs, never driven) and republishes each observed
// beat. Same clocked / internal-ready/valid-link conventions as the other roles.
// ======================================================================

// 1. Transactor-interface: ready/valid CONSUMER on the internal link, with a
//    receive FIFO. get() is a BLOCKING task the monitor bridge calls; the bridge
//    then fans the beat out through the (non-blocking) monitor API. Identical in
//    shape to the target transactor-interface.
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

// 2. Core: clocked FSM. It WATCHES the bus (valid/ready/data inputs -- it drives
//    nothing on the bus) and, on each observed transfer (valid && ready), pushes
//    the beat onto the internal ready/valid link. 1-deep skid like the target
//    core; a zero-drop monitor at full bus rate would need a deeper capture path.
module rv_monitor_xtor_core (
    input             clock,
    input             reset,
    output bit [31:0] up_data,             // ready/valid link (to xtor_if)
    output bit        up_valid,
    input             up_ready,
    input             valid,               // bus taps (observed, never driven)
    input             ready,
    input  [31:0]     data
);
    typedef enum bit [0:0] {WATCH, PRESENT} state_t;
    state_t st;
    always @(posedge clock) begin
        if (reset) begin
            st <= WATCH; up_valid <= 1'b0; up_data <= '0;
        end else case (st)
            WATCH:   if (valid && ready) begin        // observed a bus transfer
                         up_data <= data; up_valid <= 1'b1; st <= PRESENT;
                     end
            PRESENT: if (up_valid && up_ready) begin  // link transfer happened
                         up_valid <= 1'b0; st <= WATCH;
                     end
            default: ;
        endcase
    end
endmodule

// 3. Transactor module: core + interface wired by the plain ready/valid link.
module rv_monitor_xtor (
    input             clock,
    input             reset,
    input         valid,
    input         ready,
    input  [31:0] data
);
    bit [31:0] up_data;
    bit        up_valid;
    bit        up_ready;

    rv_monitor_xtor_if u_if (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready)
    );
    rv_monitor_xtor_core u_core (
        .clock(clock), .reset(reset),
        .up_data(up_data), .up_valid(up_valid), .up_ready(up_ready),
        .valid(valid), .ready(ready), .data(data)
    );
endmodule
