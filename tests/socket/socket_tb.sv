// fw_socket / fw_mirror: peer bind from either side,
// hierarchical forwarding (connect_up), and calls in both directions. Pure
// TLM -- no pins -- so the tree is driven by fw_root with no bind lines.
`include "fw_hdl_macros.svh"

package socket_tb_pkg;
    import fw_hdl_pkg::*;

    // Two one-method APIs, one per direction.
    interface class ping_if;
        pure virtual task ping(input int v);
    endclass
    interface class pong_if;
        pure virtual task pong(input int v);
    endclass

    // Kernel-macro-only IMPs (a protocol would wrap these in its own macro).
    `define PP_SOCKET_IMP(IMP, NAME) \
        `FW_SOCKET_IMP_BEGIN(ping_if, pong_if, IMP, NAME) \
            virtual task pong(input int v); m_imp.NAME``_pong(v); endtask \
        `FW_SOCKET_IMP_END(NAME)
    `define PP_MIRROR_IMP(IMP, NAME) \
        `FW_MIRROR_IMP_BEGIN(ping_if, pong_if, IMP, NAME) \
            virtual task ping(input int v); m_imp.NAME``_ping(v); endtask \
        `FW_MIRROR_IMP_END(NAME)

    // Calls ping, receives pong.
    class pinger extends fw_component implements fw_runnable;
        int got[$];
        `PP_SOCKET_IMP(pinger, lnk);
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build(); lnk = new(this); endfunction
        task run();
            for (int i = 0; i < 3; i++) lnk.t.ping(i);
        endtask
        task lnk_pong(input int v); got.push_back(v); endtask
    endclass

    // Receives ping, answers pong (from inside the inbound call).
    class ponger extends fw_component;
        int got[$];
        `PP_MIRROR_IMP(ponger, lnk);
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build(); lnk = new(this); endfunction
        task lnk_ping(input int v);
            got.push_back(v);
            lnk.t.pong(v + 100);
        endtask
    endclass

    // A wrapper that exposes its inner pinger's socket as its own (connect_up).
    class pinger_wrap extends fw_component;
        pinger inner;
        fw_socket #(ping_if, pong_if) lnk;
        function new(string name, fw_component parent); super.new(name, parent); endfunction
        function void build();
            inner = new("inner", this);
            lnk   = new("lnk", this);
        endfunction
        function void connect(); inner.lnk.connect_up(lnk); endfunction
    endclass

    class top extends fw_component implements fw_runnable;
        pinger      a;   // socket side initiates the bind
        ponger      b;
        pinger_wrap c;   // hierarchical socket, mirror side initiates
        ponger      d;
        bit         done;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            a = new("a", this); b = new("b", this);
            c = new("c", this); d = new("d", this);
        endfunction
        function void connect();
            a.lnk.connect(b.lnk);
            d.lnk.connect(c.lnk);
`ifdef NEG_SOCK_SOCK
            a.lnk.connect(c.lnk);          // socket to socket: must not compile
`endif
`ifdef NEG_MISMATCH
            begin fw_mirror #(pong_if, ping_if) m = new("m", this); a.lnk.connect(m); end  // swapped <I,E>
`endif
        endfunction
        task run();
            #10;
            done = 1;
        endtask
    endclass
endpackage

module socket_tb;
    import fw_hdl_pkg::*;
    import socket_tb_pkg::*;


    reg clock = 0, reset = 1;
    always #5 clock = ~clock;
    initial begin
        repeat (2) @(posedge clock);
        reset = 0;
    end

    function automatic bit has(string s, string sub);
        for (int i = 0; i + sub.len() <= s.len(); i++)
            if (s.substr(i, i + sub.len() - 1) == sub) return 1;
        return 0;
    endfunction

    `fw_root_begin(top, u_root, clock, reset)
    `fw_root_end

    initial begin
        int errs = 0;
        wait (u_root.root != null);
        wait (u_root.root.done);
        if (u_root.root.b.got != '{0, 1, 2})          begin errs++; $display("FAIL: b.got"); end
        if (u_root.root.a.got != '{100, 101, 102})    begin errs++; $display("FAIL: a.got"); end
        if (u_root.root.d.got != '{0, 1, 2})          begin errs++; $display("FAIL: d.got"); end
        if (u_root.root.c.inner.got != '{100, 101, 102}) begin errs++; $display("FAIL: c.inner.got"); end
        // The bind map shows each link as one endpoint, named by its peer.
        begin
            string j, want[$], a_path, b_path, c_path;
            j      = u_root.root.bind_map_json();
            a_path = u_root.root.a.lnk.full_name();
            b_path = u_root.root.b.lnk.full_name();
            c_path = u_root.root.c.lnk.full_name();
            want = '{
                // a's socket names b's mirror, and the reverse
                {"\"role\":\"socket\",\"connected\":true,\"provider\":\"", b_path, "\",\"resolved\":true"},
                {"\"role\":\"mirror\",\"connected\":true,\"provider\":\"", a_path, "\",\"resolved\":true"},
                // c's inner socket forwards up to c's own
                {"\"provider\":\"^", c_path, "\""}};
            foreach (want[i]) if (!has(j, want[i])) begin errs++; $display("FAIL: bind map lacks %s", want[i]); end
            if (has(j, "lnk.i") || has(j, "lnk.e")) begin errs++; $display("FAIL: bind map shows socket internals"); end
            if (errs != 0) u_root.root.dump_bind_map();
        end
        if (errs == 0) $display("PASS: socket_tb");
        else           $fatal(1, "FAIL: socket_tb (%0d)", errs);
        $finish;
    end
endmodule
