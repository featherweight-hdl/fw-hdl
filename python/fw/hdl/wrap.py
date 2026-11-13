"""``fw-hdl wrap``: write a wrapper class for an existing Verilog module.

The module's header is read (:mod:`fw.hdl.rtl_header`) and its pins are
grouped into class ports:

* the clock and reset, by name (or from the body's ``posedge``/``negedge``);
* streams: a valid pin whose name fits one of the kits' pin templates (or the
  XLS suffixes, or a ``valid_`` prefix), with the ready and data pins of the
  same stem. All three, directions agreeing: a ready/valid port. A valid and
  data output with no ready: a valid-only port;
* numbered stems (``req0``, ``req1``, ...) with the same shape: a port array;
* the rest: debug-like outputs left open and inputs tied to 0 (both marked
  TODO), anything else a level port.

The output is SV a person finishes: a parameter class with the module's
parameters, optionally an abstract class holding the ports, the wrapper with
its ``extern_map()`` and a ``facts()`` stub, plus a cosim spec skeleton
(:mod:`fw.hdl.verif.cosim`). Every grouping is reported with its confidence.
An existing output is never overwritten: a different one is written beside it
as ``<file>.new``.
"""
from __future__ import annotations

import dataclasses as dc
import difflib
import os
import re
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .rtl_header import Header, HeaderPort, Value, read_header

HIGH, MEDIUM, LOW = "high", "medium", "low"

#: Names that mark a pin as debug or test only.
_DEBUG = re.compile(r"(^|_)(dbg|debug|test|tst|scan|spare|unused)(_|$|\d)", re.I)
_CLOCKS = re.compile(r"^(clk|clock|aclk|clk_i|i_clk|clk_in|clock_i|.*_clk|.*_clk_i|clk_.*)$",
                     re.I)
_RESET = re.compile(r"(rst|reset)", re.I)
_LOW = re.compile(r"(^n|n(_?i)?$|_b$|_l$|_n_i$)", re.I)

#: SV keywords and fw_component members a port may not be called.
_RESERVED = {"input", "output", "inout", "module", "class", "function", "task", "begin",
             "end", "type", "string", "int", "bit", "logic", "reg", "wire", "byte", "event",
             "new", "this", "super", "null", "build", "connect", "facts", "extern_map",
             "name", "parent", "clock", "reset", "run", "step", "do", "if", "else", "for", "case",
             "default", "assign", "process", "virtual", "static", "local", "protected"}


class WrapError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pin templates
# ---------------------------------------------------------------------------

def _templates() -> Dict[str, List[str]]:
    """role -> ``${ep}`` templates, from the kits (every transactor with valid
    and ready roles), the XLS suffixes, and a few common spellings."""
    out: Dict[str, List[str]] = {"valid": [], "ready": [], "data": []}

    def add(role, t):
        if t not in out[role]:
            out[role].append(t)
    try:
        from . import kits
        for kit in kits.registry().kits.values():
            for tr in kit.transactors:
                if {"valid", "ready"} <= set(tr.pins):
                    for role in ("valid", "ready", "data"):
                        if role in tr.pins:
                            add(role, tr.pins[role])
    except Exception:                       # no kits found: the built-in spellings remain
        pass
    from zuspec.synth.kits.registry import XLS_PIN_STYLE
    for role in ("valid", "ready", "data"):
        add(role, "${ep}" + XLS_PIN_STYLE[role])
    for t in ("${ep}_valid", "valid_${ep}", "${ep}_v"):
        add("valid", t)
    for t in ("${ep}_ready", "ready_${ep}", "${ep}_r"):
        add("ready", t)
    for t in ("${ep}", "${ep}_data", "${ep}_dat", "${ep}_d", "data_${ep}", "${ep}_payload"):
        add("data", t)
    return out


def _regex(t: str) -> re.Pattern:
    a, _, b = t.partition("${ep}")
    return re.compile(f"^{re.escape(a)}(?P<ep>\\w+?){re.escape(b)}$", re.I)


