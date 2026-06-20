
typedef interface class fw_put_if;
typedef class fw_export;

class fw_put_xtor_impl #(type T) implements fw_put_if #(T);
    virtual interface fw_put_xtor_if #(T) vif;

    function new(virtual interface fw_put_xtor_if #(T) vif);
        this.vif = vif;
    endfunction

    virtual task put(T t);
        vif.put(t);
    endtask

endclass
