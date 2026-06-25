# fw-hdl: SystemVerilog → Zuspec IR → Synthesizable RTL

**Status:** design for review
**Scope:** stand up `python/fw/hdl/...` as the SV→IR front end plus a top-level
command that drives the complete `blinky` flow: parse fw-hdl SystemVerilog with
pyslang, build Zuspec IR, run it through the existing `zuspec-synth` lowering
passes, and emit synthesizable Verilog RTL.

This document is grounded in the actual APIs of the in-tree packages
(`zuspec-ir-core`, `zuspec-fe-sv`, `zuspec-synth`, `zuspec-be-sv`). File/line
references are to those packages as they exist today.

---

## 1. What `blinky` *denotes* as hardware

`tests/blinky` is the driving example. The behavioral class (`blinky.svh`) is:

```systemverilog
class blinky extends fw_component implements fw_runnable;
    fw_port #(fw_put_if #(led_t)) out;          // a "put" port
    virtual task run();
        led_t v = 1'b0;
        forever begin
            out.t.put(v);        // register v onto the LED pin (1 clock)
            tick(BLINK_TICKS);   // hold for BLINK_TICKS root clocks
            v = ~v;              // flip
        end
    endtask
endclass
```

`blinky_top.sv` is the **module boundary**: it exposes `clock`, `reset`, `led`,
instances the put transactor `fw_put_xtor_if #(led_t) u_led(.clock,.reset,.out(led))`,
and uses the `fw_root` macros to make `blinky` the elaboration root and bind
`out` → `u_led` via `fw_put_xtor_bridge #(led_t)`.

Translating the runtime semantics of the std `put` transactor
(`@(posedge clock); out <= t;`) and the clock-domain `tick`
(`repeat(n) @(posedge clock);`), the **synthesizable hardware blinky denotes** is:

```systemverilog
module blinky (input clock, input reset, output logic led);
  logic [31:0] count;
  always @(posedge clock) begin
    if (!reset) begin              // std reset_style = sync_low
      count <= 0; led <= 1'b0;
    end else if (count == BLINK_TICKS-1) begin
      count <= 0; led <= ~led;
    end else begin
      count <= count + 1;
    end
  end
endmodule
```

i.e. a **counter that counts `BLINK_TICKS` and a toggle flop on `led`**. The
class tree, `run()` coroutine, ports, transactor, and `fw_root` lifecycle are
all *elaboration/sim-only*; the only hardware is the counter + toggle FF plus
the `clock/reset/led` pins. Our flow must extract exactly this.

> **The put beat is itself a cycle.** The RTL above is the *observable* behaviour,
> but note the faithful timing: `out.t.put(v)` runs `@(posedge clock); out <= t;`
> — it **consumes one clock and registers the output**. So each loop iteration is
> a *put beat* (1 cycle, drive `led <= v`) followed by `tick(BLINK_TICKS)` (N
> cycles). Two time-consuming events per iteration ⇒ the lowered process is a
> **multi-state FSM** (a drive state + a wait/counter state), **not** a single
> free-running counter. We model the put as a real awaited beat occupying its own
> state, not as a zero-cost combinational write (see §3, §7).

---

## 2. Grounded facts about the existing subsystems

### 2.1 Zuspec IR (`zuspec.ir.core`)
Pure Python dataclasses; everything imports from `zuspec.ir.core`.
- **Container:** `Context(type_m: Dict[str, DataType])` — `context.py`.
- **Module:** `DataTypeComponent(DataTypeClass)` — `data_type.py:114`. Relevant fields:
  `fields: List[Field]`, plus four process buckets
  `sync_processes / comb_processes / wire_processes / proc_processes : List[Function]`.
- **Ports/signals:** `Field` (`fields.py:69`) and `FieldInOut(Field)` (`fields.py:98`,
  `is_out: bool`, `is_inout: bool`). Field carries `kind: FieldKind`
  (`Port`/`Export`/`Field`…), `direction: SignalDirection` (`INPUT/OUTPUT/INOUT`),
  `datatype`, `is_reg`, `reset_value`, `clock: Expr`, `initial_value: Expr`.