def _fill(t: str, ep: str) -> str:
    return t.replace("${ep}", ep)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

@dc.dataclass
class Group:
    """One class port inferred from module pins."""
    name: str                   # class port name
    kind: str                   # rv | valid | level
    direction: str              # in | out (the module's data direction)
    pins: Dict[str, str]        # role -> pin
    width: int
    confidence: str
    why: str
    ep: str = ""                # the pin stem


@dc.dataclass
class Array:
    """Numbered groups ``<base><n>`` folded into one port array."""
    name: str
    groups: List[Group]
    #: role -> pin with ``{i}`` where the index goes; ``ep`` the same for the stem.
    patterns: Dict[str, str]
    ep: str

    @property
    def first(self) -> Group:
        return self.groups[0]


@dc.dataclass
class Inference:
    header: Header
    clock: Optional[str] = None
    clock_why: str = ""
    reset: Optional[str] = None
    reset_active_low: bool = False
    reset_why: str = ""
    groups: List[Group] = dc.field(default_factory=list)       # not in an array
    arrays: List[Array] = dc.field(default_factory=list)
    ties: List[Tuple[str, int, str]] = dc.field(default_factory=list)
    opens: List[Tuple[str, str]] = dc.field(default_factory=list)
    todo: List[str] = dc.field(default_factory=list)

    @property
    def module(self) -> str:
        return self.header.module


def _port_name(stem: str, taken: set) -> str:
    n = re.sub(r"\W", "_", stem)
    if not re.match(r"[A-Za-z_]", n):
        n = "p_" + n
    if n.lower() in _RESERVED:
        n = n + "_p"
    while n in taken:
        n = n + "_"
    taken.add(n)
    return n


def _clock_reset(inf: Inference, pins: Dict[str, HeaderPort], body: str) -> None:
    ones = [p for p in pins.values() if p.direction == "in" and p.width == 1]
    clk = next((p.name for p in ones if _CLOCKS.match(p.name)), None)
    if clk is not None:
        inf.clock, inf.clock_why = clk, "by name"
    rst = next((p.name for p in ones if _RESET.search(p.name) and p.name != clk), None)
    if rst is not None:
        inf.reset, inf.reset_why = rst, "by name"
        inf.reset_active_low = bool(_LOW.search(rst))
    if (clk is None or rst is None) and body:
        for m in re.finditer(r"@\s*\(\s*posedge\s+(\w+)(?:\s*(?:or|,)\s*(posedge|negedge)\s+(\w+))?",
                             body):
            if clk is None and m.group(1) in pins:
                clk = inf.clock = m.group(1)
                inf.clock_why = "from posedge in the body"
            if rst is None and m.group(3) in pins and m.group(3) != clk:
                rst = inf.reset = m.group(3)
                inf.reset_active_low = m.group(2) == "negedge"
                inf.reset_why = f"from {m.group(2)} in the body"
    if clk is None:
        inf.todo.append("no clock found: add x.clock(\"<pin>\")")
    if rst is None:
        inf.todo.append("no reset found: add x.reset(\"<pin>\", <active_low>)")


