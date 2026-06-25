// Blinky VERIFICATION TOP: drives clock/reset into the blinky_top design module
// and checks that the LED output actually blinks (alternates). It observes only
// the LED pin -- the class tree, transactor, and fw_root machinery are all
// encapsulated inside blinky_top.
module blinky_tb;
    import blinky_pkg::*;

    logic clock = 1'b0;
    logic reset = 1'b1;
    logic led;

    always #5ns clock = ~clock;

    // DUT: the blinky design top (fw class tree + put transactor behind pins).
    blinky_top dut (.clock(clock), .reset(reset), .led(led));

    // Record every LED transition.
    led_t transitions[$];
    always @(led) if (!reset) transitions.push_back(led);

    initial begin
        automatic int errors = 0;

        reset = 1'b1;
        repeat (4) @(posedge clock);
        reset = 1'b0;

        // Wait for a handful of blinks. Poll on the clock rather than wait() on
        // the mutating queue.
        while (transitions.size() < 5) @(posedge clock);

        // Every recorded transition must flip the value -- that is what "blink"
        // means. (Consecutive equal values would mean it stopped toggling.)
        for (int i = 1; i < transitions.size(); i++) begin
            if (transitions[i] === transitions[i-1]) begin
                $display("[blinky] FAIL: LED did not flip at transition %0d (val=%0b)",
                         i, transitions[i]);
                errors++;
            end
        end

        if (errors == 0)
            $display("[blinky] PASS (%0d blinks observed)", transitions.size());
        else
            $display("[blinky] FAIL (%0d errors)", errors);
        $finish;
    end

    // Watchdog so a stalled loop fails fast instead of hanging.
    initial begin
        #500us;
        $fatal(1, "[blinky] TIMEOUT");
    end
endmodule
