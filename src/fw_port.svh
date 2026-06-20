
typedef class fw_component;
typedef class fw_export;

// Note: should be port_base, since component is too heavy
class fw_port #(type T) extends fw_component;
    T       t;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void connect(fw_export #(T) p);
    endfunction

endclass
