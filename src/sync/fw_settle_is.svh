// The fw_settle_match of class C: c is a C (or a subclass of C).
class fw_settle_is #(type C = int) extends fw_settle_match;
    function new(int unsigned depth);
        super.new(depth);
    endfunction

    virtual function bit test(fw_combinational c);
        C x;
        return $cast(x, c);
    endfunction
endclass
