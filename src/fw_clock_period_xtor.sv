// ----------------------------------------------------------------------------
// Period/delay-based clock transactor -- WRAPPER (integration).
//
// Carries the compile-time PERIOD parameter and pushes it into the inner,
// UNPARAMETERIZED interface, so the interface type stays bare and a
// `virtual fw_clock_period_xtor_if` handle (held by fw_clock_period_xtor_bridge)
// binds to u_if cleanly. This mirrors the protocol-xtor idiom: the wrapper
// carries the parameters and instances u_if; the HVL reaches the API via u_if.
//
// A period clock has no signal-level "core" (no ready/valid or bus logic to
// bridge), so unlike wb_*_xtor there is no fw_clock_period_xtor_core -- the
// interface holds the whole (delay-based) behavior.
// ----------------------------------------------------------------------------
module fw_clock_period_xtor #(
        parameter realtime PERIOD = 10ns
    ) ();

    fw_clock_period_xtor_if u_if();

    // Seat the compile-time period into the interface at t=0, before the model's
    // run phase issues any tick(). (The default member value is 10ns, so a
    // default-PERIOD instance is correct even independent of this assignment.)
    initial u_if.period = PERIOD;

endmodule
