// C1: CRC-32 (IEEE 802.3, reflected, polynomial 0xEDB88320), as a pure
// function and as a streaming proc. Check value: CRC-32("123456789") is
// 0xCBF43926.
`include "fw_std_macros.svh"

package crc32_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    function automatic bit [31:0] crc32_step(bit [31:0] crc, bit [7:0] b);
        crc ^= {24'h0, b};
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (32'hEDB88320 & {32{crc[0]}});
        return crc;
    endfunction

    function automatic bit [31:0] crc32_4(bit [31:0] word);
        bit [31:0] crc = 32'hFFFF_FFFF;
        for (int i = 0; i < 4; i++)
            crc = crc32_step(crc, word[8*i +: 8]);
        return ~crc;
    endfunction

    // Input beats are {last, byte}; on the last byte the CRC is sent.
    class crc32_stream extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [8:0]))  in;
        fw_port #(fw_put_if #(bit [31:0])) out;
        bit [31:0] crc = 32'hFFFF_FFFF;

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
                bit [8:0] w;
                in.t.get(w);
                crc = crc32_step(crc, w[7:0]);
                if (w[8]) begin
                    out.t.put(~crc);
                    crc = 32'hFFFF_FFFF;
                end
            end
        endtask
    endclass
endpackage
