// X0 proc micro-tests: one component class per proc row (xls-phase0.md §3.4).
// Each class's run() is `<prologue> forever <activation>`; the harness feeds
// its get ports from queues and records its put ports.
`include "fw_std_macros.svh"

package micro_proc_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    typedef struct packed {
        bit [7:0] data;
        bit       last;
    } beat_t;

    // P1, P2, P4, P5, P6, P7: accumulate; on a zero, send the sum and reset.
    class p_acc extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0]))  in;
        fw_port #(fw_put_if #(bit [15:0])) out;
        bit [15:0] sum = 5;

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
                bit [7:0]  x;
                bit [15:0] s;
                in.t.get(x);
                s = sum + x;
                if (x == 0) begin
                    out.t.put(s);
                    sum = 0;
                end else begin
                    sum = s;
                end
            end
        endtask
    endclass

    // P2/P3/P4: a prologue local is state (initialized by the prologue); a
    // local inside forever is a temporary, back to 0 on every activation.
    class p_temp extends fw_component implements fw_runnable;
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
            bit [7:0] count = 10;
            count += 1;
            forever begin
                bit [7:0] t;
                bit [7:0] x;
                if (count == 12) t = 100;
                in.t.get(x);
                out.t.put(x + count + t);
                count++;
            end
        endtask
    endclass

    // P7: a get and a put, each under a condition; P8: program order.
    class p_pred extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) a;
        fw_port #(fw_get_if #(bit [7:0])) b;
        fw_port #(fw_put_if #(bit [7:0])) o;
        bit [7:0] last_y;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            a = new("a", this);
            b = new("b", this);
            o = new("o", this);
        endfunction

        virtual task run();
            forever begin
                bit [7:0] x;
                bit [7:0] y;
                a.t.get(x);
                if (x[0]) begin
                    b.t.get(y);
                    last_y = y;
                end
                if (x + y > 10) o.t.put(x + y);
            end
        endtask
    endclass

    // T3/E15/E16: a packed-struct payload; frame bytes into 16-bit words.
    class p_frame extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(beat_t))      in;
        fw_port #(fw_put_if #(bit [16:0]))  out;   // {last, word}
        bit [7:0] hi;
        bit       have_hi;

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
                beat_t b;
                in.t.get(b);
                if (!have_hi && !b.last) begin
                    hi = b.data;
                    have_hi = 1;
                end else begin
                    out.t.put({b.last, have_hi ? hi : 8'h00, b.data});
                    have_hi = 0;
                end
            end
        endtask
    endclass

    // S7: an immediate assertion under a condition stops the run; what was
    // sent before it stands.
    class p_assert extends fw_component implements fw_runnable;
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
                if (x > 100)
                    assert (x != 200) else $error("x reached 200");
                out.t.put(x);
            end
        endtask
    endclass

endpackage
