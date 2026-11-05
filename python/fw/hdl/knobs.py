"""Knob files: one source, many schedules.

A knob file decides what the source does not: where registers go, how deep
buffers are, each block's schedule, and how storage is bound. It is YAML,
validated against ``schema/knobs.schema.json``, and merges other knob files
through ``base:`` (dicts merge, lists and scalars replace, later wins).

Every resolved value remembers the file and line it came from, so an error in
a deep ``base:`` chain points at the line to change.

    k = load("knobs/k2.yaml")
    k.block_options("rt_table")        # default merged with blocks.rt_table
    k.codegen_args("rt_table")         # the codegen_main flags for it
    k.codegen_options()                # per-module options for synth.xls.Codegen
    k.emit_sv_pkg()                    # <top>_knobs_pkg with the rtl: localparams
    k.resolved()                       # the merged dict, for <top>.knobs.json
"""
from __future__ import annotations

import copy
import dataclasses as dc
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "knobs.schema.json"
FORMAT = "fw-hdl.knobs"
VERSION = 1

Path_ = Tuple[str, ...]


class KnobError(Exception):
    pass


@dc.dataclass(frozen=True)
class Origin:
    file: str
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


# ---------------------------------------------------------------------------
# Loading with origins
# ---------------------------------------------------------------------------
def _to_py(node, file: str, path: Path_, origins: Dict[Path_, Origin]):
    origins[path] = Origin(file, node.start_mark.line + 1)
    if isinstance(node, yaml.MappingNode):
        out = {}
        for k, v in node.value:
            key = yaml.safe_load(yaml.serialize(k)) if not isinstance(k, yaml.ScalarNode) \
                else k.value
            key = str(key)
            if key in out:
                raise KnobError(f"{file}:{k.start_mark.line + 1}: key {key!r} given twice")
            out[key] = _to_py(v, file, path + (key,), origins)
        return out
    if isinstance(node, yaml.SequenceNode):
        return [_to_py(v, file, path + (str(i),), origins) for i, v in enumerate(node.value)]
    # A scalar: let the safe loader type it (int, float, bool, null, str).
    return yaml.safe_load(yaml.serialize(node))


def _read(path: Path) -> Tuple[dict, Dict[Path_, Origin]]:
    try:
        text = path.read_text()
    except OSError as e:
        raise KnobError(f"cannot read knob file {path}: {e.strerror}") from None
    try:
        node = yaml.compose(text)
    except yaml.YAMLError as e:
        raise KnobError(f"{path}: {e}") from None
    origins: Dict[Path_, Origin] = {}
    if node is None:
        return {}, origins
    data = _to_py(node, str(path), (), origins)
    if not isinstance(data, dict):
        raise KnobError(f"{path}:1: a knob file is a mapping")
    return data, origins


_SCHEMA = None


def schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.loads(SCHEMA_PATH.read_text())
    return _SCHEMA


def _validate(data: dict, origins: Dict[Path_, Origin], fallback: str):
    import jsonschema
    v = jsonschema.Draft202012Validator(schema())
    errs = sorted(v.iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))
    if not errs:
        return
    msgs = []
    for e in errs:
        p = tuple(str(x) for x in e.absolute_path)
        where = None
        for n in range(len(p), -1, -1):
            if p[:n] in origins:
                where = origins[p[:n]]
                break
        loc = str(where) if where else fallback
        key = ".".join(p) or "<top>"
        msgs.append(f"{loc}: {key}: {e.message}")
    raise KnobError("\n".join(msgs))


def _merge(dst: dict, dorig: Dict[Path_, Origin], src: dict, sorig: Dict[Path_, Origin],
           path: Path_ = ()):
    for k, v in src.items():
        p = path + (k,)
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            dorig[p] = sorig.get(p, dorig.get(p))
            _merge(dst[k], dorig, v, sorig, p)
            continue
        dst[k] = copy.deepcopy(v)
        for q in [q for q in dorig if q[:len(p)] == p]:
            del dorig[q]
        for q, o in sorig.items():
            if q[:len(p)] == p:
                dorig[q] = o


