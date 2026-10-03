# XLS back end — Phase X0: bring-up without an XLS installation

**Status:** X0 largely done; see §10 and §11 · **Started:** 2026-10-03
**Parent:** `killer-app.md` (§4 required enhancements, §5 MVP) ·
`chisel-xls-assessment.md` §4.4 (SV as the XLS-style input language)

Phase X0 does everything that does **not** need an XLS binary. Its job is to show three
things:

1. **Semantics are captured.** We can write XLS-style designs as fw-hdl SV classes.
2. **The meaning reaches the IR.** The SV front end puts that meaning into zuspec IR
   faithfully.
3. **The IR is emitted as the XLS IR we expect.** `zuspec-be-xls` produces it, and we
   check that the text means what the SV means.

What is left for XLS to do afterwards is parse, optimize, schedule and generate code.
Phase X1, the first contact with XLS, then starts from a reviewed, tested corpus. It does
not start from a blank page.

It runs in parallel with `killer-app.md` M0 (integration plumbing with a hand-written XLS
IR). M0 needs XLS; X0 does not.

---

## 1. Scope

### 1.1 In scope
- **The normative semantics of the static subset**, written down construct by construct
  (§3) as SV meaning → IR form → XLS IR form.
- **SV front-end enhancements** (`python/fw/hdl/fe/`) for the constructs that the
  phase-0 designs need.
- **IR additions** in `zuspec-ir-core`, kept to the minimum, plus a "static-subset" normal
  form and checker.
- **`zuspec-be-xls`:**
  - an XLS IR object model;
  - the text printer;
  - the IR → XLS lowering;
  - an XLS IR text parser, type checker and interpreter for the subset we emit (the
    stand-in for XLS during X0, §5.2).
- **The conformance harness:** SV on Verilator (the normative reference) vs our
  interpreter running the emitted XLS IR, with directed and random tests.
- **The phase-0 corpus:** construct micro-tests, CRC-32, RLE encoder, and the AES-128
  cipher plus the CTR core proc.
- **Source locations** carried from SV through the IR into the XLS `pos=` attributes.
- **The predicted block signature:** the engine-neutral signature type in
  `zuspec-ir-core`, and what we expect XLS to report for each corpus design. X1 checks
  this prediction.

### 1.2 Out of scope (X1 or later)
- Running `opt_main`, `codegen_main`, `eval_ir_main` or `ir_converter_main`.
- Scheduling, QoR and delay models.
- The glue generator, transactors, structural stitching and view switching
  (`killer-app.md` §4.7–4.8).
- `fork…join` effect reordering, non-blocking channel ops, multiple ops on one channel in
  one activation, RAMs, and multi-proc packages.
- The XLS IR → zuspec IR importer.

---

## 2. Pipeline and package boundaries

```
 SV class (fw_component, run(), functions)        fw-hdl: python/fw/hdl/fe/
        │  pyslang
        ▼
 zuspec IR (DataTypeComponent, Function, Expr)    zuspec-ir-core
        │  static-subset checker + normalization (§4.3)
        ▼
 XLS IR object model ──► text (.ir)               zuspec-be-xls
        │                                  ▲
        │ parse (ours) ─► typecheck ─► interpret   zuspec-be-xls/testing
        ▼
 channel/return traces  ══ compare ══  Verilator run of the same SV   fw-hdl tests/xls/
```

**Dependency rules:**
- `zuspec-be-xls` depends on `zuspec-ir-core` only.
- Its unit tests start from **hand-built IR**, the same approach as the zuspec-synth
  tests.
- Tests that start from SV live in fw-hdl (`tests/xls/`), because that is where the front
  end is.

**Package layout (as built):**

```
packages/zuspec-be-xls/
  pyproject.toml                       # deps: zuspec-ir-core
  src/zuspec/be/xls/
    __init__.py
    xir.py          # XLS IR object model: types, nodes, Function, Proc, Package
    printer.py      # xir → .ir text
    width.py        # bottom-up width/type rules of the static subset (R1) + StaticSubsetError
    lower_fn.py     # expressions, statements, Function → xls fn (dataflow); the
                    #   emittability checks live here and in lower_proc (BX-5)
    lower_proc.py   # run() activation → xls proc (state, receive/send, tokens)
    signature.py    # predicted BlockSignature + codegen naming options (BX-8)
    testing/
      parser.py     # .ir text → xir   (independent of printer; round-trip tested)
      typecheck.py  # XLS op typing rules (from ir_semantics.md)
      interp.py     # xir interpreter: fn eval; proc as a Kahn process over streams
      xlstools.py   # optional: opt_main parse check + function eval by constant folding
  tests/unit/       # hand-built IR → golden .ir; parser/typecheck/interp tests
```

The engine-choice policy (is this component XLS or the native scheduler?) is **not**
here. It belongs to `zuspec-synth`. The lowering's checks answer only "can this emitter
take it?".

**In fw-hdl:**
- `python/fw/hdl/fe/static_mapper.py` — the static-subset front end;
- `python/fw/hdl/xls_flow.py` — SV → XLS entry points;
- `tests/xls/` — conformance harness, micro designs, corpus, fuzzer, negative suite and
  goldens.

---

## 3. Semantics matrix

This is the core artifact. Each row is one construct with its normative meaning (SV
2-state; see `chisel-xls-assessment.md` §4.1 D1–D4), the IR form, and the XLS form. Each
row also gets at least one micro-test (§6.1).

Status columns (updated 2026-10-03):
- **FE:** ✅ the static front end (`python/fw/hdl/fe/static_mapper.py`) maps it.
  The planning-time column recorded the SPL mapper, which is unchanged.
- **IR:** ✅ uses an existing node · ➕ uses a node X0 added (R2, R3, R10, R11).
- **Emit:** ☑ `zuspec-be-xls` lowers it.
- **Test** names the suites that cover the row:
  - `u` — be-xls unit tests on hand-built IR, against an SV model and XLS;
  - `m` — micro functions, Verilator = interpreter = XLS;
  - `x` — exhaustive at 1–4 bits;
  - `f` — fuzz;
  - `p` — proc micro-tests;
  - `c` — the corpus;
  - `n` — the negative suite.

### 3.1 Types

| # | SV construct | Normative meaning | zuspec IR | XLS IR | FE | IR | Emit | Test |
|---|---|---|---|---|---|---|---|---|
| T1 | `bit [N-1:0]`, `bit signed` | 2-state, N bits | `DataTypeInt(bits, signed)` | `bits[N]` (signedness lives in the ops) | ✅ | ✅ | ☑ | u m x f |
| T2 | `logic` (wider than 1 bit) | rejected in declarations (4-state). Literals are 4-state types but are accepted if they have no x/z | — | — | ✅ (error) | — | — | n |
| T3 | `typedef struct packed` | the first field is the MSB | `DataTypeInt` (a bit vector, D-10); `.f` → `ExprPartSelect` | `bits[N]`; a field is `bit_slice` | ✅ | ✅ | ☑ | m p c (C2) |
| T4 | unpacked fixed array `T a[N]` | indices 0..N-1 (`[N]` or `[0:N-1]` only in X0) | `DataTypeArray(elem, N)` | `T[N]` | ✅ | ✅ | ☑ | u m |
| T5 | packed array `bit [M-1:0][N-1:0]` | element `i` at bits `[i*N +: N]` | `DataTypeInt` (D-2); `p[i]` → `ExprPartSelect` | `bits[M*N]`; `bit_slice` / `dynamic_bit_slice` | ✅ (descending ranges only) | ✅ | ☑ | m |
| T6 | `typedef enum bit [k-1:0]` | k-bit value | `DataTypeInt(k)`; enum values are constants | `bits[k]` | ✅ | ✅ | ☑ | m |
| T7 | class parameter `#(int W)` | elaborated per specialization | the top is named by a typedef of one specialization (FE-11) | one package per specialization | ✅ | ✅ | ☑ | c (C2 at W=8 and W=4) |
| T8 | `localparam` scalar or array constant | constant | `ExprCast(ExprConstant)`; an array is `ExprList` (R4) | `literal` (one array literal) | ✅ | ✅ | ☑ | m c (S-box) |

