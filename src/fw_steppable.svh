// A *steppable* says "this body is one clock cycle". It registers with its
// containing component through fw_component::add_steppable(this), usually from
// its constructor, the way an fw_runnable uses add_runnable(). The run phase
// then calls step() once per rising edge of the component's clock domain.
//
// step() is a function, so it cannot wait: what it may call is what the
// language allows in a function. That is try_get on an fw_get_nb_if, get on an
// fw_level_if, put on an fw_valid_put_if and set on an fw_level_set_if. A
// blocking get or put is a task and does not compile there.
//
// What a cycle sees: a value that another step puts or sets during an edge
// is seen from the next edge on, whatever order the steps run in. Values put
// by run() processes before the edge are seen at that edge. Fields keep
// ordinary sequential semantics inside step(); they belong to the component,
// so nothing else observes them mid-cycle.
//
// In XLS a step is one proc activation at II=1: every receive non-blocking,
// every send on a channel without back-pressure.
interface class fw_steppable;
    pure virtual function void step();
endclass

// An *all-or-nothing* step (fw_atomic_step) may also put to a stream output
// that back-pressures, with put_or_stall on an fw_put_step_if. If every such
// put found its output ready at the start of the cycle, the step commits as an
// ordinary step does. Otherwise it has no effect: no field changes, nothing
// is taken from an input, nothing is put or set. The next edge runs it again
// from the same state. The step cannot tell which happened.
//
// In XLS this is one proc activation whose send blocks: a send that is not
// ready stalls the whole activation.
//
// The library channels undo their own effects. A class that implements a port
// API itself (a test's source, say) and changes state in try_get, put or set
// must record an fw_step_undo with fw_step_ctx::record() when
// fw_step_ctx::atomic is set.
interface class fw_atomic_steppable extends fw_steppable;
    // Save the state before a step, and put it back after a stall.
    pure virtual function void step_save();
    pure virtual function void step_restore();
endclass

// How a channel undoes one effect of a step that stalled.
virtual class fw_step_undo;
    pure virtual function void undo();
endclass

// The step that is executing, for the channels: whether one is (the
// visibility rule), whether it can stall, and what to undo if it does. A step
// runs to completion without yielding, so one set of statics is enough.
class fw_step_ctx;
    static bit active;
    static bit atomic;
    static bit stalled;
    static fw_step_undo log[$];

    // Was a value stamped at *t* put during this edge's steps (so a step must
    // not see it yet)?
    static function bit hidden(realtime t);
        return active && t >= $realtime;
    endfunction

    // A channel's effect, to undo if this step stalls. Only an atomic step
    // keeps them.
    static function void record(fw_step_undo u);
        if (atomic)
            log.push_back(u);
    endfunction

    // A stalling put may only run in an atomic step: an ordinary step cannot
    // stall.
    static function void check_atomic(string where);
        if (!(active && atomic))
            $fatal(1, "%s: put_or_stall outside an all-or-nothing step (fw_atomic_step)",
                   where);
    endfunction

    // A stalling put found its output not ready.
    static function void stall();
        stalled = 1'b1;
    endfunction

    static function void begin_step(bit is_atomic);
        active = 1'b1;
        atomic = is_atomic;
        stalled = 1'b0;
        log.delete();
    endfunction

    // End the step: undo its effects, newest first, if it stalled. Returns
    // whether it committed.
    static function bit end_step();
        bit ok = !stalled;
        if (!ok)
            for (int i = log.size() - 1; i >= 0; i--)
                log[i].undo();
        log.delete();
        active = 1'b0;
        atomic = 1'b0;
        stalled = 1'b0;
        return ok;
    endfunction
endclass
