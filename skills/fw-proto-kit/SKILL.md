---
name: fw-proto-kit
description: Build a Featherweight-HDL protocol kit — an SV package that declares a protocol
  (its method-level APIs, its pin-level bundles, its payload types), from which fw-hdl-fe-sv's
  GenKit dfm task generates the rest (proxies, listeners, transactions, pin maps, ready/valid
  transactors and monitors). Use when creating or extending an fw-hdl protocol/transactor
  package (ready/valid, wishbone, AXI…); the std ready/valid protocol in fw-hdl-spec std/ is the
  reference.
---

# Featherweight-HDL Protocol Kit

A protocol kit joins everything about one interface standard: the class-level
**APIs** that model it, the **bundles** that are its pin-level forms, and the
**transactors** that convert between the two. A component written against the
API never touches pins; the transactor does.

You write only the kit's *source*: the protocol class, its APIs, its payload
types and its bundles, in one SV package. Everything else is derived by a
generator, fw-hdl-fe-sv's `GenKit`, into one package `<pkg>_gen_pkg`. Do not
hand-write proxies, listeners, transaction classes, pin maps or ready/valid
transactors; if the generator cannot derive something you need, that is a
generator gap to report, not code to write in the kit.

Read alongside this guide:

| What | Where (under `packages/`) |
| --- | --- |
| The guide (protocol hub, bundles, sockets, what is generated, transactors, abstractors, timed channels) | `fw-hdl-spec/docs/protocols.rst` |
| The normative rules and "Derived shapes" | `fw-hdl-spec/semantics/protocols.md` |
| API reference | `fw-hdl-spec/docs/api/protocols.rst` |
| The reference protocol: ready/valid | `fw-hdl-spec/std/fw_rv_proto.svh` (protocol), `fw_rv_if.svh` (bundle), `fw_rv_xtor.svh` (initiator, target, monitor) |
| A kit whose bundle is a bundle of channels | `fw-hdl-fe-sv/tests/unit/gen/src/proto_chan/top.sv` |
| Wrapping existing RTL whose ports are ready/valid bundles | `fw-hdl-fe-sv/examples/wrap_rtl/` (README.md) |
| GenKit through dfm | `fw-hdl-fe-sv/tests/e2e/test_genkit_flow.py` |
| Generated testbench and monitors on wrapped RTL | `fw-hdl-fe-sv/tests/e2e/test_gen_tb.py`, `test_gen_bind.py` |

## What you write

1. **The protocol** — a class extending `fw_protocol` with only static members.
   Its `declare()` registers the APIs, at most one per direction. A parameterized
   protocol declares `this_t` and uses `` `fw_protocol_param_utils ``:
   ```systemverilog
   class axi4_proto #(int AW = 32, int DW = 32) extends fw_protocol;
       typedef axi4_proto #(AW, DW) this_t;
       `fw_protocol_param_utils(axi4_proto)
       static function void declare(fw_protocol_decl d);
           d.api(fw_api_type_of #(axi4_mem_if #(AW, DW))::get(), FW_PROTO_REQ);
       endfunction
   endclass
   ```
   Derived names start with the family name less a trailing `_proto` (`axi4`);
   set another with `d.prefix("...")`. Never write names as strings.

2. **The APIs** — ordinary interface classes (see the **fw-api-kit** skill). An
   API cannot register itself; the protocol registers it, and one API may belong
   to many protocols.

3. **Payload types** — packed structs per channel payload. The generator derives
   `sprint`, `compare` and `mask` for them (`<p>_payloads`).

4. **The bundles** — each names its protocol with `` `fw_bundle_protocol ``, and
   is written from the initiator's view. A protocol may have several bundle
   forms. For a handshaked protocol, make the bundle a **bundle of channels**:
   one `fw_rv_if` member per channel, `fw_bundle` for a channel the initiator
   drives, `fw_mirror` for one it receives:
   ```systemverilog
   virtual class test_ch_bundle #(int W = 8) extends fw_bundle_base;
       `fw_bundle_protocol(test_ch_proto #(W))
       fw_bundle #(fw_rv_if #(logic [W-1:0])) req;   // initiator -> target
       fw_mirror #(fw_rv_if #(test_ch_rsp_t)) rsp;   // target -> initiator
       ...
   endclass
   ```

## What is generated

`GenKit` scans the kit and writes `<pkg>_gen_pkg.sv` (it imports `fw_hdl_pkg`
and your package). For API `<api>`, method `<m>`, prefix `<p>` it derives:
`<p>_req_if`/`<p>_rsp_if` (one task per channel), `<api>_base`, `<api>_listener`
(`<m>_pre`/`<m>_post`) with base and fan-out, `<api>_proxy`, `<api>_imp`,
`<api>_txn`/`<api>_<m>_txn`/`_txn_sink`/`_txn_listener`/`_txn_driver`,
`<p>_payloads`, `<p>_pins` (`flat(m, b, pre)`: the AXI-style pin map), and —
for a bundle whose channels are all `fw_rv_if` — the transactors `<p>_initiator`,
`<p>_target` and `<p>_monitor`, built from the std `fw_rv_initiator`,
`fw_rv_target` and `fw_rv_monitor` per channel and registered with the protocol.
The full table is in `protocols.rst`, "What is generated".

