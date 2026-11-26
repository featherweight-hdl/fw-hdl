# Verilator reproducers from the task-sync crossing lowering

Found while running lowered crossings in mixed simulation
([xing-lowering-plan.md](../../../xing-lowering-plan.md) §4g).
Verilator 5.055 (the workspace's IVPM build). pyslang accepts the file
with no diagnostics.

```
verilator --binary -Wno-fatal --top-module top <file>.sv && ./obj_dir/Vtop
```

| File | Expected | Observed |
|---|---|---|
| `bug1_module_class_same_name.sv` | prints `R 1` | `Internal Error: ../V3Ast.h:1173: AstNode is not of expected type, but instead has type 'MODULE'`. Needs a module and a package class of the same name, both parameterized, specialized with the same value. Different values, an unparameterized side, or a module left at its defaults all compile. Whether the package is imported doesn't matter. |

**For fw-hdl:** a parameterized module emitted from a parameterized class
(`to_ir(parameterize=True)`, the default, when the module keeps a parameter) can't be simulated under Verilator
alongside that class at the same specialization, which is what a mixed
bench does. Such a bench renames the emitted modules (`emit_sv(rename=...)`).
