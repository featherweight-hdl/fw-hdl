# Modules and interfaces

The signal-level side: the root module that starts the class tree, the transactor
interfaces the bridges drive, and the ready/valid FIFO that `fw.hdl.spl.Integrate`
puts on a channel with a depth.

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
```
