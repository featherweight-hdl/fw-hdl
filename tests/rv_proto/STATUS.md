# fw-hdl interface/protocol work — session status (2026-06-20)

Handoff for restart. Read this first.

## TL;DR
- The API layer + deferred-binding wrappers + the `intf_pc` test all WORK and pass.
- `rv_proto` now **PASSES** with the FULL three-component transactor structure
  (transactor-interface + clocked core FSM + wrapper) per role. The earlier
  blocker is RESOLVED. Pending decision below is moot.
- The fix (see "RESOLUTION" section): every interface/module is CLOCKED, and the
  interface<->core link is ALWAYS a plain ready/valid channel driven by a real
  clocked FSM (NOT a bare registered passthrough). The core never adopts the
  external protocol's language.

## RESOLUTION (2026-06-20, restart) — rv_proto now PASSES
Two things, both now captured in the `rv_proto_tb.sv` file header:
1. **Everything must be clocked.** In this Verilator flow a module/core output
   is only reliably observed by another block's clocked sampling when it is
   REGISTERED. A combinational drive into an interface input port is lost to a
   delta-cycle race (both-combinational cores => target/initiator interfaces read
   their input ports as 0 even though the bus shows valid&&ready => TIMEOUT).
   Both `_core` modules stay clocked `always @(posedge clock)` FSMs — which is
   realistic anyway (a real protocol core has an FSM).
2. **The interface<->core link is ALWAYS a plain ready/valid channel, driven by
   a real clocked FSM — not a bare registered passthrough.** The link NEVER
   adopts the external protocol's language. A registered passthrough merely
   DELAYS the signals; the round-trip latency let the target re-sample a beat the
   initiator had not yet advanced past => DUPLICATED beats (received
   cafe0000,cafe0000,cafe0001…). A proper ready/valid handshake transfers exactly
   one beat per (valid && ready) cycle on each side. Result: 8 beats, exactly
   once, in order, ~20ns/beat.

Link signals (both roles): `up_valid`/`up_data`/`up_ready` ("up" = the link up
toward the transactor-interface/API). The interface is the ready/valid producer
(initiator send) or consumer (target recv); the core is the opposite endpoint on
the link and the protocol endpoint on the pins. Core FSMs: initiator
ACCEPT→DRIVE, target ACCEPT→PRESENT (1-deep skid). Debug `$display`s removed;
watchdog `#100us`.

3. **PIPELINING — FIFO inside the xtor_if.** Each transactor-interface holds a
   DEPTH-deep SV-queue FIFO. `send()`/`recv()` only touch the FIFO (send blocks
   only when full, recv only when empty); a clocked always block drains/fills the
   FIFO across the ready/valid link. So the caller runs ahead by up to DEPTH beats
   and is NOT serialized by the link/bus round-trip (driver queues 4 beats at
   t=35ns, then paces with the drain). Tasks poll on `@(posedge clock)` rather
   than `wait()` (robust against queue-mutation sensitivity in Verilator).
   - **Parameterize symmetrically or not at all.** A parameter on the interface
     mangles its type (`rv_initiator_xtor_if__D4`), so every element naming it (vif
     handle, bridge, wrapper) must carry the same parameter. Asymmetry — a
     `#(.DEPTH(4))` instance bound to a plain `virtual rv_initiator_xtor_if` — gives
     "expected ... interface but ... is a different interface". DEPTH is a fixed
     protocol property, so it's an internal localparam (no parameter to thread).

## What works (passing)
- `src/`: `fw_if_base.svh`, `fw_export.svh`, `fw_port.svh` (deferred-binding
  wrappers; `connect()` records the link, `get_if()` resolves lazily through the
  graph to the imp). `fw_component`, `fw_bind` unchanged. `fw_put_xtor_if.sv`
  got `parameter type T = int` default (so testbenches that don't instantiate it
  still elaborate).
- `tests/intf_pc/intf_pc_tb.sv` — **PASSES**. Self-contained: defines the `send`
  protocol inline (interface class `fw_send_if` + `\`FW_SEND_IMP` macro), with
  `producer` (port), `consumer` (export via macro), `pc_top` whose `connect()`
  does `prod.out.connect(cons.in)`.
- `skills/fw-api-kit/SKILL.md` — elaborated: two application modes (interface
  class already defined vs informal spec), conventions, and a Checking/
  Validation section whose first/mandatory check is "an implementation macro
  exists for the API."
- `skills/fw-proto-kit/SKILL.md` — describes roles (initiator=export provider,
  target=port consumer, monitor) and the per-role elements (API interface-class,
  core transactor module, transactor-interface, transactor module, bridge class).

## Conventions locked in
- **API = interface class `<proto>_if` + `\`FW_<PROTO>_IMP` macro.** EVERY API
  ships a macro; EVERY implementation MUST use it (never hand-roll the fw_export
  proxy). Macro proxy: `extends fw_export #(<api>)` AND `implements <api>`;
  `new(IMP imp)` does `super.new(\`"NAME\`", imp, this); m_imp = imp;`; each API
  method `m` redirects to `m_imp.NAME``_m`. Macro ends with member decl
  `NAME``_imp_t NAME`, so **the macro call needs a trailing `;`**.
- **Providers** (implement an API) use the macro to expose an export member;
  **consumers** hold an `fw_port`. `port.connect(export)`; also export→export
  (forward) and port→port (inner up to outer). Resolution is lazy via `get_if()`.
