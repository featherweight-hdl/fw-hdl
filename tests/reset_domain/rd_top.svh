// The reset-domain tree:
//   a    : inherits the root reset domain (fw_root's, or none for a bare root)
//   b    : overridden to `sig`, a bench-local signal domain that starts in reset
//   s    : a stepper in `sig`
class rd_top extends fw_component;
    rd_leaf      a;
    rd_leaf      b;
    rd_stepper   s;
    rd_sig_reset sig;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        a   = new("a", this);
        b   = new("b", this);
        s   = new("s", this);
        sig = new("sig", this, 1'b1);
    endfunction

    function void connect();
        sig.clk.connect(this.clock);
        b.reset.connect(sig);
        s.reset.connect(sig);
    endfunction
endclass
