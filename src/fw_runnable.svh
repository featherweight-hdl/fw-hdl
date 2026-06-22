
// A *runnable* opts in to having a process forked for it during the run phase.
// fw_component does NOT provide run() by default, so a purely structural or
// passive component (and most ports/exports) spawn no process.
//
// Opting in is EXPLICIT: an object that implements fw_runnable registers itself
// with its containing component via fw_component::add_runnable(this) -- usually
// from its own constructor. That places it in the component's m_run list, and
// do_run() forks its run(). There is no automatic detection.
interface class fw_runnable;
    pure virtual task run();
endclass
