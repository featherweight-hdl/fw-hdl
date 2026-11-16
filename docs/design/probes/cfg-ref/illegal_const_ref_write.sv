// Not legal: writing through a const ref argument.
package p;
  typedef struct packed { int unsigned baud; } cfg_t;
  class consumer;
    function void use_cfg(const ref cfg_t c); c.baud = 1; endfunction
  endclass
endpackage
module top; endmodule
