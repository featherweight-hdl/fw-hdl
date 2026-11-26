// T5 hand-written reference (docs/design/xtor-shell-plan.md): what the
// generator must emit for wb_target's interface. It is the task side of
// the transactor's crossings, over the core's ready/valid ports: one task
// per process-side crossing method, with the crossing semantics of
// fw-hdl-spec semantics/processes.md (X3-X8):
//
// - reqs (fw_from_sync, depth 1): reqs_get(req). Waits for an item, and
//   returns at the edge that gives it (X5). reqs_wait is waiting() (X6).
// - rsps (fw_to_sync, depth 1): rsps_put(rsp). Waits for room; with depth 1
//   returns at the edge where its item is taken (X6).
//
// It is wb_initiator_xtor_if with the crossings' roles swapped: the
// template is per crossing direction, not per transactor. The
// transactor's own task code (run: reqs.get(r); p.access(s, r);
// rsps.put(s)) is the bridge's, calling these through a virtual interface.
//
// Synthesizable form and timing: as wb_initiator_xtor_if. Tasks wait only
// on @(posedge clock); one writer per variable (tasks: reqs_got,
// reqs_wait, rsps_put_t, rsps_data; the clock: reqs_gave, reqs_q,
// rsps_took); a slot is full when its toggles differ; tasks decide from
// this edge's handshake (valid && ready) and write with <= only.
interface wb_target_xtor_if(input logic clock);
    import wb_target_xtor_lowered_types_pkg::*;  // the core's (emit_core.py)

    // reqs: core -> task side. The slot fills at a giving edge that no
    // reqs_get takes.
    logic reqs_gave, reqs_got, reqs_wait;
    logic reqs_valid, reqs_ready, reqs_full;
    req_t reqs_data, reqs_q;
    assign reqs_full  = reqs_gave ^ reqs_got;
    assign reqs_ready = !reqs_full;
    always @(posedge clock) if (reqs_valid && reqs_ready && !reqs_wait) begin
        reqs_gave <= ~reqs_gave;
        reqs_q    <= reqs_data;
    end

    // rsps: task side -> core. Full from rsps_put until the edge that
    // takes it.
    logic rsps_put_t, rsps_took;
    logic rsps_valid, rsps_ready;
    rsp_t rsps_data;
    assign rsps_valid = rsps_put_t ^ rsps_took;
    always @(posedge clock) if (rsps_valid && rsps_ready) rsps_took <= ~rsps_took;

    // reqs.get: the slot's item; else one given at this edge; else wait
    // for the edge that gives one (it goes to the waiter, not the slot).
    task automatic reqs_get(output req_t req);
        if (reqs_full) begin
            req = reqs_q;
            reqs_got <= ~reqs_got;
        end else if (reqs_valid && reqs_ready && !reqs_wait) begin
            req = reqs_data;
            reqs_got <= ~reqs_got;
        end else begin
            reqs_wait <= 1;
            do @(posedge clock); while (!(reqs_valid && reqs_ready));
            req = reqs_data;
            reqs_wait <= 0;
        end
    endtask

    // rsps.put: waits out an item still pending, fills the slot, returns
    // at the edge that takes it.
    task automatic rsps_put(input rsp_t rsp);
        while (rsps_valid && !rsps_ready) @(posedge clock);
        rsps_data  <= rsp;
        rsps_put_t <= ~rsps_put_t;
        do @(posedge clock); while (!rsps_ready);
    endtask

    initial begin reqs_gave = 0; reqs_got = 0; reqs_wait = 0; rsps_put_t = 0; rsps_took = 0; end
endinterface
