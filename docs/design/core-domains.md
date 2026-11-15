# Core domains (issues and recommendations)

Status: **all decisions in §10 settled** (2026-11-15), after the notes
added to `roadmap.md` "Domains" and review. The plan that implements them
is [core-domains-plan.md](core-domains-plan.md); this file stays the record
of the issues and the reasons. Planning raised questions that refine
decisions 2, 12 and 13 and §8 (plan §10).

Inputs:
- `roadmap.md` "Domains", including these notes:
  - Clock and reset will always exist. Power is modelled by some designs.
    Others will exist too, such as which macro a block belongs to or other
    physical aspects. Extensibility and propagation are the question, and
    a "union of all domains" approach is a concern.
  - Clock domains matter mainly at **interfaces**. Code that works with
    interfaces in different clock domains implies a crossing.
  - At higher levels, timing may be inserted relative to a clock domain.
    It is fine for that to be the block's sole domain.
  - Domains may be **entirely structural**, because marking code as
    belonging to a domain is messy. They are then **pure markers**,
    except where modelling needs delays.
- `core-layer1.md` §3.6, the constraints layer 1 already accepted, and §1
  "Out of scope".
- The old SV core's domain model:
  - code: `src/fw_domain_if.svh`, `fw_domains.svh`, `fw_domain_port`,
    `fw_clock_domain`, `fw_reg_reset_domain`, `fw_crossing*.svh`;
  - reference: `docs/reference/clocking.md`;
  - full design: fw-proto-axi-new `docs/design-domains.md`.
- Zuspec's domain model:
  - zuspec-be-py `model/domain.py`: `ClockDomain`, `DerivedClockDomain`,
    `ResetDomain(polarity, style)`, and a `PowerDomain` stub;
  - ir-core `DataTypeComponent.clock_domain` / `reset_domain`, which hold
    Python objects, not IR;
  - zuspec-synth `cdc_analysis.py`.

## 0. Direction from the roadmap notes and discussion

1. **A domain is a structural marker.** It is attached to components and
   interfaces (ports and bundles), never to code. A process runs in its
   component's domain (layer 2).
2. **Domain kinds are open.**
   - Clock and reset are the first two kinds the library provides.
   - Power, macro membership and physical placement are later kinds,
     possibly user-defined.
   - The mechanism is the same for every kind. A kind contributes its
     properties, its relation and crossing rule, and its *API*, the
     operations a component may ask of a domain.
3. **No union of all domains.**
   - A component's domain of kind K is the nearest binding of K on the
     path to the root.
   - Only bindings are stored.
4. **Crossings are found at interfaces** (§6).
5. **A domain is physical only on demand** (discussion, 2026-11-15).
   - A domain gets a physical form, a clock or reset net, only where a
     component *uses its API*. Examples: an extern maps a pin to it,
     sync code calls `in_reset()` or waits on an edge (layer 2), or
     model-level code asks for timing.
   - A domain nobody uses physically stays a marker.
   - "Has a net" is therefore not a property of the kind. Realization
     follows from use.
6. **Generic declaration, application-specific drivers.** Physical
   realization needs a bridge between a domain and signals, and bridges
   are application-specific: a PLL, a divider, a reset synchronizer, a
   soft-reset register. To keep the core generic, what a domain *is*
   is separated from what *drives* it:
   - A domain, and how it derives from another domain, is **declared**
     by the scope that uses it, with built-in, generic declarations.
     This is enough for markers, crossing relations, and modelling, such
     as ticking a divided clock in simulation.
   - A **driver** is an ordinary component that produces the physical
     net. It is needed only when something demands the domain physically
     (§3).
7. **`build()` pushes domains down; bridges are attached in `connect()`.**
   - *Association* is set in `build()`, top-down (§2): which domain each
     child and interface is in. A child's `build()` can depend on it, for
     example choosing a synchronous or an asynchronous FIFO from the
     relation of two domains.
   - *Bridges* are attached in `connect()` or by the extern map, like
     signal connections and pins (§3): which signal or extern pin produces
     a domain's net. A bridge never changes structure, and relations come
     from declarations, not from drivers.
