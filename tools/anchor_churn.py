#!/usr/bin/env python3
"""Anchor churn across edits.

Builds the IR of named example tops at two source trees, assigns anchors to
both, and diffs the tables per named scope (root or member):

(a) anchors that changed in a scope whose content hash did not change.
    Must be 0: an edit may re-key only the scope it touches.
(b) in scopes whose hash changed, the share of *matched* nodes that got a new
    anchor. Nodes are matched by aligning each scope's anchor-ordered nodes on
    (kind, subtree hash); a node that was edited (or contains the edit) has a
    new hash and is not in the denominator. Informational.

Two corpora:
- ``history``: consecutive commits that touch a case's files (``git archive``,
  read-only on the repo).
- ``edits``: systematic source edits applied to the working tree's sources
  (insert/delete/change a statement, add a member or function, shift lines).

Usage::

    direnv exec . python tools/anchor_churn.py [--out build/anchor_churn]
"""
from __future__ import annotations

import argparse
import dataclasses as dc
import difflib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

from zuspec.ir.core.anchor import AnchorTable, assign_anchors, scope_hash

from fw.hdl.config import FlowConfig
from fw.hdl.spl_flow import module_name
from fw.hdl.xls_flow import sv_to_component, sv_to_functions

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBTREES = ["examples/xls", "src"]
STD = "examples/xls/common/xls_std_pkg.sv"
FW_LIB = ["src/fw_hdl_pkg.sv", "src/fw_clock_xtor_if.sv", "src/std/fw_std_pkg.sv"]


@dc.dataclass
class Case:
    name: str
    files: List[str]          # repo-relative, parsed together
    fns: List[str] = dc.field(default_factory=list)      # function tops
    classes: List[str] = dc.field(default_factory=list)  # component tops


CASES = [
    Case("gcd", [STD, "examples/xls/gcd/gcd_pkg.sv"],
         fns=["gcd_pkg::gcd_euclidean8", "gcd_pkg::gcd_binary8"]),
    Case("rle", FW_LIB + ["examples/xls/rle/rle_pkg.sv"],
         classes=["RunLengthEncoder32", "RunLengthDecoder32"]),
    Case("aes", ["examples/xls/aes/aes_pkg.sv"], fns=["aes_pkg::encrypt"]),
    Case("lfsr", ["examples/xls/lfsr/lfsr_pkg.sv"], fns=["lfsr_pkg::lfsr8"]),
]

# (case, file, old text, new text, what the edit is)
EDITS = [
    ("gcd", "examples/xls/gcd/gcd_pkg.sv",
     "            for (int i = 0; i < DN; i++) begin\n                if (s.a == s.b)",
     "            for (int i = 0; i < DN; i++) begin\n                s.d = s.d;\n"
     "                if (s.a == s.b)",
     "insert a statement at the head of a loop body"),
    ("gcd", "examples/xls/gcd/gcd_pkg.sv",
     "                2'b00: r = '{a: a >> 1, b: b >> 1, d: d + 1'b1};",
     "                2'b00: r = '{a: a >> 1, b: b >> 1, d: d + 1'b1 + 1'b0};",
     "change an expression in one case arm"),
    ("gcd", "examples/xls/gcd/gcd_pkg.sv",
     "        static function bit [N-1:0] gcd_euclidean(bit [N-1:0] a, bit [N-1:0] b);\n",
     "        static function bit [N-1:0] gcd_euclidean(bit [N-1:0] a, bit [N-1:0] b);\n"
     "            bit [N-1:0] t = a;\n            a = t;\n",
     "insert a declaration and statement at the head of one function"),
    ("gcd", "examples/xls/gcd/gcd_pkg.sv",
     "        static function abd_t gcd_binary_match(",
     "        static function bit [N-1:0] unused_fn(bit [N-1:0] a);\n"
     "            return a;\n        endfunction\n\n"
     "        static function abd_t gcd_binary_match(",
     "add an unused function before the others"),
    ("gcd", "examples/xls/gcd/gcd_pkg.sv",
     "package gcd_pkg;\n", "package gcd_pkg;\n\n// shifted\n\n\n",
     "shift every line (no content change)"),
    ("rle", "examples/xls/rle/rle_pkg.sv",
     "            forever begin\n                EncInData zero_input",
     "            forever begin\n                bit extra = 1'b0;\n"
     "                EncInData zero_input",
     "insert a declaration at the head of the encoder's loop"),
    ("rle", "examples/xls/rle/rle_pkg.sv",
     "                    count = 1;\n",
     "                    count = 2'd1;\n",
     "change one statement in a middle branch"),
    ("rle", "examples/xls/rle/rle_pkg.sv",
     "        bit [SYMBOL_WIDTH-1:0] prev_symbol = '0;\n",
     "        bit spare = 1'b0;\n        bit [SYMBOL_WIDTH-1:0] prev_symbol = '0;\n",
     "add a state field before the others"),
    ("rle", "examples/xls/rle/rle_pkg.sv",
     "                prev_last = last;\n",
     "                prev_last = last;\n                prev_last = prev_last;\n",
     "append a statement at the tail of the encoder's loop"),
    ("aes", "examples/xls/aes/aes_pkg.sv",
     "package aes_pkg;\n", "package aes_pkg;\n// shifted\n\n",
     "shift every line (no content change)"),
]


