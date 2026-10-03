// C2: run-length encoder, as written in chisel-xls-assessment.md §4.4: a
// parameterized class (T7), a packed-struct payload (T3), state vs
// temporaries (P2/P3), a predicated send (P7) and an assignment pattern (E16).
// One change from the assessment's listing: its state variable `run` collides
// with the task run(), which is not legal SV; it is `cnt` here.
`include "fw_std_macros.svh"

package rle_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class rle_enc #(int W = 8) extends fw_component implements fw_runnable;
        typedef struct packed { bit [W-1:0] sym; bit [7:0] cnt; } pkt_t;
        fw_port #(fw_get_if #(bit [W-1:0]))  in;
        fw_port #(fw_put_if #(pkt_t))        out;
        bit [W-1:0] last;  bit [7:0] cnt;  bit valid;   // proc state

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin                    // one activation per iteration
                bit [W-1:0] x;
                in.t.get(x);
                if (valid && (x != last || cnt == 8'hFF)) out.t.put('{last, cnt});
                cnt   = (valid && x == last && cnt != 8'hFF) ? cnt + 1 : 1;
                last  = x;
                valid = 1;
            end
        endtask
    endclass
endpackage
