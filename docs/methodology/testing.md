# Testing: one test, every level

A test calls the design through an **API**. The API is generated from the design's
SV: an interface class with one task per function, or one task per port of a
component. The test asks for the API and never names what answers it. So the same
test file, unedited, runs at every level:

| Level | The API is answered by |
|---|---|
| `model` | the SV itself: functions are called, components run on the fw-hdl runtime |
| `rtl` | XLS's Verilog of the SV, through generated transactors on its pins |
| `gates` | Yosys's generic netlist of that Verilog |
| `gates-ice40`, `gates-ecp5` | the iCE40 and ECP5 netlists, with Yosys's cell models |

The tests use stock [SVUnit](https://github.com/svunit/svunit): its macros, its runner,
its reports. There is no fw-hdl test language.

## Functions

For a package of functions, `fw.hdl.api.Functions` generates
`<pkg>_api_pkg`. Each function becomes a task with the same arguments plus an
`output` for the result. It is a task because a call takes time when RTL answers it.

```{literalinclude} ../../examples/xls/crc32/crc32_unit_test.sv
:language: systemverilog
:start-at: module crc32_unit_test
:end-before: SVUNIT_TESTS_END
```

## Components

For a component, `fw.hdl.api.Components` generates an API with one task per port:
`<port>_put(v)` for a get port of the design (the test supplies the value), and
`<port>_get(v)` for a put port (the test takes the value). A `#[test_proc]` from DSLX
becomes a test that puts stimulus and gets results:

```{literalinclude} ../../examples/xls/rle/rle_unit_test.sv
:language: systemverilog
:start-at: SVTEST(RunLengthEncoderCountSymbolTest)
:end-at: SVTEST_END
```

At `model` the component runs on the fw-hdl runtime. At `rtl` and the gate levels each
API task drives or collects a ready/valid channel on the block's pins.

## How a level is selected

`fw.hdl.api.ModelBinding` and `fw.hdl.api.XlsBinding` each define a module named
`<api>_harness`. The test bench instantiates the harness, and the level decides which
file defines it. In a flow, the level is an axis of the test's matrix, and choosing one
picks the fileset:

```
dfm run tests                                  # every example, every level
dfm run tests --tests crc32,rle --views rtl    # some of them, one level
```

A failure is the same test, the same call and the same message at every level. A
mismatch found at gates can be debugged at `model` in milliseconds.

## Determinism

The tests compare streams of values, not cycle timings. For functions and for networks
of blocking components (see {doc}`components`), that comparison holds at every level,
whatever the pipeline depth XLS chose. A component that polls (`try_get`) is not
determinate. Its test has to accept the timings each level can produce; the
{doc}`../examples/xls/lfsr` example shows how.
