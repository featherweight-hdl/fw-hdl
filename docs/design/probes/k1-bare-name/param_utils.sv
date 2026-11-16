// K1 decision 18: fw_protocol_utils(C) for unparameterized classes;
// fw_protocol_param_utils(C) with a user typedef this_t for parameterized
// ones. The bare name is only stringified, never used as a type.
package p;
  class type_h; string family; function new(string f); family = f; endfunction endclass
  class type_of #(type T = int);
    static type_h h;
    static function type_h get(string f); if (h == null) h = new(f); return h; endfunction
  endclass
  `define protocol_utils(C) \
    static function string family_name(); return `"C`"; endfunction \
    static function type_h get_type(); return type_of #(C)::get(family_name()); endfunction
  `define protocol_param_utils(C) \
    static function string family_name(); return `"C`"; endfunction \
    static function type_h get_type(); return type_of #(this_t)::get(family_name()); endfunction
  class plain_proto;
    `protocol_utils(plain_proto)
  endclass
  class rv_proto #(int W = 8);
    typedef rv_proto #(W) this_t;
    `protocol_param_utils(rv_proto)
    typedef logic [W-1:0] w_t;
    static function int width(); this_t::w_t x; return $bits(x); endfunction
  endclass
endpackage
module top;
  import p::*;
  initial begin
    automatic type_h a = rv_proto#(8)::get_type(), b = rv_proto#(16)::get_type(),
                     c = rv_proto#(8)::get_type(), d = plain_proto::get_type();
    if (a != b && a == c && b.family == "rv_proto" && d.family == "plain_proto"
        && rv_proto#(16)::width() == 16 && rv_proto#(8)::width() == 8)
      $display("PASS");
    else
      $display("FAIL %0d %0d %s %s %0d", a != b, a == c, b.family, d.family, rv_proto#(16)::width());
    $finish;
  end
endmodule
