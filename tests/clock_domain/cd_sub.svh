// Runs on the divide-by-2 domain cd_top hands it. Its child `c` inherits that
// /2 domain; `e` gets a further divide-by-3 derived from it -- so `e` is at /6
// of the root. Demonstrates deriving a domain from one's own (inherited) domain.
class cd_sub extends fw_component;
    cd_leaf          c;      // inherits this component's /2 domain
    cd_leaf          e;      // /3 of /2 == /6 of root
    fw_clock_domain  div3;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        c    = new("c", this);
        e    = new("e", this);
        div3 = new("div3", this, 3);
    endfunction

    function void connect();
        div3.src.connect(this.clock);  // pull from my (inherited /2) domain
        e.clock.connect(div3);         // hand /6 down to e
        // c is left unbound -> auto-inherits my /2 domain
    endfunction
endclass