### 3.2 Expressions

| # | SV | Normative meaning | zuspec IR | XLS IR | FE | IR | Emit | Test |
|---|---|---|---|---|---|---|---|---|
| E1 | `+ - *` | wrap at the context-determined width | `ExprBin` + explicit width casts (R1) | `add`/`sub`/`umul`·`smul` at the result width | ✅ | ✅ | ☑ | u m x f |
| E2 | `/ %` | **rejected unless the divisor is a non-zero constant or guarded by `d != 0`** (D-1) | `ExprBin` | `udiv`/`sdiv`/`umod`/`smod` | ✅ | ✅ | ☑ | u m x f n |
| E3 | `& \| ^ ~ ~^` | bitwise | `ExprBin` / `ExprUnary(Invert)` | `and`/`or`/`xor`/`not` | ✅ | ✅ | ☑ | m x f |
| E4 | `<< >> <<<` | logical; shifting by ≥ width gives 0 | `ExprBin(LShift/RShift)` | `shll`/`shrl` (same over-shift result) | ✅ | ✅ | ☑ | u m x f |
| E5 | `>>>` | arithmetic on a signed left operand, logical on an unsigned one | ➕ `BinOp.ARShift` (D-3) | `shra` / `shrl` | ✅ | ➕ | ☑ | u m x f |
| E6 | `== != < <= > >=` | signed only if both operands are signed | `ExprCompare` | `eq`/`ne`/`ult`/`slt`… | ✅ | ✅ | ☑ | u m x f |
| E7 | `&& \|\| !` | 1-bit logical | `ExprBool` / `ExprUnary(Not)` | `and`/`or`/`not` on `ne(x,0)` | ✅ | ✅ | ☑ | m x f |
| E8 | reductions `& \| ^ ~& ~\| ~^` | 1-bit result | ➕ `UnaryOp.AndReduce/OrReduce/XorReduce` (+`Invert`) | `and_reduce`/`or_reduce`/`xor_reduce` | ✅ | ➕ | ☑ | m x f |
| E9 | `c ? a : b` | select | `ExprIfExp` | `sel(c, cases=[b, a])` | ✅ | ✅ | ☑ | m x f |
| E10 | `{a, b}`, `{N{a}}` | concatenation; the first operand is the MSB | ➕ `ExprConcat`, ➕ `ExprReplicate` | `concat` (operand 0 = MSB) | ✅ | ➕ | ☑ | m x f |
| E11 | `x[i]` | bit select; out of range reads 0 | ➕ `ExprPartSelect(x, i, 1)` | `bit_slice` / `dynamic_bit_slice` | ✅ | ➕ | ☑ | u m f |
| E12 | `x[hi:lo]` | part select | ➕ `ExprPartSelect(x, lo, hi-lo+1)` | `bit_slice` | ✅ | ➕ | ☑ | m f |
| E13 | `x[i +: W]`, `x[i -: W]` | indexed part select; out-of-range bits read 0, including a negative base | ➕ `ExprPartSelect` (R10) | `dynamic_bit_slice`; a signed base is padded below bit 0 | ✅ | ➕ | ☑ | u m (Verilator in-range only, §11) |
| E14 | size and sign casts, `W'(x)`, `signed'(x)`, implicit conversions | truncate; extend by the **source** signedness, or for a *propagated* conversion by the **target**'s (LRM 11.8.2) | `ExprCast` (extends by its operand's signedness), with a same-width retag first for propagated conversions | `bit_slice` / `zero_ext` / `sign_ext` | ✅ | ✅ | ☑ | u m x f |
| E15 | `s.f` (packed struct) | field | `ExprPartSelect` at the field's bit offset (D-10) | `bit_slice` | ✅ | ➕ | ☑ | m p c |
| E16 | `'{a, b}`, `'{f: a, ...}` | struct assignment pattern | `ExprConcat` in field order (D-10) | `concat` | ✅ | ➕ | ☑ | m c (C2) |
| E17 | `a[i]` read on an unpacked array | **out of bounds reads 0** | `ExprSubscript` | `sel(ult(i,N), [literal 0, array_index(a,[i])])`; a signed index is sign-extended past N first | ✅ | ✅ | ☑ | u m |
| E18 | `a[i] = v` | **out of bounds is a no-op** | `StmtAssign(ExprSubscript)` | `array_update` (a signed index is sign-extended first) | ✅ | ✅ | ☑ | u m |
| E19 | pure function call `f(a)` | call by value | `ExprCall` → `Function` | `invoke(to_apply=f)` | ✅ | ✅ | ☑ | u m c |
| E20 | integer literal `8'hFF`, unsized `1`, `'0`/`'1` | sized by SV context | `ExprConstant` inside an explicit cast (R1) | `literal(value=…)` at the resolved width | ✅ | ✅ | ☑ | m x f |

### 3.3 Statements and procedural structure

| # | SV | Normative meaning | zuspec IR | XLS IR | FE | IR | Emit | Test |
|---|---|---|---|---|---|---|---|---|
| S1 | blocking `=` | sequential update | `StmtAssign` | SSA renaming | ✅ | ✅ | ☑ | all |
| S2 | `if/else` | — | `StmtIf` | both arms computed, merged with `sel` at join points | ✅ | ✅ | ☑ | u m p |
| S3 | `case` | first match wins | `StmtMatch` | an `if` chain → `sel` | ✅ (`casez`/`casex` rejected) | ✅ | ☑ | u m n |
| S4 | `for`, `repeat` with constant bounds | fixed iteration count | `StmtWhile` (init + condition + step) / `StmtRepeat` | **unrolled** by constant folding (D-4) | ✅ | ✅ | ☑ | u m c |
| S5 | `function automatic` (class, package, `static`) | pure: reads arguments only, no tasks | `Function(args with Arg.datatype (R11), returns)` | `fn` | ✅ | ➕ | ☑ | u m c n |
| S6 | `return` / assigning the function name | — | `StmtReturn` (predicated) | function return value | ✅ | ✅ | ☑ | u m |
| S7 | immediate `assert (c) else $error(...)` | fails the simulation | `StmtAssert` | `assert(tok, !pred \| c, message=…)` | ✅ | ✅ | ☑ | u p (`p_assert`: Verilator stops at the same activation, with the same message, after the same outputs; XLS RTL fires `$fatal` there too and may finish that activation, D-11) |
| S8 | `x++`, `x += y` | — | `StmtAssign` | — | ✅ | ✅ | ☑ | m |

### 3.4 Procs (the `run()` task)

