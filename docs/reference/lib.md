# Library classes

Building blocks in `fw_std_pkg` whose cycle behaviour is part of their definition:
queues, credit senders, arbiters, keyed tables, and (to come) pools. Each class states:

- what it **observes** in a cycle;
- what it **consumes**;
- how **ties** break;
- whether a grant can depend on **same-cycle valid**.

The class model is a cycle step that implements exactly that, and the RTL is
checked against it cycle for cycle. A class whose output can be back-pressured is an
all-or-nothing step ({doc}`../methodology/components`): a cycle whose output is not
ready stalls, and changes nothing. Each class also has a **contract** (a YAML file next
to its source): the order and conservation rules any implementation must keep, whatever
its timing ({doc}`contracts`), or, for a table, the sequential table it must behave as. Any module that claims to implement a class can be
cosimulated against that contract ([Cosimulation](#cosimulation)).

| Class | Source | Form | Lowering |
|---|---|---|---|
| `fw_channel` | `src/std/fw_channel.svh` | queue between components | `fw_rv_fifo`, or a FIFO inside a multi-proc block |
| `fw_credit_tx` | `src/std/credit/` | cycle step | its `step()`, mapped |
| `fw_arbiter` | `src/std/arb/` | all-or-nothing step | its `step()`, mapped |
| `fw_keyed_table` | `src/std/table/` | all-or-nothing step | its `step()`, mapped |

## fw_channel

The queue between two components: a ready/valid FIFO of `DEPTH` values, or a wire for
`DEPTH` 0. It has no ports of its own. A producer's port connects to one of its put
exports and a consumer's port to one of its get exports.

```systemverilog
fw_channel #(type T, int DEPTH = 1)
```

| Export | API | For |
|---|---|---|
| `put_ex` | `fw_put_if #(T)` | a process's blocking `put()` |
| `put_step_ex` | `fw_put_step_if #(T)` | an all-or-nothing step's `put_or_stall()` |
| `get_ex` | `fw_get_if #(T)` | a process's blocking `get()` |
| `get_nb_ex` | `fw_get_nb_if #(T)` | a step's (or a polling process's) `try_get()` |

**Per cycle**, between steps (`DEPTH >= 1`).

| | |
|---|---|
| Observes | the values held at the start of the cycle. A put is accepted when fewer than `DEPTH` were held; a `try_get` sees the oldest of them |
| Consumes | at most one put and one take a cycle |
| Latency | one cycle: a value put in a cycle is offered from the next. There is no bypass |
| Full | a put is refused even in a cycle that takes a value (no pass-through when full). So `DEPTH` 1 runs at half rate, and full rate needs `DEPTH` 2 |

These are `fw_rv_fifo`'s rules ({doc}`rtl`). In process form, `put()` and `get()`
block and the network is a Kahn process network: the values do not depend on timing
or `DEPTH`. A rendezvous (`DEPTH` 0) holds one value, and its `put()` returns once the
value is taken.

A step may not use a `DEPTH` 0 channel. Its RTL is a wire, which moves a value in the
cycle it is put, but steps at one edge do not see each other's puts. The class model
stops with an error, and partition rejects the design at the channel's declaration.

**Contract** (`src/std/fw_channel.yaml`): one stream, in order, nothing lost or
duplicated, and at most `DEPTH` values held.

**Lowering.** Not a block. Between blocks, `fw.hdl.spl.Integrate` instantiates
`fw_rv_fifo`. Inside a multi-proc block (knob `island.groups`), XLS instantiates
`fw_xls_fifo_wrapper`, which is `fw_rv_fifo` under XLS's port names. Both have the same
timing.

**Tests.**
- `tests/stdlib/fw_channel_unit_test.sv` (SVUnit), on the model: empty, one-cycle
  latency, rate by depth, back-pressure, a stalled step's put kept, and the process
  form (a blocking put while full, a rendezvous). Order is checked throughout.
- `tests/xls/lib/test_fw_channel.py`: two steps joined by the channel at `DEPTH` 1, 2
  and 3, with the output back-pressured at random:
  - a Python model of the rules above against the class model;
  - the class model against the RTL (both blocks and `fw_rv_fifo`), cycle for cycle;
  - at 2 stages, lossless and in order.

  A step on a `DEPTH` 0 channel is rejected by partition and stops the model.
- `tests/xls/test_rv_fifo.py`: `fw_rv_fifo` under random traffic, and Yosys reads
  every `DEPTH`.
- Cosim (`tests/stdlib/cosim/fw_channel.yaml`): `fw_rv_fifo` and
  `fw_xls_fifo_wrapper` at `DEPTH` 2. Besides the contract, the driver checks that a
  module holds at most `DEPTH` values and has no bypass. `fw_rv_fifo` built 3 deep,
  or built as a wire, is expected to fail.

The class reference is in {doc}`std` ({sv:class}`fw_std_pkg::fw_channel`).

## fw_credit_tx

A credit-gated sender over `NVC` virtual channels, with a shared pool and a per-VC
reserve. Its output is valid-only: a value is offered only when its credits are held,
so the receiver never stalls it.

```systemverilog
fw_credit_tx #(type T, int CREDITS, int NVC = 1, int RESERVE = 0,
               fw_credit_policy_e POLICY = FW_CREDIT_POOL_FIRST, int CHECK = 1)
```

| Port | API | Carries |
|---|---|---|
| `in[NVC]` | `fw_get_nb_if #(T)` | the values for each VC |
| `cr` | `fw_get_nb_if #(bit [VB-1:0])` | credit returns: the VC one credit comes back to |
| `out` | `fw_valid_put_if #(bit [VB+$bits(T)-1:0])` | `{vc, value}` |

`VB` is `$clog2(NVC)`, and 1 when `NVC` is 1.

**Credits.**
- `CREDITS` is the receiver's buffer, in credits.
- At reset, the credits fill each VC's reserve (`RESERVE`) in VC order, and the rest
  go to the pool. With fewer credits than `NVC * RESERVE`, the later VCs start short.
- A value on VC `v` may be sent when `pool + reserve[v] >= CHECK`, and it spends
  `CHECK` credits:
  - `FW_CREDIT_POOL_FIRST` takes them from the pool first;
  - `FW_CREDIT_VC_FIRST` takes them from the VC's reserve first.
- A returned credit refills its VC's reserve up to `RESERVE`, then the pool.
- A return to a VC at or above `NVC` is dropped.

**Per cycle.**

| | |
|---|---|
| Observes | the credits and holds at the start of the cycle, and one credit return |
| Consumes | at most one value (one send), and one credit return |
| Ties (`NVC > 1`) | round robin over the VCs whose hold is full and whose credits cover `CHECK`, from the VC after the last one sent |
| Same-cycle valid | never decides a send. Every ready comes from registered state, and `cr` is always ready, so a credit return never waits behind data |

A credit returned in a cycle can be spent from the next cycle.

**Latency.**
- `NVC = 1` has no hold. `in[0]` is ready while the credits cover `CHECK`, and a value
  taken is sent in the same cycle. This is the shape of the `credit_tx` IR template, and
  the test checks the two cycle for cycle.
- `NVC > 1` has a one-value hold per VC. `in[v]` is ready while hold `v` is empty or
  is being sent this cycle. A value is sent from the cycle after it arrives, and one VC
  alone streams one value per cycle.

**Contract** (`src/std/credit/fw_credit_tx.yaml`):
- values leave in order within a VC (`per_key`);
- credits spent and not yet returned never exceed `CREDITS`.

**Lowering.** `step()` is mapped (no registry entry). Assign it to XLS by class name in
the knob file, like any component. One activation per cycle, at II=1.

**Tests.**
- `tests/stdlib/fw_credit_tx_unit_test.sv` (SVUnit): empty, credits exhausted and the
  reserve, return timing, round-robin tie, hold latency and rate, reset mid-traffic.
  The contract is checked throughout.
- `tests/xls/lib/test_credit_tx.py`: six parameter sets, with random closed-loop
  stimulus. It checks a Python model of the rules above against the class model, and
  the class model against the RTL cycle for cycle: at 1 and 2 stages, and with I/O
  flops on and off. It also checks `NVC = 1` against the `credit_tx` template.
- Cosim (`tests/stdlib/cosim/fw_credit_tx.yaml`, `fw_credit_tx_c4.yaml`): fw-hdl's own
  RTL, three VCs and one VC with `CHECK = 4`.

```{eval-rst}
.. autosvclass:: fw_std_pkg::fw_credit_tx
   :members:
```

## fw_arbiter

An `N`-input arbiter, accept-then-arbitrate: one hold per input, and a grant over the
full holds. Its output is a stream, so the consumer may back-pressure it.

```systemverilog
fw_arbiter #(type T, int N = 2, fw_arb_policy_e POLICY = FW_ARB_RR)
```

| Port | API | Carries |
|---|---|---|
| `in[N]` | `fw_get_nb_if #(T)` | the inputs |
| `out` | `fw_put_step_if #(bit [IB+$bits(T)-1:0])` | `{index, value}`: which input won, and its value |

`IB` is `$clog2(N)`, and 1 when `N` is 1.

**Policies.**
- `FW_ARB_RR`: round robin, the first full hold after the last winner. Input 0 goes
  first.
- `FW_ARB_PRIO`: fixed priority, the lowest full hold.

**Per cycle.**

| | |
|---|---|
| Observes | the holds at the start of the cycle. A value arriving in the cycle is not seen, so the grant never depends on same-cycle valid |
| Consumes | one held value, when `out` accepts it. Every empty hold, and the hold granted this cycle, takes its input |
| Ties | by `POLICY` |
| Back-pressure | stalls the whole arbiter: `out` keeps offering the same value, no hold fills, and the round-robin pointer moves only when `out` accepts |

What follows from those rules:
- An input is ready while its hold is empty or is being granted. Every ready comes
  from registered state.
- A value is offered from the cycle after it arrives, and one input alone streams one
  value per cycle.
- Round robin advances only when `out` accepts, so it is already the "fair" variant.
- `out` is stable under back-pressure: valid and data do not change until the value
  is taken.

**Class model.** `step()` is an all-or-nothing step: a cycle whose grant finds
`out` not ready has no effect, which is the back-pressure rule above. So the model is
cycle-exact under any back-pressure. Its state is one packed struct, zero at reset.

**Contract** (`src/std/arb/fw_arbiter.yaml`): values leave in order within an input
(`per_key`), and none is lost or duplicated.

**Lowering.** `step()` is mapped (no registry entry). Assign it to XLS by class name in
the knob file. One activation per cycle, at II=1; `put_or_stall` is a blocking send,
so a stalled `out` stalls the activation. `N` may be 1.

**Tests.**
- `tests/stdlib/fw_arbiter_unit_test.sv` (SVUnit), on the model: empty, round-robin
  rotation, fixed priority, the grant held under back-pressure with nothing taken,
  one input at full rate, and reset mid-traffic. The contract is checked throughout.
- `tests/xls/lib/test_arbiter.py`:
  - a Python model of the rules above against the class model, and the class model
    against the RTL cycle for cycle, with `out` back-pressured at random: round robin
    and fixed priority with 3 inputs, round robin with 5 and with 1;
  - the class against the `rr_arb` XLS IR template (`fw.hdl.lib.xls_ir`), the
    hand-built proc it replaces, cycle for cycle under the same back-pressure;
  - as a child of a structural component: model and RTL under the contract, at 1
    and 2 stages.
- Cosim (`tests/stdlib/cosim/fw_arbiter.yaml`): fw-hdl's own RTL (round robin; fixed
  priority at 2 stages), and a hand-written arbiter with other port names, an
  active-low reset and same-cycle grants. The same arbiter without its grant lock is
  expected to fail: it changes `out` while it is stalled.

