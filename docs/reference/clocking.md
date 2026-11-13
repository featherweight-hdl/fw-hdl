# Domains: clock, reset and time

Clock and reset are **domains**: an ambient property of where a component sits, not
something it declares. Every domain kind has the same parts:

| Part | Clock | Reset |
|---|---|---|
| API (extends {sv:class}`fw_hdl_pkg::fw_domain_if`) | {sv:class}`fw_hdl_pkg::fw_clock_domain_if`: `tick`, `root_ticks` | {sv:class}`fw_hdl_pkg::fw_reset_domain_if`: `in_reset`, `wait_assert`, `wait_deassert`, `is_async`, `sync_clock` |
| Component port, inherited from the parent | `clock` (`fw_clock_port`) | `reset` (`fw_reset_port`) |
| Root bridge, pins to domain | {sv:class}`fw_hdl_pkg::fw_clock_xtor_bridge` over `fw_clock_xtor_if` | {sv:class}`fw_hdl_pkg::fw_reset_xtor_bridge` over `fw_reset_xtor_if` |
| Derived domains | {sv:class}`fw_hdl_pkg::fw_clock_domain` (divider) | {sv:class}`fw_hdl_pkg::fw_reg_reset_domain` (register bit), {sv:class}`fw_hdl_pkg::fw_reset_combine` (OR) |

A power kind is reserved (the enum slot and this shape), not built.

## Inheritance

`fw_component::do_connect()` binds every child whose `clock` is unbound to the
parent's, and every child whose `reset` is unbound to the parent's *when the parent's
is bound*. A parent overrides a child's domain in `connect()`:
`child.clock.connect(div2)`, `child.reset.connect(soft_rst)`.

