# F1 spike: zdc GCD through the neutral path (canary gaps)

Phase 0, item F1 (`phase0-plan.md` §6). Date: 2026-11-01. No library code was changed.
The scratch scripts and logs are in `build/canary/`:
- `gcd_zdc.py`: the model (`Gcd` is the faithful version, `GcdSub` subtracts instead of using `%`, `GcdNe` uses `%` behind an `if b != 0` guard).
- `irdump.py`: a generic IR dumper.
- `sv_dump.py` / `sv_xls.py`: the SV reference.
- `zdc_dump.py`, `zdc_lower.py [raw|patched] <Class>`, `anchor_cmp.py`, `zdc_comp.py`.

## What worked

- **Authoring.** `gcd_euclidean` and `gcd_euclidean8` are plain methods on a `zdc.Component` with `zdc.u8` arguments, and they go through `DataModelFactory().build(Gcd)`. They land in `DataTypeComponent.functions`. The statement shapes match the SV front end's closely:
  - `StmtAnnAssign` / `StmtWhile` / `StmtIf` / `StmtAssign` / `StmtReturn`.
  - `ExprRefParam` for arguments and `ExprRefLocal` for locals.
  - The `self.gcd_euclidean(a, b)` call has the same IR shape as SV's `gcd_c::gcd_euclidean(a, b)`: `ExprCall(ExprAttribute(TypeExprRefSelf, 'gcd_euclidean'))`. That is the shape `lower_functions` resolves callees by.
  - SV desugars a `for` loop into init + `while` + increment, which is the shape zdc's `while` with an explicit index already has.
- **Statement `loc`.** Statements carry a `loc` with the absolute file and the correct line.
- **`assign_anchors`** runs on the zdc functions and on the whole zdc `Context` with no changes.
- **The rest of the path runs, but only with scratch-side IR patches.** The patches set the argument, return and local types, add 1 to the column, and wrap bare constants in casts. With them, `GcdSub` and `GcdNe` go through:
  - `lower_functions`, `format_package`, `opt_main` and `codegen_main` (pipeline, 2 stages, unit delay model);
  - `xls_overlay`.

  Results:

  | | zdc `GcdNe` | SV `gcd_euclidean8` |
  |---|---|---|
  | ops attributed | 73 / 73, 100% | 995 / 995, 100% |
  | exact | 0 | 78 |
  | merged | 73 | 917 |
  | crit-delay attributed | 100% | 100% |

  The `iface.block` value is **identical** to SV's when both use the same `--module_name`: latency 3, II 1, `clk` / `rst`, no channels.

## Gaps

Each gap is given as **symptom**, **root cause**, then **package / fix / size**.

1. **Argument and return widths are lost.**
   - Symptom: the arguments get `annotation=ExprConstant(<class int>)` and no `datatype`, and `returns` is `DataTypeInt(bits=-1)`. be-xls stops with "argument 'a' has no type" (`lower_fn.py:809`).
   - Root cause: `get_type_hints(member)` without `include_extras=True` drops the `Annotated` width (`data_model_factory.py:649`). On top of that, `_type_to_expr` (`:714`) and `_annotation_to_datatype` (`:720`) never resolve `U`/`S`.
   - Package: zuspec-dataclasses.
   - Fix: use `include_extras=True`. Set `Arg.datatype` and `returns` with `_resolve_field_type` (`:1336`), which already handles `Annotated[int, U(8)]`.
   - Size: **S**.
2. **Local declarations are untyped.**
   - Symptom: `r: zdc.u8 = ...` becomes a `StmtAnnAssign` with no `ir_type`, and its annotation stays `ExprAttribute(ExprRefUnresolved('zdc'), 'u8')`.
   - Root cause: `data_model_factory.py:3630-3638` never evaluates the annotation.
   - Package: zuspec-dataclasses.
   - Fix: evaluate the annotation against the scope globals (`_get_scope_globals`), then set `ir_type` with `_resolve_field_type`.
   - Size: **S**.