| # | SV | Normative meaning | zuspec IR | XLS IR | FE | IR | Emit | Test |
|---|---|---|---|---|---|---|---|---|
| P1 | `task run(); <prologue>; forever begin B end endtask` | one iteration of `B` = **one activation** | `Function(run, is_async)` with `StmtWhile(True)` | `proc` whose body is `B` | ✅ | ✅ | ☑ | u p c n |
| P2 | class properties, and `run` locals declared **outside** `forever` | persist across iterations | `Field` / prologue `StmtAnnAssign` (state) | state element: `state_read` + **one unpredicated `next_value`** per element whose value comes through `sel` (D-5) | ✅ | ✅ | ☑ | u p c |
| P3 | locals declared **inside** the `forever` body | automatic; re-initialized (to 0) on every entry | `StmtAnnAssign` local (R5, D-8) | SSA value; never state | ✅ | ✅ | ☑ | u p |
| P4 | initializers (property `= v`, prologue assignments) | initial state | `Field.initial_value`, then the prologue folded to constants | the proc's `init={…}` | ✅ | ✅ | ☑ | u p |
| P5 | `in.t.get(x)` | blocking receive into `x` | canonical: `StmtAssign(x, ExprAwait(ExprCall(port.get)))` (R6) | `receive(tok, channel=…)` → `tuple_index` 0/1 | ✅ | ✅ | ☑ | u p c |
| P6 | `out.t.put(v)` | blocking send | `StmtExpr(ExprAwait(ExprCall(port.put, [v])))` | `send(tok, v, channel=…)` | ✅ | ✅ | ☑ | u p c |
| P7 | a get or put under `if` | conditional effect | as P5/P6 under `StmtIf` | `predicate=` = the conjunction of the path conditions | ✅ | ✅ | ☑ | u p c (C2, C4) |
| P8 | effect order | program order (D-6) | statement order | token chain in program order | ✅ | — | ☑ | u p |
| P9 | a port's element type | the channel's payload type | `DataTypeGetIF` / `DataTypePutIF(element_type)` on the port field (R7) | `proc p<ch: T in, ...>` + `chan_interface` | ✅ | ✅ | ☑ | u p c |
| P10 | a get or put inside a loop, a second op on the same channel, `#delay`/`@`, other task calls | — | — | **rejected in X0** with a located diagnostic | ✅ | — | ✅ | u n |

---

## 4. Work items

Status key: ☐ not started · ◐ in progress · ☑ done. Tests are part of every item.

### 4.1 Semantics specification (S)
- ☑ **SEM-1** Write the §3 matrix into `zuspec-semantics.md` as the normative
  "static subset" section. That makes it the reference that the front end, the emitter
  and the interpreter all cite.
  → Done as `zuspec-semantics.md` §6.3.1, the static subset's value and proc semantics. It also resolves open question S3 for this subset.
- ◐ **SEM-2** For each row, record the SV LRM clause and the XLS `ir_semantics.md` section
  behind it.
  → The doc and test comments cite the clauses that mattered: LRM 11.5.1 (out-of-range selects), 11.8.2 (propagated conversions), 6.18 (forward typedefs), and the `ir_semantics.md` op sections in `typecheck.py` and `interp.py`. A per-row citation column is still to do.
- ☑ **SEM-3** Resolve decisions D-1 to D-6 (§8).
  → D-1 to D-6 are settled as recommended, and D-2 is revised (§8). Added D-10.

### 4.2 SV front end (`python/fw/hdl/fe/`) (M–L, the largest item)
- ☑ **FE-1 Width fidelity (R1).** Map pyslang `Conversion` to `ExprCast`, `ExprZext` or
  `ExprSext`, and stop dropping it. Wrap constants in their resolved width. Afterwards,
  every expression's width must be computable **bottom-up**, without context. This
  matters most, because silent width bugs are the main semantic risk.
  → In `fe/static_mapper.py`. Every `Conversion` becomes an `ExprCast`, and propagated conversions retag before extending (LRM 11.8.2; §11). Constants are cast to their SV type and read exactly from the SVInt (`toString`, not `str`). The fuzzer guards this.
- ☑ **FE-2** Packed structs (T3) and enums (T6), including field access (E15) and
  assignment patterns (E16). The type mapper must look at the canonical type before
  the `isIntegral` check.
  → As bit vectors (D-10): `.f` → `ExprPartSelect` at the field's `bitOffset`, a pattern → `ExprConcat`, an enum value → a constant.
- ☑ **FE-3** Arrays (T4, T5), constant arrays (T8), element read and write (E17, E18).
  → Unpacked arrays (`[N]` / `[0:N-1]`), packed arrays as bits (D-2), constant arrays as `ExprList`, and element reads and writes.
- ☑ **FE-4** Operators: `>>>`, reductions, `?:`, `&&`/`||`, concatenation and
  replication, part select and indexed part select (E5, E7–E10, E12, E13). Signed
  tagging (E6).
  → Also the reductions `~&`, `~|`, `~^`, binary `~^`, `$signed`/`$unsigned`, and `x[i -: W]`.
- ☑ **FE-5** Pure functions (S5, S6): class functions, `static` functions and package
  functions. Purity check. Calls (E19).
  → Package and class (`static`) functions, mapped on demand from calls. Assigning to the function name works, and so do early returns. A function that reads a class property is rejected as impure, and so is one with an output argument.
- ☑ **FE-6** `case` (S3) and constant-bound `for` (S4).
  → `case` (first match; `casez`/`casex` rejected), any constant-bound `for`, and `repeat`.
- ☑ **FE-7** The state/temporary split (P2, P3): locals inside `forever` are temporaries;
  prologue locals and properties are state. Prologue assignments become initial values
  (P4).
  → Locals inside `forever` are `StmtAnnAssign` temporaries, and prologue locals are state. Only in the static mapper: the SPL mapper is unchanged.
- ☑ **FE-8** Canonical channel ops (P5, P6, R6) and typed port fields (P9, R7). **Check
  that `lower/spl2rtl.py` and `mmio_synth` still accept the typed port fields**; if they
  don't, put the change behind an option.
  → In the static mapper. The SPL path is untouched, so `spl2rtl`/`mmio_synth` are unaffected. Each port field carries `pragmas['sv_type']`, its payload type as SV spells it.
- ☑ **FE-9** Immediate `assert` (S7).
  → The message is taken from `$error("...")`.
- ☑ **FE-10** Source locations: set `loc` (file, line, column) on every node the front
  end creates.
  → Every statement and expression carries `Loc(file, line, col)`, and diagnostics use it.
- ☑ **FE-11** Class specialization: choose the specialization named by the test top or a
  typedef, and map one component per specialization (T7).
  → The top may be a typedef of a class specialization (`typedef rle_enc #(8) rle_enc8_t;`).
- ☑ **FE-12** Negative suite: every construct the front end rejects gives one located
  diagnostic, and each diagnostic has a test.
  → `tests/xls/test_negative.py`: 12 rejected constructs, each with its SV line checked.

- ☐ **FE-13** (new) Move the SPL mapper onto the exact-width contract. Today the static
  mapper and the SPL mapper are separate (FE-8 risk). Once `spl2rtl`/`mmio_synth`
  accept `ExprCast`, temporaries as locals and typed ports, they become one front end:
  one model, many engines (`killer-app.md`).
### 4.3 IR additions and static-subset normal form (`zuspec-ir-core`) (S–M)

Keep these to the minimum. Each addition also needs a visitor method and a `be-sv`
rendering, so the existing back ends don't trip on it.

- ☑ **R1** Width contract: after the front end, the width of every `Expr` follows from
  its operands and explicit casts. This is documented, and asserted by `width.py`.
  (The alternative, a `dtype` slot on `Expr`, is decision D-7.)
  - The contract is written at the top of `zuspec-be-xls/width.py`.
  - A bare integer constant is unsigned and minimal-width, so anything else needs a cast.
  - `ExprCast` extends by the **source** signedness, as SV does.