# -- building ---------------------------------------------------------------

def build(tree: str, case: Case) -> Tuple[Optional[AnchorTable], Dict[str, str]]:
    """The anchor table of *case* built from the sources under *tree*, and the
    tops that failed to build (top -> error)."""
    files = [os.path.join(tree, f) for f in case.files]
    config = FlowConfig(incdirs=[os.path.join(tree, "src"), os.path.join(tree, "src", "std")])
    roots, errs = [], {}
    if any(not os.path.exists(f) for f in files):
        return None, {"*": "files missing at this tree"}
    for top in case.fns:
        try:
            roots += sv_to_functions(files, [top], config, rename={top: module_name(top)})
        except Exception as e:  # noqa: BLE001 - recorded, not fatal
            errs[top] = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
    for top in case.classes:
        try:
            roots.append(sv_to_component(files, top, config))
        except Exception as e:  # noqa: BLE001
            errs[top] = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
    # Callees reached from several tops appear once.
    seen, uniq = set(), []
    for r in roots:
        if r.name not in seen:
            seen.add(r.name)
            uniq.append(r)
    return (assign_anchors(uniq) if uniq else None), errs


# -- diffing ----------------------------------------------------------------

@dc.dataclass
class Diff:
    scopes_same: int = 0
    scopes_changed: int = 0
    scopes_added: int = 0
    scopes_removed: int = 0
    #: (a): anchors added/removed/re-kinded in hash-unchanged scopes.
    unchanged_scope_anchor_changes: int = 0
    unchanged_scope_details: List[str] = dc.field(default_factory=list)
    #: (b): matched nodes in changed scopes, and how many got a new anchor.
    matched: int = 0
    rekeyed: int = 0
    rekeyed_examples: List[str] = dc.field(default_factory=list)

    def add(self, o: "Diff") -> None:
        for f in dc.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, list):
                v.extend(getattr(o, f.name))
            else:
                setattr(self, f.name, v + getattr(o, f.name))

    @property
    def rekey_pct(self) -> Optional[float]:
        return round(100.0 * self.rekeyed / self.matched, 1) if self.matched else None


def _by_scope(t: AnchorTable) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for a, e in t.entries.items():
        out.setdefault(e.scope, []).append(a)
    return out


def _sig(t: AnchorTable, a: str) -> Tuple[str, str]:
    node = t.node_of(a)
    return t.entries[a].kind, (scope_hash(node) if node is not None else a)


def diff(old: AnchorTable, new: AnchorTable) -> Diff:
    d = Diff()
    so, sn = _by_scope(old), _by_scope(new)
    d.scopes_added = len(set(sn) - set(so))
    d.scopes_removed = len(set(so) - set(sn))
    for scope in sorted(set(so) & set(sn)):
        ao, an = so[scope], sn[scope]
        if old.scope_hashes.get(scope) == new.scope_hashes.get(scope):
            d.scopes_same += 1
            ko = {a: old.entries[a].kind for a in ao}
            kn = {a: new.entries[a].kind for a in an}
            bad = sorted(set(ko.items()) ^ set(kn.items()))
            d.unchanged_scope_anchor_changes += len(bad)
            d.unchanged_scope_details += [f"{scope}: {a} ({k})" for a, k in bad[:5]]
            continue
        d.scopes_changed += 1
        sigo, sign = [_sig(old, a) for a in ao], [_sig(new, a) for a in an]
        sm = difflib.SequenceMatcher(a=sigo, b=sign, autojunk=False)
        for blk in sm.get_matching_blocks():
            for i in range(blk.size):
                a_old, a_new = ao[blk.a + i], an[blk.b + i]
                d.matched += 1
                if a_old != a_new:
                    d.rekeyed += 1
                    if len(d.rekeyed_examples) < 8:
                        d.rekeyed_examples.append(f"{a_old} -> {a_new}")
    return d


# -- trees ------------------------------------------------------------------

