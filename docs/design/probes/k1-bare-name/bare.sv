// K1 probe: bare class name inside a parameterized class, used by a macro.
package p;
  class type_h;                         // stands in for fw_protocol_type
    string family;
    function new(string f); family = f; endfunction
  endclass
  class type_of #(type T = int);        // one handle per specialization
    static type_h h;
    static function type_h get(string f);
      if (h == null) h = new(f);
      return h;
    endfunction
  endclass
  `define proto_utils(C) \
    typedef C this_t; \
    static function string family_name(); return `"C`"; endfunction \
    static function type_h get_type(); return type_of #(C)::get(`"C`"); endfunction
  class rv_proto #(int W = 8);
    `proto_utils(rv_proto)
    typedef logic [W-1:0] w_t;
    static function int width_via_this(); this_t::w_t x; return $bits(x); endfunction
  endclass
endpackage

module top;
  import p::*;
  initial begin
    type_h a = rv_proto#(8)::get_type();
    type_h b = rv_proto#(16)::get_type();
    type_h c = rv_proto#(8)::get_type();
    if (a == b) $display("FAIL: same handle for 8 and 16");
    else if (a != c) $display("FAIL: two handles for 8");
    else if (rv_proto#(16)::family_name() != "rv_proto") $display("FAIL: family %s", rv_proto#(16)::family_name());
    else if (rv_proto#(16)::width_via_this() != 16 || rv_proto#(8)::width_via_this() != 8) $display("FAIL: this_t width"); else $display("PASS family=%s w16=%0d", b.family, rv_proto#(16)::width_via_this());
    $finish;
  end
endmodule
