// Proc micro-tests: several operations on one channel per activation,
// channel operations in constant-bound loops, state arrays written several
// times per activation, and state used only under a guard.
`include "fw_std_macros.svh"

package micro_f5_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // Guarded double send: two sends on out in opposite arms of an if, and
    // three on aux in the arms of a case (exclusive: proven_mutually_exclusive).
    class f5_dsend extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        fw_port #(fw_put_if #(bit [7:0])) aux;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            aux = new("aux", this);
        endfunction

        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                if (x[0])
                    out.t.put(x + 8'd1);
                else
                    out.t.put(x ^ 8'hff);
                case (x[2:1])
                    2'd0: aux.t.put(x);
                    2'd1: aux.t.put(x + 8'd16);
                    2'd2: ;
                    default: aux.t.put(8'h00);
                endcase
            end
        endtask
    endclass

    // An unrolled per-VC loop: one receive and one send per VC, each under
    // v == k (exclusive for different k). Per-VC sums are state.
    class f5_vc extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [1:0]))  sel;
        fw_port #(fw_get_if #(bit [7:0]))  in;
        fw_port #(fw_put_if #(bit [11:0])) out;   // {vc, sum}
        bit [9:0] sum[4];

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            sel = new("sel", this);
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                bit [1:0] v;
                bit [7:0] x;
                sel.t.get(v);
                for (int k = 0; k < 4; k++) begin
                    if (v == k) begin
                        in.t.get(x);
                        sum[k] = sum[k] + x;
                        out.t.put({k[1:0], sum[k]});
                    end
                end
            end
        endtask
    endclass

    // A CAM-like table: release one slot and install a key in the lowest
    // free slot in the same activation. vld and keys are written several
    // times per activation (an unrolled search, then the release).
    class f5_cam extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [11:0])) in;   // {rel, rel_idx[1:0], ins, key[7:0]}
        fw_port #(fw_put_if #(bit [2:0]))  out;  // {ok, slot[1:0]}
        bit [3:0] vld;
        bit [7:0] keys[4];

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                bit [11:0] c;
                bit        done;
                bit [1:0]  slot;
                in.t.get(c);
                if (c[11])
                    vld[c[10:9]] = 1'b0;
                if (c[8]) begin
                    for (int k = 0; k < 4; k++) begin
                        if (!done && !vld[k]) begin
                            vld[k] = 1'b1;
                            keys[k] = c[7:0];
                            slot = k[1:0];
                            done = 1'b1;
                        end
                    end
                    out.t.put({done, slot});
                end
            end
        endtask
    endclass

    // Multi-lane push: up to three lanes into an 8-entry ring per activation.
    class f5_push extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [25:0])) in;   // {n[1:0], d2, d1, d0}
        fw_port #(fw_put_if #(bit [7:0]))  out;  // the newest entry
        bit [7:0] q[8];
        bit [2:0] wp;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                bit [25:0] c;
                in.t.get(c);
                for (int l = 0; l < 3; l++) begin
                    if (l < c[25:24]) begin
                        q[wp] = c[8*l +: 8];
                        wp = wp + 3'd1;
                    end
                end
                out.t.put(q[wp - 3'd1]);
            end
        endtask
    endclass

    // State used only under a guard: acc's state_read and next_value are
    // predicated on x[0].
    class f5_gstate extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0]))  in;
        fw_port #(fw_put_if #(bit [15:0])) out;
        bit [15:0] acc = 16'd100;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                if (x[0]) begin
                    acc = acc + x;
                    out.t.put(acc);
                end
            end
        endtask
    endclass

    // Two adjacent sends whose guards can both hold: runtime_mutually_exclusive.
    // XLS asserts in simulation that at most one fires per activation.
    class f5_rt extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                if (x[0])
                    out.t.put(x);
                if (x[1])
                    out.t.put(x + 8'd1);
            end
        endtask
    endclass

    // Rejected: guards that can both hold, with another send between.
    class f5_bad_gap extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        fw_port #(fw_put_if #(bit [7:0])) aux;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            aux = new("aux", this);
        endfunction

        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                if (x[0])
                    out.t.put(x);
                aux.t.put(x);
                if (x[1])
                    out.t.put(x + 8'd1);
            end
        endtask
    endclass

    // Rejected: an unguarded send and a guarded one on the same channel.
    class f5_bad_bare extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                bit [7:0] x;
                in.t.get(x);
                out.t.put(x);
                if (x[0])
                    out.t.put(x + 8'd1);
            end
        endtask
    endclass

endpackage
