# Featherweight-HDL API Kit

Use this skill to define a featherweight-HDL **API**: the class-based contract by
which fw components communicate. This is the lower of the two communication
layers:

- **API** (this skill) — pure class-level interface: an `interface class` plus
  the macro that lets a component *provide* it. No signals, no RTL.
- **Protocol** (see `fw-proto-kit`) — an API *plus* transactors that bridge it to
  a signal-level interface (`*_xtor_if`, `*_xtor_core`, integration modules).

Define the API first; a protocol is built on top of a finished API.

## What an API kit contains

Two artifacts, always:

1. **The interface-class API** — a pure-virtual `interface class <proto>_if`
   declaring the task/function signatures. Consumers (ports) are typed on this;
   it is the stable contract.
2. **The implementation-template macro** — `` `FW_<PROTO>_IMP `` — used inside a
   providing component to stamp out a proxy that is at once the **export**
   (extends `fw_export #(<proto>_if#())`) and the **imp** (implements
   `<proto>_if`), redirecting each API call to a local method, plus a member of
   that type.

A consumer calls the API through an `fw_port #(<proto>_if#())`; a provider
publishes an implementation with the macro. The port binds to the export with
`port.connect(export)` and resolves the implementation lazily via `get_if()`.
(`fw_component`, `fw_port`, `fw_export` come from `fw_pkg` — do not redefine
them.)

## How users apply this skill — two modes

**Mode A — the interface class already exists.** The user hands you a finished
`interface class <proto>_if`. Your job: generate the matching
`` `FW_<PROTO>_IMP `` macro (and nothing else). Read every `pure virtual`
method and emit one redirect per method, threading every type parameter through
as a positional macro argument.

**Mode B — informal specification.** The user describes the methods and
signatures in prose (e.g. "a `send` task that takes a `T`" or "a blocking
`call` that takes a request and returns a response"). Your job: generate **both**
the interface class and the macro. Pick `pure virtual task` for anything that
may consume time or block, `pure virtual function` for immediate/returning
calls. Confirm the protocol name and type parameters with the user only if
genuinely ambiguous; otherwise choose sensible names and state them.

In both modes, finish by showing a minimal provider/consumer usage snippet so
the user can see the wiring, and offer to drop it into a `tests/<name>/` test
modeled on `tests/intf_pc/` to prove it compiles.

## Conventions (must follow)

- **Interface class name:** `<proto>_if`. Methods are `pure virtual task`
  (blocking / time-consuming) or `pure virtual function` (immediate). API
  classes may or may not be parameterized.
- **Parameter order — outputs (returns) FIRST.** A method's `output` (and
  `inout`) arguments are listed *before* its `input` arguments, i.e. the
  response/return values lead. A request/response call is therefore
  `call(output Trsp rsp, input Treq req)`, a protocol transfer is
  `xfer(output RSP rsp, input REQ req)` — read it as "rsp = xfer(req)". Order the
  method body, the macro redirect, and the `<NAME>_<method>` implementation
  identically. (Pure one-way calls have a single argument and are unaffected.)
- **Macro name:** `` `FW_<PROTO>_IMP `` (upper-case `<PROTO>`).
- **Macro signature:** every interface-class type parameter becomes a leading
  positional macro argument, followed by `IMP, NAME`:
  `` `FW_<PROTO>_IMP(<TYPE_PARAMS...>, IMP, NAME) ``.
  - `IMP` — the type of the implementing component (usually the enclosing class).
  - `NAME` — the export member name; also the per-method redirect prefix.
- **The stamped proxy** must:
  - `extends fw_export #(<proto>_if #(<params>))` **and**
    `implements <proto>_if #(<params>)`;
  - in `new(IMP imp)`, call `super.new(`"NAME`", imp, this)` — registering
    itself (`this`) as the export's implementation and `imp` as its hierarchy
    **parent** — then store `m_imp = imp`;
  - redirect each API method `m(args)` to `m_imp.NAME``_m(args)`.
- **Method-redirect convention:** the providing component implements one method
  per API call named `<NAME>_<method>`. The `<NAME>_` prefix lets one component
  expose several exports of the same API without clashes; the `_<method>` suffix
  scales to multi-method APIs.
- **Provider usage:** `NAME = new(this);` in `build()`.
- **Consumer usage:** hold `fw_port #(<proto>_if#())`; call
  `port.get_if().<method>(...)` (resolve once into a local handle if calling
  repeatedly).
- **Comments (required):** a header comment on the interface class describing
  the type parameters; a comment on every method; a header comment on the macro
  describing its arguments and the `<NAME>_<method>` contract.

## Production placement

- The interface class goes in its **own `.svh`** (`<proto>_if.svh`), `` `include ``d
  by the package.
- The macro goes in the package's **`<pkg>_macros.svh`**.
- (In `tests/intf_pc/` both are inlined in the testbench because they are test
  scaffolding, not library features — do that only for throwaway tests.)

## Worked example (from `tests/intf_pc/`)

### 1. Interface-class API

```systemverilog
// The "send" interface protocol -- the pure-virtual API.
// T: the payload type carried by send().
interface class fw_send_if #(type T);
    // Hand one payload of type T to the implementation.
    pure virtual task send(input T t);
