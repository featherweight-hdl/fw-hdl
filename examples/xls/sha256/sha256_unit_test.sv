// SVUnit tests for sha256_pkg: the #[test] functions of sha256.x (see orig/),
// transcribed. They call the design through its generated API, so the same
// file runs at every level.
`include "svunit_defines.svh"

module sha256_unit_test;
    import svunit_pkg::svunit_testcase;
    import sha256_pkg_api_pkg::*;
    import sha256_pkg::Digest;

    string name = "sha256_ut";
    svunit_testcase svunit_ut;
    sha256_pkg_api api;

    function void build();
        svunit_ut = new(name);
        api = get();
    endfunction

    task setup();
        svunit_ut.setup();
    endtask

    task teardown();
        svunit_ut.teardown();
    endtask

    `SVUNIT_TESTS_BEGIN

    // #[test] fn compute_pad_bits_test()
    `SVTEST(compute_pad_bits_test)
        bit [31:0] got;
        api.compute_pad_bits(32'd1, got);    `FAIL_UNLESS_EQUAL(got, 32'd511)
        api.compute_pad_bits(32'd511, got);  `FAIL_UNLESS_EQUAL(got, 32'd1)
        api.compute_pad_bits(32'd512, got);  `FAIL_UNLESS_EQUAL(got, 32'd0)
        api.compute_pad_bits(32'd513, got);  `FAIL_UNLESS_EQUAL(got, 32'd511)
        api.compute_pad_bits(32'd1024, got); `FAIL_UNLESS_EQUAL(got, 32'd0)
    `SVTEST_END

    // #[test] fn sha256_empty_payload_test()
    `SVTEST(sha256_empty_payload_test)
        bit [511:0] chunk = {1'b1, 511'b0};    // u1:0b1 ++ bits[511]:0
        Digest digest;
        api.sha256(chunk, digest);
        `FAIL_UNLESS_EQUAL(digest, {32'he3b0c442, 32'h98fc1c14, 32'h9afbf4c8, 32'h996fb924,
                                    32'h27ae41e4, 32'h649b934c, 32'ha495991b, 32'h7852b855})
    `SVTEST_END

    // #[test] fn sha256_abc_test()
    `SVTEST(sha256_abc_test)
        // pad_to_512b_chunk(message as u24), the test's own helper:
        // x ++ stop_bit ++ bits[P]:0 ++ I as bits[64], with I = 24 and
        // P = compute_pad_bits(24 + 65) = 423.
        bit [511:0] chunk = {"abc", 1'b1, 423'b0, 64'd24};
        Digest digest;
        api.sha256(chunk, digest);
        `FAIL_UNLESS_EQUAL(digest, {32'hba7816bf, 32'h8f01cfea, 32'h414140de, 32'h5dae2223,
                                    32'hb00361a3, 32'h96177a9c, 32'hb410ff61, 32'hf20015ad})
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
