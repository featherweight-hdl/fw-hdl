# Core protocol-kit prep (issues and recommendations)

Status: **draft, review applied (2026-11-15); readiness review
(2026-11-16, §14).** In §13:
- **Settled 2026-11-15:** decisions 1, 2, 10, 11, 12, 13, 15, 16, Q-A and Q-B. Of
  these, 10, 11, 13 and 16 were changed in review.
- **Decided 2026-11-16:** decisions 3 (names), 4–9, 14, 17 and Q-C,
  as recommended in §14.3, under the principle in §14.4 (keep what the
  user writes to a minimum).
- **Direction set 2026-11-16:** decisions 19–21: abstraction levels
  (§3.3), configuration publisher and consumer (§3.4), self-timed
  connections (§3.5).
- **Decided 2026-11-16:** decision 18, the macros' class argument:
  `*_utils(C)` without parameters, `*_param_utils(C)` with a `this_t`
  typedef, after the K1 check found the bare-name form fails (§3.2).
- **Part A done 2026-11-17** (§14.1): the protocol class, queries,
  sockets, configuration and the Kit-stage generators, with
  `fw_hdl_std_pkg` (rv and the neutral APIs) built through
  `fw.hdl.GenKit`. Exit test: fw-hdl-fe-sv
  `tests/e2e/test_part_a_exit.py`, with `test_std_flow.py` and the
  `protocols` conformance scenarios in rt-sv and fe-sv.
- **Blocking finding (resolved):** layer 2 (processes) had no design,
  and the transactors, monitors and the §9 acceptance (Part B) need it
  (§14.1). Layer 2 is now done ([core-layer2.md](core-layer2.md)).
- **Part B, transactors and timing, done 2026-11-18** (K9): endpoint
  and configuration renames (`fw_{port,export,socket}_cfg_{src,sink}`,
  transactor role derived from the pin mixin); std `fw_rv_initiator`,
  `fw_rv_target` and `fw_rv_monitor`, run back to back with no RTL
  (rt-sv `test_rv_b2b`), the monitor core proved with SymbiYosys (fe-sv
  `test_rv_formal`); std `fw_timed_channel` and the test UART's kit
  channels (§3.5; scenario `proto_timed`); two class UART models with
  baud mismatch (rt-sv `test_two_uart`, half of the Part B exit); the
  transactor generator for ready/valid bundles with a generated b2b and
  static lookup `ScanResult.xtor_for` (fe-sv `test_gen_xtor*`).
- **Part B exit met 2026-11-18** (K10): monitors register with their
  protocol and take listeners (`add_listener`, std
  `fw_rv_mon_listener`); fe-sv generates the testbench
  (`fw.hdl.gen.gen_tb`: a class tb with one opposite-role transactor
  per protocol port, the DUT and the pin bridges) and the bind module
  (`gen_bind`: input-only bridges to monitors in the same class tree).
  The `wrap_rtl` acceptance (decision 15, fe-sv
  `tests/e2e/test_wrap_rtl_acceptance.py`): random traffic and
  back-pressure from class code, scored on the bound monitors'
  listeners, hand-shakes on the same cycles as the hand-written
  all-RTL reference (`examples/wrap_rtl/tb/chain_accept_tb.sv`), so
  the transactors add no latency.
- **Old kit path retired 2026-11-18** (K11; decision 4 done): `kits.py`,
  its tests, and the kit YAMLs `fw_rv_kit.yaml`/`fw_put_kit.yaml` are
  gone; `extern.py` and `wrap.py` use fixed rv pin templates. The skill
  `skills/fw-proto-kit` describes only the new path, and its hand-written
  rv example is replaced by pointers to the spec `std/` rv and fe-sv
  `examples/wrap_rtl`. The protocol-package guide is now fw-hdl-spec
  `docs/protocol-packages.rst`. sv-weave and `python/fw/hdl/weave/` stay
  (settle/sp_comb); zuspec-synth's own `zuspec/synth/kits/` is not ours
  to retire.
This file follows the form of [core-domains.md](core-domains.md): the
issues, what exists, and a recommendation for each. The plan and its
status are tracked in the work packet, outside the repo
(`.work-packet/state/protocol-kit-plan.md`).

Inputs:
- `roadmap.md` "Prep for protocol-kit support", its "Verification IP"
  notes, and "Protocol kits".
- The new core:
  - `core-layer1.md`, especially §1 "Out of scope", which puts
    transaction-level ports, exports and sockets in layer 3 under new names;
  - the domain layer ([core-domains.md](core-domains.md),
    [core-domains-plan.md](core-domains-plan.md));
  - `packages/fw-hdl-spec` (`bindings/sv`, `semantics/bundles.md`).
- The old core (`src/`, reference only):
  - `fw_port`, `fw_export`, `fw_socket`/`fw_mirror`, and the `FW_*_IMP`
    macros;
  - the rv kit `src/std/rv/` and its descriptor `fw_rv_kit.yaml`;
  - the sync pin bridge `src/sync/fw_rv_pin.svh`;
  - the debug listener `src/dbg/`.
- `python/fw/hdl/weave/`, `python/fw/hdl/kits.py` (retired, K11), and `packages/sv-weave`.
- `skills/fw-proto-kit` and its rv reference kit.
- **fw-proto-axi-new** (`/packets/featherweight-ip/fw-proto-axi-new`).
  It is the new-style AXI4 kit, and it is the main prior art for this
  layer:
  - `docs/design-new-style.md`, `docs/derived-classes.md`,
    `docs/writing-a-protocol-package.md`, `docs/rules.md`,
    `docs/p6-abstractors.md`, `docs/design-sync-rtl.md`;
  - the protocol-agnostic tree `fw_proto/`, which its decision D2 says
    moves to fw-hdl once a second protocol reuses it.
- `project-architecture.md`:
  - §3.1, the standard library and `fw-proto-<p>`;
  - decision D4, rv is built in;
  - the sv-weave plugins move to `fw-hdl-rt-sv`.
- `featherweight-ip-strategy.md`: one protocol spec per protocol, from
  which the transactor, API, rules, checker and VIP are all derived.

---

## User benefit

What a user of fw-hdl gets once this layer exists. Today most of it exists
only for AXI4 in fw-proto-axi-new, built on the old core.

1. **A protocol is written once, briefly.**
   - The kit author writes the parameters, the channel payloads, the
     bundle and the transaction API.
   - Everything else is generated from it: listeners, proxies, fan-outs,
     channel APIs, transaction classes, transactors, monitors and pin-map
     presets.
   - Adding a field to a payload is a one-line change, and it reaches the
     pins and the monitor.
2. **A testbench for existing RTL is generated from its wrapper.**
   - Wrap an IP with `extern_map` and say which pins form which protocol
     port.
   - fw-hdl emits a testbench that has a transactor on every protocol
     port. Each transactor is reachable from class code by path.
3. **Monitors drop into an existing design without editing it.** A
   generated `bind` module puts a protocol monitor on each mapped port of
   the unmodified RTL. Checkers and scoreboards attach to it as listeners.
4. **Transactors do not add latency.** A call made at the method level
   and the same transfer driven through a transactor take the same cycles.
   A test moves between a class-level model and RTL without retuning.
5. **One observation contract.** The listener (pre/post per method) is the
   only way to observe a protocol, whether through a class-level proxy or
   a pin monitor. Rules, coverage, recording and scoreboards are written
   once and work on both.
6. **Fast models at the abstract level, with the same tests.** A UART
   model moves bytes, not bits, and a byte still takes a frame time,
   because the timed channel between two models times it from their
   configuration. The
   same byte-level checkers run on the RTL through a transactor, and a
   baud or parity mismatch between two models shows up as framing errors
   (§3.3–§3.5).
7. **Later, Python reaches the same API.** This comes after prep (§10).
   cocotb and pyhdl-if tests will call the same method API that SV tests
   call, with no hand-written Python binding.

---

## 0. What the roadmap asks for, and where it sits

The roadmap lists these items for the prep step:

| # | Roadmap item | Section |
|---|---|---|
| R1 | Associate a protocol with a signal-bundle port and a method API | §3 |
| R2 | Design of a protocol API: request/response (fwd/rev, egress/ingress) terminology | §2, §4 |
| R3 | Socket design for connection | §5 |
| R4 | Listener, transaction recorder, transaction classes (fwd/rev each), method↔transaction bridges | §4 |
| R5 | sv-weave derives the method-API collateral; sv-weave becomes part of the build. *Revised: IR-driven generators derive it; sv-weave is not on this path* | §7 |
| R6 | Transactors bridge method and signal without latency; complex protocols point at higher-level constructs | §6 |
| R7 | Generated Python collateral for cocotb and pyhdl-if. *Deferred past prep* | §10 |
| R8 | First use: wrap an IP, generate a testbench with connected transactors, and a bind module with monitors; self-test transactors with fw-hdl-dv | §9 |
| R9 | Set up the std package and the rv std protocol | §8 |
| R10 | Verification IP: property checkers on the API, UVM agents, coverage, randomization | §11 |

**Where it sits in the layering.** `core-layer1.md` describes the rebuilt
core as layers. This step depends on two of them:
- **Domains.** Done (D1–D8, 2026-11-15). Transactors and
  monitors take their clock and reset from domains, not from bundle
  members. fw-proto-axi-new already does this.
- **Layer 2, processes: `comb()`, `step()`, `run()`.** This is the
  roadmap's "Basic RTL (glue logic)". A transactor is a component that
  mixes a procedural `run()` with pin-level logic. It cannot be written in
  the new core until layer 2 exists.

This step *is* most of layer 3 (transaction-level ports, exports and
sockets). It also adds the protocol association and the derived
collateral. The roadmap's later "Protocol kits" step is then per-protocol
work in `fw-proto-<p>` repos, built on what this step puts in core and
std.

**The main finding of the review.** Almost all of R1–R7 has been
prototyped and tested for AXI4 in fw-proto-axi-new: the attributes, the
weavers, the derived classes, the generated transactors, the abstractors,
the rules and the reference-IP tests. That code is built on the *old*
core. So this step is mainly a port into the new layered core and its
spec/rt-sv/fe-sv split, not a design from scratch. The questions are:
- which parts become spec;
- which parts become std;
- which parts become tool;
- what the new core changes about them.

---

## 1. What exists today

