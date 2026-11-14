// S2.2: per-field semantics. set_comb() takes a comma list of fields, `*`,
// or either prefixed with the holder's name (`ch.*`); freeze() ends the
// changes; an unknown field or a change after freeze is an error naming the
// field and the holder. SVUnit can't catch $fatal, so the error paths are
// tested through check_comb(), which set_comb() fatals on.
`include "svunit_defines.svh"

module fw_sync_sem_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;

    string name = "fw_sync_sem_ut";
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

    `SVTEST(set_comb_list_and_shorthand)
        fw_rv_sig #(bit [7:0]) a = new("ar");
        fw_rv_sig #(bit [7:0]) b = new("aw");
        fw_rv_sig #(bit [7:0]) c = new("w");
        a.set_comb("valid, data");
        `FAIL_UNLESS_EQUAL(a.f_valid.comb, 1)
        `FAIL_UNLESS_EQUAL(a.f_ready.comb, 0)
        `FAIL_UNLESS_EQUAL(a.f_data.comb, 1)
        b.set_comb("aw.*");
        `FAIL_UNLESS_EQUAL(b.f_valid.comb, 1)
        `FAIL_UNLESS_EQUAL(b.f_ready.comb, 1)
        `FAIL_UNLESS_EQUAL(b.f_data.comb, 1)
        c.set_comb("w.ready");
        `FAIL_UNLESS_EQUAL(c.f_valid.comb, 0)
        `FAIL_UNLESS_EQUAL(c.f_ready.comb, 1)
        // The flag drives the behaviour: comb ready is seen at once.
        begin
            fw_rv_sp_in #(bit [7:0])  i = new(c);
            fw_rv_sp_out #(bit [7:0]) o = new(c);
            i.set_ready(1);
            `FAIL_UNLESS_EQUAL(o.get_ready(), 1)
        end
    `SVTEST_END

    `SVTEST(unknown_field_names_field_and_holder)
        fw_rv_sig #(bit [7:0]) a = new("ar");
        string err, exp;
        bit    e;
        e = a.check_comb("valid, bogus", err);
        `FAIL_UNLESS_EQUAL(e, 1)
        exp = "no field \"bogus\" in holder \"ar\"";
        `FAIL_UNLESS_STR_EQUAL(err, exp)
        e = a.check_comb("aw.*", err);
        `FAIL_UNLESS_EQUAL(e, 1)
        `FAIL_UNLESS(err.len() > 0)
        e = a.check_comb(" , ", err);
        `FAIL_UNLESS_EQUAL(e, 1)
        e = a.check_comb("ar.valid,*", err);
        `FAIL_UNLESS_EQUAL(e, 0)
        `FAIL_UNLESS_EQUAL(err.len(), 0)
        // A failed check changes nothing.
        `FAIL_UNLESS_EQUAL(a.f_valid.comb, 0)
    `SVTEST_END

    `SVTEST(freeze_rejects_later_change)
        fw_sig #(int) g = new("g");
        string err;
        bit    e;
        g.set_comb("val");
        `FAIL_UNLESS_EQUAL(g.f_val.comb, 1)
        g.freeze();
        e = g.check_comb("val", err);
        `FAIL_UNLESS_EQUAL(e, 1)
        `FAIL_UNLESS(err.len() > 0)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
