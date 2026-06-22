
`ifndef INCLUDED_FW_HDL_MACROS_SVH
`define INCLUDED_FW_HDL_MACROS_SVH

// ----------------------------------------------------------------------
// Compact root-bind description (UVM field-registration style).
//
// Wrap a PURE top component `comp_t` as the elaboration root and describe, in
// one block, the transactor bridges that connect its ports/exports to the
// signal-level world. Expands to a `comp_t``_bind` class (extends
// fw_component_root #(comp_t)) whose connect() constructs the bridges, plus the
// fw_root instance that runs it.
//
//   `fw_root_begin(comp_t, inst, clock, reset)
//       `fw_root_bind_port  (port_ep,   if_path, bridge_t)
//       `fw_root_bind_export(export_ep, if_path, bridge_t)
//       ...
//   `fw_root_end
//
// `fw_root_begin stashes comp_t/inst/clock/reset in nested `define`s so the
// closing `fw_root_end takes no arguments. Those temporaries (and the
// FW_ROOT_BIND_ACTIVE guard) are `undef`d by `fw_root_end, so the block is
// self-cleaning -- but it also means a `fw_root_begin/end block CANNOT be
// nested. `fw_root_begin detects an unbalanced (nested) open via the
// FW_ROOT_BIND_ACTIVE guard and forces a compile error by referencing the
// never-defined macro `FW_ROOT_BEGIN_CANNOT_BE_NESTED.
//
// A bridge is NOT a component: by role it IS either an fw_export (provider) or
// an fw_port (consumer). The connection is always port.connect(export). The
// bind reads endpoint-first -- the tree endpoint you are binding (drv.out),
// then its live vif, then the bridge type that adapts it -- and the flavor
// suffix names the ENDPOINT's nature (which also fixes the direction):
//
//   `fw_root_bind_port(port_ep, if_path, bridge_t)
//        endpoint is a PORT (e.g. drv.out); the bridge is its export provider:
//            port_ep.connect(bridge)
//
//   `fw_root_bind_export(export_ep, if_path, bridge_t)
//        endpoint is an EXPORT (e.g. chk.in); the bridge is the consuming port:
//            bridge.connect(export_ep)
//
// Each constructs one `bridge_t` over the live interface handle `if_path` (a
// module-scope vif, e.g. init_xtor.u_if). Every bridge's constructor is
// new(name, parent, vif). Each bind is its own begin/end block, so its local
// `__fw_bridge` declaration is legal and isolated.
// ----------------------------------------------------------------------

`define fw_root_begin(comp_t, inst, clock, reset) \
    `ifdef FW_ROOT_BIND_ACTIVE \
        `FW_ROOT_BEGIN_CANNOT_BE_NESTED \
    `endif \
    `define FW_ROOT_BIND_ACTIVE \
    `define __fw_root_comp_t comp_t \
    `define __fw_root_inst inst \
    `define __fw_root_clock clock \
    `define __fw_root_reset reset \
    class comp_t``_bind extends fw_component_root #(comp_t); \
        function new(string name); \
            super.new(name); \
        endfunction \
        virtual function void connect(); \
            super.connect();

`define fw_root_bind_port(port_ep, if_path, bridge_t) \
    begin \
        bridge_t __fw_bridge = new(`"port_ep`", this, if_path); \
        port_ep.connect(__fw_bridge); \
    end

`define fw_root_bind_export(export_ep, if_path, bridge_t) \
    begin \
        bridge_t __fw_bridge = new(`"export_ep`", this, if_path); \
        __fw_bridge.connect(export_ep); \
    end

`define fw_root_end \
        endfunction \
    endclass \
    \
    fw_root #(.Tbind(`__fw_root_comp_t``_bind)) `__fw_root_inst ( \
        .clock(`__fw_root_clock), \
        .reset(`__fw_root_reset) \
    ); \
    `undef FW_ROOT_BIND_ACTIVE \
    `undef __fw_root_comp_t \
    `undef __fw_root_inst \
    `undef __fw_root_clock \
    `undef __fw_root_reset

`endif /* INCLUDED_FW_HDL_MACROS_SVH */
