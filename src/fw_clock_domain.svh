
typedef class fw_component;

// A *derived* clock domain: a domain produced by dividing a source domain.
//
// It is at once the EXPORT a child's clock port connects to and the IMP that
// child resolves (the same one-object-is-both-export-and-imp idiom the protocol
// macros use). Its own source is reached through `src`, an inner port wired -- in
// the owning component's connect() -- up to that component's clock domain:
//
//     div = new("div2", this, 2);    // build(): this domain = parent / 2
//     ...
//     div.src.connect(this.clock);   // connect(): pull from my (inherited) domain
//     child.clock.connect(div);      // hand the divided domain down a subtree
//
// Because src is a port, resolution is deferred: tick()/root_ticks() walk
// `src` -> ... -> root at the moment they are called, with the divisor folded in
// at this level. A divide-by-1 domain is a no-op pass-through (useful as a named
// boundary).
class fw_clock_domain extends fw_export #(fw_clock_domain_if)
        implements fw_clock_domain_if;
    // The source domain (up the DOMAIN tree, distinct from the component tree).
    // Parentless: it is wired explicitly, never walked for build/connect.
    fw_port #(fw_clock_domain_if) src;
    local int m_div;   // this domain advances once per m_div source cycles

    function new(string name, fw_component parent, int div = 1);
        super.new(name, parent, this);   // register `this` as the export's imp
        src   = new("src", null);
        m_div = div;
    endfunction

    // Advancing this domain by n cycles advances the source by n*div cycles.
    virtual task tick(int n = 1);
        src.get_if().tick(n * m_div);
    endtask

    // Fold this level's divisor into the count and recurse toward the root.
    virtual function longint root_ticks(int n = 1);
        return src.get_if().root_ticks(n * m_div);
    endfunction
endclass
