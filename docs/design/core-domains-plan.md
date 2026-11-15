# Core domains: plan

This is the plan for the domain layer of the rebuilt fw-hdl core: clock
and reset domains, an open set of domain kinds, how components and
interfaces are associated with them, how they become nets, and the static
crossing check. It builds on `core-layer1.md` and follows its form.

The design and its reasons are in [core-domains.md](core-domains.md). Its
decisions (§10 there, all settled 2026-11-15) are taken as given here.
This file states them normatively, adds what implementing them needs, and
lists the questions planning raised (§10).

---

## User benefit

What a user of fw-hdl gets from this layer, compared with layer 1:

1. **No clock and reset wiring through the hierarchy.**
   - In layer 1 every wrapper declares `clk`/`rst` ports and every parent
     connects them, level by level.
   - With domains, a wrapper maps its clock pin in one line, and parents
     wire nothing. A pass-through level that never mentions clocks still
     gets the `clk` and `rst` ports it needs in the generated Verilog.
2. **Mixed reset polarities compose without hand-written inverters.** An
   active-low AXI block and an active-high FIFO share one reset. Each pin
   states the polarity it expects, and the generated Verilog inverts where
   they differ.
3. **Clock-domain crossings are caught at elaboration, before
   simulation.**
   - Connecting interfaces in unrelated clock domains without a crossing
     element is an error that names both endpoints.
   - A deliberate exception is a waiver with a required reason, and the
     waivers are listed in the netlist for review.
   - A user who knows their resets are independent lowers that severity
     once, per project.
4. **Structure can adapt to the clocking.** A block can ask how its two
   domains relate and build a plain FIFO when they are the same clock, or
   a CDC FIFO when they are not. The parent decides the clocking, and the
   block adapts.
5. **Derived clocks are declared once.** `div2` derived from `clk` by 2 is
   one line. The relation is then known everywhere: a crossing between
   them is information, not an error. The declaration is also what later
   SDC output and simulation models use.
6. **The output stays plain Verilog.** One module per class, with clock
   and reset ports under conventional names (`clk`, `rst_n`, `wr_clk`).
   The domain machinery leaves no runtime library or macros in the
   emitted RTL.
7. **Room for other kinds without waiting on the core.** Power, macro
   membership or a project's own kind are added as a class in user code.
   The kind is checked at connections and recorded in the netlist for
   downstream tools (UPF, floorplanning).
8. **Moving from layer 1 is local.** For each wrapper, delete the
   `clk`/`rst` ports, add one line per pin to its map, and delete the
   parent's connections to them.

Before and after, for `examples/wrap_rtl` (`fw-hdl-fe-sv`):

```systemverilog
// Layer 1: ports, pins and connections, in every class.
class axis_slice ...;
    fw_input #(bit) clk, rst_n;          // build(): two creates
    virtual function void extern_map(fw_extern_map x);
        x.pin("aclk", clk);
        x.pin("aresetn", rst_n);
        ...
class chain ...;
    fw_input #(bit) clk, rst, rst_n;     // two resets, one per polarity
    virtual function void connect();
        fifo.clk.connect(clk);   fifo.rst.connect(rst);
        slice.clk.connect(clk);  slice.rst_n.connect(rst_n);
        ...

// With domains: one line per pin; the parent wires nothing.
class axis_slice ...;
    virtual function void extern_map(fw_extern_map x);
        fw_clock_domain::pin(x, "aclk");
        fw_reset_domain::pin(x, "aresetn", null, fw_reset_kind::active_low());
        ...
class chain ...;
    fw_input #(bit) clk_i, rst_i;
    virtual function void build();
        clk = fw_clock_domain::create("clk", this);
        rst = fw_reset_domain::create("rst", this,
                  fw_reset_kind::root(.clock(clk)));
        fw_clock_domain::set(this, clk);
        fw_reset_domain::set(this, rst);
        ...
    virtual function void connect();
        clk.drive(clk_i);
        rst.drive(rst_i);                 // active-high net; aresetn gets an inverter
        ...
```

---

## 0. Status

Update this table as each step finishes (§9), so a fresh session can pick
up from this file.

| Step | Status | Notes |
|---|---|---|
| D0 Plan | done | This file (2026-11-15). Open questions in §10 need confirming before D1. |
| D1 Spec API and semantics | not started | |
| D2 rt-sv | not started | |
| D3 Z6 IR shapes | not started | |
| D4 fe-sv elaboration | not started | |
| D5 Zuspec domain passes | not started | |
| D6 Emission | not started | |
| D7 Extensibility, options, docs | not started | |
| D8 IR reconciliation with zdc | not started, gated | Touches zuspec-dataclasses and zuspec-synth users; start only on a go-ahead. |

---

## 1. Scope

### In scope