8. **Domains are a capability layer, not methods on the core classes**
   (discussion, 2026-11-15). See "API pattern" below.

§3.6 of `core-layer1.md` fits this with one change of reading:
- §3.6 says a component "has a clock domain and a reset domain";
- read that as: a component *resolves* a domain of each kind by lookup.

### API pattern: capability layers

Class libraries tend to grow their core classes: every new concern adds
methods to the component base. fw-hdl keeps concerns separate instead.
- **The core classes stay minimal.** These are `fw_object`,
  `fw_component`, the signal, port and bundle classes, and
  `fw_extern_map`.
- **A capability is its own set of classes.** Domain association and
  query operate *on* components and interfaces, but they are written as
  static functions of capability classes that take the core object as an
  argument: `fw_domain #(K)::set(comp, dom)`, not `comp.set_domain(dom)`.
- **State lives with the tool.** A capability keeps its per-object state
  behind the object's `fw_impl_if` handle (`core-layer1.md` §4.1), not in
  fields of the core class.
- **The spec/tool split is unchanged.** The spec declares the
  capability's classes, and each tool supplies the bodies: rt-sv in SV,
  fe-sv as intrinsics.
- **Extensibility.** A new capability, such as registers, debug access
  or a user's domain kind, adds classes and never edits the core. Two
  capabilities cannot collide over method names on `fw_component`.
- **Precedent in layer 1.** `fw_param_override`, `fw_param_edit`,
  `fw_value`/`fw_type` and `fw_extern_map` already work this way.

This applies to every domain operation below, including extern pin
mapping (§5) and crossing waivers (§6). The domain layer therefore adds
nothing to `fw_component`, the port and bundle classes, or
`fw_extern_map`.

---

## 1. Kinds and domains

Two layer-1 rules rule out the old model:
- Its providers were `fw_export`s made with `new(...)`, but every
  structural object comes from the factory.
- Its consumers were `fw_domain_port`s, transaction-level ports, but
  "port" means a signal port.

**Kind.** A domain kind is a class, registered like a component.
- A registration macro, `` `fw_domain_kind_utils(T) ``, gives the kind
  a `type_t` handle: one object per kind, returned by `T::get_type()`.
- The handle is the kind's identity everywhere:
  - It is the key for binding a domain to a component and for querying
    one (§2).
  - Generic code, the netlist and the IR name the kind through it.
  - Code that does not know `K` statically can still enumerate a
    component's bindings, or apply a kind's rules.
- A kind defines:
  - its params struct (properties and derivation, §3);
  - `relate(a, b)`, which returns same, related or unrelated;
  - the severity of a crossing for each relation;
  - its physical form when realized: a clock is a 1-bit net, a reset a
    1-bit net with a polarity. A pure marker kind has none.
- The library provides `fw_clock_kind` and `fw_reset_kind`. Power, macro
  membership or a user's kind are added the same way, with no change to
  the API.

**Domain.** `fw_domain #(K)` serves two purposes.
- **A domain object** is one instance of it: a particular clock or
  reset, such as `clk` or `div2`.
  - It is created through the factory in `build()`, by the component
    whose scope uses it: `fw_domain #(K)::create(name, parent, p)`.
  - It carries `K`'s params value (its properties and derivation) and a
    path name, so it appears in the netlist.
  - It is not a signal or a port, and it has no net of its own (§3).
- **A static API**, keyed by `K::get_type()`:

  | Call | Phase | Meaning |
  |---|---|---|
  | `create(name, parent, p)` | `build()` | declare a domain |
  | `set(obj, dom, name = "")` | `build()` | associate a component or an interface with `dom` |
  | `get(obj, name = "")` | any, after the association it reads | the domain a component or interface resolves to |
  | `relate(a, b)` | any | same, related or unrelated, by `K`'s rule |

