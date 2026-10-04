<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/lfsr/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: lfsr_pkg
   :members:
   :undoc-members:

.. autosvpackage:: lfsr_proc_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/lfsr/lfsr_unit_test.sv
:language: systemverilog
:caption: lfsr_unit_test.sv
```

```{literalinclude} ../../../examples/xls/lfsr/lfsr_proc_unit_test.sv
:language: systemverilog
:caption: lfsr_proc_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/lfsr/flow.yaml
:language: yaml
:caption: lfsr/flow.yaml
```

```{literalinclude} ../../../examples/xls/lfsr/proc_flow.yaml
:language: yaml
:caption: lfsr/proc_flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/lfsr/orig/xls/examples/lfsr.x
:language: rust
:caption: xls/examples/lfsr.x
```

```{literalinclude} ../../../examples/xls/lfsr/orig/xls/examples/lfsr_proc.x
:language: rust
:caption: xls/examples/lfsr_proc.x
```
