
// Common base for the deferred-binding wrappers (fw_port, fw_export).
//
// Both a port and an export can ultimately *resolve* to a concrete
// implementation handle of the interface-class type T. get_if() performs that
// resolution -- walking up/down the connection graph until it reaches the imp
// that actually implements the API. This is our lightweight equivalent of
// UVM's resolve_bindings pass, done lazily on first use rather than as a
// separate elaboration phase.
virtual class fw_if_base #(type T);
    pure virtual function T get_if();
endclass
