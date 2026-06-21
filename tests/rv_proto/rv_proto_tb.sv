
// Ready/valid protocol-kit demonstration with the FULL three-component
// transactor structure (see skills/fw-proto-kit). Per role:
//
//   1. transactor-interface SV interface (rv_*_xtor_if) -- implements the API
//      methods (send/recv) over an internal DEPTH-deep FIFO, and is a ready/valid
//      endpoint on an internal LINK to the core. send()/recv() only touch the
//      FIFO (send blocks only when full, recv only when empty); a clocked always
//      block drains/fills the FIFO across the link. This lets the caller PIPELINE
//      -- run ahead by up to DEPTH beats, decoupled from the link/bus round-trip.
//      The link is ALWAYS a plain ready/valid channel (`up_valid`/`up_data`/
//      `up_ready`); it never adopts the external protocol's language. FIFO DEPTH
//      is a fixed protocol property set inside the interface (a localparam), NOT
//      a port parameter -- see the Verilator note below.
//   2. core transactor module (rv_*_xtor_core) -- a clocked FSM that is a
//      ready/valid endpoint on the internal link and runs the signal-level
//      protocol on the pins (for ready/valid the pins ARE ready/valid). A richer
//      protocol (e.g. wishbone) elaborates a larger pin-level FSM here; the
//      internal ready/valid link contract is unchanged.
//   3. transactor module (rv_*_xtor) -- instances the interface + core and
//      wires the ready/valid link between them with plain nets, exposing
//      clock/reset + pins.
//
// On top of that sit the class-level pieces:
//   * API interface-classes (rv_initiator_if / rv_target_if), each shipping its
//     `FW_RV_*_IMP implementation macro.
//   * Bridge classes holding a virtual transactor-interface and implementing /
//     consuming the API (initiator = provider/export, target = port).
//   * driver (port) pushes beats; sink (export) receives them.
//
// The two transactor modules share one ready/valid bus, so every beat crosses
// the real handshake; the target bridge applies backpressure.
//
// DESIGN NOTES (what makes the clocked-core split correct):
//   * Every interface and module is CLOCKED (has clock/reset). In this flow a
//     module/core output is only reliably observed by another block's clocked
//     sampling when it is REGISTERED -- a combinational drive into an interface
//     input port loses the value to a delta-cycle race. Real protocol cores are
//     clocked FSMs anyway, so this is the natural form.
//   * The interface<->core link is ALWAYS a plain ready/valid channel (never the
//     external protocol's language), and a real clocked handshake -- not a bare
//     registered passthrough. A passthrough merely delays the signals, and the
//     latency lets the consumer re-sample a beat the producer has not yet
//     advanced past (duplicated beats). A proper ready/valid handshake transfers
//     exactly one beat per (valid && ready) cycle on each side.
//   * Parameterize SYMMETRICALLY or not at all. A parameter on the interface
//     mangles its type (e.g. rv_initiator_xtor_if__D4), so EVERY element naming
//     that type must carry the same parameter -- the `virtual` handle, bridge,
//     wrapper. Asymmetry (a #(.DEPTH(4)) instance bound to a plain
//     `virtual rv_initiator_xtor_if`) gives Verilator "expected ... interface but
//     ... is a different interface". Fixed properties like FIFO DEPTH are kept as
//     internal localparams so no parameter is threaded through every element.
//   * Verilator quirks (rev v5.049): a parameterized interface as a MODULE PORT
//     crashes elaboration (V3Param.cpp:523), and a `type`-parameterized interface
//     INSTANCE does not receive externally-driven input values. So the
//     transactor interfaces/cores are concrete (logic [31:0]) while the class
//     layer stays parameterized. Full simulators (Questa/VCS/Xcelium) support
//     the parameterized form; that is the production structure.

