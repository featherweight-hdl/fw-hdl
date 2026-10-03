// Derived from XLS xls/examples/sha256.x (see orig/), Copyright The XLS
// Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.

// ---
//
// SHA algorithm based on the description in:
//
// https://en.wikipedia.org/wiki/SHA-2#Pseudocode
//
// We attempt to mirror the pseudocode presented there fairly directly for ease
// of reproducing correct results.

package sha256_pkg;

    // pub type Digest = (u32, u32, u32, u32, u32, u32, u32, u32); fields in
    // tuple order, the first the most significant, as XLS lays out a tuple.
    typedef struct packed {
        bit [31:0] d0, d1, d2, d3, d4, d5, d6, d7;
    } Digest;

    typedef bit [31:0] w_t [64];

    function automatic bit [31:0] rotr(bit [31:0] x, bit [31:0] y);
        return xls_std_pkg::rotr_c#(32)::rotr(x, y);
    endfunction

    function automatic w_t sha256_chunk_w_table(bit [511:0] chunk);
        // Seed the "w" table with the message chunk: (chunk ++ bits[1536]:0)
        // as u32[64], element 0 the most significant word.
        w_t w;
        for (int i = 0; i < 64; i++)
            w[i] = (i < 16) ? chunk[511 - 32 * i -: 32] : 32'd0;

        // Build up the remaining values of the "w" table.
        for (int i = 0; i < 48; i++) begin
            bit [31:0] w_im15 = w[i + 16 - 15];
            bit [31:0] s_0 = rotr(w_im15, 32'd7) ^ rotr(w_im15, 32'd18) ^ (w_im15 >> 3);
            bit [31:0] w_im2 = w[i + 16 - 2];
            bit [31:0] s_1 = rotr(w_im2, 32'd17) ^ rotr(w_im2, 32'd19) ^ (w_im2 >> 10);
            bit [31:0] value = w[i + 16 - 16] + s_0 + w[i + 16 - 7] + s_1;
            w[i + 16] = value;
        end
        return w;
    endfunction

    // The constant "K" table of addends.
    localparam bit [31:0] K [64] = '{
            32'h428a2f98, 32'h71374491, 32'hb5c0fbcf, 32'he9b5dba5, 32'h3956c25b,
            32'h59f111f1, 32'h923f82a4, 32'hab1c5ed5, 32'hd807aa98, 32'h12835b01,
            32'h243185be, 32'h550c7dc3, 32'h72be5d74, 32'h80deb1fe, 32'h9bdc06a7,
            32'hc19bf174, 32'he49b69c1, 32'hefbe4786, 32'h0fc19dc6, 32'h240ca1cc,
            32'h2de92c6f, 32'h4a7484aa, 32'h5cb0a9dc, 32'h76f988da, 32'h983e5152,
            32'ha831c66d, 32'hb00327c8, 32'hbf597fc7, 32'hc6e00bf3, 32'hd5a79147,
            32'h06ca6351, 32'h14292967, 32'h27b70a85, 32'h2e1b2138, 32'h4d2c6dfc,
            32'h53380d13, 32'h650a7354, 32'h766a0abb, 32'h81c2c92e, 32'h92722c85,
            32'ha2bfe8a1, 32'ha81a664b, 32'hc24b8b70, 32'hc76c51a3, 32'hd192e819,
            32'hd6990624, 32'hf40e3585, 32'h106aa070, 32'h19a4c116, 32'h1e376c08,
            32'h2748774c, 32'h34b0bcb5, 32'h391c0cb3, 32'h4ed8aa4a, 32'h5b9cca4f,
            32'h682e6ff3, 32'h748f82ee, 32'h78a5636f, 32'h84c87814, 32'h8cc70208,
            32'h90befffa, 32'ha4506ceb, 32'hbef9a3f7, 32'hc67178f2
    };

    // Evolves the digest for a single chunk in the overall message being
    // SHA256-hashed.
    function automatic Digest sha256_chunk(bit [511:0] chunk, Digest digest_init);
        w_t w = sha256_chunk_w_table(chunk);
        bit [31:0] a = digest_init.d0, b = digest_init.d1, c = digest_init.d2,
                   d = digest_init.d3, e = digest_init.d4, f = digest_init.d5,
                   g = digest_init.d6, h = digest_init.d7;

        // Compute the digest using the "w" table over 64 "rounds".
        for (int i = 0; i < 64; i++) begin
            bit [31:0] S1 = rotr(e, 32'd6) ^ rotr(e, 32'd11) ^ rotr(e, 32'd25);
            bit [31:0] ch = (e & f) ^ ((~e) & g);
            bit [31:0] temp1 = h + S1 + ch + K[i] + w[i];
            bit [31:0] S0 = rotr(a, 32'd2) ^ rotr(a, 32'd13) ^ rotr(a, 32'd22);
            bit [31:0] maj = (a & b) ^ (a & c) ^ (b & c);
            bit [31:0] temp2 = S0 + maj;
            h = g; g = f; f = e;
            e = d + temp1;
            d = c; c = b; b = a;
            a = temp1 + temp2;
        end

        // The new digest mixes together values from the original digest with the
        // derived values (a, b, c, ...) we've computed.
        return '{d0: digest_init.d0 + a, d1: digest_init.d1 + b, d2: digest_init.d2 + c,
                 d3: digest_init.d3 + d, d4: digest_init.d4 + e, d5: digest_init.d5 + f,
                 d6: digest_init.d6 + g, d7: digest_init.d7 + h};
    endfunction

    // Returns the number of bits required to add on to turn bit_count into a
    // multiple of 512.
    function automatic bit [31:0] compute_pad_bits(bit [31:0] bit_count);
        return xls_std_pkg::round_up_to_nearest(bit_count, 32'd512) - bit_count;
    endfunction

    function automatic Digest sha256(bit [511:0] message);
        Digest digest_init = '{
            d0: 32'h6a09e667, d1: 32'hbb67ae85, d2: 32'h3c6ef372, d3: 32'ha54ff53a,
            d4: 32'h510e527f, d5: 32'h9b05688c, d6: 32'h1f83d9ab, d7: 32'h5be0cd19};
        return sha256_chunk(message, digest_init);
    endfunction

    function automatic Digest main(bit [511:0] message);
        return sha256(message);
    endfunction

endpackage
