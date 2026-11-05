// Characterization facts: what a component's boundary is known to do,
// declared by the person who knows (a datasheet, a measurement, a design
// target). A component overrides facts():
//
//   virtual function void facts(fw_facts f);
//       f.latency(req, rsp, .min(3), .max(40));
//       f.ii(req, 1);
//       f.area(18500, "um2", "synthesis 2026-10");
//   endfunction
//
// The elaborator reads them into the build's results with provenance
// "declared": the latency report uses them for a block it cannot see inside
// (a wrapper, say), and reports mark them unverified until a measurement
// agrees. Ports are given as handles; a loop covers a port array. In a
// simulation facts() only records.

class fw_fact;
    string      kind;                // latency, ii, capacity, comb_path, registered, area
    fw_endpoint a, b;                // the port(s) it is about (b: the second port)
    longint     n[string];           // fixed, min, max, n, value
    string      s[string];           // unit, source
endclass

class fw_facts;
    fw_fact m_facts[$];

    // Cycles from a value accepted on src to its result offered on dst: fixed,
    // or min and/or max (-1: not given).
    function void latency(fw_endpoint src, fw_endpoint dst, longint fixed = -1,
                          longint min = -1, longint max = -1);
        fw_fact f = add("latency", src, dst);
        if (fixed >= 0) f.n["fixed"] = fixed;
        if (min >= 0) f.n["min"] = min;
        if (max >= 0) f.n["max"] = max;
    endfunction

    // One value accepted on port every n cycles at most.
    function void ii(fw_endpoint port, longint n);
        fw_fact f = add("ii", port, null);
        f.n["n"] = n;
    endfunction

    // Values accepted on src and not yet given on dst, at most.
    function void capacity(fw_endpoint src, fw_endpoint dst, longint n);
        fw_fact f = add("capacity", src, dst);
        f.n["n"] = n;
    endfunction

    // dst's handshake depends on src's in the same cycle.
    function void comb_path(fw_endpoint src, fw_endpoint dst);
        void'(add("comb_path", src, dst));
    endfunction

    // The port's pins are driven or captured by flops.
    function void registered(fw_endpoint port);
        void'(add("registered", port, null));
    endfunction

    // An area estimate: unit um2, cells or luts; where the number comes from.
    function void area(longint value, string unit = "um2", string source = "");
        fw_fact f = add("area", null, null);
        f.n["value"] = value;
        f.s["unit"] = unit;
        if (source != "") f.s["source"] = source;
    endfunction

    protected function fw_fact add(string kind, fw_endpoint a, fw_endpoint b);
        fw_fact f = new;
        f.kind = kind;
        f.a = a;
        f.b = b;
        m_facts.push_back(f);
        return f;
    endfunction
endclass
