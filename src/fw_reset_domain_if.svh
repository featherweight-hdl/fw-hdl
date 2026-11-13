// The reset-domain API: the second domain kind (fw_domain_if), with the same
// shape as the clock domain (docs/reference/clocking.md, "Reset domains").
//
// A component consumes its reset domain through its `reset` port
// (fw_reset_port), inherited from the parent when the parent's is bound. An
// unbound `reset` is legal and means "never in reset".
//
//   in_reset()      -- the level, readable at any time (a pure read of a pin, a
//                      register bit, or other domains; lowers to logic).
//   wait_assert()   -- returns at the first tick of sync_clock() at which the
//                      domain is in reset, or at once if it already is.
//   wait_deassert() -- likewise for out of reset.
//   is_async()      -- assertion may happen between edges of sync_clock().
//   sync_clock()    -- the clock deassertion is aligned to; null: none.
//
// Like tick(), the waits are exact in timed code and a lower bound in untimed
// code. Polarity does not exist inside the tree: a domain is "in reset" or
// not; a device's active-low pin is inverted where it enters the root.
(* fw_latency_insensitive *)
interface class fw_reset_domain_if extends fw_domain_if;
    pure virtual function bit                in_reset();
    pure virtual task                        wait_assert();
    pure virtual task                        wait_deassert();
    pure virtual function bit                is_async();
    pure virtual function fw_clock_domain_if sync_clock();
endclass

typedef fw_domain_port #(fw_reset_domain_if, FW_DOMAIN_RESET) fw_reset_port;
