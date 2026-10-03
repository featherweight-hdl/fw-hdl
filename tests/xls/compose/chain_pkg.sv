// T1 (xls-phase2.md): three static-subset blocks chained by two channels.
//
//   in ──► rle_enc8 ──c0 (rendezvous)──► pkt_framer ──c1 (depth 2)──► crc32_stream ──► out
//
// rle_enc8 turns bytes into {sym, cnt} packets; pkt_framer sends each packet as
// two {last, byte} beats and marks the end of every fourth packet as `last`;
// crc32_stream puts the CRC-32 of each such frame. Each block is in the static
// subset on its own; the top only builds and connects them.
package chain_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rle8_pkg::*;
    import crc32_pkg::*;

    typedef rle_enc8_t::pkt_t pkt_t;

    class pkt_framer extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(pkt_t))     in;
        fw_port #(fw_put_if #(bit [8:0])) out;
        bit       phase;      // 0: next beat is a packet's sym; 1: its cnt
        bit [7:0] held;       // the cnt waiting to be sent
        bit [1:0] n;          // packets in the current frame

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction

        virtual task run();
            forever begin
                pkt_t p;
                if (!phase)
                    in.t.get(p);
                out.t.put(phase ? {n == 2'd3, held} : {1'b0, p.sym});
                if (phase)
                    n = n + 2'd1;
                else
                    held = p.cnt;
                phase = !phase;
            end
        endtask
    endclass

    class chain_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0]))  in;
        fw_port #(fw_put_if #(bit [31:0])) out;

        rle_enc8_t                     rle;
        pkt_framer                     fr;
        crc32_stream                   crc;
        fw_channel #(pkt_t, 0)         c0;
        fw_channel #(bit [8:0], 2)     c1;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction

        function void build();
            in  = new("in", this);
            out = new("out", this);
            rle = new("rle", this);
            fr  = new("fr", this);
            crc = new("crc", this);
            c0  = new("c0", this);
            c1  = new("c1", this);
        endfunction

        function void connect();
            rle.in.connect(in);          // the top's ports are the boundary
            rle.out.connect(c0.put_ex);
            fr.in.connect(c0.get_ex);
            fr.out.connect(c1.put_ex);
            crc.in.connect(c1.get_ex);
            crc.out.connect(out);
        endfunction
    endclass
endpackage
