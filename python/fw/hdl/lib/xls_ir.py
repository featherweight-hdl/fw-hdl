"""The XLS IR shapes the library classes lower to, written by hand.

Each function returns IR text for xlsynth (proc-scoped channels). They are the
lowerings of the recognized library classes (:mod:`.registry`), and
their facts are checked by tests/xls/test_ir_templates.py.

  credit_tx   credit-gated sender: a non-blocking receive whose predicate is
              "a credit is left", a send predicated on the receive's valid, and
              the credit counter moved up/down by two predicated next_values.
              The credit return is a non-blocking receive taken every
              activation, so a return is never held behind data.
  rr_arb      accept-then-arbitrate round-robin arbiter: a 1-entry hold
              register per input (ready = slot empty), a rotated mask,
              one_hot, and priority_sel over (data, index) tuples.
  arb_credit  rr_arb -> in-package chan (depth 2) -> credit_tx under one top
              proc (proc_instantiation), for --multi_proc codegen.

Node ids are unique per package, so each proc takes a starting id (``id0``).
"""


def _ci(name: str, direction: str, kind: str = "streaming", fc: str = "ready_valid") -> str:
    return (f"  chan_interface {name}(direction={direction}, kind={kind}, "
            f"strictness=proven_mutually_exclusive, flow_control={fc}, flop_kind=none)")


class _Ids:
    def __init__(self, start: int = 1):
        self.n = start

    def __call__(self) -> int:
        n, self.n = self.n, self.n + 1
        return n


def credit_tx(width: int = 8, credits: int = 4, cbits: int = 4, name: str = "credit_tx",
              top: bool = True, ports=("data_in", "cred_in", "data_out"),
              id0: int = 1) -> str:
    din, cin, dout = ports
    i = _Ids(id0)
    L = [f"{'top ' if top else ''}proc {name}<{din}: bits[{width}] in, {cin}: bits[1] in, "
         f"{dout}: bits[{width}] out>(credits: bits[{cbits}], init={{{credits}}}) {{",
         _ci(din, "receive"), _ci(cin, "receive"), _ci(dout, "send"),
         f"  credits: bits[{cbits}] = state_read(state_element=credits, id={i()})",
         f"  tok0: token = after_all(id={i()})",
         f"  one1: bits[1] = literal(value=1, id={i()})",
         f"  czero: bits[{cbits}] = literal(value=0, id={i()})",
         f"  cone: bits[{cbits}] = literal(value=1, id={i()})",
         f"  have: bits[1] = ne(credits, czero, id={i()})",
         f"  rd: (token, bits[{width}], bits[1]) = receive(tok0, predicate=have, "
         f"channel={din}, blocking=false, id={i()})",
         f"  rc: (token, bits[1], bits[1]) = receive(tok0, predicate=one1, "
         f"channel={cin}, blocking=false, id={i()})",
         f"  dtok: token = tuple_index(rd, index=0, id={i()})",
         f"  d: bits[{width}] = tuple_index(rd, index=1, id={i()})",
         f"  dv: bits[1] = tuple_index(rd, index=2, id={i()})",
         f"  rv: bits[1] = tuple_index(rc, index=2, id={i()})",
         f"  stok: token = send(dtok, d, predicate=dv, channel={dout}, id={i()})",
         f"  ndv: bits[1] = not(dv, id={i()})",
         f"  nrv: bits[1] = not(rv, id={i()})",
         f"  up: bits[1] = and(rv, ndv, id={i()})",
         f"  down: bits[1] = and(dv, nrv, id={i()})",
         f"  inc: bits[{cbits}] = add(credits, cone, id={i()})",
         f"  dec: bits[{cbits}] = sub(credits, cone, id={i()})",
         f"  nv_up: () = next_value(state_element=credits, value=inc, predicate=up, id={i()})",
         f"  nv_down: () = next_value(state_element=credits, value=dec, predicate=down, "
         f"id={i()})",
         "}"]
    return "\n".join(L) + "\n"


