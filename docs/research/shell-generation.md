# Shell generation: class tree → pin-level module, from an API→transactor map

*Design note, 2026-11-01. This applies to **all** fw-hdl designs, not just XLS-lowered ones.
Related: [timing-shell.md](timing-shell.md) (struct wrappers, timing shell) and
[value-adds.md](value-adds.md) (P1 signature model).*

## 1. The idea

Today a designer hand-writes the top module that puts an fw-hdl class tree on pins:
- `tests/blinky/blinky_top.sv`
- `tests/rv_proto/rv_proto_tb.sv`

It's mechanical:
1. declare pins
2. instance one transactor per edge endpoint
3. open `` `fw_root_begin ``
4. write one `` `fw_root_bind_port/export/socket/mirror `` per endpoint
5. close with `` `fw_root_end ``

Every line follows from two facts:
1. **The top class's shape:** which endpoints are left at the edge, of what kind (port,
   export, socket or mirror), with what API type and type parameters, and in which clock
   domain.
2. **An API→transactor map:** for this API and endpoint kind, which transactor module,
   interface instance and bridge class to use, and how its pins are named.

So **`fw.hdl.shell.Generate`** takes a top class plus a map and writes the module.

```
 top class (SV, via slang)          API→transactor map (YAML + self-describing kits)
          │                                        │
          └───────────► fw.hdl.shell.Generate ◄────┘
                               │
     ┌─────────────┬───────────┼──────────────┬────────────────────┐
  <top>_shell.sv  shell.json   <top>_tb_shell.sv   bind for lowering  diagnostics
  (module, pins,  (pin         (mirror xtors +     (canonical *_top   (unmapped API,
   xtors, binds)   contract)    monitors)           for fw.hdl.lower)  name clashes)
```

## 2. What exists to build on

| Piece | Where | Note |
|---|---|---|
| Bind macros for all four endpoint kinds | `src/fw_hdl_macros.svh` | Uniform bridge contract: `new(name, parent, vif)` |
| A put transactor | `src/std/fw_put_xtor_if.sv`, `fw_put_xtor_bridge.svh` | Registered beat, no handshake |
| A ready/valid kit with initiator, target and monitor (interface + core FSM + wrapper, sim + SBY) | `tests/rv_proto/` | **Hard-wired to 32 bits** and **not in `src/std`**. Needs to take `type T` |
| **Runtime bind map** listing unconnected endpoints | `fw_component_root::emit_bind_map` (`+fw_bindmap`) | Ground truth for "what is at the edge" after `connect()`, including child endpoints such as `drv.out` |
| Hard-coded protocol table used by lowering | `fe/bind/protocols.py` `STD_TRANSACTORS` ("KNOWN DEBT") | **The map replaces it.** One registry for generation *and* lowering |
| Signature-driven transactor generation (XLS) | `comp_api.xls_binding_sv` | Same job for XLS modules; merge into one emitter |

## 3. Finding the edge endpoints

There are three sources, in order of preference:
1. **Elaborate and read the bind map.** Run a zero-time elaboration of the top class with
   `+fw_bindmap`. Everything listed `unconnected` is at the edge, with its full path
   (`out`, `drv.out`, `chk.in`). It's exact, because it runs the real `build()`/`connect()`.
2. **Static: endpoints declared on the top class itself.** slang lists the `fw_port`,
   `fw_export`, `fw_socket` and `fw_mirror` members and their resolved types. It's fast and
   needs no simulator. It misses child endpoints left unbound.
3. **An explicit list** in the shell config, for partial shells or when the designer wants
   to choose.

slang resolves each endpoint's **API type**: `fw_put_if #(led_t)`,
`rv_initiator_if #(pkt_t)`, `fw_reqrsp_if #(req_t, rsp_t)`, or a user interface class.
That gives the lookup key `(API class, endpoint kind)` and the type arguments to substitute.

## 4. The map

### 4.1 Self-describing kits (default layer)
Each transactor kit declares what it serves, next to its SV, so the knowledge stays with
the transactor body. That is the "Option A" direction `protocols.py` itself asks for. The
example below uses YAML; it could also be an SV attribute on the wrapper module.

```yaml
# src/std/rv/fw_rv_kit.yaml
kit: fw_rv
transactors:
  - api: rv_initiator_if          # also serves fw_put_if via an adapter bridge (below)
    endpoint: port                # the class CALLS send()/put() -> pins driven outward
    module: fw_rv_initiator_xtor  # wrapper: interface + core FSM
    params: { T: "$T" }           # type args taken from the endpoint's API type
    if_path: u_if                 # interface instance inside the wrapper (the vif)
    bridge: fw_rv_initiator_bridge #($T)
    pins: { data: "${ep}", valid: "${ep}_vld", ready: "${ep}_rdy" }
    mirror: fw_rv_target_xtor     # what a TB uses to talk to these pins
    monitor: fw_rv_monitor_xtor
  - api: rv_target_if
    endpoint: export              # the class PROVIDES the API -> pins driven inward
    module: fw_rv_target_xtor
    ...
adapters:                          # API-to-API, so std APIs can ride any protocol
  - from: { api: fw_put_if, endpoint: port }
    to:   { api: rv_initiator_if }
    bridge: fw_put_to_rv_bridge #($T)
```

`pins` is a naming template. The wrapper's real port list is **read from the SV**
(slang), excluding clock and reset, and checked against the template. A stale map fails
the build instead of silently mis-wiring.

