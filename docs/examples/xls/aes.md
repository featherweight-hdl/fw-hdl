<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/aes/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: aes_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/aes/aes_unit_test.sv
:language: systemverilog
:caption: aes_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/aes/flow.yaml
:language: yaml
:caption: aes/flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/aes/orig/xls/modules/aes/aes.x
:language: rust
:caption: xls/modules/aes/aes.x
```

```{literalinclude} ../../../examples/xls/aes/orig/xls/modules/aes/aes_common.x
:language: rust
:caption: xls/modules/aes/aes_common.x
```

```{literalinclude} ../../../examples/xls/aes/orig/xls/modules/aes/constants.x
:language: rust
:caption: xls/modules/aes/constants.x
```
