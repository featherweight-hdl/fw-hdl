// SVUnit tests for aes_pkg: the #[test] functions of aes.x (see orig/),
// transcribed; the vectors are copied from it mechanically (a DSLX `...` in an
// array literal repeats the last element, so a 16-byte key literal followed
// by `...` fills the rest with its last byte). They call the design through
// its generated API, so the same file runs at every level. (SVUnit's
// FAIL_UNLESS_EQUAL uses !==, which unpacked arrays don't have.)
`include "svunit_defines.svh"

module aes_unit_test;
    import svunit_pkg::svunit_testcase;
    import aes_pkg_api_pkg::*;
    import aes_pkg::*;

    string name = "aes_ut";
    svunit_testcase svunit_ut;
    aes_pkg_api api;

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

    // #[test] fn test_create_key_schedule_256()
    `SVTEST(test_create_key_schedule_256)
        Key key;
        KeySchedule sched;
        RoundKey want_rk;
        key = '{8'hac, 8'h75, 8'h4a, 8'h55, 8'h99, 8'h93, 8'h7e, 8'h79, 8'h9e, 8'h7c, 8'h46, 8'h97, 8'hb1, 8'hdd, 8'h57, 8'h14, 8'heb, 8'h11, 8'hda, 8'h40, 8'hb1, 8'h8c, 8'ha8, 8'h29, 8'h15, 8'haa, 8'h4a, 8'hd5, 8'hde, 8'h3c, 8'h83, 8'h35};
        api.create_key_schedule(key, KEY_256, sched);
        want_rk = '{32'hac754a55, 32'h99937e79, 32'h9e7c4697, 32'hb1dd5714};
        `FAIL_UNLESS(sched[0] == want_rk)
        want_rk = '{32'heb11da40, 32'hb18ca829, 32'h15aa4ad5, 32'hde3c8335};
        `FAIL_UNLESS(sched[1] == want_rk)
        want_rk = '{32'h4699dc48, 32'hdf0aa231, 32'h4176e4a6, 32'hf0abb3b2};
        `FAIL_UNLESS(sched[2] == want_rk)
        want_rk = '{32'h6773b777, 32'hd6ff1f5e, 32'hc355558b, 32'h1d69d6be};
        `FAIL_UNLESS(sched[3] == want_rk)
        want_rk = '{32'hbd6f72ec, 32'h6265d0dd, 32'h2313347b, 32'hd3b887c9};
        `FAIL_UNLESS(sched[4] == want_rk)
        want_rk = '{32'hb1b3e80b, 32'h25fc6d57, 32'he0e69de7, 32'hc47042f7};
        `FAIL_UNLESS(sched[14] == want_rk)
    `SVTEST_END

    // #[test] fn test_key_schedule_128()
    `SVTEST(test_key_schedule_128)
        Key key;
        KeySchedule sched;
        RoundKey want_rk;
        key = '{8'h66, 8'h65, 8'h64, 8'h63, 8'h62, 8'h61, 8'h39, 8'h38, 8'h37, 8'h36, 8'h35, 8'h34, 8'h33, 8'h32, 8'h31, 8'h30, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00};
        api.create_key_schedule(key, KEY_128, sched);
        want_rk = '{32'h66656463, 32'h62613938, 32'h37363534, 32'h33323130};
        `FAIL_UNLESS(sched[0] == want_rk)
        want_rk = '{32'h44a260a0, 32'h26c35998, 32'h11f56cac, 32'h22c75d9c};
        `FAIL_UNLESS(sched[1] == want_rk)
        want_rk = '{32'h80eebe33, 32'ha62de7ab, 32'hb7d88b07, 32'h951fd69b};
        `FAIL_UNLESS(sched[2] == want_rk)
        want_rk = '{32'h712106f1, 32'h59d16925, 32'h0321e7aa, 32'hb9ae62e0};
        `FAIL_UNLESS(sched[10] == want_rk)
    `SVTEST_END

    // #[test] fn test_encrypt_256()
    `SVTEST(test_encrypt_256)
        Key key;
        Block plaintext, expected, actual;
        key = '{8'hcc, 8'h6d, 8'he8, 8'h07, 8'hd0, 8'h19, 8'h80, 8'hc9, 8'h15, 8'h96, 8'hcc, 8'ha8, 8'h77, 8'h40, 8'h6b, 8'h95, 8'h8f, 8'hdb, 8'h3f, 8'he2, 8'hac, 8'h25, 8'hed, 8'h7d, 8'ha0, 8'h5b, 8'h44, 8'h92, 8'h1a, 8'h63, 8'h15, 8'h0f};
        plaintext = '{'{8'h43, 8'h6b, 8'h12, 8'hb4}, '{8'h6f, 8'hfa, 8'hb4, 8'h60}, '{8'h63, 8'hc8, 8'h44, 8'hba}, '{8'h6d, 8'h1c, 8'heb, 8'hf8}};
        expected = '{'{8'h60, 8'h06, 8'he9, 8'h6a}, '{8'h72, 8'hd2, 8'h8a, 8'hb8}, '{8'hdf, 8'h50, 8'hcf, 8'hf6}, '{8'h75, 8'hc9, 8'h3d, 8'h94}};
        api.encrypt(key, KEY_256, plaintext, actual);
        `FAIL_UNLESS(actual == expected)
    `SVTEST_END

    // #[test] fn test_encrypt_128()
    `SVTEST(test_encrypt_128)
        Key key;
        Block plaintext, expected, actual;
        key = '{8'hb9, 8'h6e, 8'he5, 8'he2, 8'h8d, 8'h4e, 8'h6a, 8'h22, 8'hdb, 8'h12, 8'hea, 8'hf5, 8'h63, 8'hf2, 8'h05, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29, 8'h29};
        plaintext = '{'{8'hf5, 8'h18, 8'ha0, 8'had}, '{8'h5a, 8'h0a, 8'h8a, 8'hfa}, '{8'h65, 8'h60, 8'h44, 8'h68}, '{8'h0f, 8'hc7, 8'h4b, 8'h3d}};
        expected = '{'{8'h57, 8'hcf, 8'h83, 8'h0a}, '{8'hdf, 8'h69, 8'h22, 8'h7f}, '{8'h6c, 8'h3a, 8'hda, 8'hab}, '{8'h51, 8'had, 8'h76, 8'h19}};
        api.encrypt(key, KEY_128, plaintext, actual);
        `FAIL_UNLESS(actual == expected)
    `SVTEST_END

    // #[test] fn test_decrypt_256()
    `SVTEST(test_decrypt_256)
        Key key;
        Block plaintext, ciphertext, actual;
        key = '{8'hcc, 8'h6d, 8'he8, 8'h07, 8'hd0, 8'h19, 8'h80, 8'hc9, 8'h15, 8'h96, 8'hcc, 8'ha8, 8'h77, 8'h40, 8'h6b, 8'h95, 8'h8f, 8'hdb, 8'h3f, 8'he2, 8'hac, 8'h25, 8'hed, 8'h7d, 8'ha0, 8'h5b, 8'h44, 8'h92, 8'h1a, 8'h63, 8'h15, 8'h0f};
        plaintext = '{'{8'h43, 8'h6b, 8'h12, 8'hb4}, '{8'h6f, 8'hfa, 8'hb4, 8'h60}, '{8'h63, 8'hc8, 8'h44, 8'hba}, '{8'h6d, 8'h1c, 8'heb, 8'hf8}};
        api.encrypt(key, KEY_256, plaintext, ciphertext);
        api.decrypt(key, KEY_256, ciphertext, actual);
        `FAIL_UNLESS(actual == plaintext)
    `SVTEST_END

    // #[test] fn test_decrypt_128()
    `SVTEST(test_decrypt_128)
        Key key;
        Block plaintext, ciphertext, actual;
        key = '{8'h50, 8'hb7, 8'h1d, 8'h6e, 8'h7f, 8'h04, 8'h59, 8'h23, 8'h5b, 8'hc2, 8'h7d, 8'h93, 8'h0a, 8'h30, 8'h9e, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8, 8'ha8};
        plaintext = '{'{8'hb6, 8'h7f, 8'h5e, 8'h7f}, '{8'h22, 8'h7c, 8'ha2, 8'hfc}, '{8'hf8, 8'h80, 8'h99, 8'hba}, '{8'h1f, 8'h14, 8'h68, 8'h29}};
        api.encrypt(key, KEY_128, plaintext, ciphertext);
        api.decrypt(key, KEY_128, ciphertext, actual);
        `FAIL_UNLESS(actual == plaintext)
    `SVTEST_END

    `SVUNIT_TESTS_END
endmodule
