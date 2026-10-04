# Observability

The debug facility: every component has a `dbg` port, its debug context, which a
bench can attach a listener to at any depth without modifying the component.

```{eval-rst}
.. autosvsummary::
   :packages: fw_hdl_pkg
   :kinds: class
   :files: dbg/*.svh
   :members:
```
