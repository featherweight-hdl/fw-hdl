// The plain bench's class code (T4c, docs/design/xtor-shell-plan.md): a
// driver and a memory on the Wishbone API alone. No fw-hdl: it imports
// only wb_api_pkg.
package wb_plain_tb_pkg;
    localparam int N = 40;     // accesses: N/2 writes, then N/2 reads

    `include "drv_c.svh"
    `include "mem_c.svh"
endpackage