| Area | New core (`fw-hdl-spec`, rt-sv, fe-sv) | Old core (`src/`, reference) | fw-proto-axi-new (`fw_proto/`) |
|---|---|---|---|
| Bundles and roles | `fw_bundle_base`; role mixins `fw_bundle #(B)` (initiator), `fw_mirror #(B)` (target), `fw_monitor #(B)` (tap); nested bundles; built-in `fw_rv_if #(T)` | struct ports `fw_sp_base`, `fw_rv_sp_in/out` | `fw_sp_base` with a field table; generated `<p>_<role>_sp` |
| Protocol ↔ bundle association | **none** | `fw_rv_kit.yaml`, `fw_put_kit.yaml` (`zuspec.kit` v1), loaded by `kits.py` | attributes: `fw_proto_bundle`, `fw_roles`, `fw_fwd`/`fw_rev`, `fw_opt`, `fw_defs_pkg` |
| Method-API connection | **none** (layer 3) | `fw_port`, `fw_export`, `fw_socket #(I,E)` / `fw_mirror #(I,E)`; `FW_SOCKET_IMP` macros | uses the old core's sockets; generated `<api>_imp` replaces the macros |
| Role APIs | none | `fw_rv_initiator_if.send`, `fw_rv_target_if.put`, `fw_rv_monitor_if.observe`; `fw_put_if`, `fw_get_if`, `fw_reqrsp_if` | hand-written transaction API (`(* fw_api *)`), split request/response; derived channel APIs `<p>_req_if`/`<p>_rsp_if` |
| Listeners and observation | none | `fw_rv_monitor_if` (one-to-one); `fw_dbg_listener_if` (debug events) | `<api>_listener` (`<m>_pre`/`<m>_post`), `_listener_base`, `_listener_fanout`, `_proxy` |
| Transaction classes, recorder | none | none (`FW_L_TXN` debug level only) | none: payloads are packed structs per channel, with derived `sprint`/`compare`/`mask` |
| Transactors | none | `src/std/rv/`: an interface FIFO (depth 4) plus a registered core. `send()` returns on enqueue, and the beat reaches the pins about 2 cycles later | generated from the bundle (`xtor: true`): one fw-hdl rv core per channel, with the flat payload spliced onto the pins |
| Zero-latency pin bridge | none | `src/sync/fw_rv_pin.svh` + `fw_rv_pin_in/out.sv`: signal-to-signal, and zero-latency with `COMB=1` | `design-sync-rtl.md`: struct ports with sync or comb semantics per field (draft) |
| Testbench from a wrapped IP | none | none | P6 abstractors: `<sp>.connect(<socket>)` inserts `<p>_<role>_abs`; the emitter writes the netlist and `<top>_sim.sv` |
| Bind module with monitors | none | none | none |
| Rules (property checkers) | none | none | `fw_rule`, `fw_count`/`fw_flag`/`fw_value`/`fw_any`; rules are listeners; `fw_rv_hold` for signal-level rules |
| sv-weave in the build | not used | `settle`, `sp_comb` weavers; used only by `examples/rr_merge` and tests | `woven` / `woven-xtor` dfm tasks; known gaps listed in `upstream-sv-weave.md` |
| Python (cocotb, pyhdl-if) | none | none | API conventions are pyhdl-if-friendly; generation is listed under "later" |
| Kit guidance | — | `skills/fw-proto-kit` (old style, its own duplicate rv kit) | `writing-a-protocol-package.md` (new style) |
| fw-hdl-dv | empty placeholder | — | — |

---

## 2. Terminology

**Issue.** Each source uses different words for the same thing:
- the roadmap: "request and response (or fwd/rev, egress/ingress)";
- the old core: initiator/target for rv roles, and socket/mirror with the
  API pair `<I,E>`;
- fw-proto-axi-new:
  - `fw_fwd`/`fw_rev` on channels, relative to the first role;
  - `mgr,sub` roles;
  - derived `<p>_req_if`/`<p>_rsp_if`.

The new spec's bundle roles are initiator, target (`fw_mirror`) and
monitor.

There is also a **name clash**. In the spec, `fw_mirror #(B)` is the
target role of a bundle. In the old core, `fw_mirror #(I,E)` is the peer of
a socket. Both cannot keep the name in the new core.

**Recommendation.** Use one word set, with one meaning per word:

| Concept | Word | Notes |
|---|---|---|
| The two active roles | **initiator**, **target** | Generic, as in the spec's bundle roles. A protocol may give them aliases for its own names (`mgr`/`sub`, `master`/`slave` in pin presets), but derived names use the alias consistently. |
| Direction of a channel, relative to the initiator | **fwd**, **rev** | Structural. In a bundle it is *already* expressed by the member's role: an `fw_bundle` member is fwd, an `fw_mirror` member is rev (§3). No attribute is needed. |
| The API each direction carries | **req** (fwd), **rsp** (rev) | `<p>_req_if` is called by the initiator, and `<p>_rsp_if` is called back by the target. |
| A passive observer | **monitor** | Not a role with its own API. It is a *producer of listener calls* (§4). |
| Method-level connection objects | **socket** (initiator side) and **target socket** | Avoids `mirror`, which keeps its bundle meaning. See §5. |

"Egress/ingress" is dropped. It is relative to a component, not to a
protocol, so the same channel is egress on one side and ingress on the
other.

---

## 3. Associating a protocol with a bundle port and a method API (R1)

**Today.**
- The new core has bundles, but nothing says that a bundle *is* a
  protocol.
- The old core keeps the association outside the source, in a YAML kit
  descriptor (`zuspec.kit` v1). `kits.py` checks it against the module
  ports.
- fw-proto-axi-new keeps it in the source, as attributes on a bundle
  class. Its channel members are `fw_rv_ch #(payload)` with
  `fw_fwd`/`fw_rev`.

**What the new core changes.** `semantics/bundles.md` already describes
AXI as "five channel bundles, with `r` and `b` mirrored". A protocol
bundle in the new core is therefore an ordinary bundle of channel bundles:

```systemverilog
class axi4_if #(axi4_param_t P = AXI4_PARAM_DEFAULT) extends fw_bundle_base;
    typedef axi4_types #(P) t;
    fw_bundle #(fw_rv_if #(t::aw_t)) aw;   // fwd
    fw_bundle #(fw_rv_if #(t::w_t))  w;    // fwd
    fw_mirror #(fw_rv_if #(t::b_t))  b;    // rev
    fw_bundle #(fw_rv_if #(t::ar_t)) ar;   // fwd
    fw_mirror #(fw_rv_if #(t::r_t))  r;    // rev
    ...build()...
endclass
```

These parts of fw-proto-axi-new's attributes become redundant in the new
core:
- `fw_fwd`/`fw_rev` follow from the member's role;
- the channel family follows from the member's bundle type (`fw_rv_if`);
- the payload follows from its type parameter.

What remains to join together is small:
- the protocol's name, which is the prefix for derived names. It is
  derived from the class name, not written (§3.2);
- its APIs: the hand-written transaction APIs, and the channel APIs
  derived from the bundle;
- its bundle types;
- its transactors and monitors, per role;
- optional role aliases;
- the class-free definitions package, for RTL.

### 3.1 The protocol class: a hub that the parts register with

*Direction set in review, 2026-11-15.* This replaces the first draft's
`fw_protocol #(B, REQ, RSP)`, which named every part in one type.

The joining element is a **protocol class**. The other parts associate
themselves with it, and each kind of part does so in the way SV allows:

