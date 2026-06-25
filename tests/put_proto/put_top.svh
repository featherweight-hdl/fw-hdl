// Top: a pure component holding the producer and its put port. It knows nothing
// about the signal-level transactor -- the testbench's fw_root block binds
// prod.out to the put bridge over a live fw_put_xtor_if.
class put_top extends fw_component;
    producer prod;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        prod = new("prod", this);
    endfunction
endclass
