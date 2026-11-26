# Task↔sync crossings: fw_to_sync and fw_from_sync

Task code (`run()`, `access()`, any blocking call) and sync code (`step()`,
`comb()`) meet only through two purpose-built constructs, one for each
direction (names decided 2026-11-21, §2):

- `fw_to_sync #(T)` carries items from task code into sync code;
- `fw_from_sync #(T)` carries items from sync code out to task code.

Each one has two **sides**:
- a **process side**, used by task code, with blocking calls;
- a **sync side**, used by `step()` and `comb()`, with non-blocking functions.

A change of state from the process side re-evaluates the sync and comb code
of the containing scope. A put on the process side, or a get starting to
wait, is visible to `comb()` straight away.

## User benefit

- **A transactor is sync code plus two crossings.** `access()` is
  `req.put(r); rsp.get(p);`. All the protocol timing is in `step()` and
  `comb()`, which lower to RTL and can be checked formally. There's no
  `run()` thread, no `tick` in transactor code, and no C5 defaults to
  override.
- **No timing cost.** A request put at edge *k* is on the pins for edge
  *k* + 1, and a back-to-back call keeps it there with no idle cycle. That's
  the same timing as today's `run()` transactors, without their thread.
- **The crossing has a direction and a type.** The direction of data and
  who blocks are in the declaration, so the front end can check each side's
  use and lower the sync side to ready/valid ports.

## 0. Status

| Step | State |
|---|---|
| Design (this doc) | 2026-11-21: names (§2) and the target's `run()` (Q3) decided; Q2, Q4, Q5 open |
| M1 spec: semantics, binding classes, diagnostics | done 2026-11-21: `bindings/sv/fw_to_sync.svh`, `fw_from_sync.svh`; `semantics/processes.md` "Task-sync crossings" (X1–X8); `FW-E-XING-SIDE`, `FW-E-XING-COMB` |
| M2 rt-sv: implementation | done 2026-11-21, `sv/fw_rt_xing.svh`, except X8 (reset) |
| M3 conformance tests | rt-sv run-time test `tests/sv/xing_runtime.sv` (X3, X5, X1, X2); no conformance scenario yet; X8 untested |
| M4 std: `fw_rv_initiator`, `fw_rv_get_ep`, `fw_rv_target` with no `run()` | done 2026-11-21: initiator and get endpoint have no thread; target's `run()` only calls the port. Timing unchanged (`rv_b2b`, `rv_ep`, pin-bridge tests); `rv_ep` mutants now hold the signal up in `comb()` |
| M5 `examples/wb_xtor` on the crossings | done 2026-11-21: same results as the `run()` version (149 / 185 edges, same mutant failures); the bench memory's wait states are sync code |
| M6 fe-sv: side checks; lowering the sync side to ready/valid ports | done 2026-11-24 (S0–S7 of [xing-lowering-plan.md](xing-lowering-plan.md)): static side checks; lowering to ready/valid ports; `wb_xtor`'s initiator lowered gives the class bench's results |

Note: the spec numbers the rules X1–X8 (`processes.md`); §4 below is the
design's R1–R7, kept for the record. Spec X6 adds the blocking rules and
`waiting()`.

## 1. Why

`examples/wb_xtor` and std's `fw_rv_xtor.svh` each hand the call to the
transactor's own `run()` through SV mailboxes. `run()` then writes and
samples pins, ticks, and relies on a `step()` default (C5) to drop `stb` or
`valid`. So the protocol timing is task code: it doesn't lower and isn't
checked formally, and every transactor re-solves the crossing.

A plain SV mailbox read by `step()` with `try_get` would remove `run()`,
but it costs a cycle per call. The kernel doesn't re-evaluate `comb()` when
task code changes the mailbox, so the request is first seen by `step()` at
*k* + 1 and is on the pins only after it. The construct has to be fw-hdl's
own, so the kernel knows when the process side changes it.

## 2. Names

Decided 2026-11-21: **`fw_to_sync`** (task code → sync code) and
**`fw_from_sync`** (sync code → task code). The direction is named from the
sync scope, which owns the construct.