```{eval-rst}
.. autosvclass:: fw_std_pkg::fw_arbiter
   :members:
```

## fw_keyed_table

A table of up to `N` entries, each a unique key and a value: install, look up, write
and remove. Install and lookup answer with a slot; write and remove name one, so only
install and lookup match keys.

```systemverilog
fw_keyed_table #(type K, type V, int N = 16)
```

| Port | API | Carries |
|---|---|---|
| `ins` | `fw_get_nb_if #(bit [KW+VW-1:0])` | `{key, value}` to install |
| `ins_rsp` | `fw_put_step_if #(bit [SB+1:0])` | `{ok, full, slot}` |
| `lkp` | `fw_get_nb_if #(K)` | the key to look up |
| `lkp_rsp` | `fw_put_step_if #(bit [SB+VW:0])` | `{hit, slot, value}` |
| `wr` | `fw_get_nb_if #(bit [SB+VW-1:0])` | `{slot, value}`: write a live slot's value |
| `rm` | `fw_get_nb_if #(bit [SB-1:0])` | the slot to free |

`KW` and `VW` are `$bits(K)` and `$bits(V)`; `SB` is `$clog2(N)`, and 1 when `N` is 1.
Each port takes at most one request a cycle, so a cycle can do one of each.

**Per cycle.**

