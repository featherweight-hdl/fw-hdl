// A get port that can also poll. try_get(t) takes a value if one is waiting
// and returns 1; otherwise it returns 0 at once and leaves t as it was. This
// is XLS's recv_non_blocking (and fw-hdl lowers it to that). t is `inout`:
// an `output` argument would be reset to its default on every call.
//
// Opt in deliberately: a component that polls gives up what blocking get()
// guarantees -- its outputs can depend on timing, so a network that uses it is
// no longer a Kahn process network (see fw_channel.svh). Plain fw_get_if ports
// keep that guarantee.
interface class fw_get_nb_if #(type T) extends fw_get_if #(T);
    pure virtual function bit try_get(inout T t);
endclass
