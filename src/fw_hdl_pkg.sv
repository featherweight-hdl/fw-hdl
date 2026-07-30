
package fw_hdl_pkg;
    // Observable operations & events (docs/fw_hdl_observable_events.md). The
    // static half -- vocabulary, site descriptors, the catalog, and the flat
    // transport record -- comes first: it depends on nothing, and the macros must
    // be defined before any class below can carry an instrumentation site.
    `include "dbg/fw_dbg_macros.svh"
    `include "dbg/fw_dbg_types.svh"
    `include "dbg/fw_dbg_site.svh"
    `include "dbg/fw_dbg_catalog.svh"
    `include "dbg/fw_dbg_rec.svh"
    // The listener API and its context objects. Ahead of fw_port/fw_export
    // because fw_component holds an fw_port #(fw_dbg_listener_if); the DOMAIN
    // (which is an fw_export and needs a component parent) comes after them.
    `include "dbg/fw_dbg_bindable.svh"
    `include "dbg/fw_dbg_listener_if.svh"
    `include "dbg/fw_dbg_contextual.svh"
    `include "dbg/fw_dbg_ctx.svh"
    `include "dbg/fw_dbg_listener.svh"
    // The LIVE view (op stack + blocked-on set). Depends on fw_dbg_thread, and
    // fw_event_set/fw_component below both feed it.
    `include "dbg/fw_dbg_track.svh"

    `include "fw_elaboratable.svh"
    `include "fw_runnable.svh"
    // Deferred-binding wrappers and the clock-domain API must precede
    // fw_component, which now holds an fw_port #(fw_clock_domain_if) `clock`.
    `include "fw_if_base.svh"
    `include "fw_clock_domain_if.svh"
    `include "fw_export.svh"
    `include "fw_port.svh"
    `include "fw_clock_domain.svh"
    `include "fw_clock_xtor_bridge.svh"
    `include "fw_clock_period_xtor_bridge.svh"
    `include "fw_quantum_keeper.svh"     // TLM-style temporal decoupling (loosely-timed speedup)
    `include "fw_component.svh"
    `include "fw_component_param.svh"
    `include "fw_component_root.svh"
    `include "fw_component_root_param.svh"

    // The debug tree: a domain is an fw_export carrying fw_dbg_listener_if, so
    // it lands here, after the deferred-binding wrappers and fw_component.
    `include "dbg/fw_dbg_domain.svh"
    `include "dbg/fw_dbg_sink_text.svh"
    // Policy on top of the mechanism: plusarg-driven wiring, so a bench can be
    // instrumented without being edited. Needs the domain and the sink.
    `include "dbg/fw_dbg_console.svh"

    // Register model -- a core modeling aspect, so it lives in the kernel
    // alongside the component/port/export/clock-domain machinery (it is "just
    // another API" carried over fw_port/fw_export, like fw_clock_domain_if). The
    // interface classes come first; fw_reg_base forward-declares fw_reg_set (the
    // register and its watch-set are mutually referential).
    `include "fw_event_set.svh"     // monitor: a named set of sources you wait_any() on
    `include "fw_awaitable_if.svh"  // producer: an event source, wired in via produce_to
    `include "fw_reg_rd_if.svh"     // hardware read provider hook
    `include "fw_reg_wr_if.svh"     // hardware write observer hook
    `include "fw_reg_val_if.svh"    // untyped (value-level) register API
    `include "fw_reg_block_if.svh"  // addressable group API (bus-facing)
    `include "fw_reg_base.svh"      // register state machine (untyped)
    `include "fw_reg.svh"           // typed register over a packed struct
    `include "fw_reg_set.svh"       // register watch-set (fw_event_set + which)
    `include "fw_reg_block.svh"     // register group: offsets, decode

endpackage