- **Types:** `DataTypeInt(bits, signed)`.
- **Process:** `Function(name, args, body: List[Stmt], process_kind: ProcessKind, is_async, sensitivity_list)`.
  `ProcessKind` = `COMB | SYNC | WIRE`. (Note: `proc_processes` are async coroutine
  processes — what `run()` becomes.)
- **Stmts/Exprs:** full set — `StmtWhile/StmtIf/StmtAssign/StmtExpr`,
  `ExprBin(lhs,op,rhs)/ExprUnary/ExprConstant/ExprCompare/ExprCall/ExprAttribute/
  ExprAwait/ExprRefField(base,index)/TypeExprRefSelf`. Operators are `BinOp`,
  `UnaryOp`, `CmpOp` enums.

### 2.2 SV front end reference (`zuspec.fe.sv`) — *reference only, not reused as-is*
- `SVMapper` (`mapper.py`): pyslang `Compilation` → visits `SymbolKind.ClassType`
  → `ClassMapper.map_class` per class. Returns a **list** of `DataTypeComponent`
  (`get_components()`); it does **not** build a `Context`.
- It maps **classes only** — *modules and interfaces are ignored*. Library
  classes (`zsp_*`, template specializations) are filtered.
- The `counter` example (`tests/unit/test_counter_sv_to_ir.py`) confirms the shape
  we will reproduce: `counter_c` → `proc_processes=[run]`, `run.body=[StmtWhile(...)]`,
  body contains `ExprAwait(ExprCall(ExprAttribute(ExprRefField(self,i), 'write'), …))`,
  `count` field has `is_reg=True`, `datatype.bits==32`.
- Sub-mappers we will mirror (own implementation): `type_mapper`, `expr_mapper`,
  `stmt_mapper`, `function_mapper`, `class_mapper`, `error`, `config`, `parser`.

### 2.3 Synthesis (`zuspec.synth`) — **our lowering target** (per direction)
`_synthesize_sprtl(cls)` (`__init__.py:223`) is the non-pipeline path. Crucially it
is **IR-driven**:
1. `ctx = DataModelFactory().build(cls)` → `Context`.
2. `component_ir = ctx.type_m.get(cls.__qualname__ or cls.__name__)`.
3. `ir = SynthIR(component=cls, model_context=ctx)`.
4. Run the 5-pass chain:
   `ComponentFieldsPass → ProcessToFSMPass → FSMToRTLPass → CombLowerPass → ModuleAssemblePass`.
5. `sv = ir.lowered_sv["sv/module/top"]`.

`_get_component_ir(ir)` (`process_to_fsm.py:319`) uses `ir.component` **only** to look
up the name key in `ctx.type_m` (`cls.__qualname__`/`cls.__name__`). **It never
re-parses the Python class.** ⇒ We can run the identical pass chain on IR we built
ourselves by supplying a `Context` and a tiny stand-in `component` object whose
`__name__` matches our `type_m` key.

`ProcessToFSMPass` iterates `sync_processes + proc_processes` and picks a strategy
per process. `_is_simple_tick_proc` (`process_to_fsm.py:19`) detects the *single*
awaited-beat shape `while True: await tick(); <comb stmts>`. **blinky does not fit
this fast path:** its loop has **two** awaited beats — the `put` (1 cycle) and
`tick(N)` (N cycles) — so it routes through the general `_proc_has_await` FSM
transformer that gives each beat its own state (the §1 multi-state FSM). This is
the path we lower against; we reference its construct-handling (how it sequences
awaited beats into states, how it builds the tick counter) as the model for our
own SPL→RTL lowering (§4). We deliberately keep our model general here rather than
contort blinky into the single-tick fast path.

