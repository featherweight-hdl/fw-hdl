# The lowering registry

fw-hdl recognizes library classes through the zuspec lowering registry
(`zuspec.ir.core.LoweringRegistry`). An entry is keyed by an SV class's generic
name and a target, and it declares the parameters it takes:

```python
from zuspec.ir.core import global_registry
from fw.hdl.lib.registry import XlsLowering

def _my_text(params, name):           # params: {"T": 8, "DEPTH": 4}
    return f"package {name}\n\n..."  # an XLS IR package with one top proc

def register(reg):
    reg.register_external(
        "my_fifo", {"T": int, "DEPTH": range(1, 257)}, "xls",
        XlsLowering(_my_text, lambda p: ["in", "out"]), origin="my_pkg")
```

`params` maps each parameter to what it may be:
- a Python type: `int`, `str`, or `object` for anything;
- or a collection of the values allowed, such as a tuple of enumerator names or a
  `range`.

Parameters reach the lowering as Python values:
- an `int` parameter as an int;
- an enum parameter as its enumerator's name;
- a type parameter as its width in bits, or its name for a class type.

Local parameters are not passed.

Targets:

| Target | Lowering object | Used by |
|---|---|---|
| `xls` | `XlsLowering(text, ports)`: `text(params, name)` is the IR package; `ports(params)` lists the class's port names in the IR's order | Partition: the block's IR, and its ports for the predicted signature |
| `native` | `NativeLowering(kind)` | Partition: fw-hdl emits the RTL (`regblock`) |
| `elab` | `ChannelKind(kind)` or `PortApi(direction, flow, polls)` | the front end: which classes are channels and port APIs |

`lookup(name, params, target)` returns the entry with the checked parameters, or
`None` when there is no entry. It raises `RecognitionError` for a parameter the
entry does not take.

To load your entries, add a `zuspec.lowering` entry point:

```toml
[project.entry-points."zuspec.lowering"]
my_pkg = "my_pkg.lowering:register"
```

A plugin that fails to load does not stop runs that never look a name up. It is
recorded, and the next `lookup` raises `PluginLoadError`, so a recognized class
never lowers as if it were unknown. fw-hdl's own entries also register on first
use (`fw.hdl.lib.registry.registry()`).
