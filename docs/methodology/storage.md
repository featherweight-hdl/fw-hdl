# Storage binding

Storage is most of a design's area. fw-hdl keeps **what** a design stores apart from
**what holds it**:
- the source names logical storage, such as an `fw_channel #(T, DEPTH)`;
- the knob file chooses what holds it, per instance;
- the source, the class model and the contracts are the same for every binding.

This page is about **binding storage between and beside blocks**: channels, and memories
that a step class holds as members. A binding is a knob, it keeps the storage's timing
cycle for cycle, and so it changes area, not behaviour.

It relates to the storage model of {doc}`timing` (Storage) as follows:
- **Arrays inside a process** are the other half. There, the engine chooses a realization
  for each array field, from the target's list, and `(* fw_storage="..." *)` in the
  source is a requirement that a knob may override per build. That model is read by
  the front end and not yet acted on.
- **Port capacity.** A binding here has a fixed capacity: one push and one pop per
  cycle for a FIFO, one access per cycle for `fw_sp_mem`. The source is written to it
  (a step class makes at most one access per cycle). In the storage model an engine
  spreads the accesses of untimed code over cycles to fit the capacity instead.
- **XLS-specific parts.** `xls_fifo`, the `island.groups` column, the
  `fw_xls_fifo_wrapper` and the `register_push_outputs` setting below belong to the XLS
  engine (a group is one XLS package). Bindings between blocks (Integrate) and `fw_sp_mem`
  don't depend on the engine.

## Binding a channel

The knob `storage:` maps an instance path below the top to a binding. `default`
applies to every channel that holds values.

```yaml
storage:
  default: {bind: flops}
  q:       {bind: sram}                                  # the store between two blocks
  sub.r:   {bind: wrapper, module: my_fifo, files: [rtl/my_fifo.sv]}
```

| `bind` | channel between blocks (Integrate) | channel inside an `island.groups` group |
|---|---|---|
| `flops` (default) | `fw_rv_fifo` | `fw_xls_fifo_wrapper`, which wraps `fw_rv_fifo` |
| `wrapper` | `module:`; it has `fw_rv_fifo`'s ports and parameters | `module:`; it has the ports XLS gives a FIFO module (`push_*`, `pop_*`, `Width`, `Depth`, ...) |
| `xls_fifo` | an error: no XLS package holds the channel | the FIFO XLS writes itself (`--materialize_internal_fifos`) |
| `sram` | `fw_sram_fifo`, with the RAM `macro:` beside it | an error: XLS's FIFO module has no RAM ports, so move the channel out of the group |

`files:` lists a wrapper's or a RAM module's sources, relative to the knob file.
Integrate adds them to the RTL file list.

**Every binding has the timing of `fw_rv_fifo`, cycle for cycle:**
- `in_rdy` comes from the FIFO's own state;
- a value is visible the cycle after it is pushed;
- a full FIFO takes no push, even in a cycle where it is popped.

So changing a binding changes area, not behaviour.
- **XLS's own FIFO.** Left to itself, the FIFO XLS writes would take a push while
  full if a pop happens in the same cycle. The flow declares every in-package channel
  of depth 1 or more with registered push outputs (`register_push_outputs=true`),
  which turns that off.
- **A wrapper** must keep the same rules.

## The SRAM FIFO

`fw_sram_fifo` (`src/rtl/`) keeps most of its values in a two-port RAM: one write and
one read per cycle, with the read data registered one cycle after the read.

**How it keeps `fw_rv_fifo`'s timing:**
- The head is always in a two-entry output stage in flops, so `out_data` never waits
  on a read.
- A push goes straight to the output stage while the RAM is empty and the stage has
  room. Otherwise it goes to the RAM.
- A read is issued whenever the stage has room for its data, counting the read in
  flight. This keeps the stage fed at one value per cycle.

**Sizes:**
- The RAM has `DEPTH - 1` words. The head is never in it, so a write never meets the
  read in the same word.
- `DEPTH` must be 3 or more. Below that, flops are smaller anyway.
- `read_latency`, if given, must be 1.

