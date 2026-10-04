<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/crc32/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: crc32_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/crc32/crc32_unit_test.sv
:language: systemverilog
:caption: crc32_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/crc32/flow.yaml
:language: yaml
:caption: crc32/flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/crc32/orig/xls/examples/crc32/crc32.x
:language: rust
:caption: xls/examples/crc32/crc32.x
```