def archive(commit: str, dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    for sub in SUBTREES:  # an early commit may lack one of them
        r = subprocess.run(["git", "-C", REPO, "archive", commit, sub], capture_output=True)
        if r.returncode == 0:
            with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
                tf.extractall(dest)


def worktree_copy(dest: str) -> None:
    for s in SUBTREES:
        shutil.copytree(os.path.join(REPO, s), os.path.join(dest, s),
                        ignore=shutil.ignore_patterns("rundir", "__pycache__", "*.log"))


def commits_touching(files: Sequence[str]) -> List[str]:
    out = subprocess.run(["git", "-C", REPO, "log", "--format=%h", "--reverse", "--"] +
                         list(files), check=True, capture_output=True, text=True).stdout
    return out.split()


# -- corpora ----------------------------------------------------------------

def run_history(tmp: str) -> List[dict]:
    rows = []
    trees: Dict[str, str] = {}

    def tree(c):
        if c not in trees:
            trees[c] = os.path.join(tmp, f"c-{c}")
            archive(c, trees[c])
        return trees[c]

    for case in CASES:
        cs = commits_touching(case.files)
        for c0, c1 in zip(cs, cs[1:]):
            t0, e0 = build(tree(c0), case)
            t1, e1 = build(tree(c1), case)
            if "*" in e0 or "*" in e1:
                continue  # the case did not exist yet (a shared file's early commit)
            row = {"corpus": "history", "case": case.name, "edit": f"{c0}..{c1}",
                   "errors": {**{f"{c0}:{k}": v for k, v in e0.items()},
                              **{f"{c1}:{k}": v for k, v in e1.items()}}}
            if t0 is not None and t1 is not None:
                row["diff"] = dc.asdict(diff(t0, t1))
            rows.append(row)
    return rows


def run_edits(tmp: str) -> List[dict]:
    base = os.path.join(tmp, "base")
    worktree_copy(base)
    cases = {c.name: c for c in CASES}
    base_tables = {}
    rows = []
    for i, (cname, f, old, new, what) in enumerate(EDITS):
        case = cases[cname]
        if cname not in base_tables:
            base_tables[cname] = build(base, case)
        t0, e0 = base_tables[cname]
        dest = os.path.join(tmp, f"edit{i}")
        worktree_copy(dest)
        p = os.path.join(dest, f)
        with open(p) as fh:
            text = fh.read()
        row = {"corpus": "edits", "case": cname, "edit": what, "errors": dict(e0)}
        if text.count(old) != 1:
            row["errors"]["*"] = "edit anchor text not found exactly once"
            rows.append(row)
            continue
        with open(p, "w") as fh:
            fh.write(text.replace(old, new))
        t1, e1 = build(dest, case)
        row["errors"].update({f"edited:{k}": v for k, v in e1.items()})
        if t0 is not None and t1 is not None:
            row["diff"] = dc.asdict(diff(t0, t1))
        rows.append(row)
        shutil.rmtree(dest, ignore_errors=True)
    return rows


# -- report -----------------------------------------------------------------

def report(rows: List[dict]) -> str:
    tot = Diff()
    lines = ["# Anchor churn", "",
             "| corpus | case | edit | scopes same/changed/+/- | (a) | (b) re-keyed/matched |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        if "diff" not in r:
            lines.append(f"| {r['corpus']} | {r['case']} | {r['edit']} | not built | | |")
            continue
        d = Diff(**{k: v for k, v in r["diff"].items()})
        tot.add(d)
        lines.append(f"| {r['corpus']} | {r['case']} | {r['edit']} | "
                     f"{d.scopes_same}/{d.scopes_changed}/{d.scopes_added}/{d.scopes_removed} | "
                     f"{d.unchanged_scope_anchor_changes} | {d.rekeyed}/{d.matched} |")
    lines += ["", f"**(a) total: {tot.unchanged_scope_anchor_changes}** (must be 0). "
              f"**(b): {tot.rekeyed}/{tot.matched} matched nodes re-keyed "
              f"({tot.rekey_pct}%)** in changed scopes.", ""]
    if tot.unchanged_scope_details:
        lines += ["## (a) violations", ""] + [f"- `{x}`" for x in tot.unchanged_scope_details]
    if tot.rekeyed_examples:
        lines += ["", "## Re-key examples", ""] + [f"- `{x}`" for x in tot.rekeyed_examples]
    errs = [(r["case"], r["edit"], k, v) for r in rows for k, v in r["errors"].items()]
    if errs:
        lines += ["", "## Build errors (tops skipped)", ""] + \
            [f"- {c} / {e} / `{k}`: {v}" for c, e, k, v in errs]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(REPO, "build", "anchor_churn"))
    ap.add_argument("--corpus", choices=["history", "edits", "all"], default="all")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        rows = []
        if args.corpus in ("history", "all"):
            rows += run_history(tmp)
        if args.corpus in ("edits", "all"):
            rows += run_edits(tmp)
    with open(os.path.join(args.out, "churn.json"), "w") as f:
        json.dump(rows, f, indent=1)
    text = report(rows)
    with open(os.path.join(args.out, "churn.md"), "w") as f:
        f.write(text)
    sys.stdout.write(text)
    bad = sum(r.get("diff", {}).get("unchanged_scope_anchor_changes", 0) for r in rows)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
