// S2.3: connection and driver checks. connect() and connect_up() make the
// ends share one holder; fw_sync_conn checks one driver per field and no
// undriven input that is not optional. SVUnit can't catch $fatal, so the
// error paths are tested through check_tree(), which check() fatals on.
`include "svunit_defines.svh"

module fw_sync_conn_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;

    typedef bit [7:0] byte_t;

    // A bridge to a holder the test owns and may swap (as link() does to a
    // role port's channel).
    class tb_bridge extends fw_sync_bridge;
        fw_sig_holder h;
        function new(fw_sync_port view, fw_sig_holder h);
            super.new(view);
            this.h = h;
        endfunction
        virtual function fw_sig_holder target();
            return h;
        endfunction
    endclass

    string name = "fw_sync_conn_ut";
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

    `SVTEST(connect_shares_holder)
        fw_component top = new("top", null);
        fw_component a   = new("a", top);
        fw_component b   = new("b", top);
        fw_rv_sp_out #(byte_t) o = new(null, "o", a);
        fw_rv_sp_in #(byte_t)  i = new(null, "i", b);
        string err;
        bit    e;
        `FAIL_IF(o.sig == i.sig)
        o.connect(i);
        `FAIL_UNLESS(o.sig == i.sig)
        `FAIL_UNLESS(o.holder() == i.holder())
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 0)
        o.set_valid(1);
        o.set_data(8'h5a);
        i.set_ready(1);
        o.sig.commit();
        `FAIL_UNLESS_EQUAL(i.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(i.get_data(), 8'h5a)
        `FAIL_UNLESS_EQUAL(o.get_ready(), 1)
    `SVTEST_END

    `SVTEST(double_driver_names_both)
        fw_component top = new("top", null);
        fw_component a   = new("a", top);
        fw_component b   = new("b", top);
        fw_component c   = new("c", top);
        fw_rv_sp_out #(byte_t) oa = new(null, "o", a);
        fw_rv_sp_out #(byte_t) ob = new(null, "o", b);
        fw_rv_sp_in #(byte_t)  i  = new(null, "i", c);
        string err, exp;
        bit    e;
        oa.connect(i);
        i.connect(ob);
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 1)
        exp = "field \"valid\" of \"o\" has two drivers: top.a.o and top.b.o";
        `FAIL_UNLESS_STR_EQUAL(err, exp)
    `SVTEST_END

    `SVTEST(undriven_input_unless_optional)
        fw_component top = new("top", null);
        fw_component c   = new("c", top);
        fw_rv_sp_in #(byte_t) i = new(null, "i", c);
        string err, exp;
        bit    e;
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 1)
        exp = "top.c.i: input field \"valid\" is not driven (connect it, or set_optional())";
        `FAIL_UNLESS_STR_EQUAL(err, exp)
        i.set_optional();
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 0)
    `SVTEST_END

    `SVTEST(arrays_of_4_ports)
        fw_component top = new("top", null);
        fw_component a   = new("a", top);
        fw_component b   = new("b", top);
        fw_rv_sp_out #(byte_t) o[4];
        fw_rv_sp_in #(byte_t)  i[4];
        string err, exp;
        bit    e;
        foreach (o[k]) begin
            o[k] = new(null, $sformatf("o[%0d]", k), a);
            i[k] = new(null, $sformatf("i[%0d]", k), b);
        end
        // o[2] is left unconnected: its ready input is undriven.
        foreach (o[k]) if (k != 2) o[k].connect(i[k]);
        i[2].connect(o[3]);
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 1)
        exp = "top.a.o[2]: input field \"ready\" is not driven (connect it, or set_optional())";
        `FAIL_UNLESS_STR_EQUAL(err, exp)
        // The merged net keeps the holder of the end connect() was called on.
        o[2].set_optional();
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 1)
        exp = "field \"ready\" of \"i[2]\" has two drivers: top.b.i[2] and top.b.i[3]";
        `FAIL_UNLESS_STR_EQUAL(err, exp)
        // Rebuild, all four pairs: clean, four distinct holders.
        top = new("top", null);
        a   = new("a", top);
        b   = new("b", top);
        foreach (o[k]) begin
            o[k] = new(null, $sformatf("o[%0d]", k), a);
            i[k] = new(null, $sformatf("i[%0d]", k), b);
            o[k].connect(i[k]);
        end
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 0)
        `FAIL_UNLESS(i[1].sig == o[1].sig)
        `FAIL_IF(i[1].sig == o[2].sig)
        o[2].set_valid(1);
        o[2].sig.commit();
        `FAIL_UNLESS_EQUAL(i[2].get_valid(), 1)
        `FAIL_UNLESS_EQUAL(i[1].get_valid(), 0)
    `SVTEST_END

    `SVTEST(connect_up_through_parent)
        // top { p { pc.o -> p.o } -> c { c.i -> cc.i } }
        fw_component top = new("top", null);
        fw_component p   = new("p", top);
        fw_component pc  = new("pc", p);
        fw_component c   = new("c", top);
        fw_component cc  = new("cc", c);
        fw_rv_sp_out #(byte_t) pco = new(null, "o", pc);
        fw_rv_sp_out #(byte_t) po  = new(null, "o", p);
        fw_rv_sp_in #(byte_t)  ci  = new(null, "i", c);
        fw_rv_sp_in #(byte_t)  cci = new(null, "i", cc);
        string err, exp;
        bit    e;
        e = pco.check_connect_up(ci, err);
        `FAIL_UNLESS_EQUAL(e, 1)
        exp = "top.c.i is not a port of top.p.pc's parent";
        `FAIL_UNLESS_STR_EQUAL(err, exp)
        pco.connect_up(po);
        cci.connect_up(ci);
        po.connect(ci);
        `FAIL_UNLESS(pco.sig == cci.sig)
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 0)
        // A comb valid from the inner producer reaches the inner consumer.
        pco.sig.set_comb("valid");
        pco.set_valid(1);
        `FAIL_UNLESS_EQUAL(cci.get_valid(), 1)
    `SVTEST_END

    `SVTEST(merge_keeps_comb)
        // set_comb in build() on either end's holder survives the connect.
        fw_rv_sp_out #(byte_t) o = new(null, "ar");
        fw_rv_sp_in #(byte_t)  i = new(null, "ar");
        i.sig.set_comb("ready");
        o.connect(i);
        `FAIL_UNLESS_EQUAL(o.sig.f_ready.comb, 1)
        `FAIL_UNLESS_EQUAL(o.sig.f_valid.comb, 0)
    `SVTEST_END

    `SVTEST(bridge_adopts_holder_after_connect)
        // Two children's views bridged to one outside holder share a net
        // holding it; the holder swapped before resolve is the one taken;
        // set_comb from build() carries over.
        fw_component top = new("top", null);
        fw_component a   = new("a", top);
        fw_component b   = new("b", top);
        fw_rv_sp_out #(byte_t) o = new(null, "o", a);
        fw_rv_sp_in #(byte_t)  i = new(null, "i", b);
        fw_rv_sig #(byte_t) h1 = new("aw");
        fw_rv_sig #(byte_t) h2 = new("aw");
        tb_bridge bo = new(o, h1);
        tb_bridge bi = new(i, h1);
        string err;
        bit    e;
        i.sig.set_comb("ready");
        bo.h = h2;
        bi.h = h2;
        fw_sync_bridge::resolve_tree(top);
        `FAIL_UNLESS(o.sig == h2)
        `FAIL_UNLESS(i.sig == h2)
        `FAIL_UNLESS(o.net == i.net)
        `FAIL_UNLESS_EQUAL(h2.f_ready.comb, 1)
        `FAIL_UNLESS_EQUAL(h1.f_ready.comb, 0)
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 0)
        o.set_valid(1);
        o.set_data(8'h3c);
        h2.commit();
        `FAIL_UNLESS_EQUAL(i.get_valid(), 1)
        `FAIL_UNLESS_EQUAL(i.get_data(), 8'h3c)
    `SVTEST_END

    `SVTEST(bridge_two_drivers_named)
        // Two producer views bridged to one holder: the driver check names both.
        fw_component top = new("top", null);
        fw_component a   = new("a", top);
        fw_component b   = new("b", top);
        fw_rv_sp_out #(byte_t) o1 = new(null, "o1", a);
        fw_rv_sp_out #(byte_t) o2 = new(null, "o2", b);
        fw_rv_sig #(byte_t) h = new("b");
        tb_bridge b1 = new(o1, h);
        tb_bridge b2 = new(o2, h);
        string err;
        bit    e;
        fw_sync_bridge::resolve_tree(top);
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 1)
        `FAIL_UNLESS_STR_EQUAL(err, "field \"valid\" of \"b\" has two drivers: top.a.o1 and top.b.o2")
    `SVTEST_END

    `SVTEST(bridge_alone_is_optional)
        // A consumer view bridged to a holder no view drives (a role port's
        // owner writes it) is not an undriven-input error.
        fw_component top = new("top", null);
        fw_component a   = new("a", top);
        fw_rv_sp_in #(byte_t) i = new(null, "i", a);
        fw_rv_sig #(byte_t) h = new("ar");
        tb_bridge bi = new(i, h);
        string err;
        bit    e;
        fw_sync_bridge::resolve_tree(top);
        e = fw_sync_conn::check_tree(top, err);
        `FAIL_UNLESS_EQUAL(e, 0)
        h.set_valid(1);
        h.commit();
        `FAIL_UNLESS_EQUAL(i.get_valid(), 1)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
