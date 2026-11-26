// wb: Wishbone (classic, one access in flight) as a protocol package on the
// canonical API (fw-hdl-spec, fw-hdl-rt-sv). The protocol, its bundle, and
// the two transactors: each one class with an export (or port) of the API
// on one side and the bundle on the other. The API is wb_api_pkg's (no
// fw-hdl dependency), exported from here.
// Everything takes the bus's parameters: AW, the address width, and DW, the
// data width (a whole number of bytes).
`include "fw_hdl_macros.svh"

package wb_pkg;
    import fw_hdl_pkg::*;
    import fw_hdl_std_pkg::*;
    import wb_api_pkg::*;
    export wb_api_pkg::*;

    // The protocol.
    class wb_proto #(int AW = 32, int DW = 32) extends fw_protocol;
        typedef wb_proto #(AW, DW) this_t;
        `fw_protocol_param_utils(wb_proto, wb_if #(AW, DW))
    endclass

    // The pins, from the initiator's view.
    virtual class wb_bundle #(int AW = 32, int DW = 32) extends fw_bundle_base;
        `fw_bundle_utils(wb_bundle, wb_proto #(AW, DW))
        fw_output #(bit [AW-1:0])   adr;
        fw_output #(bit [DW-1:0])   dat_w;
        fw_output #(bit [DW/8-1:0]) sel;
        fw_output #(bit)            we;
        fw_output #(bit)            cyc;
        fw_output #(bit)            stb;
        fw_input  #(bit [DW-1:0])   dat_r;
        fw_input  #(bit)            ack;
        fw_input  #(bit)            err;

        virtual function void build();
            adr   = fw_output #(bit [AW-1:0])  ::create("adr",   this);
            dat_w = fw_output #(bit [DW-1:0])  ::create("dat_w", this);
            sel   = fw_output #(bit [DW/8-1:0])::create("sel",   this);
            we    = fw_output #(bit)           ::create("we",    this);
            cyc   = fw_output #(bit)           ::create("cyc",   this);
            stb   = fw_output #(bit)           ::create("stb",   this);
            dat_r = fw_input  #(bit [DW-1:0])  ::create("dat_r", this);
            ack   = fw_input  #(bit)           ::create("ack",   this);
            err   = fw_input  #(bit)           ::create("err",   this);
        endfunction
    endclass

    // The initiator transactor. A call drives the request in the cycle it
    // is made (cyc and stb high) and returns at the edge where the target
    // terminates it (ack or err). Nothing is buffered. ``access`` only
    // hands the request to the sync code and waits for the response,
    // through two crossings (semantics/processes.md, "Task-sync
    // crossings"); ``comb()`` drives the bus from the waiting request, and
    // ``step()`` takes it and gives the response at the termination. There
    // is no thread, and a back-to-back ``access`` keeps stb high::
    //
    //     wb_initiator #(32, 32) x;
    //     ...
    //     x.pins.connect(dut_wb);          // in connect()
    //     drv.p.connect(x.t);
    class wb_initiator #(int AW = 32, int DW = 32)
            extends fw_xtor_initiator #(wb_bundle #(AW, DW))
            implements wb_if #(AW, DW), fw_comb_if, fw_step_if;
        typedef wb_initiator #(AW, DW) this_t;
        `fw_xtor_param_utils(wb_initiator)
        // The API's payloads: a class that implements an interface class
        // does not inherit its typedefs.
        typedef wb_if #(AW, DW)::req_t req_t;
        typedef wb_if #(AW, DW)::rsp_t rsp_t;

        fw_to_sync   #(req_t) reqs;   // the access in progress
        fw_from_sync #(rsp_t) rsps;   // its response

        // Creates ``pins`` and ``t`` (the base), and the crossings.
        virtual function void build();
            super.build();
            reqs = fw_to_sync   #(req_t)::create("reqs", this);
            rsps = fw_from_sync #(rsp_t)::create("rsps", this);
        endfunction

        // Makes one access and returns at the edge where it terminates.
        virtual task access(output rsp_t rsp, input req_t req);
            reqs.put(req);
            rsps.get(rsp);
        endtask

        // Drives the waiting request; idle when there is none. A cycle
        // starts only while ``rsps`` has room: the target's termination
        // can't be refused, so ``step()``'s ``give`` must not fail.
        virtual function void comb();
            req_t r = reqs.peek();
            bit      v = reqs.valid() && rsps.ready();
            pins.cyc.write(v);
            pins.stb.write(v);
            pins.adr.write(r.adr);
            pins.dat_w.write(r.dat);
            pins.sel.write(r.sel);
            pins.we.write(r.we);
        endfunction

        // At the termination: takes the request and gives the response
        // (``comb()`` raised ``stb`` only with room for it).
        virtual function void step();
            req_t r;
            rsp_t p;
            if (pins.stb.read() && (pins.ack.read() || pins.err.read())) begin
                void'(reqs.take(r));
                p.dat = pins.dat_r.read();
                p.err = pins.err.read();
                void'(rsps.give(p));
            end
        endfunction
    endclass

    // The target transactor: each request seen at the pins is passed on as
    // an ``access`` call through ``p``, and terminated (ack, or err) from
    // the edge after the call returns. While the callee blocks, the
    // initiator sees wait states. The pin timing is sync code: ``step()``
    // gives each request to ``run()`` and takes the response at the
    // termination; ``comb()`` drives the termination while a response
    // waits. ``run()`` only makes the call::
    //
    //     wb_target #(32, 32) x;
    //     ...
    //     x.pins.connect(...);             // in connect()
    //     x.p.connect(mem.t);
    class wb_target #(int AW = 32, int DW = 32)
            extends fw_xtor_target #(wb_bundle #(AW, DW))
            implements fw_run_if, fw_comb_if, fw_step_if;
        typedef wb_target #(AW, DW) this_t;
        `fw_xtor_param_utils(wb_target)
        typedef wb_if #(AW, DW)::req_t req_t;
        typedef wb_if #(AW, DW)::rsp_t rsp_t;

        fw_from_sync #(req_t) reqs;   // requests, for run()
        fw_to_sync   #(rsp_t) rsps;   // their responses
        bit busy;                       // a request is with run()

        // Creates ``pins`` and ``p`` (the base), and the crossings.
        virtual function void build();
            super.build();
            reqs = fw_from_sync #(req_t)::create("reqs", this);
            rsps = fw_to_sync   #(rsp_t)::create("rsps", this);
        endfunction

        // Calls ``access`` for each request.
        virtual task run();
            wb_if #(AW, DW) i = p.get_if();
            req_t r;
            rsp_t s;
            forever begin
                reqs.get(r);
                i.access(s, r);
                rsps.put(s);
            end
        endtask

        // Terminates while a response waits.
        virtual function void comb();
            rsp_t s = rsps.peek();
            bit      v = rsps.valid();
            pins.dat_r.write(s.dat);
            pins.ack.write(v && !s.err);
            pins.err.write(v && s.err);
        endfunction

        // Gives each new request to ``run()``; takes the response at the
        // termination.
        virtual function void step();
            req_t r;
            rsp_t s;
            if (busy) begin
                if (pins.ack.read() || pins.err.read()) begin
                    void'(rsps.take(s));
                    busy = 0;
                end
            end else if (pins.cyc.read() && pins.stb.read()) begin
                r.adr = pins.adr.read();
                r.dat = pins.dat_w.read();
                r.sel = pins.sel.read();
                r.we  = pins.we.read();
                busy  = reqs.give(r);
            end
        endfunction
    endclass
endpackage
