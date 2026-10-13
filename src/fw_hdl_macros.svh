
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

// ----------------------------------------------------------------------
// Socket/mirror implementation templates (design §3.3) and root binds (§3.4).
//
// ~FW_SOCKET_IMP_BEGIN(I, E, IMP, NAME)~ ... ~FW_SOCKET_IMP_END(NAME)~
//   Opens a nested class ~NAME_imp_t~ that extends ~fw_socket #(I, E)~ AND
//   implements E, so one object is both the socket and its inbound imp. The
//   protocol macro supplies the E methods between BEGIN and END, each
//   redirecting to ~m_imp.NAME_<method>()~. END closes the class and declares
//   the member NAME, so the protocol macro's call needs a trailing semicolon.
//   Construct the member in build(): ~NAME = new(this);~
//
// ~FW_MIRROR_IMP_BEGIN(I, E, IMP, NAME)~ ... ~FW_MIRROR_IMP_END(NAME)~
//   The same for a mirror: extends ~fw_mirror #(I, E)~, implements I.
// ----------------------------------------------------------------------

`define FW_SOCKET_IMP_BEGIN(I, E, IMP, NAME) \
    class NAME``_imp_t extends fw_socket #(I, E) implements E; \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction

`define FW_SOCKET_IMP_END(NAME) \
    endclass \
    NAME``_imp_t NAME

`define FW_MIRROR_IMP_BEGIN(I, E, IMP, NAME) \
    class NAME``_imp_t extends fw_mirror #(I, E) implements I; \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction

`define FW_MIRROR_IMP_END(NAME) \
    endclass \
    NAME``_imp_t NAME

// ----------------------------------------------------------------------
// Root binds for a link endpoint (use inside `fw_root_begin/end).
//
//   `fw_root_bind_socket(socket_ep, if_path, bridge_t)
//        endpoint is a SOCKET; bridge_t is the matching MIRROR over pins.
//   `fw_root_bind_mirror(mirror_ep, if_path, bridge_t)
//        endpoint is a MIRROR; bridge_t is the matching SOCKET over pins.
//
// As with the one-way binds, the suffix names the endpoint's kind, and the
// bridge's constructor is new(name, parent, vif). One line binds both
// directions of the link.
// ----------------------------------------------------------------------
`define fw_root_bind_socket(socket_ep, if_path, bridge_t) \
    begin \
        bridge_t __fw_bridge = new(`"socket_ep`", this, if_path); \
        socket_ep.connect(__fw_bridge); \
    end

`define fw_root_bind_mirror(mirror_ep, if_path, bridge_t) \
    begin \
        bridge_t __fw_bridge = new(`"mirror_ep`", this, if_path); \
        mirror_ep.connect(__fw_bridge); \
    end

`endif /* INCLUDED_FW_HDL_MACROS_SVH */
