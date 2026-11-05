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