| | |
|---|---|
| Observes | the table at the start of the cycle. Every request sees that state and never another request's effect from the same cycle, so a cycle is lookup, install, write, remove done in that order |
| Install | refused if the key is live (`ok = 0, full = 0`), else if no slot is free (`ok = 0, full = 1`); else takes the lowest free slot. A refusal is a response, not back-pressure. `slot` is 0 when refused |
| Lookup | `hit`, and the matching slot and value; on a miss, slot and value are 0 |
| Misuse | a write or remove naming a slot that was free at the start of the cycle does nothing |
| Back-pressure | stalls the whole table: nothing is taken and nothing changes until both responses have gone. A response whose output is ready goes at once, and only once |

What follows from those rules:
- A lookup gets the value from before a same-cycle write, and misses a key installed
  in the same cycle.
- A slot removed in a cycle is free from the next one.
- A slow lookup consumer also holds up installs. When the two paths must not wait on
  each other, put an `fw_channel` (`DEPTH` 2) on each response.

**Class model.** `step()` is an all-or-nothing step with two stalling outputs, so the
model is cycle-exact under any back-pressure. Its state is one packed struct, zero
(empty) at reset. Every match is a mask over the slots, and the lowest free slot is
found with a prefix OR in log2(`N`) steps. Each slot's next state is chosen from those
masks, so the cycle's logic stays shallow as `N` grows.

