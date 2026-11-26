// T0 hand-written reference (docs/design/xtor-shell-plan.md): what the
// generator must emit for wb_initiator's interface. It is the task side of
// the transactor's crossings, over the core's ready/valid ports: one task
// per process-side crossing method, with the crossing semantics of
// fw-hdl-spec semantics/processes.md (X3-X8):
//
// - reqs (fw_to_sync, depth 1): reqs_put(req). Waits for room; with depth 1
//   returns at the edge where its item is taken (X6).
// - rsps (fw_from_sync, depth 1): rsps_get(rsp). Waits for an item, and
//   returns at the edge that gives it (X5). rsps_wait is waiting() (X6).
//
// The transactor's own task code (access: reqs.put(req); rsps.get(rsp))
// calls these through a virtual interface.
//
// Synthesizable form (emulation): the tasks wait only on @(posedge clock),
// and every variable has one writer (tasks: reqs_put_t, reqs_data,
// rsps_got, rsps_wait; the clock: reqs_took, rsps_gave, rsps_q). A slot is
// full when its two toggles differ.
//
// Timing. Tasks are called at a clock edge (class threads run only at
// edges) and wake at one. Either way they run before the edge's <=
// updates land, so they see the values from before the edge and decide
// from this edge's handshake (valid && ready), not from the registers,
// which lag it by the update. Every write is <=, so nothing a task does at
// an edge changes what that edge samples (X4).
interface wb_initiator_xtor_if(input logic clock);
    import wb_initiator_xtor_lowered_types_pkg::*;  // the core's (emit_core.py)

    // reqs: task side -> core. Full from reqs_put until the edge that
    // takes it.
    logic reqs_put_t, reqs_took;
    logic reqs_valid, reqs_ready;
    req_t reqs_data;
    assign reqs_valid = reqs_put_t ^ reqs_took;
    always @(posedge clock) if (reqs_valid && reqs_ready) reqs_took <= ~reqs_took;

    // rsps: core -> task side. The slot fills at a giving edge that no
    // rsps_get takes.
    logic rsps_gave, rsps_got, rsps_wait;
    logic rsps_valid, rsps_ready, rsps_full;
    rsp_t rsps_data, rsps_q;
    assign rsps_full  = rsps_gave ^ rsps_got;
    assign rsps_ready = !rsps_full;
    always @(posedge clock) if (rsps_valid && rsps_ready && !rsps_wait) begin
        rsps_gave <= ~rsps_gave;
        rsps_q    <= rsps_data;
    end

    // fw_to_sync::put. Room at this edge: the slot is empty, or the core
    // takes its item now. Depth 1: return at the edge that takes ours.
    task automatic reqs_put(input req_t req);
        while (reqs_valid && !reqs_ready) @(posedge clock);
        reqs_data  <= req;
        reqs_put_t <= ~reqs_put_t;
        do @(posedge clock); while (!reqs_ready);
    endtask

    // fw_from_sync::get. An item given at an earlier edge is in the slot.
    // One given at this edge, with no get already waiting for it, is taken
    // from the ports now (the slot fills too; rsps_got empties it). Else
    // wait for the edge that gives one; the waiting get takes it there and
    // the slot stays empty.
    task automatic rsps_get(output rsp_t rsp);
        if (rsps_full) begin
            rsp = rsps_q;
            rsps_got <= ~rsps_got;
        end else if (rsps_valid && rsps_ready && !rsps_wait) begin
            rsp = rsps_data;
            rsps_got <= ~rsps_got;
        end else begin
            rsps_wait <= 1;
            do @(posedge clock); while (!(rsps_valid && rsps_ready));
            rsp = rsps_data;
            rsps_wait <= 0;
        end
    endtask

    initial begin
        reqs_put_t = 0;
        reqs_took  = 0;
        rsps_gave  = 0;
        rsps_got   = 0;
        rsps_wait  = 0;
    end
endinterface
