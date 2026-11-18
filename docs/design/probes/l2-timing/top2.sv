// Layer-2 timing probe, part 2: wait() on class fields, virtual-interface clocking.
interface clk_if(input bit clk);
  int data;
endinterface

package l2p2_pkg;
  class Comp2;
    virtual clk_if vif;
    int flag;
    task waiter();
      wait (flag == 3);
      $display("[%0t] waiter: flag==3 seen", $time);
    endtask
    task clocked();
      repeat (2) begin
        @(posedge vif.clk);
        $display("[%0t] clocked: posedge vif.clk data=%0d", $time, vif.data);
      end
      vif.data = 77;
    endtask
    task delay0();
      #0;
      $display("[%0t] delay0: after #0", $time);
    endtask
  endclass
endpackage

module top2;
  import l2p2_pkg::*;
  bit clk = 0;
  always #5 clk = ~clk;
  clk_if u_if(clk);
  Comp2 c = new;
  always @(posedge clk) begin
    c.flag <= c.flag + 1;
    u_if.data <= u_if.data + 10;
  end
  initial begin
    c.vif = u_if;
    fork
      c.waiter();
      c.clocked();
      c.delay0();
    join_none
    #40;
    $display("[%0t] flag=%0d data=%0d", $time, c.flag, u_if.data);
    $finish;
  end
endmodule
