// C3: AES-128 encryption as pure functions (FIPS-197), and C4: an AES-128-CTR
// core as a proc that produces one block per activation (SP 800-38A F.5.1).
//
// A 128-bit value holds the 16 state bytes in input order, byte 0 in the
// most significant bits ([127:120]), as FIPS-197 writes its hex strings. The
// state is column-major: row r, column c is byte r + 4c.
`include "fw_std_macros.svh"

package aes_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    localparam bit [7:0] SBOX [256] = '{
        8'h63, 8'h7c, 8'h77, 8'h7b, 8'hf2, 8'h6b, 8'h6f, 8'hc5, 8'h30, 8'h01, 8'h67, 8'h2b, 8'hfe, 8'hd7, 8'hab, 8'h76,
        8'hca, 8'h82, 8'hc9, 8'h7d, 8'hfa, 8'h59, 8'h47, 8'hf0, 8'had, 8'hd4, 8'ha2, 8'haf, 8'h9c, 8'ha4, 8'h72, 8'hc0,
        8'hb7, 8'hfd, 8'h93, 8'h26, 8'h36, 8'h3f, 8'hf7, 8'hcc, 8'h34, 8'ha5, 8'he5, 8'hf1, 8'h71, 8'hd8, 8'h31, 8'h15,
        8'h04, 8'hc7, 8'h23, 8'hc3, 8'h18, 8'h96, 8'h05, 8'h9a, 8'h07, 8'h12, 8'h80, 8'he2, 8'heb, 8'h27, 8'hb2, 8'h75,
        8'h09, 8'h83, 8'h2c, 8'h1a, 8'h1b, 8'h6e, 8'h5a, 8'ha0, 8'h52, 8'h3b, 8'hd6, 8'hb3, 8'h29, 8'he3, 8'h2f, 8'h84,
        8'h53, 8'hd1, 8'h00, 8'hed, 8'h20, 8'hfc, 8'hb1, 8'h5b, 8'h6a, 8'hcb, 8'hbe, 8'h39, 8'h4a, 8'h4c, 8'h58, 8'hcf,
        8'hd0, 8'hef, 8'haa, 8'hfb, 8'h43, 8'h4d, 8'h33, 8'h85, 8'h45, 8'hf9, 8'h02, 8'h7f, 8'h50, 8'h3c, 8'h9f, 8'ha8,
        8'h51, 8'ha3, 8'h40, 8'h8f, 8'h92, 8'h9d, 8'h38, 8'hf5, 8'hbc, 8'hb6, 8'hda, 8'h21, 8'h10, 8'hff, 8'hf3, 8'hd2,
        8'hcd, 8'h0c, 8'h13, 8'hec, 8'h5f, 8'h97, 8'h44, 8'h17, 8'hc4, 8'ha7, 8'h7e, 8'h3d, 8'h64, 8'h5d, 8'h19, 8'h73,
        8'h60, 8'h81, 8'h4f, 8'hdc, 8'h22, 8'h2a, 8'h90, 8'h88, 8'h46, 8'hee, 8'hb8, 8'h14, 8'hde, 8'h5e, 8'h0b, 8'hdb,
        8'he0, 8'h32, 8'h3a, 8'h0a, 8'h49, 8'h06, 8'h24, 8'h5c, 8'hc2, 8'hd3, 8'hac, 8'h62, 8'h91, 8'h95, 8'he4, 8'h79,
        8'he7, 8'hc8, 8'h37, 8'h6d, 8'h8d, 8'hd5, 8'h4e, 8'ha9, 8'h6c, 8'h56, 8'hf4, 8'hea, 8'h65, 8'h7a, 8'hae, 8'h08,
        8'hba, 8'h78, 8'h25, 8'h2e, 8'h1c, 8'ha6, 8'hb4, 8'hc6, 8'he8, 8'hdd, 8'h74, 8'h1f, 8'h4b, 8'hbd, 8'h8b, 8'h8a,
        8'h70, 8'h3e, 8'hb5, 8'h66, 8'h48, 8'h03, 8'hf6, 8'h0e, 8'h61, 8'h35, 8'h57, 8'hb9, 8'h86, 8'hc1, 8'h1d, 8'h9e,
        8'he1, 8'hf8, 8'h98, 8'h11, 8'h69, 8'hd9, 8'h8e, 8'h94, 8'h9b, 8'h1e, 8'h87, 8'he9, 8'hce, 8'h55, 8'h28, 8'hdf,
        8'h8c, 8'ha1, 8'h89, 8'h0d, 8'hbf, 8'he6, 8'h42, 8'h68, 8'h41, 8'h99, 8'h2d, 8'h0f, 8'hb0, 8'h54, 8'hbb, 8'h16
    };

    function automatic bit [7:0] xtime(bit [7:0] b);
        return {b[6:0], 1'b0} ^ (b[7] ? 8'h1b : 8'h00);
    endfunction

    function automatic bit [127:0] sub_bytes(bit [127:0] s);
        bit [127:0] r;
        for (int i = 0; i < 16; i++)
            r[127 - 8*i -: 8] = SBOX[s[127 - 8*i -: 8]];
        return r;
    endfunction

    // Row r rotates left by r: new (r, c) = old (r, (c + r) mod 4).
    function automatic bit [127:0] shift_rows(bit [127:0] s);
        bit [127:0] r;
        for (int c = 0; c < 4; c++)
            for (int row = 0; row < 4; row++)
                r[127 - 8*(row + 4*c) -: 8] = s[127 - 8*(row + 4*((c + row) % 4)) -: 8];
        return r;
    endfunction

    function automatic bit [31:0] mix_column(bit [31:0] col);
        bit [7:0] a0, a1, a2, a3;
        {a0, a1, a2, a3} = col;
        return {xtime(a0) ^ xtime(a1) ^ a1 ^ a2 ^ a3,
                a0 ^ xtime(a1) ^ xtime(a2) ^ a2 ^ a3,
                a0 ^ a1 ^ xtime(a2) ^ xtime(a3) ^ a3,
                xtime(a0) ^ a0 ^ a1 ^ a2 ^ xtime(a3)};
    endfunction

    function automatic bit [127:0] mix_columns(bit [127:0] s);
        bit [127:0] r;
        for (int c = 0; c < 4; c++)
            r[127 - 32*c -: 32] = mix_column(s[127 - 32*c -: 32]);
        return r;
    endfunction

    function automatic bit [31:0] sub_word(bit [31:0] w);
        return {SBOX[w[31:24]], SBOX[w[23:16]], SBOX[w[15:8]], SBOX[w[7:0]]};
    endfunction

    function automatic bit [127:0] next_round_key(bit [127:0] k, bit [7:0] rcon);
        bit [31:0] w0, w1, w2, w3, t;
        {w0, w1, w2, w3} = k;
        t = sub_word({w3[23:0], w3[31:24]}) ^ {rcon, 24'h0};
        w0 = w0 ^ t;
        w1 = w1 ^ w0;
        w2 = w2 ^ w1;
        w3 = w3 ^ w2;
        return {w0, w1, w2, w3};
    endfunction

    function automatic bit [127:0] aes128_encrypt(bit [127:0] key, bit [127:0] pt);
        bit [127:0] s = pt ^ key;
        bit [127:0] k = key;
        bit [7:0] rcon = 8'h01;
        for (int round = 1; round <= 10; round++) begin
            k = next_round_key(k, rcon);
            rcon = xtime(rcon);
            s = shift_rows(sub_bytes(s));
            if (round != 10) s = mix_columns(s);
            s = s ^ k;
        end
        return s;
    endfunction

    // C4: AES-128-CTR. A command {key, initial counter, block count} starts a
    // message; then each activation takes one plaintext block and sends one
    // ciphertext block. The block loop lives in state (`remaining`), one block
    // per activation, because a channel op inside a loop is outside X0 (P10).
    typedef struct packed {
        bit [127:0] key;
        bit [127:0] ctr;
        bit [7:0]   nblocks;
    } ctr_cmd_t;

    class aes_ctr extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(ctr_cmd_t))   cmd;
        fw_port #(fw_get_if #(bit [127:0])) din;
        fw_port #(fw_put_if #(bit [127:0])) dout;
        bit [127:0] key;
        bit [127:0] ctr;
        bit [7:0]   remaining;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            cmd = new("cmd", this);
            din = new("din", this);
            dout = new("dout", this);
        endfunction

        virtual task run();
            forever begin
                if (remaining == 0) begin
                    ctr_cmd_t c;
                    cmd.t.get(c);
                    key = c.key;
                    ctr = c.ctr;
                    remaining = c.nblocks;
                end else begin
                    bit [127:0] pt;
                    din.t.get(pt);
                    dout.t.put(pt ^ aes128_encrypt(key, ctr));
                    ctr = ctr + 1;
                    remaining = remaining - 1;
                end
            end
        endtask
    endclass
endpackage