endclass
```

### 2. Implementation-template macro

```systemverilog
// `FW_SEND_IMP(T, IMP, NAME) -- stamp a send-API provider inside a class.
//   T    : payload type
//   IMP  : implementing component type (pass its own type; new with `this`)
//   NAME : export member name; implement send() as <NAME>_send()
`define FW_SEND_IMP(T, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(fw_send_if #(T)) \
            implements fw_send_if #(T); \
        local IMP m_imp; \
        function new(IMP imp); \
            super.new(`"NAME`", imp, this); \
            m_imp = imp; \
        endfunction \
        virtual task send(input T t); \
            m_imp.NAME``_send(t); \
        endtask \
    endclass \
    NAME``_imp_t NAME
```

### 3. Provider (supplies the API)

```systemverilog
class consumer extends fw_component;
    data_t received[$];

    `FW_SEND_IMP(data_t, consumer, in);          // export member `in`

    function new(string name, fw_component parent); super.new(name, parent); endfunction

    function void build();
        in = new(this);                          // single new, hand it `this`
    endfunction

    virtual task in_send(input data_t t);        // <NAME>_send implementation
        received.push_back(t);
    endtask
endclass
```

### 4. Consumer (calls the API) and connection

```systemverilog
class producer extends fw_component;
    fw_port #(fw_send_if #(data_t)) out;
    ...
    virtual task run();
        fw_send_if #(data_t) api = out.get_if();
        api.send(v);
    endtask
endclass

// in the parent component's connect():
prod.out.connect(cons.in);                       // port (consumer) -> export (provider)
```

## Multi-method / multi-parameter APIs

When the interface class has more than one method, emit one redirect per method,
each to its own `<NAME>_<method>`:

```systemverilog
interface class fw_reqrsp_if #(type Treq, type Trsp);
    // outputs (returns) lead: rsp = call(req).
    pure virtual task call(output Trsp rsp, input Treq req);
endclass

// every type parameter is a positional macro argument:
`define FW_REQRSP_IMP(TREQ, TRSP, IMP, NAME) \
    class NAME``_imp_t extends fw_export #(fw_reqrsp_if #(TREQ, TRSP)) \
            implements fw_reqrsp_if #(TREQ, TRSP); \
        local IMP m_imp; \
        function new(IMP imp); super.new(`"NAME`", imp, this); m_imp = imp; endfunction \
        virtual task call(output TRSP rsp, input TREQ req); \
            m_imp.NAME``_call(rsp, req); \
        endtask \
    endclass \
    NAME``_imp_t NAME
```

## Procedure

1. Determine the mode: is the interface class supplied (Mode A) or specified
   informally (Mode B)?
2. (Mode B only) Write the `interface class <proto>_if`: choose the protocol
   name and type parameters, declare each method `pure virtual task`/`function`,
   comment the params and every method.
3. Write `` `FW_<PROTO>_IMP ``: one positional macro arg per type parameter, then
   `IMP, NAME`; proxy `extends fw_export #(<proto>_if#())` and `implements
   <proto>_if#()`; `super.new(`"NAME`", imp, this)`; one
   `m_imp.NAME``_<method>(...)` redirect per method; trailing `NAME``_imp_t NAME`
   member.
4. Place artifacts: production → interface class in its own `.svh` (included in
   the package), macro in `<pkg>_macros.svh`. Throwaway test → inline.
5. Show provider + consumer + `connect()` usage. Offer a `tests/<name>/` test
   modeled on `tests/intf_pc/` to confirm it compiles.

## Checking / Validation

Run these checks after defining or reviewing an API kit. They are ordered most-
to least important; the first is mandatory.

1. **An implementation macro exists for the API.** Every API MUST ship a
   `` `FW_<PROTO>_IMP `` macro. An interface class with no macro is an incomplete
   API kit -- flag it and add the macro. (Grep: for each `interface class
   <proto>_if`, there must be a matching `` `define FW_<PROTO>_IMP ``.)
2. **The macro covers every method.** The macro emits exactly one redirect per
   `pure virtual` method of the interface class, each forwarding to
   `m_imp.NAME``_<method>`. A method with no redirect means implementors cannot
   provide it through the macro.
3. **Every type parameter is threaded through.** Each `type` parameter of the
   interface class appears as a positional macro argument and is passed to both
   `fw_export #(<proto>_if #(...))` and `implements <proto>_if #(...)`.
4. **No hand-rolled implementations.** No class outside the macro should
   `implements <proto>_if` or `extends fw_export #(<proto>_if ...)`. Grep for
   `implements <proto>_if` and confirm every hit is inside the macro body; any
   other hit is a hand-rolled proxy that must be replaced with the macro.
   (Transactor bridges that *consume* the API hold an `fw_port` and are fine;
   the check is only for *providers*.)
5. **The macro is registered in the right place.** Production: the macro lives
   in `<pkg>_macros.svh`; the interface class in its own `.svh` included in the
   package. Throwaway test: both inlined in the testbench.
6. **Comments present.** Header/param comment on the interface class and the
   macro; a comment on every method.

## Checklist

- [ ] `interface class <proto>_if` with `pure virtual` methods, all commented.
- [ ] `` `FW_<PROTO>_IMP `` with every type param as a positional arg.
- [ ] Proxy `extends fw_export #(...)` **and** `implements <proto>_if #(...)`.
- [ ] `super.new(`"NAME`", imp, this)` then `m_imp = imp`.
- [ ] One `m_imp.NAME``_<method>()` redirect per API method.
- [ ] Trailing `NAME``_imp_t NAME` member; provider does `NAME = new(this)`.
- [ ] Implementing component defines each `<NAME>_<method>`.
- [ ] Header/param/method comments present on both artifacts.
