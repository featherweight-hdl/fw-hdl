// S2.1: the struct-port value holders (src/sync/). Sync writes are seen by
// the peer after commit, comb writes at once, reset-force holds during reset
// and releases on the first cycle out of it, and the writer reading its own
// sync output sees `cur`.
`include "svunit_defines.svh"

// A reset domain whose level the test sets.
class fw_sync_ut_rst implements fw_hdl_pkg::fw_reset_domain_if;
    bit lvl;
    virtual function bit in_reset(); return lvl; endfunction
    virtual task wait_assert(); endtask
    virtual task wait_deassert(); endtask
    virtual function bit is_async(); return 0; endfunction
    virtual function fw_hdl_pkg::fw_clock_domain_if sync_clock(); return null; endfunction
    virtual function fw_hdl_pkg::fw_domain_kind_e domain_kind();
        return fw_hdl_pkg::FW_DOMAIN_RESET;
    endfunction
    virtual function string domain_name(); return "ut_rst"; endfunction
    virtual function int domain_nsrc(); return 0; endfunction
    virtual function fw_hdl_pkg::fw_domain_if domain_src(int i); return null; endfunction
    virtual function fw_hdl_pkg::fw_domain_if domain_equiv(); return this; endfunction
endclass

module fw_sync_holder_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;

    string name = "fw_sync_holder_ut";
    svunit_testcase svunit_ut;

    function void build();
        svunit_ut = new(name);
    endfunction
    task setup();
        svunit_ut.setup();
    endtask
    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    `SVTEST(sync_write_after_commit)
        fw_rv_sig #(bit [7:0]) s = new("ch");
        fw_rv_sp_out #(bit [7:0]) o = new(s);
        fw_rv_sp_in #(bit [7:0])  i = new(s);
        o.set_valid(1); o.set_data(8'h5a);
        i.set_ready(1);
        `FAIL_UNLESS_EQUAL(i.get_valid(), 0)
        `FAIL_UNLESS_EQUAL(i.get_data(), 0)
        `FAIL_UNLESS_EQUAL(o.get_ready(), 0)
        s.commit();
        `FAIL_UNLESS_EQUAL(i.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(i.get_data(), 8'h5a)
        `FAIL_UNLESS_EQUAL(o.get_ready(), 1)
        // Unwritten: holds like a register.
        s.commit();
        `FAIL_UNLESS_EQUAL(i.get_data(), 8'h5a)
        // fw_sig too.
        begin
            fw_sig #(int) g = new("g");
            g.set(7);
            `FAIL_UNLESS_EQUAL(g.get(), 0)
            g.commit();
            `FAIL_UNLESS_EQUAL(g.get(), 7)
        end
    `SVTEST_END

    `SVTEST(comb_write_at_once)
        fw_rv_sig #(bit [7:0]) s = new("ch");
        fw_rv_sp_out #(bit [7:0]) o = new(s);
        fw_rv_sp_in #(bit [7:0])  i = new(s);
        fw_sig #(int) g = new("g");
        s.f_valid.comb = 1;
        s.f_data.comb  = 1;
        g.f_val.comb   = 1;
        o.set_valid(1); o.set_data(8'h33);
        i.set_ready(1);                       // ready stays sync
        `FAIL_UNLESS_EQUAL(i.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(i.get_data(), 8'h33)
        `FAIL_UNLESS_EQUAL(o.get_ready(), 0)
        g.set(9);
        `FAIL_UNLESS_EQUAL(g.get(), 9)
        // commit leaves comb values alone.
        o.set_valid(0);
        s.commit();
        `FAIL_UNLESS_EQUAL(i.get_valid(), 0)
        `FAIL_UNLESS_EQUAL(o.get_ready(), 1)
    `SVTEST_END

    `SVTEST(reset_force_holds_and_releases)
        fw_sync_ut_rst r = new;
        fw_rv_sig #(bit [7:0]) s = new("ch");
        fw_rv_sp_out #(bit [7:0]) o = new(s);
        fw_rv_sp_in #(bit [7:0])  i = new(s);
        fw_sig #(bit [3:0]) g = new("g");
        s.set_reset(r);
        g.set_reset(r);
        g.set_reset_force(4'ha);
        r.lvl = 1;
        o.set_valid(1); o.set_data(8'h11);
        i.set_ready(1);
        g.set(4'h3);
        repeat (3) begin
            s.commit(); g.commit();
            `FAIL_UNLESS_EQUAL(i.get_valid(), 0)
            `FAIL_UNLESS_EQUAL(o.get_ready(), 0)
            `FAIL_UNLESS_EQUAL(i.get_data(), 8'h11)   // data is not forced
            `FAIL_UNLESS_EQUAL(g.get(), 4'ha)
        end
        // First cycle out of reset: the registers show.
        r.lvl = 0;
        `FAIL_UNLESS_EQUAL(i.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(o.get_ready(), 1)
        `FAIL_UNLESS_EQUAL(g.get(), 4'h3)
    `SVTEST_END

    `SVTEST(writer_reads_own_cur)
        fw_sync_ut_rst r = new;
        fw_rv_sig #(bit [7:0]) s = new("ch");
        fw_rv_sp_out #(bit [7:0]) o = new(s);
        fw_rv_sp_in #(bit [7:0])  i = new(s);
        fw_sig #(int) g = new("g");
        s.set_reset(r);
        o.set_valid(1); o.set_data(8'h44);
        i.set_ready(1);
        g.set(5);
        `FAIL_UNLESS_EQUAL(o.get_valid(), 0)
        `FAIL_UNLESS_EQUAL(o.get_data(), 0)
        `FAIL_UNLESS_EQUAL(i.get_ready(), 0)
        `FAIL_UNLESS_EQUAL(g.get_own(), 0)
        s.commit(); g.commit();
        `FAIL_UNLESS_EQUAL(o.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(o.get_data(), 8'h44)
        `FAIL_UNLESS_EQUAL(i.get_ready(), 1)
        `FAIL_UNLESS_EQUAL(g.get_own(), 5)
        // In reset the writer still sees its register, not the forced value.
        r.lvl = 1;
        `FAIL_UNLESS_EQUAL(o.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(i.get_ready(), 1)
        `FAIL_UNLESS_EQUAL(i.get_valid(), 0)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
