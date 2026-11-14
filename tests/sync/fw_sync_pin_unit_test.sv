// S2.5: the pin bridge. Two pin-level modules (here always blocks: A is a
// producer, B a consumer) talk through a class comb() passthrough under a
// clocked fw_root: A -> fw_rv_pin_in -> p_wire -> fw_rv_pin_out -> B. Every
// field of p_wire is comb, so B's ready reaches A's ready, and A's valid and
// data reach B, in the same time step: at the edge (B's ready register) and
// between edges (the test pokes B's ready).
`include "svunit_defines.svh"
import fw_hdl_pkg::*;

typedef bit [7:0] pbyte_t;

// comb(): o.valid = i.valid, o.data = i.data, i.ready = o.ready.
class p_wire extends fw_component implements fw_combinational;
    fw_rv_sp_in  #(pbyte_t) i;
    fw_rv_sp_out #(pbyte_t) o;
    function new(string name, fw_component parent);
        super.new(name, parent);
        i = new(null, "i", this);
        o = new(null, "o", this);
        i.sig.set_comb("*");
        o.sig.set_comb("*");
        add_comb(this);
    endfunction
    virtual function void comb();
        o.set_valid(i.get_valid());
        o.set_data(i.get_data());
        i.set_ready(o.get_ready());
    endfunction
endclass

class p_root extends fw_component_root #(fw_component);
    p_wire w;
    function new(string name);
        super.new(name);
    endfunction
    virtual function void build();
        w = new("w", this);
    endfunction
    virtual function void connect();
        fw_rv_pin #(pbyte_t)::find("pin_a").connect_in(w.i);
        fw_rv_pin #(pbyte_t)::find("pin_b").connect_out(w.o);
    endfunction
endclass

module fw_sync_pin_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;

    string name = "fw_sync_pin_ut";

    logic clk = 0, rst = 0;
    fw_root #(.Tbind(p_root)) u_root (.clock(clk), .reset(rst));

    logic   a_valid = 0, a_ready, b_valid, b_ready = 0;
    pbyte_t a_data = 0, b_data;
    fw_rv_pin_in  #(.T(pbyte_t), .NAME("pin_a")) u_a (
        .valid(a_valid), .data(a_data), .ready(a_ready));
    fw_rv_pin_out #(.T(pbyte_t), .NAME("pin_b")) u_b (
        .valid(b_valid), .data(b_data), .ready(b_ready));

    // A sends 0, 1, 2, ... holding valid until taken; B's ready is random.
    bit       run_rtl;
    int       n_a, n_b;
    pbyte_t   got[$];
    bit [7:0] lfsr = 8'h5a;
    always @(posedge clk) if (run_rtl) begin
        if (a_valid && a_ready) begin
            a_data <= a_data + 1;
            n_a++;
        end
        a_valid <= lfsr[0] | (a_valid && !a_ready);
        if (b_valid && b_ready) begin
            got.push_back(b_data);
            n_b++;
        end
        b_ready <= lfsr[1];
        lfsr <= {lfsr[6:0], lfsr[7] ^ lfsr[5] ^ lfsr[4] ^ lfsr[3]};
    end

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

    // Pins not equal through the passthrough (0: all equal).
    function int m_bad();
        return int'(a_ready !== b_ready) + int'(b_valid !== a_valid)
             + int'(b_data !== a_data);
    endfunction

    `SVUNIT_TESTS_BEGIN

    `SVTEST(comb_passthrough_between_pins)
        p_root r;
        int    n_edge, n_mid, bad_edge, bad_mid;
        rst = 1;
        #1;
        repeat (2) begin clk = 1; #5; clk = 0; #5; end
        rst = 0;
        repeat (60) begin
            clk = 1;
            r = u_root.root;
            if (r != null && r.elaborated) run_rtl = 1;
            #1;
            if (run_rtl) begin
                n_edge++;
                bad_edge += m_bad();
            end
            #2;
            // Between edges: B's ready flips; A sees it before time moves.
            if (run_rtl && lfsr[5]) begin
                b_ready = !b_ready;
                #1;
                n_mid++;
                bad_mid += m_bad();
            end
            #2;
            clk = 0;
            #5;
        end
        `FAIL_UNLESS(r != null)
        `FAIL_UNLESS(r.m_kernel.active)
        `FAIL_UNLESS(n_edge >= 50)
        `FAIL_UNLESS(n_mid >= 10)
        `FAIL_UNLESS_EQUAL(bad_edge, 0)
        `FAIL_UNLESS_EQUAL(bad_mid, 0)
        `FAIL_UNLESS(n_a >= 10)
        `FAIL_UNLESS_EQUAL(n_b, n_a)
        foreach (got[k]) `FAIL_UNLESS_EQUAL(got[k], pbyte_t'(k))
        rst = 1;
        #1;
        fw_sync_kernel::m_live = 0;
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
