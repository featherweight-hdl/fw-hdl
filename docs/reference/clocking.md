# Clock domains and time

Every component has a `clock` port carrying its clock domain. These are the domain's
API, its implementations over a clock pin, and the quantum keeper for loosely-timed
models.

```{eval-rst}
.. autosvclass:: fw_hdl_pkg::fw_clock_domain_if
   :members:
   :undoc-members:

.. autosvclass:: fw_hdl_pkg::fw_clock_domain
   :members:

.. autosvclass:: fw_hdl_pkg::fw_clock_xtor_bridge
   :members:

.. autosvclass:: fw_hdl_pkg::fw_clock_period_xtor_bridge
   :members:

.. autosvclass:: fw_hdl_pkg::fw_quantum_keeper
   :members:
```