### 2.4 IR→SV emitter (`zuspec.be.sv`) — **the canonical Verilog emitter**
`SVGenerator(out_dir).generate(ctxt: ir.Context)` emits `.sv` directly from
`zuspec.ir.core` IR (`generator.py:136`), keyed off `ctxt.type_m`. It already
renders `sync_processes` (`ProcessKind.SYNC`) as `always @(posedge clock)` with
non-blocking assignments, `comb_processes` as `always @(*)`, `wire_processes` as
`assign`, and integral fields as `logic [N:0]` ports. **This is our Verilog
emission path** (`rtl2v`, §6): our lowering (§4) produces *RTL-level
`zuspec.ir.core` IR* (a component whose behaviour is in `sync_processes` with
explicit FSM-state/counter/output registers), and `be-sv` renders it. Per
direction, when emission needs a construct `be-sv` can't yet render, **we enhance
`be-sv`** rather than fork a second emitter. We do **not** use `zuspec-synth`'s
own text emission (`ModuleAssemblePass → lowered_sv`) as the product output — we
mine `zuspec-synth` for *lowering logic*, not for text.

---

## 3. The central problem: class → module boundary

`blinky` the **class** has no `clock`/`reset`/`led` ports — it has a `put` port
`out` and a clock-domain `tick`. Those signals are introduced by **elaborating
`blinky_top.sv`**: the `fw_root` binding (`out` ↔ `u_led` via `fw_put_xtor_bridge`)
plus the std clock transactor (clock/reset). Therefore the front end must do more
than class→IR; it must **elaborate the binding** to synthesize the module's pin
boundary and to give the `put`/`tick` calls hardware meaning.

We handle this with a **protocol/transactor knowledge table** keyed on the std
library types (we own `src/std`, so the mapping is stable):

| fw-hdl construct (in class/top) | IR / hardware meaning |
|---|---|
| clock domain / `tick(n)` | module `input clock`; `tick(n)` = wait `n` clocks (the FSM counter) |
| `fw_root` reset | module `input reset`; `reset_style="sync_low"` (std default) |
| `out : fw_port#(fw_put_if#(T))` bound via `fw_put_xtor_bridge#(T)` to pin `led` | module `output reg led : T`; `out.t.put(v)` ⇒ registered write `self.led <= v` (consumes 1 clock) |

So `out.t.put(v)` lowers to an `ExprAttribute`/`StmtAssign` against a synthesized
`led` output field, and `tick(BLINK_TICKS)` lowers to an `ExprAwait(tick(N))` that
the synth tick-proc strategy turns into the counter. The class-local `v` becomes
ordinary process state that synth promotes to the `led` flop.

**Binding approach — DECIDED: Option B for v1, with a planned migration to A.**

- **(B) Convention-driven binding (taken for v1):** parse `*_top.sv` only enough
  to read the `fw_root_bind_port(out, u_led, fw_put_xtor_bridge#(T))` bindings and
  the clock/reset port names; resolve the *protocol semantics* (put = registered
  output beat, etc.) from a built-in table of std transactors keyed on the bridge
  type. Pin name = the transactor instance's output (`led`). Gets blinky working
  end-to-end with bounded scope.
- **(A) Full elaboration (the general target):** parse the `fw_put_xtor_if`
  *interface body* with pyslang and *derive* the protocol semantics (which pins,
  which directions, what the `put`/`tick` tasks do) from the SV itself, rather than
  from a hard-coded table.

> **Why the table (B) is undesirable, and when to drop it.** The std-transactor
> table is a **hard-coded duplication of semantics that already live in the SV**
> transactor interface bodies (`src/std/fw_put_xtor_if.sv` *is* the source of
> truth for what `put` does). Risks: (1) it silently goes stale if a transactor's
> body changes; (2) it does **not** scale to **user-defined** transactors/protocols
> — anything not in the table is unsupported; (3) it encodes pin names/directions
> by convention rather than reading them. It is acceptable only because we own
> `src/std` and v1 targets a single known protocol. **Migration trigger → switch to
> (A):** the *first* of — a second std protocol needs lowering (e.g. `get`/`reqrsp`),
> a *user-defined* transactor must synthesize, or a table entry diverges from its
> SV body. The `bind/` module is structured so `protocols.py` (the table) is the
> only thing (A) replaces; `elaborate.py` (reads the bindings) stays. This is
> tracked as a known debt, not a permanent design.

---

## 4. Proposed `python/fw/hdl` architecture

The flow is a chain of **three explicit levels of `zuspec.ir.core` IR**, each with
its own CLI verb (§6) so every level is independently inspectable:

