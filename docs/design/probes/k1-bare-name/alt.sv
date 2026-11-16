package p;
  class type_h; string family; function new(string f); family = f; endfunction endclass
  class type_of #(type T = int);
    static type_h h;
    static function type_h get(string f); if (h == null) h = new(f); return h; endfunction
  endclass
  // Family name: the stringified argument up to '#', trimmed.
  function automatic string family_of(string s);
    foreach (s[i]) if (s[i] == "#" || s[i] == " ") return s.substr(0, i-1);
    return s;
  endfunction
  // Variant A: the macro takes the specialized form.
  `define proto_utils_a(T) \
    typedef T this_t; \
    static function string family_name(); return family_of(`"T`"); endfunction \
    static function type_h get_type(); return type_of #(T)::get(family_name()); endfunction
  class rv_a #(int W = 8);
    `proto_utils_a(rv_a #(W))
    typedef logic [W-1:0] w_t;
  endclass
  // Variant B: bare name, but only through C:: scope resolution.
  class rv_b #(int W = 8);
    localparam int SCOPED_W = rv_b::W;
  endclass
endpackage

module top;
  import p::*;
  p::rv_a#(16)::this_t::w_t v16;
  p::rv_a#(8)::this_t::w_t v8;
  localparam int BW16 = p::rv_b#(16)::SCOPED_W;
  initial begin
    automatic type_h a = rv_a#(8)::get_type();
    automatic type_h b = rv_a#(16)::get_type();
    automatic type_h c = rv_a#(8)::get_type();
    $display("A: distinct=%0d same8=%0d family=%s bits16=%0d", a != b, a == c, b.family, $bits(v16));
    $display("B: rv_b#(16) scoped W=%0d", BW16);
    $finish;
  end
endmodule
