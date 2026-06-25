// Provides the std put API via the implementation-template macro: `FW_PUT_IMP
// stamps the export/imp proxy `in` and the convention is that put() lands in
// in_put() below, which records each received beat.
class consumer extends fw_component;
    data_t received[$];

    `FW_PUT_IMP(data_t, consumer, in);

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        in = new(this);
    endfunction

    virtual task in_put(input data_t t);
        $display("[consumer] recv 0x%08h", t);
        received.push_back(t);
    endtask
endclass
