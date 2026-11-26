// The Wishbone initiator's sync core (sync-task-domains.md §5.1, Pattern 1):
// all of the protocol's timing, as ordinary step()/comb() code. It is the
// class form of fw-proto-wb's wb_initiator_xtor_core (ref/), and lowers to
// RTL equivalent to it (scripts/equiv.sh):
//   - a consumer on the request link: ready while idle;
//   - a producer on the response link: valid on the termination cycle,
//     comb from ack/err/rty; the phase (stb) is held until the response is
//     taken;
//   - the master on the bus: one classic cycle per request, the qualified
//     signals held stable until ACK|ERR|RTY (RULE 3.60).
// The task side (wb_init) reaches it only through the generic endpoints.
class wb_init_core extends fw_component implements fw_steppable, fw_combinational;
    fw_rv_sp_in  #(wb_req_t) req;
    fw_rv_sp_out #(wb_rsp_t) rsp;
    wb_sp_out                wb;

    bit waiting;   // a bus phase is in progress (== stb)
    bit hold;      // cyc_hold of the phase in progress

    function new(string name, fw_component parent);
        super.new(name, parent);
        req = new(null, "req", this);
        rsp = new(null, "rsp", this);
        wb  = new(null, "wb", this);
        // The comb fields (the lowering derives them from comb()).
        req.sig.set_comb("ready");
        rsp.sig.set_comb("valid, data");
        add_steppable(this);
        add_comb(this);
    endfunction

    // The response on the termination cycle; a request is taken only while
    // idle, whatever req.valid is.
    virtual function void comb();
        wb_rsp_t r;
        r.dat = wb.get_dat_r();
        r.err = wb.get_err();
        r.rty = wb.get_rty();
        rsp.set_valid(waiting && (wb.get_ack() || wb.get_err() || wb.get_rty()));
        rsp.set_data(r);
        req.set_ready(!waiting);
    endfunction

    virtual function void step();
        if (in_reset()) begin
            waiting = 0;
            hold    = 0;
            wb.set_adr(0);
            wb.set_dat_w(0);
            wb.set_sel(0);
            wb.set_we(0);
            wb.set_cyc(0);
            wb.set_stb(0);
        end else if (req.get_valid() && req.get_ready()) begin
            // Launch a phase from idle.
            wb_req_t q = req.get_data();
            wb.set_adr(q.adr);
            wb.set_dat_w(q.dat);
            wb.set_sel(q.sel);
            wb.set_we(q.we);
            wb.set_cyc(1);
            wb.set_stb(1);
            hold    = q.cyc_hold;
            waiting = 1;
        end else if (rsp.get_valid() && rsp.get_ready()) begin
            // The response is taken: end the phase, cyc held for a chain.
            wb.set_stb(0);
            wb.set_cyc(hold);
            waiting = 0;
        end
    endfunction
endclass
