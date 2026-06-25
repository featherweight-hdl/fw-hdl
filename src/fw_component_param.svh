
typedef class fw_component;

// A component whose configuration is carried by a user-defined parameter
// OBJECT (Tp), not by elaboration-time template parameters. Because Tp is a
// real class instance, ordinary procedural code -- factories, validation,
// derived/computed fields -- participates in producing it, while the strong
// type binding (no dynamic_cast, no string-keyed registry) keeps it typesafe:
// `m_params` is exactly Tp, checked at compile time.
class fw_component_param #(type Tp=int) extends fw_component;
    Tp m_params;

    function new(string name, fw_component parent, Tp params);
        super.new(name, parent);
        m_params = params;
    endfunction

endclass

// CONVENTION: a parameterized component exposes its parameter type as
// `<comp>::param_t`. Declare that type as a STANDALONE class and alias it with
// a `typedef` inside the component (below), rather than nesting `class param_t`
// in the component body. Two reasons:
//   1. No forward-declaration dance: a standalone class is fully declared
//      before the component, so it can be named directly in the extends clause.
//   2. Composition with fw_component_root_param: that root reads the param type
//      via `typedef Tb::param_t ...`. If param_t is a NESTED class (declared
//      later in the component body), Verilator's full build (--cc) rejects the
//      root's typedef as use-before-declaration. An alias to a standalone class
//      is already complete, so the root composes cleanly.
class my_component_param_t;
    int v1;
    int v2;

    function new(int v1, int v2);
        this.v1 = v1;
        this.v2 = v2;
    endfunction
endclass

class my_component extends fw_component_param #(my_component_param_t);
    // The ::param_t contract, as an alias (not a nested class).
    typedef my_component_param_t param_t;

    // Factory: this is where "computation participates in parameterization" --
    // defaults, derived values, and validation all live in normal code.
    static function param_t params(int v1=1, int v2=2);
        param_t ret = new(v1, v2);
        return ret;
    endfunction

    function new(string name, fw_component parent, param_t params=my_component::params());
        super.new(name, parent, params);
    endfunction

endclass
