# Contracts

Function is defined by **contracts** at observable points: ordering, data validity,
lifetimes and conservation. It is not defined by the cycle a value appears in. Two runs
are the same function when their streams are equal up to the reorderings the contract
allows. That is what lets one source build under many schedules.

The contract library has two halves that share one model of a rule:

- `fw_order_pkg` (`src/std/order/fw_order_pkg.sv`) checks a stream as it runs. It has
  no imports, so the same checker sits in a class-model testbench or behind a pin-level
  monitor of generated RTL.
- `fw.hdl.verif.canon` (Python) compares two recorded streams, for example the class
  model and the RTL, under the same rule.

## Rules

A rule (`fw_order_rule` / `canon.Rule`) says which **later** items may leave before which
**earlier** ones:

| Setting | Meaning |
|---|---|
| default (`fw_order_rule::in_order()`) | a total order: nothing passes anything |
| `per_key` (`in_order_per_key()`) | items with different keys never constrain each other; order is kept within a key |
| `set_pass(a, b)` / `allow_pass: [[a, b]]` | a later item of class `b` may pass an earlier item of class `a` |
| `set_strict(a, b)` / `strict_after: [[a, b]]` | an ordered (`a` before `b`) pair must also leave in strictly later cycles; leaving in the same cycle is a violation |
| `pin_cycles` (Python only) | also compare leave cycles; only for views that are meant to be cycle-exact |

Items that enter in the same cycle are ordered by call order. To make "accepted in the
same cycle counts as earlier" hold for one point, call `enter()` for that point first.

## Checkers

```{eval-rst}
.. autosvpackage:: fw_order_pkg

.. autosvclass:: fw_order_pkg::fw_order_rule
   :members:

.. autosvclass:: fw_order_pkg::fw_order_check
   :members:

.. autosvclass:: fw_order_pkg::fw_lifetime
   :members:

.. autosvclass:: fw_order_pkg::fw_dep_check
   :members:

.. autosvclass:: fw_order_pkg::fw_trace
   :members:
```

Every checker counts errors per kind (`fw_contract_err_e`), keeps the first message
(`first_error`) and the full log (`log`), and prints each error with the prefix
`FW_CONTRACT` unless `quiet` is set.

| Kind | Raised by | When |
|---|---|---|
| `FW_E_REORDER` | `fw_order_check` | a later item left before an earlier one it may not pass |
| `FW_E_UNKNOWN` | `fw_order_check` | an item left that never entered |
| `FW_E_DUPLICATE` | `fw_order_check` | an item entered or left twice |
| `FW_E_DATA` | `fw_order_check` | an item left with different data |
| `FW_E_LOST` | `fw_order_check.finish()` | an item entered and never left |
| `FW_E_SAME_CYCLE` | `fw_order_check` | a `strict_after` pair left in one cycle |
| `FW_E_DOUBLE_ALLOC`, `FW_E_BAD_FREE`, `FW_E_USE_DEAD`, `FW_E_MAX_LIVE` | `fw_lifetime` | allocate of a live id, free of a dead one, use of a dead one, more than `max_live` live |
| `FW_E_LEAK` | `fw_lifetime.finish()` | ids still live |
| `FW_E_DEP_EARLY` | `fw_dep_check` | a dependent released before the youngest older producer it recorded at entry retired |

`fw_dep_check` is sticky: once the recorded producer retires, the dependent is satisfied,
whatever producers arrive later.

## Comparing views

`fw_trace` writes one JSON line per event:

```json
{"pt":"rsp","ev":"out","cyc":12,"id":7,"key":3,"cls":0,"data":99}
```

The Python side reads such a file and compares two views:

```python
from fw.hdl.verif.canon import Rule, load_trace, compare

rule = Rule(per_key=True)
diffs = compare(load_trace("model.jsonl"), load_trace("rtl.jsonl"), rule,
                names=("model", "rtl"))
assert diffs == []
```

`compare` checks each trace on its own (as `fw_order_check` would), then compares their
canonical forms: the same items with the same data, and every pair the rule binds in the
same relative order. `canonical()` returns that form; equal forms mean equivalent
streams.

## Tests

- `tests/order/fw_order_unit_test.sv` (SVUnit, run by `tests/order/test_fw_order.py`):
  clean streams, and each error kind injected once and caught exactly once.
- `tests/python/unit/test_canon.py`: the Python rules and comparison.
