# Components, ports and exports

The kernel of `fw_hdl_pkg`: the component tree, its lifecycle, and the
deferred-binding port and export. {doc}`../methodology/components` explains how they
fit together.

```{eval-rst}
.. autosvpackage:: fw_hdl_pkg

.. autosvclass:: fw_hdl_pkg::fw_component
   :members:

.. autosvclass:: fw_hdl_pkg::fw_runnable
   :members:
   :undoc-members:

.. autosvclass:: fw_hdl_pkg::fw_elaboratable
   :members:
   :undoc-members:

.. autosvclass:: fw_hdl_pkg::fw_if_base
   :members:

.. autosvclass:: fw_hdl_pkg::fw_port
   :members:

.. autosvclass:: fw_hdl_pkg::fw_export
   :members:

.. autosvclass:: fw_hdl_pkg::fw_component_root
   :members:

.. autosvclass:: fw_hdl_pkg::fw_component_param
   :members:

.. autosvclass:: fw_hdl_pkg::fw_component_root_param
   :members:
```