3. **There is no width or cast pass for zdc.**
   - Symptom: "Lt: operand widths differ (s32 vs u5); the front end must insert a cast" on `i < 16`. Every mixed-width `+`, `-` and `==` against a literal would fail the same way.
   - Root cause: the be-xls typing contract (`width.py:1-22`) requires the front end to resolve widths and write them as explicit `ExprCast`s. fw-hdl does this (`ExprCast` appears throughout the SV IR). zdc has no such pass, and nothing neutral exists: no `ExprCast` is built anywhere in zuspec-dataclasses or zuspec-ir-core.
   - Package: zuspec-dataclasses. The pass applies zdc's own semantics for Python integers on `uN` / `iN`; casting a constant operand to the other operand's type, as the scratch patch does, is the minimum.
   - Size: **M**. It becomes **L** if zdc's arithmetic width semantics first have to be specified.
4. **There is no `loc` on functions, arguments or expressions, and the column is 0-based.**
   - Symptom:
     - `Function.loc` and `Arg.loc` are `None`, so be-xls errors carry no location.
     - Expressions have no `loc`. XLS ops therefore get only statement positions, which gives 0 "exact" ops (against 78 for SV) and `sched.stage` facts only on statement anchors.
     - The columns are 0-based.
   - Root cause: `loc` is set only on statements, in `_convert_ast_body`: `data_model_factory.py:2410-2426`, with `pos=_node_col` at `:2419`. `_convert_ast_expr` (`:3674`) and `_extract_function` (`:704`) set none. A latent bug: for a class nested in a function, the columns are taken from the dedented class source (`:2230`).
   - Package: zuspec-dataclasses (this is F2).
   - Fix:
     - Set `pos = col_offset + 1` on statements, expressions, `Function` (from the `FunctionDef`) and `Arg`.
     - Add the dedent amount back for nested classes.
   - Size: **S–M**.
5. **Component base methods leak into `functions`.**
   - Symptom: `functions` also holds `__bind__`, `close`, `shutdown`, `time` and `wait`. `lower_component(Gcd)` fails with "type DataTypeRef is not in the static subset" (`lower_proc.py:165-167`).
   - Root cause: `inspect.getmembers(t)` walks the whole MRO, including `zdc.Component` (`data_model_factory.py:803-812`).
   - Package: zuspec-dataclasses. Optionally also zuspec-be-xls: lower only the functions reachable from `run()`.
   - Fix: collect only the methods defined on classes below `Component` in the MRO.
   - Size: **S**.
6. **The division guard misses the `else` form.**
   - Symptom: the faithful `if b == 0: pass` / `else: r = a % b` is rejected with "division by a value that may be zero". The same source written with `if b != 0` lowers.
   - Root cause: `_implies_nonzero` (`lower_fn.py:410-419`) accepts only `ne(d, 0)` and `and`. The else-branch condition is `not(eq(d, 0))`. This is neutral: SV hits it too.
   - Package: zuspec-be-xls (this is F3, with a hand-built IR unit test).
   - Fix: also accept `not(eq(d, 0))`, and `eq` under an odd number of `not`s.
   - Size: **S**.
7. **Argument annotations get anchors.**
   - Symptom: zdc has `gcd_euclidean.e1` and `.e2` (the argument annotation constants); SV has none.
   - Root cause: zdc puts the Python type object in `Arg.annotation` (`:663`, `:714`).
   - Package: zuspec-dataclasses. Fixed together with gap 1: leave `annotation=None` once `datatype` is set.
   - Size: **S**.
8. **An empty branch gives a different statement shape.**
   - Symptom: Python needs a `pass` in the empty `then` branch, so zdc emits a `StmtPass` (anchor `...body.s1`). SV emits an empty body.
   - Root cause: `data_model_factory.py:3639` (`ast.Pass` becomes `StmtPass`).
   - Package: one of two. Either zuspec-dataclasses drops a body that is only `pass`, or, more neutral, zuspec-ir-core's anchor pass does not number `StmtPass`.
   - Size: **S**.
