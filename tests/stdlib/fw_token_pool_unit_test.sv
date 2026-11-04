// fw_token_pool (4 tokens) and fw_slot_reserve (6 slots, up to 3 a request),
// each carrying a 4-bit value (src/std/pool/): the per-cycle rules in the
// class headers, one edge at a time.
//
// Each request and release port has a source that offers its queued values
// in order; each grant has a sink that keeps what it is sent. Grants: tok
// {token[1:0], value}, gnt {k[1:0], value}. Contract: no token is granted
// while held (fw_lifetime, at most 4 live), checked throughout.
`include "svunit_defines.svh"
`include "fw_hdl_macros.svh"

package fw_token_pool_ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_order_pkg::*;

    class tp_src #(type T = int) implements fw_get_nb_if #(T);
        T           q[$];
        fw_lifetime life;           // releases: free the token put back
        virtual task get(output T t);
            wait (q.size() > 0);
            void'(try_get(t));
        endtask
        virtual function bit try_get(inout T t);
            if (q.size() == 0)
                return 1'b0;
            t = q.pop_front();
            if (life != null && life.is_live(longint'(t)))
                life.free(longint'(t));
            return 1'b1;
        endfunction
    endclass

    class tp_snk #(type T = int, int SHIFT = 4) implements fw_valid_put_if #(T);
        T           got[$];
        fw_lifetime life;           // grants: allocate the token
        virtual function void put(input T t);
            got.push_back(t);
            if (life != null)
                life.alloc(longint'(t >> SHIFT));
        endfunction
    endclass

    class tp_top extends fw_component;
        fw_token_pool #(4, bit [3:0])      p;
        fw_slot_reserve #(6, 3, bit [3:0]) r;
        fw_lifetime life;
        tp_src #(bit [3:0]) s_req = new;
        tp_src #(bit [1:0]) s_rel = new;
        tp_snk #(bit [5:0]) o_tok = new;
        tp_src #(bit [5:0]) s_rsv = new;
        tp_src #(bit [1:0]) s_rrel = new;
        tp_snk #(bit [5:0]) o_gnt = new;
        fw_export #(fw_get_nb_if #(bit [3:0]))    e_req;
        fw_export #(fw_get_nb_if #(bit [1:0]))    e_rel;
        fw_export #(fw_valid_put_if #(bit [5:0])) e_tok;
        fw_export #(fw_get_nb_if #(bit [5:0]))    e_rsv;
        fw_export #(fw_get_nb_if #(bit [1:0]))    e_rrel;
        fw_export #(fw_valid_put_if #(bit [5:0])) e_gnt;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            p = new("p", this);
            r = new("r", this);
            life = new("life", 4);
            life.quiet = 1;
            s_rel.life = life;
            o_tok.life = life;
            e_req = new("e_req", this, s_req);
            e_rel = new("e_rel", this, s_rel);
            e_tok = new("e_tok", this, o_tok);
            e_rsv = new("e_rsv", this, s_rsv);
            e_rrel = new("e_rrel", this, s_rrel);
            e_gnt = new("e_gnt", this, o_gnt);
        endfunction
        function void connect();
            p.req.connect(e_req);
            p.rel.connect(e_rel);
            p.tok.connect(e_tok);
            r.rsv.connect(e_rsv);
            r.rel.connect(e_rrel);
            r.gnt.connect(e_gnt);
        endfunction
    endclass
endpackage

module fw_token_pool_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import fw_token_pool_ut_pkg::*;

    string name = "fw_token_pool_ut";
    svunit_testcase svunit_ut;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(tp_top, u_tp, clock, reset)
    `fw_root_end

    function void build();
        svunit_ut = new(name);
    endfunction

    task automatic edges(int n);
        repeat (n) begin
            @(posedge clock);
            @(negedge clock);
        end
    endtask

    function automatic bit [5:0] tv(bit [1:0] tok, bit [3:0] v);
        return {tok, v};
    endfunction

    // Put back everything the earlier test left held, twice, so that a
    // request the reserve was holding is granted and then released too.
    task automatic release_all();
        repeat (2) begin
            for (int i = 0; i < 4; i++)
                u_tp.root.s_rel.q.push_back(i);
            u_tp.root.s_rrel.q.push_back(3);
            u_tp.root.s_rrel.q.push_back(3);
            edges(5);
        end
    endtask

    task setup();
        svunit_ut.setup();
        reset = 1;
        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_tp.root != null && u_tp.root.elaborated);
        @(negedge clock);
        u_tp.root.s_req.q.delete();
        u_tp.root.s_rsv.q.delete();
        release_all();
        u_tp.root.o_tok.got.delete();
        u_tp.root.o_gnt.got.delete();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // Five requests: tokens 0-3 in order, one an edge, with their values;
    // then the pool is empty and the fifth is not taken.
    `SVTEST(pool_lowest_first_then_exhausted)
        for (int i = 0; i < 5; i++)
            u_tp.root.s_req.q.push_back(4'ha + i);
        edges(6);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got.size(), 4)
        for (int i = 0; i < 4; i++)
            `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got[i], tv(i, 4'ha + i))
        `FAIL_UNLESS_EQUAL(u_tp.root.s_req.q.size(), 1)
        `FAIL_UNLESS_EQUAL(u_tp.root.life.n_errors, 0)
    `SVTEST_END

    // A token put back is free from the next edge: the waiting request is
    // not granted at the edge that takes the release, but at the one after.
    `SVTEST(pool_release_then_regrant)
        for (int i = 0; i < 5; i++)
            u_tp.root.s_req.q.push_back(i);
        edges(5);
        u_tp.root.s_rel.q.push_back(2);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got.size(), 4)
        edges(1);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got.size(), 5)
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got[4], tv(2, 4))
        `FAIL_UNLESS_EQUAL(u_tp.root.life.n_errors, 0)
    `SVTEST_END

    // With 3 and 1 put back, the next request gets 1, the lowest free.
    `SVTEST(pool_lowest_free_reused)
        for (int i = 0; i < 4; i++)
            u_tp.root.s_req.q.push_back(i);
        edges(4);
        u_tp.root.s_rel.q.push_back(3);
        u_tp.root.s_rel.q.push_back(1);
        edges(2);
        u_tp.root.s_req.q.push_back(4'h7);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got[4], tv(1, 4'h7))
        `FAIL_UNLESS_EQUAL(u_tp.root.life.n_errors, 0)
    `SVTEST_END

    // Putting back token 3, which is free, does nothing: 0 and 1 stay held,
    // so three more requests get 2 and 3, and the third waits.
    `SVTEST(pool_free_token_put_back)
        u_tp.root.s_req.q.push_back(0);
        u_tp.root.s_req.q.push_back(1);
        edges(2);
        u_tp.root.s_rel.q.push_back(3);
        edges(1);
        for (int i = 0; i < 3; i++)
            u_tp.root.s_req.q.push_back(4'h8 + i);
        edges(4);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got.size(), 4)
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got[2], tv(2, 4'h8))
        `FAIL_UNLESS_EQUAL(u_tp.root.o_tok.got[3], tv(3, 4'h9))
        `FAIL_UNLESS_EQUAL(u_tp.root.s_req.q.size(), 1)
        `FAIL_UNLESS_EQUAL(u_tp.root.life.n_errors, 0)
    `SVTEST_END

    // 3 + 3 fill the 6 slots, each granted at the edge it is taken; the 1
    // behind them is taken and held. Releasing 3 frees them from the next
    // edge, and the held request is granted then.
    `SVTEST(reserve_grant_hold_release)
        u_tp.root.s_rsv.q.push_back({2'd3, 4'ha});
        u_tp.root.s_rsv.q.push_back({2'd3, 4'hb});
        u_tp.root.s_rsv.q.push_back({2'd1, 4'hc});
        edges(4);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got.size(), 2)
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got[0], {2'd3, 4'ha})
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got[1], {2'd3, 4'hb})
        `FAIL_UNLESS_EQUAL(u_tp.root.s_rsv.q.size(), 0)
        u_tp.root.s_rrel.q.push_back(3);
        edges(1);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got.size(), 2)
        edges(1);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got.size(), 3)
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got[2], {2'd1, 4'hc})
    `SVTEST_END

    // Admission is in order: a held request for 2 keeps a request for 1
    // waiting though a slot is free. Once 3 more come back, both go.
    `SVTEST(reserve_in_order)
        u_tp.root.s_rsv.q.push_back({2'd3, 4'h1});
        u_tp.root.s_rsv.q.push_back({2'd3, 4'h2});
        u_tp.root.s_rsv.q.push_back({2'd2, 4'h3});
        u_tp.root.s_rsv.q.push_back({2'd1, 4'h4});
        edges(4);
        u_tp.root.s_rrel.q.push_back(1);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got.size(), 2)
        `FAIL_UNLESS_EQUAL(u_tp.root.s_rsv.q.size(), 1)
        u_tp.root.s_rrel.q.push_back(3);
        edges(3);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got.size(), 4)
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got[2], {2'd2, 4'h3})
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got[3], {2'd1, 4'h4})
    `SVTEST_END

    // Releasing more than is reserved frees what is reserved and no more:
    // after 3 reserved and 6 released, 6 are free, not 9.
    `SVTEST(reserve_over_release)
        u_tp.root.s_rsv.q.push_back({2'd3, 4'h1});
        edges(1);
        u_tp.root.s_rrel.q.push_back(3);
        u_tp.root.s_rrel.q.push_back(3);
        edges(2);
        u_tp.root.s_rsv.q.push_back({2'd3, 4'h2});
        u_tp.root.s_rsv.q.push_back({2'd3, 4'h3});
        u_tp.root.s_rsv.q.push_back({2'd1, 4'h4});
        edges(4);
        `FAIL_UNLESS_EQUAL(u_tp.root.o_gnt.got.size(), 3)
        `FAIL_UNLESS_EQUAL(u_tp.root.s_rsv.q.size(), 0)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
