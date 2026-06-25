// Root component for the clock-domain demo. fw_root seats cd_top's `clock`
// domain on the real clock transactor, so cd_top runs at the root rate. Child
// `a` is left to inherit that root domain (1:1); child `b` is overridden to a
// divide-by-2 domain that its whole subtree then inherits.
class cd_top extends fw_component;
    cd_leaf          a;      // inherits root (1:1)
    cd_sub           b;      // overridden to /2
    fw_clock_domain  div2;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        a    = new("a", this);
        b    = new("b", this);
        div2 = new("div2", this, 2);
    endfunction

    function void connect();
        div2.src.connect(this.clock);  // /2 of root
        b.clock.connect(div2);         // override b's subtree to /2
        // a is left unbound -> auto-inherits root (1:1)
    endfunction
endclass
