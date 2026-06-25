
// Parameterized-component demonstrator.
//
// cfg_comp is a component whose configuration is a typed OBJECT (cfg_comp::
// param_t), not template parameters. The factory cfg_comp::params() and the
// build() body are ordinary procedural code that COMPUTES with that config --
// here, deriving total_bits during elaboration -- which is the whole point of
// the scheme: algorithms participate in parameterization while the binding
// stays compile-time typesafe (m_params is exactly param_t).
package root_param_pkg;
    import fw_hdl_pkg::*;

    // param type is a STANDALONE class (see fw_component_param.svh for why this
    // is preferred over a nested class -- it lets fw_component_root_param read
    // the type under Verilator's full build).
    class cfg_comp_param_t;
        int count;
        int width;
        function new(int count, int width);
            this.count = count;
            this.width = width;
        endfunction
    endclass

    class cfg_comp extends fw_component_param #(cfg_comp_param_t);
        // The ::param_t contract, as an alias.
        typedef cfg_comp_param_t param_t;

        // Computed during elaboration from the typed params.
        int total_bits;

        // Factory: defaults + (room for) validation/derivation live in code.
        static function param_t params(int count=1, int width=8);
            param_t ret = new(count, width);
            return ret;
        endfunction

        function new(string name, fw_component parent, param_t params);
            super.new(name, parent, params);
        endfunction

        virtual function void build();
            total_bits = m_params.count * m_params.width;
            $display("[cfg_comp %s] count=%0d width=%0d -> total_bits=%0d",
                     m_name, m_params.count, m_params.width, total_bits);
        endfunction

    endclass

endpackage
