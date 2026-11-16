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
| D0 Plan | done | This file (2026-11-15). §10 Q1–Q9 confirmed 2026-11-15, with the D1 refinements noted there. |
| D1 Spec API and semantics | done | 2026-11-15. fw-hdl-spec: the API (`fw_domain*.svh`, `fw_clock_kind.svh`, `fw_reset_kind.svh`, enums and typedefs in `fw_hdl_api.svh`, the macro), `semantics/domains.md`, diagnostics, netlist schema, 29 scenarios (`dom_*`, `kind_user`, feature `domains`), `docs/api/domains.rst`, `tools/fw_conformance_schema.py`. All 66 scenarios compile; schema check, spec lint, docs `-W` pass. rt-sv has placeholder bodies (`sv/fw_rt_domain.svh`) and passes the API check; rt-sv and fe-sv skip `domains` scenarios until D2/D4. See "D1 outcomes" below. |
| D2 rt-sv | done | 2026-11-15. fw-hdl-rt-sv: `sv/fw_rt_dom.svh` (the domain runtime), `sv/fw_rt_domain.svh` (the bodies, replacing the placeholders), hooks in `sv/fw_rt.svh` (domain records, extern domain pins, the crossing check per net, end-of-elaboration checks, netlist members); `FEATURES = {"domains"}`. rt-sv conformance 59 passed, 7 skipped (static-only, as before); API check passes. See "D2 outcomes" below. |
| D3 Z6 IR shapes | done | 2026-11-15. zuspec-ir-core: `domain.py` (the §6.2 shapes), the new `DataTypeComponent` lists and `ExternPin` fields, exports, CHANGELOG; `tests/test_domain_ir.py` (a component and an extern with every shape round-trip; anchors). ir-core 225 passed, 3 skipped; fe-sv, struct_flatten and be-sv structural tests unchanged. See "D3 outcomes" below. |
| D4 fe-sv elaboration | done | 2026-11-15. fw-hdl-fe-sv: `domains.py` (domain objects, associations and lookup, drivers, extern domain pins, waivers recorded, the end-of-elaboration checks), the `fw_domain` intrinsics in `rt.py`, domain pins in the pin map and header checks (`resolve.py`), the netlist members (`netlist.py`), the Z6 shapes in `ir_map.py`, `fw_domain_kind_utils` in fe-sv's macros. zuspec-synth: `passes/domains/relation.py` (the relation, used by fe-sv's `relate`), and `struct_flatten` refusing domain pins until D6. Conformance: `FEATURES = {"domains"}`; 24 of 29 domain scenarios pass, equal to rt-sv's expectations; 5 wait (`PENDING` in `test_conformance.py`). fe-sv 129 passed, 5 skipped (was 93 passed, 29 skipped); zuspec-synth struct_flatten, CDC and relation 25 passed; be-sv structural 12 passed. See "D4 outcomes" below. |
| D5 Zuspec domain passes | done | 2026-11-15. zuspec-synth `passes/domains/`: `resolve.py` (`Resolution`: the instance tree of a concrete IR, lookup, `DomainRef` resolution; the relation's `DomainGraph`), `crossing.py` (`check_crossings`, with waivers and the severity option), `realize.py` (`realize`: realized domains, `FW-E-DOM-NODRIVER`, each class's generated domain ports, `FW-E-DOM-PORTNAME`). ir-core: `DomainPortName`, `DomainProvides` (`DataTypeComponent.domain_port_names`, `domain_provides`), `DataTypeDomainKind.pin_default`, `port_names` keyed by `port_name_key`. fe-sv: `domains.passes` runs them at the end of elaboration over `to_ir(parameterize=False)`; `ir_map` fills the kinds' port names, `port_name()` and `provides()`; fe-sv's own NODRIVER check removed. Conformance: all 29 domain scenarios pass, `PENDING` empty. fe-sv 136 passed (was 129 passed, 5 skipped); zuspec-synth domain, relation, struct_flatten, CDC 46 passed; ir-core 225 passed, 3 skipped; be-sv structural 12 passed. See "D5 outcomes" below. |
| D6 Emission | done | 2026-11-15. zuspec-synth: `passes/domains/ports.py` (`DomainPorts`: per-class domain ports and wiring, over concrete or parameterized IR); `realize.py` takes its ports from it; `struct_flatten` adds domain ports, local and inverted nets, driver assigns and child connections in both forms. ir-core: `DataTypeDomainKind.polarity`. fe-sv: domain-handle provenance (`get` returns a traced handle; `set`, `pin`, sources and `provides` record the `DomainRef`), an extern's own associations written to the IR, associations of a child made under a branch on parameters placed in its generate arm, explore runs seeded with the instance's domains. Examples: `examples/wrap_rtl` migrated; `examples/domains` new (`soc`, `soc_bad`). Spec: the `active_low` polarity convention, the per-class realization rule. fe-sv 140 passed; zuspec-synth domain, flatten and CDC tests 53 passed; ir-core 225 passed, 3 skipped; be-sv structural 12 passed; spec lint PASS; `dfm run sim` PASS for both examples. See "D6 outcomes" below. |
| D7 Extensibility, options, docs | done | 2026-11-15. The toy kind end to end: `kind_user` passes on both tools (netlist, `FW-I-DOM-CROSS`), and fe-sv emits nothing for it (`test_user_kind_emits_nothing`). Severity option: zuspec-synth `severity_option` (map or `kind.relation=severity,...`, checked); fe-sv `elaborate(domain_severity=)` and the dfm `Elaborate` parameter `domain_severity` (a map); rt-sv `+fw_dom_sev`, a malformed one `FW-E-RT-OPT`. Docs: fw-hdl-spec `docs/domains.rst` (the user guide), `docs/wrapping.rst` on domain pins, index; rt-sv README (plusargs, the user-kind handle limit). fe-sv 143 passed; rt-sv 6 passed (conformance included); zuspec-synth domain, flatten and CDC tests 54 passed; spec lint PASS; spec docs `-W` pass; `dfm run sim` PASS for both examples. The §1 criterion is met. See "D7 outcomes" below. |
| D8 IR reconciliation with zdc | done | 2026-11-15. zuspec-dataclasses: `domain_ir.py` (the library kinds; a class's clock and reset as a created, self-associated, driven domain), called by the factory. ir-core: `clock_domain`/`reset_domain` not serialized (`serialize: False` metadata, honoured by the serializers). zuspec-synth: `DomainBinding` reads only Z6 (`has_clock`, `has_reset`), used by `component_fields.py`, `synth/__init__.py` and `CDCAnalysisPass`. CDCAnalysisPass kept for zdc (by-name clocks). Tests: zdc `test_factory_domain_ir.py` (6), synth `test_domain_binding_ir.py` (3), ir-core `test_source_domain_objects_not_serialized`, fe-sv `test_zdc_kinds_match`. ir-core 226 passed, 3 skipped; fe-sv 144 passed; zdc, synth and be-sw: no new failures against the pre-existing ones (see "D8 outcomes"). |

### D1 outcomes

Where the spec now differs from §3 and §4 of this plan, the spec
(`semantics/domains.md`, `netlist.schema.json`, `bindings/sv`) wins:

- **Q7 is `provides`**, not `implements`: `implements` is an SV keyword.
- **Netlist shape** (replaces §3.11): a domain is an object of kind
  `domain` (type `fw_domain#(fw_clock_kind)`) with `params` and `drivers`;
  associations are listed on the object they were set on (`assoc`: kind ->
  name -> domain path); the extern has a `domain_pins` map; the component
  has `waivers`, `port_names`, `provides`. Every new key is present only
  when non-empty, so layer-1 expectations are unchanged. A domain's params
  are written like a component's (enums as numbers), handles as paths.
  There is no separate `deriv` object: every kind's `params_t` has
  `deriv` and `from`.
- **Crossings** (refines Q2): one diagnostic per pair of interfaces (a
  port, or its outermost bundle) and kind, on the lesser path, whichever
  nets the pair spans. Reporting on the driver would split a bundle
  crossing into one diagnostic per direction.
- `FW-E-DOM-UNUSED` is checked at the end of elaboration, after the extern
  maps, which read named associations (`pin_out(m, .., get(this, "out"))`).
- `FW-E-DOM-NONE` also covers a null derivation source (on the domain);
  `relate(null, x)` reports on the calling component. `FW-E-DOM-PIN` also
  covers a pin or driver on a marker kind.
- `fw_domain_kind` declares every kind static for a marker kind, so a user
  kind redeclares only what it changes (the toy kind is 4 lines).
- Clock `period_ns` dropped (delays are layer 2). Reset derivations:
  `root(style, clock)`, `synced(from, clock, style)`, `combined(from[],
  style, clock)`, `software(from, clock, style)`.
- **Tool notes.** Verilator takes default arguments from an out-of-block
  body, not the prototype: every tool's bodies repeat the defaults
  (`tools/fw_hdl_bodies.py` does; rt-sv's must). The library kinds write
  out `get_type()` rather than use the macro, because the API check
  compares expanded text.
- Scenario set: `dom_create_bad` replaces `dom_create_late` (adds a name
  clash); new `dom_pin_bad` and `dom_deriv`. `meta.json` gained
  `features`; runners skip scenarios needing a feature they lack.

### D2 outcomes

- **Scenario fix.** `dom_phase` waived `u0.o` and `u1.i` in `top.build()`,
  but children build after their parent, so both handles were still null.
  It now waives two of top's own ports, and expects `FW-E-DOM-PHASE` on
  `top.d_i`. No other expectation changed.
- **Handles in params (rt-sv limit).** Verilator's `%p` prints a handle
  nested in a struct as its class name, not its identity. rt-sv writes the
  handles it can reach by name as paths: `from` in every kind, and
  `fw_reset_kind`'s `clock` (through a typed box downcast). A user kind with
  a domain handle in another field gets its class name in the netlist. fe-sv
  (D4) reads the declarations, so it has no such limit. Closing it in rt-sv
  needs a kind hook that lists a params value's handles; decide in D7.
- `+fw_dom_sev` (the severity option) is not in rt-sv yet; it stays in D7
  with `domain_severity`.
- rt-sv's `dfm run tests` took `api-check` and `conformance` from its
  cache after the SV sources changed; both were run directly.

### D3 outcomes

Refinements of the §6.2 table, which is updated to match:
- **`DomainAssoc.assoc`, not `name`.** ir-core's anchor pass treats any
  named node in a component's lists as a member, so a named association
  `wr` would have claimed the anchor `top.wr` and could clash with a field.
  Domain objects (`DomainDecl.name`) are members, in the component's name
  space, and keep `name`.
- **`DomainRef` is an `Expr`, and has a `target`.** A domain of another
  kind in a derivation's arguments or a params value (a reset's `clock`)
  is then an ordinary `Expr`. `target` (`[]` = the component itself) lets
  a resolution be read through an own interface or a child, as `get(obj)`
  allows; `(kind, assoc)` alone covered only `get(this)`.
- **Paths** are lists whose elements are a field name or an
  `ExprHierarchicalElem` (a name with a subscript), the element type of
  layer 1's bind paths. A statement under a loop or a branch sits in
  `generates`, like a `Bind`.
- Severities are keyed by the relation's lower-case name (`"unrelated"`),
  as the option spells it: the serializer writes dict keys as strings, so
  `DomainRel` keys would not round-trip. `DomainRel` exists for the
  relation pass (D5).

### D4 outcomes

- **What waits.** The exit criterion is every scenario that needs no
  crossing check. Four need the crossing pass (D5): `dom_cross_clock`,
  `dom_cross_reset`, `dom_waive` (`FW-W-DOM-WAIVE` is a waiver matching no
  crossing) and `kind_user` (its expectation has a crossing).
  `dom_portname` needs the realization pass (D6). They are listed in
  `PENDING` in fe-sv's `test_conformance.py`, with the step each needs.
  `dom_cross_elem` expects no crossing, so it passes already.
- **The relation is written once.** `passes/domains/relation.py` in
  zuspec-synth takes a `DomainGraph` (`sources(d)`, `key(d)`); fe-sv's
  `relate()` and `FW-W-DOM-RSTSYNC` call it on fe-sv's objects. D5's passes
  call it on the IR. Waivers are recorded in D4, and matched by D5's
  crossing pass.
- **What ir_map writes.** A domain the component's code reached is
  written as the component can reach it:
  - its own domain object, as `decl`;
  - else a resolution that gives it: the component's default, one of its
    named associations, or the association of an interface or a child.
  So a child that derives from `get(this)` is written over its resolution,
  not over a domain of its parent, and one IR type serves every instance.
  - A kind's derivations are its `deriv_e` members, lower case; every
    non-root derivation's sources are `from`.
  - `DomainDecl.params` holds the params value's fields other than `deriv`
    and `from` (`from` is `sources`): integers as constants, domain handles
    as `DomainRef`, and null handles left out.
  - `args` stays empty: fe-sv sees the params value the derivation call
    returned, not the call's arguments.
- **Parameterized cases wait for D6.** A domain object, association or
  driver under a loop or branch on parameters makes the component a
  specialization (`FW-I-EMIT-SPEC`). A component whose domain statements
  are all outside control flow stays general.
- **Gaps in Z6 for D6.** `port_name()` and `provides()` are statements a
  class makes about itself, and Z6 has no field for them yet. They are in
  the netlist, but not in the IR.
  `DataTypeDomainKind.port_names` is left empty, because a reset's port
  name depends on the polarity the class settles on, which is
  realization. D6 adds both.
- **Emission refuses domain pins.** `struct_flatten` would have left a
  domain pin open, so both of its extern paths now raise
  `NotImplementedError` until D6. Domain objects, associations and drivers
  add nothing to the emitted RTL until then.
- fe-sv's own `fw_hdl_macros.svh` needed `fw_domain_kind_utils`, which
  `dom_pin_bad` and `kind_user` use.

### D5 outcomes

- **The passes read a concrete IR.** `Resolution` walks the IR from its
  top type, one instance per child field, and refuses a type with
  template parameters or generate blocks. fe-sv hands it
  `to_ir(parameterize=False)`, so every design is covered now; resolving
  over the parameterized IR (evaluating loops and conditions per
  instance) comes with D6's parameterized cases.
- **fe-sv runs the passes in elaboration** (`domains.passes`, after the
  end-of-elaboration checks), when the design used any domain kind, even
  after earlier errors: `dom_waive` expects `FW-E-DOM-WAIVE` and a
  crossing together. If the IR cannot be built after an earlier error,
  the passes are skipped; with no earlier error, that is `FW-E-ELAB`.
  The realization is kept on `rt.dom.realization` for emission.
- **Crossings** follow rt-sv's rule exactly: per net of each scope,
  sources against every port endpoint; local signals transparent; one
  diagnostic per pair of interfaces and kind, on the lesser path; a
  waiver matches when it was made by the connecting scope, for that
  kind and that pair of interfaces. `check_crossings` takes the
  severity option already; the dfm parameter and the rt-sv plusarg stay
  in D7.
- **NODRIVER moved** to the realization pass; fe-sv no longer checks it
  itself. `FW-E-DOM-DRIVER`, `-DERIV`, `-UNUSED` and `FW-W-DOM-RSTSYNC`
  stay in fe-sv's end-of-elaboration checks: they are about what the
  code said, not about realization.
- **Port names without SV.** A kind's `port_name(assoc, attr)` is SV
  code, so fe-sv tabulates it: `DataTypeDomainKind.port_names` holds the
  name for every association name of the kind and every attribute value
  its pins, drivers and `pin_default()` have, keyed by
  `port_name_key(assoc, attr)` (`"/active_low=1,style=2" -> "rst_n"`).
  An input port's attributes are the ones its subtree's sinks agree on,
  compared by the port name they give (so a reset's style does not
  matter), else `pin_default`. That is §3.8's polarity rule, without
  the pass knowing about resets.
- **Z6 gaps closed.** `DomainPortName` and `DomainProvides` hold
  `port_name()` and `provides()`; an extern class's `provides` is
  written too (the divider wrapper's case).
- **Output ports.** An association driven inside a class's subtree is an
  output port whether the driver is a `pin_out` or a `drive`; §3.8 names
  only `pin_out`, but a `drive` of an outer domain inside a class needs
  the same port.
- The conformance scenarios are flat, so they produce one generated
  port (`dom_portname`). The ports of hierarchical classes are covered
  by zuspec-synth's `test_domain_passes.py` and fe-sv's
  `test_realization_through_fe_sv`.
- The rest of zuspec-synth's suite has failures unrelated to domains:
  example modules not installed (`rotate`, `blink`, ...), a `pyslang`
  API change, missing `docs/rationale/`, and `zuspec.cli`.

### D6 outcomes

- **Realization is per class, over the IR types** (`DomainPorts`), not over
  an instance tree. Emission is one module per class, and the
  parameterized IR has no instance tree; a static analysis reads both
  forms, every generate arm and iteration included. Within a class each
  domain reference resolves to a symbol: a domain the class creates, an
  association its parent gives (`ext`), a domain a child creates (refused
  by emission), or nothing. D5's `realize` now takes its ports from it, so
  `FW-E-DOM-PORTNAME` and emission agree.
- **The rule is refined** (`semantics/domains.md`, Emission): an
  association is realized in a class when something in its subtree
  realizes a domain *through it*. D5 asked whether the domain it resolved
  to was realized there, so an association that only resolved to the same
  domain as a realized one got a port nothing used. A named association a
  class reads and no parent sets is now a port too; its parent connects it
  to the default it falls back to.
- **Provenance in fe-sv.** Two associations can give the same domain at an
  instance (`xfer`'s `wr` and `rd`, both `clk_a`), and D4's ir_map found a
  ref by looking up the domain, so `set(sf, wr)` came out as the default.
  Port names then followed the instance, and two instances that should
  share a class did not. Now `get` returns its handle traced
  (`Sym(handle, DomainRef)`); `set`, `pin`, `create` sources and
  `provides` sources record the ref when the component that read it uses
  it, and ir_map writes it. The lookup is the fallback.
- **Polarity.** Inversion needs to know which pin attribute is polarity,
  and the kind API has no function for it. The convention is a 1-bit
  `pin_attr_t` member `active_low` (spec text in `fw_domain_kind.svh` and
  `semantics/domains.md`); fe-sv writes it as
  `DataTypeDomainKind.polarity`. A sink of the other polarity reads
  `<net>_inv` (`assign rst_inv = ~rst`), one per net, in the module that
  makes the connection.
- **What emission writes.** Domain ports come first in a module's ports,
  sorted by kind and association. A domain the class creates and realizes
  is a net named after it. A driver is `assign <net> = <signal>`; a child
  output read only by a driver gets a net named after it, not `_unused`.
  A child output domain port drives its association's net, or the class's
  output port. Collisions are `FW-E-DOM-PORTNAME` (generated ports) or
  `FW-E-NAME-FLAT` (nets).
- **A class does not know it is the top.** A top whose subtree drives its
  own default association, unset, gets an output port for it, as any class
  would. fe-sv's instance checks (`FW-E-DOM-NONE`) report the design
  error; emission keeps the class rule.
- **Parameterized cases (§6.1).** An association of a child created under
  a branch on parameters (no loop) goes in that child's `GenerateIf` arm,
  as Z6 allows, and the class stays general: a parameter that picks a
  single- or dual-clock FIFO is one module. The class's ports are those of
  both arms. A domain port or net read only in some arms also drives a
  `<name>_unused` net, so it lints clean at values that take the other
  arm. Still specializations: domain objects, drivers and associations in
  loops, and associations under a branch on anything but a child made in
  the same arm. To cover the untaken arm, ir_map re-elaborates the class
  on its own (`FeRt.explore`); that run now starts with the instance's
  associations and defaults, so the arm sees the domains the instance
  sees.
- **Externs' own associations.** `_extern_type` wrote only `provides`, so
  `cdc_fifo`'s `set(in, wr)` and `set(out, rd)` were lost and fe-sv
  reported crossings that are not there. It now writes all of an extern's
  domain statements.
- **Examples.**
  - `examples/wrap_rtl`: the wrappers have no `clk`/`rst` ports; `chain`
    creates `clk` and `rst`, sets them as defaults and drives them from
    `clk_i`/`rst_i`. The slice's `aresetn` reads the generated `rst_inv`.
    The reference has one reset input and its own inverter. The README is
    updated.
  - `examples/domains`: `soc` takes a stream from `clk_a`, through `slow`
    (`clk_a` divided by 2, from a wrapped divider's `pin_out`), to the
    unrelated `clk_b`. `xfer` picks a single-clock FIFO when
    `relate(wr, rd)` is `SAME`, else the dual-clock wrapper (named
    associations `wr`/`rd`, interfaces in each). The reset is active low;
    the single-clock FIFO's is active high. `soc_bad` fails with
    `FW-E-DOM-CROSS`. RTL, reference, testbench, `flow.yaml`, README.
  - Both emit Verilog that is lint-clean under `verilator -Wall` and
    matches the reference in simulation: pytest (`tests/e2e/`) and
    `dfm run sim`.
- **Open.**
  - `xfer`'s two structures come from `relate` in `build()`, not from a
    parameter, so they are two classes (`xfer`, `xfer__1`, with
    `FW-I-EMIT-SPEC`). The info message names constructor factories, which
    is the general cause but not this one.
  - be-sv's full suite has 14 failing performance tests (zdc behavioral
    components in the simulation backend); they do not reach
    `struct_flatten` or the domain passes.

### D7 outcomes

- **The toy kind needed no core change.** `kind_user` already passed on
  both tools after D5; D7 adds the emission side: the kind is in the IR
  (`DataTypeDomainKind`, not physical, its severities), its domains and
  associations are in the class, and the emitted module has no domain
  port or net.
- **The severity option** is checked in one place, zuspec-synth's
  `severity_option`, which takes the map form (dfm, Python) or the text
  form (`fw_reset_kind.unrelated=warning,fw_clock_kind.related=none`).
  A bad relation or severity is a `ValueError` in fe-sv (the dfm task
  reports it as an error marker). rt-sv parses `+fw_dom_sev` itself, the
  same text form; a malformed item is `FW-E-RT-OPT`, a tool diagnostic,
  reported even when no crossing is checked. A kind name the design does
  not use is ignored, so one option can serve several designs. rt-sv has
  no dfm runner task of its own: the plusarg goes through
  `hdlsim.vlt.SimRun`'s `plusargs`.
- **Tests.** zuspec-synth `test_severity_option_forms`; fe-sv
  `test_domain_severity_option` (map, text, bad), `test_user_kind_emits_nothing`,
  and `test_domain_severity_through_dfm` (a flow elaborates `soc_bad` with
  its crossing made a warning); rt-sv `test_severity_option` (three
  plusargs on `dom_cross_reset`; the conformance runner's `run_one` takes
  `plusargs` and an `expect`).
- **Docs.** `docs/domains.rst` is the user guide: create and set, derivations
  and relations, drivers, wrapper pins and polarity, named associations,
  `pin_out` and `provides`, `relate` to choose structure, crossings,
  waivers and the severity options, what emission writes, and writing a
  kind (the toy `macro_kind`). Its Verilog excerpt is the emitted
  `examples/domains` top. `docs/wrapping.rst` maps clock and reset as domain
  pins and drops their hand connections. The `wrap_rtl` README was
  updated in D6.
- **D2's open question** (a domain handle in a user kind's params, other
  than `from`, written as a class name by rt-sv): left as a documented
  rt-sv limit (README, Notes). A kind hook to list a params value's
  handles can come when a kind needs one; no library kind does.

### D8 design

The two models differ, so D8 maps zdc's onto Z6 rather than making them
one:

- **zdc identifies a clock by name, Z6 by object.** Each zdc class
  declares its own `ClockDomain`; two classes that both name `fast_clk`
  are in one clock, and `CDCAnalysisPass` compares names. In Z6 each class
  would create its own root domain, and two root domains are unrelated.
- **zdc puts polarity on the domain, Z6 on the net.** A zdc `ResetDomain`
  has a polarity; in Z6 the polarity is an attribute of a driver or pin.
- **zdc has a period, Z6 does not.** `fw_clock_kind`'s params have no period.

The mapping (zuspec-dataclasses `domain_ir.py`, called by the factory):

- **Kinds.** zdc uses the library kinds `fw_clock_kind` and
  `fw_reset_kind`, defined the same way fe-sv builds them from the spec
  (an fe-sv test compares the two).
- **A class-level domain** (the one the factory already picks, most derived
  first) is what a Z6 top does: the class creates a root domain named after
  the attribute (`DomainDecl`), makes it its own default (`DomainAssoc`,
  `target=[]`), and drives it from the port synthesis gives it
  (`DomainDriver`, `signal=[port]`). The port is `ClockDomain.name` or
  `clk` for a clock; `rst_n` or `rst` for a reset, after its polarity.
  - A clock's params are `div`, `mul` and `phase_deg`, plus `period` in
    femtoseconds when the period is known. `period` is the one param
    outside `fw_clock_kind`'s params_t; passes ignore it.
  - A `DerivedClockDomain` is `derived` with its `div`, `mul` and phase.
    Its source is not recorded: zdc's `super()` means "the parent's
    domain", which has no `DomainRef` form, and a lambda source names a
    class attribute the factory does not otherwise read.
  - A reset's params are `style` (0 async, 1 sync). The driver's
    attributes are `active_low` and `style` 2 (any), as fe-sv writes
    `rst.drive(rst_ni, active_low())`.
  - A reset with style `none` (a class with no reset pin) is a reset
    domain with no driver. Its `style` is 1, so synthesis treats it as it
    did before, as a sync reset.
- **Not mapped:** zdc `__bind__` domain overrides
  (`{self.child.clock_domain: self.fast_clk}`). The factory has never read
  them; only the Python runtime applies them.

The readers:

- **ir-core.** `DataTypeComponent.clock_domain` and `reset_domain` stay as
  the front end's source objects, for be-sw's `c_emit.py`, but are no longer
  serialized (field metadata `serialize: False`, honoured by `Serializer`
  and `JsonConverter`). Z6 is what a serialized component has.
- **zuspec-synth.** `DomainBinding.from_component_ir` reads only Z6: the
  class's default clock and reset declarations and their drivers. It gains
  `has_clock` and `has_reset`, which `component_fields.py` and
  `synth/__init__.py` use in place of `clock_domain is not None`.
  `CDCAnalysisPass` reads domains through `DomainBinding`, so it no longer
  needs zdc's classes for them.
- **CDCAnalysisPass is kept**, not replaced by the Z6 crossing pass. With
  zdc's by-name identity, the crossing pass would report two classes that
  both name `fast_clk` as unrelated. Using it for zdc needs zdc to create
  its clocks once at the top and associate them down (a zdc front-end
  change), so it is left for later.


### D8 outcomes

- Implemented as designed above. be-sw is untouched: `c_emit.py` still
  reads `reset_domain`, which the factory still sets in memory.
- **Exit criterion.** A zdc component's domains serialize as Z6, and
  `DomainBinding` gives the same binding after a round trip
  (`test_same_after_serialization`). The zdc, synth and be-sw suites have
  failures that predate D8 (environment: missing `zuspec.cli`, `uvloop`
  and benchmark modules; solver tests). D8 was compared against them:
  - zuspec-synth: 1276 passed (1273 + 3 new), the same 53 failed and 97 errors.
  - be-sw: 526 passed, the same 6 failed and 43 errors.
  - zuspec-dataclasses: 2017 passed (+6 new), the same failures except in
    `tests/solver/test_zdc_builtins.py`. That file fails between 16 and 18
    tests per run with or without D8's changes (checked with them
    stashed), so it is flaky, not a regression.
- **Left for later:** zdc `__bind__` domain overrides in the IR; a
  `DerivedClockDomain`'s source; the Z6 crossing pass for zdc designs
  (needs zdc clocks created once and associated down);
  `BlockSignature`/`Function.metadata` clock and reset (layer 2).

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
- An **association is realized in the class** when something in the
  class's subtree realizes a domain through it (an extern pin, a driver, a
  child's port or pin resolved through it), over every generated arm and
  iteration (D6 refinement; see "D6 outcomes").
- Each realized association whose driver is outside the subtree is an
  **input port**, named by `K::port_name(assoc, attr)`: `clk`, `wr_clk`,
  `rst`, `rst_n`, `wr_rst_n`.
- Each association driven inside the subtree, by a `pin_out` or a `drive`
  there, is an **output port** of the class (§10 Q4).
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
  `fw_elab` plusarg `+fw_dom_sev=fw_reset_kind.unrelated=warning`
  (comma-separated for several). `none` silences. (D7: a malformed
  option is a `ValueError` in fe-sv, `FW-E-RT-OPT` in rt-sv.)
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
  traced frames like `create` and `connect` do. An association of a child
  created under a branch on parameters goes in the child's generate arm
  (D6). Any other domain statement under a loop or a branch on parameters
  is emitted as a specialization (`FW-I-EMIT-SPEC`).

### 6.2 Z6: IR shapes (ir-core)

| Shape | Fields |
|---|---|
| `DataTypeDomainKind` | `name`, `physical: bool`, `derivations: Dict[str, DomainDerivDecl(sources: List[str])]` (which arguments are same-kind sources), `severities: Dict[str, DomainSeverity]` (keyed `"same"`, `"related"`, `"unrelated"`), `port_names: Dict[str, str]` (`K::port_name`, tabulated by fe-sv, keyed by `port_name_key(assoc, attr)`; D5), `pin_default` (D5), `polarity` (the attribute that is a net's polarity, `"active_low"`; D6) |
| `DataTypeDomain` | `kind`: the kind's name in `type_m` |
| `DomainDecl` | `name`, `kind`, `deriv: str`, `sources: List[DomainRef]`, `args: Dict[str, Expr]`, `params: Dict[str, Expr]` |
| `DomainRef` | an `Expr`: either a `DomainDecl` of this component by name (`decl`), or a resolution `(kind, assoc, target)`: the domain `target` (`[]` = this component, or an own interface or child) resolves to |
| `DomainAssoc` | `target: List[str]` (field path, `[]` = self, may hold index expressions), `kind`, `assoc` (the association's name, `""` = default), `domain: DomainRef` |
| `DomainDriver` | `domain: DomainRef`, `signal: List[str]`, `attr: Dict[str, Expr]` |
| `DomainWaiver` | `kind`, `a`, `b`: paths; `reason` |
| `DomainPortName` | `kind`, `assoc`, `port`: `port_name(this, assoc, port)` (D5) |
| `DomainProvides` | `kind`, `assoc`, `deriv`, `sources`, `params`: `provides(this, assoc, p)` (D5) |
| `DataTypeComponent` | gains `domains: List[DomainDecl]`, `domain_assocs`, `domain_drivers`, `domain_waivers`; `domain_port_names`, `domain_provides` (D5) |
| `ExternPin` | gains `domain: Optional[DomainRef]`, `domain_kind`, `domain_attr`, `output: bool` |

- All of it round-trips through the serializer; kinds are stored once in
  `type_m`, like the types package's types.
- Clock and reset are *instances* of `DataTypeDomainKind`, so a new kind
  needs no IR change.
- Nothing existing changes in D3: `clock_domain`, `reset_domain`,
  `BlockSignature` and `Function.metadata` are left alone until D8.
  (D8: zdc writes Z6 too; `clock_domain`/`reset_domain` are no longer
  serialized; `BlockSignature` and `Function.metadata` are still for
  layer 2.)

### 6.3 Zuspec passes (zuspec-synth `passes/domains/`)

- **Relation.** `relate(a, b)` over a domain graph interface that both the
  IR and fe-sv's objects implement (§6.1).
- **Resolution.** For each instance path: each kind's default and named
  associations, and each interface's domain, by §3.3.
- **Crossing.** Over the connections of every component (`bind_map`
  after Z3's resolution of nets), by §3.9, with the severity option.
  It returns diagnostics; fe-sv reports them. It replaces
  `CDCAnalysisPass` for fw-hdl designs; zdc designs keep it (D8 design).
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
  ports, nets and assigns by then. (D6: it needed nothing.)
- The ports and wiring come from `DomainPorts` (`passes/domains/ports.py`),
  computed per class on the structural form before any rewrite.

### 6.5 dfm

- `Elaborate` gains `domain_severity` (a map, §3.9).
- The rt-sv runner passes `+fw_dom_sev`. (D7: rt-sv has no runner task;
  `hdlsim.vlt.SimRun`'s `plusargs` carries it, and the conformance
  runner's `run_one` takes `plusargs`.)

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
| zuspec-synth `CDCAnalysisPass` | replaced by the crossing pass for fw-hdl; for zdc it stays, reading Z6 through `DomainBinding` | D5, D8 |
| ir-core `DataTypeComponent.clock_domain`/`reset_domain` | the front end's source objects, not serialized; Z6 is the IR (read by `DomainBinding`; be-sw's `c_emit.py` still reads `reset_domain`) | D8 |
| `BlockSignature.clock`/`reset`/`reset_active_low`, `Function.metadata['clock'/'reset']` | reconciled with Z6 (layer 2 and engines) | layer 2 |
| zuspec-be-py `model/domain.py` | unchanged; zdc maps its classes to Z6 (`zuspec.dataclasses.domain_ir`) | D8 |

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

Planning raised these. *Confirmed 2026-11-15 as recommended*, with Q2 and
Q7 refined in D1 (see "D1 outcomes" under §0). Several refine a decision in
`core-domains.md` §10, as noted.

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
