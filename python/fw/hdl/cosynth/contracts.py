"""Contract records (sidecar YAML) -> SBY proof tasks on the implementing side.

Record format (see fw-aes src/cosynth/contracts.yaml):

  module: <implementing RTL module>      params: {..}   clock: clk   reset: rst
  aux:  <Verilog: checker state over the module's ports>
  env:  [{id, text, check}]              # assumptions on the free environment
  contracts:
    - id: C1  name: ..  channel|csr: ..  implemented_by: ..  consumed_by: [X..]
      clauses: [{id: C1.x, text: .., check: <Verilog bool, $past/$stable ok>}]

For each contract, `gen_sby` writes a checker module that instantiates the
implementing module with every input free, adds `aux`, assumes `env` and reset
in the first cycle, and asserts every clause (label = clause id). The proof is
unbounded (`mode prove`, abc pdr by default).
"""
import json
import os
import re
import subprocess
import yaml

_PORT_RE = re.compile(r'^\s*(input|output)\s+logic\s*(\[[^\]]+\])?\s*(\w+)', re.M)


def load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def module_ports(sv_text, module):
    m = re.search(r'module\s+%s\b(.*?)\);' % re.escape(module), sv_text, re.S)
    if m is None:
        raise RuntimeError('module %s not found' % module)
    return [(d, w or '', n) for d, w, n in _PORT_RE.findall(m.group(1))]


def _expr(check):
    """`a -> b` (one top-level implication) to plain Verilog."""
    if '->' in check:
        a, b = check.split('->', 1)
        return '!(%s) || (%s)' % (a.strip(), b.strip())
    return check


def _guard(check, rst):
    """Checks that look back one cycle start one cycle after reset."""
    return ' && !$past(%s)' % rst if ('$past' in check or '$stable' in check) else ''


def _label(cid):
    return re.sub(r'\W', '_', cid)


def gen_checker(rec, contract, ports, params=None):
    p = dict(rec.get('params', {}))
    p.update(params or {})
    clk, rst = rec.get('clock', 'clk'), rec.get('reset', 'rst')
    name = 'chk_' + _label(contract['id'])
    L = ['module %s(' % name]
    L.append(',\n'.join('    input logic %s %s' % (w, n) for d, w, n in ports if d == 'input'))
    L.append(');')
    for d, w, n in ports:
        if d == 'output':
            L.append('    logic %s %s;' % (w, n))
    ps = ', '.join('.%s(%s)' % (k, v) for k, v in p.items())
    L.append('    %s #(%s) dut(%s);' % (rec['module'], ps, ', '.join('.%s(%s)' % (n, n) for _, _, n in ports)))
    L.append(rec.get('aux', ''))
    L.append('    logic past_valid = 1\'b0;')
    L.append('    always_ff @(posedge %s) past_valid <= 1\'b1;' % clk)
    L.append('    always @(*) if (!past_valid) assume(%s); else assume(!%s);' % (rst, rst))
    for e in rec.get('env', []):
        L.append('    // env %s: %s' % (e['id'], e.get('text', '')))
        L.append('    always @(posedge %s) if (past_valid && !%s%s) %s: assume(%s);'
                 % (clk, rst, _guard(e['check'], rst), _label(e['id']), _expr(e['check'])))
    for c in contract['clauses']:
        L.append('    // %s: %s' % (c['id'], c.get('text', '')))
        L.append('    always @(posedge %s) if (past_valid && !%s%s) %s: assert(%s);'
                 % (clk, rst, _guard(c['check'], rst), _label(c['id']), _expr(c['check'])))
    L.append('endmodule')
    return name, '\n'.join(L) + '\n'


def gen_sby(rec, contract, sv_files, outdir, params=None, tag=None):
    engine = contract.get('engine', 'abc pdr')
    mode = contract.get('mode', 'prove')
    if 'depth' in contract:
        mode += '\ndepth %d' % contract['depth']
    with open(sv_files[0]) as f:
        ports = module_ports(f.read(), rec['module'])
    top, text = gen_checker(rec, contract, ports, params)
    tag = tag or contract['id']
    os.makedirs(outdir, exist_ok=True)
    chk = os.path.join(outdir, '%s.sv' % top)
    with open(chk, 'w') as f:
        f.write(text)
    files = [os.path.abspath(s) for s in sv_files] + [os.path.abspath(chk)]
    sby = os.path.join(outdir, '%s.sby' % tag)
    with open(sby, 'w') as f:
        f.write('[options]\nmode %s\n\n[engines]\n%s\n\n[script]\n' % (mode, engine))
        f.write('read -formal %s\nprep -top %s\nsetundef -zero\n\n[files]\n' %
                (' '.join(os.path.basename(x) for x in files), top))
        f.write('\n'.join(files) + '\n')
    return sby


def run_sby(sby, timeout=1800):
    d = os.path.dirname(sby)
    r = subprocess.run(['sby', '-f', os.path.basename(sby)], cwd=d,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    log = r.stdout
    status = 'PASS' if re.search(r'DONE \(PASS', log) else ('FAIL' if re.search(r'DONE \(FAIL', log) else 'ERROR')
    if status == 'ERROR' and re.search(r'returned FAIL', log):
        status = 'FAIL'   # engine found a counterexample; trace replay failed (no yices here)
    failed = sorted(set(re.findall(r'Assert(?:ion)? failed in \S+: (\S+)', log) +
                        re.findall(r'Property ASSERT in \S+ at \S+ \((\S+)\)? failed', log)))
    m = re.search(r'summary: Elapsed clock time \[H:MM:SS \(secs\)\]: \S+ \((\d+)\)', log)
    with open(sby[:-4] + '.log', 'w') as f:
        f.write(log)
    return {'status': status, 'failed': failed, 'secs': int(m.group(1)) if m else None}


def prove_all(rec_path, sv_files, outdir, mutants=()):
    """Prove every contract; `mutants` = [(tag, contract_id, params, expect)]."""
    rec = load(rec_path)
    res = {'module': rec['module'], 'contracts': {}, 'mutants': {}}
    for c in rec['contracts']:
        r = run_sby(gen_sby(rec, c, sv_files, outdir))
        r['clauses'] = {cl['id']: ('FAIL' if _label(cl['id']) in r['failed'] else r['status'])
                        for cl in c['clauses']}
        r['consumed_by'] = c.get('consumed_by', [])
        r['mode'] = c.get('mode', 'prove') + (' depth %d' % c['depth'] if 'depth' in c else '')
        res['contracts'][c['id']] = r
    for tag, cid, params, expect in mutants:
        c = next(x for x in rec['contracts'] if x['id'] == cid)
        r = run_sby(gen_sby(rec, c, sv_files, outdir, params=params, tag=tag))
        r.update({'contract': cid, 'params': params, 'expect': expect, 'ok': r['status'] == expect})
        res['mutants'][tag] = r
    with open(os.path.join(outdir, 'contracts_proof.json'), 'w') as f:
        json.dump(res, f, indent=1)
    return res
