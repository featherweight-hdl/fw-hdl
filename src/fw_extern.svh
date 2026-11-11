// Wrapped IP: an existing Verilog module behind an fw-hdl class.
//
// The wrapper is a subclass of the class it realizes, so it has that class's
// ports and parameter object. It implements fw_extern_impl: extern_map()
// says which module it is, which parameter values it gets (computed from the
// class's own parameters if need be), and which module pins each class port
// is. Integration then instantiates the module in place of the class.
//
//   class q_rtl extends q implements fw_extern_impl;
//       `fw_extern_utils("fw_rv_fifo", "fw_rv_fifo.sv")
//       ...
//       virtual function void extern_map(fw_extern_map x);
//           x.param("WIDTH", 8);
//           x.param("DEPTH", m_params.depth > 4 ? 8 : 4);
//           x.clock("clk");
//           x.reset("rst");
//           x.rv(in,  "in",  .data("in_data"),  .valid("in_vld"),  .ready("in_rdy"));
//           x.rv(out, "out", .data("out_data"), .valid("out_vld"), .ready("out_rdy"));
//       endfunction
//   endclass
//
// Every module pin must be accounted for: bound to a port, the clock or the
// reset, tied to a constant, or declared open (an unused output). The
// elaborator checks the map against the module's header, with the parameter
// values applied. In simulation the map is only recorded; the class's body
// (inherited from the class it realizes) is the model.

// One port of the class bound to a group of module pins.
class fw_extern_bind;
    fw_endpoint ep;
    string      kind;           // "rv" | "valid" | "level"
    string      name;           // the endpoint name pin templates use (${ep})
    string      style;          // "fw": ${ep}, ${ep}_valid, ${ep}_ready
                                // "xls": ${ep}, ${ep}_vld, ${ep}_rdy
    string      pins[string];   // role -> pin name, overriding the style
endclass

// A mapping rule, as data: which algorithm names the pins for a struct port's
// fields, and its arguments. The map is strings only (module pin <-> struct
// port field); the tool that resolves it runs the algorithm.
//   "prefix": pin = prefix + (rename[field] or field) + suffix, the middle
//             part upper-cased after upper()
//   x.prefix(in, "in_").rename("valid", "vld").rename("ready", "rdy");
//   x.prefix(s, "S_AXI_").upper();       // S_AXI_AWADDR, ...
//   x.prefix(s1, "s_axi_").slot(1);      // slot 1 of packed pins (see fw_extern_pin)
class fw_pin_rule;
    string m_kind;
    string m_prefix;
    string m_suffix;
    string m_rename[string];
    bit    m_upper;
    int    m_slot = -1;

    function fw_pin_rule rename(string field, string name);
        m_rename[field] = name;
        return this;
    endfunction

    function fw_pin_rule upper();
        m_upper = 1;
        return this;
    endfunction

    function fw_pin_rule slot(int k);
        m_slot = k;
        return this;
    endfunction
endclass

// One entry of a struct-port pin map, in call order: either a module pin bound
// to a field of a struct port, or to a bit slice of one (msb/lsb of -1: the
// whole field); or a rule (rule != null) naming pins for the endpoint's
// fields. Nothing about the protocol is assumed: the struct port's type
// declares its fields.
//
// A slot (>= 0) places the field in one slot of a packed-vector pin shared by
// several ports (e.g. a crossbar's s_axi_awid holds every slave port's ID):
// slot k is bits [(k+1)*w-1 : k*w], w the width of what the entry maps. The
// slots of one pin must be 0..n-1, each mapped once.
//
// Entries resolve in order. A rule maps only the fields still unmapped, so an
// explicit pin before it is an exception the rule leaves alone. An explicit
// pin after a rule replaces what the rule chose for that field.
class fw_extern_pin;
    string      pin;
    fw_endpoint ep;
    string      field;
    int         msb;
    int         lsb;
    int         slot = -1;
    fw_pin_rule rule;
endclass

// What extern_map() records.
class fw_extern_map;
    string         m_param_names[$];
    longint        m_param_int[string];
    string         m_param_str[string];
    string         m_clock;
    string         m_reset;
    bit            m_reset_active_low;
    fw_extern_bind m_binds[$];
    string         m_tie_pins[$];
    longint        m_tie_values[$];
    string         m_open_pins[$];
    fw_extern_pin  m_pins[$];

    // A module parameter, as an integer or a string.
    function void param(string name, longint value);
        m_param_names.push_back(name);
        m_param_int[name] = value;
    endfunction

    function void param_str(string name, string value);
        m_param_names.push_back(name);
        m_param_str[name] = value;
    endfunction

    function void clock(string pin);
        m_clock = pin;
    endfunction

    function void reset(string pin, bit active_low = 0);
        m_reset = pin;
        m_reset_active_low = active_low;
    endfunction

    // A ready/valid port: data, valid and ready pins.
    function void rv(fw_endpoint ep, string name, string style = "fw",
                     string data = "", string valid = "", string ready = "");
        fw_extern_bind b = add(ep, "rv", name, style);
        if (data != "") b.pins["data"] = data;
        if (valid != "") b.pins["valid"] = valid;
        if (ready != "") b.pins["ready"] = ready;
    endfunction

    // A valid-only output: data and valid pins, no ready.
    function void valid(fw_endpoint ep, string name, string style = "fw",
                        string data = "", string valid = "");
        fw_extern_bind b = add(ep, "valid", name, style);
        if (data != "") b.pins["data"] = data;
        if (valid != "") b.pins["valid"] = valid;
    endfunction

    // A level: one pin carrying the value.
    function void level(fw_endpoint ep, string pin);
        fw_extern_bind b = add(ep, "level", pin, "fw");
        b.pins["data"] = pin;
    endfunction

    // A pin that is a field of a struct port, or bits [msb:lsb] of one.
    function void pin(string pin, fw_endpoint ep, string field, int msb = -1, int lsb = -1,
                      int slot = -1);
        fw_extern_pin p = new;
        p.pin = pin;
        p.ep = ep;
        p.field = field;
        p.msb = msb;
        p.lsb = lsb;
        p.slot = slot;
        m_pins.push_back(p);
    endfunction

    // Pins named prefix + field + suffix, for the fields still unmapped.
    function fw_pin_rule prefix(fw_endpoint ep, string pre, string suffix = "");
        fw_extern_pin p = new;
        fw_pin_rule   r = new;
        r.m_kind = "prefix";
        r.m_prefix = pre;
        r.m_suffix = suffix;
        p.ep = ep;
        p.rule = r;
        m_pins.push_back(p);
        return r;
    endfunction

    // An input pin held at a constant.
    function void tie(string pin, longint value);
        m_tie_pins.push_back(pin);
        m_tie_values.push_back(value);
    endfunction

    // An output pin left unconnected on purpose.
    function void open(string pin);
        m_open_pins.push_back(pin);
    endfunction

    protected function fw_extern_bind add(fw_endpoint ep, string kind, string name,
                                          string style);
        fw_extern_bind b = new;
        b.ep = ep;
        b.kind = kind;
        b.name = name;
        b.style = style;
        m_binds.push_back(b);
        return b;
    endfunction
endclass

// Implemented by a wrapper; `fw_extern_utils supplies the first two methods.
interface class fw_extern_impl;
    // The Verilog module's name.
    pure virtual function string extern_module();
    // Its sources: a fileset name (knob design.filesets), or file paths
    // separated by spaces, relative to the file that declares the class.
    pure virtual function string extern_fileset();
    pure virtual function void extern_map(fw_extern_map x);
endclass
