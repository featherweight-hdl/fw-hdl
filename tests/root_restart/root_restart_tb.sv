// fw_root restart: a reset mid-run tears the whole tree down -- every process
// it forked, at any depth -- and reset release builds a fresh one. Also the
// `elaborated` flag a testbench waits on before using the tree.
`include "fw_hdl_macros.svh"

package root_restart_pkg;
    import fw_hdl_pkg::*;

    // Counts ticks in its own run(), and in a grandchild process it forks.
    class ticker extends fw_component implements fw_runnable;
        int n, n_child;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        task run();
            fork
                forever begin tick(); n_child++; end
            join_none
            forever begin tick(); n++; end
        endtask
    endclass

    class top extends fw_component;
        ticker t;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build(); t = new("t", this); endfunction
    endclass
endpackage

module root_restart_tb;
    import fw_hdl_pkg::*;
    import root_restart_pkg::*;

    reg clock = 0, reset = 1;
    always #5 clock = ~clock;

    `fw_root_begin(top, u_root, clock, reset)
    `fw_root_end

    initial begin
        int   errs = 0;
        top_bind first;
        int   n0, c0;

        repeat (2) @(posedge clock);
        reset = 0;
        wait (u_root.root != null && u_root.root.elaborated);
        first = u_root.root;
        repeat (10) @(posedge clock);
        if (first.t.n < 5) begin errs++; $display("FAIL: first tree not running (n=%0d)", first.t.n); end

        // Reset mid-run: the first tree must stop, all of it.
        reset = 1;
        repeat (2) @(posedge clock);
        n0 = first.t.n; c0 = first.t.n_child;
        repeat (5) @(posedge clock);
        if (first.t.n != n0)       begin errs++; $display("FAIL: old run() still running"); end
        if (first.t.n_child != c0) begin errs++; $display("FAIL: old forked process still running"); end
        if (u_root.root != null)   begin errs++; $display("FAIL: root not cleared in reset"); end

        // Release: a NEW tree, elaborated and running from zero.
        reset = 0;
        wait (u_root.root != null && u_root.root.elaborated);
        if (u_root.root == first) begin errs++; $display("FAIL: same root object after restart"); end
        repeat (10) @(posedge clock);
        if (u_root.root.t.n < 5)  begin errs++; $display("FAIL: new tree not running"); end
        if (first.t.n != n0)      begin errs++; $display("FAIL: old tree woke up"); end

        if (errs == 0) $display("PASS: root_restart_tb");
        else           $fatal(1, "FAIL: root_restart_tb (%0d)", errs);
        $finish;
    end
endmodule
