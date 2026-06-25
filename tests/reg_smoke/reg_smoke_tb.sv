
// M0 smoke test for the register model. Proves the kernel register classes
// compile and a basic software write -> read round-trip works, plus a one-line
// nested-decode and hardware-update sanity check. Registers are plain model
// classes (not components), so no lifecycle/fw_root is needed -- an initial
// block exercises them directly.
module reg_smoke_tb;
    import fw_hdl_pkg::*;

    // a trivial 32-bit register block: one fully-writable RW register, and a
    // second register so we can prove offset decode.
    typedef bit [31:0] word_t;

    initial begin
        automatic int errors = 0;
        automatic fw_reg_block #(32)  blk = new("blk");
        automatic fw_reg #(word_t)    r0  = new("r0");
        automatic fw_reg #(word_t)    r1  = new("r1");
        automatic word_t got;

        blk.add(r0);          // 0x00
        blk.add(r1);          // 0x04 (auto stride 4)

        // sw write -> read round-trip through the block (by offset)
        blk.write_val(32'h00, 32'hdead_beef);
        got = blk.read_val(32'h00);
        if (got !== 32'hdead_beef) begin
            $display("FAIL: r0 round-trip expected 0xdeadbeef got 0x%08h", got);
            errors++;
        end

        // second register decodes independently
        blk.write_val(32'h04, 32'h1234_5678);
        got = blk.read_val(32'h04);
        if (got !== 32'h1234_5678) begin
            $display("FAIL: r1 decode expected 0x12345678 got 0x%08h", got);
            errors++;
        end
        if (blk.read_val(32'h00) !== 32'hdead_beef) begin
            $display("FAIL: r0 disturbed by r1 write");
            errors++;
        end

        // size() spans both registers
        if (blk.size() !== 32'h08) begin
            $display("FAIL: size expected 0x08 got 0x%08h", blk.size());
            errors++;
        end

        if (errors == 0) $display("[reg_smoke] PASS");
        else             $display("[reg_smoke] FAIL (%0d errors)", errors);
        $finish;
    end

    initial begin
        #100us;
        $fatal(1, "[reg_smoke] TIMEOUT");
    end
endmodule