- ☑ **R2** `ExprConcat(values)` and `ExprReplicate(count, value)`. Landed in `expr.py`,
  with be-sv rendering in both `generator.py` and `ir/expr_emit.py`.
- ☑ **R3** `UnaryOp.AndReduce/OrReduce/XorReduce`; `BinOp.ARShift` (D-3). `ARShift` is SV
  `>>>`: arithmetic on a signed left operand, logical on an unsigned one.
- ☑ **R10** (new) `ExprPartSelect(value, base, width)` for `x[i +: W]`, `x[hi:lo]` and
  packed-array element selects: the width is a constant, so it is known bottom-up.
  `ExprSlice` carries no width and could not express a variable-base select.
- ☑ **R4** A constant-array literal: `ExprList` of element expressions, with no new
  node. It lowers to a single XLS array `literal` when every element is constant (the
  S-box case).
- ☑ **R5** Temporaries need **no new flag** (D-8). A temporary is a `StmtAnnAssign`
  declaring an `ExprRefLocal` inside the `forever` body. A local the prologue declares
  is state.
- ☑ **R6** One canonical channel-op form (P5, P6), with no new node (D-9):
  - get: `StmtAssign([x], ExprAwait(ExprCall(ExprAttribute(<port>, "get"), [])))`;
  - put: `StmtExpr(ExprAwait(ExprCall(ExprAttribute(<port>, "put"), [v])))`.

  It is documented in `lower_proc.py` and in `SPL-IR-CONTRACT.md` ("The static-subset
  contract"), next to the SPL contract it shares the `put` shape with.
- ☑ **R7** Port fields typed as `DataTypeGetIF` / `DataTypePutIF`. The types already
  exist; be-xls requires them and rejects an untyped port with a diagnostic.
- ☒ **R8** Dropped: no `packed` flags. Packed structs and packed arrays stay bit vectors
  in X0 (D-2, D-10), so they need no IR marker.
- ☑ **R11** (new) `Arg.datatype`: function arguments had no typed slot (`annotation` is
  an `Expr`). Added to `stmt.py`.
- ☑ **R9** The `BlockSignature` type: channels (name, direction, payload type, flow
  control, ports), latency/II, reset and clock. Both engines will fill it in.
  → `zuspec-ir-core/signature.py`: `BlockSignature` and `ChannelSignature`.

### 4.4 `zuspec-be-xls` emitter (M)
- ☑ **BX-0** Package skeleton: `pyproject.toml`, `ivpm.yaml` and pytest set-up, with an
  `xls` marker that skips tests when no `opt_main` is found.
  - CI: `.github/workflows/ci.yml` uses the estate's shared `zuspec-pybuild` workflow,
    as ir-core does, with a `__version__.py` (0.1.0) and the version-reading
    `setup.py`.
  - Also a README.
- ☑ **BX-1** `xir.py` object model (types, values, nodes, `Builder` with the result-type
  rules) and `printer.py`. The syntax is **pinned to xlsynth v0.59.0**. The references
  are `ir_converter_main` and `opt_main` output from that release, stored in
  `tests/unit/data/xls_ref/` with their DSLX sources. `print(parse(ref)) == ref` holds
  byte for byte for all six. Proc form: `proc p<ch: T in, ...>(st: T, init={v})`, with
  `chan_interface` lines, `state_read` and `next_value`.
- ☑ **BX-2** `width.py`: the typing rules (`infer`). The lowering applies them to every
  expression it lowers, so a width or type violation stops it with the expression's
  location (`StaticSubsetError`, `file:line:col: ...`).
- ☑ **BX-3** `lower_fn.py`: expressions, SSA renaming, `if` merges, unrolled loops,
  `case`, invokes, and the out-of-bounds guards (E17).
  - The guards:
    - array reads are guarded with `sel`;
    - signed indices are sign-extended so a negative index can't alias an in-range one
      (§11);
    - a negative signed part-select base reads and writes only the in-range bits;
    - variable bit and part writes use `bit_slice_update`, which already matches SV.
  - Constant-bound loops unroll by constant folding the loop condition. Any SV `for`
    form works, as long as the condition folds.
  - `return` is predicated, so early returns work. A divide must be guarded (D-1).
  - Pure calls lower to `invoke`, callees first; recursion is rejected.
  - Dead nodes are removed.
- ☑ **BX-4** `lower_proc.py`:
  - state elements with their `init`;
  - one `next_value` per element;
  - receives and sends with predicates;
  - a program-order token chain;
  - channel declarations.

  Tested: the accumulator, prologue state vs temporaries, predicated get/put, effect
  order, a predicated assert, and C1 CRC-32 as a streaming proc.
- ◐ **BX-5** Emittability check. It lives in the lowering itself (`width.infer` and
  `ProcLowerer._port_call`) rather than a separate `check.py`, and every rejection
  carries the IR `loc`. The P10 rejections are tested:
  - a channel op in a loop;
  - a second op on one channel;
  - `get` without a target;
  - other awaited calls;
  - a missing `forever`;
  - an untyped port;
  - a channel op in the prologue.

  Still to do: a test that runs these from SV through the front end (FE-12).
- ☑ **BX-6** `pos=` attributes and the `file_number` table from `loc`.
  → `pos=[(file, line-1, col-1)]` (XLS is 0-based) on every node, with a `file_number` table per package.
- ☑ **BX-7** Golden tests: hand-built IR → `.ir` text for every §3 row. Golden diffs are
  reviewed by a person when they change.
  → `tests/xls/golden/*.ir` holds 7 procs and 2 function packages from the corpus and micro designs; regenerate with `XLS_GOLDEN_UPDATE=1`. The hand-built-IR goldens of the original plan became SV-model tests in `test_lower_fn.py`/`test_lower_proc.py`, which check meaning rather than text.
- ☑ **BX-8** Predicted signature (R9) for each corpus design. The X1 check: does XLS
  report the same?
  → `zuspec-be-xls/signature.py`: `predict_signature(comp, CodegenOptions)`. The options carry the codegen naming flags that X1-3 must pass.

### 4.5 Stand-in for XLS (`zuspec-be-xls/testing`) (M)
- ☑ **XT-1** `parser.py`: parses the subset we emit, written **separately from the
  printer** against XLS's own output. It also reads `opt_main`'s `non_synth=` state
  split. Every op test round-trips through text.
- ☑ **XT-2** `typecheck.py`: XLS per-op typing rules for the emitted ops, written from
  `ir_semantics.md`, with each rule's doc section cited in a comment. It also has one rule
  the docs omit (§11, 2026-10-03).
- ☑ **XT-3** `interp.py`, functions: evaluate a `fn` on bit-vector inputs.
- ☑ **XT-4** `interp.py`, procs: run a proc as a Kahn process over input streams
  (blocking receive; activation by activation) and collect the output streams.
  - Tested on XLS-generated procs: the accumulator and the two-state proc with an
    assert. The `opt_main`-optimized proc gives the same trace as the unoptimized one.
  - An activation that blocks is abandoned. Effects before the blocking receive stand;
    state is not updated.
- ☑ **XT-5** Op-level tests taken from the examples in `ir_semantics.md`. These are
  independent of our emitter, which limits common-mode errors (§9, risk 1).
  - **Plus an op-level differential against real XLS** (`test_xls_differential`, marked
    `xls`): every emitted op at widths 1, 3, 8, 13, 64 and 65, with 40 random and edge
    vectors each.
  - It runs through `opt_main`'s constant folding (`testing/xlstools.py`), so no
    `eval_ir_main` is needed. All pass (§11).
- ☑ **XT-6** Data-layout functions (tuples MSB-first, arrays element 0 in the LSBs), with
  a round-trip test against SV packed casts on Verilator.
  → `xir.flatten`/`unflatten`, with **the original statement confirmed by codegen (X1-4)**.
  - In X0 I "corrected" arrays to element 0 in the MSBs, from the DSLX `as` cast. That
    cast is a different convention from the port layout.
  - XLS's generated Verilog writes `[0x11, 0x22, 0x33]` as `{8'h33, 8'h22, 8'h11}`, so
    element 0 is in the LSBs, as in an SV packed array. `flatten` now follows the
    Verilog.
  - The round trip against Verilator is moot while packed types stay bit vectors (D-2,
    D-10).

### 4.6 Conformance harness (`fw-hdl tests/xls/`) (M)
- ☑ **CH-1** Function harness: a generated SV top calls the function on vectors from a
  file and prints the results. It runs on Verilator (from the workspace `packages/`).
  → `tests/xls/xls_harness.py: check_functions`; vectors are inline, or loops in exhaustive mode.
- ☑ **CH-2** Proc harness: source and sink components feed the input streams to the
  class and record the output streams on Verilator (`--timing`, as `tests/intf_pc`
  does).
  → `check_proc` generates the source/sink harness from the port types (`fw_component_root` + clock bridge), with `--timing`.
- ☑ **CH-3** Comparator: Verilator output against `interp.py` output on the emitted
  `.ir`, exactly, per function result or per channel stream.
  → Per function result, per channel stream, and the final integral property values. With `opt_main` present, XLS also evaluates every function vector (`xls_eval_calls`).
- ☑ **CH-4** Exhaustive mode for narrow operands: every E-row at 1–4 bits, signed and
  unsigned.
  → `test_exhaustive_single_ops`: about 900 single-operator functions (every binary and unary op, `?:`, replication, casts), 1–4 bits, all signedness combinations, results at w and w+2. Over 50k vectors, about 9 s.
- ☑ **CH-5** Expression fuzzer: random well-typed SV expressions over the E-rows with
  random widths and signedness, run through both sides. Shrink failing cases. This is
  the start of the cross-back-end fuzzer in `chisel-xls-assessment.md` §7.
  → `tests/xls/exprgen.py` + `test_fuzz.py`: random expressions with mixed signedness, unsized literals, casts, concatenation, shifts and guarded division. Arguments are up to 70 bits. It caught a deliberately re-introduced FE-1 bug at once, and found the wide-constant bug (§11). Variable selects are kept in range (§11).
- ◐ **CH-6** DFM flow entries so `dfm run` executes the whole conformance set.
  → `tests/xls/flow.yaml` (task `xls.xls-conformance`, running both pytest suites), added to the root `tests` task. **Not run here**: `dfm` in this workspace fails to start (`ModuleNotFoundError: dv_flow.libyosys` while loading plugins), independent of this change.

---

## 5. Verification strategy without XLS

### 5.1 The oracle
**Verilator running the SV source is normative**, because the SV semantics are
(`sv-normative-semantics`). Every check compares against it.

### 5.2 The stand-in
`testing/` implements just enough of XLS to read and execute what we emit. It answers
"does this XLS IR mean what the SV means?" **under our reading of the XLS semantics**.
That reading is the weak point. Three things limit it:
- **Separate implementation:** the parser and interpreter are written independently of
  the printer and lowering, and the typing and op semantics are coded directly from the
  XLS docs, with citations.
- **Op-level tests** (XT-5) come from the docs' own examples, not from our output.
- **The first task of X1** replays the whole corpus through XLS's own parser and
  `eval_ir_main` and compares the results with our interpreter (§7). A difference there
  is a bug in our reading, and is fixed in the interpreter **and** the emitter.

### 5.3 Test layers

| Layer | Input | Check | Volume |
|---|---|---|---|
| Unit (be-xls) | hand-built IR | golden `.ir`; our type check passes | 1+ per §3 row |
| Op semantics | doc examples | interpreter results | 1+ per emitted op |
| Conformance, directed | SV micro-tests | Verilator = interpreter | 1+ per §3 row |
| Conformance, exhaustive | E-rows at 1–4 bits | Verilator = interpreter | all values |
| Conformance, fuzz | random expressions | Verilator = interpreter | ≥10k per CI run (nightly: more) |
| Designs | §6.2 corpus | reference vectors; Verilator = interpreter | per design |
| Negative | unsupported SV | exactly one located diagnostic | 1 per rejected construct |

---

## 6. Corpus

### 6.1 Construct micro-tests
One small SV class or function per §3 row, in `tests/xls/micro/`.

### 6.2 Designs
The same designs as the `killer-app.md` MVP, cut down to what X0 can show:

| # | Design | X0 form | Exercises | Reference |
|---|---|---|---|---|
| C1 | CRC-32 | pure function, `crc32_step(crc, byte)`, plus a streaming proc (`get` byte → state update → `put` on the last byte) | E3, E4, E9, S4, S5, P1–P6 | check value `0xCBF43926` for `"123456789"` |
| C2 | RLE encoder | the `rle_enc` class from `chisel-xls-assessment.md` §4.4 | T3 (struct payload), P2/P3 split, P7 predicated send, E16 | XLS `rle_enc.x` test vectors, hand-transcribed |
| C3 | AES-128 cipher | pure functions: `sub_bytes` (S-box constant array), `shift_rows`, `mix_columns`, `add_round_key`, key expansion, `aes_encrypt` (10 rounds unrolled) | T4, T5, T8, E10, E12, E17, S4, S5 (a large function) | FIPS-197 Appendix B/C.1 |
| C4 | AES-128-CTR core | a proc: `get` command (key, IV, count) → loop of `put` blocks. **In X0 this becomes a counter-state proc, one block per activation**, because P10 forbids channel ops inside loops. | P1–P8, T3, state machine as state | NIST SP 800-38A F.5.1 |

C4 is a good test of the subset rules. The natural SV (`for` around a `put`) is rejected,
and the diagnostic has to point at the restructuring: one block per activation, with a
counter in state. That is the "next rung" guidance from `killer-app.md` §1.4, at small
scale.

---

## 7. Phase X1: what first contact with XLS must check

These are assumptions X0 makes. X1 tests each of them first, before any optimization or
codegen work:

- ☐ **X1-0 Tool source.** XLS comes from the xlsynth release binaries, pinned through
  `ivpm.yaml` (see the note below this list).
- ◐ **X1-1 Text syntax.** *Done early for everything X0 emits:* with `opt_main`
  v0.59.0 on hand, every package the be-xls and conformance suites produce is parsed and
  verified by XLS, procs included. What remains is the pinned install (X1-0).
  The original check: all corpus `.ir` files parse and verify with the pinned XLS:
  `opt_main` parses, verifies and re-prints. Watch the proc syntax in particular: state
  element and `init` form, `state_read`/`next_value` vs the older `next` form, `chan`
  declarations and their attributes. The XLS docs show both styles.
- ☑ **X1-2 Semantics.** *Done early.*
  - **Functions:** `opt_main` constant-folds a call on literal arguments, so
    `xls_eval_calls` gets XLS's own answer. Every function vector in the micro,
    exhaustive, fuzz and corpus suites matches Verilator and `interp.py` in a
    three-way comparison. That includes AES-128 against FIPS-197, and every op at
    widths 1–65.
  - **Procs:** through the fallback below. `codegen_main` (v0.59.0, `unit` delay model)
    generates RTL at 1 and at 2 pipeline stages. The RTL runs on Verilator behind
    ready/valid sources and sinks that throttle at random, holding valid until the
    handshake. Its output streams must match `interp.py`, which already matches
    Verilator on the SV source. This runs inside every `check_proc`, so it covers
    every micro proc and every corpus proc (`xls_harness.check_proc_rtl`).
  - The one difference found is by design: in RTL, a failing assert does not stop
    the rest of its activation (D-11).

  The original check: XLS's interpreter on every function and proc vector set gives the
  same results as `interp.py`. **The xlsynth release ships no `eval_ir_main`.** Options:
  - the IR interpreter in `libxls` (its C API, used by the xlsynth Rust crate), called
    through ctypes;
  - asking xlsynth to add `eval_ir_main` and `eval_proc_main` to the release;
  - as a fallback, `codegen_main` → Verilator, compared against `interp.py`.
- ☑ **X1-3 Signature.** The `module_signature` from `codegen_main` matches the predicted
  `BlockSignature` (BX-8).
  - `signature.signature_from_codegen` reads XLS's `ModuleSignatureProto` text, and
    `signature_mismatches` compares it with the prediction. The comparison covers name,
    clock, reset and polarity, and each channel's direction, flow control, port names
    and payload width.
  - Checked for every proc in the conformance suites with the default options. A
    be-xls unit test also checks module renaming, an active-low reset and custom
    suffixes.
  - Latency and II are left to the scheduler and not predicted.
- ☑ **X1-4 Layout.** The flattened tuple and array bit order in the generated Verilog
  matches XT-6.
  - `test_layout.py::test_x1_4_*` sends a nested tuple/array literal and compares
    codegen's Verilog constant with `xir.flatten`.
  - Tuple element 0 is in the MSBs; **array element 0 is in the LSBs**. This is the
    opposite of the DSLX `as` cast, and it reverses the X0 "correction" of XT-6.
  - Nothing in X0 depended on the array order: ports carry bit vectors. Narrower now: X0 keeps packed types as bit vectors (D-2, D-10), so only
  unpacked arrays and the receive tuple are affected.
- ☑ **X1-5 Positions.** `pos=` survives into the schedule and the Verilog comments
  (`killer-app.md` Q3).
  - With `--source_annotation_strategy=comment`, codegen writes
    `// micro_proc_pkg.sv:L:C` above the logic for each node. It survives
    `opt_main`, which merges nodes.
  - **XLS prints positions 0-based**, so line L is SV line L+1. It does the same for
    DSLX: `acc.x:8:39` names line 9. Our `pos=` uses XLS's own 0-based convention, so
    any tool that maps a comment back to source must add 1.
  - `test_micro_proc.py::test_x1_5_*` maps the comments back to the compare, add and
    put of `p_acc`.
  - Not checked: the schedule report.
