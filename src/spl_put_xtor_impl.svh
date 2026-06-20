
typedef interface class spl_put_if;
typedef class spl_export;

class spl_put_xtor_impl #(type T) implements spl_put_if #(T);
    virtual interface spl_put_xtor_if #(T) vif;

    function new(virtual interface spl_put_xtor_if #(T) vif);
        this.vif = vif;
    endfunction

    virtual task put(T t);
        vif.put(t);
    endtask

endclass
