<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/prefix_sum/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: prefix_sum_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/prefix_sum/prefix_sum_unit_test.sv
:language: systemverilog
:caption: prefix_sum_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/prefix_sum/flow.yaml
:language: yaml
:caption: prefix_sum/flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/prefix_sum/orig/xls/examples/prefix_sum.x
:language: rust
:caption: xls/examples/prefix_sum.x
```
