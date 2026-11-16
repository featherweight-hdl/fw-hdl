// Legal forms: struct returned by value; const ref and ref arguments.
package p;
  typedef struct packed { int unsigned baud; bit [3:0] data_bits; } cfg_t;
  typedef class consumer;
  class publisher;
    cfg_t m_cfg = '{baud: 115200, data_bits: 8};
    function cfg_t get();                    // by value: a snapshot copy
      return m_cfg;
    endfunction
    function void read(const ref cfg_t c);   // hand out a read-only view
      $display("read: baud=%0d", c.baud);
    endfunction
    function void visit(consumer c);         // publisher passes its own struct
      c.use_cfg(m_cfg);
    endfunction
  endclass
  class consumer;
    function void use_cfg(const ref cfg_t c);
      $display("use_cfg: baud=%0d", c.baud);
    endfunction
  endclass
endpackage
module top;
  import p::*;
  initial begin
    automatic publisher pub = new;
    automatic consumer  con = new;
    automatic cfg_t s = pub.get();
    s.baud = 9600;                            // changes the copy only
    $display("copy=%0d publisher=%0d", s.baud, pub.get().baud);
    pub.read(pub.m_cfg);
    pub.visit(con);
    $finish;
  end
endmodule