| Part | How it joins the protocol | Why that way |
|---|---|---|
| **API** (an interface class) | The protocol registers it, through a type handle `fw_api_type_of #(API)::get()` | An interface class can hold only pure virtual methods, typedefs and parameters. It cannot register itself or be passed as a value, so a class parameterized by it stands for it. This is the `fw_domain_kind_type_of #(K)` pattern. |
| **Bundle** (physical) | The bundle names its protocol: `` `fw_bundle_protocol(PROTO) `` in the bundle class | A bundle is the physical form of a protocol, and there may be more than one form (pin-level variants). The protocol need not know about them. |
| **Transactor and monitor** | Each registers itself with its protocol: `` `fw_xtor_utils `` / `` `fw_xtor_param_utils `` (§3.2). *Amended 2026-11-17 (decision 3):* the role is not an argument; it is derived (below) | Transactors are written or generated *after* the protocol. Some are generated (§7) and some are hand-written (non-rv families), and there may be several per role. |
| **Generated APIs** (channel APIs) | Registered by a small generated class, in the same way as a transactor | The hand-written protocol class cannot name code generated after it. |

```systemverilog
// The hub, written by hand, first.
class axi4_proto #(axi4_param_t P = AXI4_PARAM_DEFAULT) extends fw_protocol;
    typedef axi4_proto #(P) this_t;
    `fw_protocol_param_utils(axi4_proto)
    static function void declare(fw_protocol_decl d);
        d.api(fw_api_type_of #(axi4_burst_req_if #(P))::get(), FW_PROTO_REQ);
        d.api(fw_api_type_of #(axi4_burst_rsp_if #(P))::get(), FW_PROTO_RSP);
    endfunction
endclass

// The physical form names its protocol.
class axi4_if #(axi4_param_t P = AXI4_PARAM_DEFAULT) extends fw_bundle_base;
    `fw_bundle_protocol(axi4_proto #(P))
    ...
endclass

// A transactor, generated or hand-written, registers with its protocol.
// Its role is derived, never stated (decision 3, amended 2026-11-17).
class axi4_initiator_xtor #(axi4_param_t P = AXI4_PARAM_DEFAULT) extends fw_component;
    typedef axi4_initiator_xtor #(P) this_t;
    `fw_xtor_param_utils(axi4_initiator_xtor, axi4_proto #(P))
    ...
endclass
```

**A role is derived, never declared or registered** *(amended
2026-11-17, decision 3)*. A transactor's role is what its endpoints
already say:
- on the pin side, the mixin of its bundle member (`fw_bundle`,
  `fw_mirror` or `fw_monitor` of the protocol's bundle);
- on the method side, which way the protocol's `req` and `rsp` travel
  through its port, export or socket (§5).

The two must agree; a transactor whose sides disagree is an elaboration
error. A monitor has no outbound API and is a monitor by its
`fw_monitor` member.

**Finding a transactor is static** *(amended 2026-11-17; was the
run-time `xtor_for` and `xtors(role)`)*. The question is always asked
about a bundle in the design, and answered from IR (fe-sv, the
generators of §7 and §9), where the transactors' members are visible:
1. I have a bundle here: what protocol is it? Its bundle type names it
   (`` `fw_bundle_protocol ``).
2. What transactors exist for that protocol? Those registered with it
   (`` `fw_xtor_utils ``), found in the kit's source and the generated
   code.
3. Which one has the counterpart of the bundle I have? The one whose pin
   member is the opposite mixin over the same bundle type: `fw_mirror #(B)`
   for an `fw_bundle #(B)` port, `fw_bundle #(B)` for an `fw_mirror #(B)`
   port, `fw_monitor #(B)` for a monitor tap. Matching on the bundle type,
   not only the protocol, also tells bundle variants apart.

There is no run-time transactor lookup. The generated testbench and bind
module name each transactor they place (§9), so rt-sv never has to find
one.

**All registrations point at the hub.** The protocol class depends on
nothing but its hand-written APIs. That gives three properties:
- a kit's source builds in order: core first, then the generated code;
- there are no cycles between hand-written and generated types;
- a third party can add a transactor or a bundle variant for an existing
  protocol without editing it.

**Finding the parts from anywhere.** The queries follow the
capability-layer pattern: they are static functions that take the core
object, never methods added to the bundle or component classes.

| Starting from | Query | Gives |
|---|---|---|
| a bundle instance in any role: `fw_bundle`, `fw_mirror` or `fw_monitor` of B | `fw_protocol::of(b)`, `fw_protocol::role_of(b)` | the protocol's handle (`fw_protocol_type`), and the role from the mixin. The mixins extend B, so this works on a wrapped IP's mapped ports too. |
| a protocol handle | `p.api(FW_PROTO_REQ)`, `p.apis()`, `p.bundles()` | the parts that have registered |
| a bundle, to get its transactor | static only, in IR (fe-sv and the generators; *amended 2026-11-17*, no run-time query) | the protocol's transactor whose pin member is the opposite mixin over the same bundle type (a target port gets an initiator transactor; a monitor tap gets the monitor), as above |
| an API handle | `a.protocols()` | every protocol that uses it, at the family level (§3.2). The std neutral APIs (`put`, `mem`) belong to many protocols. |
| a protocol or API handle | `p.family()`, `a.family()`; `p.params()` | the unparameterized identity (§3.2); the specialization's parameters, for reporting |
| a transactor | `fw_protocol::of(x)`, or `PROTO::get_type()` statically | the hub, and from it everything else. A socket is typed by its APIs (§5), so from a socket it is `a.protocols()` on its APIs, and its role in each is derived from which way `req` and `rsp` travel (§5) |

The testbench and bind generators (§9) are clients of these queries: from
each protocol port of the DUT, they find the protocol and the transactor or
monitor to place.

### 3.2 Identity at two levels, with no user-written strings

*Decided 2026-11-16.* A user-written name string is flaky: it can
disagree with the class, collide, or go stale after a rename. So no
registration macro takes a name.

A protocol (and an API) has an identity at two levels:

| Level | Answers | Static (fe-sv, IR) | Run time (rt-sv) |
|---|---|---|---|
| **Family**: the class, without parameters | "is this an AXI4 port?": the testbench and bind generators, rules and coverage written for any width, naming, the netlist | the generic class | `p.family()`: one singleton per class, holding its name |
| **Specialization**: the class with its parameters | "can this socket connect to that bundle?", "which transactor fits this port?": connection checks, transactor choice | the specialized type | the `fw_protocol_type` handle (`p` itself); `p.params()` for reporting |

How the macros get both levels without a string (*decided 2026-11-16*,
decision 18):
- **Two forms of each macro**, as in UVM:
  - a class without parameters uses `` `fw_protocol_utils(C) ``;
  - a parameterized class declares `typedef C #(...) this_t;` and uses
    `` `fw_protocol_param_utils(C) ``.
- **In both, the argument is the bare class name**, and the macro only
  stringifies it, for the family's name. The type handle comes from `C`
  in the first form and from `this_t` in the second. The macro never
  uses the bare name as a type.
- **Why `this_t`:** checked in K1 (plan §5.1), in pyslang and Verilator,
  a bare class name used as a type inside a parameterized class is the
  *default* specialization, not the current one: `type_of #(C)` gives one
  handle for `C#(8)` and `C#(16)`. So the specialization must be written
  once, and `this_t` is where. The two-macro form is checked in both
  tools (`probes/k1-bare-name/param_utils.sv`).
- **The user's `this_t` is checked.** A missing typedef is a compile
  error. A `this_t` that is not the class's own specialization (for
  example `C #()`, the default) compiles in SV, so fe-sv checks it: its
  parameters must be the class's parameters, in order.
- **The same pair for every registration macro:** `` `fw_xtor_utils `` /
  `` `fw_xtor_param_utils ``, and `` `fw_abstractor_utils `` /
  `` `fw_abstractor_param_utils ``.
- **Generated code reads `this_t` only inside the class.** Verilator
  mis-resolves `C#(16)::this_t::<typedef>` used from module scope
  (`probes/k1-bare-name/verilator-bugs/`).
- **The prefix for derived names** is the family name with a trailing
  `_proto` removed (`axi4_proto` → `axi4`, `fw_rv_proto` → `fw_rv`).
  A protocol whose class name does not fit overrides it in `declare()`;
  this is the only name a user ever writes, and only when the convention
  fails.

The minimum protocol is the class and its macro (§14.4); a parameterized
one adds its `this_t`:

```systemverilog
class fw_rv_proto #(type T = bit) extends fw_protocol;
    typedef fw_rv_proto #(T) this_t;
    `fw_protocol_param_utils(fw_rv_proto)
endclass
```

**Attributes** stay only for facts at member granularity that SV types
cannot carry:
- `fw_opt` on payload fields;
- `fw_default` on API methods.

**Issue: registration of parameterized classes.** At run time, SV runs a
parameterized class's static initializers only for specializations that
exist in the image, so a run-time list of `axi4_initiator_xtor #(P)`
specializations would be incomplete. The static view does not have this
gap: fe-sv sees every registration macro in the source. *Amended
2026-11-17:* this is now moot for transactors, which are found only
statically (above).

Recommendation:
- **The complete lookups are made statically.** The generators work from
  IR, where every registration is present (§7, Z7). The generated
  testbench and bind module name each specialization explicitly, so their
  rt-sv images contain the registrations they need.
- **The run-time queries are complete for what the image contains.**
  `fw_protocol::of(b)` and `p.api(...)` are always answerable, because
  the bundle and the protocol are present wherever a bundle is. There is
  no run-time transactor query (amended 2026-11-17).

**Zuspec (Z7).** The hub and its registrations have to reach the IR,
because all of the generated collateral is produced from IR (§7):
- the derived classes, from the kit's types;
- the bind module and the testbench, from the elaborated design (§9).

Z7 is **a new Zuspec work item**: a protocol type in ir-core, with
- its APIs and their direction;
- the bundle types that name it;
- the transactor types registered with it, per role;
- the protocol and role of each bundle instance in an elaborated design.

The YAML kit descriptor and `kits.py` are then retired (done
2026-11-18, K11). If zuspec-synth still needs a `zuspec.kit` file, it is
generated from the IR.

### 3.3 Abstraction levels: transactors and abstractors

*Direction set in review, 2026-11-16; decision 19.* Many protocols have a
wire-level form and a useful abstract form. UART is serial on the wire,
but conceptually it is a stream of bytes with meta-data (parity error,
framing error, break). A fast software model should move bytes, not
bits. A test, checker or coverage model written against bytes should run
on both the fast model and the RTL.

**Two cases.** The hub (§3.1) already relates two levels inside one
protocol: its API is the method level and its bundle the pin level, and
the transactor converts between them. AXI4 is already this case: its API
carries bursts, and its channels carry beats. So the test for "one
protocol or two" is whether the abstract level exists on its own:

| Case | Shape | Converter | Example |
|---|---|---|---|
| The abstract level is this protocol's transactions | **One protocol:** the API is the abstract level, the bundle is the wire | the **transactor** (§6) | UART: API `put #(uart_char_t)`; bundle: the serial `tx` line. AXI4: bursts over beats. |
| The abstract level is another protocol, used on its own or over several wire protocols | **Two protocols**, related by an **abstractor** | the abstractor: a typed component registered with both | a layered stack (symbols to packets to transactions); one packet protocol carried over two PHYs |

UART is the first case. Its API can be std's neutral `put` API
specialized on `uart_char_t`. APIs are shared between protocols already
(`a.protocols()`, §3.1), so code written against `put #(uart_char_t)`
works on any protocol that registers it, with no second protocol.

```systemverilog
typedef struct packed { logic [7:0] data; logic parity_err, frame_err, brk; } uart_char_t;

class uart_proto #(uart_param_t P = UART_PARAM_DEFAULT) extends fw_protocol;
    typedef uart_proto #(P) this_t;
    `fw_protocol_param_utils(uart_proto)
    typedef uart_cfg_t cfg_t;                        // §3.4
    static function void declare(fw_protocol_decl d);
        d.api(fw_api_type_of #(fw_put_if #(uart_char_t))::get(), FW_PROTO_REQ);
    endfunction
endclass
// The frame time is the kit's timed channel's, not the hub's (§3.5).
```

**The abstractor (the second case)** registers with two protocols, as a
transactor registers with one, and in the same way: the registration
points at the hubs, so neither protocol names the other, and a third
party can add an abstractor without editing either.

```systemverilog
class pkt_over_phy_abs #(...) extends fw_component;
    typedef pkt_over_phy_abs #(...) this_t;
    `fw_abstractor_param_utils(pkt_over_phy_abs, phy_proto #(...), pkt_proto #(...))
```

- Queries: `p.abstractors()`, and `fw_protocol::abstractor_for(from, to)`
  in either direction.
- Elaboration can insert one when two sides are connected at different
  levels. P6's struct-port `connect(socket)` already inserts a converter;
  this generalizes it.
- **One registration kind.** A transactor is the degenerate abstractor:
  both sides are the same protocol, the API on one side and the bundle on
  the other. The two macros stay, for readability, but share one
  registration, one query path and one Z7 shape (a converter with two
  sides and a direction). The generators look up one kind of thing.
- **One hop first.** Chains (a stack of three levels) compose by
  connecting abstractors. Finding a path across several is left until a
  kit needs it.

**What the abstract level keeps is declared.** The abstract payload's
meta-data is exactly what the abstraction keeps: for UART, the error and
break flags, which carry both error injection (downward) and error
detection (upward). Exact bit timing is dropped, and is visible as
dropped rather than silently lost.

**Timing.** A converter across levels cannot add zero time: a UART byte
takes `frame_bits × bit_time`. Decision 8's rule "a transactor adds no
cycles" is read as *no cycles beyond the protocol's own transfer time*:
no FIFO and no added latency. For rv the transfer time is the handshake
cycle; for UART it is the frame time from the configuration (§3.4).

**Observation across levels.** A wire-level monitor feeding an upward
transactor or abstractor produces API-level listener events (§4.3). A
checker written against bytes runs on a fast model and on RTL alike.

### 3.4 Configuration state: publisher and consumer

*Direction set in review, 2026-11-16; decision 20.* Some protocols have
run-time configuration that more than one party needs. A UART's baud
rate, data bits, parity and stop bits are needed by:
- the transactor, to drive and sample the serial line;
- a self-timed connection, to time a byte-level transfer (§3.5);
- a monitor, to sample the line.

The configuration belongs to the component that owns it (the UART's
registers). Others read it. There is no need to subscribe to changes.

**What SV allows** (checked in pyslang and Verilator, probes in
`probes/cfg-ref/`): a function cannot return by reference, `const` or
otherwise; `ref` and `const ref` exist only on arguments. A struct
returns by value, as a copy. Class handles are the only references, and
SV has no `const` objects.

**Design: pushed copies, read directly.** Configuration changes rarely,
and is read on every transfer. So the copy happens on change, and a read
is a field access with no call:

```systemverilog
// In the UART (the owner):
fw_cfg_src  #(uart_cfg_t) cfg_pub;        // was fw_cfg_publisher (decision 22)
...  cfg_pub.set(c);              // the commit point: pushes c to every consumer

// In a transactor, monitor or timed channel:
fw_cfg_sink #(uart_cfg_t) cfg;            // was fw_cfg_consumer
...  bit_t = 1s / cfg.cfg.baud;   // a direct read of the consumer's copy
```

- **The configuration is a struct value** (a packed struct where it fits).
  It maps directly to Zuspec IR, which K5 extends to packed structs; a
  class handle would need object references in the IR.
- **The publisher keeps its own copy**, and pushes it to a consumer when
  the consumer is bound. So a `set()` in `build()`, before connect,
  still reaches every consumer, and no consumer reads a default by
  accident.
- **`set()` is the commit point.** The owner may build the new value
  field by field; consumers see it only when the whole struct is pushed,
  so they never see a half-changed configuration (a new baud with the old
  parity).
- **A consumer samples at the start of a transfer.** A `set()` can land
  mid-transfer, so a consumer reads the fields it needs into locals when
  a transfer starts, and uses them for that transfer. That is a few
  fields, not a copy of the struct. A divisor change mid-frame takes
  effect on the next frame, as in hardware.
- **Consumers never write their copy.** Checked twice:
  - fe-sv, statically: any write whose target starts with a consumer's
    `cfg`, from outside the runtime, is an error. This includes a partial
    write (`cons.cfg.baud = x`) and passing it as a `ref` argument;
    `const ref` is allowed.
  - rt-sv, at run time: before each push, the publisher compares each
    consumer's copy with the last value pushed, and reports a mismatch.
    `set()` is rare, so this costs nothing that matters, and it catches
    writes from code fe-sv never saw.
- **One copy per consumer.** Fan-out is a loop of small copies on each
  `set()`. A shared copy behind a handle would cost the direct read.
- **A change listener** *(amended 2026-11-17, decision 22; was "no change
  events")*. Configuration is passive: a reader sees only the current
  value, so checking it on every transfer costs on every transfer. A
  consumer may instead register a listener, called after each push with
  the new value. A sink or channel uses it to check a configuration once
  per change: a VIP checks that it supports the new baud, a
  device-to-device channel flags a mismatch at the register write that
  causes it. A consumer with no listener pays nothing. Derived values
  (bit time, frame bits) are still computed at the start of a transfer.

**Configuration travels with an endpoint** *(amended 2026-11-17, decision
22; was "Binding is derived" through the hub's `cfg_t`)*.
- A method-level endpoint (§5) **may** carry configuration; most do not.
  One that does is a **source** or a **sink**, and the role is in its
  class name, so a wrong connection does not compile:

  | Endpoint | No configuration | Sources it | Sinks it |
  |---|---|---|---|
  | port | `fw_port #(API)` | `fw_port_cfg_src #(API, CFG)` | `fw_port_cfg_sink #(API, CFG)` |
  | export | `fw_export #(API)` | `fw_export_cfg_src #(API, CFG)` | `fw_export_cfg_sink #(API, CFG)` |
  | socket | `fw_socket #(OUT, IN)` | `fw_socket_cfg_src #(OUT, IN, CFG)` | `fw_socket_cfg_sink #(OUT, IN, CFG)` |
  | configuration only | — | `fw_cfg_src #(CFG)` | `fw_cfg_sink #(CFG)` |

- A source publishes. Its owner sets it, for a device from its
  configuration registers. A sink consumes: its owner reads `cfg` (and
  may listen for changes).
- `fw_cfg_src #(CFG)` and `fw_cfg_sink #(CFG)` are the same roles with no
  API, for configuration that is not tied to a method-level connection
  (a power controller's mode read by a power model). They follow the
  same rules: factory, `connect()` phase, netlist, source-to-sink only.
- `connect` joins a source to a sink of the same `CFG`, and its argument
  type says so: source to source, sink to sink, and a configured to an
  unconfigured endpoint are compile errors. `connect_up` passes an
  endpoint to a parent endpoint of the *same* role.
- Configuration is a property of the endpoint, not of the protocol. The
  hub's `cfg_t` no longer drives binding.
- Each side of a link has its own configuration. A UART link has no
  shared clock, and its two ends are configured independently; a channel
  (§3.5) joins them.
- Not covered yet: configuration on a *bundle* port, for a transactor at
  a DUT's pins (see "Open: a wrapped RTL UART" below).

**Static view.** A consumer's `cfg` has exactly one writer, the
publisher's push, and any number of readers. In IR this is the shape of a
single-driver connection, updated by an event instead of continuously:
- the netlist records it like a port connection;
- it takes part in the domain crossing check, which matters when a
  register write in one clock domain sets a configuration read in another;
- in hardware it lowers to wires from the configuration registers.

The static no-write rule is what makes the single-writer claim true.

**The general primitive** *(amended 2026-11-17, decision 22)*.
`fw_cfg_src #(T)` and `fw_cfg_sink #(T)` are a capability class pair, not
methods on `fw_component`. They replace `fw_cfg_publisher #(T)` and
`fw_cfg_consumer #(T)` (renamed, so the standalone pair and the
configured endpoints share one vocabulary); the push, the commit point,
the direct read and the no-write check above are theirs. The configured
endpoints (`_cfg_src`, `_cfg_sink`) carry the same behavior.

**Open: a wrapped RTL UART.** In the testbench case (§9), the DUT's real
configuration is in its registers, not in a publisher. The transactor at
its pins still needs a consumer. Either the testbench programs the DUT
and a publisher from one source, or the transactor detects the baud
rate. Prep starts with the first.

### 3.5 Timed channels

*Amended 2026-11-17, decision 22 (supersedes decision 21's derived
insertion).* When two class-level UART models are connected at the byte
level, an outbound byte should take a frame time. The initiator should
not time it: that duplicates what the transactor does at the signal
level, and every initiator would write it again. Neither should the
receiver. **A channel times it**, and neither end knows it is there.

- **The channel is explicit.** A channel is a component in the topology,
  shipped by the protocol kit and placed by the user. It is not inserted
  by elaboration (decision 21 had elaboration insert one when the hub
  defined `xfer_time`; SV cannot tell whether a hub defines a static
  function, so that needed a registration only GenKit or the user could
  write). Without a channel a link is untimed, and that is visible in the
  topology. Derived insertion may come back later; not in prep.
- **Its shape follows the endpoints (§5).** A channel between a port and
  an export is one-way. A channel between two sockets is two-way, since
  calls travel both ways. A kit can ship both, for example
  `uart_tx_chan` (one-way) and `uart_txrx_chan` (two-way).
- **Configuration decides what kind of channel it is (§3.4):**

  | Channel | Joins | Its endpoints | Timing | Mismatch |
  |---|---|---|---|---|
  | forwarding | a device and a VIP | sink on the device side, source on the VIP side; passes the device's configuration through | by the device's configuration | none: one configuration |
  | sinking | two devices | sinks on both sides | each direction by its sender's configuration | when the two differ |

  ```systemverilog
  // device <-> VIP
  dut_uart.sock.connect(fwd.dev);     fwd.vip.connect(uart_vip.sock);
  // device <-> device: each device sources what its registers hold
  uart_a.sock.connect(dd.a);          dd.b.connect(uart_b.sock);
  ```
- **The kit owns the timing, as methods of the channel.** A std base
  (`fw_timed_channel`) holds the sampling and delivery; the kit's channel
  defines the transfer time and the mismatch rule as virtual methods, not
  as conventions on the hub. The transactor uses the same helpers (bit
  time, frame bits) at the signal level, so the timing is written once,
  in the kit.
- **A channel samples the sender's configuration at the start of a
  transfer** (§3.4). A sinking channel compares it with the receiver's:
  its mismatch rule returns the payload as the receiver sees it (for
  UART, with `frame_err` or `parity_err` set), so the most common UART
  bug is visible in a fast model, at byte speed. A channel may also
  check on change, through the consumer's listener (§3.4).
- **Blocking is up to the channel.** One channel may block the sender for
  the transfer time and deliver unbuffered; another may return at once
  and queue.
- **Depends on layer 2.** Delaying a delivery needs time in the class
  model, so channels are Part B. The configured endpoints are Part A.

---

## 4. The protocol API and its derived collateral (R2, R4)

### 4.1 Hand-written versus derived

Adopt fw-proto-axi-new's split (`design-new-style.md` §1). The test is
that **adding a payload field or an API method is a one-line change**.

| Written by hand (the core) | Derived |
|---|---|
| parameters and encodings (class-free package) | `<api>_base` (each method defaults to an error, or empty with `fw_default`) |
| one packed struct per channel payload | `<api>_listener`, `_listener_base`, `_listener_fanout` |
| the bundle (§3) | `<api>_proxy` (target plus listeners) |
| the transaction API(s), `fw_api` | `<api>_imp #(P, IMP)` (replaces the `_IMP` macros) |
| adapters between the transaction API and the channels; a reference model; rules | channel APIs `<p>_req_if`/`<p>_rsp_if` from the bundle; payload `sprint`/`compare`/`mask`; field table and pin-map presets; transaction classes (§4.3); transactors and monitors (§6) |

### 4.2 API shape

Keep the conventions fw-proto-axi-new settled. They are shared with
fw-api-kit and keep the API pyhdl-if-friendly:
- **Split by direction.** A request returns once it is accepted, and
  responses arrive as calls. No thread waits per outstanding transaction.
  A blocking form is a shim on top of the split API.
- **A response may arrive inside its request's call.** A caller is ready
  for its responses before it calls.
- **Signature rules:**
  - a method is a task if it may block, and a function otherwise;
  - arguments are `input`/`output` only;
  - there are no `ref` arguments, events or class handles;
  - argument types are packed types and queues of them;
  - signatures use class-local typedefs.
- **One parameter struct per protocol**, `#(<p>_param_t P)`, on every class
  and module.
- **Channel APIs:** one method per channel, with the method name equal to
  the channel name. This is the only link a transactor needs between a
  method and its pins.

**Spec or std?** The conventions and the *shape* of the derived classes
(names, methods, calling order) are normative. They go in a new
`fw-hdl-spec/semantics/protocols.md`. A user extends `<api>_base`, attaches
`<api>_listener`s, and relies on `<m>_pre` coming before `<m>_post`, so
these are language-level promises, like the bundle roles. The generators
that produce them are automation in fw-hdl, not part of the spec (§7).

### 4.3 Listener, transaction classes, recorder and bridges (R4)

**Listener.** As in fw-proto-axi-new:
- `<m>_pre(inputs)` and `<m>_post(inputs, outputs)` per method;
- callbacks are functions, so a listener cannot block or change the call.
  That is required for rules to be checkable in formal;
- on a proxy, pre comes before forwarding and post after it returns;
- on a pin monitor, pre is the first cycle with `valid`, and post is the
  handshake.

The monitor role has no API of its own: a monitor emits listener calls.

**Transaction classes.** The roadmap asks for a transaction class per
direction. fw-proto-axi-new deliberately has none: a channel's payload
struct is its transaction. That is enough for rules and adapters, but not
for four kinds of user:
- UVM agents and sequences need objects;
- a recorder needs a uniform record;
- randomization (§11) needs `rand` members;
- method↔transaction bridges need a value that stands for a call.

**Recommendation.**
- **Derive one transaction class per API method:** `<api>_<m>_txn`.
  - Its members are the method's inputs and outputs, as the payload types.
  - It is `rand`-capable.
  - It has `sprint`/`compare`.
  - Optionally it carries timing: the pre and post times, or cycles.
- **Group them per direction,** as the roadmap asks: `<p>_req_txn`
  and `<p>_rsp_txn` are tagged unions, or a common base, over their API's
  methods.
- **Payload structs stay the wire-level value.** The transaction class
  wraps them; it does not replace them.
- **Derive the two bridges:**
  - **method → transaction:** `<api>_txn_listener` implements the
    listener and emits a transaction object at `<m>_post` to a sink.
  - **transaction → method:** `<api>_txn_driver` takes transaction
    objects and makes the calls on an `<api>` handle.
- **Recorder.** A recorder is a `<api>_txn_listener` whose sink writes
  records. The format and sink are a later choice:
  - the old core's `fw_dbg_rec` format, or
  - a waveform transaction stream.

  For prep, the recorder needs only the listener and the txn class.

### 4.4 The rv std protocol and the existing role APIs

The old rv role APIs map onto the derived ones, so none of them is ported
as hand-written code:
- `send` maps to the channel API `rv_req_if.<ch>`;
- `put` maps to the target side of the same API;
- `observe` maps to the listener.

The generic `fw_put_if`/`fw_get_if`/`fw_reqrsp_if` APIs are std APIs in
their own right. They are std's protocol-neutral layer, which adapters
map onto (e.g. AXI→mem). Like any other API, they are written as `fw_api`
classes with derived collateral.

---

## 5. Sockets and connection (R3, layer 3)

**Today.** The old core's model works, and fw-proto-axi-new relies on it:
- `fw_port` holds a required API and `fw_export` provides one;
- `fw_socket #(I,E)` is a port of I plus an export of E, and its peer
  `fw_mirror #(I,E)` is the reverse;
- `connect` binds both directions, and `connect_up` passes through a level
  of hierarchy;
- binding is required, and a port resolves its target once in the
  connect phase.

**What the new core changes.**
- **Names.** "port" now means a signal port, and `fw_mirror` is a bundle
  role (§2).
- **Phase rules.** Connections are made in `connect()`, the same phase
  rule as signal connections (`semantics/connections.md`).
- **Domains.** The domain layer associates domains with interfaces (ports
  and bundles). Method-level endpoints need the same association, so that
  the crossing check covers a socket connected across clocks.
- **Netlist.** Socket connections must appear in the elaborated netlist, so
  that fe-sv and the testbench generator see them.

**Recommendation.**
- **Two typed endpoint classes, parameterized by API** *(names amended
  2026-11-17, decision 22; were `fw_api_port` / `fw_api_export`)*:
  - `fw_port #(API)`, the client side: it calls `API`;
  - `fw_export #(API)`, the provider side: it implements `API`.

  Signal endpoints are `fw_input`/`fw_output`, so the short names do not
  clash, and "api" in every name made the configured forms
  (`fw_port_cfg_src`) long. They follow layer 1's rules:
  created through the factory, connected in `connect()`, recorded in the
  netlist, and with domain association as for bundles.
- **Sockets parameterized by an API pair** *(amended 2026-11-17, decision
  22; was `fw_socket #(PROTO)` / `fw_target_socket #(PROTO)`)*:
  - `fw_socket #(OUT, IN)` calls `OUT` and provides `IN`. Its peer is
    `fw_socket #(IN, OUT)`: swapped APIs mean the mirror image, so there
    is no separate target class, and two identical full-duplex devices
    (`fw_socket #(put_if, put_if)`) connect socket to socket.
  - Conceptually a socket is a port of `OUT` bundled with an export of
    `IN`. It is not implemented as one: it is its own endpoint class.
  - Use a socket when calls travel both ways, and a port/export pair when
    they travel one way.
  - Each endpoint kind has configured forms (`_cfg_src`, `_cfg_sink`,
    §3.4).

  **The role is derived, never declared or registered.** Against a
  protocol, an endpoint's role is which way the protocol's APIs travel
  through it:
  - outbound `req` (and inbound `rsp`): initiator;
  - outbound `rsp` (and inbound `req`): target;
  - the same for ports and exports: a port of `req` is an initiator, an
    export of `req` a target.

  A symmetric socket (`fw_socket #(put_if, put_if)` on a protocol whose
  `req` is `put`) is both, which is right: a full-duplex UART has no
  initiator. An API shared by several protocols (std `put`) gives a role
  per protocol, so the generators (§6, §9) ask in the context of the
  protocol they start from (the DUT port's), not of the socket alone.
  This is why there is no `fw_target_socket`: a target class would put
  the role in the type, where it is redundant with the API order, and
  would double the configured family (initiator/target is independent of
  source/sink: an AXI master device sources configuration, an AXI master
  VIP sinks it).
- **Implementing an export.** A component implements an export with a
  derived `<api>_imp`, never with a macro. Generating per-field
  forwarders (fw-proto-axi-new §4.4, "later") is not needed for
  prep.
- **Synthesis.** Method-level endpoints are simulation-only in prep. fe-sv
  records them in the netlist, but lowering a method-level connection to
  hardware (Zuspec channel or `PortApi` primitives) is a later layer. A
  method-level connection becomes pins only through a transactor.

---

## 6. Transactors (R6)

**Today: two incompatible timing models.**
- **The old rv kit,** which fw-proto-axi-new's generated transactors build
  on:
  - an SV interface with a FIFO (depth 4, up to 16, with a `max_gap`
    random stall) in front of a registered core;
  - `send()` returns when the beat is queued, not when it is accepted;
  - the beat reaches the pins about 2 cycles later;
  - the monitor core is a 1-deep skid, and can drop beats at full bus
    rate (`skills/fw-proto-kit` example).
- **The sync-layer pin bridge** (`fw_rv_pin`). It is signal-to-signal, and
  has zero latency with `COMB=1`: comb fields settle in the same time step.

The roadmap asks for the second property for method↔signal transactors:
"must bridge method/signal without latency".

**Issue.** A FIFO in the transactor gives a test a different cycle-level
behavior from the method-level model it replaces. A test tuned against
class-level timing changes behavior when an abstractor is inserted. It
also means a monitor can lose beats.

**Recommendation: a transactor adds no cycles and holds no buffer.**
"No cycles" means none beyond the protocol's own transfer time (§3.3):
for rv that is the handshake cycle, for UART the frame time.
- **Outbound (a call drives the pins):**
  - the call drives `valid` and `data` in the cycle it is made;
  - the call returns at the clock edge where `valid && ready` holds;
  - a back-to-back call keeps `valid` high, so full throughput needs no
    FIFO.
- **Inbound (the pins make a call):**
  - the transactor makes the call in the handshake cycle;
  - `ready` is the callee's acceptance, which is a comb path from the
    target's state;
  - a target that blocks holds `ready` low.
- **Monitor:**
  - `<ch>_pre` is called on the first cycle with `valid`;
  - `<ch>_post` is called on the handshake;
  - it never buffers and never drops beats.
- **Buffering and random stalls are separate std components** (`fw_fifo`,
  a stall injector) that a user inserts on purpose. The knobs `depth` and
  `max_gap` move onto them.
- **How it is written:** a transactor is an ordinary layer-2 component.
  - Its procedural side is `run()`, and its pin side is `comb()`/`step()`
    on a bundle.
  - This is the "mix `run()` and `step()`" case in fw-proto-axi-new's
    `design-sync-rtl.md` §3.5.
  - So this step depends on layer 2, and on comb semantics on bundle
    members.
  - The synthesizable pin core is the lowered `comb`/`step` part. It
    replaces the hand-written `*_xtor_core.sv`.
- **Per-channel generation.** For a protocol whose channels are all
  `fw_rv_if`, a transactor is one rv transactor per channel, wired by a
  derived wrapper. This is fw-proto-axi-new's `xtors.py`, retargeted.
- **Non-rv channel families.** A family like APB's PSEL/PENABLE/PREADY
  needs a family-specific transactor. Prep covers rv only. The family
  interface (control fields, the signal-level hold rule, the transactor
  generator) is made explicit so a second family can be added.

**Complex protocols.** The per-channel transactors are generic. What a
complex protocol adds is the adapter between its transaction API and its
channels: for AXI, bursts, ordering per ID and response matching. In
fw-proto-axi-new these adapters are hand-written behavior. The std
components `match`, `order` and `pool` (project-architecture §3.1) are
the higher-level constructs the roadmap hints at. Prep only notes them;
whether adapters can be built from them is a question for the first
complex kit.

---

## 7. Generating the collateral (R5)

*Revised after review (2026-11-15, decisions 10–12).* The first draft had
sv-weave generate the SV collateral, and kept the weavers in
`fw-hdl-spec`. Review changed both points:
- **All collateral comes from IR-driven generators.** Every construct
  involved (protocols, bundles, APIs, payloads, components) must be
  represented in Zuspec IR anyway.
- **sv-weave is for something else:** cases where the user works on
  arbitrary source, or source written in a custom pattern.
- **The spec stays pure spec.** The automation is part of fw-hdl proper.

**Today.**
- sv-weave is a dependency, but only `examples/rr_merge` and some tests
  run it.
- Its two fw-hdl plugins, `settle` and `sp_comb`, work on arbitrary user
  `comb()`/`step()` bodies. That is the kind of job review assigns to
  sv-weave.
- The fw-proto weavers (`fw_proto_weave`, including `xtors.py`) are in
  fw-proto-axi-new. They read SV attributes through sv-weave's pyslang
  model. They hold the logic for what to derive, and this logic is
  ported.
- `upstream-sv-weave.md` there lists three sv-weave gaps:
  - the up-to-date check misses an edited weaver;
  - `DECLFILENAME` lint;
  - two init packages in one image.
- Those gaps stay sv-weave's issues. They no longer block protocol kits.

**Recommendation.**
- **Two stages, both from Zuspec IR.**
  1. **Kit stage, from the kit's types.**
     - fe-sv reads a kit's hand-written core into IR: the protocol
       class, the bundles that name it, the API interface classes it
       registers and the payload structs (§3.1, Z7).
     - Generators emit the derived SV from that IR:
       - bases, listeners, proxies, fan-outs and imps;
       - channel APIs;
       - txn classes and bridges;
       - transactor and monitor components;
       - pin-map presets.
     - The kit's core plus the generated package form the kit library.
       Both rt-sv and fe-sv read it like any other source.
     - This works because a kit's core is a library, built before any
       design that uses it. User code names the derived classes, so they
       must exist before user code is read. Generating them per kit, ahead
       of the design, satisfies that.
  2. **Design stage, from the elaborated design.** These outputs depend
     on the elaborated design, so they are generated from its IR:
     - the testbench top and the bind module (§9);
     - later, the Python and UVM collateral (§10, §11).
- **fe-sv has two modes** (Q-A below):
  - **scan:** parse a collection of SV, map its types to IR, and find
    the fw-hdl types in it (here, protocols and their parts);
  - **elaborate:** elaborate a given specification, which is layer 1's
    `Elaborate`.

  The kit stage uses scan, and the design stage uses elaborate.
- **Where the generators live: fw-hdl proper, not `fw-hdl-spec`.**
  - The spec states what is generated: the shapes in
    `semantics/protocols.md` (§4.2).
  - The generators are automation that meets that statement.
  - Home (*decided 2026-11-15*, Q-B): a generator package `fw.hdl.gen`
    in `fw-hdl-fe-sv`, since it consumes fe-sv's IR. Emission of general SV constructs goes
    through zuspec-be-sv, not a private emitter.
- **sv-weave's role.** It keeps the source-pattern jobs:
  - `settle` and `sp_comb`, which stay with rt-sv as project-architecture
    says;
  - future user-pattern automation, such as the comb/step closure
    annotation that `roadmap.md` "Basic RTL" mentions.

  It is not on the protocol-kit path.
- **One generation per kit, in its flow.** fw-hdl exports a dfm task,
  `fw.hdl.GenKit`, that runs the kit stage. Transactors are always
  included, so fw-proto-axi-new's `woven`/`woven-xtor` split goes away.
  Unlike sv-weave today, the task's up-to-date check covers the
  generator's own version.
- **Generated code is not committed** (*decided 2026-11-15*). It is
  build-time only, with golden tests of the generators themselves.

**Open questions raised by the revision.**
- **Q-A: fe-sv scanning a collection of sources.** *Decided 2026-11-15.*
  - **The two modes are fe-sv's job.** fe-sv parses a collection of SV
    and finds the relevant types in it, and it elaborates a given
    specification. Scanning is not a special case of elaboration.
  - **Layer 1 left out the scan mode.** `core-layer1.md` §6.7 defines
    only `Elaborate` (sources plus a top class). Layer 1 had no
    type-level outputs, so the scan mode was not needed then. It was
    never a limit of the design.
  - **The pieces exist underneath.** zuspec-fe-sv's `SVMapper` already
    maps classes, structs and methods to IR from parsed source without
    elaborating. The interpreter that fe-sv uses for `build()` runs the
    static registration functions as well.
  - **`core-layer1.md` §6.7 is amended** (done 2026-11-15) with a `Scan`
    task next to `Elaborate`.
    - Input: SV sources.
    - Output: a `.zir` of the types found. This covers the fw-hdl types
      known by their registration macros: protocols, components, extern
      wrappers, domain kinds and bundles. Their registrations are
      evaluated as intrinsics.
    - `Elaborate` can then take a scanned `.zir` and a choice of top,
      instead of re-parsing.
  - **For a kit, the protocol class is the hub** (§3.1):
  - **Input.** The kit's flow gives fe-sv the kit's source fileset.
  - **Entry points.** fe-sv finds the protocol classes in it, by
    `` `fw_protocol_utils ``.
  - **APIs.** fe-sv reads them from each protocol's `declare()`, which
    is interpreted like the other static registrations, as intrinsics.
  - **Bundles.** fe-sv finds them by their `` `fw_bundle_protocol ``
    naming the protocol.
  - **Transactors.** Hand-written ones are found in the kit's source,
    by `` `fw_xtor_utils ``. Generated ones register in the generated
    code, and the design stage sees them.
- **Q-B: the generators' repo.** *Decided 2026-11-15:* `fw-hdl-fe-sv`,
  as `fw.hdl.gen`. They split out only if a second front end appears.

---

## 8. The std package and the rv std protocol (R9)

**Today.**
- The spec has `fw_rv_if #(T)` in core (decision D4: rv is built in).
- The old core's std is `src/std`: role APIs, bridges, xtors and the kit
  YAML.
- `skills/fw-proto-kit/references/example` duplicates the rv kit in the
  old style.
- project-architecture §3.1 puts the standard library in `fw-hdl-spec`.
  It says the duplicate rv kit is retired.

**Recommendation.**
- **Create the std package now.**
  - It is named `fw_hdl_std_pkg` (*decided 2026-11-15*), keeping the
    `fw-hdl` tag line.
  - Its hand-written source goes in `fw-hdl-spec`, written only against
    core.
  - Its derived package is generated at build time by the kit stage
    (§7), so std is the first consumer of `fw.hdl.GenKit`. This means
    building std depends on fw-hdl's generators, while the spec repo
    holds only std's source.
- **The rv std protocol is written exactly as a kit would be:**
  - `fw_rv_proto #(T)` is the protocol class, and `fw_rv_if #(T)` names
    it with `` `fw_bundle_protocol ``;
  - the channel API is derived;
  - the zero-latency rv transactor and monitor (§6) are included;
  - the back-to-back sim test and the SBY formal component follow
    `skills/fw-proto-kit`.

  The std rv protocol is then the reference kit. It is also the
  per-channel building block that every rv-based protocol's derived
  transactor uses (§6).
- **The protocol-neutral std APIs** (`put`, `get`, `reqrsp`, `mem`) are
  in std as `fw_api` classes, with derived collateral (§4.4).
- **Retire the old pieces:**
  - the skill's rv example, which becomes a small non-rv protocol, or
    points at std rv and fw-proto-axi;
  - the old-style rules in `skills/fw-proto-kit`, whose new style is
    `writing-a-protocol-package.md`, moved to fw-hdl;
  - `fw_rv_kit.yaml`/`fw_put_kit.yaml` and `kits.py` (§3).
  (All three done 2026-11-18, K11; the guide is fw-hdl-spec
  `docs/protocol-packages.rst`.)
- **Move `fw_proto/` into fw-hdl** (fw-proto-axi-new D2).
  - The weaver logic (`fw_proto_weave`, `xtors.py`) is rewritten as
    IR-driven generators in `fw.hdl.gen` (§7). The rules for what to
    derive carry over, but the sv-weave plumbing does not.
  - The SV runtime
  part (`fw_proto_pkg`: `fw_dir_e`, `fw_field_t`, `fw_inbox`, the rule
  library) is ported into std and the spec, not copied. Parts the new
  core makes redundant are dropped:
  - `fw_rv_ch` → `fw_rv_if`;
  - `fw_sp_base` → bundles;
  - `fw_realized`/`fw_extern_component` → layer-1 externs.

---

## 9. First use: wrapped IP, testbench, bind monitors (R8)

**Today.**
- fw-proto-axi-new's P6 does testbench generation on the old core:
  - a struct port's `connect(<socket>)` inserts an abstractor;
  - an emitter writes the netlist and a `<top>_sim.sv`, with one
    transactor per abstractor;
  - three reference IPs pass.
- Nothing generates a `bind` module.
- In the new core, layer 1 maps an extern's pins to bundles with
  `extern_map` and pin rules (`prefix`, `rename`), so the protocol ports
  of a wrapped IP are already known as bundles.

**Recommendation.** Both outputs are generated from the elaborated IR (Z7
records which bundle instances are protocol ports, and in which role).

1. **Testbench with connected transactors.**
   - For a wrapped IP (or any component), emit a top that instances the
     DUT and one transactor per protocol port.
   - The transactor's role is the opposite of the port's: a target port
     gets an initiator transactor.
   - Clock and reset come from the DUT's domains.
   - On the class side, each transactor exposes a socket (or port/export)
     plus a proxy, reachable by path (`dut.s_axi`), so
     tests and listeners attach by path.
   - This is P6's abstractor, without a struct-port `connect` overload.
     The generator places the transactors, not user code.
2. **Bind module with monitors.**
   - For a design's module (a wrapped IP or emitted RTL), emit
     `bind <module> <p>_monitor #(.P(...)) u_<port>_mon (...)` per
     protocol port, with the pins connected by the pin map.
   - The monitor has no outputs, so the design is unchanged.
   - Its class side is a listener fan-out registered by hierarchical path.
   - Rules, recorders and scoreboards attach to it.
3. **Self-test of transactors.**
   - Prep uses the kit's own tests: back-to-back sim, plus SBY on the pin
     cores, as `skills/fw-proto-kit` prescribes.
   - fw-hdl-dv is an empty placeholder, so "self-test with fw-hdl-dv"
     waits until fw-hdl-dv has content.
   - The b2b test is written against the listener and txn classes so it
     carries over.

**Acceptance criterion for prep.**
- Take `packages/fw-hdl-fe-sv/examples/wrap_rtl` (an AXI-Stream slice and a
  FIFO, both rv).
- Declare their bundles as std rv protocol ports.
- Generate a testbench and a bind module.
- In Verilator:
  - drive traffic through the generated transactors from class code;
  - check it with a scoreboard on the bind monitors' listeners;
  - match a hand-written reference cycle for cycle. This shows that the
    transactors add no latency.

---

## 10. Python collateral (R7): deferred

*Decided 2026-11-15: deferred past prep.*

**Today.**
- Nothing exists.
- fw-proto-axi-new's API conventions were chosen to be pyhdl-if-friendly,
  and it lists "the pyhdl-if API definition from each `fw_api` class" as
  later work.
- `featherweight-ip-strategy.md` has the cocotb side drive the fw-proto
  transactor.

**What prep keeps so that this stays cheap later:**
- the pyhdl-if-friendly API conventions (§4.2);
- the API and protocol types in IR (Z7). The pyhdl-if API definition is
  then one more design-stage generator (§7), and cocotb is a thin layer
  over it.

Python-side randomization and coverage belong with §11.

---

## 11. Verification IP (R10): what prep must reserve

These are not built in prep, but prep must not block them:

| Need | What prep provides |
|---|---|
| Property checkers in terms of the API | The listener as the one observation contract (§4.3), with pre/post meaning the same at class and pin level. fw-proto-axi-new's rule library (`fw_rule`, `fw_count`, ...) moves with `fw_proto/` into the verification side, not into core. |
| Generated UVM agents | Txn classes, txn bridges and transactors with path-reachable sockets are the agent's driver, monitor and sequence item. The agent shell is generated from the IR, in the kit's `dv/` package (project-architecture §3.1). |
| Coverage monitors | A coverage collector is a listener. A parameterized collector per API is a later derivative. |
| Randomization, "constraints in terms of the API" | Txn classes have `rand` members, so `std::randomize` with constraints over a method's request and response values works directly. Whether *legality* constraints belong to the kit (a derived `<api>_<m>_txn` with a legal constraint) or to the user is open (§13 Q9). |

---

## 12. Scope of prep

In:
- the terminology (§2);
- the protocol class, its registrations (APIs, bundles, transactors)
  and the queries (§3.1),
  including Zuspec Z7;
- `semantics/protocols.md`: API conventions and the normative derived
  shapes (§4);
- txn classes and bridges, and the recorder as a listener (§4.3);
- method-level endpoints and sockets, as layer 3 (§5): spec, rt-sv,
  fe-sv netlist, domain association;
- abstraction levels (§3.3): the abstractor registration, shared with
  transactors, and its queries;
- configuration state (§3.4): the publisher and consumer pair with the
  change listener, the configured endpoints (`_cfg_src`/`_cfg_sink`),
  the no-write check;
- timed channels (§3.5): std's `fw_timed_channel` base and a kit's
  channels, placed explicitly (Part B);
- the zero-latency rv transactor and monitor, as layer-2 components (§6);
- IR-driven generators in `fw.hdl.gen`:
  - the kit stage, which includes fe-sv's `Scan` mode (Q-A),
    and `fw.hdl.GenKit`;
  - the design stage (§7);
- `fw_hdl_std_pkg` with the std rv protocol and the neutral APIs (§8);
- testbench and bind-module generation from IR, with the `wrap_rtl`
  acceptance (§9).

Out, for later:
- non-rv channel families (APB);
- complex-protocol adapters (§6), which are per kit;
- Python collateral: the pyhdl-if API definition and cocotb (§10);
- UVM agent shells, coverage collectors and legality constraints (§11);
- a recorder format and sink;
- generated per-field forwarders for exports (§5);
- abstractor chains: finding a path across more than one hop (§3.3);
- configuration from a wrapped RTL DUT's registers, or baud detection
  (§3.4);
- lowering method-level connections to hardware;
- fw-hdl-dv.

**Dependencies.**
- Domains: transactor clock and reset. Done (D1–D8).
- Layer 2, "Basic RTL": `run()` with `comb()`/`step()`, and comb semantics
  on bundle members. Not designed yet (§14.1).

The parts of prep that do not need layer 2 can start before it:
- §2–§5;
- §7, up to the kit stage for std (without the transactors).

---

## 13. Decision list

| # | Question | Status | Recommendation / decision |
|---|---|---|---|
| 1 | Terminology | *Decided 2026-11-15* | initiator/target roles; fwd/rev channel direction from the member's bundle role; req/rsp APIs; monitor is a listener producer; drop egress/ingress (§2) |
| 2 | `fw_mirror` name clash | *Decided 2026-11-15*; peer *amended 2026-11-17* (22) | Keep `fw_mirror` for the bundle target role. The method-level peer is no longer `fw_target_socket`: it is `fw_socket` with its APIs swapped (§5) |
| 3 | How a protocol is declared | *Direction set 2026-11-15*; names *decided 2026-11-16* as §14.3; roles *amended 2026-11-17* | A protocol class is the hub. It registers its APIs through `fw_api_type_of #(API)`. Bundles name their protocol (`` `fw_bundle_protocol ``). Transactors and generated APIs register with their protocol (`` `fw_xtor_utils ``); a role is never stated or registered, it is derived from the endpoints (bundle mixin on the pin side, `req`/`rsp` direction on the method side). Static queries (`fw_protocol::of`, `role_of`, `p.apis()`, `a.protocols()`) reach every part from any part; finding a transactor for a bundle is static only, in IR (§3.1). Attributes only for per-member facts (`fw_opt`, `fw_default`); fwd/rev and channel family come from the bundle (§3.1) |
| 4 | Protocol in Zuspec | *Decided 2026-11-16* as §14.3; **done 2026-11-18** (Z7 in K3; YAML and `kits.py` retired in K11) | New work item Z7: protocol type with its APIs, bundle types and registered transactors per role; protocol and role per bundle instance; retire the `zuspec.kit` YAML and `kits.py` (§3.1) |
| 5 | Derived shapes normative? | *Decided 2026-11-16* as §14.3 | Yes: names, methods and calling order in `semantics/protocols.md`; the generators are automation that meets it (§4.2) |
| 6 | Transaction classes | *Decided 2026-11-16* as §14.3 | One `<api>_<m>_txn` per method, grouped per direction; payload structs stay; derived `_txn_listener` and `_txn_driver` bridges; recorder is a txn listener (§4.3) |
| 7 | Method-level endpoints | *Decided 2026-11-16* as §14.3; names and sockets *amended 2026-11-17* (22) | `fw_port #(API)`, `fw_export #(API)` (were `fw_api_port`, `fw_api_export`); sockets `fw_socket #(OUT, IN)`, peer `fw_socket #(IN, OUT)` (was `fw_socket #(PROTO)` / `fw_target_socket #(PROTO)`); layer-1 phase, factory and netlist rules; domain association; simulation-only in prep (§5) |
| 8 | Transactor timing | *Decided 2026-11-16* as §14.3 | Zero added cycles, no buffer; drive in the call cycle, return on handshake; monitor never drops; FIFOs and stalls are separate std components (§6) |
| 9 | Legality constraints in txn classes | *Decided 2026-11-16* as §14.3 | Kit-provided legal constraints vs user-only (§11) |
| 10 | Where the generators live | *Decided 2026-11-15*, changed in review | Not in `fw-hdl-spec`: the spec is pure spec and states what is generated; the automation is part of fw-hdl proper, as `fw.hdl.gen` in `fw-hdl-fe-sv` (Q-B) (§7) |
| 11 | What is generated, and from what | *Decided 2026-11-15*, changed in review | All collateral comes from IR-driven generators: derived SV from the kit's types (kit stage), tb top and bind module from the elaborated design (design stage). sv-weave is for user work on arbitrary or custom-pattern source (`settle`, `sp_comb`), not for protocol kits (§7) |
| 12 | Generated code in git | *Decided 2026-11-15* | Build-time only; golden tests of the generators (§7) |
| 13 | std package and rv | *Decided 2026-11-15*, renamed | `fw_hdl_std_pkg` (the `fw-hdl` tag line); source in `fw-hdl-spec`; rv std protocol written as a kit and used as the reference kit; neutral APIs as `fw_api` classes; retire the skill's rv example and the kit YAMLs (§8) |
| 14 | `fw_proto/` from fw-proto-axi-new | *Decided 2026-11-16* as §14.3 | Port into fw-hdl (its D2): weaver logic as IR-driven generators, SV runtime into spec/std; drop what the new core replaces (`fw_rv_ch`, `fw_sp_base`, `fw_realized`, ...) (§8) |
| 15 | Prep acceptance | *Decided 2026-11-15* | `wrap_rtl` with std rv: generated tb and bind module, scoreboard on bind monitors, cycle-exact against a hand-written reference (§9) |
| 16 | Python in prep | *Decided 2026-11-15* | Deferred past prep; prep keeps the pyhdl-if-friendly conventions and the API types in IR (§10) |
| 17 | Scope | *Decided 2026-11-16* as §14.3 | §12 |
| Q-A | How fe-sv finds a kit's types | *Decided 2026-11-15* | fe-sv has two modes: `Scan` (parse a collection of SV, map its types to IR, find fw-hdl types by their registrations) and `Elaborate` (a given specification). Layer 1 defined only `Elaborate`, so `core-layer1.md` §6.7 gains `Scan`. For a kit, protocol classes are the entry points, and parts are found through their registrations (§3.1, §7) |
| Q-C | Registration of parameterized transactors at run time | *Decided 2026-11-16* as §14.3 | Complete lookups are static, from IR. Generated tb and bind modules name theirs explicitly. *Amended 2026-11-17:* transactor lookup is static only (bundle → protocol → registered transactors → the one with the counterpart mixin of that bundle type); rt-sv has no `xtors()` or `xtor_for` (§3.1) |
| 18 | Form of the registration macros' class argument | *Decided 2026-11-16* | §3.2's bare-name form fails in pyslang and Verilator (plan §5.1). Two forms, as in UVM: `` `fw_protocol_utils(C) `` for a class without parameters; `typedef C #(...) this_t;` and `` `fw_protocol_param_utils(C) `` for a parameterized one. The argument is the bare name, only stringified for the family name; fe-sv checks that `this_t` is the class's own specialization. The same pair for `fw_xtor_*` and `fw_abstractor_*` (§3.2) |
| 19 | Protocols at more than one abstraction level | *Direction set 2026-11-16* | One protocol when the abstract level is the protocol's own transactions: API above, bundle below, transactor between (UART: `put #(uart_char_t)` over the serial line). Two protocols and an abstractor when the abstract level stands alone or spans wire protocols. Transactor and abstractor share one registration, query path and Z7 shape. One hop first (§3.3) |
| 20 | Configuration shared between components | *Direction set 2026-11-16* | `fw_cfg_publisher #(T)` / `fw_cfg_consumer #(T)` (renamed `fw_cfg_src` / `fw_cfg_sink` by 22): a struct value, pushed on `set()` (the commit point), read directly from the consumer's copy; writes to a consumer's copy are errors, checked by fe-sv statically and by rt-sv on each push. *Amended 2026-11-17* (22): a change listener on the consumer (was: no change events); configuration travels with configured endpoints, not with the hub's `cfg_t` (§3.4) |
| 21 | Who times an abstract-level transfer | *Direction set 2026-11-16*; insertion *superseded 2026-11-17* by 22 | The connection, not the initiator. The hub defines `xfer_time(cfg_t, payload)` (and optionally `mismatch`); elaboration inserts std's `fw_timed_channel #(PROTO)` between API-level endpoints of such a protocol. Part B, since it needs time in the class model (§3.5) |
| 22 | Configured endpoints and explicit channels | *Decided 2026-11-17* | A method-level endpoint may carry configuration as a source or a sink, in its class name: `fw_port_cfg_src`/`_sink #(API, CFG)`, `fw_export_cfg_src`/`_sink`, `fw_socket_cfg_src`/`_sink #(OUT, IN, CFG)`; and standalone `fw_cfg_src`/`fw_cfg_sink #(CFG)` (renaming the publisher/consumer pair); source connects to sink, checked at compile time. Plain endpoints are `fw_port`/`fw_export #(API)`. Sockets are typed by their API pair, the peer is the swap, `fw_target_socket` goes; an endpoint's initiator/target role is derived from whether the protocol's `req` or `rsp` is its outbound API, never declared or registered. Consumers may listen for changes. Timing is in channels, which are kit components placed explicitly: port/export channels are one-way, socket channels two-way; a forwarding channel (device to VIP) or a sinking one (device to device, with mismatch); blocking is per channel; transfer time and mismatch are virtual methods of the channel (§3.4, §3.5, §5) |
| Q-B | Repo for the generators | *Decided 2026-11-15* | `fw-hdl-fe-sv`, as `fw.hdl.gen`; split out only if a second front end appears (§7) |

---

## 14. Readiness review (2026-11-16)

A check of what implementing this needs, against the code as it is after
domains D8. It changes no settled decision. It adds one blocking finding,
four toolchain gaps that become plan steps, and a recommendation for each
open decision.

### 14.1 Blocking: layer 2 is not designed

Transactors and monitors are layer-2 components (§6). Layer 2 does not
exist in the new core:
- there is no design doc or plan; `roadmap.md` "Basic RTL" is a sketch,
  and `core-layer1.md` lists processes as out of scope;
- `fw-hdl-spec/semantics/signals.md` has only a "Reserved (layer 2)"
  stub; there is no `fw_comb_if`/`fw_step_if`, no `read()`/`write()`, no
  `run()` hook and no process scenarios;
- rt-sv has no kernel or settle, and fe-sv lowers no process.

The old core's sync layer (`src/sync/*`, `python/fw/hdl/fe/elab/sync*.py`,
`docs/methodology/sync-logic.md`) is the reference to port, on old-core
types (struct ports), as `core-layer1.md` says.

What §6 needs from layer 2, stated as requirements on its design:
1. `read()`/`write()` on signals and on bundle members, with the update
   scheduler (request-update);
2. `comb`/`step` registration, and a `run()` task tied to the
   component's clock and reset domains, with an edge wait;
3. comb semantics on bundle members, on the effective (mirror-flipped)
   direction, so a `comb` that writes `ready` settles in the same edge;
4. defined visibility of `run()`'s writes, so a call drives `valid` and
   `data` in its own cycle and returns on the handshake edge (decision 8);
5. rt-sv: the kernel, settle and the pin bridge to RTL; fe-sv: lowering
   `comb`/`step` (`run()` stays simulation-only).

**Recommendation.** Split prep at this line (decision 17, §14.3).
- **Part A** needs no layer 2: the protocol class and queries,
  method-level endpoints and sockets, Z7, `Scan`, the kit-stage
  generators without transactors, and std with the rv protocol and the
  neutral APIs.
- **Part B** needs layer 2: the transactors and monitors, the design-stage
  generators (testbench and bind module) and the `wrap_rtl` acceptance.
- Layer 2 gets its own design and plan (`core-layer2.md`), with the five
  requirements above among its inputs. Part A runs alongside it.

### 14.2 Toolchain gaps

| # | Gap | Today | Needed |
|---|---|---|---|
| G1 | Mapping a kit's types to IR | zuspec-fe-sv `SVMapper` (`mapper.py`, `class_mapper.py`) skips parameterized classes, drops `extends`/`implements` and interface classes, maps only 2-state integral types, drops argument types, and reads no attributes but `zsp_output`. fw-hdl-fe-sv does not use it. | Parameterized classes with value parameters of struct type; `extends`/`implements`; interface classes; packed structs, enums and class-local typedefs; full method signatures; general attributes (`fw_opt`, `fw_default`). In zuspec-fe-sv, so other front ends get it. |
| G2 | Running registrations without elaborating | The interpreter runs static functions and static initializers (`Interpreter.call(sub, this=None)`), and intrinsics dispatch in fe-sv `rt.py` `FeIntrinsics`. Only `elaborate()` drives it. | A `Scan` entry point (Q-A) that calls each protocol's `declare()` with new `fw_protocol_decl` intrinsics and reads the other registration macros. |
| G3 | IR for APIs and protocols | ir-core has `DataTypeProtocol(methods)` (an interface of methods), `Function.is_task`, `FieldKind.ProtocolPort/ProtocolExport`, and `DataTypeParameterized`. No `implements` list, no interface-class inheritance, nothing for the hub or its registrations. | Z7 (decision 4, §14.3). |
| G4 | Emitting SV classes | zuspec-be-sv's SV IR has `SVClass` (extends, implements, rand fields, virtual tasks and functions), `SVInterfaceClass` and an emitter. Classes take no parameters; types and bodies are strings; `core_to_sv.translate_class` has no path from an API type to `SVInterfaceClass`. | Class parameters (`#(axi4_param_t P = ...)`); API to interface class; enough structure in bodies for the derived classes, which are mostly forwarding and fan-out loops. |

`fw.hdl.gen` does not exist yet (`fw-hdl-fe-sv/python/fw/hdl/` holds only
`fe/`).

### 14.3 Recommendations for the open decisions

| # | Recommendation |
|---|---|
| 3 (names) | Keep the names in §3.1: `fw_protocol`, `` `fw_protocol_utils(C) `` / `` `fw_protocol_param_utils(C) `` (no string; decision 18, §3.2), `fw_protocol_decl` with `api(type, dir)`, `fw_api_type_of #(API)` / `fw_api_type`, `` `fw_bundle_protocol(PROTO) ``, `` `fw_xtor_utils(T, PROTO, ROLE) `` (and `_param_utils`, decision 18; monitors too, with `FW_ROLE_MONITOR`; *the `ROLE` argument is dropped by decision 3's 2026-11-17 amendment*), and for generated APIs `` `fw_protocol_api(PROTO, API, DIR) ``. Enums `fw_proto_dir_e` (`FW_PROTO_REQ`, `FW_PROTO_RSP`) and `fw_proto_role_e` (`FW_ROLE_INITIATOR`, `FW_ROLE_TARGET`, `FW_ROLE_MONITOR`). Queries as in §3.1. |
| 4 | Yes, Z7 in ir-core, specified in the plan as D3 specified Z6. API interface classes map to the existing `DataTypeProtocol`, extended with its base APIs; classes gain an `implements` list. The hub is a new type, `DataTypeProtocolDecl` (APIs with direction, bundle types, transactors per role). A component records the protocol and role of each bundle instance, and its API endpoints and their connections. The `zuspec.kit` YAML and `kits.py` retire in Part B, when nothing reads them. |
| 5 | Yes, as recommended (§4.2). |
| 6 | Yes, as recommended (§4.3). |
| 7 | Yes, as recommended (§5). Socket and endpoint connections go in the netlist and in Z7; they take part in the domain crossing check as bundles do. |
| 8 | Yes, as recommended (§6). It is also a requirement on layer 2 (§14.1, item 4). |
| 9 | User-only in prep. Txn classes have `rand` members and no constraints. Kit-provided legality constraints are decided with the first VIP work (§11). |
| 14 | Yes, port, not copy. Part A ports the derivation rules into `fw.hdl.gen` and the SV runtime pieces std needs (`fw_dir_e`, `fw_field_t`). Part B ports the transactor generator. The rule library moves with the verification side, after prep. |
| 17 | §12, split into Part A and Part B (§14.1). |
| Q-C | As recommended (§3.1): complete lookups are static, from IR; rt-sv's `xtors()` covers the specializations in the image. *(Superseded 2026-11-17: no run-time transactor lookup.)* |

### 14.4 Principle: keep the user's specification to a minimum

*Set 2026-11-16, with the decisions above.* What a kit author or a user
writes is kept to what cannot be derived. Everything that follows from
types, roles or other declarations is derived, by the generators or by
fe-sv, and is never asked for again. Applied in the plan:
- fwd/rev, channel family and payload come from the bundle (§3); there
  are no per-channel attributes;
- attributes only for per-member facts that types cannot carry
  (`fw_opt`, `fw_default`);
- registrations of generated parts (channel APIs, transactors,
  monitors) are in generated code, not written by the user;
- each spec step (K1) checks its API against this: a macro argument,
  a `declare()` call or a query that could be derived is dropped.

**The minimum is the protocol class.** A protocol with no hand-written
API (std rv, for example) still has bundle forms and channel APIs
derived from them. It still needs a class, because bundles, sockets and
transactors name it. So the protocol class is always written, and in
that case it is nearly empty: the registration macro and, for a
parameterized protocol, its `this_t`.
`declare()` has an empty default, and a protocol overrides it only to
register hand-written APIs.

```systemverilog
class fw_rv_proto #(type T = bit) extends fw_protocol;
    typedef fw_rv_proto #(T) this_t;
    `fw_protocol_param_utils(fw_rv_proto)
endclass
```

The name is derived, not written (§3.2).
