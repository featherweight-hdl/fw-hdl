"""Replay a counterexample in a dynamic run (``formal-svunit.md`` F4).

A counterexample (``<test>.cex.json``, from :mod:`.prove`) gives the values
each ``randomize()`` call of a test returns. The replay is a copy of the test
file in which each of those calls is replaced by a call of a generated
function, which assigns the values and returns 1, as a successful
``randomize()`` does:

    `FAIL_UNLESS(std::randomize(m) with { m != 8'h31; })
    `FAIL_UNLESS(__fw_replay_f_one_char_collides_0(m))

The copy runs at any level in place of the original: same module, same tests,
same line numbers (a `` `line `` directive names the original file, so a
failure is reported at the original line). Only the calls of tests with a
counterexample change; the other tests run as before.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Sequence

FORMAT = "fw.hdl.formal-cex"


class ReplayError(Exception):
    pass


def load(path: str) -> dict:
    with open(path) as f:
        cex = json.load(f)
    if cex.get("format") != FORMAT:
        raise ReplayError(f"{path}: not a counterexample file (format {cex.get('format')!r})")
    return cex


def _skip_space(src: str, i: int) -> int:
    while i < len(src):
        if src[i].isspace():
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = len(src) if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = len(src) if j < 0 else j + 2
        else:
            break
    return i


def _balanced(src: str, i: int, open_: str, close: str) -> int:
    """*src[i]* is *open_*: the offset just past its matching *close*."""
    depth = 0
    while i < len(src):
        c = src[i]
        if c == '"':
            i += 1
            while i < len(src) and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
        elif src.startswith("//", i) or src.startswith("/*", i):
            i = _skip_space(src, i)
            continue
        elif c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ReplayError(f"unbalanced {open_!r} at offset {i}")


def call_span(src: str, start: int, end: int) -> int:
    """The end of the ``randomize`` call at *src[start:end]*: past its
    argument list, if the span stops before it, and its ``with`` clause."""
    i = _skip_space(src, end)
    if not src[start:end].rstrip().endswith(")") and src.startswith("(", i):
        end = _balanced(src, i, "(", ")")
        i = _skip_space(src, end)
    if re.match(r"with\b", src[i:]):
        i = _skip_space(src, i + 4)
        if src.startswith("(", i):                      # with (a, b) { ... }
            i = _skip_space(src, _balanced(src, i, "(", ")"))
        if not src.startswith("{", i):
            raise ReplayError(f"expected '{{' after 'with' at offset {i}")
        end = _balanced(src, i, "{", "}")
    return end


def _ident(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s)


def _value(v: dict) -> str:
    w = int(v["width"])
    return f"{w}'h{int(v['value']) & ((1 << w) - 1):x}"


def replay_source(path: str, cexes: Sequence[dict]) -> str:
    """The text of test file *path*, with the ``randomize()`` calls of each
    counterexample in *cexes* that is in this file replaced by its values."""
    with open(path) as f:
        src = f.read()
    real = os.path.realpath(path)
    edits = []                     # (start, end, replacement)
    funcs: Dict[int, List[str]] = {}   # offset of the module's endmodule -> functions
    for cex in cexes:
        for site in cex.get("randomize", []):
            if os.path.realpath(site["file"]) != real:
                continue
            start, end = int(site.get("start", -1)), int(site.get("end", -1))
            if start < 0:
                raise ReplayError(f"{path}:{site['line']}: the randomize() call of test "
                                  f"{cex['test']!r} is not in the file's text (a macro "
                                  f"body?); it cannot be replayed")
            end = call_span(src, start, end)
            name = f"__fw_replay_{_ident(cex['test'])}_{site['site']}"
            vs = site["vars"]
            text = src[start:end]
            # The replacement is on one line; the lines the call spanned follow it,
            # empty, so that every later line keeps its number.
            edits.append((start, end, f"{name}({', '.join(v['name'] for v in vs)})"
                          + "\n" * text.count("\n")))
            m = re.compile(r"\bendmodule\b").search(src, end)
            if m is None:
                raise ReplayError(f"{path}: no endmodule after line {site['line']}")
            outs = ", ".join(f"output bit {'signed ' if v['signed'] else ''}"
                             f"[{int(v['width']) - 1}:0] v{i}" for i, v in enumerate(vs))
            body = " ".join(f"v{i} = {_value(v)};" for i, v in enumerate(vs))
            shown = ", ".join(f"{v['name']}={_value(v)}" for v in vs)
            funcs.setdefault(m.start(), []).append(
                f"  // {cex['test']}: the counterexample's values for line {site['line']}, "
                f"{' '.join(text.split())}\n"
                f"  function automatic bit {name}({outs});\n"
                f"    {body}\n"
                f"    $display(\"INFO:  [%0t][fw.formal]: replay {cex['test']} line "
                f"{site['line']}: {shown}\", $time);\n"
                f"    return 1;\n"
                f"  endfunction\n")
    for off, fs in funcs.items():
        edits.append((off, off, "\n" + "".join(fs)))
    edits.sort(key=lambda e: (e[0], e[1]))
    out, pos = [], 0
    for start, end, rep in edits:
        if start < pos:
            raise ReplayError(f"{path}: overlapping replay edits at offset {start}")
        out += [src[pos:start], rep]
        pos = end
    out.append(src[pos:])
    return f'`line 1 "{os.path.abspath(path)}" 0\n' + "".join(out)


def replay_files(tests: Sequence[str], cex_files: Sequence[str], outdir: str) -> List[str]:
    """Write the replay of each test file of *tests* into *outdir*, under its
    own name; the files are returned in the order given. A file with no
    counterexample is copied unchanged (with only the `` `line `` directive)."""
    cexes = [load(p) for p in cex_files]
    os.makedirs(outdir, exist_ok=True)
    out, names = [], set()
    for t in tests:
        base = os.path.basename(t)
        if base in names:
            raise ReplayError(f"two test files named {base!r}")
        names.add(base)
        dst = os.path.join(outdir, base)
        with open(dst, "w") as f:
            f.write(replay_source(t, cexes))
        out.append(dst)
    known = {os.path.realpath(t) for t in tests}
    for c in cexes:
        for s in c.get("randomize", []):
            if os.path.realpath(s["file"]) not in known:
                raise ReplayError(f"counterexample of {c['test']!r} is in {s['file']}, "
                                  f"which is not among the test files")
    return out