**Contract** (`src/std/table/fw_keyed_table.yaml`): the responses are those of a
sequential table. Each request takes effect at one point between the cycle it is
taken and the cycle of its response (either may come first), or, for a write or
remove, within `WINDOW` cycles of being taken. Requests on one port take effect in
order.

**Lowering.** `step()` is mapped (no registry entry). One activation per cycle, at
II=1. In a pipeline, all of a step's receives are kept in one stage, so an activation
takes one cycle's requests ({doc}`../methodology/synthesis`). The critical path at one
stage, from XLS's schedule with the asap7 delay model (12-bit keys, 48-bit values;
`tests/xls/lib/qor_keyed_table.py`):

| `N` | State bits | Critical path |
|---|---|---|
| 16 | 976 | 423 ps |
| 64 | 3904 | 455 ps |
| 256 | 15616 | 502 ps |

Each size meets a 500 ps clock in one stage on that model. These are schedule
estimates, before synthesis.

**Tests.**
- `tests/stdlib/fw_keyed_table_unit_test.sv` (SVUnit), on the model: install then
  lookup, duplicate and full, lowest free slot reused, all four requests in one edge,
  a response sent once while the other stalls, and misuse.
- `tests/xls/lib/test_keyed_table.py`: a Python model of the rules above against the
  class model, and the class model against the RTL cycle for cycle, with both
  responses back-pressured at random (`N` = 1, 4, 5, 16), and at 2 stages with the
  responses always ready.
