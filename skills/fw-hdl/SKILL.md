# Featherweight-HDL

Featherweight-HDL (fw-hdl) is a lightweight, UVM-flavored **class modeling layer**
for SystemVerilog. You describe a testbench/model as a tree of `fw_component`
objects that talk to each other through **deferred-binding** APIs (the
`fw_port`/`fw_export` pair), run them through a fixed **build → connect → run**
lifecycle, and bridge the pure class world to **signal-level pins** through a thin
module wrapper driven by the `` `fw_root `` macros.

Two packages make up the library (see `src/flow.yaml`, fragment `hdl`):
- **`fw_hdl_pkg`** — the KERNEL: the deferred-binding mechanism (`fw_component`,
  `fw_port`, `fw_export`), the lifecycle interfaces (`fw_elaboratable`,
  `fw_runnable`), the clock-domain API, and the `fw_root` module.
- **`fw_std_pkg`** — the STANDARD protocol library built on the kernel: the
  transaction-level APIs (`fw_put_if`, `fw_get_if`, `fw_reqrsp_if`), their
  implementation macros (`fw_std_macros.svh`), and signal-level bridges
  (`fw_put_xtor_bridge`).

A consumer depends on the bundled FileSet export **`fw-hdl.hdl.sv-src`** (it pulls
in kernel + std). Macros are text, not package symbols, so a package that uses
them `` `include ``s `fw_hdl_macros.svh` (the `` `fw_root `` macros) and/or
`fw_std_macros.svh` (the `` `FW_*_IMP `` macros) — both are found via the incdir
that `hdl.sv-src` exports.

> For building *protocols* (a set of role APIs + signal-level transactors:
> ready/valid, wishbone, AXI…), see the **fw-proto-kit** skill. This skill covers
> the core modeling library those kits are built on.

---

## 1. The class architecture

### fw_component — the building block
A component is a node in the model tree. Subclass `fw_component`, create children
in `build()`, and wire them in `connect()`.

```systemverilog
class my_comp extends fw_component;
    function new(string name, fw_component parent);
        super.new(name, parent);   // self-registers with `parent`
    endfunction

    function void build();   // create immediate children + ports/exports here
    endfunction

    function void connect(); // wire ports to providers here
    endfunction
endclass
```

- A component is constructed `new("name", parent)`. Passing a non-null parent
  **self-registers** it into the parent (via `add_elaboratable`), so the parent's
  lifecycle walk reaches it — you never maintain a child list by hand.
- `build()` creates the *immediate* children (`child = new("child", this);`); the
  lifecycle recurses into them automatically (do not call `child.build()`).
- `connect()` wires this level's ports to their providers. **Only wire here**
  (pointer assignment); the actual resolution happens in the connect *phase*
  after all `connect()`s run (see §2).
- Every component has a built-in `clock` port (a clock DOMAIN — see §4).

### fw_port and fw_export — deferred binding
APIs are not called directly between components; they flow over two wrapper
objects that resolve to a concrete implementation during the connect phase. This
is fw-hdl's equivalent of UVM's `resolve_bindings`.

- **`fw_port #(API)`** — an API *consumer*. A component holds a port to *call* an
  API whose implementation lives elsewhere. `port.connect(provider)` binds it;
  then `do_connect()` resolves the implementation handle once into the public
  member **`port.t`**, and run-phase code calls the API directly as
  `port.t.method(args)`. (`port.get_if()` is the underlying resolver — still
  available for manual/out-of-lifecycle use, e.g. a module that wires a tree by
  hand.)
- **`fw_export #(API)`** — an API *provider*. It resolves either to a terminal
  implementation handle (an **imp**) or forwards to another export below it.

Connection rules (enforced in `src/fw_port.svh` / `src/fw_export.svh`):
- **port → export** (the common case): `consumer_port.connect(provider_export)`.
- **port → port**: an inner port connects up to an outer port (up the hierarchy).
- **export → export**: an export forwards to a provider lower down.
- An export may **not** connect to a port — calls always flow *toward* the imp.

`API` is an **interface class** with `pure virtual` methods — the class-level
contract. Tasks block; functions don't. Example, the std `put` API
(`src/std/fw_put_if.svh`):

```systemverilog
interface class fw_put_if #(type T);
    pure virtual task put(input T t);
endclass
```