```
 FW-SystemVerilog ──sv2ir──▶ SPL IR ──spl2rtl──▶ RTL IR ──rtl2v──▶ Verilog
                            (proc_processes,     (sync_processes,    (via
                             awaited beats:       explicit FSM-state,  zuspec.be.sv
                             put/tick, forever)   counter, output regs) SVGenerator)
```

- **SPL IR** (Sequential-Process Level): a `DataTypeComponent` whose behaviour is
  the behavioural coroutine — `proc_processes` holding the `forever` loop with
  *awaited beats* (`put`, `tick`). This is the SV mapped into the constructs
  `zuspec-synth` knows how to lower.
- **RTL IR**: the same `DataTypeComponent` re-expressed in clocked form —
  `sync_processes` (`ProcessKind.SYNC`) with an explicit FSM-state register, the
  tick counter, and registered outputs. Still pure `zuspec.ir.core`, so the
  existing `be-sv` emitter renders it natively.

```
python/fw/
  hdl/
    __init__.py
    __main__.py            # thin: delegates to cli.main()
    cli.py                 # command infra: sv2ir / spl2rtl / rtl2v / synth
    flow.py                # Flow orchestrator (synth = sv2ir -> spl2rtl -> rtl2v + report)
    config.py              # FlowConfig (incdirs, defines, top, top_module, reset_style…)
    errors.py              # ErrorReporter (diagnostics w/ source locations)

    fe/                    # sv2ir:  FW-SystemVerilog -> SPL IR  (ALL SV->IR code here)
      __init__.py
      parser.py            # pyslang wrapper: SourceManager, +incdir/+define, Compilation
      collect.py           # walk AST: find component classes + fw_root bindings
      class_mapper.py      # ClassType -> DataTypeComponent (fields + proc_processes)
      type_mapper.py       # SV integral types -> DataTypeInt
      expr_mapper.py       # SV expr  -> Expr   (Bin/Unary/Const/Ref/Call/Await…)
      stmt_mapper.py       # SV stmt  -> Stmt   (forever->StmtWhile(True), if, assign)
      func_mapper.py       # task/function (run) -> Function (async proc)
      bind/                # the class->module boundary (§3)
        elaborate.py       # read fw_root_* bindings + clock/reset from *_top.sv
        protocols.py       # std-transactor TABLE (Option B; debt — see §3 caveat)
      context.py           # assemble mapped components into ir.Context(type_m)
      diagnostics.py       # unsupported/unrecognized construct -> hard error (§6)

    lower/                 # spl2rtl:  SPL IR -> RTL IR  (the novel lowering)
      __init__.py
      spl2rtl.py           # proc_processes(awaited beats) -> sync_processes(FSM+counter)
      beats.py             # beat sequencing: put-beat -> drive state; tick -> wait/counter
      component_stub.py     # name-stub (__name__/__qualname__ == type_m key) for synth reuse
      # Reuses zuspec-synth's proc->FSM lowering *logic* as the reference/engine and
      # MATERIALIZES the result back into zuspec.ir.core RTL IR (see §9 risk #1).

    emit/                  # rtl2v:  RTL IR -> Verilog
      __init__.py
      be_sv.py             # thin wrapper over zuspec.be.sv.SVGenerator(ctxt)
      # Emitter enhancements are upstreamed into zuspec-be-sv, not forked here (MSB).

    DESIGN.md              # (this file)
```

Notes:
- **All SV→IR code is under `python/fw/hdl/fe/`**, satisfying the requirement.
- We **reuse `zuspec.ir.core` (the IR), `zuspec.synth` (lowering logic), and
  `zuspec.be.sv` (emission)** as libraries; we write only the *front end* (`fe/`),
  the *SPL→RTL lowering* (`lower/`), and thin *glue* (`emit/`, `cli`, `flow`).
- `fe/` mirrors `zuspec-fe-sv`'s sub-mapper decomposition (proven shape) but is our
  own code, adds the `bind/` elaboration that `fe-sv` lacks, and emits a `Context`
  rather than a bare list.
- The three levels stay in **one IR universe** (`zuspec.ir.core`), which is what
  lets `be-sv` be the single emitter for the final step.

