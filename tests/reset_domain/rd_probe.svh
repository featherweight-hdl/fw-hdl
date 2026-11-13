// Calls a reset domain's waits from its own run() and records when they
// return, so the bench can check they return at the first tick of the domain's
// clock at which the condition holds. Its own reset is left as inherited; it
// only watches `dom`.
class rd_probe extends fw_component implements fw_runnable;
    fw_port #(fw_reset_domain_if) dom;
    longint t_assert = -1, t_deassert = -1;

    function new(string name, fw_component parent);
        super.new(name, parent);
        dom = new("dom", this);
        add_runnable(this);
    endfunction

    virtual task run();
        forever begin
            dom.t.wait_assert();
            t_assert = $time;
            dom.t.wait_deassert();
            t_deassert = $time;
        end
    endtask
endclass
