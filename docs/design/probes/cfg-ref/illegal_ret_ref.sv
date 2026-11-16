// Not legal: a function cannot return by reference.
package p;
  typedef struct packed { int unsigned baud; } cfg_t;
  class publisher;
    cfg_t m_cfg;
    function ref cfg_t get(); return m_cfg; endfunction
  endclass
endpackage
module top; endmodule
