# Registers and events

The register model is part of the kernel: a register is another API carried over
ports and exports. Event sets let a model wait on any of several sources.

```{eval-rst}
.. autosvsummary::
   :packages: fw_hdl_pkg
   :kinds: class
   :files: fw_reg*.svh
   :members:

.. autosvclass:: fw_hdl_pkg::fw_event_set
   :members:

.. autosvclass:: fw_hdl_pkg::fw_awaitable_if
   :members:
   :undoc-members:
```