def infer(header: Header, body: str = "") -> Inference:
    """Group *header*'s pins into class ports. *body* is the module's source
    text, used only to find the clock and reset when names do not tell."""
    inf = Inference(header)
    pins = {p.name: p for p in header.ports}
    for p in header.ports:
        if p.interface:
            inf.todo.append(f"interface port {p.name}: not supported, map it by hand")
    _clock_reset(inf, pins, body)
    used = {x for x in (inf.clock, inf.reset) if x}
    free = {n: p for n, p in pins.items() if n not in used and not p.interface}
    tmpl = _templates()
    taken: set = set()
    stems: List[Tuple[str, str]] = []           # (ep, valid pin), in pin order
    for p in free.values():
        for t in tmpl["valid"]:
            m = _regex(t).match(p.name)
            if m and m.group("ep") not in [s for s, _ in stems]:
                stems.append((m.group("ep"), p.name))
                break
    groups: List[Group] = []
    claimed: set = set()
    for ep, vpin in stems:
        if vpin in claimed:
            continue
        v = free[vpin]
        ready = [_fill(t, ep) for t in tmpl["ready"] if _fill(t, ep) in free
                 and _fill(t, ep) not in claimed]
        data = [_fill(t, ep) for t in tmpl["data"] if _fill(t, ep) in free
                and _fill(t, ep) not in claimed and _fill(t, ep) != vpin
                and _fill(t, ep) not in ready]
        if not data:
            continue                            # a bare handshake: left to the leftovers
        d = free[data[0]]
        notes = []
        conf = HIGH
        if len(data) > 1:
            conf, notes = MEDIUM, [f"data pin {data[0]} chosen over {', '.join(data[1:])}"]
        if d.direction != v.direction or v.width != 1:
            continue
        if ready:
            r = free[ready[0]]
            if r.direction == v.direction or r.width != 1:
                continue
            g = Group("", "rv", v.direction, {"data": d.name, "valid": vpin, "ready": r.name},
                      d.width, conf, "; ".join(notes or ["data, valid and ready; directions "
                                                         "agree"]), ep)
        elif v.direction == "out":
            g = Group("", "valid", "out", {"data": d.name, "valid": vpin}, d.width, MEDIUM,
                      "; ".join(notes + ["no ready pin: a valid-only output"]), ep)
        else:
            inf.todo.append(f"{vpin}/{d.name}: a valid-only input is not supported; "
                            f"mapped as levels")
            continue
        claimed |= set(g.pins.values())
        groups.append(g)
    inf.arrays, rest = _arrays(groups, taken)
    for g in rest:
        g.name = _port_name(g.ep, taken)
    inf.groups = rest
    for n, p in free.items():
        if n in claimed:
            continue
        if p.direction == "inout":
            inf.todo.append(f"inout pin {n}: not supported, map it by hand")
        elif _DEBUG.search(n) and p.direction == "out":
            inf.opens.append((n, "debug-like output, left open"))
        elif _DEBUG.search(n):
            inf.ties.append((n, 0, "debug-like input, tied to 0"))
        else:
            inf.groups.append(Group(_port_name(n, taken), "level", p.direction, {"data": n},
                                    p.width, LOW, "no protocol matched: a level", n))
    for t in header.type_params:
        inf.todo.append(f"type parameter {t}: not supported, set it by hand")
    return inf


_NUM = re.compile(r"^(?P<base>.*?[A-Za-z])(?P<sep>_?)(?P<n>\d+)$")


def _arrays(groups: List[Group], taken: set) -> Tuple[List[Array], List[Group]]:
    by: Dict[Tuple[str, str], List[Tuple[int, Group]]] = {}
    for g in groups:
        m = _NUM.match(g.ep)
        if m:
            by.setdefault((m.group("base"), m.group("sep")), []).append((int(m.group("n")), g))
    arrays, done = [], set()
    for (base, sep), members in by.items():
        members.sort(key=lambda x: x[0])
        if len(members) < 2 or [n for n, _ in members] != list(range(len(members))):
            continue
        g0 = members[0][1]
        shape = (g0.kind, g0.direction, g0.width, tuple(sorted(g0.pins)))
        if any((g.kind, g.direction, g.width, tuple(sorted(g.pins))) != shape
               for _, g in members):
            continue
        pats = {r: p.replace(g0.ep, base + sep + "{i}", 1) for r, p in g0.pins.items()}
        if any(g.pins[r] != pats[r].replace("{i}", str(n))
               for n, g in members for r in pats):
            continue
        arrays.append(Array(_port_name(base, taken), [g for _, g in members], pats,
                            base + sep + "{i}"))
        done |= {id(g) for _, g in members}
    return arrays, [g for g in groups if id(g) not in done]


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------

def _type(width: int) -> str:
    return "bit" if width == 1 else f"bit [{width - 1}:0]"


