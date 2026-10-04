<!-- The prose is the example's README.md; the sections below show the
     sources it describes. -->

```{include} ../../../examples/xls/gcd/README.md
```

## Reference: the SV port

Generated from the doc comments in the port's source.

```{eval-rst}
.. autosvpackage:: gcd_pkg
   :members:
   :undoc-members:
```

## Listing: the tests

```{literalinclude} ../../../examples/xls/gcd/gcd_unit_test.sv
:language: systemverilog
:caption: gcd_unit_test.sv
```

## Listing: the flow

```{literalinclude} ../../../examples/xls/gcd/flow.yaml
:language: yaml
:caption: gcd/flow.yaml
```

## Listing: the original DSLX

Unmodified, from the XLS repository at the tag in `orig/UPSTREAM`. Copyright The XLS Authors, Apache-2.0.

```{literalinclude} ../../../examples/xls/gcd/orig/xls/examples/gcd.x
:language: rust
:caption: xls/examples/gcd.x
```
