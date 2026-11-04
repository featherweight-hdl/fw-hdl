
// Featherweight standard protocol library -- the std layer on top of the
// fw_hdl_pkg kernel. fw_hdl_pkg supplies the deferred-binding mechanism
// (fw_component / fw_port / fw_export / clock domain); this package supplies the
// reusable, transaction-level protocol APIs that ride over it: put/get (no
// handshake), request/response, and the put transactor bridge.
//
// SystemVerilog packages don't nest, so this separate package -- imported
// alongside fw_hdl_pkg -- is how the kernel/std-library layering is expressed.
// One-way dependency: fw_std_pkg imports fw_hdl_pkg, never the reverse.
package fw_std_pkg;
    import fw_hdl_pkg::*;

    // Transaction-level protocol APIs (interface classes).
    `include "fw_put_if.svh"      // put(t)            -- write to an output, no handshake
    `include "fw_get_if.svh"      // get(t)            -- sample an input, no handshake
    `include "fw_get_nb_if.svh"   // + try_get(t)      -- poll an input (opt-in; not KPN)
    `include "fw_put_step_if.svh" // + put_or_stall(t) -- put from an all-or-nothing step
    `include "fw_valid_put_if.svh" // put(t), a function -- valid only: never waits (credits)
    `include "fw_level_if.svh"    // get() / set(t)    -- a level: no handshake
    `include "fw_reqrsp_if.svh"   // call(out, in)     -- blocking request/response
    `include "fw_mem_if.svh"      // read/write(addr)  -- protocol-independent memory access

    // Signal-level bridge for the put protocol: holds a virtual
    // fw_put_xtor_if (a separate compilation unit) and implements fw_put_if.
    `include "fw_put_xtor_bridge.svh"

    // Joins a put port to a get port: a FIFO (DEPTH >= 1) or a rendezvous
    // (DEPTH == 0) between two components.
    `include "fw_channel.svh"

    // The other two channel kinds: valid-only (the producer never waits) and
    // a level (a wire in RTL).
    `include "fw_valid_channel.svh"
    `include "fw_level_channel.svh"

    // A FIFO with packed storage and one writer per side, which lowers:
    // count, peek and flush for designs (fw_channel does not lower).
    `include "fw_fifo.svh"

    `include "fw_reg_component.svh" // a register block as a child: write stream in, levels out

    // Library classes the registry recognizes (fw.hdl.lib): the bodies are models.
    `include "credit/fw_credit_tx.svh" // credit-gated sender, valid-only out
    `include "arb/fw_arbiter.svh"      // N-input arbiter, {index, value} out
    `include "table/fw_keyed_table.svh" // keyed table: install, lookup, write, remove
    `include "pool/fw_token_pool.svh"   // lowest free token; put back
    `include "pool/fw_slot_reserve.svh" // reserve k slots, free on release
    `include "dep/fw_dep_tracker.svh"   // dependents wait for the youngest older producer
    `include "match/fw_match_set.svh"   // equality over the valid slots of a set (functions)

endpackage