- **proto-kit roles:** initiator PROVIDES an export (passive — driven when its
  method is called); target IS a port (active — samples and calls `put()` into
  the connected component, which implements the API).
- **Gotcha:** `checker` is a reserved SV keyword (checker/endchecker). Don't name
  a class `checker` (used `sink`).
- Build/run: `export IVPM_PACKAGES=/home/mballance/projects/featherweight-hdl/fw-wb-dma/packages;
  export PATH=$IVPM_PACKAGES/python/bin:$IVPM_PACKAGES/verilator/bin:$PATH;
  dfm run fw-hdl.rv_proto.rv-proto`. Sim stdout: `rundir/<task>/sim.log`.
  Verilator `--timing` is on (`@`/`#` work).

## rv_proto: the blocker (Verilator limitations, confirmed by experiment)
Goal was the full three-component structure per role: a transactor-interface
(`rv_*_xtor_if`, API methods ⟷ internal FIFO handshake), a core transactor
module (`rv_*_xtor_core`, FIFO ⟷ pins; passthrough for RV), and a transactor
module (`rv_*_xtor`) wiring them. Findings:

1. **Parameterized interface ports → Verilator internal error**:
   `../V3Param.cpp:523: Couldn't find pin in clone list` for
   `rv_initiator_xtor_if #(T) fifo`. Workaround: drop the `#(T)` on the port.
2. **A module driving an interface signal through an interface port does not
   propagate.** With `assign fifo.f_ready = ready;` in the core, the design-side
   `init_if.f_ready` stays 0 even though `bus_ready` is 1. Proven with a
   hierarchical probe:
   `[BUS design-view] init.f_ready=0 init.f_ready_s=0 bus_ready=1 @ 55000`.
   So the transactor-interface's `send()` never observes `ready`. (The vif reads
   were actually correct — the signal genuinely wasn't driven.)
3. Earlier I also suspected vif can't read externally-driven signals; the real
   issue is (2) — the external drive never reaches the interface signal.

Net: the clean iface + **separate core MODULE** split does not run under this
Verilator (5.049). Module reads of interface signals through a port DO work
(`assign valid = fifo.f_valid` propagated); module WRITES to interface signals
through a port do NOT.

## The WORKING rv_proto (single transactor-interface) — restore this for option 1
One interface holds the handshake; both API methods are tasks that drive/read
its INTERNAL signals (so everything the tasks read is driven by a task — no
external drives, no separate core module):

```
interface rv_xtor_if #(parameter type T = logic[31:0]) (input logic clock, input logic reset);
    logic valid = 0; logic ready = 0; T data = 0;
    task automatic send(input T t);
        data <= t; valid <= 1;
        do @(posedge clock); while (ready !== 1);
        valid <= 0;
    endtask
    task automatic recv(output T t);
        ready <= 1;
        do @(posedge clock); while (valid !== 1);
        t = data; ready <= 0;
    endtask
endinterface
```
- One `rv_xtor_if #(data_t) u_xtor(.clock,.reset)`. BOTH bridges hold `vif=u_xtor`.
- `rv_initiator_bridge`: `extends fw_component`, `\`FW_RV_INITIATOR_IMP(T, rv_initiator_bridge #(T), exp);`,
  `exp = new(this)` in new(), `exp_send(t)` → `vif.send(t)`.
- `rv_target_bridge`: `extends fw_port #(rv_target_if #(T))`, `run()` loop:
  `#17ns; vif.recv(t); get_if().put(t);` (the #17ns gives backpressure).
- `rv_top`: `vif=u_xtor`; `connect()` builds ibr+tbr, `drv.out.connect(ibr.exp);
  tbr.connect(chk.in);`.
- `initial`: reset; `fork top.tbr.run(); join_none  top.drv.run();`
  `while (top.chk.received.size() < N) @(posedge clock);` then check → PASS.
- Result: `[rv_proto] PASS`, 8 beats, 20ns/beat backpressure cadence.

The API interface-classes (`rv_initiator_if` send / `rv_target_if` put), the two
`\`FW_RV_*_IMP` macros, `driver`, `sink` (uses `\`FW_RV_TARGET_IMP(data_t, sink, in)`,
implements `in_put`) are all correct and reusable across either structure.

## PENDING DECISION (asked, user chose to restart instead of answering)
How should rv_proto land?
 1. **Revert to the working single transactor-interface** (recommended). For RV
    the separate core is a functional no-op; document the 3-component split as
    the production structure for full simulators (Questa/VCS/Xcelium) where
    interface-port drives and vifs work. CI green.
 2. Keep the 3-component code as a non-running reference; mark the test
    xfail/skip so CI isn't red. Nothing verifies in this Verilator flow.
 3. Push for a Verilator workaround — e.g. concrete (non-parameterized) types to
    dodge the interface-port bugs, or change how the core couples to the
    interface. More time, uncertain.

## Immediate cleanup needed in rv_proto_tb.sv regardless of choice
- Remove `$display("[DBG send task-view] ...")` in the initiator interface send.
- Remove the `[BUS design-view]` probe `initial` block.
- Remove the `f_ready_s` / `f_valid_s` / `f_data_s` sampling regs + always blocks
  (debugging artifacts).
- Restore watchdog to `#100us` (currently `#400ns`).
