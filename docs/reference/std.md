# Standard APIs and channels

`fw_std_pkg`: the transaction-level APIs that ride on the kernel's ports and exports,
the channels that join two ports, and the put transactor. The three channel kinds
(stream, valid-only, level) and when to use each are in
{doc}`../methodology/islands`.

```{eval-rst}
.. autosvpackage:: fw_std_pkg

.. autosvclass:: fw_std_pkg::fw_put_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_get_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_get_nb_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_put_step_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_valid_put_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_level_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_level_set_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_reqrsp_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_mem_if
   :members:
   :undoc-members:

.. autosvclass:: fw_std_pkg::fw_channel
   :members:

.. autosvclass:: fw_std_pkg::fw_channel_put_ex

.. autosvclass:: fw_std_pkg::fw_channel_put_step_ex

.. autosvclass:: fw_std_pkg::fw_channel_get_ex

.. autosvclass:: fw_std_pkg::fw_channel_get_nb_ex

.. autosvclass:: fw_std_pkg::fw_valid_channel
   :members:

.. autosvclass:: fw_std_pkg::fw_level_channel
   :members:

.. autosvclass:: fw_std_pkg::fw_put_xtor_bridge
   :members:

.. autosvclass:: fw_std_pkg::fw_reg_component
   :members:

.. autosvclass:: fw_std_pkg::fw_reg_level
   :members:

```