---

## 5. End-to-end data flow (the `blinky` flow)

```
 blinky_pkg.sv / blinky.svh / blinky_top.sv
        │  sv2ir:  fe.parser (pyslang) + fe.collect + fe.class_mapper + fe.bind.elaborate
        ▼
 SPL IR — DataTypeComponent "blinky":
   fields  = [ FieldInOut clock(IN,1), FieldInOut reset(IN,1),
               FieldInOut led(OUT,1,is_reg), <state v:1> ]
   proc_processes = [ Function run (is_async),
       body=[ StmtWhile(True, [
                 await put(led, v),     # awaited BEAT  -> drives led, 1 cycle/state
                 await tick(N),         # awaited BEAT  -> wait N cycles (counter)
                 v = ~v ]) ] ]
        │  fe.context -> ir.Context(type_m={"blinky": <SPL component>})
        ▼
        │  spl2rtl:  lower/spl2rtl.py  (beats -> FSM states; tick -> counter)
        ▼
 RTL IR — DataTypeComponent "blinky":
   fields  = [ clock(IN), reset(IN), led(OUT,is_reg),
               state(reg), count[31:0](reg), v(reg) ]
   sync_processes = [ Function(ProcessKind.SYNC, clock=clock, reset=reset,
       body= FSM:  S_DRIVE: led<=v;  -> S_WAIT
                   S_WAIT : count==N-1 ? (v<=~v; count<=0; ->S_DRIVE)
                                       : count<=count+1 ) ]
        │  rtl2v:  emit/be_sv.py -> zuspec.be.sv.SVGenerator(ctxt)
        ▼
 blinky.sv   (synthesizable RTL: FSM + counter + registered led)
```

