# The lowering registry

fw-hdl recognizes library classes through the zuspec lowering registry
(`zuspec.ir.core.LoweringRegistry`). An entry is keyed by an SV class's generic
name and a target, and it declares the parameters it takes.

Most library classes need no entry: a cycle step or an all-or-nothing step is mapped
from its `step()`. An entry is for a class whose body cannot be its implementation,
such as a staged variant of a simple model. Its lowering should build Zuspec IR (the
`zuspec` target), so that every backend and every check that reads Zuspec IR sees
the block:

```python
import zuspec.ir.core as ir
from fw.hdl.lib.registry import ZuspecLowering

def _my_block(params, name, ports):   # params: {"T": 8, "DEPTH": 4}
    comp = ir.DataTypeComponent(name=name, super=None,
                                fields=[ports["in"], ports["out"], ...], functions=[])
    comp.proc_processes = [ir.Function(name="run", is_async=True, body=[...],
                                       metadata={"fw_step": True})]
    return comp

def register(reg):
    reg.register_external(
        "my_fifo", {"T": int, "DEPTH": range(1, 257)}, "zuspec",
        ZuspecLowering(_my_block), origin="my_pkg")
```

`tests/xls/test_registry_zuspec.py` has a complete factory.

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
| `zuspec` | `ZuspecLowering(component)`: `component(params, name, ports)` returns a `DataTypeComponent` named `name`, whose port fields come from `ports` (the child's, by name) | Partition: the block, lowered like a class it mapped |
| `xls` | `XlsLowering(text, ports)`: `text(params, name)` is the IR package; `ports(params)` lists the class's port names in the IR's order. For an existing XLS proc; it bypasses every check on Zuspec IR | Partition: the block's IR, and its ports for the predicted signature |
| `native` | `NativeLowering(kind)` | Partition: fw-hdl emits the RTL (`regblock`) |
| `elab` | `ChannelKind(kind, bindings)`, `PortApi(direction, flow, polls, stalls)`, `StorageKind(bindings, why)` or `MemoryKind(ports, read_latency, bindings)` | the front end: which classes are channels, port APIs and memory members; the storage bindings a channel, a table or a memory allows ({doc}`../methodology/storage`) |

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