// ----------------------------------------------------------------------
// Implementation-template macros provided by the rv APIs. EVERY API ships one,
// and any implementation of that API MUST use it to define the implementation
// redirect rather than hand-rolling the fw_export proxy.
//
// `FW_RV_INITIATOR_IMP(T, IMP, NAME) -- export NAME whose send() redirects to
//   IMP's NAME_send().
// `FW_RV_TARGET_IMP(T, IMP, NAME)    -- export NAME whose put() redirects to
//   IMP's NAME_put().
// ----------------------------------------------------------------------
`define FW_RV_INITIATOR_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(rv_initiator_if #(T)) \
            implements rv_initiator_if #(T); \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction \
        virtual task send(input T t); \
            m_imp.NAME``_send(t); \
        endtask \
    endclass \
    NAME``_imp_t NAME

`define FW_RV_TARGET_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(rv_target_if #(T)) \
            implements rv_target_if #(T); \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction \
        virtual task put(input T t); \
            m_imp.NAME``_put(t); \
        endtask \
    endclass \
    NAME``_imp_t NAME

// `FW_RV_MONITOR_IMP(T, IMP, NAME) -- export NAME whose observe() redirects to
//   IMP's NAME_observe(). NOTE: observe() is a FUNCTION (non-blocking) -- monitor
//   APIs may not block.
`define FW_RV_MONITOR_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(rv_monitor_if #(T)) \
            implements rv_monitor_if #(T); \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction \
        virtual function void observe(input T t); \
            m_imp.NAME``_observe(t); \
        endfunction \
    endclass \
    NAME``_imp_t NAME

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

module rv_proto_tb;
    import fw_pkg::*;

    typedef logic [31:0] data_t;

    localparam int unsigned N = 8;

    // --------------------------------------------------------------
    // API interface-classes: the class-level contract for each role.
    // --------------------------------------------------------------
    // Initiator API: hand a beat to the protocol (blocks until accepted).
    interface class rv_initiator_if #(type T);
        pure virtual task send(input T t);
    endclass

    // Target API: accept a beat delivered by the protocol. The target
    // transactor (a port) calls put(); the connected component implements it.
    interface class rv_target_if #(type T);
        pure virtual task put(input T t);
    endclass

    // Monitor API: observe a beat seen on the bus. NON-BLOCKING (a function) --
    // monitor APIs may not block. The monitor transactor (a port) calls
    // observe(); the connected subscriber implements it.
    interface class rv_monitor_if #(type T);
        pure virtual function void observe(input T t);
    endclass

    // --------------------------------------------------------------
    // Bridge classes: hold a virtual transactor-interface and implement /
    // consume the API.
    //
    //   * The INITIATOR bridge is a PROVIDER. It implements rv_initiator_if via
    //     the API's `FW_RV_INITIATOR_IMP macro (never hand-rolled); send()
    //     redirects to exp_send(), which calls vif.send(). The driver's port
    //     connects to its export member `exp`.
    //   * The TARGET bridge is a CONSUMER: it extends fw_port #(rv_target_if)
    //     and runs an active loop (vif.recv a beat, then put() it), connecting
    //     up to the component that implements the API.
    //
    // The class layer stays parameterized (#(type T)); the virtual transactor
    // interface is concrete (see Verilator quirks in the file header).
    // --------------------------------------------------------------
    class rv_initiator_bridge #(type T) extends fw_component;
        virtual rv_initiator_xtor_if vif;

        `FW_RV_INITIATOR_IMP(T, rv_initiator_bridge #(T), exp);

        function new(string name, fw_component parent,
                     virtual rv_initiator_xtor_if vif);
            super.new(name, parent);
            this.vif = vif;
            exp = new(this);
        endfunction

        virtual task exp_send(input T t);
            vif.send(t);
        endtask
    endclass

    class rv_target_bridge #(type T) extends fw_port #(rv_target_if #(T));
        virtual rv_target_xtor_if vif;

        function new(string name, fw_component parent,
                     virtual rv_target_xtor_if vif);
            super.new(name, parent);
            this.vif = vif;
        endfunction

        task run();
            rv_target_if #(T) api = get_if();
            forever begin
                automatic T t;
                #17ns;                 // idle: ready low -> backpressure
                vif.recv(t);
                api.put(t);
            end
        endtask
    endclass

    //   * The MONITOR bridge is a CONSUMER like the target: it extends
    //     fw_port #(rv_monitor_if) and runs an active loop. It BLOCKS on
    //     vif.get(t) (the transactor-interface's blocking method) and then fans
    //     the beat out via the NON-BLOCKING monitor API observe().
    class rv_monitor_bridge #(type T) extends fw_port #(rv_monitor_if #(T));
        virtual rv_monitor_xtor_if vif;

        function new(string name, fw_component parent,
                     virtual rv_monitor_xtor_if vif);
            super.new(name, parent);
            this.vif = vif;
        endfunction

        task run();
            rv_monitor_if #(T) api = get_if();
            forever begin
                automatic T t;
                vif.get(t);            // blocking: next observed beat
                api.observe(t);        // non-blocking: publish to subscriber
            end
        endtask
    endclass

    // --------------------------------------------------------------
    // Driver: consumes the initiator API through a port.
    // --------------------------------------------------------------
    class driver extends fw_component;
        fw_port #(rv_initiator_if #(data_t)) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            out = new("out", this);
        endfunction

        virtual task run();
            rv_initiator_if #(data_t) api = out.get_if();
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t v = 32'hcafe_0000 + i;
                api.send(v);
                $display("[driver]  sent 0x%08h @ %0t", v, $time);
            end
        endtask
    endclass

    // --------------------------------------------------------------
    // Sink: PROVIDES the rv_target_if implementation (via the API macro).
    // --------------------------------------------------------------
    class sink extends fw_component;
        data_t received[$];

        `FW_RV_TARGET_IMP(data_t, sink, in);

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            in = new(this);
        endfunction

        virtual task in_put(input data_t t);
            received.push_back(t);
            $display("[sink]    put  0x%08h @ %0t", t, $time);
        endtask
    endclass

    // --------------------------------------------------------------
    // Observer: PROVIDES the rv_monitor_if implementation (via the API macro).
    // A passive subscriber -- records every beat the monitor publishes.
    // --------------------------------------------------------------
    class observer extends fw_component;
        data_t seen[$];

        `FW_RV_MONITOR_IMP(data_t, observer, mon);

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            mon = new(this);
        endfunction

        virtual function void mon_observe(input data_t t);
            seen.push_back(t);
            $display("[monitor] observed 0x%08h @ %0t", t, $time);
        endfunction
    endclass

    // --------------------------------------------------------------
    // Top: instances driver + sink, builds the bridges over the two transactor
    // interfaces, and connects each to its peer.
    // --------------------------------------------------------------
    class rv_top extends fw_component;
        driver   drv;
        sink     chk;
        observer obs;
        rv_target_bridge  #(data_t) tbr;
        rv_monitor_bridge #(data_t) mbr;
        virtual rv_initiator_xtor_if vif_init;
        virtual rv_target_xtor_if    vif_targ;
        virtual rv_monitor_xtor_if   vif_mon;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            drv = new("drv", this);
            chk = new("chk", this);
            obs = new("obs", this);
            drv.build();
            chk.build();
            obs.build();
        endfunction

        function void connect();
            // Initiator transactor: the driver's port connects to its export.
            rv_initiator_bridge #(data_t) ibr =
                new("init_bridge", this, vif_init);
            drv.out.connect(ibr.exp);

            // Target transactor: a port that calls into the sink's export.
            tbr = new("targ_bridge", this, vif_targ);
            tbr.connect(chk.in);

            // Monitor transactor: a port that publishes to the observer's export.
            mbr = new("mon_bridge", this, vif_mon);
            mbr.connect(obs.mon);
        endfunction
    endclass

    // --------------------------------------------------------------
    // Signal-level setup: the two transactor modules on a shared ready/valid bus.
    // --------------------------------------------------------------
    logic clock = 1'b0;
    logic reset = 1'b1;

    bit        bus_valid;
    bit        bus_ready;
    bit [31:0] bus_data;

    always #5ns clock = ~clock;

    // Bus monitor: shows the initiator's driven output and the target's ready
    // on the actual wires (no reaching into interfaces).
    always @(posedge clock) if (!reset)
        $display("[bus]          valid=%b data=0x%08h ready=%b @ %0t",
                 bus_valid, bus_data, bus_ready, $time);

    // The two transactor modules (each bundles its xtor_if + core via an internal
    // ready/valid link) wired together on the shared ready/valid bus. Each
    // xtor_if has an internal pipeline FIFO (depth is a protocol property set in
    // the interface), so the caller can run ahead of the bus round-trip.
    rv_initiator_xtor init_xtor (
        .clock(clock), .reset(reset),
        .data(bus_data), .valid(bus_valid), .ready(bus_ready)
    );
    rv_target_xtor targ_xtor (
        .clock(clock), .reset(reset),
        .valid(bus_valid), .ready(bus_ready), .data(bus_data)
    );
    // Monitor transactor: passively taps the same bus (drives nothing).
    rv_monitor_xtor mon_xtor (
        .clock(clock), .reset(reset),
        .valid(bus_valid), .ready(bus_ready), .data(bus_data)
    );

    initial begin
        automatic rv_top top;
        automatic int errors = 0;

        // Reset, then release.
        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        top = new("top", null);
        top.vif_init = init_xtor.u_if;   // reach into the transactor module
        top.vif_targ = targ_xtor.u_if;
        top.vif_mon  = mon_xtor.u_if;
        top.build();
        top.connect();

        // Start the target + monitor sampling loops, then push N beats.
        fork
            top.tbr.run();
            top.mbr.run();
        join_none
        top.drv.run();

        // Drain: wait until every beat has reached BOTH the sink and the monitor.
        while (top.chk.received.size() < N || top.obs.seen.size() < N)
            @(posedge clock);

        // Check: every beat arrived at the sink, in order, unchanged.
        if (top.chk.received.size() != N) begin
            $display("FAIL: expected %0d beats, got %0d", N, top.chk.received.size());
            errors++;
        end else begin
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t exp = 32'hcafe_0000 + i;
                if (top.chk.received[i] !== exp) begin
                    $display("FAIL: beat %0d expected 0x%08h got 0x%08h",
                             i, exp, top.chk.received[i]);
                    errors++;
                end
            end
        end

        // Check: the monitor observed the same N beats, in order.
        if (top.obs.seen.size() != N) begin
            $display("FAIL: monitor expected %0d beats, got %0d", N, top.obs.seen.size());
            errors++;
        end else begin
            for (int unsigned i = 0; i < N; i++) begin
                automatic data_t exp = 32'hcafe_0000 + i;
                if (top.obs.seen[i] !== exp) begin
                    $display("FAIL: monitor beat %0d expected 0x%08h got 0x%08h",
                             i, exp, top.obs.seen[i]);
                    errors++;
                end
            end
        end

        if (errors == 0)
            $display("[rv_proto] PASS");
        else
            $display("[rv_proto] FAIL (%0d errors)", errors);
        $finish;
    end

    // Watchdog so a broken handshake fails fast instead of hanging.
    initial begin
        #100us;
        $fatal(1, "[rv_proto] TIMEOUT");
    end
endmodule
