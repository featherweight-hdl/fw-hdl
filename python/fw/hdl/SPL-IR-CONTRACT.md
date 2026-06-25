# SPL IR contract — the shared input to `zuspec.synth.spl`

The centralized transparent lowering (`zuspec.synth.spl`) consumes a
**sequential-process-level (SPL) `zuspec.ir.core` component** and produces RTL
`ir.core` (be-sv netlists it). Any front end that produces a component matching
this contract reuses the same lowering. Verified with two front ends today:
**fw-hdl** (SV) and **zuspec-dataclasses** (`@zdc` Python).

The lowering accepts **both conventions** below (front-end-neutral); over time
front ends should converge on the *preferred* column.

## The component shape

| element | contract | preferred | also accepted (legacy) |
|---|---|---|---|
| **module pins** | `FieldInOut` (`is_out` = direction) | — | — |
| **clock / reset** | identified per-process | `Function.metadata['clock'/'reset'] = ExprRefField(self, idx)` (zdc, be-sv) | `Field.pragmas['fw_role'] = 'clock'/'reset'` (fw-hdl) |
| **data pins** | `FieldInOut` other than clock/reset | plain `FieldInOut(is_out=True)` (zdc) | `Field.pragmas['fw_role']='pin'` (fw-hdl, ignored — inferred from FieldInOut) |
| **internal state** | `Field(is_reg=True)`, not a `FieldInOut` | — | — |
| **register reset value** | a constant | `reset_value=N` (zdc) | `initial_value=ExprConstant(N)` (fw-hdl) |
| **the process** | a coroutine: `while True:` of awaited beats | `proc_processes` or `sync_processes`, `body=[StmtWhile(True, …)]` | — |

## The beats (the loop body)

The `while True` body is a sequence of statements; **awaited** statements are
*beats* (cycle boundaries), the rest are combinational logic that runs at the
adjacent beat. Recognized beats:

| beat | source form | IR | lowers to |
|---|---|---|---|
| **wait N cycles** (N>1) | fw-hdl `tick(N)` / zdc `cycles(N)` | `StmtExpr(ExprAwait(ExprCall(func.attr ∈ {tick,cycles}, [Const N])))` | a down-counter (load N-1, decrement, terminal = underflow MSB bit) |
| **cycle boundary** (N=1) | `tick()` / `cycles(1)` | same, N=1 | a pure 1-cycle advance — the loop body runs **every cycle**, no counter |
| **put** (registered output) | fw-hdl `port.put(v)` | `StmtExpr(ExprAwait(ExprCall(func=…port…`.put`, [v])))`; the port `Field` tagged `pragmas['fw_protocol']='put', ['fw_pin']=<pin>` | `pin <= v`, one FSM state |
| **combinational** | any non-awaited `StmtAssign`/`StmtIf` | — | runs at the adjacent beat (non-blocking, same state) |

## Lowering rules (the cookbook — "no magic")

- **1 awaited beat = 1 FSM state = 1 cycle.** No state merging, reordering, or
  scheduling.
- `n` beats ⇒ a `state` register (omitted when `n == 1`); FSM emitted as an
  `if (state==0) … else if … else …` chain.
- a `put` beat ⇒ `pin <= value`, then advance.
- a `tick(N)`/`cycles(N)` beat ⇒ down-counter; preloaded by the preceding state
  (or reset); terminal via the borrow/MSB bit (no wide equality comparator).
- **synchronous reset** initialises every register to its reset value; polarity
  from `SplConfig.reset_style` (default `async_high` = active-high `if (reset)`).

## What a front end must guarantee

1. Pins are `FieldInOut`; internal state is `Field(is_reg=True)`.
2. The clocked coroutine is a `while True:` of awaited beats, with clock/reset
   resolvable (metadata preferred, pragma accepted).
3. Beats are `tick`/`cycles`/`put` as above; everything else in the loop is
   synthesizable combinational `ir.core` (`StmtAssign`/`StmtIf`/`ExprBin`/
   `ExprCompare`/`ExprUnary`/`ExprSubscript`/`ExprConstant`/`ExprRefField`).

## Not yet in the contract (future)

- Control-dependent beats (`if cond: await X else await Y`), loops with awaits.
- `fork`/`join`/`select` (the concurrency primitives `SpawnStmt`/`SelectStmt`/
  `CompletionSetStmt` — C5).
- First-class protocol-port types (`DataTypePutIF`/…) replacing the pragma tags.
