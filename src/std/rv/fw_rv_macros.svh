`ifndef INCLUDED_FW_RV_MACROS_SVH
`define INCLUDED_FW_RV_MACROS_SVH

// Implementation macros for the rv APIs. A component that provides one of the
// APIs declares its export with the macro rather than writing the fw_export
// proxy by hand:
//
// `FW_RV_INITIATOR_IMP(T, IMP, NAME) -- export NAME; send() calls IMP's NAME_send()
// `FW_RV_TARGET_IMP(T, IMP, NAME)    -- export NAME; put() calls IMP's NAME_put()
// `FW_RV_MONITOR_IMP(T, IMP, NAME)   -- export NAME; observe() calls IMP's
//                                       NAME_observe() (a function: may not block)
`define FW_RV_INITIATOR_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(fw_rv_initiator_if #(T)) \
            implements fw_rv_initiator_if #(T); \
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
    class NAME``_imp_t extends fw_export #(fw_rv_target_if #(T)) \
            implements fw_rv_target_if #(T); \
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

`define FW_RV_MONITOR_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(fw_rv_monitor_if #(T)) \
            implements fw_rv_monitor_if #(T); \
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

`endif /* INCLUDED_FW_RV_MACROS_SVH */
