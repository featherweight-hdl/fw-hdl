"""python -m fw.hdl.cosynth contracts <records.yaml> <outdir> <rtl.sv>... [--mutant TAG:CID:PARAM=V:EXPECT]"""
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
    a = ap.parse_args()
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
