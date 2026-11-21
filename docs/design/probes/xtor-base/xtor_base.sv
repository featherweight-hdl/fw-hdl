// Probe: role base classes for transactors (fw_xtor_initiator/target/
// monitor #(type B)), parameterized on the bundle type B. The role is a
// static fact of the class, the protocol comes from B's
// fw_bundle_protocol, and registration needs only the class name. Run
// against rt-sv (fw_hdl_pkg) and std (fw_hdl_std_pkg) with Verilator 5.055;
// see run.sh. Expected output: expected.txt.
`include "fw_hdl_macros.svh"

package xb_pkg;
    import fw_hdl_pkg::*;
    import fw_hdl_std_pkg::*;

    // ---- the proposed base classes ----

    virtual class fw_xtor_initiator #(type B = fw_bundle_base) extends fw_component;
        fw_bundle #(B) pins;
        static function fw_proto_role_e role();
            return FW_ROLE_INITIATOR;
        endfunction
        static function fw_protocol_type protocol();
            return B::__fw_bundle_protocol();
        endfunction
        virtual function void build();
            pins = fw_bundle #(B)::create("pins", this);
        endfunction
    endclass

    virtual class fw_xtor_target #(type B = fw_bundle_base) extends fw_component;
        fw_mirror #(B) pins;
        static function fw_proto_role_e role();
            return FW_ROLE_TARGET;
        endfunction
        static function fw_protocol_type protocol();
            return B::__fw_bundle_protocol();
        endfunction
        virtual function void build();
            pins = fw_mirror #(B)::create("pins", this);
        endfunction
    endclass

    virtual class fw_xtor_monitor #(type B = fw_bundle_base) extends fw_component;
        fw_monitor #(B) pins;
        static function fw_proto_role_e role();
            return FW_ROLE_MONITOR;
        endfunction
        static function fw_protocol_type protocol();
            return B::__fw_bundle_protocol();
        endfunction
        virtual function void build();
            pins = fw_monitor #(B)::create("pins", this);
        endfunction
    endclass

    // The one-argument registration: protocol and role come from the base.
    `define xb_xtor_utils(C) \
        `fw_component_utils(C) \
        static function fw_protocol_type __fw_xtor_protocol(); \
            return protocol(); \
        endfunction \
        static bit __fw_conv_reg = fw_hdl_pkg::__fw_rt_proto::add_conv($typename(C), \
            protocol(), protocol(), role(), 1, fw_ctor_of #(fw_component, C)::get());

    `define xb_xtor_param_utils(C) \
        `xb_xtor_utils(this_t)

    // ---- a two-channel protocol, as the guide's sbus ----

    typedef struct packed { bit [7:0] addr; bit we; } q_req_t;
    typedef struct packed { bit [7:0] data; } q_rsp_t;

    class q_proto extends fw_protocol;
        `fw_protocol_utils(q_proto)
    endclass

    virtual class q_bundle extends fw_bundle_base;
        `fw_bundle_protocol(q_proto)
        fw_bundle #(fw_rv_if #(q_req_t)) req;
        fw_mirror #(fw_rv_if #(q_rsp_t)) rsp;
        virtual function void build();
            req = fw_bundle #(fw_rv_if #(q_req_t))::create("req", this);
            rsp = fw_mirror #(fw_rv_if #(q_rsp_t))::create("rsp", this);
        endfunction
    endclass

    // non-parameterized: extends the base, adds its own member
    class q_init extends fw_xtor_initiator #(q_bundle);
        `xb_xtor_utils(q_init)
        int n;
        virtual function void build();
            super.build();
            n = 1;
        endfunction
    endclass

    class q_tgt extends fw_xtor_target #(q_bundle);
        `xb_xtor_utils(q_tgt)
    endclass

    class q_mon extends fw_xtor_monitor #(q_bundle);
        `xb_xtor_utils(q_mon)
    endclass

    // a target nobody creates: its role must still be known
    class q_tgt_unused extends fw_xtor_target #(q_bundle);
        `xb_xtor_utils(q_tgt_unused)
    endclass

    // parameterized over a std protocol bundle
    class r_init #(type T = bit) extends fw_xtor_initiator #(fw_rv_if #(T));
        typedef r_init #(T) this_t;
        `xb_xtor_param_utils(r_init)
        static function string tn_self();
            return $typename(this_t);
        endfunction
    endclass

    typedef r_init #(bit [7:0])  r_init8;
    typedef r_init #(bit [15:0]) r_init16;

    class top_c extends fw_component;
        `fw_component_utils(top_c)
        q_init   qi;
        q_tgt    qt;
        q_mon    qm;
        r_init8  r8;
        r_init16 r16;
        virtual function void build();
            qi  = q_init::create("qi", this);
            qt  = q_tgt::create("qt", this);
            qm  = q_mon::create("qm", this);
            r8  = r_init8::create("r8", this);
            r16 = r_init16::create("r16", this);
        endfunction
        virtual function void connect();
            qi.pins.connect(qt.pins);
            qm.pins.connect(qi.pins);
        endfunction
    endclass
endpackage

module xtor_base;
    import fw_hdl_pkg::*;
    import xb_pkg::*;

    // a runtime object's path and kind
    function automatic string pk(fw_object h);
        __fw_rt_obj o = __fw_rt_acc::get(h);
        return (o == null) ? "null" : {o.path, ":", o.kind_s()};
    endfunction

    initial begin
        top_c t;
        int nerr;
        t = top_c::create("top", null);
        nerr = __fw_rt::elaborate(t);
        $display("elab_errors %0d", nerr);

        // static facts, without an instance
        $display("role q_init %s", __fw_rt_proto::role_s(q_init::role()));
        $display("role q_tgt %s", __fw_rt_proto::role_s(q_tgt::role()));
        $display("role q_mon %s", __fw_rt_proto::role_s(q_mon::role()));
        $display("role q_tgt_unused %s", __fw_rt_proto::role_s(q_tgt_unused::role()));
        $display("proto q_init %s", q_init::protocol().name());
        $display("proto q_tgt_unused %s", q_tgt_unused::__fw_xtor_protocol().name());
        $display("proto r_init8 %s", r_init8::protocol().name());
        $display("proto r_init16 %s", r_init16::protocol().name());
        $display("r8_ne_r16 %0d", r_init8::protocol() != r_init16::protocol());
        $display("r8_eq_rv8 %0d",
                 r_init8::protocol() == fw_hdl_std_pkg::fw_rv_proto #(bit [7:0])::get_type());

        $display("typename %s | %s", $typename(r_init8), $typename(r_init16));
        $display("typename_in_class %s | %s", r_init8::tn_self(), r_init16::tn_self());

        // instances: pins built by the base, named "pins"
        $display("pins %s %s %s", pk(t.qi.pins), pk(t.qt.pins), pk(t.qm.pins));
        $display("sub_build %0d", t.qi.n);
        $display("pins_r16 %s", pk(t.r16.pins));

        foreach (__fw_rt::diags[i]) $display("D %s %s", __fw_rt::diags[i].id, __fw_rt::diags[i].path);
        $finish;
    end
endmodule
