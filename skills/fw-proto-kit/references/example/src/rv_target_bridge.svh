// Target bridge -- the CONSUMER side. Extends fw_port #(rv_target_if) and runs an
// active loop: pop a beat from the transactor-interface FIFO (vif.recv) then push
// it up the connected API (api.put). Connect this port to the component that
// implements rv_target_if. The #17ns idle models consumer backpressure.
class rv_target_bridge #(type T = logic [31:0]) extends fw_port #(rv_target_if #(T));
    virtual rv_target_xtor_if vif;

    function new(string name, fw_component parent,
                 virtual rv_target_xtor_if vif);
        super.new(name, parent);
        this.vif = vif;
    endfunction

    task run();
        rv_target_if #(T) api = get_if();
        forever begin
            automatic T t;
            #17ns;                 // idle: lets the FIFO apply backpressure
            vif.recv(t);
            api.put(t);
        end
    endtask
endclass
