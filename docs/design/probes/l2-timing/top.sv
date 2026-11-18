// Layer-2 timing probe: class tasks under verilator --timing.
package l2p_pkg;
  class Comp;
    string name;
    event  ev;          // triggered from an always @(posedge clk)
    int    ev_cnt;
    int    comb_out;    // written by eval() from always_comb
    int    in_val;      // class field input (variant B)

    function new(string name); this.name = name; endfunction

    // (1) run(): wait on event, then on #d
    task run();
      repeat (3) begin
        @(ev);
        $display("[%0t] %s.run: ev seen cnt=%0d", $time, name, ev_cnt);
        #3;
        $display("[%0t] %s.run: after #3", $time, name);
      end
    endtask

    // (2) worker forked with join_none
    task worker(int id, int d);
      #d;
      $display("[%0t] %s.worker%0d: done after #%0d", $time, name, id, d);
    endtask

    // (3a) combinational eval from an argument
    function void eval(int a);
      comb_out = a * 2;
    endfunction
    // (3b) combinational eval from a class field only
    function void eval_field();
      comb_out = in_val * 2;
    endfunction
  endclass
endpackage

module top;
  import l2p_pkg::*;
  bit clk = 0;
  int cyc = 0;
  int a = 0;
  int y_a, q_a;          // variant A: arg-driven
  int y_b, q_b;          // variant B: field-driven
  Comp c  = new("c");
  Comp cb = new("cb");

  always #5 clk = ~clk;

  always @(posedge clk) begin
    cyc <= cyc + 1;
    a   <= a + 1;
    c.ev_cnt++;
    -> c.ev;
  end

  // variant A: arg carries the dependency
  always_comb begin
    c.eval(a);
    y_a = c.comb_out;
  end
  always_ff @(posedge clk) q_a <= c.comb_out;

  // variant B: only a class field carries the dependency
  always @(posedge clk) cb.in_val <= a + 100;
  always_comb begin
    cb.eval_field();
    y_b = cb.comb_out;
  end
  always_ff @(posedge clk) q_b <= cb.comb_out;

  always @(negedge clk)
    $display("[%0t] cyc=%0d a=%0d y_a=%0d q_a=%0d cb.in_val=%0d y_b=%0d q_b=%0d",
             $time, cyc, a, y_a, q_a, cb.in_val, y_b, q_b);

  initial begin
    fork
      c.run();
      c.worker(1, 7);
      c.worker(2, 12);
      c.worker(3, 1);
    join_none
    $display("[%0t] initial: forked", $time);
    #60;
    $display("[%0t] done", $time);
    $finish;
  end
endmodule
