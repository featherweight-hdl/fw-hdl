// S3.1: fw_rv_slice between pins, under a clocked fw_root: a pin-level
// producer A -> fw_rv_pin_in -> fw_rv_slice -> fw_rv_pin_out -> consumer B.
// Every field is sync, so this runs the sync-field pin paths. Checks: beats
// arrive in order with none lost; one beat per cycle at full ready; out.valid
// and out.data hold while B stalls; in.ready and out.valid read 0 in reset.
`include "svunit_defines.svh"
import fw_hdl_pkg::*;
import fw_std_pkg::*;

typedef bit [7:0] sbyte_t;

class s_root extends fw_component_root #(fw_component);
    fw_rv_slice #(sbyte_t) s;
    function new(string name);
        super.new(name);
    endfunction
    virtual function void build();
        s = new("s", this);
    endfunction
    virtual function void connect();
        fw_rv_pin #(sbyte_t)::find("slice_a").connect_in(s.in);
        fw_rv_pin #(sbyte_t)::find("slice_b").connect_out(s.out);
    endfunction
endclass

module fw_rv_slice_unit_test;
    import svunit_pkg::svunit_testcase;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    string name = "fw_rv_slice_ut";

    logic clk = 0, rst = 0;
    fw_root #(.Tbind(s_root)) u_root (.clock(clk), .reset(rst));

    logic   a_valid = 0, a_ready, b_valid, b_ready = 0;
    sbyte_t a_data = 0, b_data;
    fw_rv_pin_in  #(.T(sbyte_t), .NAME("slice_a")) u_a (
        .valid(a_valid), .data(a_data), .ready(a_ready));
    fw_rv_pin_out #(.T(sbyte_t), .NAME("slice_b")) u_b (
        .valid(b_valid), .data(b_data), .ready(b_ready));

    // A sends 0, 1, 2, ... holding valid until taken. full: A always valid
    // and B always ready; otherwise both random.
    bit       run_rtl, full;
    int       n_a, n_b, n_stall, bad_stall;
    sbyte_t   got[$];
    bit [7:0] lfsr = 8'h5a;
    logic     p_valid, p_ready;
    sbyte_t   p_data;
    always @(posedge clk) if (run_rtl) begin
        // A beat offered and not taken stays, unchanged.
        if (p_valid && !p_ready) begin
            n_stall++;
            bad_stall += int'(b_valid !== 1'b1) + int'(b_data !== p_data);
        end
        p_valid = b_valid;
        p_ready = b_ready;
        p_data  = b_data;
        if (a_valid && a_ready) begin
            a_data <= a_data + 1;
            n_a++;
        end
        a_valid <= full | lfsr[0] | (a_valid && !a_ready);
        if (b_valid && b_ready) begin
            got.push_back(b_data);
            n_b++;
        end
        b_ready <= full | lfsr[5] | lfsr[7];  // not lfsr[1:2]: they track a_valid
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

    task automatic m_cycle();
        clk = 1;
        #5;
        clk = 0;
        #5;
    endtask

    `SVUNIT_TESTS_BEGIN

    `SVTEST(slice_between_pins)
        s_root r;
        int    rst_bad, n_full0;
        rst = 1;
        #1;
        repeat (3) begin
            m_cycle();
            rst_bad += int'(a_ready !== 1'b0) + int'(b_valid !== 1'b0);
        end
        rst = 0;
        // Wait for the tree, then run full, then random.
        repeat (5) begin
            r = u_root.root;
            if (r != null && r.elaborated) run_rtl = 1;
            m_cycle();
        end
        `FAIL_UNLESS(run_rtl)
        full = 1;
        repeat (10) m_cycle();
        n_full0 = n_b;
        repeat (40) m_cycle();
        `FAIL_UNLESS_EQUAL(n_b - n_full0, 40)
        full = 0;
        repeat (400) m_cycle();
        `FAIL_UNLESS(r.m_kernel.active)
        `FAIL_UNLESS(n_stall >= 20)
        `FAIL_UNLESS_EQUAL(bad_stall, 0)
        `FAIL_UNLESS(n_b >= 100)
        `FAIL_UNLESS(n_a - n_b >= 0 && n_a - n_b <= 2)
        foreach (got[k]) `FAIL_UNLESS_EQUAL(got[k], sbyte_t'(k))
        // Back into reset: in.ready and out.valid read 0.
        run_rtl = 0;
        rst = 1;
        #1;
        repeat (2) begin
            m_cycle();
            rst_bad += int'(a_ready !== 1'b0) + int'(b_valid !== 1'b0);
        end
        `FAIL_UNLESS_EQUAL(rst_bad, 0)
        fw_sync_kernel::m_live = 0;
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
