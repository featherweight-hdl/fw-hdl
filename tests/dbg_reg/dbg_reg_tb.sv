// D-3: register-model events.
//
// The claim: **every fw-hdl register in any design becomes traceable with zero
// per-design work.** The only line in this testbench that mentions debug at all
// is `rf = new("rf", this)` — passing the component — and from that one argument
// every register under the block inherits a context.
//
// What the register model can now answer that it could not before:
//
//   * who moved this value — software, hardware, or reset;
//   * why my write did not take (`.masked`, with the bits the mask refused);
//   * that a read happened at all (a read changes no state, so the register
//     itself leaves no trace — the decode does);
//   * that an access hit nothing (previously silent: reads returned 0 and
//     writes were dropped, with no complaint).
module dbg_reg_tb;
    import fw_hdl_pkg::*;
    `include "dbg/fw_dbg_macros.svh"

    int errors = 0;

    function automatic void chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endfunction

    // A minimal clock domain so the tree's `clock` ports resolve.
    class fake_clock extends fw_export #(fw_clock_domain_if)
            implements fw_clock_domain_if;
        function new(string name, fw_component parent);
            super.new(name, parent);
            set_imp(this);
        endfunction
        virtual task tick(int n = 1); #(n); endtask
        virtual function longint root_ticks(int n = 1); return n; endfunction
    endclass

    // --- the design under observation --------------------------------------
    //   csr    @0  : software-writable low byte, upper 24 bits read-only
    //   status @4  : hardware-owned, low nibble read-to-clear
    class rf_comp extends fw_component;
        fw_reg_block #(32)    rf;
        fw_reg #(bit [31:0])  csr;
        fw_reg #(bit [31:0])  status;
        // A second block built in the CONSTRUCTOR rather than in build(), which
        // is where a real design usually puts one (wb_dma_rf does). It has to
        // adopt this component too, and for a different reason: at that moment
        // build() has not run and `this` is still being constructed.
        fw_reg_block #(32)    early;
        fw_reg #(bit [31:0])  ereg;

        function new(string name, fw_component parent);
            super.new(name, parent);
            early = new("early");
            ereg  = new("ereg", early);
        endfunction

        virtual function void build();
            // NO wiring at all. A block built during elaboration adopts the
            // component building it, exactly as `clock` and `dbg` are adopted.
            rf     = new("rf");
            csr    = new("csr",    rf, .sw_wmask(32'h0000_00ff));
            status = new("status", rf, .sw_wmask(32'h0000_0000),
                                       .hw_wmask(32'hffff_ffff),
                                       .rclr_mask(32'h0000_000f));
        endfunction
    endclass

`ifdef FW_TRACE_OFF
    fw_component_root #(rf_comp) root = new("top");

    initial begin
        automatic fake_clock ck = new("clk", root);
        root.clock.connect(ck);
        root.start();
        // The register model must behave identically with every site removed.
        root.rf.write_val(0, 32'h0000_00aa);
        chk(root.csr.read_val() == 32'h0000_00aa, "OFF: register model unchanged");
        chk(fw_dbg_catalog::num_sites() == 0,     "OFF: no instance sites registered");
        if (errors == 0) $display("[dbg_reg] PASS (FW_TRACE_OFF)");
        else begin $display("[dbg_reg] FAIL (%0d errors)", errors); $fatal(1, "FAIL"); end
        $finish;
    end
`else

    // Records every event it is given, so payloads can be asserted rather than
    // merely counted. Note it keeps `snapshot()`s, not the contexts.
    class rec_listener extends fw_dbg_listener;
        string     names[$];
        fw_dbg_rec recs[$];

        protected function void keep(string nm, fw_dbg_rec r);
            names.push_back(nm);
            recs.push_back(r);
        endfunction
        virtual function void on_state   (fw_state_ctx    st); keep(st.name(), st.snapshot()); endfunction
        virtual function void on_notice  (fw_notice_ctx   n);  keep(n.name(),  n.snapshot());  endfunction
        virtual function void on_decision(fw_decision_ctx d);  keep(d.name(),  d.snapshot());  endfunction

        function void clear(); names.delete(); recs.delete(); endfunction
        function int count(string nm);
            int n = 0;
            foreach (names[i]) if (names[i] == nm) n++;
            return n;
        endfunction
        // The nth (0-based) event named `nm`, or null.
        function fw_dbg_rec nth(string nm, int idx = 0);
            int n = 0;
            foreach (names[i]) begin
                if (names[i] == nm) begin
                    if (n == idx) return recs[i];
                    n++;
                end
            end
            return null;
        endfunction
    endclass

    fw_dbg_root                  dbg  = new("top");
    fw_component_root #(rf_comp) root = new("top");

    initial begin
        automatic rec_listener     log  = new();
        automatic fw_dbg_sink_text sink = new();
        automatic fake_clock       ck   = new("clk", root);
        automatic fw_dbg_rec       r;

        root.clock.connect(ck);
        dbg.add_listener(log,  FW_K_ALL, FW_L_TRACE);
        dbg.add_listener(sink, FW_K_ALL, FW_L_TRACE);
        root.set_dbg_domain(dbg);
        root.start();
        #1;

        // ===== instance sites are named after the model object ==============
        chk(fw_dbg_catalog::find("rf.csr")         != null, "a register registers a site named <block>.<reg>");
        chk(fw_dbg_catalog::find("rf.csr.masked")  != null, "...and one for the masked-write notice");
        chk(fw_dbg_catalog::find("rf.decode")   != null, "a block registers a decode site");
        chk(fw_dbg_catalog::find("rf.decode_miss") != null, "...and a decode-miss site");

        // ===== 0. ownership is AMBIENT, not declared =========================
        // Neither block was passed a component. Both report, because a block
        // built during elaboration adopts its builder. This is the property
        // that matters: the previous design took an OPTIONAL parent, and an
        // optional argument whose omission costs nothing visible -- the
        // registers still work, they just go quiet -- is one that gets omitted.
        log.clear();
        root.rf.write_val(0, 32'h1);
        chk(log.count("rf.csr") == 1,
            "a block built in build() adopts the component with no wiring");
        log.clear();
        root.early.write_val(0, 32'h1);
        chk(log.count("early.ereg") == 1,
            "...and so does one built in the constructor, before build() ran");
        chk(fw_dbg_catalog::num_uncontexted() == 0,
            "nothing was left without a context");

        root.csr.reset();
        root.ereg.reset();

        $display("--- register traffic ---");

        // ===== 1. a clean software write ====================================
        log.clear();
        root.rf.write_val(0, 32'h0000_00aa);
        r = log.nth("rf.csr");
        chk(r != null,                       "a software write reports a change");
        if (r != null) begin
            chk(r.fields[0] == 32'h0000_0000, "change carries the old value");
            chk(r.fields[1] == 32'h0000_00aa, "change carries the new value");
            chk(r.actor     == FW_ACTOR_SW,   "change is attributed to software");
        end
        chk(log.count("rf.csr.masked") == 0,     "a clean write raises no masked notice");
        chk(log.count("rf.decode")  == 1,     "the write is visible at the decode");
        r = log.nth("rf.decode");
        if (r != null) begin
            chk(r.fields[0] == 0,             "decode carries the offset");
            chk(r.fields[1] == 32'h0000_00aa, "decode carries the data");
            chk(r.fields[2] == 1,             "decode says it was a write");
        end

        // ===== 2. a write whose bits the mask refuses =======================
        // Low byte is written with the value it already holds, so there is NO
        // change -- and without the notice this write would be entirely silent.
        log.clear();
        root.rf.write_val(0, 32'h1234_00aa);
        chk(log.count("rf.csr") == 0,            "an all-masked write changes nothing");
        r = log.nth("rf.csr.masked");
        chk(r != null,                        "...but it is not silent");
        if (r != null) begin
            chk(r.severity  == FW_SEV_WARN,   "masked write is a warning");
            chk(r.fields[0] == 32'h1234_00aa, "notice carries what was written");
            chk(r.fields[1] == 32'h0000_00aa, "...what actually landed");
            chk(r.fields[2] == 32'h1234_0000, "...and exactly which bits were refused");
        end

        // ===== 2b. a hardware-owned bit is NOT a refused write ==============
        // Programming a register means writing the whole word, and status bits
        // that hardware owns sit in that word carrying 0. Warning about those
        // means warning on every single write -- 47 identical warnings in one
        // wb_dma transfer test, every one of them describing correct behavior.
        // A bit hardware owns is hardware's business.
        log.clear();
        root.status.update_val(32'h0000_00f0);        // hw sets bits it owns
        log.clear();
        root.rf.write_val(4, 32'h0000_0000);          // sw writes the word, 0 there
        chk(log.count("rf.status.masked") == 0,
            "writing 0 over a hardware-owned bit raises no warning");
        chk(root.status.read_val() == 32'h0000_00f0,
            "...and the bit is untouched, as it should be");
        root.status.reset();

        // ===== 3. hardware moving the value underneath software =============
        log.clear();
        root.status.update_val(32'h0000_00ff);
        r = log.nth("rf.status");
        chk(r != null && r.actor == FW_ACTOR_HW,
            "a hardware update is attributed to hardware, not software");

        // ===== 4. a read: no state change, so only the decode sees it =======
        // ...except this register is read-to-clear, which IS a change, and is
        // reported as software-caused. Which bits cleared is old & ~new.
        log.clear();
        begin
            automatic bit [31:0] v = root.rf.read_val(4);
            chk(v == 32'h0000_00ff,           "read returns the pre-clear value");
        end
        r = log.nth("rf.decode");
        chk(r != null,                        "a read is visible at the decode");
        if (r != null) begin
            chk(r.fields[0] == 4,             "decode carries the offset");
            chk(r.fields[2] == 0,             "decode says it was a read");
        end
        r = log.nth("rf.status");
        chk(r != null,                        "read-to-clear reports a change");
        if (r != null) begin
            chk(r.actor == FW_ACTOR_SW,       "...attributed to software");
            chk((r.fields[0] & ~r.fields[1]) == 32'h0000_000f,
                "...and the cleared bits are derivable as old & ~new");
        end

        // ===== 5. an access that hits nothing ===============================
        // Previously: a read returned 0 and a write vanished, both in silence.
        log.clear();
        void'(root.rf.read_val(32'h100));
        root.rf.write_val(32'h100, 32'h1);
        chk(log.count("rf.decode_miss") == 2, "both directions of an unmapped access complain");
        chk(log.count("rf.decode")      == 0, "...and neither is reported as a decode");
        r = log.nth("rf.decode_miss", 0);
        if (r != null) begin
            chk(r.fields[0] == 32'h100,       "miss carries the offset");
            chk(r.fields[1] == 0,             "miss distinguishes read from write");
        end
        r = log.nth("rf.decode_miss", 1);
        if (r != null) chk(r.fields[1] == 1,  "...for the write too");

        // ===== 6. reset is its own actor ====================================
        log.clear();
        root.csr.reset();
        r = log.nth("rf.csr");
        chk(r != null && r.actor == FW_ACTOR_RESET, "reset is attributed to reset");

        // ===== 7. levels do real work =======================================
        // At TXN, the high-rate per-access detail goes quiet while the two
        // diagnostics that matter -- a refused write and an unmapped access --
        // keep firing. That is the level split earning its keep.
        log.clear();
        dbg.cfg("top", .level(FW_L_TXN));
        dbg.apply();
        root.rf.write_val(0, 32'h1234_00aa);
        void'(root.rf.read_val(32'h100));
        chk(log.count("rf.csr")            == 0, "L_DETAIL change is clamped away at L_TXN");
        chk(log.count("rf.decode")      == 0, "L_DETAIL decode is clamped away at L_TXN");
        chk(log.count("rf.csr.masked")     == 1, "...but the masked-write warning survives");
        chk(log.count("rf.decode_miss") == 1, "...and so does the unmapped access");

        // ===== 8. outside elaboration, silence -- but SAID out loud ==========
        // The ambient owner is only trustworthy while the tree is being built.
        // A block created after that has no honest owner to adopt, and guessing
        // one would put its events in someone else's context -- a worse failure
        // than silence, because it looks like data. So it stays quiet, and the
        // facility records that it cannot speak.
        begin
            automatic fw_reg_block #(32)   late = new("late");
            automatic fw_reg #(bit [31:0]) lreg = new("lreg", late);
            dbg.apply();
            log.clear();
            late.write_val(0, 32'hff);
            chk(log.count("late.lreg") == 0,
                "a block built after elaboration adopts nothing");
            chk(fw_dbg_catalog::num_uncontexted() == 1,
                "...and is recorded as having no context");
            chk(fw_dbg_catalog::uncontexted(0) == "late",
                "...by name, so the report can point at it");
            chk(lreg.read_val() == 32'hff,
                "...while the register model itself is entirely unaffected");
        end

        // ===== 9. containment is authoritative ==============================
        // A register map is ONE artifact with one root: a bank at offset X
        // belongs to the map, whatever object happened to call `new` on it.
        // So a block that is nested takes its context from its CONTAINER -- and
        // the "this will be silent" note is retracted, because it is no longer
        // a root and reporting it would be a false alarm.
        dbg.clear_cfg();          // undo the clamp from section 7
        dbg.apply();
        begin
            automatic fw_reg_block #(32)    region = new("region");
            automatic fw_reg #(bit [31:0])  rreg   = new("rreg", region);
            chk(fw_dbg_catalog::num_uncontexted() == 2,
                "a block built with no owner starts out context-less");

            root.rf.add_block(region, 32'h200);

            chk(fw_dbg_catalog::num_uncontexted() == 1,
                "...and nesting it retracts that -- it is not a root any more");
            dbg.apply();
            log.clear();
            root.rf.write_val(32'h200, 32'h5);
            chk(log.count("region.rreg") == 1,
                "a nested block reports under its CONTAINER's context");
        end

        $display("--- end ---");

        if (errors == 0) $display("[dbg_reg] PASS");
        else begin
            $display("[dbg_reg] FAIL (%0d errors)", errors);
            $fatal(1, "[dbg_reg] FAIL");
        end
        $finish;
    end
`endif /* FW_TRACE_OFF */

endmodule
