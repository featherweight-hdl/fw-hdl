"""python -m fw.hdl.cosynth contracts|pass|equiv ...

  contracts <records.yaml> <outdir> <rtl.sv>... [--mutant TAG:CID:PARAM=V:EXPECT]
  pass <v5.sv> <structure.json> <records.yaml> <outdir> [--x X6,X2,X1,X3,X5] [--top NAME]
  equiv <pre_v5.sv> <post.sv> <cosynth_pass.json> <outdir> [--timeout S]
"""
import argparse
import json
from . import contracts


def main():
    ap = argparse.ArgumentParser(prog='fw.hdl.cosynth')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('contracts', help='prove every contract record with SBY')
    c.add_argument('records')
    c.add_argument('outdir')
    c.add_argument('rtl', nargs='+')
    c.add_argument('--mutant', action='append', default=[],
                   help='TAG:CONTRACT:PARAM=VALUE:EXPECT, e.g. C3_mut:C3:GATE_BUSY=0:FAIL')
    p = sub.add_parser('pass', help='rewrite a lowered V5 top under the contract records')
    p.add_argument('v5')
    p.add_argument('structure')
    p.add_argument('records')
    p.add_argument('outdir')
    p.add_argument('--x', default='X6,X2,X1,X3,X5', help='comma list of transformations ("" = none)')
    p.add_argument('--top', default=None, help='name of the rewritten top (default: same as pre)')
    e = sub.add_parser('equiv', help='pre==post: X6 lemma (Yosys SAT) + sequential harness (SBY)')
    e.add_argument('pre')
    e.add_argument('post')
    e.add_argument('report')
    e.add_argument('outdir')
    e.add_argument('--timeout', type=int, default=600)
    e.add_argument('--engine', default='abc pdr')
    a = ap.parse_args()
    if a.cmd == 'pass':
        from . import rewrite
        xs = [x for x in a.x.split(',') if x]
        r = rewrite.run_pass(a.v5, a.structure, a.records, a.outdir, xs, a.top)
        print(json.dumps({'applied': r['applied'], 'pre': r['pre'], 'post': {k: r['post'][k] for k in
                          ('latency', 'register_bits', 'v0_folded')}, 'output': r['output']}, indent=1))
        raise SystemExit(0)
    if a.cmd == 'equiv':
        from . import equiv
        r = equiv.run(a.pre, a.post, a.report, a.outdir, a.timeout, a.engine)
        print(json.dumps({k: v['status'] for k, v in r['checks'].items()}, indent=1))
        raise SystemExit(0 if all(v['status'] == 'PASS' for v in r['checks'].values()) else 1)
    muts = []
    for m in a.mutant:
        tag, cid, pv, exp = m.split(':')
        k, v = pv.split('=')
        muts.append((tag, cid, {k: int(v)}, exp))
    r = contracts.prove_all(a.records, a.rtl, a.outdir, muts)
    summ = {k: v['status'] for k, v in r['contracts'].items()}
    summ.update({k: '%s (expect %s)' % (v['status'], v['expect']) for k, v in r['mutants'].items()})
    print(json.dumps(summ, indent=1))
    ok = all(v['status'] == 'PASS' for v in r['contracts'].values()) and all(v['ok'] for v in r['mutants'].values())
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
