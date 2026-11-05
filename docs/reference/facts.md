# Characterization facts

A fact says what a block's boundary does without looking inside it: its latency,
rate, capacity, combinational paths, registered ports and area. Facts let the
latency report, and later the system checks, reason about blocks whose insides no
engine sees, such as a [wrapped module](extern.md).

## Kinds

| SV method / sidecar `kind` | Core kind | Value |
|---|---|---|
| `latency(src, dst, fixed, min, max)` | `iface.latency` | `{src, dst, fixed}` or `{src, dst, min, max?}`: cycles from a value accepted on `src` to its result offered on `dst`. No `max` means unbounded; `max` alone means `min` 0 |
| `ii(port, n)` | `iface.ii` | `{port, n}`: one value every `n` cycles at most |
| — | `iface.throughput` | `{port, k, n}`: `k` values every `n` cycles |
| `capacity(src, dst, n)` | `iface.capacity` | `{src, dst, n}`: values accepted and not yet given, at most |
| `comb_path(src, dst)` | `iface.comb_path` | `{src, dst}`: `dst`'s handshake depends on `src`'s in the same cycle |
| — | `iface.stall_coupling` | `{a, b}`: back-pressure on `b` stalls `a` |
| `registered(port)` | `iface.registered` | `{port}`: the port's pins are driven or captured by flops |
| — | `timing.io_delay_ps` | `{port, ps}`: a delay budget at the boundary |
| `area(value, unit, source)` | `area.estimate` | `{value, unit, source?}`; `unit` is `um2`, `mm2`, `ge`, `cells`, `luts`, `ffs`, `brams` or `dsps` |

Ports are named by their RTL names: `in_0` for `in[0]`.

## Declaring facts in SV

Override `facts()` (`src/fw_facts.svh`). Ports are handles; loop over a port array:

```systemverilog
virtual function void facts(fw_facts f);
    foreach (req[i]) f.latency(req[i], rsp, .min(3), .max(40));
    f.ii(req[0], 1);
    f.area(18500, "um2", "synthesis 2026-10");
endfunction
```

The elaborator calls `facts()` after `connect()` on every leaf whose class (or a base
of it) defines one. A class and its wrapper may both declare facts; the most derived
`facts()` is the one that runs. A component with children may not define `facts()`:
its numbers come from its children. In a simulation `facts()` is never called.

Each error points at the `f.<kind>(...)` line, for example:

```
fact_pkg.sv:60:13: error: order_top.q: latency: min 3 > max 1
```

Other errors: a null port (`f.latency(in, null, ...)`), a port of another component,
`fixed` together with `min`/`max`, a value the kind does not accept.

## Sidecar files

For RTL with no SV class of its own (knob `design.extern`), or numbers that come from
a datasheet, list facts in a file named by knob `design.facts`:

```yaml
format: fw-hdl.facts
version: 1
blocks:
  - class: my_ip
    facts:
      - {kind: latency, src: "req[*]", dst: rsp, min: 3, max: 40}
      - {kind: area, value: 18500, unit: um2, source: "datasheet rev 2"}
```

`req[*]` stands for every element of the port array `req`; `req[2]` for one.
`class` is the child's class: its generic name, its specialization or its block
name. A `class` that names no leaf of the top is an error, and so is a port the class
does not have. Paths in `design.facts` are relative to the knob file.

## Provenance

Every fact goes into an overlay whose header says where it came from:

| Provenance | Source | Trust |
|---|---|---|
| `engine` | an engine built the block (XLS's schedule, say) | highest |
| `generator` | a library generator, exact for its parameters | |
| `measured` | a characterization run of the RTL | |
| `declared` | a person (`facts()` or a sidecar) | lowest |

A lower-ranked fact that contradicts a higher-ranked one on the same ports is a
conflict, reported rather than overridden: a latency range from a higher rank must lie
inside the lower rank's range, and the other compared kinds (`ii`, `throughput`,
`capacity`, `registered`, `io_delay_ps`) must be equal. Area estimates are not
compared. Reports mark a `declared` number **unverified** until a measured one agrees.

## Where facts go

- **The partition.** A leaf child's entry in `partition.json` has `facts`: each
  `{kind, value, provenance, unverified}`, with port arrays expanded.
- **Results bundles.** The Partition task writes one bundle per block with facts, under
  `facts/<module>/`: the block's anchors and an overlay of provenance `declared`.
- **The latency report.** A hop through a block nothing schedules (a wrapper, say) uses
  its `latency` facts. See [Reports](reports.md).
