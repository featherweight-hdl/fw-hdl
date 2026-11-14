# Value ports

`src/sync` (in `fw_hdl_pkg`): ports that carry values between components, field by
field, with sync or comb meaning. The model is in {doc}`../methodology/sync-logic`.

## Holders

A **holder** (`fw_sig_holder`) owns the values of one channel. Each field has:
- `cur`, what readers see, and `nxt`, what writers write;
- a flag, **sync** (default) or **comb**;
- an optional reset-force value, read by the peer while the holder's reset domain
  (`set_reset(fw_reset_domain_if)`; null means never in reset) is in reset.

A sync write goes to `nxt`; `commit()` copies `nxt` to `cur`. `nxt` keeps its value, so a
field nobody writes holds. A comb write goes to both at once.

| Holder | Fields | API |
|---|---|---|
| `fw_rv_sig #(T)` | `valid`, `ready`, `data` (T) | `set_valid/ready/data(v)`, `get_valid/ready/data()` |
| `fw_sig #(T)` | one value | `set(v)`, `get()` (peer read), `get_own()`, `set_reset_force(v)` |

For `fw_rv_sig`, `valid` and `ready` are forced to 0 in reset; `data` is not forced.

### Field semantics

`set_comb(spec)` marks fields comb. `spec` is a comma list of `f` or `*`, either of them
optionally prefixed with the holder's own name (`valid`, `*`, `ar.valid`, `ar.*`); spaces
are ignored. Nothing turns a comb field back to sync. `check_comb(spec, out err)` returns 1
and a message instead of stopping: an unknown field (`no field "x" in holder "ar"`), a
prefix that names another holder, an empty list, or a frozen holder. `set_comb` stops with
`fw-hdl: <holder>: set_comb(...): <err>`.

Call `set_comb` from `build()`. The roots `freeze()` every holder after build; a later
change is an error.

### Declaring comb fields: `fw_sp_comb`

Instead of calling `set_comb`, list the comb fields on the port member:

```systemverilog
class c_mid extends fw_component;
    (* fw_sp_comb = "valid,data" *) fw_rv_sp_out #(byte_t) o;   // a view
    (* fw_sp_comb = "ar.*,w.valid" *) axi4_sub_sp #(P) s;        // a port of channels
endclass
```

| Member type | Items | Becomes |
|---|---|---|
| a view (`fw_sync_port`) | `f`, `*`, `<member>.f` | `m.holder().set_comb(..)` (prefix dropped) |
| a port with its own `set_comb` (fw_proto `fw_sp_base`) | `ch.f`, `ch.*` | `m.set_comb(..)` |

The `fw_sp_comb` weaver (`packages/fw-hdl/python/fw/hdl/weave/sp_comb.py`) generates the
calls. Add it to the sv-weave config next to the binding:

```yaml
binding: fw.hdl.weave.binding:FwHdlBinding
weavers:
  - name: fw.hdl.weave.sp_comb:SpCombWeaver
```

For each class that declares such a member, `<pkg>_woven` gets a class extending
`fw_hdl_pkg::fw_sp_comb`. Its `apply(c)` casts `c` to the class with `$cast` and makes the
calls. `fw_sync_kernel::freeze_tree` applies these classes to the whole tree at the end of
build. That is before `connect()`/`link()` and before freeze. A subclass also matches its
base's `$cast`, so it inherits the base's declarations. A `set_comb` call in `build()` can
add more fields; it cannot clear a declared one.

Weave-time errors (`fw_sp_comb: <class>.<member>: ...`):
- an empty list
- a member that is `local`, `protected` or `static`
- a view item whose prefix is not the member's name
- `no channel "x" in <port>`. The port's channels are its `fw_sig_holder` members.
- a member type that is not a struct port

Field names are checked at run time by `check_comb`, which is fatal. Channel names are also
checked at run time when the port class is not in the woven sources, for example a class
that another weave run generated.

Limits:
- The member must be public.
- A generic class needs a specialization in the woven sources, for example a `typedef` in
  the package. Without one, the weaver generates nothing for that class.

### Pin shells: `fw_pins`

When `fw.hdl.sync.Emit` lowers a class with fw_proto role-port members, each role port
becomes `<port>_<ch>valid`, `<port>_<ch>ready` and a packed `<port>_<ch>data`. To get
AMBA-named pins as well, put a prefix on the member:

```systemverilog
class axi_pass #(axi4_param_t P = AXI4_PARAM_DEFAULT) extends fw_component;
    (* fw_pins = "s_axi_" *) axi4_sub_sp #(P) s;
    (* fw_pins = "m_axi_" *) axi4_mgr_sp #(P) m;
endclass
```

Emit then also writes `<var>_pins.sv` beside `<var>.sv` (`python/fw/hdl/emit/pins.py`,
`pin_shell`). It is a module that instantiates the lowered top and has, per channel,
`<prefix><ch>valid`, `<prefix><ch>ready` and one pin per member of the channel's payload
struct, `<prefix><ch><member>` (for example `s_axi_awaddr`), sliced from the packed data.
A struct member marked `(* fw_opt = "NAME" *)` is absent when field `NAME` of the
declaring class's parameter is 0: an absent input is tied to 0, an absent output is
dropped. Other ports, clock and reset keep their names.

Errors: `fw_pins` on a member that is not a role port.

Limits: the preset is a prefix only (no upper-case or rename rules); clock and reset are not
renamed (no `aclk`/`aresetn`).

## Views

A **view** is one component's end of a channel. It sets which fields the end drives and
reads, and its reads are the peer reads (reset-forced).

| View | Drives | Base |
|---|---|---|
| `fw_rv_sp_out #(T)` | `valid`, `data` | `fw_sync_port`, role FWD |
| `fw_rv_sp_in #(T)` | `ready` | `fw_sync_port`, role BWD |

`new(sig = null, name = "", owner = null)`: with no holder the view makes its own, named
`name`. The owner registers the view (`add_sync_port`). Arrays of ports are unpacked
arrays of views (named `o[k]`).

## Connecting

- `out.connect(in)` or `in.connect(out)` joins two ends on one `fw_sync_net`. The net
  keeps the holder of the end `connect` was called on (so the holder's name is that end's
  name), ORs comb flags, and keeps a reset domain that is set.
- `inner.connect_up(outer)` passes a port up the hierarchy: same role, and `outer`'s owner
  must be the inner owner's parent. `outer` becomes a *through* end; it drives and reads
  nothing.
- `set_optional()` lets an input go undriven.

After `connect()` the root checks every net once (`fw_sync_conn::check_tree`):
- `field "valid" of "o" has two drivers: top.a.o and top.b.o`
- `top.c.i: input field "valid" is not driven (connect it, or set_optional())`

## Pin bridges

`fw_rv_pin #(T)` joins a value port to module pins. Instance the module beside
`fw_root` and connect by name in the tree's `connect()`:

| Module | Pins are | In `connect()` |
|---|---|---|
| `fw_rv_pin_in #(T, NAME)` | the producer: `valid`, `data` in, `ready` out | `fw_rv_pin #(T)::find(NAME).connect_in(c.in)` |
| `fw_rv_pin_out #(T, NAME)` | the consumer | `fw_rv_pin #(T)::find(NAME).connect_out(c.out)` |

A changed input pin of a comb field is written and its domain settled at once
(`settle_now`); an input of a sync field is written to `nxt`. Outputs come from `cur` for
comb fields (blocking) and from `nxt` for sync fields (nonblocking). Both are
reset-forced. The bridge makes a fresh view per tree, so `fw_root` can rebuild the tree
at each reset release.

## Protocol ports (fw_proto)

A protocol port (`fw_sp_base`) can hold one holder per channel (`m_sync`, named by
channel). `sync(ch)` finds one; `set_comb("aw.*, b.ready")` routes each `ch.f` item to its
channel's holder (`no channel "x" in port "m" (write ch.f or ch.*)` otherwise). `link()`
shares the manager side's holders with the subordinate side, keeping the subordinate's
comb flags. A port with no holders behaves as before. The fw_proto bundle weaver gives each
generated role port (`<proto>_<role>_sp`) one typed holder per `fw_rv_ch` channel, named
by the channel; for AXI4, `axi4_mgr_sp`/`axi4_sub_sp #(P)` have `fw_rv_sig` channels `aw`,
`w`, `b`, `ar`, `r` (`s.aw.set_data(v)`, `s.aw.get_valid()`).

Not yet: protocol-port holders are not views, so they are not in the connection check or
the kernel's domains, and `bind_inner()` does not share them.
