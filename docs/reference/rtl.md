# Modules and interfaces

The signal-level side: the root module that starts the class tree, the transactor
interfaces the bridges drive, and the ready/valid FIFOs that `fw.hdl.spl.Integrate`
puts on a channel with a depth (in flops, or in a RAM).

```{eval-rst}
.. sv:module:: fw_root #(parameter type Tbind = int) (input clock, input reset)

   The elaboration root. Holds the class tree in reset; on the first clock after
   reset it constructs ``Tbind`` (an ``fw_component_root`` specialization, usually
   the ``<comp>_bind`` class that ```fw_root_begin`` declares), seats its clock domain
   on ``clock``/``reset`` through an ``fw_clock_xtor_if``, and forks its ``start()``.
   Asserting ``reset`` again kills the tree.

   Instantiated by ```fw_root_end``; a design top does not usually name it.

.. autosvsummary::
   :kinds: interface
   :files: fw_*_xtor_if.sv

.. autosvmodule:: fw_rv_fifo

.. autosvmodule:: fw_valid_check

.. autosvmodule:: fw_sram_fifo

.. autosvmodule:: fw_ram_1r1w_model
```

## `fw_rv_fifo` behaviour (normative)

The library's FIFO-bound classes rely on these points. A replacement FIFO (an XLS-internal
FIFO, a supplied wrapper, or `fw_sram_fifo`; see {doc}`../methodology/storage`) must keep
them:

| Property | `DEPTH >= 1` | `DEPTH == 0` |
|---|---|---|
| `in_rdy` | `count != DEPTH`, from registered state only | `out_rdy` (a wire) |
| `out_vld` | `count != 0`, from registered state only | `in_vld` |
| Bypass (a value in and out in the same cycle) | none: latency ≥ 1 | the handshake *is* the transfer |
| Push while full and popping | refused: there is no pass-through when full, so full rate needs `DEPTH >= 2` | — |
| Head | shown ahead: `out_data` is the oldest value while `out_vld` | `in_data` |
| Reset | synchronous, active high | — |

`DEPTH == 0` is safe to chain only because a block's valid never depends on its ready.
The boundary check (`fw.hdl.spl.Integrate`) enforces that.
