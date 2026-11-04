// fw_match_set for tests/xls/lib/test_match_set.py: package functions that
// fix K and T (small enough to try every argument, one slot, a size that is
// not a power of two, a 16-bit key); a step that calls it; and the sizes for
// the QoR probe.
`include "fw_std_macros.svh"

package lib_match_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef bit [1:0] k2_t;
    typedef bit [15:0] k16_t;

    function automatic bit [2:0] m3_hits(k2_t [2:0] keys, bit [2:0] valid, k2_t q);
        return fw_match_set#(3, k2_t)::hits(keys, valid, q);
    endfunction
    function automatic bit m3_any(k2_t [2:0] keys, bit [2:0] valid, k2_t q);
        return fw_match_set#(3, k2_t)::any(keys, valid, q);
    endfunction
    function automatic bit [1:0] m3_first(k2_t [2:0] keys, bit [2:0] valid, k2_t q);
        return fw_match_set#(3, k2_t)::first(keys, valid, q);
    endfunction

    function automatic bit m1_any(k2_t [0:0] keys, bit [0:0] valid, k2_t q);
        return fw_match_set#(1, k2_t)::any(keys, valid, q);
    endfunction
    function automatic bit [0:0] m1_first(k2_t [0:0] keys, bit [0:0] valid, k2_t q);
        return fw_match_set#(1, k2_t)::first(keys, valid, q);
    endfunction

    function automatic bit [4:0] m5_hits(k16_t [4:0] keys, bit [4:0] valid, k16_t q);
        return fw_match_set#(5, k16_t)::hits(keys, valid, q);
    endfunction
    function automatic bit [2:0] m5_first(k16_t [4:0] keys, bit [4:0] valid, k16_t q);
        return fw_match_set#(5, k16_t)::first(keys, valid, q);
    endfunction

    // QoR: one stage of the whole match, at the target's sizes.
    function automatic bit [3:0] q16_first(k16_t [15:0] keys, bit [15:0] valid, k16_t q);
        return fw_match_set#(16, k16_t)::first(keys, valid, q);
    endfunction
    function automatic bit [5:0] q64_first(k16_t [63:0] keys, bit [63:0] valid, k16_t q);
        return fw_match_set#(64, k16_t)::first(keys, valid, q);
    endfunction
    function automatic bit q64_any(k16_t [63:0] keys, bit [63:0] valid, k16_t q);
        return fw_match_set#(64, k16_t)::any(keys, valid, q);
    endfunction

    // A filter step: a set of 4 allowed 8-bit values, written in by `set`
    // ({slot, valid, value}); each value on `in` goes out with {hit, slot}
    // above it. The match is the caller's, in the caller's cycle.
    class match_filter extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(bit [10:0]))     set;
        fw_port #(fw_get_nb_if #(bit [7:0]))      in;
        fw_port #(fw_valid_put_if #(bit [10:0]))  out;

        protected bit [3:0][7:0] m_keys;
        protected bit [3:0]      m_valid;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction

        function void build();
            set = new("set", this);
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual function void step();
            bit [10:0] s;
            bit [7:0] x;
            bit [3:0][7:0] keys = m_keys;
            bit [3:0] valid = m_valid;
            if (in.t.try_get(x))
                out.t.put({fw_match_set#(4, bit [7:0])::any(m_keys, m_valid, x),
                           fw_match_set#(4, bit [7:0])::first(m_keys, m_valid, x), x});
            if (set.t.try_get(s)) begin
                keys[s[10:9]] = s[7:0];
                valid[s[10:9]] = s[8];
            end
            m_keys = keys;
            m_valid = valid;
        endfunction
    endclass
endpackage
