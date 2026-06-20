
typedef class spl_component;
typedef class spl_export;

// Note: should be port_base, since component is too heavy
class spl_port #(type T) extends spl_component;
    T       t;

    function new(string name, spl_component parent);
        super.new(name, parent);
    endfunction

    function void connect(spl_export #(T) p);
    endfunction

endclass