- Typedefs name the library kinds' domains: `fw_clock_domain` is
  `fw_domain #(fw_clock_kind)` and `fw_reset_domain` is
  `fw_domain #(fw_reset_kind)`.

There are **no slot objects.** An earlier draft had `fw_domain_slot`, a
binding point declared by a component that spans domains. Named
associations (§2) cover that case with no extra object.

**Naming note.** The association call is not named `connect`, because
connections are allowed only in `connect()` (`FW-E-CONN-PHASE`) and
association happens in `build()`. It is not named `bind` either, because
`bind` is an SV keyword.

**Netlist.** It lists domain objects with their kind and params, every
`set`, and the drivers. The domain each object resolves to is derived,
not listed.

## 2. Association of sub-components and interfaces

```systemverilog
// parent build(): declare, then push down before the children build
div2 = fw_clock_domain::create("div2", this,
           fw_clock_kind::derived(.from(fw_clock_domain::get(this)), .div(2)));
u    = core::create("u", this);
fw_clock_domain::set(u, div2);            // u's clock domain
fifo = cdc_fifo::create("fifo", this);
fw_clock_domain::set(fifo, div2, "rd");   // a named association

// cdc_fifo build(): resolve, then assign interfaces
wr = fw_clock_domain::get(this, "wr");
rd = fw_clock_domain::get(this, "rd");
fw_clock_domain::set(in,  wr);
fw_clock_domain::set(out, rd);
if (fw_clock_domain::relate(wr, rd) == FW_DOMAIN_SAME) ...  // structure may depend on it
```

**Recommendation.**
- **Default association** of a component, `set(comp, dom)`:
  - It is made by the component's parent, in the parent's `build()`,
    after `create`. Since `build()` runs top-down (`core-layer1.md`
    §3.2), it is in place before the child's `build()`.
  - The top sets its own.
  - Without one, `get(comp)` resolves to the parent's domain of `K`,
    recursively up to the root.
- **Named association**, `set(comp, dom, "wr")`:
  - For a component that spans more than one domain of a kind.
  - The component reads it with `get(this, "wr")`.
  - An unset name resolves to the component's default domain of `K`. So
    a CDC FIFO used where both sides share one clock needs no
    association at all; it can tell from `relate` and build accordingly.
  - This replaces declared slot objects. The trade-off is that a
    misspelled name is caught only at the end of `build`: a named
    association that nothing read is `FW-E-DOM-UNUSED`.
- **Interfaces**, `set(intf, dom)`:
  - Made by the interface's own component, in its `build()`.
  - Without one, an interface resolves to its component's default domain
    of `K`.
  - A bundle is one interface in one domain. Its members follow it, and
    setting a member is `FW-E-DOM-OBJ`.
- **Querying**, `get(obj)` / `get(obj, name)`:
  - Valid on components and interfaces.
  - It is how `build()` code, the extern map and later layer-2 code see
    domains.
  - The result is `null` when no domain of `K` is found. That is legal
    until something needs the domain: an extern pin, the physical API, or
    a crossing rule that requires one. That case is `FW-E-DOM-NONE`.
- **Phase.** `set` is allowed only in `build()`; association in
  `connect()` would be too late for structure to depend on it. Anything
  else is `FW-E-DOM-PHASE`.
- **Other errors:**
  - setting the same object, name and kind twice is `FW-E-DOM-BIND`;
  - setting a component other than a direct child, itself as top, or one
    of its own interfaces is `FW-E-DOM-OBJ`.

Later: **declared relationship constraints.** A component class may state
how its named associations must relate, for example that `rd` and `wr`
are different domains (`get(this, "rd") != get(this, "wr")`), or that
they are unrelated. The check runs when associations are resolved.
- It turns a silent fallback into a diagnostic for a component that
  requires distinct domains.
