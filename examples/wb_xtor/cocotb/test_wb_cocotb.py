"""T7 bench (docs/design/xtor-shell-plan.md, D9): the class bench
(tb/wb_xtor_tb.sv) in cocotb, on the generated cores through their
generated cocotb bridges. The driver, memory, gaps and checks are the
class bench's, so the results must be too: 149 edges plain, 185 with
+rand, 7 back to back.

The bridges are built with the cores' handles and the clock, the memory
is given to the target's bridge (set_p), both are started (run), and the
driver makes its accesses through the initiator's bridge, which
implements wb_if. +mut_mem corrupts read data (the checks must fail);
+no_set leaves the target's port unset (its run() must raise).
"""
import cocotb
from cocotb.clock import Clock
from cocotb.simtime import get_sim_time
from cocotb.triggers import First, ReadOnly, RisingEdge

from wb_api_pkg import req_t, rsp_t
from wb_initiator_bridge import wb_initiator_bridge
from wb_target_bridge import wb_target_bridge

N = 40
ERR_ADR = 0xF000_0000
M32 = 0xFFFF_FFFF
PERIOD = 10        # ns; rising edges at 5, 15, ...
BUS = ("adr", "dat_w", "sel", "we", "cyc", "stb", "dat_r", "ack", "err")


class Gap:
    """A gap of 0-3 from a 16-bit LFSR (the class bench's gap_c)."""

    def __init__(self, seed):
        self.s = seed

    def next(self):
        s = self.s
        b = ((s >> 15) ^ (s >> 13) ^ (s >> 12) ^ (s >> 10)) & 1
        self.s = ((s << 1) | b) & 0xFFFF
        return self.s & 3


def edges():
    """The rising edges so far: code at edge k reads k (0 before the first)."""
    return int(get_sim_time("ns") + PERIOD // 2) // PERIOD


class Mem:
    """The memory behind the target: 16 words; an access to ERR_ADR is an
    error. With +rand, 0-3 wait states per access: the call returns that
    many edges later. Implements wb_if."""

    def __init__(self, clk, rnd, mut):
        self.clk = clk
        self.rnd = rnd
        self.mut = mut
        self.mem = [0] * 16
        self.g = Gap(0x0B0E)
        self.n_acc = 0

    def apply(self, req):
        i = (req.adr >> 2) & 0xF
        rsp = rsp_t(err=int(req.adr == ERR_ADR))
        if not rsp.err and req.we:
            for b in range(4):
                if (req.sel >> b) & 1:
                    m = 0xFF << (8 * b)
                    self.mem[i] = (self.mem[i] & ~m) | (req.dat & m)
        rsp.dat = 0 if rsp.err else self.mem[i]
        if self.mut and not req.we:
            rsp.dat ^= 1
        return rsp

    async def access(self, req):
        self.n_acc += 1
        ws = self.g.next() if self.rnd else 0
        for _ in range(ws):
            await RisingEdge(self.clk)
        return self.apply(req)


class Chk:
    """Logs the bus as each edge sees it."""

    def __init__(self, dut):
        self.dut = dut
        self.log = []

    async def run(self):
        await ReadOnly()
        while True:
            b = {n: int(getattr(self.dut, n).value) for n in BUS}
            await RisingEdge(self.dut.clk)
            self.log.append(b)
            await ReadOnly()


async def drive(clk, xi, calls):
    """The N accesses (the class bench's drv_c): a write then a read back
    of each word, every 7th to ERR_ADR, each after a gap of 0-3 edges."""
    g = Gap(0xACE1)
    for a in range(N):
        for _ in range(g.next()):
            await RisingEdge(clk)
        we = int(a % 2 == 0)
        q = req_t(adr=ERR_ADR if a % 7 == 6 else ((a // 2) % 16) * 4, we=we,
                  dat=(0x1000_0000 * (a % 16) + a) & M32 if we else 0, sel=0xF)
        c = edges()
        s = await xi.access(q)
        calls.append((c, edges(), q, s))


def check(calls, log, m):
    """The class bench's check_parts(): the first failure, or ""."""
    shadow = [0] * 16
    for a, (c, r, q, s) in enumerate(calls):
        w = (q.adr >> 2) & 0xF
        eerr = int(q.adr == ERR_ADR)
        if r <= c or r > len(log):
            return f"access {a}: called at {c}, returned at {r}"
        for e in range(c + 1, r + 1):
            b = log[e - 1]
            term = b["ack"] or b["err"]
            if not (b["cyc"] and b["stb"]):
                return f"access {a}: cyc/stb low at edge {e} (C3)"
            if (b["adr"] != q.adr or b["we"] != q.we or b["sel"] != q.sel
                    or (q.we and b["dat_w"] != q.dat)):
                return f"access {a}: request not on the bus at edge {e}"
            if term != (e == r):
                return f"access {a}: termination {term} at edge {e}, returned at {r} (C7)"
        if ((a + 1 == len(calls) or calls[a + 1][0] > r) and r < len(log)
                and log[r]["stb"]):
            return f"access {a}: stb still high at edge {r + 1} (drop)"
        if s.err != eerr:
            return f"access {a}: err {s.err}"
        if not eerr and q.we:
            shadow[w] = q.dat
        if not eerr and s.dat != shadow[w]:
            return f"access {a}: read {s.dat:08x}, expected {shadow[w]:08x}"
    if len(calls) != N:
        return f"{len(calls)} accesses returned"
    if m.n_acc != N:
        return f"the target saw {m.n_acc} accesses"
    return ""


async def caught(coro, errs):
    try:
        await coro
    except Exception as e:      # reported as the result
        errs.append(e)


@cocotb.test()
async def wb_cocotb(dut):
    args = cocotb.plusargs
    Clock(dut.clk, PERIOD, unit="ns").start(start_high=False)
    bi = wb_initiator_bridge(dut.xi, dut.clk)
    bt = wb_target_bridge(dut.xt, dut.clk)
    m = Mem(dut.clk, "rand" in args, "mut_mem" in args)
    k = Chk(dut)
    if "no_set" not in args:
        bt.set_p(m)
    cocotb.start_soon(k.run())
    cocotb.start_soon(bi.run())
    errs = []
    tgt = cocotb.start_soon(caught(bt.run(), errs))
    calls = []
    drv = cocotb.start_soon(drive(dut.clk, bi, calls))
    await First(drv.complete, tgt.complete)
    if errs:
        print(f"R fail {errs[0]}")
        return
    await RisingEdge(dut.clk)       # log the last edge
    e = check(calls, k.log, m)
    b2b = sum(1 for i in range(1, len(calls)) if calls[i][0] == calls[i - 1][1])
    if e == "":
        print(f"R ok {N} accesses in {calls[-1][1]} edges, {b2b} back to back")
    else:
        print(f"R fail {e}")