### Providing an API — the `` `FW_*_IMP `` macro
Every std API ships an implementation-template macro. A component that *provides*
the API uses the macro instead of hand-rolling the export proxy. It stamps a
nested proxy that is at once the export a port connects to and the imp it
resolves, plus a member of that type; each API method redirects to
`<member>_<method>()`.

```systemverilog
class consumer extends fw_component;
    data_t received[$];

    `FW_PUT_IMP(data_t, consumer, in);   // provides fw_put_if; note trailing ;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction
    function void build();
        in = new(this);                  // construct the stamped export member
    endfunction
    virtual task in_put(input data_t t); // put() lands here
        received.push_back(t);
    endtask
endclass
```

A *consumer of the API* instead holds a port and calls through `port.t` (the imp
the connect phase resolved for it):

```systemverilog
class producer extends fw_component implements fw_runnable;
    fw_port #(fw_put_if #(data_t)) out;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);              // opt in to a run() process (see §2)
    endfunction
    function void build();
        out = new("out", this);
    endfunction
    virtual task run();
        for (int i = 0; i < 4; i++)
            out.t.put(32'hdead_0000 + i);   // out.t resolved during connect
    endtask
endclass
```

The top component instances both and wires them in `connect()`:

```systemverilog
function void connect();
    prod.out.connect(cons.in);   // port (consumer) -> export (provider)
endfunction
```

This pure-TLM pattern is demonstrated end to end in **`tests/intf_pc/`**.

---

## 2. The lifecycle: elaboratable + runnable

Elaboration (build/connect) is separate from execution (run):

- **`fw_elaboratable`** (`do_build`/`do_connect`) — every `fw_component`,
  `fw_port`, and `fw_export` is elaboratable and self-registers into its
  container, which drives each phase polymorphically.
- **`fw_runnable`** (`run`) — opt-in. `fw_component` has **no** `run()` by
  default; an object that needs a process `implements fw_runnable` and calls
  `add_runnable(this)` (usually from its constructor). There is no auto-detection.

The phases (`src/fw_component.svh`):
- **`do_build()`** — TOP-DOWN: run *this* `build()` (which creates children), then
  recurse into the just-created children.
- **`do_connect()`** — TOP-DOWN: run *this* `connect()` (which only *wires*
  pointers); then **auto-inherit clock** for any child whose `clock` port wasn't
  explicitly bound (it defaults to this component's domain); then recurse —
  during which each port resolves its provider into `port.t`. Because `connect()`
  only wires and resolution happens in the recursion afterward, ordering is free.
- **`do_run()`** — fork the `run()` of every registered runnable, then recurse
  into child components.

**Wiring vs. resolution:** `connect()` only *wires* pointers
(`port.connect(provider)`); the graph isn't complete until every `connect()` has
run. Resolution into `port.t` therefore happens later, in the `do_connect()`
recursion, once the chain is fully wired — so a `connect()` body must not read a
`port.t` (it isn't bound yet). Run-phase code uses `port.t` freely. The
underlying `get_if()` resolver stays available for code that wires a tree by hand
outside the lifecycle (e.g. the smoke test), where `do_connect()` never runs. The
older guidance to "resolve in `run()`" is superseded: resolution is automatic at
connect; just use `port.t` in `run()`.

The whole lifecycle is driven by **`fw_component_root #(Tb)`**
(`src/fw_component_root.svh`): its `run()` calls `do_build()` → `do_connect()` →
`do_run()`, and `kill()` tears the tree's process down. You rarely write this
directly — the `` `fw_root `` macros generate a subclass of it (§5).

---

## 3. A pure class tree, end to end

```systemverilog
class pc_top extends fw_component;
    producer prod;
    consumer cons;
    function new(string name, fw_component parent); super.new(name, parent); endfunction
    function void build();
        prod = new("prod", this);
        cons = new("cons", this);
    endfunction
    function void connect();
        prod.out.connect(cons.in);
    endfunction
endclass
```

To run it you need something to drive the lifecycle and supply clock/reset — that
is `fw_root` (§5). For a pure-TLM tree with no pins, the `` `fw_root `` block
carries no bind lines; `pc_top.connect()` does all the wiring and `do_run()` forks
the producer.

---

## 4. Clock domains

Every component carries a `clock` port typed `fw_clock_domain_if`
(`src/fw_clock_domain_if.svh`):

```systemverilog
interface class fw_clock_domain_if;
    pure virtual task     tick(int n = 1);          // advance n cycles (run phase)
    pure virtual function longint root_ticks(int n = 1); // n ticks here = ? root clocks
endclass
```

- A component advances its own domain with `this.tick(n)` (which resolves
  `clock.get_if().tick(n)`); `root_ticks(n)` walks up to the root, folding in each
  divisor, and is callable any time the graph is wired.
- **Auto-inheritance:** a child whose `clock` was not explicitly bound defaults to
  its parent's domain during `do_connect()`. The root's domain is seated
  externally by `fw_root`.
- **Derived (divided) domains** use `fw_clock_domain` (`src/fw_clock_domain.svh`),
  which is both the export a child connects to and the imp it resolves. Build it,
  point its inner `src` port at your own domain, and hand it down:

  ```systemverilog
  function void build();   div2 = new("div2", this, 2); ... endfunction
  function void connect();
      div2.src.connect(this.clock);   // pull from my (inherited) domain
      child.clock.connect(div2);      // give the child the divided domain
  endfunction
  ```

See **`tests/clock_domain/`** for inherit + top-down override + divide-by-N.

---

## 5. Connecting the class tree to signal-level pins

A pure class tree has no pins. To exercise real RTL you wrap it in a module and
connect each port/export to the signal world through a **bridge** over a
**transactor interface**, all driven by `fw_root`.

### The three pieces
1. **Transactor interface** — an SV `interface` with the clock/reset and protocol
   **pins** as ports, plus task/function methods that implement the API against
   those pins. For the unhandshaked `put` (`src/std/fw_put_xtor_if.sv`):

   ```systemverilog
   interface fw_put_xtor_if #(parameter type T = int)
                            (input clock, input reset, output T out);
       task automatic put(input T t);
           @(posedge clock);
           out <= t;            // register the beat onto the pin; no handshake
       endtask
   endinterface
   ```
   (A handshaked protocol additionally splits into a FIFO'd interface + a clocked
   core FSM — that is the domain of the **fw-proto-kit** skill. `put` has no
   handshake, so the interface *is* the whole transactor.)

2. **Bridge class** — adapts the API to a `virtual` transactor interface, and by
   role IS either an `fw_export` (a *provider*: driven when its API method is
   called) or an `fw_port` (a *consumer*: an active `run()` loop that samples the
   bus and calls a connected export). The `put` provider bridge
   (`src/std/fw_put_xtor_bridge.svh`):

   ```systemverilog
   class fw_put_xtor_bridge #(type T) extends fw_export #(fw_put_if #(T))
           implements fw_put_if #(T);
       virtual interface fw_put_xtor_if #(T) vif;
       function new(string name, fw_component parent,
                    virtual interface fw_put_xtor_if #(T) vif);
           super.new(name, parent, this);   // the export's imp is the bridge
           this.vif = vif;
       endfunction
       virtual task put(input T t);
           vif.put(t);                      // drive the beat onto the wire
       endfunction
   endclass
   ```
   **Every bridge's constructor is `new(name, parent, vif)`** — the `` `fw_root ``
   macros rely on this signature.

3. **Module wrapper** — a top module that instances the transactor interface(s)
   on the real pins/bus, supplies clock/reset, and contains the `` `fw_root ``
   block that constructs the bridges and runs the tree.

### The `fw_root` module
`fw_root #(.Tbind(...)) inst (.clock, .reset)` (`src/fw_root.sv`) is the
class↔module boundary. On **reset release** it `new`s the `Tbind` root, seats the
root clock domain from its own `clock`/`reset`, and forks the tree's `run()`
(build → connect → run). On a **reset** it kills and restarts the tree.
`inst.root` is the live root handle (used by the testbench to read results).

---

## 6. The `` `fw_root `` macros (`src/fw_hdl_macros.svh`)

These describe, compactly, how a pure top component is wrapped as the elaboration
root and how its ports/exports bind to the signal world. `` `include
"fw_hdl_macros.svh" `` in the wrapper module first.

```systemverilog
`fw_root_begin(comp_t, inst, clock, reset)
    `fw_root_bind_port  (port_ep,   if_path, bridge_t)
    `fw_root_bind_export(export_ep, if_path, bridge_t)
    ...
`fw_root_end
```

- **`` `fw_root_begin(comp_t, inst, clock, reset) ``** opens the block. It emits a
  class `comp_t``_bind extends fw_component_root #(comp_t)` and begins its
  `connect()` with `super.connect()` — so the pure top's *own* `connect()` (its
  TLM wiring) still runs, and the binds below *add* the signal-level connections.
  It stashes `comp_t`/`inst`/`clock`/`reset` in nested `` `define ``s.

- **`` `fw_root_bind_port(port_ep, if_path, bridge_t) ``** — the endpoint is a
  **port** (e.g. `prod.out`); the bridge is its export provider. Expands to:
  ```
  bridge_t __fw_bridge = new("port_ep", this, if_path);
  port_ep.connect(__fw_bridge);
  ```

