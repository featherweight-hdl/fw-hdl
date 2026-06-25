`ifndef INCLUDED_RV_PROTO_MACROS_SVH
`define INCLUDED_RV_PROTO_MACROS_SVH

// ----------------------------------------------------------------------
// Implementation-template macros provided by the rv APIs. EVERY API ships one,
// and any implementation of that API MUST use it to define the implementation
// redirect rather than hand-rolling the fw_export proxy.
//
// `FW_RV_INITIATOR_IMP(T, IMP, NAME) -- export NAME whose send() redirects to
//   IMP's NAME_send().
// `FW_RV_TARGET_IMP(T, IMP, NAME)    -- export NAME whose put() redirects to
//   IMP's NAME_put().
// ----------------------------------------------------------------------
`define FW_RV_INITIATOR_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(rv_initiator_if #(T)) \
            implements rv_initiator_if #(T); \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction \
        virtual task send(input T t); \
            m_imp.NAME``_send(t); \
        endtask \
    endclass \
    NAME``_imp_t NAME

`define FW_RV_TARGET_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(rv_target_if #(T)) \
            implements rv_target_if #(T); \
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

// `FW_RV_MONITOR_IMP(T, IMP, NAME) -- export NAME whose observe() redirects to
//   IMP's NAME_observe(). NOTE: observe() is a FUNCTION (non-blocking) -- monitor
//   APIs may not block.
`define FW_RV_MONITOR_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(rv_monitor_if #(T)) \
            implements rv_monitor_if #(T); \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction \
        virtual function void observe(input T t); \
            m_imp.NAME``_observe(t); \
        endfunction \
    endclass \
    NAME``_imp_t NAME

`endif /* INCLUDED_RV_PROTO_MACROS_SVH */
