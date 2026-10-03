// HAND-WRITTEN. What a user writes, on the plain-XLS path, so that the
// unchanged crc32_unit_test.sv runs against the DSLX path's RTL and netlist
// (xls-examples.md section 2.3). On the fw-hdl path all of this is generated.
//
// The test imports crc32_pkg_api_pkg and calls get(), so this package must
// provide both. DSLX has no SV types: the argument and result types are
// restated from crc32.x by hand (u8 -> bit [7:0], u32 -> bit [31:0]), and must
// be kept in step with it.
package crc32_pkg_api_pkg;

    interface class crc32_pkg_api;
        pure virtual task main(input bit [7:0] message, output bit [31:0] result);
    endclass

    crc32_pkg_api impl;     // set by the harness at time 0

    class crc32_pkg_api_proxy implements crc32_pkg_api;
        virtual task main(input bit [7:0] message, output bit [31:0] result);
            if (impl == null) #1;
            impl.main(message, result);
        endtask
    endclass

    function automatic crc32_pkg_api get();
        crc32_pkg_api_proxy p = new();
        return p;
    endfunction

endpackage
