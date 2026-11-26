// wb_api_pkg: the Wishbone transaction-level API alone, with no fw-hdl
// dependency, so class code outside fw-hdl (a UVM environment, a plain
// bridge) can use it. wb_pkg imports and exports it.
`include "wb_macros.svh"

package wb_api_pkg;
    `include "wb_if.svh"
endpackage