| Concept | SV binding names |
|---|---|
| Kind handle | `fw_domain_kind_type`; `` `fw_domain_kind_utils(T) `` gives `T::get_type()` |
| Kind base | `fw_domain_kind` |
| Domain object, and the static API | `fw_domain_base`, `fw_domain #(K)`: `create`, `set`, `get`, `relate`, `pin`, `pin_out`, `waive`; `dom.drive(sig)` |
| Library kinds | `fw_clock_kind`, `fw_reset_kind`; typedefs `fw_clock_domain`, `fw_reset_domain` |
| Relations | `fw_domain_rel_e`: `FW_DOMAIN_SAME`, `FW_DOMAIN_RELATED`, `FW_DOMAIN_UNRELATED` |
| Derivations | clock: `derived(.from, .div, .mul)`, `phase`, `gated`, `muxed`; reset: `synced(.from, .clock)`, `combined`, `software` |
| Reset properties | net polarity and style on the domain; expected polarity and style on each sink pin |
| Crossing check | per connection between interfaces; per-kind severities, configurable; waivers |
| Emission | module ports per class from the domains its subtree realizes; internal domain nets; inversions |
| Netlist | domain objects, associations, drivers, domain pins and waivers |
| Zuspec | Z6 domain IR, and the relation, crossing and realization passes |

The scope list in `core-domains.md` §9 is authoritative for what is in and
out. Out, for later: the run lifecycle, `tick` and other timing behavior
(layer 2), clock periods for delays, drivers written as layer-2 code, a
standard library of drivers, associations by path override, declared
relationship constraints, a real power kind, UPF and SDC output.

**Acceptance criterion for the layer.**
- `examples/wrap_rtl` is migrated: no `clk`/`rst` ports on the wrappers
  and no clock or reset connections in `chain`. Its emitted Verilog lints
  clean under `verilator -Wall` and matches the hand-wired reference
  cycle for cycle (adapted to one reset input, since the inverter is now
  generated).
- A new example, `examples/domains`, has two unrelated clocks, a divided
  clock produced by a wrapped divider (`pin_out`), a dual-clock FIFO
  wrapper with named associations, a block that chooses its FIFO by
  `relate`, and resets of both polarities. It emits lint-clean Verilog
  that matches a hand-wired reference in simulation. A variant with a
  missing crossing element fails elaboration with the crossing error.
- rt-sv and fe-sv produce identical netlists and diagnostics for every
  domain conformance scenario they can both run.
- A kind defined only in a test (the toy `macro` kind) is associated,
  checked at connections and listed in the netlist, with no change to the
  core.

---

## 2. Where the code lives

No new repos. Each part goes where its layer-1 counterpart is.

| Part | Where |
|---|---|
| API declarations | `fw-hdl-spec/bindings/sv/`: `fw_domain_kind_type.svh`, `fw_domain_kind.svh`, `fw_domain_base.svh`, `fw_domain.svh`, `fw_clock_kind.svh`, `fw_reset_kind.svh`; `fw_domain_rel_e` and the typedefs in `fw_hdl_api.svh`; `` `fw_domain_kind_utils `` in `fw_hdl_macros.svh` |
| Semantics | `fw-hdl-spec/semantics/domains.md`; new rows in `diagnostics.md`; `netlist.md` and `netlist.schema.json` |
| Conformance | `fw-hdl-spec/conformance/dom_*` and `kind_user` |
| Reference runtime | `fw-hdl-rt-sv/sv/`: the bodies, and the crossing check |
| Static front end | `fw-hdl-fe-sv/python/fw/hdl/fe/sv/`: intrinsics in `rt.py`, objects in `objects.py`, checks in `resolve.py`, `netlist.py`, `ir_map.py`; a new `domains.py` for the fe-sv side of domain state |
| IR | `zuspec-ir-core`: Z6 shapes (§6.2) |
| Passes | `zuspec-synth/passes/domains/`: relation, crossing, realization (§6.3) |
| Emission | `zuspec-synth/passes/struct_flatten.py` (ports, nets, inversions); be-sv unchanged if possible |
| Examples | `fw-hdl-fe-sv/examples/domains`, and the migrated `examples/wrap_rtl` |
| User docs | `fw-hdl-spec/docs/domains.rst`; the wrapping guide and the `wrap_rtl` README updated |

The dependency lint (`tools/layer1_dep_lint.py`) covers the new files
unchanged. The old SV domain code (`src/fw_domain_if.svh`,
`fw_domains.svh`, `fw_clock_domain*.svh`, `fw_reset_*.svh`,
`fw_crossing*.svh`) is reference only, as in layer 1.

---

## 3. Semantics

Normative. It becomes `semantics/domains.md`. Section numbers in
`core-domains.md` are given for the reasons.

### 3.1 Kinds

- A **kind** is a class that extends `fw_domain_kind` and uses
  `` `fw_domain_kind_utils(T) ``. The macro declares
  `static function fw_domain_kind_type get_type()`, which returns one
  object per kind.
- The kind handle, `fw_domain_kind_type`, is the kind's identity: the key
  for associations, the name in the netlist (`name()` returns the class
  name, as `type_name` spells it), and the way code that does not know
  `K` statically reaches the kind's rules.
- A kind declares, as static members:
  - `params_t`: a struct with the domain's properties and its
    derivation;
  - one static function per derivation, returning a `params_t`, and
    `root(...)` for a domain with none;
  - `pin_attr_t` and `pin_default()`: the attributes a pin mapped to the
    domain states (§3.7);
  - `severity(fw_domain_rel_e r)`: the default severity of a crossing
    with relation `r`;
  - `physical()`: 1 when the domain is a 1-bit net when realized, 0 for a
    marker kind;
  - `port_name(string assoc, pin_attr_t attr)`: the name of a generated
    port (§3.8).
