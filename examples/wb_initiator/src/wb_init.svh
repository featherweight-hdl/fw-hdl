// The Wishbone initiator (sync-task-domains.md §4, §5.1): the sync core and,
// on the task side, only the generic ready/valid endpoints. access() has no
// timing of its own: put() returns at the edge the core takes the request,
// get() at the edge the response is taken (C7), and the endpoints' defaults
// drop valid and ready unless the next call raises them at that edge (C5).
class wb_init extends fw_component;
    wb_init_core             core;
    fw_rv_put_ep #(wb_req_t) ereq;
    fw_rv_get_ep #(wb_rsp_t) ersp;
    wb_sp_out                wb;    // the bus, driven by the core

    function new(string name, fw_component parent);
        super.new(name, parent);
        core = new("core", this);
        ereq = new("ereq", this);
        ersp = new("ersp", this);
        wb   = new(null, "wb", this);
        ereq.out.connect(core.req);
        core.rsp.connect(ersp.in);
        core.wb.connect_up(wb);
    endfunction

    // One bus cycle: r, then its response.
    task access(wb_req_t r, output wb_rsp_t p);
        ereq.put(r);
        ersp.get(p);
    endtask

    task write(wb_adr_t adr, wb_dat_t dat, output wb_rsp_t p);
        wb_req_t r = '{adr: adr, dat: dat, sel: '1, we: 1, cyc_hold: 0};
        access(r, p);
    endtask

    task read(wb_adr_t adr, output wb_rsp_t p);
        wb_req_t r = '{adr: adr, dat: 0, sel: '1, we: 0, cyc_hold: 0};
        access(r, p);
    endtask
endclass
