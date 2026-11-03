# Ready/valid kit

`src/std/rv`: a protocol kit for ready/valid streaming with a payload of any type `T`.
A class talks to it through an API; the kit's transactors turn that into pins. One beat
moves on each cycle where `valid && ready`.

| Role | API (`fw_rv_pkg`) | Endpoint on the class | Transactor module | Pins (`fw` style) |
|---|---|---|---|---|
| initiator | `fw_rv_initiator_if #(T)`: `send(t)` | port | `fw_rv_initiator_xtor` | `<ep>` out, `<ep>_valid` out, `<ep>_ready` in |
| target | `fw_rv_target_if #(T)`: `put(t)` | export | `fw_rv_target_xtor` | `<ep>` in, `<ep>_valid` in, `<ep>_ready` out |
| monitor | `fw_rv_monitor_if #(T)`: `observe(t)`, a function | export | `fw_rv_monitor_xtor` | all inputs |

**Adapters** put the std APIs on the same pins, so a component written against
`fw_put_if` or `fw_get_if` needs no change:
- `fw_put_to_rv_bridge #(T)`: a put port onto an initiator. `put()` queues the beat
  and blocks while the transactor's FIFO is full, so no beat is lost while `ready` is low.
- `fw_get_from_rv_bridge #(T)`: a get port from a target. `get()` takes the next beat
  and blocks while none has arrived.

Each transactor has three parts:
- an **interface** (`*_xtor_if`) that the bridge holds. It has a small FIFO, so the
  caller can run a few beats ahead of the pins.
- a **core** (`*_xtor_core`): a clocked FSM that runs the pin protocol. The cores are
  the kit's only synthesizable RTL.
- a **module** (`*_xtor`) that joins the two over an internal ready/valid link.

Payloads are `type T` everywhere except the cores, which take a width `W`. The module
passes `W = $bits(T)` to the core. Yosys's SV front end has no `type` parameters, and
the formal proofs read the cores through yosys.

Two Verilator 5.052 rules shape the SV:
- An interface used as a module port is declared without parameters (`fw_rv_initiator_xtor_if port`).
  A parameterized spelling crashes elaboration.
- The interfaces keep their FIFO in a ring buffer, not a queue. A queue in a
  parameterized interface reached through a virtual handle is not supported.

## Binding in a top

```systemverilog
fw_rv_target_xtor    #(.T(pkt_t)) u_in  (.clock, .reset, .data(in),  .valid(in_valid),  .ready(in_ready));
fw_rv_initiator_xtor #(.T(pkt_t)) u_out (.clock, .reset, .data(out), .valid(out_valid), .ready(out_ready));

`fw_root_begin(pkt_engine, u_root, clock, reset)
    `fw_root_bind_port(in,  u_in.u_if,  fw_get_from_rv_bridge #(pkt_t))
    `fw_root_bind_port(out, u_out.u_if, fw_put_to_rv_bridge   #(pkt_t))
`fw_root_end
```

## Kit descriptors

Each kit describes itself next to its SV, in the `zuspec.kit` v1 format (zuspec-synth
`docs/kits.rst`):
- `src/std/rv/fw_rv_kit.yaml` covers the three roles and the two adapters.
- `src/std/fw_put_kit.yaml` covers the put transactor.

Shell generation and lowering both read these descriptors through
`fw.hdl.kits.registry()`. A project adds its own kit directories to that call.

`fw.hdl.kits.check_kits` compares every descriptor with its module's real port list,
read with pyslang. A renamed pin fails that check instead of being mis-wired.

```{eval-rst}
.. autosvpackage:: fw_rv_pkg

.. autosvclass:: fw_rv_pkg::fw_rv_initiator_if
   :members:

.. autosvclass:: fw_rv_pkg::fw_rv_target_if
   :members:

.. autosvclass:: fw_rv_pkg::fw_rv_monitor_if
   :members:

.. autosvclass:: fw_rv_pkg::fw_rv_initiator_bridge

.. autosvclass:: fw_rv_pkg::fw_rv_target_bridge

.. autosvclass:: fw_rv_pkg::fw_rv_monitor_bridge

.. autosvclass:: fw_rv_pkg::fw_put_to_rv_bridge

.. autosvclass:: fw_rv_pkg::fw_get_from_rv_bridge

.. autosvsummary::
   :kinds: module, interface
   :files: fw_rv_*.sv
```
