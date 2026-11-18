# Layer-2 `--timing` probe (P0.1)

Does Verilator 5.055 (`--binary --timing`) run the class-task patterns
the layer-2 rt-sv kernel needs (`docs/design/core-layer2.md`)?

Run: `direnv exec /packets/featherweight-hdl/fw-hdl-sync sh run.sh`
(prints `l2-timing: PASS`; build logs in `obj_dir/`).

## What is probed

`top.sv` (expected trace: `expected_top.txt`)

1. A class `run()` task waiting on `@(ev)`, where `ev` is a class
   `event` triggered from `always @(posedge clk)`, then on `#3`.
2. `fork ... join_none` of several class tasks (`run`, `worker(id, #d)`)
   from an `initial` block.
3. A class function called from `always_comb`, writing a class field
   that an `always_ff` reads:
   - **A**: the input is passed as an argument (`c.eval(a)`).
   - **B**: the input is only a class field (`cb.eval_field()` reads
     `cb.in_val`, written by NBA from an `always`).

`top2.sv` (expected trace: `expected_top2.txt`)

4. `wait (flag == 3)` in a class task on a class field.
5. `@(posedge vif.clk)` in a class task through a virtual interface,
   and a blocking write to `vif.data`.
6. `#0` in a class task.

## Results

| # | Pattern | Result |
|---|---|---|
| 1 | `@(event)` + `#d` in class task | works (`[5] ev seen`, `[8] after #3`, ...) |
| 2 | `fork/join_none` of class tasks | works (workers finish at 1, 7, 12) |
| 3A | `always_comb` → class fn, input as argument | works: `y_a` follows `a`, `q_a` lags one cycle |
| 3B | `always_comb` → class fn, input only a class field | **never re-evaluates**: `y_b`, `q_b` stay 0 while `cb.in_val` counts 100..105 |
| 4 | `wait()` on a class field | works (`[25] flag==3 seen`) |
| 5 | `@(posedge vif.clk)` via virtual interface | works |
| 6 | `#0` | works with `--sched-zero-delay` |
| - | `#d` with a run-time `d` | build **fails** with `%Warning-ZERODLY` (fatal) unless `--sched-zero-delay` or `--no-sched-zero-delay` is given |

3B is a silent wrong result, not a crash (guess: a known Verilator
limitation, sensitivity not inferred through class handles; not checked
against its docs or issue tracker); no reproducer under
`verilator-bugs/` was needed. Item 5's blocking write on the clock edge
races the module's NBA on the same signal (final `data=107`); that is
an ordinary SV race, avoided by rule R4 below.

## Rules for rt-sv (copied to protocol-kit-plan §3)

- R1 Build with `--timing` and an explicit `--sched-zero-delay`
  (or `--no-sched-zero-delay` when no `#0` is emitted); a variable
  `#d` without one is a fatal ZERODLY.
- R2 `always_comb` sensitivity does not see class fields. Every value a
  combinational class function reads must reach it as an argument (or
  a module/interface signal); results go back to a module variable.
- R3 Class tasks may wait on class `event`s, `wait()` on class fields,
  `#d`, and `@(posedge vif.clk)`; all are safe.
- R4 Each pin has one writer. A class task must not write a signal
  that module code also writes: blocking or NBA, the result depends on
  scheduling order (checked by hand: with `vif.data <= 77` the module's
  NBA wins, final `data=40`; with `=` the task wins, `data=107`).
  Drive pins from class tasks by NBA (`vif.x <= v`) on signals only
  the class drives.
