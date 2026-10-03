"""Generate SV functions for the exhaustive (CH-4) and random (CH-5) tests.

The generator only has to produce *legal* SV. It does not compute any
widths: Verilator decides what the SV means, and the static front end and
lowering must agree with it. The expressions lean on what makes SV widths
subtle: mixed signedness, unsized literals that widen the context, size and
sign casts, concatenation (self-determined operands), shifts, and
comparisons and logical ops that produce 1 bit.

Kept out on purpose:

* variable bit and part selects that could go out of range: Verilator does
  not follow the LRM there (xls-phase0.md §11), so it can't be the reference;
* an unguarded divide (D-1). A divide is generated only as
  ``(b != 0) ? a / b : 0`` with ``b`` an argument, which the lowering accepts.

Written around:

* a ``?:`` condition is generated as ``(|(c))``. That means the same: both
  are self-determined and true when ``c`` is nonzero (``c != 0`` would not be,
  it widens ``c`` to 32 bits).
  Verilator 5.049 evaluates ``b ~^ 1`` and ``~(b ^ 1)`` (1-bit ``b``) at 1 bit
  when they are a condition (xls-phase0.md §11); the bare forms are pinned in
  ``micro/lrm_pins_pkg.sv``.
"""
from __future__ import annotations

import dataclasses as dc
import random
from typing import List, Optional, Tuple


@dc.dataclass
class Arg:
    name: str
    width: int
    signed: bool

    def decl(self) -> str:
        return f"bit {'signed ' if self.signed else ''}[{self.width - 1}:0] {self.name}"


@dc.dataclass
class GenFn:
    name: str
    args: List[Arg]
    ret_width: int
    ret_signed: bool
    body: str

    def sv(self) -> str:
        ret = f"bit {'signed ' if self.ret_signed else ''}[{self.ret_width - 1}:0]"
        args = ", ".join(a.decl() for a in self.args)
        return (f"    function automatic {ret} {self.name}({args});\n"
                f"        return {self.body};\n"
                f"    endfunction\n")


BINOPS = ["+", "-", "*", "&", "|", "^", "~^", "<<", ">>", ">>>", "<<<",
          "==", "!=", "<", "<=", ">", ">=", "&&", "||"]
UNOPS = ["~", "-", "!", "&", "|", "^", "~&", "~|", "~^", "+"]


class ExprGen:
    def __init__(self, rng: random.Random, args: List[Arg]):
        self.rng = rng
        self.args = args

    def literal(self, sized: bool) -> str:
        r = self.rng
        if not sized and r.random() < 0.5:
            return str(r.choice([0, 1, 2, 3, 7, 15, 100, 255, 256, 1000, r.getrandbits(20)]))
        w = r.randint(1, 20)
        v = r.getrandbits(w)
        s = "s" if r.random() < 0.3 else ""
        return f"{w}'{s}h{v:x}"

    def gen(self, depth: int, sized: bool = False) -> str:
        """An expression; ``sized`` forbids unsized literals at the top
        (a concatenation operand must be sized)."""
        r = self.rng
        if depth <= 0 or r.random() < 0.15:
            if r.random() < 0.75:
                a = r.choice(self.args)
                k = r.random()
                if k < 0.12 and a.width > 1:
                    return f"{a.name}[{r.randrange(a.width)}]"
                if k < 0.22 and a.width > 1:
                    hi = r.randrange(1, a.width)
                    lo = r.randrange(0, hi + 1)
                    return f"{a.name}[{hi}:{lo}]"
                return a.name
            return self.literal(sized)
        k = r.random()
        if k < 0.42:
            op = r.choice(BINOPS)
            lhs = self.gen(depth - 1, sized)
            rhs = self.gen(depth - 1, sized and op not in ("<<", ">>", ">>>", "<<<"))
            return f"({lhs} {op} {rhs})"
        if k < 0.55:
            op = r.choice(UNOPS)
            return f"({op}{self.gen(depth - 1, sized)})"
        if k < 0.65:
            return f"((|({self.gen(depth - 1)})) ? {self.gen(depth - 1, sized)} : {self.gen(depth - 1, sized)})"
        if k < 0.74:
            n = r.randint(2, 3)
            return "{" + ", ".join(self.gen(depth - 1, sized=True) for _ in range(n)) + "}"
        if k < 0.78:
            return f"{{{r.randint(1, 3)}{{{self.gen(depth - 1, sized=True)}}}}}"
        if k < 0.88:
            return f"{r.randint(1, 24)}'({self.gen(depth - 1)})"
        if k < 0.95:
            return f"{r.choice(['signed', 'unsigned'])}'({self.gen(depth - 1, sized)})"
        b = r.choice(self.args)
        op = r.choice(["/", "%"])
        return f"(({b.name} != 0) ? ({self.gen(depth - 1, sized)} {op} {b.name}) : {self.literal(True)})"


def random_function(rng: random.Random, name: str, depth: int = 4) -> GenFn:
    nargs = rng.randint(1, 3)
    args = []
    for i in range(nargs):
        w = rng.choice([1, 2, 3, 4, 5, 7, 8, 9, 12, 16, 17, 31, 32, 33, 48, 64, 65, 70])
        args.append(Arg(f"a{i}", w, rng.random() < 0.4))
    body = ExprGen(rng, args).gen(depth)
    rw = rng.choice([1, 2, 3, 4, 7, 8, 9, 16, 24, 32, 33, 40, 64, 72])
    return GenFn(name, args, rw, rng.random() < 0.4, body)


def single_op_functions(widths=(1, 2, 3, 4)) -> List[GenFn]:
    """One function per (operator, operand width, operand signedness, result
    width): the exhaustive E-row checks of CH-4."""
    out: List[GenFn] = []
    n = 0
    for w in widths:
        for sa in (False, True):
            for sb in (False, True):
                a, b = Arg("a", w, sa), Arg("b", w, sb)
                for op in BINOPS + ["/", "%"]:
                    for rw in (w, w + 2):
                        if op in ("/", "%"):
                            body = f"((b != 0) ? (a {op} b) : {rw}'(0))"
                        else:
                            body = f"(a {op} b)"
                        out.append(GenFn(f"x{n}", [a, b], rw, sa and sb, body))
                        n += 1
                if sb:
                    continue
                for op in UNOPS:
                    for rw in (w, w + 2):
                        out.append(GenFn(f"x{n}", [a], rw, sa, f"({op}a)"))
                        n += 1
                for rw in (w, w + 2):
                    out.append(GenFn(f"x{n}", [a, Arg("b", w, sb)], rw, sa,
                                     "(a[0] ? a : b)"))
                    n += 1
                    out.append(GenFn(f"x{n}", [a], rw, False, f"{{2{{a}}}}"))
                    n += 1
                    out.append(GenFn(f"x{n}", [a], rw, sa, f"{max(1, w - 1)}'(a)"))
                    n += 1
                    out.append(GenFn(f"x{n}", [a], rw, sa, f"signed'(a)"))
                    n += 1
    return out


def package(name: str, fns: List[GenFn]) -> str:
    return f"package {name};\n" + "".join(f.sv() for f in fns) + "endpackage\n"
