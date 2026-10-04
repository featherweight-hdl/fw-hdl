<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/aes_ctr/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: aes_ctr_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/aes_ctr/aes_ctr_unit_test.sv
:language: systemverilog
:caption: aes_ctr_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/aes_ctr/flow.yaml
:language: yaml
:caption: aes_ctr/flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/aes/orig/xls/modules/aes/aes_ctr.x
:language: rust
:caption: xls/modules/aes/aes_ctr.x
```
