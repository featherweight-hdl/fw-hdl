
// M2 tests for the hardware-facing register hooks and the hierarchical watch-set:
//   - read provider (fw_reg_rd_if): supplies a LIVE value, single source of truth;
//   - write observer (fw_reg_wr_if): fires on sw writes (not hw updates), with
//     correct (val, prev);
//   - fw_reg_set.wait_change: a forked "engine" process sleeps until ANY member
//     changes and is told WHICH -- the design's arbiter pattern.
module reg_hooks_tb;
    import fw_hdl_pkg::*;

    int errors = 0;

    task automatic chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endtask

    // --- a read provider that reports live hardware state, ignoring `stored` ---
    class live_provider implements fw_reg_rd_if #(32);
        bit [31:0] live;
        virtual function bit [31:0] on_read(input bit [31:0] stored);
            return live;
        endfunction
    endclass

    // --- a write observer that records what it saw ----------------------------
    class rec_observer implements fw_reg_wr_if #(32);
        int        count;
        bit [31:0] last_val, last_prev;
        virtual task on_write(input bit [31:0] val, input bit [31:0] prev);
            count++;  last_val = val;  last_prev = prev;
        endtask
    endclass

    // --- a watch-set consumer (the "engine") ----------------------------------
    class watcher;
        fw_reg_set #(32)   set;
        int                wakes;
        fw_reg_base #(32)  last;
        function new(fw_reg_set #(32) s); set = s; endfunction
        task run();
            forever begin
                fw_reg_base #(32) which;
                set.wait_change(which);
                wakes++;  last = which;
            end
        endtask
    endclass

    initial begin
        // ===== read provider: live value, single source of truth =============
        begin
            automatic fw_reg_block #(32)   blk = new("blk");
            automatic fw_reg #(bit [31:0]) r = new("rp", blk, .hw_wmask('1));
            automatic live_provider        p = new();
            r.set_rd(p);
            p.live = 32'h0000_0011;
            chk(r.read_val() === 32'h11, "RP: read_val routes through provider");
            chk(r.sw_read()  === 32'h11, "RP: sw_read == read_val (single source)");
            p.live = 32'h0000_0022;                  // hw state changes, no update_val
            chk(r.read_val() === 32'h22, "RP: provider reports LIVE value");
            chk(r.read()     === 32'h22, "RP: typed read() peek also live");
        end

        // ===== write observer: fires on sw write only, with (val, prev) ======
        begin
            automatic fw_reg_block #(32)   blk = new("blk");
            automatic fw_reg #(bit [31:0]) r = new("wo", blk, .sw_wmask('1));
            automatic rec_observer         o = new();
            r.add_wr(o);
            r.write_val(32'hAAAA_0000);
            chk(o.count   === 1,             "WO: observer fired on sw write");
            chk(o.last_val  === 32'hAAAA_0000, "WO: val is post-write value");
            chk(o.last_prev === 32'h0,         "WO: prev is value before write");
            r.write_val(32'hBBBB_0000);
            chk(o.count   === 2,             "WO: fires again");
            chk(o.last_prev === 32'hAAAA_0000, "WO: prev tracks prior value");
            r.update_val(32'hCCCC_CCCC);       // hw update must NOT fire observer
            chk(o.count   === 2,             "WO: hw update does not fire observer");
        end

        // ===== watch-set: forked engine sleeps until any member changes ======
        begin
            automatic fw_reg_block #(32)   blk = new("blk");
            automatic fw_reg #(bit [31:0]) r0 = new("r0", blk, .sw_wmask('1), .hw_wmask('1));
            automatic fw_reg #(bit [31:0]) r1 = new("r1", blk, .sw_wmask('1), .hw_wmask('1));
            automatic fw_reg_set #(32)     s  = new();
            automatic watcher              w  = new(s);
            s.add(r0);
            s.add(r1);

            fork w.run(); join_none
            #1;                                       // let the engine reach its wait

            r0.update_val(32'h0000_0001);             // hw change on r0
            #1;
            chk(w.wakes === 1,        "SET: woke on r0 change");
            chk(w.last  === r0,       "SET: reported r0 as the changed reg");

            r1.write_val(32'h0000_0002);              // sw change on r1
            #1;
            chk(w.wakes === 2,        "SET: woke on r1 change");
            chk(w.last  === r1,       "SET: reported r1 as the changed reg");

            r1.write_val(32'h0000_0002);              // same value -> no change -> no wake
            #1;
            chk(w.wakes === 2,        "SET: same-value write does not wake (model gates on change)");
        end

        if (errors == 0) $display("[reg_hooks] PASS");
        else             $display("[reg_hooks] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[reg_hooks] TIMEOUT");
    end
endmodule