The sides have no handles of their own. The methods show which side a call
is on: blocking `put`/`get` and `try_*` for the process side, and
`valid`/`peek`/`take` and `ready`/`give` for the sync side. (SV reserves
`task` and `logic`, so neither can be a side's member name.)

Considered and not taken:
- `fw_task2sync` / `fw_sync2task`;
- `fw_sync_in` / `fw_sync_out`;
- `fw_sync_inbox` / `fw_sync_outbox`;
- `fw_call_in` / `fw_call_out`;
- `fw_handoff_in` / `fw_handoff_out`;
- `fw_xing_in` / `fw_xing_out`.

## 3. The constructs

```systemverilog
// Task code -> sync code.
class fw_to_sync #(type T = bit) extends fw_object;
    static function fw_to_sync #(T) create(string name, fw_object parent, int depth = 1);
    // process side
    task         put(input T t);        // blocks until the sync side takes t
    function bit try_put(input T t);    // 0 if full
    // sync side
    function bit valid();               // an item is waiting (comb or step)
    function T   peek();                // the oldest item (comb or step)
    function bit take(output T t);      // step only: removes it, releases its put
endclass

// Sync code -> task code.
class fw_from_sync #(type T = bit) extends fw_object;
    static function fw_from_sync #(T) create(string name, fw_object parent, int depth = 1);
    // process side
    task         get(output T t);       // blocks until the sync side gives an item
    function bit try_get(output T t);
    // sync side
    function bit ready();               // there is room (comb or step)
    function bit waiting();             // a get waits with no item queued for it (comb or step)
    function bit give(input T t);       // step only: hands t to a get, or queues it
endclass
```

- Both are created in `build()`, like a signal, and belong to the
  component. Their clock and reset domains are the component's
  (`domains.md`).
- **`fw_to_sync::put` returns when the item is taken**, not when it is
  queued. `access()` therefore returns only after the protocol has used the
  request, and nothing is buffered behind the caller's back. With `depth`
  > 1, `put` returns when it is queued, for pipelined protocols (§8 Q4).
- **`fw_from_sync::waiting()` is true while a `get` is waiting** with no
  item queued for it. So a `get` starting to wait is itself a process-side
  change: it re-evaluates `comb()`. That is how `fw_rv_get_ep` raises `ready` only while a get is
  pending, with no thread of its own.

## 4. Rules

- **R1 Sides.** Only the owning component's sync code (`step()`, `comb()`
  and the functions they call) uses the sync side. Task code may use the
  process side from any thread, usually through an export method of the
  owner. Anything else is `FW-E-XING-SIDE`, on the construct.
- **R2 Comb only looks.** `comb()` may call `valid`, `peek` and `ready`.
  `take` or `give` in `comb()` is `FW-E-XING-COMB`. `comb` runs on every
  settle, so it would act each time.
- **R3 Process-side changes re-evaluate the scope.** A process-side call
  that changes the construct makes the change visible at once and
  re-evaluates the containing component's `comb()`. The settle then
  propagates as for any wire. The changes are:
  - an item put;
  - an item got;
  - a get starting or stopping to wait.

  That's the timing of a register written at that edge (C3): `step()`
  blocks see it at the next edge.
- **R4 Sync sees the state before the edge.** At edge *k*, `step()` sees
  the construct as it was before *k*. Task code never runs inside an edge
  (as in Crossings).
- **R5 Sync-side changes act at the edge.** `take` and `give` in `step()`
  at edge *k* take effect in *k*'s update. A process-side call they release
  resumes after *k*'s release, at edge *k* (C4, C7).
- **R6 No drive-twice.** Items are separate entries, so several puts
  sampled by one edge aren't an error (unlike C5 for signals). A full
  construct blocks `put`.
- **R7 Reset.** While the owner's reset domain is asserted, both are
  emptied at each edge. Blocked calls stay blocked. Task code that drives
  a protocol waits with `wait_reset_done` first (C8).

## 5. Timing: Wishbone initiator

