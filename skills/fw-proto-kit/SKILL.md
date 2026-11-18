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

A protocol kit (protocol package) joins everything about one interface standard: the
class-level **APIs** that model it, the **bundles** that are its pin-level forms, and the
**transactors** that convert between the two. You write the source (protocol, APIs, payload
structs, bundles) in one SV package; fw-hdl-fe-sv's `GenKit` derives the rest into
`<pkg>_gen_pkg`. Never hand-write what GenKit derives; a missing derivation is a generator
gap to report.

## Read the guide first

The how-to is **`packages/fw-hdl-spec/docs/protocol-packages.rst`** and its pages under
`docs/protocol-packages/`. Follow it step by step; this skill only orients you.

| Step | Page (under `packages/fw-hdl-spec/docs/`) |
| --- | --- |
| 0. Fit check (channels, roles, config, timing, known limits) | `protocol-packages.rst` |
| 1–3. Package, payload structs, APIs, protocol (`declare()`, `this_t`), bundles of channels | `protocol-packages/declare.rst` |
| 4. GenKit (dfm task and Python), compile order, every generated class and how to use it | `protocol-packages/generate.rst` |
| 5. Adapters, reference model, endpoints/sockets, hand-written transactors, configuration, timed channels, abstractors | `protocol-packages/behaviour.rst` |
| 6–7. Back to back, static elaboration, against RTL (wrap, emit, testbench, bind monitors), formal, reference IPs | `protocol-packages/testing.rst` |
| Diagnostics, known limits, checklist | `protocol-packages/reference.rst` |

Reference material the guide links to: `docs/protocols.rst` (hub, sockets, transactors,
abstractors, configuration, timing, generated testbenches), `semantics/protocols.md`
(normative rules, derived shapes), `docs/wrapping.rst`, `docs/domains.rst`.

## The worked example

`packages/fw-hdl-spec/docs/examples/sbus/`: a two-channel request/response bus, carried
through every step. Copy its layout for a new kit:

- `src/sbus_pkg.sv` (the whole hand-written source), `flow.yaml` (GenKit, Scan),
  `src/sbus_behav_pkg.sv` (adapters, model), `tb/sbus_b2b.sv` + `tb/sbus_b2b_top.sv`
  (back to back), `rtl/`, `src/sbus_wrap_pkg.sv`, `tb/sbus_rtl_tb.sv` (against RTL).
- `direnv exec . python packages/fw-hdl-spec/docs/examples/sbus/check.py build/sbus`
  generates, builds and runs all of it in Verilator, and elaborates the b2b top in fe-sv.

Also: std ready/valid (`fw-hdl-spec/std/fw_rv_*.svh`), fw-hdl-fe-sv
`tests/unit/gen/src/proto_chan/` (parameterized bundle of channels),
`fw-hdl-spec/conformance/_lib/test_uart_*.svh` (plain-signal pins, config, timed
channels), fw-hdl-fe-sv `examples/wrap_rtl/` (gen_tb/gen_bind on std rv ports).

## Rules that bite (details in the guide)

1. **One package** for all APIs and payload structs (`FW-E-GEN-PKG` otherwise).
2. **Payload structs**: package-level, `bit` members, no channel prefix on member names.
   A `logic` member silently loses the helpers and field pins; widths cannot follow a
   parameter (use a non-struct `logic [W-1:0]` payload for that).
3. **Bundle of channels**: one `fw_rv_if` member per channel, `fw_bundle` = initiator
   drives, `fw_mirror` = target drives. Only such bundles get generated transactors;
   plain-signal bundles need a hand-written `` `fw_xtor_utils `` transactor.
4. **Parameterized classes** need `this_t` + the `_param_utils` macro, and a specialization
   named in the scanned source (a typedef), or GenKit silently skips the bundle.
5. **Timing is a channel** (`fw_timed_channel`) the user places; config is a struct on
   endpoints (`fw_cfg_src`/`fw_cfg_sink`), never on the protocol.
6. `gen_tb`/`gen_bind` work for std ready/valid DUT ports only; for a bundle of channels
   write the bench by hand like `tb/sbus_rtl_tb.sv`.
7. Don't name a class `checker` (SV keyword), or a channel `pins`, `s`, `p`, `t`.

Check the guide's "Known limits" table before designing around `fw_opt` (optional
fields), 4-state payloads, struct-valued parameters, `abstractor_for` in fe-sv, or
Yosys/SBY on lowered type-parameterized classes.
