// Top: instances producer + consumer and, in connect(), wires the producer's
// port to the consumer's export. do_build() recurses into the children, and
// do_run() forks the producer (the only runnable), so there is no manual
// build()/run() plumbing here.
class pc_top extends fw_component;
    producer prod;
    consumer cons;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        prod = new("prod", this);
        cons = new("cons", this);
    endfunction

    function void connect();
        prod.out.connect(cons.in);   // port (consumer) -> export (provider)
    endfunction
endclass
