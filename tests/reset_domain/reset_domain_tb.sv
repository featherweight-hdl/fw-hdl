// Reset domains, driven through fw_root on a real clock and reset:
//
//   * fw_root seats the root reset domain; children inherit it; it is never
//     seen asserted by live code, and deasserts on the root clock;
//   * a parent overrides a child's reset domain in connect();
//   * a root that seats only a clock (here a bare fw_component_root) leaves
//     `reset` unbound: never in reset, and nothing is inherited.
`include "fw_hdl_macros.svh"

module reset_domain_tb;
    import fw_hdl_pkg::*;
    import reset_domain_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;
    always #5ns clock = ~clock;

    `fw_root_begin(rd_top, u_root, clock, reset)
    `fw_root_end

    // A bare root: a clock and no reset (the xls_harness / comp_api shape).
    fw_clock_xtor_if u_clk2(.clock(clock), .reset(1'b0));
    fw_component_root #(rd_top) bare;

    int errors = 0;
    function automatic void chk(bit cond, string what);
        if (!cond) begin $display("FAIL: %s", what); errors++; end
        else       $display("  ok: %s", what);
    endfunction

    initial begin
        rd_top t;
        fw_clock_xtor_bridge ck2;
        int n0, c0, n_in;

        repeat (4) @(posedge clock);
        reset = 1'b0;
        wait (u_root.root != null && u_root.root.elaborated);
        t = u_root.root;

        // --- the root reset domain, inherited ----------------------------------
        chk(t.reset.is_connected(), "root reset seated by fw_root");
        chk(t.a.reset.t == t.reset.t, "a inherits the root reset domain");
        chk(!t.reset.t.in_reset(), "root domain not in reset while the tree lives");
        chk(t.reset.t.is_async(), "root domain asserts asynchronously");
        chk(t.reset.t.sync_clock() == t.clock.t, "root domain deasserts on the root clock");
        chk(t.reset.t.domain_kind() == FW_DOMAIN_RESET, "root domain kind is reset");
        chk(t.reset.t.domain_nsrc() == 0, "root domain is a root");
        chk(t.domain(FW_DOMAIN_RESET).ref_domain() == t.reset.t, "domain(RESET) is the reset port");

        // --- override -----------------------------------------------------------
        chk(t.b.reset.t == t.sig, "b overridden to sig");
        chk(fw_domains::relate(t.b.reset.t, t.a.reset.t) == FW_DOMAIN_UNRELATED,
            "sig and the root reset are unrelated");

        // --- live code; the run lifecycle ----------------------------------------
        while (!t.a.started) @(posedge clock);
        chk(!t.a.reset_supervised(), "a (root domain) is not supervised");
        chk(t.b.reset_supervised(), "b (sig domain) is supervised");
        chk(!t.a.reset_at_start, "a: not in reset at run()");
        chk(t.a.deassert_t >= 0, "a: wait_reset_deassert() returned at once");
        repeat (3) @(posedge clock);
        chk(t.b.n_start == 0, "b: run() not started while sig is asserted");
        chk(t.s.n_steps_in_reset > 0, "s: step() runs in reset and sees in_reset()");
        t.sig.set(1'b0);
        repeat (4) @(posedge clock);
        chk(t.b.n_start == 1, "b: run() started on deassertion");
        chk(!t.b.reset_at_start, "b: not in reset at run()");
        chk(t.b.n > 0 && t.b.n_child > 0, "b: run() and its forked process tick");
        chk(!t.b.in_reset(), "b: out of reset");
        n_in = t.s.n_steps_in_reset;
        repeat (3) @(posedge clock);
        chk(t.s.n_steps_in_reset == n_in, "s: in_reset() 0 out of reset");

        // assertion kills run() and its descendants, once; reset_state() once
        t.sig.set(1'b1);
        repeat (3) @(posedge clock);
        n0 = t.b.n; c0 = t.b.n_child;
        repeat (5) @(posedge clock);
        chk(t.b.n == n0, "b: run() killed on assertion");
        chk(t.b.n_child == c0, "b: run()'s forked process killed on assertion");
        chk(t.b.n_reset_state == 1, "b: reset_state() called once");
        chk(t.a.n_reset_state == 0, "a: reset_state() not called");
        chk(t.s.n_steps_in_reset > n_in, "s: step() keeps running in reset");
        chk(t.a.n > 0, "a: unaffected");

        // deassertion starts run() again
        t.sig.set(1'b0);
        repeat (4) @(posedge clock);
        chk(t.b.n_start == 2, "b: run() restarted on the next deassertion");
        chk(t.b.n > n0, "b: the new run() ticks");
        chk(t.b.n_reset_state == 1, "b: reset_state() not called on deassertion");

        // --- a root with no reset ------------------------------------------------
        bare = new("bare");
        ck2  = new("clock", bare, u_clk2);
        bare.clock.connect(ck2);
        fork bare.start(); join_none
        while (!bare.elaborated) @(posedge clock);
        chk(!bare.reset.is_connected(), "bare: root reset unbound");
        chk(!bare.a.reset.is_connected(), "bare: unbound reset is not inherited");
        chk(!bare.a.in_reset(), "bare: unbound reset is never in reset");
        while (!bare.a.started) @(posedge clock);
        repeat (2) @(posedge clock);
        chk(bare.a.deassert_t >= 0, "bare: wait_reset_deassert() returns at once");
        chk(bare.b.reset.t == bare.sig, "bare: an explicit override still binds");

        if (errors == 0) $display("[reset_domain] PASS");
        else             $fatal(1, "[reset_domain] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #200us;
        $fatal(1, "[reset_domain] TIMEOUT");
    end
endmodule