- The library provides `fw_clock_kind` and `fw_reset_kind`. A user kind is
  declared the same way, in user code (§10 Q1 covers how relations are
  computed).

This is the first type handle in the core. Components do not have one in
layer 1. When factory substitution gives components a type handle, the
two should share a base.

### 3.2 Domain objects

- `fw_domain #(K)::create(name, parent, p = K::root())` declares a domain
  object, during `build()`. It is factory-made and named like any
  structural object: it takes part in `FW-E-NAME-DUP`, and in
  `FW-E-ELAB-LATE` when created after `build()`.
- A domain object is not a signal, port or child component. It is listed
  under its parent in the netlist with its kind, params and derivation.
- **Derivation.** `params_t` may name source domains of the same kind
  (`derived(.from(clk), .div(2))`) and domains of other kinds
  (`synced(.from(por), .clock(div2))`: `por` is a source, `div2` is not).
  A domain with no source of its own kind is a **root domain**.
- A derivation's source must be a domain object visible to the creating
  code: one it created, or one it got by `get`. A source of the wrong kind
  is `FW-E-DOM-KIND`.

### 3.3 Association and lookup

Per kind `K`, keyed by `K::get_type()`:

- `set(comp, dom, name = "")` associates a component with `dom`.
  - Legal on a direct child, during the parent's `build()`, after the
    child's `create`; or on the top itself, during its own `build()`.
  - `name = ""` is the **default association**; any other name is a
    **named association**.
- `set(intf, dom)` associates an interface (a port or a bundle in a role)
  with `dom`, during the `build()` of the interface's component. A bundle
  is one interface: setting a member of a bundle is `FW-E-DOM-OBJ`. An
  interface has no named associations.
- **Lookup**, `get(obj, name = "")`:
  - a component's default: its own default association, else its
    parent's resolved default, up to the root, else `null`;
  - a component's named association: its own, else the component's
    resolved default;
  - an interface: its own association, else the enclosing bundle's, else
    its component's resolved default.
- `get` is legal in any phase, and reads only associations made so far.
  `null` is legal until something needs the domain (§3.6, §3.7, §3.9):
  then `FW-E-DOM-NONE`, on the object that needed it.
- Errors:
  - `set` outside `build()`: `FW-E-DOM-PHASE`;
  - the same object, kind and name set twice: `FW-E-DOM-BIND`;
  - a target that is not a direct child, the top itself, or the
    component's own interface: `FW-E-DOM-OBJ`;
  - a named association that the component's code never read with `get`
    by the end of `build()`: `FW-E-DOM-UNUSED`, on the component, naming
    the association.

### 3.4 Relation

`fw_domain #(K)::relate(a, b)` returns:
- `FW_DOMAIN_SAME` when `a` and `b` are the same domain object;
- `FW_DOMAIN_RELATED` when they share a root domain, following sources of
  kind `K` through derivations;
- `FW_DOMAIN_UNRELATED` otherwise.

`relate` with a `null` argument is `FW-E-DOM-NONE`. The relation is a
function of the declarations alone, so it is available in `build()` and is
the same in every implementation and pass (§10 Q1).

### 3.5 Drivers

