// ----------------------------------------------------------------------------
// Period/delay-based clock transactor -- INTERFACE (task API + tick delay).
//
// Unlike fw_clock_xtor_if there is NO toggling clock: edge k is at exactly
// k*period from time 0 (fw-hdl-spec processes.md, "Edges"), and tick(n) waits
// with a `#` delay for the n-th edge after now -- no free-running clock, no
// per-edge simulation events. The cycle length `period` is a plain member (default 10ns) SET BY THE
// WRAPPER (fw_clock_period_xtor) from its compile-time PERIOD parameter; the
// interface itself is UNPARAMETERIZED so a bare `virtual fw_clock_period_xtor_if`
// handle (the one fw_clock_period_xtor_bridge holds) binds cleanly. A
// parameterized interface would specialize the type (…__Pz1) and Verilator would
// refuse that bind -- hence the wrapper carries the parameter, not the interface.
//
// No `timescale (matches fw_clock_xtor_if and the rest of fw-hdl); the default
// `10ns` is an absolute literal, so the advance is 10ns/cycle regardless of the
// compile's timescale. tick(0) is a delta cycle (#0), matching fw_clock_xtor_if.
// tick(n>0) lands on edges, whoever calls it and when, so two processes
// ticking one period clock see the same edges.
// ----------------------------------------------------------------------------
interface fw_clock_period_xtor_if ();

    // Sim time advanced per cycle. Default 10ns; the wrapper drives its PERIOD in.
    realtime period = 10ns;

    // To the count-th edge after now (one due now counts as passed: a
    // computed edge comes before a delay ending at its time). count==0 is a
    // delta cycle (#0).
    task automatic tick(int count);
        if (count == 0) begin
            #0;
        end else begin
            wait_edge(edges() + count);
        end
    endtask

    // The edges at or before now. Edge k is at exactly k * period from time
    // 0 (fw-hdl-spec processes.md, "Edges"). Computed from the time, not
    // counted by a loop, so the clock still costs no event per edge.
    function automatic longint unsigned edges();
        longint unsigned e = longint'($realtime / period);   // the nearest
        if (e > 0 && $realtime < e * period - period / 4) e--;
        return e;
    endfunction

    // Returns at edge k. Its time is k * period, not a sum of periods, so
    // edges don't drift and none comes twice.
    task automatic wait_edge(longint unsigned k);
        realtime t = k * period;
        if (t > $realtime) #(t - $realtime);
    endtask

endinterface
