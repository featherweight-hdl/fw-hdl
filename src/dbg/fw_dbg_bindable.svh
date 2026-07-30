
// A *bindable endpoint*: the non-parameterized face of an fw_port / fw_export.
//
// Why this exists at all: `fw_port #(T)` and `fw_export #(T)` are parameterized,
// so a tree walk cannot collect them through any common handle type -- and
// `$cast`ing an `fw_elaboratable` handle down to `fw_port #(T)` is doubly
// impossible (you would have to know T, and Verilator 5.049 silently fails to
// downcast out of an interface-class handle when the target extends a
// parameterized base). So endpoints register themselves through THIS interface,
// which is unparameterized and answers exactly the questions the bind map asks.
//
// Everything here is elaboration-time and string-valued. That is deliberate and
// it is the exception, not a precedent: the bind map is a STATIC artifact
// produced once, so it is the right place for names -- which is precisely why
// the per-bind and per-resolve *event* sites were dropped (design §14.13, "emit
// only the irrecoverable": a stream of resolve events carries nothing the map
// does not carry better).
interface class fw_dbg_bindable;
    // Local (leaf) name of the endpoint, e.g. "clock", "out".
    pure virtual function string bind_name();
    // "port" (a consumer) or "export" (a provider).
    pure virtual function string bind_role();
    // Has anything been wired to it?
    pure virtual function bit bind_connected();
    // Name of what it was wired to: a peer endpoint's name, "<imp>" for an
    // export holding a terminal implementation, or "" when unconnected.
    pure virtual function string bind_provider();
    // Did resolution actually yield an implementation handle? A port can be
    // connected and still resolve to null if its provider chain is broken.
    pure virtual function bit bind_resolved();
endclass
