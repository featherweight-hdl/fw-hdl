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

// Whether a step() is executing, for the channels' visibility rule. A step
// runs to completion without yielding, so one flag is enough.
class fw_step_ctx;
    static bit active;

    // Was a value stamped at *t* put during this edge's steps (so a step must
    // not see it yet)?
    static function bit hidden(realtime t);
        return active && t >= $realtime;
    endfunction
endclass
