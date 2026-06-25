`ifndef INCLUDED_FW_STD_MACROS_SVH
`define INCLUDED_FW_STD_MACROS_SVH

// ----------------------------------------------------------------------
// Implementation-template macros for the featherweight standard protocol APIs.
// EVERY std API ships one, and any implementation of that API MUST use the
// matching macro rather than hand-rolling the fw_export proxy. The macro,
// invoked inside a class body, stamps out a nested proxy class `NAME``_imp_t`
// that BOTH `extends fw_export #(<api>)` and `implements <api>` -- so one object
// is at once the export a port connects to and the imp it resolves -- plus a
// member `NAME` of that type. Each API method redirects to `IMP.NAME``_<method>`.
//
// Because the macro ends with a member declaration, the macro call needs a
// trailing `;`.
//
// This file is the one std .svh that carries an include guard: it is `include`d
// by every user package that implements a std API (potentially more than once),
// and re-`define`ing a macro warns. It is found via the std incdir, so a package
// that depends on `fw-hdl.std.sv-src` can `include "fw_std_macros.svh"` directly.
// ----------------------------------------------------------------------

// `FW_PUT_IMP(T, IMP, NAME) -- export NAME providing fw_put_if #(T); its put()
//   redirects to IMP's NAME``_put(). Use this in a component that supplies the
//   put API in the pure class (TLM) layer; the signal-level provider is instead
//   fw_put_xtor_bridge over an fw_put_xtor_if.
`define FW_PUT_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(fw_put_if #(T)) \
            implements fw_put_if #(T); \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction \
        virtual task put(input T t); \
            m_imp.NAME``_put(t); \
        endtask \
    endclass \
    NAME``_imp_t NAME

`endif /* INCLUDED_FW_STD_MACROS_SVH */
