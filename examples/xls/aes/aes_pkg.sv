// Derived from XLS xls/modules/aes/{constants,aes_common,aes}.x (see orig/),
// Copyright The XLS Authors, Apache-2.0 (see ../NOTICE). A line-for-line port
// to the fw-hdl static subset; README.md lists the deviations.
//
// DSLX casts between bits and arrays put element 0 in the *most* significant
// position: `word as u8[4]` makes bytes[0] = word[31:24].

package aes_pkg;

    // ---- constants.x -------------------------------------------------
    localparam bit [7:0] S_BOX [256] = '{
        8'h63, 8'h7c, 8'h77, 8'h7b, 8'hf2, 8'h6b, 8'h6f, 8'hc5,
        8'h30, 8'h01, 8'h67, 8'h2b, 8'hfe, 8'hd7, 8'hab, 8'h76,
        8'hca, 8'h82, 8'hc9, 8'h7d, 8'hfa, 8'h59, 8'h47, 8'hf0,
        8'had, 8'hd4, 8'ha2, 8'haf, 8'h9c, 8'ha4, 8'h72, 8'hc0,
        8'hb7, 8'hfd, 8'h93, 8'h26, 8'h36, 8'h3f, 8'hf7, 8'hcc,
        8'h34, 8'ha5, 8'he5, 8'hf1, 8'h71, 8'hd8, 8'h31, 8'h15,
        8'h04, 8'hc7, 8'h23, 8'hc3, 8'h18, 8'h96, 8'h05, 8'h9a,
        8'h07, 8'h12, 8'h80, 8'he2, 8'heb, 8'h27, 8'hb2, 8'h75,
        8'h09, 8'h83, 8'h2c, 8'h1a, 8'h1b, 8'h6e, 8'h5a, 8'ha0,
        8'h52, 8'h3b, 8'hd6, 8'hb3, 8'h29, 8'he3, 8'h2f, 8'h84,
        8'h53, 8'hd1, 8'h00, 8'hed, 8'h20, 8'hfc, 8'hb1, 8'h5b,
        8'h6a, 8'hcb, 8'hbe, 8'h39, 8'h4a, 8'h4c, 8'h58, 8'hcf,
        8'hd0, 8'hef, 8'haa, 8'hfb, 8'h43, 8'h4d, 8'h33, 8'h85,
        8'h45, 8'hf9, 8'h02, 8'h7f, 8'h50, 8'h3c, 8'h9f, 8'ha8,
        8'h51, 8'ha3, 8'h40, 8'h8f, 8'h92, 8'h9d, 8'h38, 8'hf5,
        8'hbc, 8'hb6, 8'hda, 8'h21, 8'h10, 8'hff, 8'hf3, 8'hd2,
        8'hcd, 8'h0c, 8'h13, 8'hec, 8'h5f, 8'h97, 8'h44, 8'h17,
        8'hc4, 8'ha7, 8'h7e, 8'h3d, 8'h64, 8'h5d, 8'h19, 8'h73,
        8'h60, 8'h81, 8'h4f, 8'hdc, 8'h22, 8'h2a, 8'h90, 8'h88,
        8'h46, 8'hee, 8'hb8, 8'h14, 8'hde, 8'h5e, 8'h0b, 8'hdb,
        8'he0, 8'h32, 8'h3a, 8'h0a, 8'h49, 8'h06, 8'h24, 8'h5c,
        8'hc2, 8'hd3, 8'hac, 8'h62, 8'h91, 8'h95, 8'he4, 8'h79,
        8'he7, 8'hc8, 8'h37, 8'h6d, 8'h8d, 8'hd5, 8'h4e, 8'ha9,
        8'h6c, 8'h56, 8'hf4, 8'hea, 8'h65, 8'h7a, 8'hae, 8'h08,
        8'hba, 8'h78, 8'h25, 8'h2e, 8'h1c, 8'ha6, 8'hb4, 8'hc6,
        8'he8, 8'hdd, 8'h74, 8'h1f, 8'h4b, 8'hbd, 8'h8b, 8'h8a,
        8'h70, 8'h3e, 8'hb5, 8'h66, 8'h48, 8'h03, 8'hf6, 8'h0e,
        8'h61, 8'h35, 8'h57, 8'hb9, 8'h86, 8'hc1, 8'h1d, 8'h9e,
        8'he1, 8'hf8, 8'h98, 8'h11, 8'h69, 8'hd9, 8'h8e, 8'h94,
        8'h9b, 8'h1e, 8'h87, 8'he9, 8'hce, 8'h55, 8'h28, 8'hdf,
        8'h8c, 8'ha1, 8'h89, 8'h0d, 8'hbf, 8'he6, 8'h42, 8'h68,
        8'h41, 8'h99, 8'h2d, 8'h0f, 8'hb0, 8'h54, 8'hbb, 8'h16
    };

    localparam bit [7:0] INV_S_BOX [256] = '{
        8'h52, 8'h09, 8'h6a, 8'hd5, 8'h30, 8'h36, 8'ha5, 8'h38,
        8'hbf, 8'h40, 8'ha3, 8'h9e, 8'h81, 8'hf3, 8'hd7, 8'hfb,
        8'h7c, 8'he3, 8'h39, 8'h82, 8'h9b, 8'h2f, 8'hff, 8'h87,
        8'h34, 8'h8e, 8'h43, 8'h44, 8'hc4, 8'hde, 8'he9, 8'hcb,
        8'h54, 8'h7b, 8'h94, 8'h32, 8'ha6, 8'hc2, 8'h23, 8'h3d,
        8'hee, 8'h4c, 8'h95, 8'h0b, 8'h42, 8'hfa, 8'hc3, 8'h4e,
        8'h08, 8'h2e, 8'ha1, 8'h66, 8'h28, 8'hd9, 8'h24, 8'hb2,
        8'h76, 8'h5b, 8'ha2, 8'h49, 8'h6d, 8'h8b, 8'hd1, 8'h25,
        8'h72, 8'hf8, 8'hf6, 8'h64, 8'h86, 8'h68, 8'h98, 8'h16,
        8'hd4, 8'ha4, 8'h5c, 8'hcc, 8'h5d, 8'h65, 8'hb6, 8'h92,
        8'h6c, 8'h70, 8'h48, 8'h50, 8'hfd, 8'hed, 8'hb9, 8'hda,
        8'h5e, 8'h15, 8'h46, 8'h57, 8'ha7, 8'h8d, 8'h9d, 8'h84,
        8'h90, 8'hd8, 8'hab, 8'h00, 8'h8c, 8'hbc, 8'hd3, 8'h0a,
        8'hf7, 8'he4, 8'h58, 8'h05, 8'hb8, 8'hb3, 8'h45, 8'h06,
        8'hd0, 8'h2c, 8'h1e, 8'h8f, 8'hca, 8'h3f, 8'h0f, 8'h02,
        8'hc1, 8'haf, 8'hbd, 8'h03, 8'h01, 8'h13, 8'h8a, 8'h6b,
        8'h3a, 8'h91, 8'h11, 8'h41, 8'h4f, 8'h67, 8'hdc, 8'hea,
        8'h97, 8'hf2, 8'hcf, 8'hce, 8'hf0, 8'hb4, 8'he6, 8'h73,
        8'h96, 8'hac, 8'h74, 8'h22, 8'he7, 8'had, 8'h35, 8'h85,
        8'he2, 8'hf9, 8'h37, 8'he8, 8'h1c, 8'h75, 8'hdf, 8'h6e,
        8'h47, 8'hf1, 8'h1a, 8'h71, 8'h1d, 8'h29, 8'hc5, 8'h89,
        8'h6f, 8'hb7, 8'h62, 8'h0e, 8'haa, 8'h18, 8'hbe, 8'h1b,
        8'hfc, 8'h56, 8'h3e, 8'h4b, 8'hc6, 8'hd2, 8'h79, 8'h20,
        8'h9a, 8'hdb, 8'hc0, 8'hfe, 8'h78, 8'hcd, 8'h5a, 8'hf4,
        8'h1f, 8'hdd, 8'ha8, 8'h33, 8'h88, 8'h07, 8'hc7, 8'h31,
        8'hb1, 8'h12, 8'h10, 8'h59, 8'h27, 8'h80, 8'hec, 8'h5f,
        8'h60, 8'h51, 8'h7f, 8'ha9, 8'h19, 8'hb5, 8'h4a, 8'h0d,
        8'h2d, 8'he5, 8'h7a, 8'h9f, 8'h93, 8'hc9, 8'h9c, 8'hef,
        8'ha0, 8'he0, 8'h3b, 8'h4d, 8'hae, 8'h2a, 8'hf5, 8'hb0,
        8'hc8, 8'heb, 8'hbb, 8'h3c, 8'h83, 8'h53, 8'h99, 8'h61,
        8'h17, 8'h2b, 8'h04, 8'h7e, 8'hba, 8'h77, 8'hd6, 8'h26,
        8'he1, 8'h69, 8'h14, 8'h63, 8'h55, 8'h21, 8'h0c, 8'h7d
    };

    localparam bit [31:0] R_CON [10] = '{
        32'h01000000, 32'h02000000, 32'h04000000, 32'h08000000,
        32'h10000000, 32'h20000000, 32'h40000000, 32'h80000000,
        32'h1b000000, 32'h36000000
    };

    localparam bit [7:0] GF_MUL_9_TBL [256] = '{
        8'h00, 8'h09, 8'h12, 8'h1b, 8'h24, 8'h2d, 8'h36, 8'h3f,
        8'h48, 8'h41, 8'h5a, 8'h53, 8'h6c, 8'h65, 8'h7e, 8'h77,
        8'h90, 8'h99, 8'h82, 8'h8b, 8'hb4, 8'hbd, 8'ha6, 8'haf,
        8'hd8, 8'hd1, 8'hca, 8'hc3, 8'hfc, 8'hf5, 8'hee, 8'he7,
        8'h3b, 8'h32, 8'h29, 8'h20, 8'h1f, 8'h16, 8'h0d, 8'h04,
        8'h73, 8'h7a, 8'h61, 8'h68, 8'h57, 8'h5e, 8'h45, 8'h4c,
        8'hab, 8'ha2, 8'hb9, 8'hb0, 8'h8f, 8'h86, 8'h9d, 8'h94,
        8'he3, 8'hea, 8'hf1, 8'hf8, 8'hc7, 8'hce, 8'hd5, 8'hdc,
        8'h76, 8'h7f, 8'h64, 8'h6d, 8'h52, 8'h5b, 8'h40, 8'h49,
        8'h3e, 8'h37, 8'h2c, 8'h25, 8'h1a, 8'h13, 8'h08, 8'h01,
        8'he6, 8'hef, 8'hf4, 8'hfd, 8'hc2, 8'hcb, 8'hd0, 8'hd9,
        8'hae, 8'ha7, 8'hbc, 8'hb5, 8'h8a, 8'h83, 8'h98, 8'h91,
        8'h4d, 8'h44, 8'h5f, 8'h56, 8'h69, 8'h60, 8'h7b, 8'h72,
        8'h05, 8'h0c, 8'h17, 8'h1e, 8'h21, 8'h28, 8'h33, 8'h3a,
        8'hdd, 8'hd4, 8'hcf, 8'hc6, 8'hf9, 8'hf0, 8'heb, 8'he2,
        8'h95, 8'h9c, 8'h87, 8'h8e, 8'hb1, 8'hb8, 8'ha3, 8'haa,
        8'hec, 8'he5, 8'hfe, 8'hf7, 8'hc8, 8'hc1, 8'hda, 8'hd3,
        8'ha4, 8'had, 8'hb6, 8'hbf, 8'h80, 8'h89, 8'h92, 8'h9b,
        8'h7c, 8'h75, 8'h6e, 8'h67, 8'h58, 8'h51, 8'h4a, 8'h43,
        8'h34, 8'h3d, 8'h26, 8'h2f, 8'h10, 8'h19, 8'h02, 8'h0b,
        8'hd7, 8'hde, 8'hc5, 8'hcc, 8'hf3, 8'hfa, 8'he1, 8'he8,
        8'h9f, 8'h96, 8'h8d, 8'h84, 8'hbb, 8'hb2, 8'ha9, 8'ha0,
        8'h47, 8'h4e, 8'h55, 8'h5c, 8'h63, 8'h6a, 8'h71, 8'h78,
        8'h0f, 8'h06, 8'h1d, 8'h14, 8'h2b, 8'h22, 8'h39, 8'h30,
        8'h9a, 8'h93, 8'h88, 8'h81, 8'hbe, 8'hb7, 8'hac, 8'ha5,
        8'hd2, 8'hdb, 8'hc0, 8'hc9, 8'hf6, 8'hff, 8'he4, 8'hed,
        8'h0a, 8'h03, 8'h18, 8'h11, 8'h2e, 8'h27, 8'h3c, 8'h35,
        8'h42, 8'h4b, 8'h50, 8'h59, 8'h66, 8'h6f, 8'h74, 8'h7d,
        8'ha1, 8'ha8, 8'hb3, 8'hba, 8'h85, 8'h8c, 8'h97, 8'h9e,
        8'he9, 8'he0, 8'hfb, 8'hf2, 8'hcd, 8'hc4, 8'hdf, 8'hd6,
        8'h31, 8'h38, 8'h23, 8'h2a, 8'h15, 8'h1c, 8'h07, 8'h0e,
        8'h79, 8'h70, 8'h6b, 8'h62, 8'h5d, 8'h54, 8'h4f, 8'h46
    };

    localparam bit [7:0] GF_MUL_11_TBL [256] = '{
        8'h00, 8'h0b, 8'h16, 8'h1d, 8'h2c, 8'h27, 8'h3a, 8'h31,
        8'h58, 8'h53, 8'h4e, 8'h45, 8'h74, 8'h7f, 8'h62, 8'h69,
        8'hb0, 8'hbb, 8'ha6, 8'had, 8'h9c, 8'h97, 8'h8a, 8'h81,
        8'he8, 8'he3, 8'hfe, 8'hf5, 8'hc4, 8'hcf, 8'hd2, 8'hd9,
        8'h7b, 8'h70, 8'h6d, 8'h66, 8'h57, 8'h5c, 8'h41, 8'h4a,
        8'h23, 8'h28, 8'h35, 8'h3e, 8'h0f, 8'h04, 8'h19, 8'h12,
        8'hcb, 8'hc0, 8'hdd, 8'hd6, 8'he7, 8'hec, 8'hf1, 8'hfa,
        8'h93, 8'h98, 8'h85, 8'h8e, 8'hbf, 8'hb4, 8'ha9, 8'ha2,
        8'hf6, 8'hfd, 8'he0, 8'heb, 8'hda, 8'hd1, 8'hcc, 8'hc7,
        8'hae, 8'ha5, 8'hb8, 8'hb3, 8'h82, 8'h89, 8'h94, 8'h9f,
        8'h46, 8'h4d, 8'h50, 8'h5b, 8'h6a, 8'h61, 8'h7c, 8'h77,
        8'h1e, 8'h15, 8'h08, 8'h03, 8'h32, 8'h39, 8'h24, 8'h2f,
        8'h8d, 8'h86, 8'h9b, 8'h90, 8'ha1, 8'haa, 8'hb7, 8'hbc,
        8'hd5, 8'hde, 8'hc3, 8'hc8, 8'hf9, 8'hf2, 8'hef, 8'he4,
        8'h3d, 8'h36, 8'h2b, 8'h20, 8'h11, 8'h1a, 8'h07, 8'h0c,
        8'h65, 8'h6e, 8'h73, 8'h78, 8'h49, 8'h42, 8'h5f, 8'h54,
        8'hf7, 8'hfc, 8'he1, 8'hea, 8'hdb, 8'hd0, 8'hcd, 8'hc6,
        8'haf, 8'ha4, 8'hb9, 8'hb2, 8'h83, 8'h88, 8'h95, 8'h9e,
        8'h47, 8'h4c, 8'h51, 8'h5a, 8'h6b, 8'h60, 8'h7d, 8'h76,
        8'h1f, 8'h14, 8'h09, 8'h02, 8'h33, 8'h38, 8'h25, 8'h2e,
        8'h8c, 8'h87, 8'h9a, 8'h91, 8'ha0, 8'hab, 8'hb6, 8'hbd,
        8'hd4, 8'hdf, 8'hc2, 8'hc9, 8'hf8, 8'hf3, 8'hee, 8'he5,
        8'h3c, 8'h37, 8'h2a, 8'h21, 8'h10, 8'h1b, 8'h06, 8'h0d,
        8'h64, 8'h6f, 8'h72, 8'h79, 8'h48, 8'h43, 8'h5e, 8'h55,
        8'h01, 8'h0a, 8'h17, 8'h1c, 8'h2d, 8'h26, 8'h3b, 8'h30,
        8'h59, 8'h52, 8'h4f, 8'h44, 8'h75, 8'h7e, 8'h63, 8'h68,
        8'hb1, 8'hba, 8'ha7, 8'hac, 8'h9d, 8'h96, 8'h8b, 8'h80,
        8'he9, 8'he2, 8'hff, 8'hf4, 8'hc5, 8'hce, 8'hd3, 8'hd8,
        8'h7a, 8'h71, 8'h6c, 8'h67, 8'h56, 8'h5d, 8'h40, 8'h4b,
        8'h22, 8'h29, 8'h34, 8'h3f, 8'h0e, 8'h05, 8'h18, 8'h13,
        8'hca, 8'hc1, 8'hdc, 8'hd7, 8'he6, 8'hed, 8'hf0, 8'hfb,
        8'h92, 8'h99, 8'h84, 8'h8f, 8'hbe, 8'hb5, 8'ha8, 8'ha3
    };

    localparam bit [7:0] GF_MUL_13_TBL [256] = '{
        8'h00, 8'h0d, 8'h1a, 8'h17, 8'h34, 8'h39, 8'h2e, 8'h23,
        8'h68, 8'h65, 8'h72, 8'h7f, 8'h5c, 8'h51, 8'h46, 8'h4b,
        8'hd0, 8'hdd, 8'hca, 8'hc7, 8'he4, 8'he9, 8'hfe, 8'hf3,
        8'hb8, 8'hb5, 8'ha2, 8'haf, 8'h8c, 8'h81, 8'h96, 8'h9b,
        8'hbb, 8'hb6, 8'ha1, 8'hac, 8'h8f, 8'h82, 8'h95, 8'h98,
        8'hd3, 8'hde, 8'hc9, 8'hc4, 8'he7, 8'hea, 8'hfd, 8'hf0,
        8'h6b, 8'h66, 8'h71, 8'h7c, 8'h5f, 8'h52, 8'h45, 8'h48,
        8'h03, 8'h0e, 8'h19, 8'h14, 8'h37, 8'h3a, 8'h2d, 8'h20,
        8'h6d, 8'h60, 8'h77, 8'h7a, 8'h59, 8'h54, 8'h43, 8'h4e,
        8'h05, 8'h08, 8'h1f, 8'h12, 8'h31, 8'h3c, 8'h2b, 8'h26,
        8'hbd, 8'hb0, 8'ha7, 8'haa, 8'h89, 8'h84, 8'h93, 8'h9e,
        8'hd5, 8'hd8, 8'hcf, 8'hc2, 8'he1, 8'hec, 8'hfb, 8'hf6,
        8'hd6, 8'hdb, 8'hcc, 8'hc1, 8'he2, 8'hef, 8'hf8, 8'hf5,
        8'hbe, 8'hb3, 8'ha4, 8'ha9, 8'h8a, 8'h87, 8'h90, 8'h9d,
        8'h06, 8'h0b, 8'h1c, 8'h11, 8'h32, 8'h3f, 8'h28, 8'h25,
        8'h6e, 8'h63, 8'h74, 8'h79, 8'h5a, 8'h57, 8'h40, 8'h4d,
        8'hda, 8'hd7, 8'hc0, 8'hcd, 8'hee, 8'he3, 8'hf4, 8'hf9,
        8'hb2, 8'hbf, 8'ha8, 8'ha5, 8'h86, 8'h8b, 8'h9c, 8'h91,
        8'h0a, 8'h07, 8'h10, 8'h1d, 8'h3e, 8'h33, 8'h24, 8'h29,
        8'h62, 8'h6f, 8'h78, 8'h75, 8'h56, 8'h5b, 8'h4c, 8'h41,
        8'h61, 8'h6c, 8'h7b, 8'h76, 8'h55, 8'h58, 8'h4f, 8'h42,
        8'h09, 8'h04, 8'h13, 8'h1e, 8'h3d, 8'h30, 8'h27, 8'h2a,
        8'hb1, 8'hbc, 8'hab, 8'ha6, 8'h85, 8'h88, 8'h9f, 8'h92,
        8'hd9, 8'hd4, 8'hc3, 8'hce, 8'hed, 8'he0, 8'hf7, 8'hfa,
        8'hb7, 8'hba, 8'had, 8'ha0, 8'h83, 8'h8e, 8'h99, 8'h94,
        8'hdf, 8'hd2, 8'hc5, 8'hc8, 8'heb, 8'he6, 8'hf1, 8'hfc,
        8'h67, 8'h6a, 8'h7d, 8'h70, 8'h53, 8'h5e, 8'h49, 8'h44,
        8'h0f, 8'h02, 8'h15, 8'h18, 8'h3b, 8'h36, 8'h21, 8'h2c,
        8'h0c, 8'h01, 8'h16, 8'h1b, 8'h38, 8'h35, 8'h22, 8'h2f,
        8'h64, 8'h69, 8'h7e, 8'h73, 8'h50, 8'h5d, 8'h4a, 8'h47,
        8'hdc, 8'hd1, 8'hc6, 8'hcb, 8'he8, 8'he5, 8'hf2, 8'hff,
        8'hb4, 8'hb9, 8'hae, 8'ha3, 8'h80, 8'h8d, 8'h9a, 8'h97
    };

    localparam bit [7:0] GF_MUL_14_TBL [256] = '{
        8'h00, 8'h0e, 8'h1c, 8'h12, 8'h38, 8'h36, 8'h24, 8'h2a,
        8'h70, 8'h7e, 8'h6c, 8'h62, 8'h48, 8'h46, 8'h54, 8'h5a,
        8'he0, 8'hee, 8'hfc, 8'hf2, 8'hd8, 8'hd6, 8'hc4, 8'hca,
        8'h90, 8'h9e, 8'h8c, 8'h82, 8'ha8, 8'ha6, 8'hb4, 8'hba,
        8'hdb, 8'hd5, 8'hc7, 8'hc9, 8'he3, 8'hed, 8'hff, 8'hf1,
        8'hab, 8'ha5, 8'hb7, 8'hb9, 8'h93, 8'h9d, 8'h8f, 8'h81,
        8'h3b, 8'h35, 8'h27, 8'h29, 8'h03, 8'h0d, 8'h1f, 8'h11,
        8'h4b, 8'h45, 8'h57, 8'h59, 8'h73, 8'h7d, 8'h6f, 8'h61,
        8'had, 8'ha3, 8'hb1, 8'hbf, 8'h95, 8'h9b, 8'h89, 8'h87,
        8'hdd, 8'hd3, 8'hc1, 8'hcf, 8'he5, 8'heb, 8'hf9, 8'hf7,
        8'h4d, 8'h43, 8'h51, 8'h5f, 8'h75, 8'h7b, 8'h69, 8'h67,
        8'h3d, 8'h33, 8'h21, 8'h2f, 8'h05, 8'h0b, 8'h19, 8'h17,
        8'h76, 8'h78, 8'h6a, 8'h64, 8'h4e, 8'h40, 8'h52, 8'h5c,
        8'h06, 8'h08, 8'h1a, 8'h14, 8'h3e, 8'h30, 8'h22, 8'h2c,
        8'h96, 8'h98, 8'h8a, 8'h84, 8'hae, 8'ha0, 8'hb2, 8'hbc,
        8'he6, 8'he8, 8'hfa, 8'hf4, 8'hde, 8'hd0, 8'hc2, 8'hcc,
        8'h41, 8'h4f, 8'h5d, 8'h53, 8'h79, 8'h77, 8'h65, 8'h6b,
        8'h31, 8'h3f, 8'h2d, 8'h23, 8'h09, 8'h07, 8'h15, 8'h1b,
        8'ha1, 8'haf, 8'hbd, 8'hb3, 8'h99, 8'h97, 8'h85, 8'h8b,
        8'hd1, 8'hdf, 8'hcd, 8'hc3, 8'he9, 8'he7, 8'hf5, 8'hfb,
        8'h9a, 8'h94, 8'h86, 8'h88, 8'ha2, 8'hac, 8'hbe, 8'hb0,
        8'hea, 8'he4, 8'hf6, 8'hf8, 8'hd2, 8'hdc, 8'hce, 8'hc0,
        8'h7a, 8'h74, 8'h66, 8'h68, 8'h42, 8'h4c, 8'h5e, 8'h50,
        8'h0a, 8'h04, 8'h16, 8'h18, 8'h32, 8'h3c, 8'h2e, 8'h20,
        8'hec, 8'he2, 8'hf0, 8'hfe, 8'hd4, 8'hda, 8'hc8, 8'hc6,
        8'h9c, 8'h92, 8'h80, 8'h8e, 8'ha4, 8'haa, 8'hb8, 8'hb6,
        8'h0c, 8'h02, 8'h10, 8'h1e, 8'h34, 8'h3a, 8'h28, 8'h26,
        8'h7c, 8'h72, 8'h60, 8'h6e, 8'h44, 8'h4a, 8'h58, 8'h56,
        8'h37, 8'h39, 8'h2b, 8'h25, 8'h0f, 8'h01, 8'h13, 8'h1d,
        8'h47, 8'h49, 8'h5b, 8'h55, 8'h7f, 8'h71, 8'h63, 8'h6d,
        8'hd7, 8'hd9, 8'hcb, 8'hc5, 8'hef, 8'he1, 8'hf3, 8'hfd,
        8'ha7, 8'ha9, 8'hbb, 8'hb5, 8'h9f, 8'h91, 8'h83, 8'h8d
    };

    // ---- aes_common.x ------------------------------------------------
    localparam int unsigned MAX_KEY_BITS = 256;
    localparam int unsigned MAX_KEY_BYTES = MAX_KEY_BITS >> 3;
    localparam int unsigned MAX_KEY_WORDS = MAX_KEY_BYTES >> 2;

    localparam int unsigned KEY_WORD_BITS = 32;
    localparam int unsigned BLOCK_BITS = 128;
    localparam int unsigned BLOCK_BYTES = BLOCK_BITS >> 3;

    typedef bit [7:0] Block [4][4];
    typedef bit [7:0] Key [MAX_KEY_BYTES];
    typedef bit [KEY_WORD_BITS-1:0] KeyWord;
    typedef bit [31:0] RoundKey [4];
    typedef bit [7:0] Bytes4 [4];

    typedef enum bit [1:0] {
        KEY_128 = 0,
        KEY_256 = 2
    } KeyWidth;

    // `word as u8[4]` and `bytes as KeyWord`: element 0 most significant.
    function automatic Bytes4 word_bytes(bit [31:0] word);
        Bytes4 b;
        b[0] = word[31:24];
        b[1] = word[23:16];
        b[2] = word[15:8];
        b[3] = word[7:0];
        return b;
    endfunction

    function automatic bit [31:0] bytes_word(Bytes4 b);
        return {b[0], b[1], b[2], b[3]};
    endfunction

    function automatic KeyWord rot_word(KeyWord word);
        Bytes4 bytes = word_bytes(word);
        Bytes4 rot;
        rot[0] = bytes[1];
        rot[1] = bytes[2];
        rot[2] = bytes[3];
        rot[3] = bytes[0];
        return bytes_word(rot);
    endfunction

    function automatic KeyWord sub_word(KeyWord word);
        Bytes4 bytes = word_bytes(word);
        Bytes4 sub;
        sub[0] = S_BOX[bytes[0]];
        sub[1] = S_BOX[bytes[1]];
        sub[2] = S_BOX[bytes[2]];
        sub[3] = S_BOX[bytes[3]];
        return bytes_word(sub);
    endfunction

    function automatic Block add_round_key(Block block, RoundKey key);
        Block out;
        for (int i = 0; i < 4; i++) begin
            Bytes4 key_i = word_bytes(key[i]);
            for (int j = 0; j < 4; j++)
                out[i][j] = block[i][j] ^ key_i[j];
        end
        return out;
    endfunction

    function automatic Block sub_bytes(Block block);
        Block out;
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                out[i][j] = S_BOX[block[i][j]];
        return out;
    endfunction

    function automatic Block shift_rows(Block block);
        Block out;
        // out[i] = [block[i][0], block[i+1][1], block[i+2][2], block[i+3][3]]
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                out[i][j] = block[(i + j) % 4][j];
        return out;
    endfunction

    function automatic bit [7:0] gfmul2(bit [7:0] input_);
        bit [7:0] result = input_ << 1;
        return ((input_ & 8'h80) != 8'h00) ? result ^ 8'h1b : result;
    endfunction

    function automatic bit [7:0] gfmul3(bit [7:0] input_);
        bit [7:0] result = gfmul2(input_);
        return result ^ input_;
    endfunction

    function automatic bit [7:0] gfmul9(bit [7:0] input_);
        return GF_MUL_9_TBL[input_];
    endfunction

    function automatic bit [7:0] gfmul11(bit [7:0] input_);
        return GF_MUL_11_TBL[input_];
    endfunction

    function automatic bit [7:0] gfmul13(bit [7:0] input_);
        return GF_MUL_13_TBL[input_];
    endfunction

    function automatic bit [7:0] gfmul14(bit [7:0] input_);
        return GF_MUL_14_TBL[input_];
    endfunction

    function automatic Bytes4 mix_column(Bytes4 col);
        Bytes4 out;
        out[0] = gfmul2(col[0]) ^ gfmul3(col[1]) ^ col[2] ^ col[3];
        out[1] = col[0] ^ gfmul2(col[1]) ^ gfmul3(col[2]) ^ col[3];
        out[2] = col[0] ^ col[1] ^ gfmul2(col[2]) ^ gfmul3(col[3]);
        out[3] = gfmul3(col[0]) ^ col[1] ^ col[2] ^ gfmul2(col[3]);
        return out;
    endfunction

    function automatic Block mix_columns(Block block);
        Block out;
        for (int i = 0; i < 4; i++) begin
            Bytes4 col = mix_column(block[i]);
            out[i] = col;
        end
        return out;
    endfunction

    function automatic Block inv_sub_bytes(Block block);
        Block out;
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                out[i][j] = INV_S_BOX[block[i][j]];
        return out;
    endfunction

    function automatic Block inv_shift_rows(Block block);
        Block out;
        // out[i] = [block[i][0], block[i-1][1], block[i-2][2], block[i-3][3]]
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++)
                out[i][j] = block[(i + 4 - j) % 4][j];
        return out;
    endfunction

    function automatic Bytes4 inv_mix_column(Bytes4 col);
        Bytes4 out;
        out[0] = gfmul14(col[0]) ^ gfmul11(col[1]) ^ gfmul13(col[2]) ^ gfmul9(col[3]);
        out[1] = gfmul9(col[0]) ^ gfmul14(col[1]) ^ gfmul11(col[2]) ^ gfmul13(col[3]);
        out[2] = gfmul13(col[0]) ^ gfmul9(col[1]) ^ gfmul14(col[2]) ^ gfmul11(col[3]);
        out[3] = gfmul11(col[0]) ^ gfmul13(col[1]) ^ gfmul9(col[2]) ^ gfmul14(col[3]);
        return out;
    endfunction

    function automatic Block inv_mix_columns(Block block);
        Block out;
        for (int i = 0; i < 4; i++) begin
            Bytes4 col = inv_mix_column(block[i]);
            out[i] = col;
        end
        return out;
    endfunction

    function automatic Block xor_block(Block a, Block b);
        Block out;
        for (int i = 0; i < 4; i++)
            out[i] = word_bytes(bytes_word(a[i]) ^ bytes_word(b[i]));
        return out;
    endfunction

    // ---- aes.x -------------------------------------------------------
    localparam int unsigned MAX_NUM_ROUNDS = 14;

    typedef RoundKey KeySchedule [MAX_NUM_ROUNDS + 1];

    function automatic bit [31:0] get_num_rounds(KeyWidth key_width);
        return (key_width == KEY_128) ? 32'd10 : 32'd14;
    endfunction

    function automatic KeySchedule create_key_schedule(Key key, KeyWidth key_width);
        localparam int unsigned NUM_SCHED_WORDS = 4 * (MAX_NUM_ROUNDS + 1);
        bit [31:0] key_words = (key_width == KEY_128) ? 32'd4 : 32'd8;
        bit [31:0] round_shift = (key_width == KEY_128) ? 32'd2 : 32'd3;
        bit [31:0] sched_words = (get_num_rounds(key_width) + 32'd1) << 2;
        bit [31:0] sched [NUM_SCHED_WORDS] = '{default: 32'd0};
        bit [31:0] key_w [MAX_KEY_WORDS];
        bit [31:0] last_word = 32'd0;
        KeySchedule final_sched;

        // key as uN[MAX_KEY_BITS] as u32[MAX_KEY_WORDS]
        for (int w = 0; w < MAX_KEY_WORDS; w++)
            key_w[w] = {key[4 * w], key[4 * w + 1], key[4 * w + 2], key[4 * w + 3]};

        for (int i = 0; i < NUM_SCHED_WORDS; i++) begin
            bit [31:0] word_idx = 32'(i);
            bit a = word_idx < key_words;
            // std::mod_pow2(word_idx, key_words) is word_idx & (key_words - 1)
            bit b = word_idx >= key_words && (word_idx & (key_words - 32'd1)) == 32'd0;
            // Condition "C" is actually:
            //  word_idx > key_words && key_words > u32:6 && word_idx % key_words == 4,
            // but since we don't support 192-bit keys, we can force-mod2 the modulo.
            bit c = word_idx >= key_words && key_words > 32'd6 &&
                    (word_idx & (key_words - 32'd1)) == 32'd4;

            // Only one condition can be true, but this is a lot cleaner than an
            // if/else chain.
            bit [31:0] r_con_idx = (word_idx >> round_shift) - 32'd1;
            bit [31:0] r_con = (r_con_idx < 32'd10) ? R_CON[r_con_idx] : 32'd0;
            bit [31:0] word;
            if (a)
                word = key_w[word_idx];
            else if (b)
                word = sched[word_idx - key_words] ^ sub_word(rot_word(last_word)) ^ r_con;
            else if (c)
                word = sched[word_idx - key_words] ^ sub_word(last_word);
            else
                word = sched[word_idx - key_words] ^ last_word;

            if (!(word_idx > sched_words))
                sched[word_idx] = word;
            last_word = word;
        end

        for (int i = 0; i < MAX_NUM_ROUNDS + 1; i++)
            for (int k = 0; k < 4; k++)
                final_sched[i][k] = sched[i * 4 + k];
        return final_sched;
    endfunction

    function automatic Block encrypt(Key key, KeyWidth key_width, Block block);
        bit [31:0] num_rounds = get_num_rounds(key_width);
        KeySchedule round_keys = create_key_schedule(key, key_width);
        Block b = add_round_key(block, round_keys[0]);

        for (int round = 1; round < MAX_NUM_ROUNDS; round++) begin
            Block nb = sub_bytes(b);
            nb = shift_rows(nb);
            nb = mix_columns(nb);
            nb = add_round_key(nb, round_keys[round]);
            if (32'(round) < num_rounds)
                b = nb;
        end
        b = sub_bytes(b);
        b = shift_rows(b);
        b = add_round_key(b, round_keys[num_rounds]);
        return b;
    endfunction

    function automatic Block decrypt(Key key, KeyWidth key_width, Block block);
        bit [31:0] num_rounds = get_num_rounds(key_width);
        KeySchedule round_keys = create_key_schedule(key, key_width);
        Block b = add_round_key(block, round_keys[num_rounds]);
        b = inv_shift_rows(b);
        b = inv_sub_bytes(b);

        for (int i = 1; i < MAX_NUM_ROUNDS; i++) begin
            bit [31:0] round = num_rounds - 32'(i);
            if (32'(i) < num_rounds) begin
                b = add_round_key(b, round_keys[round]);
                b = inv_mix_columns(b);
                b = inv_shift_rows(b);
                b = inv_sub_bytes(b);
            end
        end

        b = add_round_key(b, round_keys[0]);
        return b;
    endfunction

endpackage
