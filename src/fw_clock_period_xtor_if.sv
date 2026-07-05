// ----------------------------------------------------------------------------
// Period/delay-based clock transactor -- INTERFACE (task API + tick delay).
//
// Unlike fw_clock_xtor_if there is NO toggling clock: tick(n) advances sim time
// by n*period via a `#` delay -- no free-running clock, no per-edge simulation
// events. The cycle length `period` is a plain member (default 10ns) SET BY THE
// WRAPPER (fw_clock_period_xtor) from its compile-time PERIOD parameter; the
// interface itself is UNPARAMETERIZED so a bare `virtual fw_clock_period_xtor_if`
// handle (the one fw_clock_period_xtor_bridge holds) binds cleanly. A
// parameterized interface would specialize the type (…__Pz1) and Verilator would
// refuse that bind -- hence the wrapper carries the parameter, not the interface.
//
// No `timescale (matches fw_clock_xtor_if and the rest of fw-hdl); the default
// `10ns` is an absolute literal, so the advance is 10ns/cycle regardless of the
// compile's timescale. tick(0) is a delta cycle (#0), matching fw_clock_xtor_if;
// tick(n>0) advances n cycles relative to "now" (a delay), NOT aligned to a
// physical clock edge (there is none) -- which is the point.
// ----------------------------------------------------------------------------
interface fw_clock_period_xtor_if ();

    // Sim time advanced per cycle. Default 10ns; the wrapper drives its PERIOD in.
    realtime period = 10ns;

    // Advance this domain by `count` cycles. count==0 is a delta cycle (#0).
    task automatic tick(int count);
        if (count == 0) begin
            #0;
        end else begin
            #(count * period);
        end
    endtask

endinterface
