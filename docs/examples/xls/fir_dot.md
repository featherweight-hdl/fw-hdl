<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/fir_dot/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: fir_dot_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/fir_dot/fir_dot_unit_test.sv
:language: systemverilog
:caption: fir_dot_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/fir_dot/flow.yaml
:language: yaml
:caption: fir_dot/flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/fir_dot/orig/xls/examples/fir_filter.x
:language: rust
:caption: xls/examples/fir_filter.x
```

```{literalinclude} ../../../examples/xls/fir_dot/orig/xls/examples/dot_product.x
:language: rust
:caption: xls/examples/dot_product.x
```