- Cosim (`tests/stdlib/cosim/fw_keyed_table.yaml`): fw-hdl's own RTL at 1 and 2
  stages against the contract. The same RTL held to 7 of its 8 slots is expected to
  fail.

```{eval-rst}
.. autosvclass:: fw_std_pkg::fw_keyed_table
   :members:
```

## Cosimulation

`fw.hdl.verif.cosim` runs any module that claims to implement a library class against
the class's rules. Timing is free: the module may take more or fewer cycles than the
class model, so nothing is compared cycle for cycle. Each run checks:

- **the stream protocol** on every output with a ready: once valid, valid and data
  hold until the value is taken;
- **the class's per-cycle rules** that hold whatever the timing, for example that
  `fw_credit_tx` never stalls a credit return and never has more than `CREDITS`
  credits outstanding;
- **the contract**: order (`canon.check` with the class's rule), and every value
  offered is taken and leaves exactly once. For a table, whose outputs are answers
  rather than its inputs passed on, the driver checks the sequential table instead.

A spec is a YAML file: the class, its parameters, and one or more targets. A target
maps each of the class's ports to a module's signals:

```yaml
class: fw_arbiter
params: {W: 8, N: 3}
targets:
  - name: mine
    module: my_arb                  # the module under test
    files: [rtl/my_arb.sv]          # relative to the spec
    params: {DEPTH: 2}              # the module's own parameters (optional)
    clock: clk_i
    reset: {port: rst_ni, active_low: true}
    ports:
      in[0]: {data: req0_data, valid: req0_valid, ready: req0_ready}
      in[1]: {data: req1_data, valid: req1_valid, ready: req1_ready}
      in[2]: {data: req2_data, valid: req2_valid, ready: req2_ready}
      out:   {data: gnt_data, valid: gnt_valid, ready: gnt_ready}
```

- A port with no `ready` is valid-only.
- The payload has the class's layout. For example, `out` of `fw_arbiter` is
  `{index, value}`.
- In place of `module` and `files`, a target can be fw-hdl's own lowering of a
  component that wraps the class: `fallback: {files: [...], top: <component>, xls:
  [<classes>], stages: <n>}`, where `xls` lists the classes to assign to XLS, as in a
  knob file.

Run it with:

```sh
python -m fw.hdl.verif.cosim spec.yaml [more.yaml ...] [--target NAME] [--seeds N] \
    [--workdir build/cosim] [--verilator PATH]
```

It prints `PASS` or `FAIL` per target and seed, with the rules broken. Each run's
testbench and simulator log are in the work directory. Verilator is found through
`--verilator`, then `$VERILATOR`, then `PATH`.

The testbench comes from the class's *driver* (`cosim.DRIVERS`), which knows which
ports are sources and which are sinks:

| Class | Environment |
|---|---|
| `fw_arbiter` | `in[k]` are sources; `out` is a sink with a random ready |
| `fw_credit_tx` | `in[v]` are sources; `out` is valid-only; the testbench is the receiver: for each value it is sent, it returns `CHECK` credits on `cr`, in order, a random 1 to *d* cycles later |
| `fw_channel` | `put_ex` is a source; `get_ex` is a sink with a random ready. At most `DEPTH` values are held, and for `DEPTH` 1 or more none leaves in the cycle it came |
| `fw_keyed_table` | `ins`, `lkp`, `wr` and `rm` are sources, with keys from a few more than `N` and slots from the whole slot range; `ins_rsp` and `lkp_rsp` are sinks with a random ready. The run passes if some order of the requests, as the contract allows, gives every response seen |

Each seed sets the source rate, the sink rate and the receiver's delay *d*: busy and
sparse sources, slow and fast sinks. So values arrive both before and behind a stalled
output, and a credit sender runs both with credits to spare and with none left.

The specs in `tests/stdlib/cosim/` run under `tests/stdlib/test_cosim.py`. Wrappers for
the own-RTL targets are in `cosim_pkg.sv`, and the hand-written reference arbiter is
`ref_arb3.sv`.
