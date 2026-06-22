
// An *elaboratable* participates in the build/connect lifecycle and is walked
// by its containing component during elaboration.
//
// Elaboration (build/connect) is SEPARATE from execution (run). Being
// elaboratable says nothing about whether the object runs a process -- that is
// opt-in via fw_runnable. fw_component, fw_port and fw_export are all
// elaboratable; they self-register into their containing component, which keeps
// them in m_elab and drives each phase polymorphically through this interface.
//
// See fw_runnable for the execution half: an elaboratable that ALSO implements
// fw_runnable is additionally placed in the component's m_run list and has its
// run() forked during do_run().
interface class fw_elaboratable;
    pure virtual function void do_build();
    pure virtual function void do_connect();
endclass