- Its form follows the capability pattern: a static declaration on the
  domain classes, not a method on the component.

Later, maybe: associations by path override from a farther ancestor,
like parameter overrides (`soc` putting `chain.u[0]` into another
domain).

## 3. Derivation, drivers and physical realization

**Derived clocks and resets are declared, not generated.**
- A domain's params may say it derives from other domains of the same
  kind:
  ```systemverilog
  div2  = fw_clock_domain::create("div2", this,
              fw_clock_kind::derived(.from(clk), .div(2)));
  rst_s = fw_reset_domain::create("rst_s", this,
              fw_reset_kind::synced(.from(por), .clock(div2)));
  ```
- The kind defines which derivations exist:
  - **clock:** divide or multiply by a ratio, phase, gated, and muxed
    (derived from several clocks);
  - **reset:** synchronized to a clock, combined (OR of several resets),
    and software (a register bit gating another reset).
- What a derivation records:
  - **Relation:** a derived domain is *related* to its source, so
    crossings between them get the related severity.
  - **Modelling:** a simulation can tick `div2` from `clk` without any
    driver. This is the "delays" exception to pure markers.
  - **Constraints:** later SDC output can write
    `create_generated_clock` from it.
- A domain with no derivation is a **root domain**: a top input, or a
  clock produced inside the design, such as by a PLL.

**A driver produces the physical net.** A driver is needed only when the
domain is realized somewhere: an extern pin is mapped to it, or code uses
its physical API. Drivers are bridges between domains and signals, and
they are attached in one of two ways, never in `build()`:
- **From a signal, in `connect()`.** `dom.drive(sig)` makes `sig` the
  domain's net. The top creates and sets its domain in `build()`
  (`clk = fw_clock_domain::create("clk", this);
  fw_clock_domain::set(this, clk);`) and drives it from its input port in
  `connect()` (`clk.drive(clk_i);`).
- **From an extern output pin, in the map.**
  - A PLL or divider wrapper is given the domain it produces by a named
    association. Its parent does `fw_clock_domain::set(pll, div2, "out")`
    in `build()`.
  - The wrapper's map makes the pin drive it:
    `fw_clock_domain::pin_out(m, "clk_o", fw_clock_domain::get(this, "out"))`.
- **Checks:**
  - a domain realized somewhere with no driver is `FW-E-DOM-NODRIVER`;
  - two drivers for one domain is `FW-E-DOM-DRIVER`.
- **A driver may declare the derivation it implements**, for example a
  `clk_div #(2)` wrapper. When it does, it is checked against the domain
  it drives (`FW-E-DOM-DERIV`). The domain's declaration stays the
  authority.

**Generic declarations, application-specific drivers.** The core
provides:
- the kind and domain classes, and the derivations;
- the two bridges between domains and signals: `drive(sig)`, and
  extern pin mapping with `fw_domain #(K)::pin` and `pin_out`.

Dividers, synchronizers, reset combiners and soft-reset registers are
ordinary components: externs wrapping RTL now, layer-2 components with
sync code later. They belong in a small standard library on top of the
core, not in it.

The old model's built-ins (the `fw_clock_domain` divider,
`fw_reg_reset_domain`, `fw_reset_combine`) split in two: a derivation
records what a domain *is*, and an optional library driver produces it.

**Realization follows from use.** The domain's net exists in a module
only where its subtree needs it (§7). A marker kind, or a clock or reset
nobody realizes, emits nothing.

## 4. Kind properties: polarity and style (reset)

The old SV model keeps resets active-high inside the tree and inverts at
the root. zdc stores polarity and style on `ResetDomain`.

**Recommendation** (aligns with zdc):
- A reset **domain** records:
  - the polarity of its net, set by its driver (the top port's params,
    or the `pin_out` mapping);
  - its style: `async` (asynchronous assert, synchronous release) or
    `sync`.