def _iface(g: Group) -> str:
    t = _type(g.width)
    if g.kind == "level":
        return f"fw_level_if #({t})" if g.direction == "in" else f"fw_level_set_if #({t})"
    if g.kind == "valid":
        return f"fw_valid_put_if #({t})"
    return f"fw_get_if #({t})" if g.direction == "in" else f"fw_put_if #({t})"


def _sv_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fmt(pattern: str) -> str:
    return f"$sformatf({_sv_str(pattern.replace('{i}', '%0d'))}, i)"


def _map_call(g: Group, port: str, ep: str, pins: Mapping[str, str]) -> str:
    if g.kind == "level":
        return f"x.level({port}, {pins['data']});"
    roles = ("data", "valid", "ready") if g.kind == "rv" else ("data", "valid")
    args = ", ".join(f".{r}({pins[r]})" for r in roles)
    return f"x.{g.kind}({port}, {ep}, {args});"


@dc.dataclass
class Output:
    svh: str
    cosim: str
    report: str


def emit(inf: Inference, files: Sequence[str], out_path: str,
         abstract: Optional[str] = None, cls: Optional[str] = None) -> Output:
    """The wrapper SV, the cosim skeleton and the report for *inf*. *files*
    are the module's sources; the wrapper names them relative to *out_path*."""
    h = inf.header
    mod = h.module
    cls = cls or f"{mod}_rtl"
    pcls = f"{mod}_params"
    base_dir = os.path.dirname(os.path.abspath(out_path))
    rel = [os.path.relpath(os.path.abspath(f), base_dir) for f in files]
    L: List[str] = []
    w = L.append
    w(f"// Wrapper for {mod}, written by fw-hdl wrap from {', '.join(os.path.basename(f) for f in files)}.")
    w("// Finish the TODOs, then keep the file: running fw-hdl wrap again writes")
    w(f"// {os.path.basename(out_path)}.new beside it instead of overwriting it.")
    w("// Include it in a package that imports fw_hdl_pkg and fw_std_pkg, after")
    w("// `include \"fw_hdl_macros.svh\".")
    w("")
    w(f"// {mod}'s parameters, defaults from the module.")
    w(f"class {pcls};")
    for k, v in h.params.items():
        if isinstance(v, int):
            w(f"    longint {k} = {v};")
        else:
            w(f"    string {k} = {_sv_str(str(v))};")
    w("endclass")
    w("")

    def ports_block(indent: str) -> None:
        for a in inf.arrays:
            w(f"{indent}fw_port #({_iface(a.first)}) {a.name}[{len(a.groups)}];")
        for g in inf.groups:
            w(f"{indent}fw_port #({_iface(g)}) {g.name};")

    def ctor(name: str, indent: str, defaults: bool) -> None:
        w(f"{indent}function new(string name, fw_component parent, param_t params = null);")
        arg = "params != null ? params : default_params()" if defaults else "params"
        w(f"{indent}    super.new(name, parent, {arg});")
        w(f"{indent}endfunction")
        if defaults:
            w(f"{indent}static function param_t default_params();")
            w(f"{indent}    param_t p = new;")
            w(f"{indent}    return p;")
            w(f"{indent}endfunction")

    def build(indent: str) -> None:
        w(f"{indent}function void build();")
        for a in inf.arrays:
            w(f"{indent}    foreach ({a.name}[i]) {a.name}[i] = new($sformatf(\"{a.name}[%0d]\", i), this);")
        for g in inf.groups:
            w(f"{indent}    {g.name} = new(\"{g.name}\", this);")
        w(f"{indent}endfunction")

    widths = ", ".join(f"{k}={v}" for k, v in h.params.items())
    if abstract:
        w(f"// What {mod} does, as ports only: realized by {cls}.")
        w(f"virtual class {abstract} extends fw_component_param #({pcls});")
        w(f"    typedef {pcls} param_t;")
        ports_block("    ")
        ctor(abstract, "    ", True)
        build("    ")
        w("endclass")
        w("")
        w(f"class {cls} extends {abstract} implements fw_extern_impl;")
    else:
        w(f"class {cls} extends fw_component_param #({pcls}) implements fw_extern_impl;")
        w(f"    typedef {pcls} param_t;")
        ports_block("    ")
    w(f"    `fw_extern_utils({_sv_str(mod)}, {_sv_str(' '.join(rel))})")
    if abstract:
        ctor(cls, "    ", False)
    else:
        ctor(cls, "    ", True)
        build("    ")
    w("    virtual function void extern_map(fw_extern_map x);")
    if h.params:
        w(f"        // Port types are the widths at the defaults ({widths}).")
    for k, v in h.params.items():
        call = "param" if isinstance(v, int) else "param_str"
        w(f"        x.{call}({_sv_str(k)}, m_params.{k});")
    if inf.clock:
        w(f"        x.clock({_sv_str(inf.clock)});")
    if inf.reset:
        w(f"        x.reset({_sv_str(inf.reset)}{', 1' if inf.reset_active_low else ''});")
    for a in inf.arrays:
        g = a.first
        pins = {r: _fmt(p) for r, p in a.patterns.items()}
        w(f"        foreach ({a.name}[i])   // {g.confidence}: {g.why}")
        w(f"            {_map_call(g, f'{a.name}[i]', _fmt(a.ep), pins)}")
    for g in inf.groups:
        pins = {r: _sv_str(p) for r, p in g.pins.items()}
        w(f"        {_map_call(g, g.name, _sv_str(g.ep), pins)}   // {g.confidence}: {g.why}")
    for pin, v, why in inf.ties:
        w(f"        x.tie({_sv_str(pin)}, {v});   // TODO: {why}")
    for pin, why in inf.opens:
        w(f"        x.open({_sv_str(pin)});   // TODO: {why}")
    for t in inf.todo:
        w(f"        // TODO: {t}")
    w("    endfunction")
    ins = [f"{a.name}[0]" for a in inf.arrays if a.first.kind != "level" and a.first.direction == "in"] + \
        [g.name for g in inf.groups if g.kind != "level" and g.direction == "in"]
    outs = [f"{a.name}[0]" for a in inf.arrays if a.first.kind != "level" and a.first.direction == "out"] + \
        [g.name for g in inf.groups if g.kind != "level" and g.direction == "out"]
    w("    virtual function void facts(fw_facts f);")
    w("        // TODO: what the datasheet or a measurement says, for example:")
    for i in ins[:3]:
        for o in outs[:3]:
            w(f"        // f.latency({i}, {o}, .fixed(TODO));")
    for i in ins[:3]:
        w(f"        // f.ii({i}, TODO);")
    w("    endfunction")
    w("endclass")
    svh = "\n".join(L) + "\n"
    # The cosim skeleton sits beside the wrapper, so the same relative paths serve.
    return Output(svh, _cosim(inf, rel, abstract), report(inf))