9. **The SV front end leaks a shape: the function-name return variable.**
   - Symptom: every SV function gets a `StmtAnnAssign <fn>` as `s1` and a trailing `StmtReturn <fn>`, even when the body never uses the variable. Every statement index after it therefore shifts by one relative to zdc: SV `s3` is the `while`, zdc `s2`.
   - Root cause: `python/fw/hdl/fe/static_mapper.py:763-773`.
   - Package: fw-hdl, this repo (outside the three packages).
   - Fix: emit the variable and the trailing return only when the body references the variable.
   - Size: **S**.
10. **Expression numbering depends on the front end.**
    - Symptom: `eN` is a pre-order count within a statement. Anything the front end synthesizes therefore shifts it:
      - SV wraps `i` twice in `ExprCast` in `i < 16` and casts every literal;
      - SV's declaration annotation is 1 node (`ExprConstant('int')`), zdc's is 2 (`ExprAttribute` over `ExprRefUnresolved`).
    - Package: zuspec-ir-core (the A1 grammar).
    - Fix: do not number synthesized nodes, that is casts and annotations without a source `loc`. Alternatively, the canary compares statement anchors only.
    - Size: **M**.
11. **The reference designs use different algorithms.**
    - Symptom: SV computes `iterative_div_mod(a, b).r` (a call plus a part-select over a struct return); zdc uses `%`. The ops and the stage facts can never agree.
    - Fix: make the canary use the same operation on both sides. Either both use `%` behind a guard (the SV side then needs gap 6), or zdc ports `iterative_div_mod`; that port was not tried and would need struct returns, concatenation and part-selects in zdc.
    - Size: **S** for the `%` form.

## Anchor comparison

These are function-list roots, as the SV test uses. Passing the zdc `Context` instead roots the anchors at `Gcd.gcd_euclidean#...`, so the plan's "`gcd_pkg.gcd` vs `gcd_zdc.Gcd`" roots do not exist as such: the SV function path roots each function by its own name. Run `build/canary/anchor_cmp.py` to reproduce the counts.

| Anchors | Count |
|---|---|
| SV, `gcd_euclidean8` + `gcd_euclidean` (`iterative_div_mod` excluded) | 59 |
| zdc `Gcd` | 46 |
| Common to both | 14 |

The 14 common anchors are only the roots, `s1` and the first expressions of each function. Everything after the SV return variable is shifted (gap 9). The other differences are the `pass` (gap 8), the argument annotations (gap 7), and the casts and annotation nodes in expressions (gap 10).

**Statement anchors would match** once gaps 7, 8 and 9 are fixed, checked by hand. Both sides would then be `s1` (the `i` declaration), `s2` (the `while`), `s2.body.s1` (the `if`), `s2.body.s1.orelse.s1..s3`, `s2.body.s2` (the increment), `s3` (the return), plus `gcd_euclidean8#s1`.

## Recommendation for F4

**(a) Anchor sets equal modulo root:** not achievable now.
- After F2 (gaps 1, 2, 4, 7, 8) plus gap 9 in fw-hdl, **assert statement anchors** equal. All of these are size S.
- Keep **expression anchors as xfail** until gap 10 has a decision.
- Correct the plan's root naming. With function roots, the only difference is the top name (`gcd_pkg__gcd_euclidean8` against `gcd_euclidean8`), so pass the same `rename`.

**(b) `iface.block` equal:** achievable as soon as zdc lowers at all.
- With the scratch patches it is already byte-identical.
- It needs gaps 1–3; gap 3 (the cast pass) is the long pole. Make it a must-pass gated on F2.

**(c) `sched.stage` agree:** **xfail.** There are three blockers:
- The two designs schedule different ops (gap 11).
- zdc expressions have no `loc` (gap 4).
- The anchors are not aligned (gaps 9 and 10).

Revisit it once both sides use `%` and gaps 4 and 6 are fixed.

**(d) Overlays validate:** yes. The patched zdc overlays build, with 100% of ops attributed.
