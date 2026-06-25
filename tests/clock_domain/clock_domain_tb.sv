
// Clock-domain demonstrator, driven through the fw_root_begin/fw_root_end
// lifecycle on a real clock. The class layer (cd_top and friends) lives in
// clock_domain_pkg; this module just supplies clock/reset and the fw_root
// instance, then checks the result.
//
// cd_top has no signal-level API to bind, so the fw_root block carries no
// bind lines -- fw_root still seats the root clock domain on the clock
// transactor, and the tree inherits/derives from there:
//
//   a    : inherits root            -> 1:1
//   b    : overridden to /2
//   b.c  : inherits b's /2          -> /2
//   b.e  : /3 derived from b's /2   -> /6
//
// Each leaf ticks k times and records the elapsed sim time. Because every tick
// lands on a root posedge, the spans are exact multiples of one another, so we
// check the cadence by ratio (timescale-independent) alongside the static
// root_ticks() trace-up.
`include "fw_hdl_macros.svh"

module clock_domain_tb;
    import fw_hdl_pkg::*;
    import clock_domain_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;

    always #5ns clock = ~clock;

    // No bind lines: a clock domain needs no signal-level transactor. fw_root
    // seats cd_top's clock domain on its built-in clock transactor.
    `fw_root_begin(cd_top, u_root, clock, reset)
    `fw_root_end

    function automatic void check(string what, longint got, longint exp, ref int errors);
        if (got != exp) begin
            $display("FAIL: %s expected %0d got %0d", what, exp, got);
            errors++;
        end else begin
            $display("  ok: %s == %0d", what, got);
        end
    endfunction

    initial begin
        automatic int errors = 0;

        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        // fw_root news the root one clock after release; then wait for every
        // leaf to finish its k ticks.
        while (u_root.root == null) @(posedge clock);
        while (!(u_root.root.a.done && u_root.root.b.c.done && u_root.root.b.e.done))
            @(posedge clock);

        // Trace UP: root_ticks(1) for each leaf's domain.
        check("a ratio",   u_root.root.a.ratio,   1, errors);
        check("b.c ratio", u_root.root.b.c.ratio, 2, errors);
        check("b.e ratio", u_root.root.b.e.ratio, 6, errors);

        // Cadence DOWN: tick spans scale with the domain ratio. (a.span is one
        // root period per tick; the others are exact multiples.)
        if (u_root.root.a.span == 0) begin
            $display("FAIL: a.span is zero"); errors++;
        end
        check("b.c span == 2*a", u_root.root.b.c.span, 2 * u_root.root.a.span, errors);
        check("b.e span == 6*a", u_root.root.b.e.span, 6 * u_root.root.a.span, errors);

        if (errors == 0)
            $display("[clock_domain] PASS");
        else
            $display("[clock_domain] FAIL (%0d errors)", errors);
        $finish;
    end

    // Watchdog so a broken cadence fails fast instead of hanging.
    initial begin
        #100us;
        $fatal(1, "[clock_domain] TIMEOUT");
    end
endmodule