- ☑ **X1-6 Guards are free.** The E17 out-of-bounds guard disappears after `opt_main` when
  the index is provably in range (QoR, not correctness).
  - *Checked early:* `T[i & 3]` into a 4-entry table goes from
    `ult`+`sel`+`array_index` to a bare `array_index` after `opt_main`.
  - `T[i]` with a wider `i` keeps a guard, which XLS rewrites as a mask. That is
    correct: the index really can be out of range.

**XLS tool source (checked 2026-10-03).**
- **What xlsynth publishes:** <https://github.com/xlsynth/xlsynth> releases (v0.59.0,
  2026-09-26) are **one raw executable per tool and platform**, not archives. Examples:
  `opt_main-ubuntu2004`, `codegen_main-ubuntu2004`, `-rocky8`, `-arm64`. Each comes with a
  `.sha256`, alongside `dslx_stdlib.tar.gz` and `libxls-*.so.gz`.
- **What we tested:** `opt_main-ubuntu2004` depends only on glibc. It runs on this host
  (glibc 2.39) and parses and re-prints a hand-written `fn`.
- **Why IVPM's `gh-rls` can't use it directly:**
  - it installs a single archive (`.tar.*` or `.zip`);
  - its platform matching doesn't recognize `ubuntu2004` or `rocky8`;
  - the release has no `export.envrc` to put the tools on `PATH`.
