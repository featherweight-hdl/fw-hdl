# Library classes

Building blocks in `fw_std_pkg` whose cycle behaviour is part of their definition:
credit senders, arbiters, and (to come) tables, pools and queues. Each class states:

- what it **observes** in a cycle;
- what it **consumes**;
- how **ties** break;
- whether a grant can depend on **same-cycle valid**.

A cycle-step class model implements exactly that, and the RTL is checked against it
cycle for cycle. A class whose output can be back-pressured has a process model
instead, and its per-cycle rules are checked on the RTL. Each class also has a **contract** (a YAML file next to its
source): the order and conservation rules any implementation must keep, whatever its
timing ({doc}`contracts`).

| Class | Source | Form | Lowering |
|---|---|---|---|
| `fw_credit_tx` | `src/std/credit/` | cycle step | its `step()`, mapped |
| `fw_arbiter` | `src/std/arb/` | process | registry entry: the `rr_arb` template, round robin or fixed priority ({doc}`registry`) |

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
| `in[N]` | `fw_get_if #(T)` | the inputs |
| `out` | `fw_put_if #(bit [IB+$bits(T)-1:0])` | `{index, value}`: which input won, and its value |

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

**Class model.** The model is a process, not a cycle step: a step cannot see whether
`out` will accept (an XLS send has no non-blocking form). It makes one grant per clock
over the holds that are full at that edge, and it blocks while `out` back-pressures.
Its holds may fill during a stall, which the RTL's do not. So model and RTL are
compared under the contract, per input, and the per-cycle rules above are checked on
the RTL directly.

**Contract** (`src/std/arb/fw_arbiter.yaml`): values leave in order within an input
(`per_key`), and none is lost or duplicated.

**Lowering.** A registry entry (no knob needed), the `rr_arb` template from
`fw.hdl.lib.xls_ir`, with `prio=True` for `FW_ARB_PRIO`. It takes `N` from 2 to 64.

**Tests.**
- `tests/stdlib/fw_arbiter_unit_test.sv` (SVUnit), on the model: empty, round-robin
  rotation, fixed priority, grant held under back-pressure, one input at full rate,
  and reset mid-traffic. The contract is checked throughout.
- `tests/xls/lib/test_arbiter.py`:
  - model and RTL under the contract, for round robin and fixed priority with 3
    inputs and round robin with 5, at 1 and 2 stages;
  - the RTL's tie rule under each policy, cycle by cycle;
  - the grant held under back-pressure, with `out` stable;
  - `N` out of range, rejected at the child's line.

```{eval-rst}
.. autosvclass:: fw_std_pkg::fw_arbiter
   :members:
```