**The RAM is a separate instance** named by `macro:`, with these ports:

| Port | Direction | Meaning |
|---|---|---|
| `clk` | in | clock |
| `wa`, `we`, `wd` | in | write address, enable, data |
| `ra`, `re` | in | read address, enable |
| `rd` | out | read data, valid the cycle after `re`, held until the next read |

and the parameters `WIDTH` and `WORDS`.
- **Default model.** When `macro:` is not given, the RAM is `fw_ram_1r1w_model`, a
  behavioural model for simulation.
- **A real memory.** Write a shim with these ports that instantiates the cell, and
  name it in `macro:`.

## Binding a memory

A step class may keep an array in a RAM: an `fw_sp_mem #(T, WORDS)` member
({doc}`../reference/lib`). Its block has the ports `<mem>_req` and `<mem>_rd`, and
Integrate places a RAM beside it on those ports. The knob key is `<child>.<mem>`:

```yaml
storage:
  tbl.mem: {bind: sram, macro: my_ram_shim, files: [rtl/my_ram_shim.sv]}
```

| `bind` | The RAM Integrate places |
|---|---|
| `flops` (default) | `fw_ram_1rw_model`, a flop array |
| `sram` | `macro:` (default `fw_ram_1rw_model`), a shim with the ports below |
| `wrapper` | `module:`, with the ports below |

Every one has a 1-cycle read, which is the memory's own timing, so a binding changes area,
not behaviour.

The RAM's ports:

| Port | Direction | Meaning |
|---|---|---|
| `clk` | in | clock |
| `en` | in | an access this cycle |
| `we` | in | the access is a write (otherwise a read) |
| `a`, `wd` | in | address, write data |
| `rd` | out | read data, valid the cycle after a read, held until the next read |

The parameters are `WIDTH` and `WORDS`. `read_latency`, if given, must be 1.

## What may be bound

| Class | Bindings |
|---|---|
| `fw_channel` | `flops`, `wrapper`, `xls_fifo`, `sram` |
| `fw_valid_channel` | `flops`, `wrapper`, `sram` |
| `fw_level_channel`, any channel of `DEPTH` 0 | none: it holds no values |
| `fw_sp_mem` (a member) | `flops`, `wrapper`, `sram` |
| `fw_keyed_table`, `fw_token_pool`, `fw_slot_reserve`, `fw_dep_tracker` | `flops` only: each reads every entry each cycle |

The library registry records what each class allows.

**Errors.** Each of the following is an error that names the knob key:
- a binding the class does not allow;
- a key that names no instance;
- `sram` below DEPTH 3;
- `xls_fifo` between blocks;
- `sram` inside a group;
- two channels in one group with different bindings. A group is one XLS package, and
  one package takes one FIFO form.

## The storage report

Partition writes `storage.json` and `storage.txt` next to `partition.json`. They give,
for each channel:
- its depth and width;
- its binding and module;
- its bits in flops and in RAM. The bits in flops are unknown for a wrapper.

Memories are listed as well, with their words, their width and the RAM module. Tables
are listed with their binding, which is always flops.

```
instance                 bind       depth x bits  flop bits  RAM bits  module
q                        sram             6 x 12         24        60  fw_ram_1r1w_model
```

## Tests

- `tests/xls/test_sram_fifo.py`: `fw_sram_fifo` against `fw_rv_fifo` in lockstep, at
  several depths, under fill, drain and streaming traffic.
- `tests/xls/test_storage_binding.py`:
  - one source built with every binding, between blocks and inside a group, giving the
    same output stream cycle for cycle;
  - the errors;
  - the report;
  - the reference design's queue as flops and as an SRAM FIFO through dfm, against
    the class model, its contract and its latency report.
- `tests/stdlib/cosim/fw_channel_sram.yaml`: the SRAM FIFO against `fw_channel`'s
  contract and rules.
- `tests/xls/test_sp_mem.py`: a memory bound to flops, an SRAM shim or a wrapper, with
  the same stream cycle for cycle.
