
// Something that is not a component but still emits: it needs a debug context
// handed to it, and it cannot get one from a `dbg` port of its own.
//
// The register model is the motivating case. An `fw_reg_block #(W)` is owned by a
// component but is not one, and it is parameterized -- so a component cannot
// collect its register files through any common handle type. This interface is
// that handle: a block created as `new("rf", this)` registers itself, and
// `fw_component::do_build` hands it the resolved context. Zero per-design wiring,
// which is the whole point of instrumenting the library rather than the model.
//
// Same shape and same reason as fw_dbg_bindable: an unparameterized face, so a
// tree walk never has to know `W`.
interface class fw_dbg_contextual;
    pure virtual function void set_dbg_context(fw_dbg_listener_if l);
endclass
