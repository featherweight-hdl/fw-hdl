
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

class fw_component_type #(type T=fw_component) implements fw_type_if;

    static function T create(string name, fw_component parent);
      // Use the override information in 'parent' to determine the specific type to create
      // Return cast to 'T'
    endfunction

endclass

class fw_component_param_type #(type Tcomp=fw_component, type Tparam=fw_params);
endclass
