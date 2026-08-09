
typedef interface class fw_type_if;

class fw_type #(type T=int) implements fw_type_if;
    typedef fw_type #(T) this_t;
    static this_t       type_inst;

    static function this_t get();
        if (type_inst == null) begin
        end
        return type_inst;
    endfunction

endclass
