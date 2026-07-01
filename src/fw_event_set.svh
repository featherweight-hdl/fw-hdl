
typedef class fw_awaitable_if;   // forward: add() wires a source's production in

// fw_event_set -- the MONITOR side: a list of event sources you wait on.
//
// Build it with add() (pull-style look-and-feel), then wait_any() blocks until any
// member's "event occurred". Internally this is a PUSH: add() wires each source to
// signal() this set when it fires, so wait_any() is a single @event -- O(1), with
// no per-wait fork. That produce/monitor split is also what lowers to synthesizable
// RTL: each source's "fired" pulse drives this set's event (the OR of its members),
// and a wait site is a process sensitive to it.
//
// We do not report which source fired; the consumer re-evaluates its own state on
// wake. (fw_reg_set is the register-specific primitive that tracks which moved.)
class fw_event_set;
    protected event m_any;

    // Pull-style API: add a source to wait on. Wires the source (produce_to) to
    // signal this set when it fires.
    function void add(fw_awaitable_if a);  a.produce_to(this);  endfunction

    // Called by a member source when its event occurs (the push).
    function void notify();  -> m_any;  endfunction

    // The wait/monitor site: block until any member's event occurs.
    task wait_any();  @(m_any);  endtask
endclass
