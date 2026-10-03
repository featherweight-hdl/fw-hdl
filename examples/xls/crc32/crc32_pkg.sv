// Derived from XLS xls/examples/crc32/crc32.x (see orig/), Copyright 2020 The
// XLS Authors, Apache-2.0 (see ../NOTICE). A line-for-line port to the fw-hdl
// static subset; README.md lists the deviations.

// Performs a table-less crc32 of the input data as in Hacker's Delight:
// https://www.hackersdelight.org/hdcodetxt/crc.c.txt (roughly flavor b)

package crc32_pkg;

    localparam bit [31:0] U32_MAX = 32'hFFFF_FFFF;  // std::unsigned_max_value<u32:32>()

    function automatic bit [31:0] crc32_one_byte(bit [7:0] byte_, bit [31:0] polynomial,
                                                 bit [31:0] crc);
        crc = crc ^ 32'(byte_);
        // 8 rounds of updates.
        for (int i = 0; i < 8; i++) begin
            bit [31:0] mask = -(crc & 32'd1);
            crc = (crc >> 1) ^ (polynomial & mask);
        end
        return crc;
    endfunction

    function automatic bit [31:0] main(bit [7:0] message);
        return crc32_one_byte(message, 32'hEDB88320, U32_MAX) ^ U32_MAX;
    endfunction

endpackage