- **Plan:** a repackaging repository (`edapack/xlsynth-bin`, the same pattern as
  `verilator-bin`). It publishes a manylinux-tagged tarball containing `bin/`,
  `share/xls/dslx_stdlib` and `export.envrc`. `ivpm.yaml` then pins it with
  `version: vX.Y.Z`.

---

## 8. Decisions to make in X0

| # | Question | Recommendation |
|---|---|---|
| D-1 | Divide or modulo by zero | Reject unless the divisor is a non-zero constant or the operation is inside `if (d != 0)`. The 2-state SV result is X→0, but that differs between simulators. XLS returns all ones. |
| D-2 | Packed multi-dimensional arrays | **Decided (revised): flatten to bits plus slices.** The original recommendation (XLS array + `packed` flag, "layouts match") was wrong: DSLX's array↔bits convention puts element 0 in the **MSBs** (`u8[2] as u16` lowers to `concat(a[0], a[1])`), while an SV packed array's element 0 is in the LSBs (for a `[N-1:0]` range). pyslang already treats packed arrays as integral, so the front end maps an element select to an `ExprPartSelect` at `(i - lo) * W`. Out-of-range selects then read 0 and write nothing, as in SV, through `dynamic_bit_slice` / `bit_slice_update`. *Note (X1-4):* at the Verilog **ports**, XLS does put array element 0 in the LSBs, as SV does. Only the in-IR array↔bits conversion is reversed. The decision stands, because the lowering converts inside the IR. |
| D-10 | Packed structs | **Decided: bit vectors in X0.** Field access maps to `ExprPartSelect` and a pattern to `ExprConcat`. That is exactly SV and needs no IR flag. An XLS tuple has the same layout (element 0 = MSB), so presenting payloads as tuples is a later change to the types alone, not to the semantics. |
| D-11 | What a failing assertion stops | **Decided: an assertion is a check, not a gate.** In simulation (Verilator, the interpreter) execution stops at the failing assert. In XLS-generated RTL the assert is a simulation check (`$fatal` under `ASSERT_ON`), and the hardware still completes the failing activation's other effects. Conformance therefore compares effects up to the failing activation. The RTL may add that activation's effects: at most one per channel, by P10. Gating effects on the assert condition would put the check into the hardware, which is not what an SV `assert` means. |
| D-3 | Arithmetic shift | Add `BinOp.ARShift`. Overloading `RShift` by operand signedness is fragile once casts are involved. |
| D-4 | `for` loops | Unroll in X0, which is exact and simple. `counted_for` once XLS QoR or IR size shows a need. |
| D-5 | Predicated state updates | One unpredicated `next_value` per element, with its value merged through `sel`. This is the safe form recommended by XLS's `ir_semantics.md`. |
| D-6 | Effect order | Program order only. `fork…join` comes later. |
| D-7 | How widths are carried | Explicit casts plus bottom-up inference (R1), with no `dtype` field on `Expr`. Revisit if the inference has more than a handful of special cases. |
| D-8 | Temporaries | Separate them from state in the IR (R5). The proc lowering must never have to guess. |
| D-9 | Channel-op IR form | Keep the existing SPL `ExprAwait(ExprCall(port.get/put))` shape. `spl2rtl` already consumes it, and one form serves both the SPL and XLS paths. |