- A reset **sink pin** declares the polarity it expects, through the
  reset kind's pin attributes:
  `fw_reset_domain::pin(m, "aresetn", null, fw_reset_kind::active_low())`. When that differs from the
  net's, emission inserts one inverted net per module that needs it.
- A sink may declare the style it requires. A mismatch is a warning.

## 5. Extern pin mapping

Pin mapping for domains is part of the domain capability too, not
methods on `fw_extern_map`:

```systemverilog
virtual function void extern_map(fw_extern_map m);
    fw_clock_domain::pin(m, "aclk");                                  // default clock
    fw_reset_domain::pin(m, "aresetn", null, fw_reset_kind::active_low());
    fw_clock_domain::pin(m, "wr_clk", fw_clock_domain::get(this, "wr"));
    fw_clock_domain::pin_out(m, "clk_o", fw_clock_domain::get(this, "out"));
    void'(m.prefix(s, "s_axis_t"));                                   // core map as before
endfunction
```

- `fw_domain #(K)::pin(m, pin, dom = null, attr = K::pin_default())`
  maps a sink pin to `dom`.
  - Omitted, `dom` is the extern's default domain of `K`.
  - `attr` is the kind's pin attributes value. For a reset that is the
    expected polarity and style; a clock has none yet.
- `fw_domain #(K)::pin_out(m, pin, dom, attr = ...)` makes the pin
  `dom`'s driver.
- **Any kind with a physical form maps pins the same way.** A power kind
  could map `pwr_ok` with no new API.
- A pin mapped to a domain is not a port of the wrapper. A layer-1
  wrapper's `clk`/`rst` ports, and its parent's connections to them, are
  deleted.
- **Consequence for layer 1** (*decided 2026-11-15*, option A of 5a).
  - `core-layer1.md` §3.6 had reserved `clock`, `reset`, `clock_out`
    and `reset_out` as `fw_extern_map` methods. The reservation is
    dropped, and `fw_extern_map` keeps no domain methods.
  - The map's pin check (`FW-E-EXT-PIN`, every module pin mapped exactly
    once) counts domain pins too. So the capability registers its pins
    through the map's tool-side state, not through new public methods.

## 6. Crossing analysis

The old check runs in simulation, as an SV walk after connect.
zuspec-synth has a separate `CDCAnalysisPass` that works from Python
classes. Neither one fits.

**Recommendation.**
- Represent domains, associations and drivers in Zuspec IR (§8). Run the
  check as a Zuspec pass over the structural IR.
  - fe-sv reports its diagnostics.
  - rt-sv applies the same rules, so both produce the same netlists and
    diagnostics in conformance.
- **A crossing** is a connection between two interfaces whose resolved
  domains of some kind differ. The kind's `relate()` gives the relation,
  and its table gives the severity:
  - **clock:** same is fine, related is info, unrelated is an error;
  - **reset:** related is a warning, unrelated is an error;
  - **marker kinds** declare their own (a macro kind might be info only;
    power would later require an isolation element).
- Structure only reaches the processes in layer 2. Until then, a check
  per connection is exact. Layer 2 extends it to a process that reads
  interfaces in two domains. That still follows from the interfaces, not
  from marking code.
- **Crossing elements and waivers:**
  - A component whose interfaces are set to different domains *is* the
    crossing element. Setting them is its permission, so there is no
    `is_crossing()` override.
  - `fw_domain #(K)::waive(a, b, reason)` in `connect()` waives a
    crossing of kind `K`; the reason is required. Waivers are listed in
    the netlist.
- **Configurable severities.** The severities above are each kind's
  defaults. An elaboration option (`Elaborate`, `fw_elab`) can change
  them per kind and relation. Unrelated reset domains are common in
  real SoCs, so a project may lower that error.
- **Reset synchronization:** a component whose reset domain is `sync` but
  whose reset's clock is unrelated to its clock domain gets a warning.
  This is the reset kind's rule, not special code.