def _load(path: Path, stack: Tuple[Path, ...]) -> Tuple[dict, Dict[Path_, Origin], List[str]]:
    path = path.resolve()
    if path in stack:
        chain = " -> ".join(str(p) for p in stack + (path,))
        raise KnobError(f"base: cycle: {chain}")
    data, origins = _read(path)
    _validate(data, origins, str(path))
    bases = data.pop("base", [])
    bases = [bases] if isinstance(bases, str) else bases
    merged: dict = {}
    morig: Dict[Path_, Origin] = {}
    files: List[str] = []
    for b in bases:
        bd, bo, bf = _load(path.parent / b, stack + (path,))
        _merge(merged, morig, bd, bo)
        files += [f for f in bf if f not in files]
    origins = {p: o for p, o in origins.items() if p[:1] != ("base",)}
    _merge(merged, morig, data, origins)
    files.append(str(path))
    return merged, morig, files


def from_resolved(path) -> "Knobs":
    """Knobs from a ``<top>.knobs.json`` that fw.hdl.knobs.Resolve wrote."""
    d = json.loads(Path(path).read_text())
    if d.get("format") != FORMAT:
        raise KnobError(f"{path}: not a resolved knob file (format {d.get('format')!r})")
    return Knobs(d["knobs"], {}, list(d.get("files", [])))


def load(path) -> "Knobs":
    data, origins, files = _load(Path(path), ())
    _validate(data, origins, str(path))
    k = Knobs(data, origins, files)
    k._check()
    return k


# ---------------------------------------------------------------------------
# The resolved knobs
# ---------------------------------------------------------------------------
_CG_FLAGS = ("pipeline_stages", "clock_period_ps", "delay_model", "worst_case_throughput",
             "flop_inputs", "flop_outputs", "flop_inputs_kind", "flop_outputs_kind",
             "reset", "reset_active_low")