---

## 9. Risks

1. **Common-mode misreading.** Our emitter and our interpreter could share a mistaken
   reading of XLS semantics. Mitigations: separate implementation, op tests taken from the
   docs, and X1-2 as the first XLS task. The **residual risk is accepted**; it is the
   price of not waiting for XLS.
   - *Status:* largely retired for functions. XLS's own constant folding agrees with
     our interpreter on every op (widths 1–65) and on every function vector in the
     suites; it also caught one rule the docs omit. For procs it is still open (X1-2).
2. **Syntax drift.** XLS IR text has changed in the past (procs especially). Pin a
   commit, take reference `.ir` files from that commit, and keep the printer to one module.
   - *Status:* pinned to xlsynth v0.59.0, with reference files in
     `zuspec-be-xls/tests/unit/data/xls_ref/` and a byte-exact round-trip test.
3. **Front-end changes break existing paths.** Typed ports (FE-8) and the temporary/state
   split (FE-7) touch what SPL→FSM consumes. Run the existing `tests/` suite on every
   front-end change, and add options where needed.
   - *Status:* avoided by a separate static mapper; the SPL mapper is untouched.
     Converging them is FE-13.
4. **pyslang representation surprises** (packed structs reported as integral, Conversion
   chains, how class specializations appear). Add them to
   `pyslang11-ast-notes` as they turn up.
   - *Status:* several turned up and are recorded there:
     - propagated vs implicit conversions;
     - `str(SVInt)` abbreviation;
     - `'0`/`'1` values;
     - unpacked parameters and enum values without `.constant`;
     - output arguments as `Assignment(…, EmptyArgument)`;
     - the forward typedef of an interface class.
5. **The Verilator class/timing subset.** The proc harness depends on Verilator's
   `--timing` support for class tasks. `tests/intf_pc` shows the pattern works; if a
   construct is unsupported, fall back to the commercial simulator in CI or to a module
   wrapper.
   - *Status:* the harness works (`fw_component_root` + clock bridge, `--timing`).
   - **Two oracle holes found**:
     - out-of-range *packed* selects wrap instead of reading 0 (not LRM 11.5.1);
     - two specializations of one parameterized class in one build can share a nested
       payload type.

     Workarounds: in-range vectors with an LRM model for those cases, and one
     specialization per build.
   - **A third hole**, found by the 100k fuzz campaign: a 1-bit operand with the
     unsized literal `1` (`b ~^ 1`, `~(b ^ 1)`) is evaluated at 1 bit when it is a
     `?:` or `if` condition. The LRM makes it 32 bits, so it is true. Assignments and
     `&&`/`||`/`!`/`|()` operands are correct. Workaround: the fuzzer writes
     conditions as `|(c)`, and the bare forms are pinned to LRM values
     (`micro/lrm_pins_pkg.sv`).
   - **New risk 6:** Verilator is not a complete oracle. A commercial simulator run of
     the corpus (or at least the micro tests) before X1 would close these holes.

---

## 10. Exit criteria for X0

- ◐ Every §3 row has: a matrix entry, front-end support, an emitter golden, a directed
  conformance test, and an exhaustive test where it applies.
  - **Met**, except: goldens are per design (BX-7), not per row; and out-of-range packed
    selects (E11/E13) are checked against an LRM model, because Verilator wraps the
    index (§11).
- ☑ C1–C4 pass their reference vectors on Verilator **and** in the interpreter on the
  emitted `.ir`, with identical traces.
  - CRC-32 `0xCBF43926`; RLE at W=8 and W=4; AES-128 per FIPS-197 B and C.1;
    AES-128-CTR per SP 800-38A F.5.1.
  - The functions are also evaluated by XLS.
- ☑ The fuzzer runs ≥100k expressions with no mismatches.
  - 100 batches × 1,000 random functions × 8 vectors (seed 9001), three ways.
  - Two functions disagreed with Verilator, and both were Verilator bugs (the third
    hole in risk 5). XLS agreed with our interpreter on both.
  - With conditions written as `|(c)`, the flagged batches pass. The two functions
    are pinned to their LRM values.
- ☑ The negative suite: every rejected construct gives one diagnostic with its SV
  location (`tests/xls/test_negative.py`).
- ☑ The existing fw-hdl test suite still passes, **relative to its baseline**.
  - `tests/python`: 42 failures, all in regmap/MMIO, and they were already failing
    before X0 (§11). The library-list and forward-typedef fixes took it from 75 to 42.
  - ir-core 89 and be-sv 187 pass.
  - zuspec-synth: my ir-core changes add no failures, and they fix 52 tests that were
    erroring at baseline.
- ◐ The X1 checklist (§7) is ready to run, with the pinned XLS commit chosen:
  **xlsynth v0.59.0**.
  - X1-1 through X1-6 are done early.
  - X1-0 (the `edapack/xlsynth-bin` repackaging for `ivpm.yaml`) is still to do.

---

## 11. Log

