<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/idct_chen/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: idct_chen_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/idct_chen/idct_chen_unit_test.sv
:language: systemverilog
:caption: idct_chen_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/idct_chen/flow.yaml
:language: yaml
:caption: idct_chen/flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/idct_chen/orig/xls/examples/jpeg/idct_chen.x
:language: rust
:caption: xls/examples/jpeg/idct_chen.x
```
