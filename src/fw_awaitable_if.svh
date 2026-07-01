
// fw_awaitable_if -- the PRODUCER side: an event source. Implementers (a register,
// a HW-handshake port, a timer, ...) PRODUCE an "event occurred" into the monitors
// they have been added to, by calling monitor.notify() when they fire.
// fw_event_set.add() performs the wiring (produce_to); a source may feed several
// monitors.
//
// This is a push: the source signals the monitor, so the wait is O(1) (no per-wait
// fork) and it lowers to synthesizable RTL -- the source drives a "fired" pulse,
// the monitor ORs the pulses of its members, and a wait site is a process sensitive
// to that OR. We do not report WHICH source fired; the consumer re-evaluates its own
// state on wake. (fw_reg_set is the register-specific primitive that tracks which.)
interface class fw_awaitable_if;
    // Wire this source to signal `s` (s.notify()) whenever it fires.
    pure virtual function void produce_to(fw_event_set s);
endclass
