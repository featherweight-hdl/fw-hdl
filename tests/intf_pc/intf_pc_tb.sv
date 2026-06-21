
// Producer/consumer demonstration of the fw interface-protocol pattern,
// connected through the fw_port/fw_export deferred-binding wrappers.
//
// The reusable infrastructure (fw_component, fw_port, fw_export) comes from
// fw_pkg. The "send" *protocol* used to exercise it -- its interface-class API
// and its implementation-template macro -- is defined here in the test, since
// it is test scaffolding rather than a generic library feature.
//
// Three "key elements" are exercised:
//
//   1. The pure-virtual interface-class API (fw_send_if #(T), below). The
//      *producer* talks to its peer purely through this API; it knows nothing
//      about who implements it.
//
//   2. The implementation-template macro (`FW_SEND_IMP, below). The *consumer*
//      uses it to stamp out the imp (a proxy that `implements fw_send_if #(T)`
//      and redirects send() to a method on the consumer) and an fw_export that
//      publishes that imp.
//
//   3. The deferred-binding wrappers. The producer holds an fw_port (an
//      implementation *consumer*); the consumer holds an fw_export (an
//      implementation *provider*). A top-level component instances both and,
//      in its connect(), wires the port to the export:
//
//          prod.out.connect(cons.send_export)
//
//      The producer resolves the bound implementation lazily, at run time, via
//      out.get_if().

// ----------------------------------------------------------------------
// Key element 2: the implementation template for the "send" protocol.
//
// `FW_SEND_IMP(T, IMP, NAME)`, used inside a class body, stamps out:
//   1. a proxy class `NAME``_imp_t` that BOTH `extends fw_export #(fw_send_if
//      #(T))` and `implements fw_send_if #(T)` -- so one object is at once the
//      export (a provider that ports connect to) and the imp (the terminal
//      implementation). Its new() registers itself (`this`) as the export's
//      implementation and records `imp` as its hierarchy parent; and
//   2. a member `NAME` of that type.
//
// By convention each API method redirects to `imp.NAME``_<method>()` -- here
// send() redirects to `imp.NAME``_send()`. The NAME prefix lets one component
// provide several exports of the same protocol without method-name clashes,
// and the per-method suffix extends naturally when the protocol has more than
// one method.
//
// The providing component just news the member and hands it `this`:
//
//     `FW_SEND_IMP(data_t, consumer, in)   // implement via in_send()
//     ...
//     function void build(); in = new(this); endfunction
//     virtual task in_send(input data_t t); ... endtask
// ----------------------------------------------------------------------
`define FW_SEND_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(fw_send_if #(T)) \
            implements fw_send_if #(T); \
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

module intf_pc_tb;
    import fw_pkg::*;

    typedef bit [31:0] data_t;

    // ------------------------------------------------------------------
    // Key element 1: the pure-virtual interface-class API.
    // ------------------------------------------------------------------
    interface class fw_send_if #(type T);
        pure virtual task send(input T t);
    endclass

    // ------------------------------------------------------------------
    // Producer: consumes the send API through a port.
    // ------------------------------------------------------------------
    class producer extends fw_component;
        fw_port #(fw_send_if #(data_t)) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            out = new("out", this);
        endfunction

        virtual task run();
            // Resolve the bound implementation, then drive it.
            fw_send_if #(data_t) api = out.get_if();
            for (int i = 0; i < 4; i++) begin
                automatic data_t v = 32'hdead_0000 + i;
                $display("[producer] send 0x%08h", v);
                api.send(v);
            end
        endtask
    endclass

    // ------------------------------------------------------------------
    // Consumer: provides the send API via the implementation-template macro.
    // ------------------------------------------------------------------
    class consumer extends fw_component;
        data_t received[$];

        // Stamps out the proxy class `in_imp_t` (which is both the export and
        // the imp) and the member `in`. By convention send() on it is
        // redirected to in_send() below.
        `FW_SEND_IMP(data_t, consumer, in);

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            // Single new, handing the export/imp `this`.
            in = new(this);
        endfunction

        // The actual implementation the imp redirects to (NAME_send).
        virtual task in_send(input data_t t);
            $display("[consumer] recv 0x%08h", t);
            received.push_back(t);
        endtask
    endclass

    // ------------------------------------------------------------------
    // Top: instances producer + consumer and connects them.
    // ------------------------------------------------------------------
    class pc_top extends fw_component;
        producer prod;
        consumer cons;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            prod = new("prod", this);
            cons = new("cons", this);
            prod.build();
            cons.build();
        endfunction

        function void connect();
            // port (consumer) connects to export (provider).
            prod.out.connect(cons.in);
        endfunction

        virtual task run();
            prod.run();
        endtask
    endclass

    initial begin
        pc_top top;
        int errors = 0;

        top = new("top", null);
        top.build();
        top.connect();
        top.run();

        // Check what arrived at the consumer.
        if (top.cons.received.size() != 4) begin
            $display("FAIL: expected 4 items, got %0d", top.cons.received.size());
            errors++;
        end else begin
            for (int i = 0; i < 4; i++) begin
                automatic data_t exp = 32'hdead_0000 + i;
                if (top.cons.received[i] !== exp) begin
                    $display("FAIL: item %0d expected 0x%08h got 0x%08h",
                             i, exp, top.cons.received[i]);
                    errors++;
                end
            end
        end

        if (errors == 0)
            $display("[intf_pc] PASS");
        else
            $display("[intf_pc] FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
