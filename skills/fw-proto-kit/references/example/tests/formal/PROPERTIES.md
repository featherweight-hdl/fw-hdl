# Ready/valid kit — invariant properties → synthesizable checkers

This is the worked "spec → invariants → checkers" mapping for the ready/valid
kit (see the SKILL section *"From spec to checkers"*). Every row is implemented in
`rv_proto_fv.sv`, inside the `` `ifdef FORMAL `` block, and proven by
`dfm run rv.proto.formal.fv`.

The ready/valid spec, in one breath:
> A beat transfers on a cycle where `valid && ready`. The source must keep
> `valid` asserted and `data` held stable from the cycle it first asserts `valid`
> until the cycle the sink accepts. Beats are delivered in the order issued; none
> are lost, duplicated, or corrupted.

| # | Spec statement | Invariant class | Checker in `rv_proto_fv.sv` |
| --- | --- | --- | --- |
| 1 | source holds `valid`/`data` until accepted (bus side) | handshake stability | `$past(bus_valid) && !$past(bus_ready)` ⇒ `bus_valid && $stable(bus_data)` |
| 2 | same rule on the target's up-link (link side) | handshake stability | `$past(t_up_valid) && !$past(snk_ready)` ⇒ `t_up_valid && $stable(t_up_data)` |
| 3 | a beat moves only on `valid && ready` | no phantom transfer | transfer events (`in_xfer`, `out_xfer`) are *defined* as `valid && ready`; counters advance only on them |
| 4 | beats delivered in order, none lost/duplicated/corrupted | ordering + conservation/integrity | anyconst `f_idx`: capture the `f_idx`-th `in_xfer` payload; `assert` the `f_idx`-th `out_xfer` payload equals it (and that it had entered: `f_have`) |

Reachability / non-vacuity: a `cover` that the tracked beat actually traverses the
pair end to end (`out_xfer && out_cnt == f_idx && f_have`).

Building blocks used (both synthesizable): `$past`/`$stable` (shadow registers,
require `read_verilog -formal`) and the `(* anyconst *)` free-flowing index
tracker (plain counters + comparisons).

## Extending to a richer protocol
Keep this table per kit; each new protocol adds rows that become one more checker:
- **Wishbone**: + *framing* (`ack` only within an active `cyc && stb` cycle) and
  + *range* on any pipelined outstanding-transfer count.
- **AXI**: + *framing* per burst (`RLAST` after exactly `ARLEN+1` beats; no `R`
  without an outstanding `AR`) and + *ordering per ID*. Replicate the source/sink
  + integrity tracker once per channel (each channel is its own ready/valid
  stream).