- This pass replaces zuspec-synth's `CDCAnalysisPass`.

## 7. Emission (realized domains)

With one module per class (`core-layer1.md` §6.6), a module's ports must
be a function of the *class*, not of where an instance is used.

**Recommendation.**
- A domain is *realized in* a module when the module's subtree uses it
  physically:
  - an extern pin is mapped to it;
  - layer-2 code uses its physical API;
  - a pin of the subtree drives it.
- A generated module gets an input port for each association realized in
  its subtree whose driver is outside:
  - the default associations give `clk`, and `rst` or `rst_n` after the
    net's polarity;
  - a named association `wr` gives `wr_clk` and `wr_rst_n`.
- Two associations that resolve to the same domain at an instance stay
  two ports. The parent connects both to the same net.
- "Used" is decided per class, over all of its generated structure.
- **Name collisions.** A generated domain port whose name collides with
  another port of the module, for example a user port already named
  `clk`, is `FW-E-DOM-PORTNAME`. It is never renamed silently. The
  association can name its port explicitly to resolve the collision.
- A domain driven inside a module is a net there. It becomes an output
  port only if it is realized outside.
- A domain that is never realized emits nothing, and neither does a kind
  with no physical form. Marker kinds go to the IR and the netlist for
  later consumers: UPF for power, floorplan constraints for macros.
- This is done in `struct_flatten` (Zuspec), alongside bundle flattening.

## 8. Zuspec IR (new work item Z6)

ir-core today has:
- `DataTypeComponent.clock_domain` and `reset_domain`, which hold Python
  domain objects;
- `BlockSignature(clock, reset, reset_active_low)`;
- `Function.metadata['clock'/'reset']`.

None of it is serializable IR, and all of it is fixed to clock and reset.

**Recommendation.**
- **Types.**
  - `DataTypeDomainKind`: a name, a property schema, derivations and a
    physical form. The kind's `type_t` handle maps to it.
  - `DataTypeDomain`.
  - Clock and reset are instances of these, not dedicated classes, so a
    new kind needs no IR change.
- **Domain objects.** A domain object is a field with role
  `DomainRole.DOMAIN`. Its derivation is an expression over other domain
  fields.
- **Associations.** `DataTypeComponent.domain_assocs` holds entries of
  (target, kind, name, domain):
  - the target is a child, an interface or the component itself;
  - the domain is a path to a domain field, or to the parent's
    resolution.
- **Drivers.** `drive(sig)` is a `Bind` from the domain to a signal.
- **Extern pins.** `ExternPin` gains `domain` (a path or a named
  association), the kind's pin attributes, and `output` for
  `pin_out`.
- **Reconciliation.** `DataTypeComponent.clock_domain` / `reset_domain`
  and `BlockSignature`'s clock and reset are brought into line with
  these shapes, so the zdc front end produces the same IR. Check
  zuspec-dataclasses' users first; this is the part most likely to touch
  other work.

## 9. Scope of the first domain layer

In:
- the kind registration, `fw_domain #(K)` and its static API, and the
  clock and reset kinds with their derivations;
- default and named associations at build time, with lookup;
- interface association;
- drivers: `drive(sig)` and `pin_out`; realization on
  demand;
- extern pin mapping through the capability (`pin`, `pin_out`);
- reset polarity and style;
- emission of clock and reset ports and inversions;
- the static crossing check, with relations, severities and waivers;
- one marker kind, to prove extensibility: a toy `macro` kind with no
  physical form and an info-only rule, used only in tests;
- the netlist schema, conformance scenarios, rt-sv, fe-sv and Z6;
- migrating `wrap_rtl` and the smoke design.

Out, for later:
- the run lifecycle and `reset_state()` (layer 2);
- `tick`, `wait_assert` and other timing behavior, through the domain
  API (layer 2);