`spl2rtl` sequences the two awaited beats into FSM states (the `put` beat into a
drive state that registers `led`, the `tick(N)` beat into a wait state with the
`BLINK_TICKS` counter) and re-expresses the loop as a `sync_processes` clocked
process — exactly the lowering `zuspec-synth` performs, but materialized as
`zuspec.ir.core` RTL IR so `be-sv` emits it (§2.4, §9 risk #1).
`reset_style="sync_low"` matches the std reset convention.

---

## 6. Top-level command infrastructure

`fw.hdl` exposes an argparse CLI (the existing empty `__main__.py` becomes a
delegator). Each level of the IR chain (§4) gets its own verb so it is
independently inspectable, and `synth` is the full flow:

```
python -m fw.hdl sv2ir   <files...> --top blinky --top-module blinky_top -o blinky.spl.json
python -m fw.hdl spl2rtl  blinky.spl.json  -o blinky.rtl.json
python -m fw.hdl rtl2v    blinky.rtl.json  -o blinky.sv
python -m fw.hdl synth   <files...> --top blinky --top-module blinky_top -o out/   # full flow + report
```

| verb | stage | input → output | notes |
|---|---|---|---|
| `sv2ir`   | front end (`fe/`)   | FW-SV → **SPL IR** | **unrecognized/unsupported SV constructs are a hard error** (no silent drop) |
| `spl2rtl` | lowering (`lower/`) | SPL IR → **RTL IR** | sequential-process-level → clocked FSM/RTL IR |
| `rtl2v`   | emit (`emit/`)      | RTL IR → **Verilog** | via `zuspec.be.sv.SVGenerator` |
| `synth`   | full flow (`flow.py`) | FW-SV → **Verilog + report** | runs sv2ir → spl2rtl → rtl2v, writes RTL + a synthesis report |

Each verb accepts an IR artifact (JSON via `zuspec.ir.core` serializer) or runs
from source, so stages compose and intermediate IR is reviewable.

**Options — follow SystemVerilog tool conventions** (plusargs), plus long opts:
- `+incdir+<path>` — include search path (repeatable)   [alias: `-I/--incdir`]
- `+define+<sym>[=<val>]` — preprocessor macro define (repeatable)   [alias: `-D/--define`]
- `--top <class>` — root component class (e.g. `blinky`)
- `--top-module <module>` — the `*_top.sv` module carrying the `fw_root` binding
  (drives §3 boundary elaboration)
- `--reset-style <sync_low|sync_high|async_low|async_high>` (default `sync_low`)
- `-o/--output <path>` — output file/dir
- `--dump-ir` / `--report <path>` — debug/inspection aids

The plusarg forms (`+incdir+`, `+define+`) are parsed in `fe/parser.py` and fed to
the pyslang `SourceManager`/preprocessor so fw-hdl sources elaborate the same way
they do under a simulator.

**DFM integration (follow-on):** package this as a dv-flow task
(`fw.hdl.Synth`) mirroring `zuspec.synth`'s `__ext__.py`/`dfm.py`, so a
`flow.yaml` can do `uses: fw.hdl.Synth` and feed the generated `.sv` into the
existing `hdlsim.vlt`/`yosys` tasks. The `tests/blinky/flow.yaml` already runs the
hand-written RTL through Verilator; a `blinky-synth` task would generate RTL from
the class model and run the *same* `blinky_tb` against it — closing the loop and
giving us an equivalence check (generated vs. hand-written) for free.

---

## 7. Resolved decisions (from review)

1. **Binding elaboration depth (§3).** ✅ **Option B for v1** (std-transactor
   table), but recorded as **known debt** with an explicit "why it's undesirable"
   and a **migration trigger** to Option A (full interface-body elaboration). See
   the §3 caveat block. The `bind/` split isolates the table (`protocols.py`) so
   (A) is a contained replacement later.

2. **Emission path.** ✅ **Reuse the `be-sv` IR→SV emitter** as the single Verilog
   emitter (`rtl2v`). `zuspec-synth` is used for its **lowering logic**, not its
   text output. When emission needs a construct `be-sv` can't render, **enhance
   `be-sv`** — do not fork a second emitter (§2.4). This is why the lowering must
   land in `zuspec.ir.core` RTL IR rather than synth's internal text.

3. **`put` modeling.** ✅ The put transactor **consumes one clock with no
   handshake**, so it is a real **awaited beat that occupies its own FSM state**
   (drive `led`, advance 1 cycle) — *not* a zero-cost combinational write. blinky's
   loop therefore has two beats (put + `tick`) and lowers via the general
   multi-state FSM path (§1, §2.3, §5). We model `put` as an awaited beat in SPL IR
   whose hardware effect is a registered output; `spl2rtl` gives it a state.

4. **Driving the lowering without a Python class.** ✅ Use the `Context` + name-stub
   approach (`lower/component_stub.py`); the pass logic only needs the IR keyed by
   `__name__`/`__qualname__` (`process_to_fsm.py:319`). Fine for now; revisit only
   if a future pass reaches into the original Python `cls`.

5. **v1 SV envelope.** ✅ Target the fw-hdl idiom blinky needs (one runnable
   `fw_component`, integral state, a `forever` loop with awaited `put`+`tick`,
   `if`/assignment/unary-not); `counter` is the second test. **But design for
   growth, not for blinky:** keep three general IR levels, model beats/states
   generally (not a hard-coded counter+toggle), keep `sv2ir` strict (unsupported
   constructs error out so gaps surface instead of miscompiling), and isolate the
   one expedient shortcut (the Option-B table) behind a seam. Do not paint into a
   corner — more complex protocols, multiple processes, sub-components, and derived
   clock domains are expected to land on top of this structure.

---

## 8. Phased implementation plan

- **P0 — skeleton + parser:** `fe/parser.py` (incl. `+incdir+`/`+define+`),
  `cli.py` (the 4 verbs), `config.py`, `errors.py`. *Exit:* `fw.hdl sv2ir` parses
  blinky and dumps the pyslang AST; unsupported constructs raise a clear error.
- **P1 — sv2ir (class→SPL IR):** `type/expr/stmt/func/class` mappers; produce the
  SPL `DataTypeComponent` for `blinky` (state `v` + `run` proc with awaited beats)
  into a `Context`. *Exit:* SPL-IR dump matches the §5 shape (mirrors the fe-sv
  counter-test assertions: `proc_processes=[run]`, `body=[StmtWhile]`, awaited
  `ExprCall`).
- **P2 — binding elaboration:** `bind/elaborate.py` + `bind/protocols.py`; inject
  `clock/reset/led` ports and tag `put`/`tick` beats with their hardware meaning.
  *Exit:* SPL component carries the pin boundary in the exact shape the lowering /
  `be-sv` expect (validate against `component_fields.py` / be-sv port handling).
- **P3 — spl2rtl + rtl2v:** `lower/spl2rtl.py` (beats→FSM states, tick→counter,
  producing RTL-level `sync_processes` IR) + `emit/be_sv.py`. *Exit:*
  `fw.hdl synth tests/blinky/*.sv --top blinky --top-module blinky_top -o blinky.sv`
  emits FSM+counter+registered-`led` RTL via `be-sv`.
- **P4 — verify:** lint generated RTL with Verilator; add a `blinky-synth`
  flow.yaml task that runs generated RTL against the existing `blinky_tb`. *Exit:*
  generated blinky passes the original testbench.
- **P5 — generalize:** second example (`counter`), DFM packaging (`fw.hdl.Synth`),
  begin Option A (interface-body elaboration) per the §3 migration trigger.

---

## 9. Risks / unknowns to validate early

1. **RTL-IR materialization (the keystone).** ✅ **SETTLED by spike → Option (b).**
   `spl2rtl` builds **`zuspec.ir.core` RTL IR directly** (clocked `sync_processes`
   with an FSM-state reg + counter + nested `StmtIf`), and the **unmodified `be-sv`
   `SVGenerator` emits Verilator-lint-clean RTL** from it. Option (a) (reuse synth
   passes + an *FSM-IR → ir.core* materializer) is rejected: `zuspec-synth`'s FSM IR
   is a *separate* dataclass hierarchy (`sprtl/fsm_ir.py`: `FSMState`/`FSMAssign`/
   `FSMCond`) that lowers to **text**, so it would need a materializer anyway and
   buys nothing over (b). `zuspec-synth` is therefore used as the **reference
   algorithm** for beat→state sequencing, not as a runtime dependency of `spl2rtl`.
   Spike facts that pin the IR contract (validated end-to-end, see the plan doc):
   - Ports = `FieldInOut(is_out=True/False)`; **internal regs = plain `Field(is_reg=True)`**
     (a `FieldInOut` is *always* a port → internal state modeled as `FieldInOut`
     wrongly emits as an `input`).
   - **Equality/relational = `ExprCompare`**, *not* `ExprBin(op=BinOp.Eq)` —
     `be-sv`'s `ExprBin` op-map omits comparisons and falls back to `"?"`; its
     `ExprCompare` path (`_get_sv_cmpop`) renders `==`/`!=`/`<`… correctly.
   - Clock/reset wired via `Function.metadata['clock'|'reset'] = ExprRefField(self, idx)`;
     `be-sv` emits `always @(posedge clock)` with in-body `if (!reset)` (sync_low).
- **`be-sv` coverage of the RTL IR.** Confirm `be-sv` renders the constructs our
  RTL IR uses (state register + `case`/`if` FSM in a `sync_processes` body, counter
  compare/increment). Gaps are **fixed in `be-sv`** (decision §7.2), so budget for
  small be-sv enhancements in P3.
- **Port shape for the boundary.** `bind/` must emit `FieldInOut` pin ports
  (`clock/reset/led`) in exactly the shape downstream code reads (`fields.py`
  `FieldInOut(is_out=…)`, `FieldKind.Port`, `SignalDirection`); validate against
  `component_fields.py` and `be-sv` port emission early in P2.
- **Name keying for any synth reuse.** If P3 reuses synth passes, the stub's
  `__name__`/`__qualname__` must equal the `type_m` key (use plain `__name__`, no
  nesting) to satisfy `_get_component_ir` (`process_to_fsm.py:319`).
- **Timing fidelity vs. reference RTL.** The faithful FSM (put-beat + N-cycle wait)
  has a different exact period than the hand-written `blinky_rtl` (§1); for the P4
  equivalence test, assert on *observable blink behaviour* (led alternates) as the
  existing `blinky_tb` does, not on exact cycle counts. Match reset polarity
  (`sync_low`) and the terminal count.
```
