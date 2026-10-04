# Overview

## One model, many hosts

An fw-hdl design is written once, as SystemVerilog classes, and used in several
places:

| Host | What runs | What it is for |
|---|---|---|
| a SystemVerilog simulator | the classes themselves, on the fw-hdl runtime | a fast transaction-level model, debugged with ordinary SV tools |
| synthesis | the static subset of the classes, compiled through XLS | RTL, and from it gates on an ASIC or FPGA flow |
| a test bench | whichever of the above the level selects, behind one generated API | one test file that runs unchanged at every level |

The source stays plain IEEE 1800 SystemVerilog. It needs no preprocessor and no
code generator to simulate; Verilator and the commercial simulators run it as it is.

## The pieces

**Components** ({sv:class}`fw_hdl_pkg::fw_component`) form a tree. Each one builds its
children and ports in `build()`, connects them in `connect()`, and, if it is a
runnable ({sv:class}`fw_hdl_pkg::fw_runnable`), runs a `run()` task.

**Ports and exports** carry an API between components. A port
({sv:class}`fw_hdl_pkg::fw_port`) is the consumer: the component calls
`port.t.method(...)`. An export ({sv:class}`fw_hdl_pkg::fw_export`) is the provider.
The APIs are interface classes; {doc}`../reference/std` has the standard ones
(`put`, `get`, request/response, memory).

**Channels** ({sv:class}`fw_std_pkg::fw_channel`) join two components that both hold
ports, for example a producer's put port and a consumer's get port.

**Transactors** connect a port or export at the top of the tree to pins. The tree
itself never sees a signal; the design top binds its edge to interfaces with the
`` `fw_root_begin `` macros.

## What makes a design synthesizable

The same class source is synthesizable when it stays inside the **static subset**:

* 2-state types (`bit`, packed structs, fixed arrays), with SV's own semantics.
  Out-of-bounds reads give 0, out-of-bounds writes do nothing, and division needs a
  constant or guarded divisor.
* **Functions** that are pure and `automatic`. Each becomes an XLS function, then a
  combinational or pipelined module.
* **Components** whose `run()` is a `forever` loop of blocking `get`/`put` calls. Each
  becomes an XLS proc: one loop iteration is one activation; class properties are its
  state.
* **Structural components**, which only build and connect, become an RTL top that wires
  the blocks together.

{doc}`synthesis` has the details. {doc}`testing` shows how one test covers all of it.

## Semantics

The simulator's answer is the defined answer. For the static subset, 2-state SV
semantics are normative: widths come from SV's context rules, and the XLS back end
inserts whatever it takes to keep that meaning. Simulating the source on any
compliant simulator gives the reference result that every lower level must match.