- a clock's period used for delays (the property is reserved now);
- clocks and resets made from synthesized logic (drivers written as
  layer-2 code);
- a standard library of drivers (dividers, reset synchronizers,
  combiners), which are ordinary components, not core;
- associations by path override from a farther ancestor;
- declared relationship constraints between a component's associations
  (`rd` != `wr`);
- a real power kind and UPF;
- SDC emission.

## 10. Decision list

| # | Question | Recommendation |
|---|---|---|
| 1 | What a domain is | *Decided 2026-11-15.* A structural marker on components and interfaces, never on code; physical only where its API is used |
| 2 | Extensibility | *Decided 2026-11-15.* Kind classes registered like components (`` `fw_domain_kind_utils ``); the kind's `type_t` handle is the key for association and query; clock and reset are library kinds |
| 3 | No union of all domains | *Decided 2026-11-15.* Per-kind lookup up the tree; only associations are stored |
| 4 | Objects | *Decided 2026-11-15.* Domain objects (`fw_domain #(K)::create`, factory-made, in the netlist); no slot objects |
| 5 | API shape | *Decided 2026-11-15.* A capability layer: static functions of `fw_domain #(K)` (`create`, `set`, `get`, `relate`, `pin`, `pin_out`, `waive`) that take core objects; state behind `fw_impl_if`; nothing added to `fw_component`, the port classes or `fw_extern_map`; not `connect` (phase rule) or `bind` (SV keyword) |
| 5a | Layer-1 reservation | *Decided 2026-11-15:* option A. Domain pins are mapped only through `fw_domain #(K)::pin`/`pin_out`; the reserved `clock`/`reset`/`clock_out`/`reset_out` names on `fw_extern_map` are dropped (done in `core-layer1.md` §3.6, `fw_extern_map.svh`, `semantics/signals.md`). Options B (shortcut methods), C (a kind-neutral `m.domain_pin`) and D (reuse `m.pin` with direction from the header) were rejected |
| 6 | Association | *Decided 2026-11-15.* `set(child, dom[, name])` by the parent in `build()`, before the child builds; `set(intf, dom)` by the interface's component; unset resolves by lookup |
| 7 | Multi-domain components | *Decided 2026-11-15:* named associations read with `get(this, name)`; an unset name resolves to the default; an unread name is `FW-E-DOM-UNUSED`. Later: declared relationship constraints (§2) |
| 8 | Query | *Decided 2026-11-15.* `get(obj[, name])` on components and interfaces; `null` is legal until a domain is needed (`FW-E-DOM-NONE`) |
| 9 | Derived clocks and resets | *Decided 2026-11-15.* Declared in the domain's params (`derived(.from, .div)`, `synced(.from, .clock)`, ...), giving relation, modelling and later SDC; no logic generated |
| 10 | Drivers | *Decided 2026-11-15.* Ordinary, application-specific components; attached by `dom.drive(sig)` in `connect()` or `fw_domain #(K)::pin_out` in the map; needed only when the domain is realized; a driver's own derivation is checked |
| 11 | Reset polarity and style | *Decided 2026-11-15.* Net polarity and style on the domain; expected polarity on each sink pin; inversions emitted |
| 12 | Crossing check | *Decided 2026-11-15.* Static Zuspec pass on IR, per connection between interfaces; each kind's relation and default severities, configurable per kind by an elaboration option; the spanning component is the crossing element; waivers need a reason |
| 13 | Module ports | *Decided 2026-11-15.* Per class: one per association realized in the subtree and driven from outside; unrealized domains and marker kinds emit nothing; a name collision is `FW-E-DOM-PORTNAME`, never a silent rename |
| 14 | IR (Z6) | *Decided 2026-11-15.* Generic domain-kind and domain types, associations on the component; reconcile `DataTypeComponent.clock_domain` and `BlockSignature` |
| 15 | Scope | *Decided 2026-11-15.* §9, including a toy marker kind to prove extensibility |