In a flow, after the kit's `fwHdlSource` FileSet:
```yaml
- name: kit
  uses: std.FileSet
  with: {type: fwHdlSource, base: src, include: [axi4_pkg.sv]}
- name: kit-gen
  uses: fw.hdl.fe.sv.GenKit        # optional: pkg_name
  needs: [kit]
```
It re-runs when its inputs or the generators change. `fw.hdl.fe.sv.Scan` writes
the protocol table alone (`scan.json`, `scan.zir`). From Python:
`gen_kit(scan([...], incdirs=[...]))` (`fw.hdl.gen`, `fw.hdl.fe.sv.scan`).

## Decomposing a protocol into channels

Before writing the bundle, split the protocol into its **independent activity
streams**: each direction with its own valid/ready (or req/ack) that advances on
its own is one channel. Each channel becomes one `fw_rv_if` member of the bundle,
one task of the derived channel API, and one std transactor in the generated
initiator/target/monitor; channels pipeline independently.

- **Ready/valid**: one channel. The std `fw_rv_proto` is the whole kit.
- **Wishbone**: a request and a response phase → `req` + `rsp` channels.
- **AXI**: five channels — AW, W, B, AR, R. Channels that are logically coupled
  (W follows AW; B completes the write) stay separate channels; a higher-level
  API method (`write()`) composes them in an adapter (below).

A protocol whose pins are not a bundle of ready/valid channels (a UART line, a
bus sampled every cycle) needs a hand-written transactor: a component with an
endpoint on one side and a bundle on the other, registered with
`` `fw_xtor_utils(<xtor>, <proto>) `` (see `protocols.rst`, "Transactors", and
`fw_rv_xtor.svh` for the shape). Its role is not stated: the bundle mixin gives
it. A monitor is a transactor whose pins are an `fw_monitor` and whose class side
is a list of listeners.

## Adapters: higher-level APIs over the protocol API

The channel APIs express the protocol's own vocabulary. An **adapter** is a
plain component that provides a higher-level API (an export) and holds a port to
the lower one; its methods translate one high-level call into calls on the
channels. It adds no transactor and no pins, and adapters stack (burst over
single-beat). The big win is a protocol-independent API (`fw_mem_if`:
read/write): write models and tests against it, and pick a protocol by choosing
its adapter. When the abstract level is itself a protocol (packets over a byte
PHY), the adapter is an *abstractor*, registered with both protocols by
`` `fw_abstractor_utils `` (`protocols.rst`, "Abstractors").

## Rules

1. **Declare only; derive the rest.** The kit source is protocol + APIs +
   payloads + bundles. No names as strings; no hand-written proxies, pin maps or
   rv transactors.
2. **Parameterize the protocol, not the pieces.** Width parameters live on the
   protocol and bundle (`#(int W)`); connection checks and transactor choice key
   on the specialization, generators and naming on the family.
3. **Timing is a channel, not a transactor.** A method-level link that should
   take wire time (a UART character time) gets an explicit
   kit channel extending `fw_timed_channel` between the endpoints
   (`protocols.rst`, "Timing"); elaboration never inserts one.
4. `checker` is a reserved SV keyword — don't name a class `checker`.

## Testing a kit

- **Back to back, no RTL.** A generated initiator and target run back to back
  by connecting their `pins` directly. Drive traffic through the initiator's API
  against a model behind the target's API, exercise backpressure on both sides
  and every response variant, and attach a listener to the monitor to check it
  sees every beat. `fw-hdl-fe-sv/tests/unit/gen/src/proto_chan/xtor_b2b.sv` is
  the shape.
- **Against RTL.** Wrap the RTL (`examples/wrap_rtl`; `<p>_pins::flat` makes the
  extern map one line), elaborate and emit it, and let `gen_tb` generate the
  testbench (the opposite-role transactor per DUT port) and `gen_bind` the bound
  monitors (`fw.hdl.gen.tb`, `fw.hdl.gen.bind`). The user writes a subclass whose
  `run()` puts and gets.
- **Formal.** Write protocol invariants as synthesizable checkers on the RTL
  (handshake stability, no phantom transfer, ordering and integrity with an
  `(* anyconst *)` index, framing). Immediate asserts with `$past`, guarded by an
  `f_past_valid` reg; a `cover` per property; and always confirm the proof has
  teeth by injecting a bug. `fw-hdl-fe-sv/tests/e2e/sv/rv_formal.sv` proves the
  lowered std `fw_rv_mon_core` this way (sby setup in the **sby** skill).
