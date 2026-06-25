
// Top: instances the device and the CPU and, in connect(), wires the CPU's bus
// port to the device's register-block export -- the same port->export binding
// used everywhere else in fw-hdl. do_run() forks both runnables; the clock is
// seated by fw_root and inherited by both children.
class reg_bus_top extends fw_component;
    reg_device dev;
    reg_cpu    cpu;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        dev = new("dev", this);
        cpu = new("cpu", this);
    endfunction

    function void connect();
        cpu.regs_p.connect(dev.regs);   // port (consumer) -> export (provider)
    endfunction
endclass
