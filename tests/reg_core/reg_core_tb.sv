
// M1 directed tests for the core register & block model (no hardware hooks /
// watch-set yet -- those are M2). Covers the access-mask contract (RW / RO / WO /
// ROC / RW+hw-set overlap), the typed packed-struct projection, and block offset
// decode (auto-stride, explicit gap, nested sub-block). Registers are plain
// model classes, so an initial block drives them directly.
module reg_core_tb;
    import fw_hdl_pkg::*;

    int errors = 0;

    // Channel-CSR-like layout to exercise the typed projection (subset of the
    // DMA CSR: a couple of RW config bits, hw-set status, an interrupt source).
    typedef struct packed {
        bit [27:0] rsvd;       // 31:4 RO reserved
        bit        int_src;    //  3   ROC interrupt source (hw set, read-clear)
        bit        done;       //  2   RO  status (hw set)
        bit        busy;       //  1   RO  status (hw set)
        bit        en;         //  0   RW  config
    } csr_t;

    task automatic chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endtask

    initial begin
        // ---- profile: RW (sw writes, hw cannot) -----------------------------
        begin
            automatic fw_reg_block #(32) blk = new("blk");
            automatic fw_reg #(bit [31:0]) r =
                new("rw", blk, .sw_wmask(32'hFFFF_FFFF), .hw_wmask(32'h0));
            r.write_val(32'hA5A5_1234);
            chk(r.read_val() === 32'hA5A5_1234, "RW: sw write should land");
            r.update_val(32'hFFFF_FFFF);                 // hw cannot write
            chk(r.read_val() === 32'hA5A5_1234, "RW: hw update must be ignored");
        end

        // ---- profile: RO (sw cannot write, hw owns) --------------------------
        begin
            automatic fw_reg_block #(32) blk = new("blk");
            automatic fw_reg #(bit [31:0]) r =
                new("ro", blk, .sw_wmask(32'h0), .hw_wmask(32'hFFFF_FFFF));
            r.write_val(32'hFFFF_FFFF);                  // sw cannot write
            chk(r.read_val() === 32'h0, "RO: sw write must be ignored");
            r.update_val(32'h0000_1234);                 // hw owns
            chk(r.read_val() === 32'h0000_1234, "RO: hw update should land");
        end

        // ---- profile: ROC (hw set, read-to-clear on sw read only) ------------
        begin
            automatic fw_reg_block #(32) blk = new("blk");
            automatic fw_reg #(bit [31:0]) r =
                new("roc", blk, .sw_wmask(32'h0), .hw_wmask(32'hFFFF_FFFF),
                    .rclr_mask(32'hFFFF_FFFF));
            r.update_val(32'h0000_0007);                  // hw sets sticky bits
            chk(r.read_val() === 32'h7, "ROC: read_val peek must NOT clear");
            chk(r.read_val() === 32'h7, "ROC: second peek still 7");
            chk(r.sw_read()  === 32'h7, "ROC: sw_read returns value-before-clear");
            chk(r.read_val() === 32'h0, "ROC: sw_read cleared the sticky bits");
        end

        // ---- profile: RW + hw-set overlap (hardware wins) --------------------
        begin
            automatic fw_reg_block #(32) blk = new("blk");
            automatic fw_reg #(bit [31:0]) r =
                new("ovl", blk, .sw_wmask(32'h0000_0001), .hw_wmask(32'h0000_0001));
            r.write_val(32'h1);                           // sw sets bit0
            chk(r.read_val() === 32'h1, "OVL: sw write takes effect");
            r.update_val(32'h0, 32'h1);                   // hw clears bit0 -> wins
            chk(r.read_val() === 32'h0, "OVL: hw update is authoritative");
            r.write_val(32'h1);                           // sw sets again
            chk(r.read_val() === 32'h1, "OVL: sw effect persists until next hw write");
        end

        // ---- typed packed-struct projection ----------------------------------
        begin
            automatic csr_t hwm = '{busy:1, done:1, int_src:1, default:'0};
            automatic csr_t swm = '{en:1, default:'0};
            automatic fw_reg_block #(32) blk = new("blk");
            automatic fw_reg #(csr_t) csr =
                new("csr", blk, .sw_wmask(swm), .hw_wmask(hwm),
                    .rclr_mask('{int_src:1, default:'0}));
            csr_t v;

            csr.write('{en:1, busy:1, default:'0});       // only en is sw-writable
            v = csr.read();
            chk(v.en  === 1'b1, "PROJ: en written by sw");
            chk(v.busy === 1'b0, "PROJ: busy is hw-only, sw write ignored");

            // hardware sets a single status bit via an inline masked update
            csr.update('{done:1, default:'0}, '{done:1, default:'0});
            chk(csr.read().done === 1'b1, "PROJ: single-bit hw update (done)");
            chk(csr.read().busy === 1'b0, "PROJ: masked update left busy alone");

            // interrupt source: hw set, sw read clears
            csr.update('{int_src:1, default:'0}, '{int_src:1, default:'0});
            chk(csr.read().int_src === 1'b1, "PROJ: int_src set by hw");
            void'(csr.sw_read());
            chk(csr.read().int_src === 1'b0, "PROJ: int_src cleared by sw_read");
        end

        // ---- block decode: auto-stride + explicit gap ------------------------
        begin
            automatic fw_reg_block #(32) blk = new("blk");
            automatic fw_reg #(bit [31:0]) a = new("a", blk);            // 0x00
            automatic fw_reg #(bit [31:0]) b = new("b", blk);            // 0x04 (auto)
            automatic fw_reg #(bit [31:0]) c = new("c", blk, 32'h20);    // explicit, leaves a gap
            chk(a.offset() === 0,      "DEC: a @ 0x00");
            chk(b.offset() === 4,      "DEC: b @ 0x04");
            chk(c.offset() === 32'h20, "DEC: c @ 0x20");
            chk(blk.size() === 32'h24, "DEC: size spans through c");
            blk.write_val(32'h20, 32'hcafe_f00d);
            chk(blk.read_val(32'h20) === 32'hcafe_f00d, "DEC: gap reg decodes");
            chk(blk.read_val(32'h10) === 32'h0,         "DEC: unmapped reads 0");
        end

        // ---- nested sub-block decode -----------------------------------------
        begin
            automatic fw_reg_block #(32) top = new("top");
            automatic fw_reg_block #(32) sub = new("sub");
            automatic fw_reg #(bit [31:0]) g  = new("g",  top);   // 0x00
            automatic fw_reg #(bit [31:0]) s0 = new("s0", sub);   // local 0x00
            automatic fw_reg #(bit [31:0]) s1 = new("s1", sub);   // local 0x04 -> sub.size()==0x08
            top.add_block(sub, 32'h10); // sub occupies 0x10..0x17
            chk(top.size() === 32'h18, "NEST: top size spans sub-block");
            top.write_val(32'h10, 32'h1111_1111);
            top.write_val(32'h14, 32'h2222_2222);
            chk(top.read_val(32'h10) === 32'h1111_1111, "NEST: sub s0 via top");
            chk(top.read_val(32'h14) === 32'h2222_2222, "NEST: sub s1 via top");
            chk(s0.read_val()        === 32'h1111_1111, "NEST: write reached s0");
            chk(top.read_val(32'h00) === 32'h0,         "NEST: global g untouched");
        end

        if (errors == 0) $display("[reg_core] PASS");
        else             $display("[reg_core] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[reg_core] TIMEOUT");
    end
endmodule
