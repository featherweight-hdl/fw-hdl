<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/rle/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: rle_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/rle/rle_unit_test.sv
:language: systemverilog
:caption: rle_unit_test.sv
```

```{literalinclude} ../../../examples/xls/rle/rle_loop_unit_test.sv
:language: systemverilog
:caption: rle_loop_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/rle/flow.yaml
:language: yaml
:caption: rle/flow.yaml
```

```{literalinclude} ../../../examples/xls/rle/loop_flow.yaml
:language: yaml
:caption: rle/loop_flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/rle/orig/xls/modules/rle/rle_common.x
:language: rust
:caption: xls/modules/rle/rle_common.x
```

```{literalinclude} ../../../examples/xls/rle/orig/xls/modules/rle/rle_enc.x
:language: rust
:caption: xls/modules/rle/rle_enc.x
```

```{literalinclude} ../../../examples/xls/rle/orig/xls/modules/rle/rle_dec.x
:language: rust
:caption: xls/modules/rle/rle_dec.x
```
