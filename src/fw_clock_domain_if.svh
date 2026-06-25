
// The clock-domain API (TLM-style interface class).
//
// A clock domain is "just another API" carried over the fw_port/fw_export
// deferred-binding wrappers: a component consumes it through its `clock` port
// and resolves the concrete domain, lazily, via get_if(). Every provider in the
// chain -- the root transactor bridge, and any derived domain (divider) -- is an
// fw_export #(fw_clock_domain_if) whose imp implements this API.
//
//   tick(n)       -- advance this domain by n cycles (blocks; run phase only).
//   root_ticks(n) -- how many ROOT-domain clocks span n ticks of THIS domain.
//                    Pure: it walks the provider chain up to the root, folding in
//                    each derived domain's divisor, so it is callable any time
//                    the graph is wired (connect or run). The root domain returns
//                    n (1:1); behind a divide-by-2 then divide-by-3 it returns
//                    6*n. This is the "N clocks in <domain> wrt <root_domain>"
//                    query, resolved by tracing up the tree.
interface class fw_clock_domain_if;
    pure virtual task     tick(int n = 1);
    pure virtual function longint root_ticks(int n = 1);
endclass