An unbound `reset` is legal and means "never in reset": `in_reset()` is 0,
`wait_reset_deassert()` returns at once. `fw_root` seats the root's `reset` on its
`reset` pin (active high: invert an active-low pin where it enters,
`` `fw_root_begin(top, u_root, aclk, !aresetn) ``), deasserting on the root clock.
A root that seats only a clock (a hand-written harness) keeps working.

Component helpers: `tick(n)`, `root_ticks(n)`, `in_reset()`,
`wait_reset_deassert()`, `wait_reset_assert()`, `domain(kind)`.

## Relations

{sv:class}`fw_hdl_pkg::fw_domains`'s `relate(a, b)` compares two domains of one kind:
SAME (one behaves as the other: a divide-by-1 clock, a one-source combine), RELATED
(their root sets meet: two divisions of one clock; a reset built from another),
UNRELATED (otherwise).

## The run lifecycle

Behavior follows the reset domain. For a component whose reset domain is bound and is
not SAME as its tree root's, `do_run()` forks a supervisor that:

1. waits until the domain is out of reset;
2. forks every registered `run()`;
3. waits until the domain asserts;
4. ends each `run()` and everything it forked (`disable fork`);
5. calls `reset_state()`, then goes back to 1.

`step()` is not gated: it is called on every edge, in reset or not, and reads
`in_reset()` itself, as an always block has a reset branch.

Class property initializers do not run again, so a component that keeps state across
a restart puts the initial values back in `virtual function void reset_state()`
(default: nothing). That is the class-model side of what a reset does to a process's
registers in the lowered design.

The tree root's reset domain is not supervised: `fw_root` tears the whole tree down on
reset and builds a fresh one on release, which is the same lifecycle with every field
at its initial value.

A blocking call runs in the caller's process. Killing the caller ends the call where
it is, inside the callee's code. In the same reset domain the callee is reset too.
Across a reset crossing it is not: it sees a call that began and never ended. A
callee reset alone while a caller from another domain is blocked in it leaves that
caller blocked; release such waiters in `reset_state()`, or put a crossing element
between the domains.

## Crossings

A **crossing** is logic that works with two different domains of one kind. After
connect, `fw_component_root::start()` runs
{sv:class}`fw_hdl_pkg::fw_crossing_check` over the tree and reports each
{sv:class}`fw_hdl_pkg::fw_crossing`:

| Via | Found when |
|---|---|
| binding | a caller-end port and the export it resolves to are in domains that are not SAME |
| component | a component that is not a crossing element has an endpoint associated (`set_domain`) with another domain |
| reset-sync | a component's reset deasserts on no clock, or on one UNRELATED to the component's clock |

Not crossings: the domain ports themselves and other ambient endpoints, an unbound
component reset, a structural parent's forwarding port, and anything inside a
crossing element.

| Kind | Relation | Severity |
|---|---|---|
| clock | related | info |
| clock | unrelated | error |
| reset | related | warn |
| reset | unrelated | error |
| reset-sync | | error |
| any | waived | info |

A **crossing element** is a component built to join two domains: it overrides
`is_crossing(kind)` to return 1, declares a domain port per side
(`fw_clock_port wclock, rclock;`) and associates each endpoint with its side
(`put_ex.set_domain(wclock)`). Its outer bindings are then SAME on both sides. A
**waiver** accepts one crossing with a reason:
`waive_crossing("out", FW_DOMAIN_RESET, "drains before ctrl[3] is set")` in the port
owner's `connect()`; it is reported at info with the reason. An endpoint associated
with an unbound domain port is an error.

Each crossing of severity warn and above is printed, and an `fw_error`/`fw_warn` event
goes to the port owner's debug context; an error then stops the run with `$fatal`:

```
fw-hdl crossing [error] clock unrelated binding: top.a.out (clk_b) -> top.b.in_ex (clk_a): needs a synchronizer or an async FIFO (a crossing element)
fw-hdl crossing [warn ] reset related binding: top.dma.ch.req (top.dma.ch_rst) -> top.dma.req_ex (top.reset): a reset on one side kills run() processes, and the calls they have in flight, across it
```

| Plusarg | Effect |
|---|---|
| `+fw_crossings_off` | skip the check |
| `+fw_crossings_show` | also print info rows |
| `+fw_crossings`, `+fw_crossings=<path>` | write JSON (`fw_crossings.json` by default) |
| `+fw_crossings_nofatal` | errors do not stop the run |
| `+fw_crossings_sev=<kind>:<rel>:<sev>[,...]` | override a severity (`reset:related:error`, `reset:sync:warn`) |

The Python flows do not run this check. Partition rejects, at the SV line that bound
it, an instance whose clock domain is UNRELATED to the root's or whose reset domain is
not the root's; the native flow rejects a supervised `run()` ({doc}`../methodology/synthesis`).

## API

```{eval-rst}
.. autosvclass:: fw_hdl_pkg::fw_domain_if
   :members:
   :undoc-members:

.. autosvclass:: fw_hdl_pkg::fw_domain_ref
   :members:
   :undoc-members:

.. autosvclass:: fw_hdl_pkg::fw_domains
   :members:

.. autosvclass:: fw_hdl_pkg::fw_domain_port
   :members:

.. autosvclass:: fw_hdl_pkg::fw_clock_domain_if
   :members:
   :undoc-members:

.. autosvclass:: fw_hdl_pkg::fw_clock_domain
   :members:

.. autosvclass:: fw_hdl_pkg::fw_clock_xtor_bridge
   :members:

.. autosvclass:: fw_hdl_pkg::fw_clock_period_xtor_bridge
   :members:

.. autosvclass:: fw_hdl_pkg::fw_reset_domain_if
   :members:
   :undoc-members:

.. autosvclass:: fw_hdl_pkg::fw_reset_xtor_bridge
   :members:

.. autosvclass:: fw_hdl_pkg::fw_reg_reset_domain
   :members:

.. autosvclass:: fw_hdl_pkg::fw_reset_combine
   :members:

.. autosvclass:: fw_hdl_pkg::fw_crossing
   :members:

.. autosvclass:: fw_hdl_pkg::fw_crossing_check
   :members:

.. autosvclass:: fw_hdl_pkg::fw_quantum_keeper
   :members:
```