def _cosim(inf: Inference, files: List[str], abstract: Optional[str]) -> str:
    import yaml
    ports: Dict[str, dict] = {}
    for a in inf.arrays:
        for i, g in enumerate(a.groups):
            ports[f"{a.name}[{i}]"] = dict(g.pins)
    for g in inf.groups:
        if g.kind != "level":
            ports[g.name] = dict(g.pins)
    target = {"name": inf.module, "module": inf.module, "files": files}
    if inf.header.params:
        target["params"] = dict(inf.header.params)
    if inf.clock:
        target["clock"] = inf.clock
    if inf.reset:
        target["reset"] = {"port": inf.reset, "active_low": inf.reset_active_low}
    target["ports"] = ports
    head = (f"# Cosim skeleton for {inf.module} (python -m fw.hdl.verif.cosim).\n"
            f"# TODO: set `class` to the library class {inf.module} realizes (one with a\n"
            f"# cosim driver) and its `params`, and rename the port keys to that class's\n"
            f"# ports.\n")
    body = {"class": abstract or "TODO", "params": {}, "targets": [target]}
    return head + yaml.safe_dump(body, sort_keys=False, default_flow_style=None)


def report(inf: Inference) -> str:
    L = [f"{inf.module}: {len(inf.header.ports)} pins"]
    if inf.clock:
        L.append(f"  clock  {inf.clock}  ({inf.clock_why})")
    if inf.reset:
        L.append(f"  reset  {inf.reset}  active-{'low' if inf.reset_active_low else 'high'} "
                 f"({inf.reset_why})")
    for a in inf.arrays:
        g = a.first
        L.append(f"  {g.kind:<5}  {a.name}[{len(a.groups)}]  "
                 f"{'/'.join(a.patterns[r] for r in sorted(a.patterns))}  "
                 f"{g.confidence}: {g.why}")
    for g in inf.groups:
        L.append(f"  {g.kind:<5}  {g.name}  {'/'.join(g.pins[r] for r in sorted(g.pins))}  "
                 f"{g.confidence}: {g.why}")
    for pin, v, why in inf.ties:
        L.append(f"  tie    {pin} = {v}  low: {why}")
    for pin, why in inf.opens:
        L.append(f"  open   {pin}  low: {why}")
    for t in inf.todo:
        L.append(f"  TODO   {t}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def write_new(path: str, text: str) -> Tuple[bool, str]:
    """Write *text* to *path* unless a different file is there; then write
    ``<path>.new`` and return ``(False, diff)``."""
    if os.path.exists(path):
        old = open(path).read()
        if old == text:
            return True, ""
        with open(path + ".new", "w") as f:
            f.write(text)
        diff = "".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                            path, path + ".new"))
        return False, diff
    with open(path, "w") as f:
        f.write(text)
    return True, ""