### 4.2 Project map (override layer)
```yaml
# shell.yaml
top: pkt_engine
defaults:
  fw_put_if: { kit: fw_rv }       # every put port becomes ready/valid
  fw_get_if: { kit: fw_rv }
  pin_style: xls                  # suffixes _vld/_rdy, matching XLS codegen
endpoints:
  csr:      { kit: fw_apb }       # this reqrsp export becomes an APB target
  irq:      { kit: fw_wire }      # single-value: a plain output pin
  dbg_out:  { omit: true }        # left unbound (sim-only)
clocks:
  core: { clock: clk, reset: rst_n, active_low: true }
  bus:  { clock: pclk, reset: presetn, active_low: true }
```

### 4.3 Resolution order
Per-endpoint override → project defaults → kit (exact API) → kit via adapter → **error**.
The error names the endpoint, its API type and the kits that came close.

## 5. What gets generated

**`<top>_shell.sv`.** For `blinky` it reproduces `blinky_top.sv`. For a ready/valid design:

```systemverilog
module pkt_engine_shell import pkt_pkg::*; (
    input  logic   clk, rst_n,
    input  pkt_t   pkt_in,  input  logic pkt_in_vld,  output logic pkt_in_rdy,
    output pkt_t   pkt_out, output logic pkt_out_vld, input  logic pkt_out_rdy
);
    fw_rv_target_xtor    #(.T(pkt_t)) u_pkt_in  (.clock(clk), .reset(!rst_n),
        .data(pkt_in),  .valid(pkt_in_vld),  .ready(pkt_in_rdy));
    fw_rv_initiator_xtor #(.T(pkt_t)) u_pkt_out (.clock(clk), .reset(!rst_n),
        .data(pkt_out), .valid(pkt_out_vld), .ready(pkt_out_rdy));

    `fw_root_begin(pkt_engine, u_root, clk, !rst_n)
        `fw_root_bind_export(pkt_in,  u_pkt_in.u_if,  fw_rv_target_bridge    #(pkt_t))
        `fw_root_bind_port  (pkt_out, u_pkt_out.u_if, fw_put_to_rv_bridge    #(pkt_t))
    `fw_root_end
endmodule
```

**`shell.json` (the pin contract).** Clock and reset, and for each endpoint: pins (name,
direction, SV type), protocol, kit and API. It is the same shape as the XLS-signature model
(value-adds P1). That buys three things:
- The **XLS RTL wrapper** for an XLS-lowered block is checked against the same contract:
  XLS streaming ready/valid matches `fw_rv` initiator/target pins when `pin_style: xls`. So
  the model shell and the XLS RTL wrapper become **one generator with two back ends**.
- Datasheet, IP-XACT, UVM agents and SVA (value-adds C6, C7, D2, D3) read the contract,
  not the SV.
- Lowering (`fw.hdl.lower`) reads a **canonical generated top** instead of tracing
  hand-written `*_top` modules. The map replaces `STD_TRANSACTORS`.

**`<top>_tb_shell.sv` (optional).**
- A **mirror** harness: for each endpoint, the kit's mirror transactor on the same pins
  (initiator ↔ target), plus a monitor.
- The result is a pin-level, self-checking loopback against the class model. It can also
  serve as a ready-made TB front end that exposes the mirror APIs to a test.
- The monitors feed the transaction recorder (value-adds P3).

## 6. Where it can't be fully automatic (the "many cases" boundary)

| Case | Handling |
|---|---|
| API with no kit or adapter | Error listing the endpoint, API and nearest kits. Offer `omit` or a user kit |
| One transactor serving several endpoints (e.g. a bus with request and response APIs, or a socket bundle) | Kit entry with `endpoints: [a, b]` grouping. Sockets and mirrors already pair both directions in one bind |
| Multiple clock domains | Each endpoint's domain comes from its component's `clock` port. The map assigns a clock and reset per domain, and the generator emits clock transactors (`fw_clock_xtor`) per domain |
| Exact pin names imposed from outside (an XLS signature, an existing RTL port list) | `pin_style` or per-endpoint `pins:` override; checked by the pin-parity check |
| Static/config pins | A `fw_wire` kit for single-value APIs; `fw_reg`/CSR kits for register access (value-adds C3) |
| Several shells in one sim, each with its own `fw_root` | **Verify.** `fw_root_begin` can't be nested within one module, but separate shell modules each own a root. Multiple roots per sim need a test |
| Transactor with parameters beyond `T` (address width, ID width) | Kit `params` templates bind them from the API's type args or from project config |

## 7. Plan

| Step | Deliverable | Status of inputs |
|---|---|---|
| S1 | Move `rv_proto` into `src/std/rv/` and parameterize it on `type T` (it's 32-bit today); add the `fw_put_if`→rv adapter bridge | Kit works and has SBY proofs |
| S2 | Kit descriptor format, with `fw_put` and `fw_rv` described; slang reader for the wrapper port lists | — |
| S3 | `fw.hdl.shell.Generate` (dfm task + CLI): static edge discovery, map resolution, emits `<top>_shell.sv` + `shell.json` | Regenerating `blinky_top.sv` is the first golden test |
| S4 | Bind-map edge discovery (elaborate with `+fw_bindmap`) | Runtime support exists |
| S5 | `pin_style: xls` plus the pin-parity check against the XLS signature. The XLS RTL wrapper reuses the emitter | `comp_api.xls_binding_sv`, `zuspec.xls.Signature` |
| S6 | TB mirror shell plus monitors | Kit `mirror` / `monitor` fields |
| S7 | Switch `fw.hdl.lower` from `STD_TRANSACTORS` to the kit registry | Retires the "KNOWN DEBT" table |

S1–S3 give the first visible win: no more hand-written tops. S5 joins it to the XLS
commercial path. S7 pays down an existing debt with the same registry.