def rr_arb(n: int = 4, width: int = 8, name: str = "rr_arb", top: bool = True,
           ins=None, out: str = "arb_out", id0: int = 1) -> str:
    ins = list(ins or [f"in{k}" for k in range(n)])
    ib = max(1, (n - 1).bit_length())
    ow = width + ib
    i = _Ids(id0)
    st = [f"hv: bits[{n}]"] + [f"h{k}: bits[{width}]" for k in range(n)] + [f"last: bits[{n}]"]
    init = ["0"] * (n + 1) + [str(1 << (n - 1))]     # last = top input: input 0 goes first
    chans = ", ".join([f"{c}: bits[{width}] in" for c in ins] + [f"{out}: bits[{ow}] out"])
    L = [f"{'top ' if top else ''}proc {name}<{chans}>({', '.join(st)}, init={{{', '.join(init)}}}) {{"]
    L += [_ci(c, "receive") for c in ins] + [_ci(out, "send")]
    L += [f"  hv: bits[{n}] = state_read(state_element=hv, id={i()})",
          f"  last: bits[{n}] = state_read(state_element=last, id={i()})",
          f"  tok0: token = after_all(id={i()})"]
    for k, c in enumerate(ins):
        L += [f"  h{k}: bits[{width}] = state_read(state_element=h{k}, id={i()})",
              f"  hv{k}: bits[1] = bit_slice(hv, start={k}, width=1, id={i()})",
              f"  free{k}: bits[1] = not(hv{k}, id={i()})",
              f"  r{k}: (token, bits[{width}], bits[1]) = receive(tok0, predicate=free{k}, "
              f"channel={c}, blocking=false, id={i()})",
              f"  rt{k}: token = tuple_index(r{k}, index=0, id={i()})",
              f"  rd{k}: bits[{width}] = tuple_index(r{k}, index=1, id={i()})",
              f"  rv{k}: bits[1] = tuple_index(r{k}, index=2, id={i()})",
              f"  v{k}: bits[1] = or(hv{k}, rv{k}, id={i()})",
              f"  d{k}: bits[{width}] = sel(hv{k}, cases=[rd{k}, h{k}], id={i()})",
              f"  ix{k}: bits[{ib}] = literal(value={k}, id={i()})",
              f"  t{k}: (bits[{width}], bits[{ib}]) = tuple(d{k}, ix{k}, id={i()})"]
    vs = ", ".join(f"v{k}" for k in reversed(range(n)))
    ts = ", ".join(f"t{k}" for k in range(n))
    rts = ", ".join(f"rt{k}" for k in range(n))
    L += [f"  req: bits[{n}] = concat({vs}, id={i()})",
          f"  none: bits[{n}] = literal(value=0, id={i()})",
          f"  nonen: bits[{n}] = literal(value=1, id={i()})",
          # gt = the inputs above the last grant: ~((last << 1) - 1)
          f"  lsh: bits[{n}] = shll(last, nonen, id={i()})",
          f"  lm1: bits[{n}] = sub(lsh, nonen, id={i()})",
          f"  gt: bits[{n}] = not(lm1, id={i()})",
          f"  hi: bits[{n}] = and(req, gt, id={i()})",
          f"  anyhi: bits[1] = ne(hi, none, id={i()})",
          f"  src: bits[{n}] = sel(anyhi, cases=[req, hi], id={i()})",
          f"  oh: bits[{n + 1}] = one_hot(src, lsb_prio=true, id={i()})",
          f"  g: bits[{n}] = bit_slice(oh, start=0, width={n}, id={i()})",
          f"  anyv: bits[1] = ne(req, none, id={i()})",
          f"  z{width}: bits[{width}] = literal(value=0, id={i()})",
          f"  zi: bits[{ib}] = literal(value=0, id={i()})",
          f"  dflt: (bits[{width}], bits[{ib}]) = tuple(z{width}, zi, id={i()})",
          f"  ps: (bits[{width}], bits[{ib}]) = priority_sel(g, cases=[{ts}], default=dflt, "
          f"id={i()})",
          f"  od: bits[{width}] = tuple_index(ps, index=0, id={i()})",
          f"  oi: bits[{ib}] = tuple_index(ps, index=1, id={i()})",
          f"  ov: bits[{ow}] = concat(oi, od, id={i()})",
          f"  rtok: token = after_all({rts}, id={i()})",
          f"  stok: token = send(rtok, ov, predicate=anyv, channel={out}, id={i()})",
          f"  ng: bits[{n}] = not(g, id={i()})",
          f"  nhv: bits[{n}] = and(req, ng, id={i()})",
          f"  nlast: bits[{n}] = sel(anyv, cases=[last, g], id={i()})",
          f"  nv_hv: () = next_value(state_element=hv, value=nhv, id={i()})",
          f"  nv_last: () = next_value(state_element=last, value=nlast, id={i()})"]
    L += [f"  nv_h{k}: () = next_value(state_element=h{k}, value=d{k}, id={i()})"
          for k in range(n)]
    L.append("}")
    return "\n".join(L) + "\n"


def arb_credit(n: int = 4, width: int = 8, credits: int = 4, depth: int = 2,
               bypass: bool = False) -> str:
    ib = max(1, (n - 1).bit_length())
    ow = width + ib
    ins = [f"in{k}" for k in range(n)]
    arb = rr_arb(n, width, name="rr_arb", top=False, ins=[f"a_{c}" for c in ins], out="a_out",
                 id0=1)
    ctx = credit_tx(ow, credits, name="credit_tx", top=False,
                    ports=("c_in", "c_cred", "c_out"), id0=500)
    chans = ", ".join([f"{c}: bits[{width}] in" for c in ins] +
                      ["cred_in: bits[1] in", f"data_out: bits[{ow}] out"])
    L = [f"top proc arb_credit<{chans}>(st: (), init={{()}}) {{"]
    L += [_ci(c, "receive") for c in ins] + [_ci("cred_in", "receive"), _ci("data_out", "send")]
    L += [f"  chan mid(bits[{ow}], id=0, kind=streaming, ops=send_receive, "
          f"flow_control=ready_valid, strictness=proven_mutually_exclusive, "
          f"fifo_depth={depth}, bypass={'true' if bypass else 'false'}, "
          f"register_push_outputs=false, register_pop_outputs=false)",
          _ci("mid", "send"), _ci("mid", "receive"),
          f"  proc_instantiation arb_inst({', '.join(ins)}, mid, proc=rr_arb)",
          "  proc_instantiation ctx_inst(mid, cred_in, data_out, proc=credit_tx)",
          "  st: () = state_read(state_element=st, id=1000)",
          "  u: () = tuple(id=1001)",
          "  nv: () = next_value(state_element=st, value=u, id=1002)",
          "}"]
    return arb + "\n" + ctx + "\n" + "\n".join(L) + "\n"


def package(name: str, *procs: str) -> str:
    return f"package {name}\n\n" + "\n".join(procs)