A **driver** produces a domain's net.
- `dom.drive(sig, attr = K::pin_default())`, in `connect()`: the signal
  `sig` (a port or local signal in the caller's scope) is the net.
  - `attr` is the net's attributes: for a reset, its polarity.
  - Outside `connect()`: `FW-E-DOM-PHASE`. A signal out of scope:
    `FW-E-CONN-SCOPE`. A signal wider than 1 bit: `FW-E-DOM-PIN`.
- `fw_domain #(K)::pin_out(m, pin, dom, attr)`, in an extern map: the
  module's output pin is the net (§3.7).
- Checks, on the domain:
  - more than one driver: `FW-E-DOM-DRIVER`;
  - realized (§3.6) with no driver: `FW-E-DOM-NODRIVER`.
- A driver may declare the derivation it implements (§10 Q7). When it does,
  a mismatch with the domain it drives is `FW-E-DOM-DERIV`.
- Drivers do not change relations. Relations come only from declarations.

### 3.6 Realization

A domain of a kind with a physical form is **realized** when something
uses it physically:
- an extern pin is mapped to it (`pin` or `pin_out`);
- a signal drives it (`drive`);
- (layer 2) code uses its physical API.

Realization is what makes a driver required, and what gives generated
modules their domain ports (§3.8). A domain that is never realized, and
every domain of a marker kind, stays a marker.

### 3.7 Extern pins

- `fw_domain #(K)::pin(m, pin, dom = null, attr = K::pin_default())`
  maps an input pin of the module to `dom`; `null` means the extern's
  resolved default of `K`.
- `fw_domain #(K)::pin_out(m, pin, dom, attr = K::pin_default())` maps an
  output pin, which drives `dom`. `dom` is required.
- Domain pins count toward the map's own rules. A pin mapped twice, by
  any mix of `m.pin`, `m.tie`, `m.open` and domain pins, is
  `FW-E-EXT-PIN`. With the module header (static only): a domain pin the
  module lacks is `FW-E-EXT-PIN`; a domain pin of the wrong direction or
  wider than 1 bit is `FW-E-DOM-PIN`.
- **Reset attributes.** `fw_reset_kind::pin_attr_t` has `active_low` and
  `style` (`async`, `sync`, or `any`). `active_low()` and `active_high()`
  return attribute values. On `pin`, they are what the pin expects; on
  `pin_out` and `drive`, they describe the net.
- **Reset checks.**
  - A sink whose expected polarity differs from the net's gets an
    inverter (§3.8). This is not a diagnostic.
  - A sink whose required style differs from the domain's:
    `FW-W-DOM-STYLE`, on the pin's extern.
  - A component whose reset domain is `synced` to a clock unrelated to its
    clock domain: `FW-W-DOM-RSTSYNC`. This is the reset kind's rule.

### 3.8 Emission

One module per class (`core-layer1.md` §6.6). For each class:
- An **association is realized in the class** when its resolved domain is
  realized inside the class's subtree, over every generated arm and
  iteration.
- Each realized association whose driver is outside the subtree is an
  **input port**, named by `K::port_name(assoc, attr)`: `clk`, `wr_clk`,
  `rst`, `rst_n`, `wr_rst_n`.
- Each association driven inside the subtree, by a `pin_out` there, is an
  **output port** of the class (§10 Q4).
- Two associations that resolve to the same domain at an instance stay
  two ports. The parent connects both to the same net.
- A domain created in the class and realized only inside it is a local
  net.
- **Reset polarity of a port.** A reset port's polarity is a property of
  the class: the polarity its subtree's sinks expect when they agree,
  else active high (§10 Q3). Where a net feeds a port or pin of the other
  polarity, the module that makes the connection declares one inverted
  net per domain and uses it for all such sinks.
- A generated port name that collides with another port of the module is
  `FW-E-DOM-PORTNAME`, on the class's first instance. Never renamed
  silently. The component can name the port itself (§10 Q6).
- Marker kinds, and domains never realized, emit nothing.

### 3.9 Crossing check

- A **crossing** is a connection between two interfaces whose resolved
  domains of some kind differ. For each kind, the kind's relation
  (§3.4) selects a severity, and that severity's diagnostic is reported
  on the connection's first endpoint:
  `FW-E-DOM-CROSS`, `FW-W-DOM-CROSS` or `FW-I-DOM-CROSS`. The message
  names the kind, both endpoints and both domains.
- What counts as the connection's endpoints, when nets pass through local
  signals, is §10 Q2.
- Default severities:

  | Kind | same | related | unrelated |
  |---|---|---|---|
  | clock | none | info | error |
  | reset | none | warning | error |
  | `macro` (toy, tests only) | none | info | info |

- **Severities are configurable** per kind and relation by an
  elaboration option: dfm `Elaborate` parameter `domain_severity`
  (`{"fw_reset_kind": {"unrelated": "warning"}}`), and the rt-sv
  `fw_elab` plusarg `+fw_dom_sev=fw_reset_kind.unrelated=warning`.
  `none` silences.
- An interface whose domain of `K` resolves to `null` is not checked for
  `K`.
- **Crossing elements.** A component whose interfaces are in different
  domains is the crossing element. That is not a diagnostic.
- **Waivers.** `fw_domain #(K)::waive(a, b, reason)`, in `connect()` of
  the component that connects `a` and `b`, waives the crossing of kind
  `K` between them. An empty reason is `FW-E-DOM-WAIVE`. A waiver that
  matches no crossing is `FW-W-DOM-WAIVE`. Waivers are listed in the
  netlist.

### 3.10 Diagnostics

New rows for `diagnostics.md`. It also gains the `FW-I-` level
(information), which fe-sv already uses for `FW-I-EMIT-SPEC`.
Conformance compares `FW-I-` diagnostics like the others.

| ID | Condition | Path |
|---|---|---|
| `FW-E-DOM-PHASE` | `set` outside `build()`; `drive` or `waive` outside `connect()` | the target, the domain, or the first endpoint |
| `FW-E-DOM-BIND` | the same object, kind and name set twice | the target |
| `FW-E-DOM-OBJ` | `set` on an object that is not a direct child, the top itself, or an own interface; on a bundle member | the target |
| `FW-E-DOM-UNUSED` | a named association never read by the component's code | the component |
| `FW-E-DOM-NONE` | a needed domain resolves to `null` | the object that needed it |
| `FW-E-DOM-KIND` | a derivation source of the wrong kind | the domain being created |
| `FW-E-DOM-DRIVER` | more than one driver | the domain |
| `FW-E-DOM-NODRIVER` | realized with no driver | the domain |
| `FW-E-DOM-DERIV` | a driver's declared derivation differs from its domain's | the driver's component |
| `FW-E-DOM-PIN` | a domain pin or driven signal wider than 1 bit; a domain pin of the wrong direction (header check) | the extern, or the signal |
| `FW-E-DOM-PORTNAME` | a generated domain port collides with a port (static only) | the class's first instance |
| `FW-E-/W-/I-DOM-CROSS` | a crossing, at its kind's severity for the relation | the first endpoint |
| `FW-E-DOM-WAIVE` | a waiver with an empty reason | the first endpoint |
| `FW-W-DOM-WAIVE` | a waiver that matches no crossing | the first endpoint |
| `FW-W-DOM-STYLE` | a reset sink's required style differs from the domain's | the extern |
| `FW-W-DOM-RSTSYNC` | a `synced` reset whose clock is unrelated to the component's clock domain | the component |

### 3.11 Netlist

The schema gains, per component object:
- `domains`: `[{"name", "kind", "params": {...}, "deriv": {"op",
  "sources": [path], "args": {...}}}]`; params values are written as in
  `fw_value` (`core-layer1.md` §3.11), domain handles as paths;
- `assocs`: `[{"target": rel path or "", "kind", "name", "domain":
  path}]`, in call order;
- `drivers`: `[{"domain": path, "signal": path, "attr": {...}}]`;
- `waivers`: `[{"kind", "a": path, "b": path, "reason"}]`;
- on an extern: `domain_pins`: `[{"pin", "kind", "domain": path, "dir":
  "in" | "out", "attr": {...}}]`.

The domain each object resolves to is derived, not listed. Realization
and generated ports are emission, not netlist.

---

## 4. SV binding

Declarations only, as in layer 1 (`core-layer1.md` §4.1): the spec
declares, each tool supplies bodies. State lives behind `fw_impl_if`.

```systemverilog
typedef enum { FW_DOMAIN_SAME, FW_DOMAIN_RELATED, FW_DOMAIN_UNRELATED } fw_domain_rel_e;
typedef enum { FW_SEV_NONE, FW_SEV_INFO, FW_SEV_WARNING, FW_SEV_ERROR } fw_severity_e;

// A kind's handle: one object per kind.
virtual class fw_domain_kind_type;
    pure virtual function string name();
    pure virtual function fw_severity_e severity(fw_domain_rel_e r);
    pure virtual function bit physical();
endclass

// Base of every kind. Kinds have only static members; this class has none.
virtual class fw_domain_kind;
endclass

// Any domain object, of any kind.
virtual class fw_domain_base extends fw_object;
    extern function fw_domain_kind_type kind();
endclass

class fw_domain #(type K = fw_domain_kind) extends fw_domain_base;
    typedef fw_domain #(K) this_t;
    typedef K::params_t    params_t;     // class-local typedefs: §10 Q2 of core-layer1.md
    typedef K::pin_attr_t  pin_attr_t;

    extern static function this_t create(string name, fw_component parent,
                                         params_t p = K::root());
    extern static function void   set(fw_object obj, this_t dom, string name = "");
    extern static function this_t get(fw_object obj, string name = "");
    extern static function fw_domain_rel_e relate(this_t a, this_t b);
    extern static function void   pin(fw_extern_map m, string pin, this_t dom = null,
                                      pin_attr_t attr = K::pin_default());
    extern static function void   pin_out(fw_extern_map m, string pin, this_t dom,
                                          pin_attr_t attr = K::pin_default());
    extern static function void   waive(fw_object a, fw_object b, string reason);

    extern function void     drive(fw_signal_base sig, pin_attr_t attr = K::pin_default());
    extern function params_t params();
endclass

typedef fw_domain #(fw_clock_kind) fw_clock_domain;
typedef fw_domain #(fw_reset_kind) fw_reset_domain;
```

The library kinds:

```systemverilog
class fw_clock_kind extends fw_domain_kind;
    `fw_domain_kind_utils(fw_clock_kind)
    typedef enum { ROOT, DERIVED, PHASE, GATED, MUXED } deriv_e;
    typedef struct {
        deriv_e         deriv;
        fw_domain_base  from[$];        // sources of this kind
        int             div, mul, phase_deg;
        real            period_ns;      // reserved: delays are layer 2
    } params_t;
    typedef struct { bit reserved; } pin_attr_t;

    static function params_t root(real period_ns = 0);
    static function params_t derived(fw_domain_base from, int div = 1, int mul = 1);
    static function params_t phase(fw_domain_base from, int deg);
    static function params_t gated(fw_domain_base from);
    static function params_t muxed(fw_domain_base from[$]);
    static function pin_attr_t     pin_default();
    static function fw_severity_e  severity(fw_domain_rel_e r);
    static function bit            physical();
    static function string         port_name(string assoc, pin_attr_t attr);   // clk, <assoc>_clk
endclass

class fw_reset_kind extends fw_domain_kind;
    `fw_domain_kind_utils(fw_reset_kind)
    typedef enum { ROOT, SYNCED, COMBINED, SOFTWARE } deriv_e;
    typedef enum { ASYNC, SYNC, ANY } style_e;
    typedef struct {
        deriv_e         deriv;
        fw_domain_base  from[$];        // reset sources
        fw_domain_base  clock;          // SYNCED: the clock (not a source)
        style_e         style;
    } params_t;
    typedef struct { bit active_low; style_e style; } pin_attr_t;

    static function params_t root(fw_domain_base clock = null, style_e style = ASYNC);
    static function params_t synced(fw_domain_base from, fw_domain_base clock);
    static function params_t combined(fw_domain_base from[$]);
    static function params_t software(fw_domain_base from);
    static function pin_attr_t active_low(style_e style = ANY);
    static function pin_attr_t active_high(style_e style = ANY);
    ...                                  // pin_default (active high), severity, physical, port_name
endclass
```

Notes:
- The kind statics are ordinary SV with bodies in the spec, not tool
  bodies: they are the kind's definition, and a user kind writes its own.
  Only `fw_domain #(K)`'s functions are tool bodies.
- `` `fw_domain_kind_utils(T) `` expands to `get_type()`, returning a
  spec-provided `fw_domain_kind_type_of #(T)` singleton that forwards
  `severity` and `physical` to `T`'s statics.
- `set` and `get` take `fw_object`, so the target kind (component or
  interface) is checked at run time (`FW-E-DOM-OBJ`), not by the
  compiler.

The worked example is the `examples/domains` design (§1). It is written
in D6, and goes into `semantics/domains.md` and the user guide.

---

## 5. rt-sv

- Bodies for `fw_domain #(K)`; per-object association tables in the
  tool's `fw_impl_if` objects, keyed by kind handle and name.
- `relate` by walking sources (§3.4); the same algorithm as the Zuspec
  pass (§6.3), written in SV.
- Drivers and domain pins recorded with the map's existing tool-side
  state, so `FW-E-EXT-PIN` counts them.
- After `connect()`: the `UNUSED`, `NONE`, `DRIVER`, `NODRIVER`,
  `RSTSYNC` checks, and the crossing check over recorded connections.
  Severity option from `+fw_dom_sev`.
- The netlist writer emits §3.11.
- Not in rt-sv: header checks and emission (`FW-E-DOM-PIN` direction,
  `FW-E-DOM-PORTNAME`). Those scenarios are `static-only`.

---

## 6. fe-sv and Zuspec

### 6.1 fe-sv elaboration

- Intrinsics in `rt.py` for every `fw_domain #(K)` function, on the
  interpreter's class specializations of `fw_domain`. Kind statics run in
  the interpreter as user code.
- `domains.py`: `FwDomain` objects (name, parent, kind, params value,
  derivation), association tables on `FwObject`, drivers, domain pins,
  waivers; and the lookup of §3.3, which `get` needs during `build()`.
- `relate` during `build()` calls the Zuspec relation function (§6.3) on
  fe-sv's objects through a small adapter, so the rule has one
  implementation on the static side.
- `resolve.py`: the checks of §3.3 to §3.7 that need no IR.
- `netlist.py`: §3.11.
- Tracing (§6.6 of `core-layer1.md`): `create` and `set` record their
  traced frames like `create` and `connect` do. A domain created, or an
  association whose target or domain differs, under a loop or a branch on
  parameters is first emitted as a specialization (`FW-I-EMIT-SPEC`).
  Associations that are the same in every iteration and arm are general.

### 6.2 Z6: IR shapes (ir-core)

| Shape | Fields |
|---|---|
| `DataTypeDomainKind` | `name`, `physical: bool`, `derivations: Dict[str, DomainDerivDecl(sources: List[str])]` (which arguments are same-kind sources), `severities: Dict[rel, sev]`, `port_names: Dict[str, str]` (computed by fe-sv per used association) |
| `DataTypeDomain` | `kind`: the kind's name in `type_m` |
| `DomainDecl` | `name`, `kind`, `deriv: str`, `sources: List[DomainRef]`, `args: Dict[str, Expr]`, `params: Dict[str, Expr]` |
| `DomainRef` | either a `DomainDecl` of this component by name, or a resolution `(kind, assoc name)` of this component |
| `DomainAssoc` | `target: List[str]` (field path, `[]` = self, may hold index expressions), `kind`, `name`, `domain: DomainRef` |
| `DomainDriver` | `domain: DomainRef`, `signal: List[str]`, `attr: Dict[str, Expr]` |
| `DomainWaiver` | `kind`, `a`, `b`: paths; `reason` |
| `DataTypeComponent` | gains `domains: List[DomainDecl]`, `domain_assocs`, `domain_drivers`, `domain_waivers` |
| `ExternPin` | gains `domain: Optional[DomainRef]`, `domain_kind`, `domain_attr`, `output: bool` |

- All of it round-trips through the serializer; kinds are stored once in
  `type_m`, like the types package's types.
- Clock and reset are *instances* of `DataTypeDomainKind`, so a new kind
  needs no IR change.
- Nothing existing changes in D3: `clock_domain`, `reset_domain`,
  `BlockSignature` and `Function.metadata` are left alone until D8.

### 6.3 Zuspec passes (zuspec-synth `passes/domains/`)

- **Relation.** `relate(a, b)` over a domain graph interface that both the
  IR and fe-sv's objects implement (§6.1).
- **Resolution.** For each instance path: each kind's default and named
  associations, and each interface's domain, by §3.3.
- **Crossing.** Over the connections of every component (`bind_map`
  after Z3's resolution of nets), by §3.9, with the severity option.
  It returns diagnostics; fe-sv reports them. It replaces
  `CDCAnalysisPass` for fw-hdl designs; for zdc designs, see D8.
- **Realization.** Per class (§3.8): the realized associations, their
  directions, the per-class reset polarity, `NODRIVER` and
  `PORTNAME`. Its result is a list of domain ports per class, which
  `struct_flatten` consumes.

fe-sv runs the relation, resolution and crossing passes as part of
elaboration, so the crossing diagnostics are elaboration diagnostics and
appear in the conformance results. It runs realization before
`struct_flatten`.

### 6.4 Emission (`struct_flatten`)

- Adds each class's domain ports to its module, before bundle flattening
  so the name check sees every port.
- Per instance: connects each domain port and domain pin to the net of
  the domain it resolves to at that instance; declares a local net for a
  domain created and realized in the class; declares the inverted nets.
- Drivers: `drive(sig)` becomes an `assign` from the signal, or the
  signal's net is used directly; `pin_out` connects the output pin to the
  domain's net.
- be-sv should need nothing new: domain ports and nets are ordinary
  ports, nets and assigns by then.

### 6.5 dfm

- `Elaborate` gains `domain_severity` (a map, §3.9).
- The rt-sv runner passes `+fw_dom_sev`.

---

## 7. Conformance and tests

| Level | What | Runs against |
|---|---|---|
| Conformance | `fw-hdl-spec/conformance/dom_*`, `kind_user` | rt-sv (Verilator) and fe-sv |
| Zuspec unit | Z6 round-trip; relation, resolution, crossing and realization on hand-built IR | pytest in ir-core and zuspec-synth |
| fe-sv unit | intrinsics, lookup during `build()`, tracing of associations | pytest |
| End to end | `examples/wrap_rtl` migrated; `examples/domains` (§1): emit, `verilator -Wall`, simulate against a hand-wired reference; the crossing-error variant | pytest + dfm |

Scenarios, about 26:
- `dom_create`: domain objects, every derivation, netlist form;
- `dom_create_late`: `FW-E-ELAB-LATE`;
- `dom_kind`: `FW-E-DOM-KIND`;
- `dom_lookup`: default association inherited three levels, set on a
  middle level;
- `dom_named`: named associations, read, and an unset name falling back;
- `dom_unused`: `FW-E-DOM-UNUSED`;
- `dom_phase`: `FW-E-DOM-PHASE` for `set`, `drive` and `waive`;
- `dom_bind`: `FW-E-DOM-BIND`;
- `dom_obj`: `FW-E-DOM-OBJ` (grandchild, bundle member, a sibling's
  port);
- `dom_intf`: interfaces set, bundles one interface, members following;
- `dom_none`: `FW-E-DOM-NONE` (pin with no domain; `relate(null, x)`);
- `dom_relate`: `relate` in `build()` choosing structure;
- `dom_drive`: a top driving from its input ports; drive attributes;
- `dom_driver`: `FW-E-DOM-DRIVER`;
- `dom_nodriver`: `FW-E-DOM-NODRIVER`;
- `dom_pin`: default, named and explicit domain pins, attributes;
- `dom_pin_out`: a divider wrapper producing a parent's domain;
- `dom_pin_dup`: `FW-E-EXT-PIN` with a domain pin;
- `dom_pin_hdr`: `FW-E-DOM-PIN` direction and width (static only);
- `dom_cross_clock`: same, related (info), unrelated (error);
- `dom_cross_reset`: related (warning), unrelated (error);
- `dom_cross_elem`: a spanning component is not a crossing;
- `dom_waive`: a waiver; `FW-E-DOM-WAIVE`; `FW-W-DOM-WAIVE`;
- `dom_rst_style`: `FW-W-DOM-STYLE`; `dom_rst_sync`: `FW-W-DOM-RSTSYNC`;
- `dom_portname`: `FW-E-DOM-PORTNAME` (static only);
- `kind_user`: the toy `macro` kind, declared in the scenario.

Severity options are tested end to end, not in conformance, since the
scenario format has no options.

---

## 8. Relationship to existing code

| Existing | Becomes | When |
|---|---|---|
| `src/fw_domain_if.svh`, `fw_domains.svh` | reference for kinds and lookup | D1 |
| `src/fw_domain_port.svh` | nothing: named associations replace domain ports | — |
| `src/fw_clock_domain*.svh`, `fw_reg_reset_domain`, `fw_reset_combine` | the derivations of `fw_clock_kind`/`fw_reset_kind`; drivers become library components, later | D1; later |
| `src/fw_crossing*.svh` | the crossing pass (§6.3) | D5 |
| zuspec-synth `CDCAnalysisPass` | replaced by the crossing pass for fw-hdl; for zdc in D8 | D5, D8 |
| ir-core `DataTypeComponent.clock_domain`/`reset_domain` | derived from the Z6 shapes | D8 |
| `BlockSignature.clock`/`reset`/`reset_active_low`, `Function.metadata['clock'/'reset']` | reconciled with Z6 (layer 2 and engines) | D8 or layer 2 |
| zuspec-be-py `model/domain.py` | unchanged; zdc maps its classes to Z6 in D8 | D8 |

---

## 9. Work plan

Each step ends with its exit criterion met. Update §0 as steps finish.

- **D1. Spec API and semantics.**
  - The §4 declarations, the two library kinds with their static bodies,
    the macro; the API check and spec lint extended to them.
  - `semantics/domains.md`, the §3.10 diagnostics, the §3.11 schema.
  - The §7 scenarios with hand-written expectations.
  - *Exit:* every scenario's `top.sv` compiles against `fw_hdl_pkg`
    under Verilator; the API check passes.
- **D2. rt-sv.**
  - §5.
  - *Exit:* every non-`static-only` domain scenario passes; layer-1
    scenarios still pass.
- **D3. Z6 IR shapes.**
  - §6.2 in ir-core, with round-trip tests.
  - *Exit:* ir-core suite passes; a component with every shape
    round-trips.
- **D4. fe-sv elaboration.**
  - §6.1, and `ir_map.py` filling the Z6 shapes.
  - *Exit:* every domain scenario that needs no crossing check passes on
    fe-sv, with netlists equal to rt-sv's.
- **D5. Zuspec domain passes.**
  - §6.3, run by fe-sv.
  - *Exit:* every domain scenario passes on fe-sv, crossing ones
    included, matching rt-sv; zuspec-synth unit tests for each pass.
- **D6. Emission.**
  - §6.4, the realization pass's use in `struct_flatten`, and the
    parameterized cases of §6.1.
  - Migrate `examples/wrap_rtl`; write `examples/domains` with its
    hand-wired reference and the crossing-error variant.
  - *Exit:* the §1 acceptance criterion, except the toy kind.
- **D7. Extensibility, options, docs.**
  - The `kind_user` scenario end to end (netlist, crossing, nothing
    emitted); `domain_severity` and `+fw_dom_sev`; `docs/domains.rst`;
    the wrapping guide and `wrap_rtl` README updated.
  - *Exit:* the full §1 criterion; the docs build with `-W`; dfm
    `sim` passes for both examples.
- **D8. IR reconciliation with zdc (gated).**
  - Make the zdc factory emit Z6 for its `ClockDomain`/`ResetDomain`
    class attributes; make `DomainBinding.from_component_ir`
    (zuspec-synth `sprtl/fsm_ir.py`) the single reader of Z6;
    `clock_domain`/`reset_domain` become read-only views kept for
    `component_fields.py` and be-sw `c_emit.py`; replace
    `CDCAnalysisPass` for zdc designs.
  - Users today (survey 2026-11-15): the zdc factory writes the fields
    (`data_model_factory.py:848-902`); `DomainBinding`, `CDCAnalysisPass`,
    `component_fields.py`, synth `__init__.py` and be-sw `c_emit.py` read
    them, by isinstance on zdc classes. ir-core, be-sv and both SV front
    ends do not use them. No test round-trips them through the
    serializer.
  - *Exit:* zuspec-dataclasses and zuspec-synth suites pass unchanged in
    count; a zdc component's domains serialize as Z6.

---

## 10. Open questions

Planning raised these. Each has a recommendation; D1 starts once they are
confirmed. Several refine a decision in `core-domains.md` §10, as noted.

1. **How a kind defines relations** (refines decision 2, "a kind defines
   `relate(a, b)`"). A relation written as SV code in each kind would have
   to be run by every pass, or its results copied into the IR.
   *Recommendation:* the core computes relations from the derivation
   graph (§3.4); a kind only declares which derivation arguments are
   sources of its own kind. A kind-specific relation hook can be added
   later if a kind needs one.
2. **Endpoints of a crossing** (refines decision 12, "per connection
   between interfaces"). Two children's ports joined through a local
   signal are two connections, each with a local signal at one end, and
   local signals have no domain.
   *Recommendation:* check per net. On each net, compare its interface
   endpoints (child ports, the scope's own ports); local signals are
   transparent. Report on the driver's endpoint, once per reader in a
   different domain.
3. **A reset port's polarity per class** (refines decision 13, "`rst` or
   `rst_n` after the net's polarity"). With one module per class, the
   port cannot follow a net that differs between instances.
   *Recommendation:* the polarity is the one the class's sinks agree on,
   else active high; the instantiating module inverts where needed
   (§3.8).
4. **Output domain ports.** Whether an association driven inside a class
   is used outside depends on the instance.
   *Recommendation:* such an association is always an output port; an
   instance that does not use it leaves it on an `_unused` net, like any
   unread output.
5. **Domain declarations in the IR** (refines `core-domains.md` §8,
   "a field with role `DomainRole.DOMAIN`"). ir-core has no field roles
   other than `BundleRole`, and domain objects are not values.
   *Recommendation:* `DataTypeComponent.domains`, a list of
   `DomainDecl` (§6.2), not fields.
6. **Naming a generated port.** Decision 13 lets an association name its
   port, but `set` is made by the parent, per instance, and the port name
   must be a property of the class.
   *Recommendation:* `fw_domain #(K)::port_name(this, assoc, port)` in the
   component's own `build()`; it applies to its class.
7. **How a driver declares its derivation** (decision 10).
   *Recommendation:* `fw_domain #(K)::implements(this, assoc, p)` in the
   driver's `build()`: a `clk_div #(2)` wrapper states that its `out`
   association is `derived(.from(get(this)), .div(2))`. Checked against
   the domain its parent sets `out` to (`FW-E-DOM-DERIV`). It can slip to
   after D7 if needed, since the check is advisory.
8. **Top-level clock and reset ports.** The design has the top drive its
   root domains from its own input ports (`clk.drive(clk_i)`), so a
   realized root domain with no driver is `FW-E-DOM-NODRIVER`.
   *Recommendation:* keep that for this layer. Generating top ports
   implicitly saves two lines per top, but hides the reset polarity and
   the port names at the one place a user expects to see them.
9. **Kind statics in the spec.** The library kinds' static functions are
   real code in the spec, not tool bodies, unlike the rest of the API.
   *Recommendation:* accept this. The spec lint's "trivial bodies only"
   rule exempts kind classes; the API check still compares their
   declarations.