@dc.dataclass
class Knobs:
    data: dict
    origins: Dict[Path_, Origin]
    files: List[str]

    # -- lookup --------------------------------------------------------
    def get(self, *path, default=None):
        d = self.data
        for p in path:
            if not isinstance(d, dict) or p not in d:
                return default
            d = d[p]
        return d

    def origin(self, *path) -> Optional[Origin]:
        p = tuple(path)
        for n in range(len(p), -1, -1):
            if p[:n] in self.origins:
                return self.origins[p[:n]]
        return None

    def where(self, *path) -> str:
        o = self.origin(*path)
        return str(o) if o else (self.files[-1] if self.files else "<knobs>")

    @property
    def top(self) -> Optional[str]:
        return self.get("design", "top")

    def xls_blocks(self) -> List[str]:
        return list(self.get("design", "xls", default=[]) or [])

    def extern_blocks(self) -> Dict[str, dict]:
        """``design.extern``: class -> ``{signature, module, files}``, with
        relative paths resolved against the knob file that names them."""
        out = {}
        for cls, e in (self.get("design", "extern", default={}) or {}).items():
            o = self.origin("design", "extern", cls)
            base = Path(o.file).parent if o else Path(".")
            res = lambda f: str((base / f).resolve()) if not os.path.isabs(f) else f  # noqa: E731
            out[cls] = {**e, "signature": res(e["signature"]),
                        "files": [res(f) for f in e.get("files", [])]}
        return out

    def filesets(self) -> Dict[str, List[str]]:
        """``design.filesets``: name -> files, with relative paths resolved
        against the knob file that names them."""
        out = {}
        for name, fs in (self.get("design", "filesets", default={}) or {}).items():
            o = self.origin("design", "filesets", name)
            base = Path(o.file).parent if o else Path(".")
            out[name] = [f if os.path.isabs(f) else str((base / f).resolve()) for f in fs]
        return out

    def facts_files(self) -> List[str]:
        """``design.facts``: sidecar files of characterization facts, with
        relative paths resolved against the knob file that names them."""
        fs = self.get("design", "facts", default=[]) or []
        o = self.origin("design", "facts")
        base = Path(o.file).parent if o else Path(".")
        return [f if os.path.isabs(f) else str((base / f).resolve()) for f in fs]

    def block_options(self, block: str) -> dict:
        """xls.default merged with xls.blocks.<block> (block wins)."""
        out = dict(self.get("xls", "default", default={}) or {})
        out.update(self.get("xls", "blocks", block, default={}) or {})
        return out

    def scheduler_period_ps(self, block: str) -> Optional[int]:
        """The clock period handed to the scheduler: clock_period_ps times the
        delay-model scale."""
        p = self.block_options(block).get("clock_period_ps")
        if p is None:
            return None
        return int(round(p * float(self.get("delay", "scale", default=1.0))))

    def codegen_args(self, block: str) -> List[str]:
        """codegen_main flags for *block* (module name and I/O paths are the
        caller's)."""
        o = self.block_options(block)
        args = []
        for k in _CG_FLAGS:
            if k not in o:
                continue
            v = self.scheduler_period_ps(block) if k == "clock_period_ps" else o[k]
            if isinstance(v, bool):
                v = "true" if v else "false"
            args.append(f"--{k}={v}")
        if "delay_model" not in o and self.get("delay", "model"):
            args.append(f"--delay_model={self.get('delay', 'model')}")
        if o.get("io_constraints"):
            args.append("--io_constraints=" + ",".join(o["io_constraints"]))
        args += list(o.get("extra_args", []))
        return args

    def codegen_module_options(self, block: str) -> dict:
        """*block*'s entry in an ``xlsCodegenOptions`` file (synth.xls.Codegen):
        the task parameters it overrides, and the rest as extra arguments."""
        o = self.block_options(block)
        out: dict = {}
        for k in ("delay_model", "reset", "reset_active_low"):
            if k in o:
                out[k] = o[k]
        if "delay_model" not in o and self.get("delay", "model"):
            out["delay_model"] = self.get("delay", "model")
        args: List[str] = []
        if "clock_period_ps" in o:
            out["clock_period_ps"] = self.scheduler_period_ps(block)
            if "pipeline_stages" in o:      # Codegen passes one of the two; XLS takes both
                args.append(f"--pipeline_stages={o['pipeline_stages']}")
        elif "pipeline_stages" in o:
            out["pipeline_stages"] = o["pipeline_stages"]
        for k in ("worst_case_throughput", "flop_inputs", "flop_outputs", "flop_inputs_kind",
                  "flop_outputs_kind"):
            if k in o:
                v = o[k]
                args.append(f"--{k}={('true' if v else 'false') if isinstance(v, bool) else v}")
        from .check.contracts import io_constraints
        ioc = list(o.get("io_constraints", [])) + io_constraints(self, block)
        if ioc:
            args.append("--io_constraints=" + ",".join(ioc))
        args += list(o.get("extra_args", []))
        if args:
            out["args"] = args
        return out

    def codegen_options(self) -> dict:
        """The ``xlsCodegenOptions`` document for every design.xls block,
        keyed by generated module name."""
        from .spl_flow import module_name
        return {"format": "xls.codegen-options",
                "modules": {module_name(b): self.codegen_module_options(b)
                            for b in self.xls_blocks()}}

    def chan_flop(self, block: str, channel: str, direction: Optional[str] = None) -> str:
        """The register on one channel of a proc block: ``none``, ``flop``,
        ``skid`` or ``zerolatency``. ``xls.chan_flop["<block>.<channel>"]``
        wins; otherwise the block's ``flop_inputs``/``flop_outputs`` (and
        ``_kind``) for a receive/send channel, when the knobs set them.

        For procs this is the only switch that works: codegen's
        ``--flop_inputs``/``--flop_outputs`` do not register a proc's channels
        (tests/xls/test_xls_facts.py); the kind goes on the IR's
        ``chan_interface``."""
        per = (self.get("xls", "chan_flop", default={}) or {})
        if f"{block}.{channel}" in per:
            return per[f"{block}.{channel}"]
        o = self.block_options(block)
        side = {"receive": "inputs", "send": "outputs"}.get(direction or "")
        if side and o.get(f"flop_{side}"):
            return o.get(f"flop_{side}_kind", "flop")
        return "none"

    def storage_section(self) -> Dict[str, dict]:
        """``storage:`` as written, with each entry's ``files`` resolved
        against the knob file that names them (:mod:`fw.hdl.storage`)."""
        out = {}
        for key, e in (self.get("storage", default={}) or {}).items():
            o = self.origin("storage", key)
            base = Path(o.file).parent if o else Path(".")
            out[key] = {**e, **({"files": [f if os.path.isabs(f) else str((base / f).resolve())
                                           for f in e["files"]]} if e.get("files") else {})}
        return out

    def storage(self, inst: str) -> dict:
        s = self.get("storage", default={}) or {}
        out = dict(s.get("default", {"bind": "flops"}))
        out.update(s.get(inst, {}))
        return out

    def exceptions(self) -> List[dict]:
        return list(self.get("island", "exceptions", default=[]) or [])

    def exception_for(self, channel: str) -> Optional[dict]:
        return next((e for e in self.exceptions() if e["channel"] == channel), None)

    def groups(self) -> Dict[str, List[str]]:
        return dict(self.get("island", "groups", default={}) or {})

    def group_of(self, block: str) -> Optional[str]:
        return next((g for g, bs in self.groups().items() if block in bs), None)

    def rtl_params(self) -> dict:
        return dict(self.get("rtl", default={}) or {})

    def latency_contracts(self) -> Dict[str, dict]:
        return dict(self.get("contracts", "latency", default={}) or {})

    # -- checks beyond the schema --------------------------------------
    def _check(self):
        msgs = []
        known = set(self.xls_blocks())
        for b in (self.get("xls", "blocks", default={}) or {}):
            if known and b not in known:
                msgs.append(f"{self.where('xls', 'blocks', b)}: xls.blocks.{b}: not in "
                            f"design.xls {sorted(known)}")
        seen: Dict[str, str] = {}
        for g, bs in self.groups().items():
            for b in bs:
                if b in seen:
                    msgs.append(f"{self.where('island', 'groups', g)}: block {b} is in groups "
                                f"{seen[b]} and {g}")
                seen[b] = g
                if known and b not in known:
                    msgs.append(f"{self.where('island', 'groups', g)}: island.groups.{g}: "
                                f"{b} is not in design.xls")
            # One stages/II setting per multi-proc package (tests/xls/test_xls_facts.py).
            sched = {b: tuple(self.block_options(b).get(k) for k in
                              ("pipeline_stages", "clock_period_ps", "worst_case_throughput"))
                     for b in bs}
            if len(set(sched.values())) > 1:
                msgs.append(f"{self.where('island', 'groups', g)}: island.groups.{g}: its blocks "
                            f"have different schedules {sched}; XLS takes one schedule per "
                            f"multi-proc package")
        for i, c in enumerate(self.get("contracts", "latency", default={}) or {}):
            if "->" not in c:
                msgs.append(f"{self.where('contracts', 'latency', c)}: contracts.latency: "
                            f"{c!r} is not '<block>.<port> -> <block>.<port>'")
        if msgs:
            raise KnobError("\n".join(msgs))

    # -- outputs -------------------------------------------------------
    def resolved(self) -> dict:
        return {"format": FORMAT, "version": VERSION, "files": list(self.files),
                "knobs": copy.deepcopy(self.data)}

    def sv_pkg_name(self) -> str:
        return f"{self.top or 'design'}_knobs_pkg"

    def emit_sv_pkg(self, name: Optional[str] = None) -> str:
        name = name or self.sv_pkg_name()
        L = [f"// Generated from {', '.join(Path(f).name for f in self.files)} by fw.hdl.knobs;",
             "// do not edit.", f"package {name};"]
        for k, v in self.rtl_params().items():
            if isinstance(v, bool):
                L.append(f"    localparam bit {k} = 1'b{int(v)};")
            elif isinstance(v, int):
                L.append(f"    localparam int {k} = {v};")
            else:
                L.append(f'    localparam string {k} = "{v}";')
        L.append("endpackage")
        return "\n".join(L) + "\n"

    def write(self, outdir) -> Dict[str, str]:
        """Write <top>.knobs.json and <top>_knobs_pkg.sv; return {kind: path}."""
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        j = out / f"{self.top or 'design'}.knobs.json"
        j.write_text(json.dumps(self.resolved(), indent=2) + "\n")
        sv = out / f"{self.sv_pkg_name()}.sv"
        sv.write_text(self.emit_sv_pkg())
        cg = out / f"{self.top or 'design'}.codegen.json"
        cg.write_text(json.dumps(self.codegen_options(), indent=2) + "\n")
        return {"json": str(j), "sv": str(sv), "codegen": str(cg)}