```systemverilog
fw_to_sync #(req_t) req;
fw_from_sync #(rsp_t) rsp;

task access(output rsp_t r, input req_t q);
    req.put(q);
    rsp.get(r);
endtask

function void comb();
    req_t q = req.peek();
    pins.cyc.write(req.valid()); pins.stb.write(req.valid());
    pins.adr.write(q.adr); ...
endfunction

function void step();
    req_t q;
    if (pins.stb.read() && (pins.ack.read() || pins.err.read())) begin
        void'(req.take(q));
        void'(rsp.give('{dat: pins.dat_r.read(), err: pins.err.read()}));
    end
endfunction
```

Two accesses, A then B. The target acks at the first edge that samples
`stb`.

| Edge | Task side, after the release | `step()` at the edge | On the pins after the edge |
|---|---|---|---|
| k | `req.put(A)`: `comb` re-evaluates (R3); `put` blocks | — | `stb=1`, A |
| k+1 | `put` returns; `rsp.get` returns A's response (R5); `access(B)`: `req.put(B)`, `comb` re-evaluates | `stb && ack`: take A, give A's response | `stb=1`, B |
| k+2 | B returns | `stb && ack`: take B | `stb=0` |

Every access is on the bus for the edge after the call, and back-to-back
accesses keep `stb` high. That's today's timing, without the thread.

## 6. Implementation

- **rt-sv (M2).**
  - Each construct holds an SV queue and a count of waiting calls.
  - A process-side change re-evaluates the owner's comb blocks, then
    settles. Settling everything (`__fw_rt_kern::write_now` → `settle()`)
    is correct, just not minimal.
  - `take` and `give` in `step()` are staged and applied in the edge's
    update.
  - A blocked call waits on an event that the kernel triggers after the
    release.
  - The kernel knows which process is running (`__fw_rt_procs::running()`),
    so R1 and R2 are checked at run time.
- **fe-sv (M6).**
  - Checks R1 and R2 statically.
  - When a component that owns crossings is emitted, each one becomes a
    ready/valid port pair on the module:
    - **`fw_to_sync`:** `valid()` and `peek()` are `valid` and data. A
      `take` under condition *c* in `step()` is `ready = c`, and the
      handshake is the take.
    - **`fw_from_sync`:** the mirror; `ready()` is the input `ready`.

    The process side stays in simulation (`fw_pin_bridge`, or a task
    harness). This is the "the endpoints are a connection" picture of
    `sync-task-domains.md` §5.1, with the endpoint built in.

## 7. Steps

1. **M1:** the classes in `fw-hdl-spec/bindings/sv`, the rules in
   `semantics/processes.md` (a section next to Crossings), and the
   diagnostics.
2. **M2:** the rt-sv implementation.
3. **M3:** conformance tests:
   - R3: `comb` follows a put made at an edge, and `ready()` follows a
     waiting get;
   - R5;
   - the R1 and R2 errors;
   - R7.
4. **M4:** rewrite std's `fw_rv_initiator`, `fw_rv_get_ep` and
   `fw_rv_target` with no `run()`, keeping their documented timing and
   their tests.
5. **M5:** `examples/wb_xtor`: the initiator, the target and the memory
   model. The memory's wait states become sync code, which removes its
   `FW-E-DOM-OBJ` workaround.
6. **M6:** fe-sv checks and lowering.

## 8. Open questions

- **Q1 Names.** Decided: §2.
- **Q2 Direct task writes.** Once these exist, should task code still be
  allowed to write signals directly (`processes.md`, Crossings)?
  - It could stay allowed.
  - It could become a warning.
  - It could become an error outside std.
- **Q3 A target that calls out.** Decided 2026-11-21: a target may have a
  `run()`, because it has a port to call. Its `run()` does
  `fw_from_sync.get` (the request its sync code gave) → `p.access()` (or
  `p.put()`) → `fw_to_sync.put` (the response). The pin timing stays in
  `step()`/`comb()`. The thread only makes the call. An initiator, called
  through its export, has no `run()`.
- **Q4 Depth.** Is a `depth` > 1 needed for anything but pipelined
  protocols? With depth > 1, does `put` return on queue (as written) or
  still on take?
- **Q5 Scope.** "The containing scope" is the owning component. Should a
  crossing owned by a component also wake the comb blocks of its children
  that read it? It can't, under R1. That's fine if the owner passes the
  values on as signals.
