// fw_fifo unit test: a writer and a reader process on one fw_fifo, each on
// its own pace, so pushes and pops land in the same clock; then full, empty
// and flush from either side.
package fifo_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class fifo_top extends fw_component implements fw_runnable;
        fw_fifo #(bit [7:0], 4) f;
        bit [7:0] got[$];
        int       same_clock;   // clocks with both a push and a pop
        bit       done;
        int       errors;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction

        function void build(); f = new(); endfunction

        function void check(bit c, string msg);
            if (!c) begin
                $display("FAIL: %s", msg);
                errors++;
            end
        endfunction

        // Phase 1: 64 values through the FIFO, writer and reader at
        // different paces, both in this one task as a single clocked loop
        // (one decision per clock for each side).
        virtual task run();
            int unsigned n_w = 0, n_r = 0, clk = 0;
            while (n_r < 64) begin
                bit do_w = (n_w < 64) && !f.full() && ((clk % 3) != 1);
                bit do_r = !f.empty() && ((clk % 5) != 2);
                bit [7:0] h = f.head();
                if (do_w && do_r) same_clock++;
                if (do_r) begin
                    got.push_back(h);
                    f.pop();
                    n_r++;
                end
                if (do_w) begin
                    f.push(8'(n_w * 7));
                    n_w++;
                end
                tick();
                clk++;
            end
            foreach (got[i]) check(got[i] == 8'(i * 7), $sformatf("item %0d: 0x%02h", i, got[i]));
            check(same_clock > 0, "no clock had both a push and a pop");

            // Phase 2: full, count, peek, flush.
            for (int i = 0; i < 4; i++) f.push(8'(8'hA0 + i));
            check(f.full() && f.count() == 4, "full after 4 pushes");
            check(f.peek(2) == 8'hA2, "peek(2)");
            f.pop();
            check(f.count() == 3 && f.head() == 8'hA1, "pop from full");
            f.flush();
            check(f.empty() && f.count() == 0, "empty after flush");
            f.pop();
            check(f.empty() && f.count() == 0, "pop when empty does nothing");
            f.push(8'h55);
            check(f.count() == 1 && f.head() == 8'h55, "push after flush");
            done = 1;
        endtask
    endclass
endpackage