| Date | Item | Note |
|---|---|---|
| 2026-10-03 | — | Plan written. `packages/zuspec-be-xls` created (empty). |
| 2026-10-03 | BX-0/1, XT-1..5 | **Syntax pinned to xlsynth v0.59.0.** XLS's own binaries are in the session scratchpad, not the workspace. `ir_converter_main` printed reference procs and functions from DSLX. The printer reproduces all six reference files byte for byte. |
| 2026-10-03 | XT-5 | **Function semantics checked against XLS without `eval_ir_main`.** `opt_main` folds a call on literal arguments to a literal, so `xls_eval_fn_batch` gets XLS's answer for any function. The differential matches XLS on every op at widths 1–65. A failing assert survives folding, so it is detected too. |
| 2026-10-03 | XT-2 | **Doc gap found:** XLS requires `dynamic_bit_slice` width ≤ operand width. `ir_semantics.md` doesn't say so; the verifier rejected it. Added to `typecheck.py` and the builder. |
| 2026-10-03 | R2, R3, R10, R11 | IR additions in zuspec-ir-core: `ExprConcat`, `ExprReplicate`, `ExprPartSelect`, the reduction `UnaryOp`s, `BinOp.ARShift`, `Arg.datatype`. be-sv renders all of them. The ir-core (89) and be-sv (187) suites pass. |
| 2026-10-03 | BX-2..4 | **Lowering done on hand-built IR.** 51 tests pass, and with `opt_main` present every emitted package also parses in XLS and every function vector matches it. **Bug found by the SV-model test:** a narrow signed index (`s3` −4 = `0b100`) aliased array element 4 in both `array_index` and `array_update`. Signed indices are now sign-extended one bit past the array's range. |
| 2026-10-03 | D-2, D-10, R5, R8 | Packed arrays and structs stay bit vectors (the layout note is in D-2). Temporaries are `StmtAnnAssign` locals, so R5 and R8 need no IR change. |
| 2026-10-03 | (pre-existing) | **The fw-hdl FE suite was red at HEAD**: 75 of 129 failed, because the SV library had outgrown the front end. Two minimal fixes: (1) `fe/parser.py` `FW_LIB_FILES` lacked `fw_clock_period_xtor_if.sv`; (2) `src/fw_event_set.svh` forward-declared an interface class as `typedef class`. LRM 6.18 says `typedef interface class`, slang rejects the other form, and Verilator accepts both. Also added `Parser.parse(include_root=False)`: a class-only design otherwise elaborates `fw_root` as a top with `Tbind=int`. **42 still fail, all in register-map/MMIO** (`regmap` sizes come out 0). They fail identically with my ir-core/be-sv changes stashed, so they are pre-existing and out of X0 scope. **This is the baseline for the exit criterion "the existing suite still passes".** |
| 2026-10-03 | FE-1..11 (XLS path) | **The static-subset front end** is `python/fw/hdl/fe/static_mapper.py`, a separate mapper. The SPL mapper is unchanged, so the SPL→RTL path is untouched (FE-8 risk avoided). It is exact-width (every `Conversion` becomes an `ExprCast`, every constant is cast to its SV type), with typed ports, canonical get/put, temporaries vs state, packed struct/array selects as `ExprPartSelect`, constant arrays, functions and calls, `case`, `for`/`repeat`, immediate asserts, and source locations. The entry point is `fw.hdl.xls_flow` (`sv_to_xls`, `sv_functions_to_xls`). |
| 2026-10-03 | CH-1 | **SV → Verilator vs SV → XLS IR → interpreter vs XLS all agree** on 41 micro functions covering E1–E20, T5, T6, S3, S4, S6 and S8 (`tests/xls/test_micro_fn.py`, about 10 s). Two findings: |
| 2026-10-03 | FE-1 | **Bug found by conformance: propagated conversions.** `signed a * unsigned b` in a 16-bit context: Verilator `0x80`, ours `0xff80`. LRM 11.8.2: a context-determined operand takes the *propagated* type and is sign-extended only if **that** type is signed. Implicit (assignment) and explicit conversions extend by the **source** signedness. The front end now retags before extending when pyslang's `ConversionKind` is `Propagated`. |
| 2026-10-03 | CH-2 | **The proc harness works.** A generated `fw_component_root` + clock bridge feeds the get ports from queues and records the put ports, on Verilator with `--timing`. The P-row micro procs agree with the interpreter on streams and final state: the accumulator, prologue state vs temporaries, predicated get/put, and a struct payload. |
| 2026-10-03 | §6.2 | **Corpus C1–C4 pass:** CRC-32 (function and stream), RLE (W=8 and W=4), AES-128 (FIPS-197) and AES-128-CTR (SP 800-38A F.5.1, plus a counter wrap). **Doc bug:** the `rle_enc` listing in `chisel-xls-assessment.md` §4.4 is not legal SV, because the state variable `run` collides with task `run()`; it is renamed `cnt` in the corpus. **Verilator issue:** with both `rle_enc#(8)` and `rle_enc#(4)` elaborated in one build, the W=8 put port carried the 12-bit `pkt_t` of W=4. Each builds correctly alone, and a minimal class/interface-class repro does not show it. So the corpus compiles one specialization per build (`rle8_pkg.sv`, `rle4_pkg.sv`). |
| 2026-10-03 | FE-12 | The negative suite passes: 12 constructs, each rejected at its SV line. That includes C4's natural form (a `put` inside `for`), whose message points at the fix: move the loop into state. |
| 2026-10-03 | CH-4, CH-5 | Exhaustive (about 900 single-operator functions, over 50k vectors) and fuzz runs agree three ways (Verilator / interpreter / XLS). **The fuzzer has teeth:** with the FE-1 propagated-conversion fix reverted, both batches fail within the first ten functions. **A fuzz campaign found an FE bug:** `str(SVInt)` abbreviates wide values (`146'd892029...e6`). Constants are now read with `SVInt.toString(Hex, false)`, and `'0`/`'1` are handled (pyslang gives them as context-width SVInts; `hasUnknown` is a property on SVInt). |
| 2026-10-03 | BX-7, BX-8, R9 | Goldens for 9 corpus and micro packages. `BlockSignature`/`ChannelSignature` added to ir-core; `predict_signature` and `CodegenOptions` added to be-xls. |
| 2026-10-03 | X1-6 | Checked early with `opt_main`: a provably in-range guard folds away. |
| 2026-10-03 | (side effect) | zuspec-synth's suite is red at baseline (63 failed, 138 errors). With the ir-core additions it is 53 / 96, and no test fails that didn't before. Some synth code already referenced nodes X0 added. |
| 2026-10-03 | CH-6 | Flow entry added (`tests/xls/flow.yaml`, `xls.xls-conformance` in the root `tests` task). It could not be run: `dfm` fails to start in this workspace (`ModuleNotFoundError: dv_flow.libyosys`), independent of X0. |
| 2026-10-03 | CH-1, risk 5 | **The oracle has a hole: Verilator does not follow LRM 11.5.1 for out-of-range selects on packed vectors.** It wraps the index (`x[8]` of a `bit [7:0]` reads `x[0]`; `x[i +: 4]` rotates), where the LRM says 0 for 2-state. Unpacked-array reads are correct (0). The normative semantics stay LRM, so commercial simulators, XLS and our emitter agree. Verilator vectors for packed selects stay in range, and out-of-range packed selects are pinned against an LRM model in the be-xls unit tests instead. |
| 2026-10-03 | CH-5 | **The 100k fuzz campaign** (100 × 1,000 functions × 8 vectors, seed 9001, about 16 min) found 2 mismatches. Both were **a third Verilator hole**: a 1-bit `b` with the unsized literal `1` (`b ~^ 1`, `~(b ^ 1)`) evaluates at 1 bit as a `?:`/`if` condition. `w = b ~^ 1` gives `fffffffe`, yet `(b ~^ 1) ? 7 : 3` gives 3. `~(b ^ 32'd1)` and wider operands are fine, so it looks like a peephole that ignores the literal's width. XLS agreed with our interpreter on both functions. The generator now writes `?:` conditions as `\|(c)`: self-determined and true iff nonzero, unlike `c != 0`, which widens `c`. The bare forms are pinned to LRM values (`check_functions_lrm`). |
| 2026-10-03 | X1-2, X1-3 | **Done early with `codegen_main`** (downloaded from the v0.59.0 release next to `opt_main`; the sha256 matches). The predicted signature matched XLS's module signature on the first run. XLS's RTL for every micro and corpus proc, at 1 and 2 pipeline stages, behind randomly throttled ready/valid, produces the interpreter's output streams. `p_assert`: the RTL fires `$fatal` with the message and the SV source line (`x reached 200 @ micro_proc_pkg.sv:157`), and also emits the failing activation's `put`. That is decided as D-11 (an assertion checks, it does not gate). |
| 2026-10-03 | X1-5 | `pos=` reaches the Verilog as comments (`--source_annotation_strategy=comment`). XLS prints positions 0-based, for DSLX too, so a comment's line is the SV line minus one. |
| 2026-10-03 | X1-4, XT-6 | **Array layout reversed in `xir.flatten`.** Codegen writes array element 0 in the LSBs (`{8'h33, 8'h22, 8'h11}` for `[0x11, 0x22, 0x33]`), as the original XT-6 said. The X0 "correction" had generalized the DSLX `as` cast, which is a different convention. Tuples are MSB-first as assumed. No X0 output changed: ports carry bit vectors (D-2, D-10). |
| 2026-10-03 | X1-2, CH-6 | Full `tests/xls` with `opt_main` + `codegen_main`: **37 passed**, including every corpus proc through XLS RTL at 1 and 2 stages. It now takes about 14.5 min, up from about 1 min. Almost all of that is Verilator's C++ compile of the AES-CTR RTL. For CI, pass `rtl_stages=(1,)` for C4, or run the RTL checks nightly. |
| 2026-10-03 | (next) | The integration phase is planned in `xls-phase2.md`: explicit per-component partition, XLS blocks through dv-flow (be-xls → libsynth), and a structural top built from signatures alone. |