def cosim_path(out_path: str) -> str:
    root, _ = os.path.splitext(out_path)
    return root + ".cosim.yaml"


def wrap(files: Sequence[str], module: str, out_path: str, abstract: Optional[str] = None,
         cls: Optional[str] = None, params: Optional[Mapping[str, Value]] = None,
         include_dirs: Sequence[str] = (), defines: Optional[Mapping[str, str]] = None) -> Output:
    """Read *module* from *files* and return what :func:`emit` writes."""
    h = read_header(files, module, params, defines, include_dirs)
    body = ""
    for f in files:
        text = open(f).read()
        m = re.search(rf"\bmodule\s+{re.escape(module)}\b.*?\bendmodule\b", text, re.S)
        if m:
            body = m.group(0)
            break
    return emit(infer(h, body), files, out_path, abstract, cls)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``fw-hdl wrap <files> --module M [--abstract NAME] [--class NAME] -o out.svh``."""
    import argparse
    import sys
    from .rtl_header import HeaderError
    p = argparse.ArgumentParser(prog="fw-hdl wrap", description=__doc__.split("\n\n")[0])
    p.add_argument("files", nargs="+")
    p.add_argument("--module", required=True)
    p.add_argument("--abstract", help="also write an abstract class holding the ports")
    p.add_argument("--class", dest="cls", help="the wrapper's name (default <module>_rtl)")
    p.add_argument("-o", "--output", required=True, help="the wrapper .svh")
    p.add_argument("--report", help="also write the inference report here")
    p.add_argument("-I", dest="incdirs", action="append", default=[])
    p.add_argument("-D", dest="defines", action="append", default=[])
    a = p.parse_args(argv)
    defines = dict((d.split("=", 1) + ["1"])[:2] for d in a.defines)
    try:
        out = wrap(a.files, a.module, a.output, a.abstract, a.cls, None, a.incdirs, defines)
    except HeaderError as e:
        print(f"fw-hdl wrap: {e}", file=sys.stderr)
        return 2
    print(out.report, end="")
    if a.report:
        with open(a.report, "w") as f:
            f.write(out.report)
    status = 0
    for path, text in ((a.output, out.svh), (cosim_path(a.output), out.cosim)):
        ok, diff = write_new(path, text)
        if ok:
            print(f"wrote {path}")
        else:
            print(f"{path} exists and differs: wrote {path}.new\n{diff}", end="")
            status = 1
    return status
