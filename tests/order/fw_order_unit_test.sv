// fw_order_pkg on clean streams, and each violation kind
// injected once and caught exactly once.
`include "svunit_defines.svh"

module fw_order_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_order_pkg::*;

    string name = "fw_order_ut";
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

    // Exactly one error, of this kind.
    function automatic bit only(fw_contract c, fw_contract_err_e kind);
        return c.n_errors == 1 && c.count(kind) == 1;
    endfunction

    `SVUNIT_TESTS_BEGIN

    // ---- fw_order_check ------------------------------------------------
    `SVTEST(in_order_clean)
        fw_order_check c = new("c");
        c.quiet = 1;
        for (longint i = 0; i < 10; i++) c.enter(i, 0, 0, i * 3, i);
        for (longint i = 0; i < 10; i++) c.leave(i, i * 3, 20 + i);
        c.finish();
        `FAIL_UNLESS_EQUAL(c.n_errors, 0)
        `FAIL_UNLESS_EQUAL(c.n_out, 10)
    `SVTEST_END

    `SVTEST(reorder_caught)
        fw_order_check c = new("c");
        c.quiet = 1;
        c.enter(1); c.enter(2);
        c.leave(2); c.leave(1);
        `FAIL_UNLESS(only(c, FW_E_REORDER))
    `SVTEST_END

    `SVTEST(per_key_allows_cross_key)
        fw_order_check c = new("c", fw_order_rule::in_order_per_key());
        c.quiet = 1;
        c.enter(1, 10); c.enter(2, 20); c.enter(3, 10);
        c.leave(2); c.leave(1); c.leave(3);
        `FAIL_UNLESS_EQUAL(c.n_errors, 0)
    `SVTEST_END

    `SVTEST(per_key_keeps_same_key)
        fw_order_check c = new("c", fw_order_rule::in_order_per_key());
        c.quiet = 1;
        c.enter(1, 10); c.enter(2, 20); c.enter(3, 10);
        c.leave(3); c.leave(2); c.leave(1);
        `FAIL_UNLESS(only(c, FW_E_REORDER))
    `SVTEST_END

    `SVTEST(class_pass)
        // class 1 may pass class 0 (e.g. a response past a non-posted request),
        // but not the other way round
        fw_order_rule r = new;
        fw_order_check c;
        r.set_pass(0, 1);
        c = new("c", r);
        c.quiet = 1;
        c.enter(1, 0, 0); c.enter(2, 0, 1);
        c.leave(2); c.leave(1);
        `FAIL_UNLESS_EQUAL(c.n_errors, 0)
        c.enter(3, 0, 1); c.enter(4, 0, 0);
        c.leave(4); c.leave(3);
        `FAIL_UNLESS(only(c, FW_E_REORDER))
    `SVTEST_END

    `SVTEST(unknown_duplicate_data_lost)
        fw_order_check c = new("c");
        c.quiet = 1;
        c.leave(9);
        `FAIL_UNLESS(only(c, FW_E_UNKNOWN))
        c = new("c"); c.quiet = 1;
        c.enter(1); c.enter(1);
        `FAIL_UNLESS(only(c, FW_E_DUPLICATE))
        c = new("c"); c.quiet = 1;
        c.enter(1); c.leave(1); c.leave(1);
        `FAIL_UNLESS(only(c, FW_E_DUPLICATE))
        c = new("c"); c.quiet = 1;
        c.enter(1, 0, 0, 'h55); c.leave(1, 'h56);
        `FAIL_UNLESS(only(c, FW_E_DATA))
        c = new("c"); c.quiet = 1;
        c.enter(1); c.enter(2); c.leave(1); c.finish();
        `FAIL_UNLESS(only(c, FW_E_LOST))
    `SVTEST_END

    `SVTEST(strict_after)
        // class 1 must leave strictly after an earlier class 0 it follows
        fw_order_rule r = new;
        fw_order_check c;
        r.set_strict(0, 1);
        c = new("c", r);
        c.quiet = 1;
        c.enter(1, 0, 0); c.enter(2, 0, 1);
        c.leave(1, 0, 5); c.leave(2, 0, 6);
        `FAIL_UNLESS_EQUAL(c.n_errors, 0)
        c.enter(3, 0, 0); c.enter(4, 0, 1);
        c.leave(3, 0, 7); c.leave(4, 0, 7);
        `FAIL_UNLESS(only(c, FW_E_SAME_CYCLE))
    `SVTEST_END

    `SVTEST(legal_next)
        fw_order_check c = new("c", fw_order_rule::in_order_per_key());
        longint ids[$];
        c.enter(1, 10); c.enter(2, 20); c.enter(3, 10);
        c.legal_next(ids);
        `FAIL_UNLESS_EQUAL(ids.size(), 2)
        `FAIL_UNLESS(ids[0] == 1 && ids[1] == 2)
    `SVTEST_END

    // ---- fw_lifetime ---------------------------------------------------
    `SVTEST(lifetime_clean)
        fw_lifetime l = new("l", 2);
        l.quiet = 1;
        l.alloc(1); l.alloc(2); l.use_id(1); l.free(1); l.alloc(3); l.free(2); l.free(3);
        l.finish();
        `FAIL_UNLESS_EQUAL(l.n_errors, 0)
        `FAIL_UNLESS_EQUAL(l.peak, 2)
    `SVTEST_END

    `SVTEST(lifetime_violations)
        fw_lifetime l = new("l");
        l.quiet = 1;
        l.alloc(1); l.alloc(1);
        `FAIL_UNLESS(only(l, FW_E_DOUBLE_ALLOC))
        l = new("l"); l.quiet = 1;
        l.free(4);
        `FAIL_UNLESS(only(l, FW_E_BAD_FREE))
        l = new("l"); l.quiet = 1;
        l.alloc(1); l.free(1); l.use_id(1);
        `FAIL_UNLESS(only(l, FW_E_USE_DEAD))
        l = new("l", 1); l.quiet = 1;
        l.alloc(1); l.alloc(2);
        `FAIL_UNLESS(only(l, FW_E_MAX_LIVE))
        l = new("l"); l.quiet = 1;
        l.alloc(7); l.finish();
        `FAIL_UNLESS(only(l, FW_E_LEAK))
    `SVTEST_END

    // ---- fw_dep_check --------------------------------------------------
    `SVTEST(dep_sticky)
        fw_dep_check d = new("d");
        d.quiet = 1;
        d.producer(1); d.producer(2);
        d.dependent(100);            // waits for 2, the youngest live
        d.retire(2);
        d.release_dep(100);
        d.dependent(101);            // waits for 1
        d.retire(1);
        d.producer(3);               // younger than 101: not waited for
        d.release_dep(101);
        d.dependent(102);            // nothing older live but 3
        `FAIL_UNLESS_EQUAL(d.n_errors, 0)
        d.release_dep(102);
        `FAIL_UNLESS(only(d, FW_E_DEP_EARLY))
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