- **`` `fw_root_bind_export(export_ep, if_path, bridge_t) ``** — the endpoint is
  an **export** (e.g. `chk.in`); the bridge is the consuming port. Expands to:
  ```
  bridge_t __fw_bridge = new("export_ep", this, if_path);
  __fw_bridge.connect(export_ep);
  ```

  The suffix names the **endpoint's** nature (which fixes the direction).
  `if_path` is a live module-scope transactor-interface handle (e.g. the interface
  instance `u_put`, or a transactor module's internal `init_xtor.u_if`).

- **`` `fw_root_end ``** closes `connect()` and the class, then emits the actual
  `fw_root #(.Tbind(comp_t``_bind)) inst (.clock, .reset)` instance, and
  `` `undef ``s its temporaries. **A `` `fw_root_begin/end `` block cannot be
  nested** (it detects an unbalanced open and forces a compile error).

### Worked example — signal-level `put` (`tests/put_proto/put_proto_tb.sv`)
```systemverilog
`include "fw_hdl_macros.svh"
module put_proto_tb;
    import fw_hdl_pkg::*; import fw_std_pkg::*; import put_proto_pkg::*;

    logic clock = 0, reset = 1;  data_t bus;
    always #5ns clock = ~clock;

    // transactor interface on the real pin
    fw_put_xtor_if #(data_t) u_put (.clock(clock), .reset(reset), .out(bus));

    // wrap put_top as the root; bind its producer's PORT to the put bridge
    `fw_root_begin(put_top, u_root, clock, reset)
        `fw_root_bind_port(prod.out, u_put, fw_put_xtor_bridge #(data_t))
    `fw_root_end

    initial begin
        reset = 1; repeat (4) @(posedge clock); reset = 0;
        while (u_root.root == null) @(posedge clock);   // wait for fw_root to new it
        // ... sample `bus`, check u_root.root.<children> ...
    end
endmodule
```

A multi-endpoint example (ports *and* exports, plus a monitor) is in
**`tests/rv_proto/rv_proto_tb.sv`**.

---

## 7. Where to look

| Topic | Reference |
| --- | --- |
| Pure-TLM tree (port↔export, `` `FW_PUT_IMP ``) | `tests/intf_pc/` |
| Signal-level transactor bridge + `` `fw_root `` binds | `tests/put_proto/` |
| Handshaked protocol (ready/valid), monitors, formal | `tests/rv_proto/` + **fw-proto-kit** skill |
| Clock-domain inherit / override / divide | `tests/clock_domain/` |
| Kernel source | `src/fw_*.svh`, `src/fw_root.sv`, `src/fw_hdl_macros.svh` |
| Std protocol source | `src/std/` |

### Conventions
- One class per `.svh`, `` `include ``d into the package `.sv` in dependency
  order. SV `interface`/`module` definitions cannot live in a package — list them
  separately in the FileSet (mirrors `src/flow.yaml`).
- **Include guards only on macro files** (`fw_hdl_macros.svh`, `fw_std_macros.svh`)
  — they are the only `.svh` pulled in more than once. Every other `.svh` is
  `` `include ``d exactly once, inside its package; no guard.
- Call APIs through `port.t` in `run()` (resolved automatically during connect);
  `connect()` only wires (`port.connect(provider)`) and must not read `port.t`.
- A bridge is not a component: by role it is an `fw_export` (provider) or an
  `fw_port` (consumer). Its constructor is always `new(name, parent, vif)`.
