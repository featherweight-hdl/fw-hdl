# Verilator reproducers from the K1 bare-name check

Found while checking the protocol macros' class-name form
([core-protocol-kit-prep.md](../../../core-protocol-kit-prep.md) §3.2,
decision 18).
Verilator 5.055 (the workspace's IVPM build). pyslang accepts all three
files with no diagnostics and gives the expected values.

```
verilator --binary -Wno-fatal --top-module top <file>.sv && ./obj_dir/Vtop
```

| File | Expected | Observed |
|---|---|---|
| `bug1_typedef_chain_decl.sv` | prints 16 | `%Error: Package/class for ':: reference' not found: 'this_t'` on `p::C#(16)::this_t::w_t x;`. The same chain in `$bits()` in a `localparam` resolves. |
| `bug2_localparam_genif_crash.sv` | prints 8 | `Verilator internal fault`, exit 139. Needs both a `localparam` set from `$bits(p::C#(8)::w_t)` and a generate-`if` on it; either alone is fine. No typedef chain is involved. |
| `bug3_typedef_chain_wrong_width.sv` | `bits16=16` | `bits16=8`: `rv_a#(16)::this_t::w_t` gets the default width. Not minimized: the plain-typedef version hits bug 1 instead, and what lets this one compile is not isolated. |

Comment lines in these files avoid starting with `// Verilator`, which
Verilator parses as a pragma (`BADVLTPRAGMA`).

**For fw-hdl:** generated and kit code must not reach class-scoped
typedefs through a `this_t` chain from module scope, and must not feed a
generate condition from `$bits()` of a parameterized class's typedef.
