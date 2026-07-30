
// fw_awaitable_if -- the PRODUCER side: an event source. Implementers (a register,
// a HW-handshake port, a timer, ...) PRODUCE an "event occurred" into the monitors
// they have been added to, by calling monitor.notify(this) when they fire.
// fw_event_set.add() performs the wiring (produce_to); a source may feed several
// monitors.
//
// This is a push: the source signals the monitor, so the wait is O(1) (no per-wait
// fork) and it lowers to synthesizable RTL -- the source drives a "fired" pulse,
// the monitor ORs the pulses of its members, and a wait site is a process sensitive
// to that OR. The MONITOR does not tell its consumer which source fired; the
// consumer re-evaluates its own state on wake. (fw_reg_set is the register-specific
// primitive that tracks which.) The identity passed to notify() is for the
// OBSERVER -- see below.
interface class fw_awaitable_if;
    // Wire this source to signal `s` (s.notify(this)) whenever it fires.
    pure virtual function void produce_to(fw_event_set s);

    // This source's catalog site, or FW_DBG_NO_SITE if it has none.
    //
    // Present so a wait can be *named*. "Blocked on 5 things" is not a
    // diagnosis; "blocked on {ch0.csr, ch1.csr, hs0.req}" is, and the difference
    // is entirely whether a source can say who it is. Nothing about the model's
    // behavior depends on it, and under `FW_TRACE_OFF` every implementation
    // returns 0 -- so this is one unused int-returning function, not a tax.
    pure virtual function int unsigned dbg_site();
endclass
