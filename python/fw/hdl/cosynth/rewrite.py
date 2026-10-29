"""Co-synthesis pass over a lowered V5 pipeline (synth.xls.Lower output).

Input: the V5 SystemVerilog (``<m>__stage<s>`` combinational modules plus the
pipeline top ``<m>``), the Lower ``structure.json`` (register model per
boundary) and the contract records (contracts.yaml). The pass keeps the stage
modules verbatim and writes a new top. Each transformation (X*) is applied
only if the contract clauses it relies on exist in the records and name the
X in ``consumed_by``; the report records the change and the clause ids.

Transformations (A0 = 2-stage, fully unrolled encrypt):
  X6  AES-128 only: key_width tied 0, key[255:128] tied 0 at stage 0.
  X2  no key flops: stage 0 reads the CSR key (and key_width) directly.
  X1  no block flops: stage 0 reads the channel buffer directly. If no input
      flop remains, v0 is folded into input_valid (latency - 1).
  X3  no load enables on the inner pipeline registers, no reset on data
      registers (valid bits keep their reset).
  X5  resource sharing: N/A for a fully unrolled schedule (recorded only).
"""
import json
import re
from typing import Dict, List, Tuple

ALL_X = ['X6', 'X2', 'X1', 'X3', 'X5']

# X -> (contract clause ids relied on, rationale)
REASONS = {
    'X6': (['C3.mode_fixed', 'C3.key_stable_op'],
           'MODE is fixed after the first START (C3.mode_fixed) and the host programs AES-128 '
           '(MODE=0, host assumption, not proved); with key_width=0 stage 0 does not depend on '
           'key[255:128] (combinational lemma, cosynth equiv)'),
    'X2': (['C3.key_stable_op', 'C3.key_stable_busy', 'C3.mode_fixed'],
           'the key (and MODE) at the core equals the key at op start for the whole op, so '
           'the input flops hold a copy of a value that does not change while it is used'),
    'X1': (['C1.block_stable', 'C1.one_in_flight'],
           'the block is not changed while the op is in flight and only one op is in flight, '
           'so the block input flops hold a copy of a stable value'),
    'X3': (['C1.one_in_flight', 'C2.store_after_result'],
           'one op in flight and the result is read only after output_valid: inner pipeline '
           'registers may load every cycle (their consumer is enabled by the next valid) and '
           'data registers need no reset (only valid bits are observed before a result)'),
    'X5': (['C3.key_stable_busy'],
           'N/A for A0: the schedule is fully unrolled (2 stages, one op per 4 clk); there is '
           'no repeated round hardware to share. Needs A2/A3.'),
}


def _clause_index(records: dict) -> Dict[str, List[str]]:
    """clause id -> list of X ids that the clause's contract is consumed_by."""
    idx = {}
    for c in records.get('contracts', []):
        for cl in c.get('clauses', []):
            idx[cl['id']] = list(c.get('consumed_by', []))
    return idx


def parse_v5(text: str, mod: str):
    """Return (prefix text with the stage modules, [stage ports], top ports)."""
    m = re.search(r'^module %s\(' % re.escape(mod), text, re.M)
    if not m:
        raise ValueError('top module %s not found' % mod)
    prefix = text[:m.start()]
    stages = []
    s = 0
    while True:
        sm = re.search(r'^module %s__stage%d\((.*?)\);' % (re.escape(mod), s), prefix, re.M | re.S)
        if not sm:
            break
        ins, outs = [], []
        for d, hi, nm in re.findall(r'(input|output)\s+wire\s+\[(\d+):0\]\s+(\w+)', sm.group(1)):
            (ins if d == 'input' else outs).append((nm, int(hi) + 1))
        stages.append((ins, outs))
        s += 1
    tm = re.search(r'^module %s\((.*?)\);' % re.escape(mod), text[m.start():], re.M | re.S)
    tports = []
    for d, w, nm in re.findall(r'(input|output)\s+wire\s+(?:\[(\d+):0\]\s+)?(\w+)', tm.group(1)):
        tports.append((d, nm, int(w) + 1 if w else 1))
    return prefix, stages, tports


def build_top(mod: str, top_name: str, stages, tports, xs: List[str], key_lo_bits=128):
    """Write the rewritten top. Returns (sv text, facts dict)."""
    xs = set(xs)
    S = len(stages)
    tp = {nm: w for _, nm, w in tports}
    L = []
    w = L.append
    facts = {'removed_flops': [], 'removed_flop_bits': 0, 'resets_dropped': [], 'enables_dropped': []}
    hdr = ',\n    '.join('%s  wire %s%s' % (d.ljust(6), '' if wd == 1 else '[%d:0] ' % (wd - 1), nm)
                         for d, nm, wd in tports)
    w('// Co-synthesis rewrite of %s (fw.hdl.cosynth pass): %s' % (mod, ', '.join(sorted(xs)) or 'none'))
    w('// Stage modules %s__stage0..%d are reused unchanged.' % (mod, S - 1))
    w('module %s(\n    %s\n);' % (top_name, hdr))
    # ---- stage 0 sources
    s0_in = stages[0][0]
    src = {}
    in_flops = []
    for nm, wd in s0_in:
        port = nm[2:]  # r_key -> key
        kind = 'key' if port in ('key', 'key_width') else 'block'
        if port == 'key_width' and 'X6' in xs:
            src[nm] = "%d'b0" % wd
            facts['removed_flops'].append('in_key_width (X6: tied 0)')
            facts['removed_flop_bits'] += wd
            continue
        eff_w = wd
        if port == 'key' and 'X6' in xs:
            eff_w = key_lo_bits
        direct = (kind == 'key' and 'X2' in xs) or (kind == 'block' and 'X1' in xs)
        if direct:
            val = '%s[%d:0]' % (port, eff_w - 1)
            facts['removed_flops'].append('in_%s (%s)' % (port, 'X2' if kind == 'key' else 'X1'))
            facts['removed_flop_bits'] += wd
        else:
            in_flops.append(('in_' + port, port, eff_w))
            val = 'in_%s' % port
            facts['removed_flop_bits'] += wd - eff_w
        if eff_w != wd:
            val = "{%d'b0, %s}" % (wd - eff_w, val)
            facts['removed_flops'].append('in_%s[%d:%d] (X6: tied 0)' % (port, wd - 1, eff_w))
        src[nm] = val
    fold = not in_flops
    facts['v0_folded'] = fold
    if fold:
        w('    // no input flops remain: stage 0 runs in the input_valid cycle (v0 folded, latency -1)')
        w('    wire v0 = input_valid;')
    else:
        w('    logic v0;')
    for r, port, ew in in_flops:
        w('    logic [%d:0] %s;' % (ew - 1, r))
    # ---- inner registers p<b> and stage instances
    for s, (ins, outs) in enumerate(stages):
        for nm, wd in outs:
            w('    wire [%d:0] n%d_%s;' % (wd - 1, s + 1, nm[2:]))
        if s + 1 < S:
            w('    logic v%d;' % (s + 1))
            for nm, wd in outs:
                w('    logic [%d:0] p%d_%s;' % (wd - 1, s + 1, nm[2:]))
    w('    logic v%d;' % S)
    ow = stages[-1][1][0][1]
    w('    logic [%d:0] out_flop;' % (ow - 1))
    for s, (ins, outs) in enumerate(stages):
        conns = []
        for nm, wd in ins:
            conns.append('.%s(%s)' % (nm, src[nm] if s == 0 else 'p%d_%s' % (s, nm[2:])))
        for nm, wd in outs:
            conns.append('.%s(n%d_%s)' % (nm, s + 1, nm[2:]))
        w('    %s__stage%d u_stage%d(\n        %s);' % (mod, s, s, ',\n        '.join(conns)))
    # ---- registers
    x3 = 'X3' in xs
    w('    always_ff @(posedge clk) begin')
    w('        if (rst) begin')
    if not fold:
        w('            v0 <= 1\'b0;')
    for s in range(1, S + 1):
        w('            v%d <= 1\'b0;' % s)
    if not x3:
        for r, _, _ in in_flops:
            w('            %s <= \'0;' % r)
        for s in range(1, S):
            for nm, _ in stages[s - 1][1]:
                w('            p%d_%s <= \'0;' % (s, nm[2:]))
        w('            out_flop <= \'0;')
    w('        end else begin')
    if not fold:
        w('            v0 <= input_valid;')
    for s in range(1, S + 1):
        w('            v%d <= v%d;' % (s, s - 1))
    loads = []
    for r, port, ew in in_flops:
        loads.append('if (input_valid) %s <= %s[%d:0];' % (r, port, ew - 1))
    for s in range(1, S):
        en = '' if x3 else 'if (v%d) ' % (s - 1)
        for nm, _ in stages[s - 1][1]:
            loads.append('%sp%d_%s <= n%d_%s;' % (en, s, nm[2:], s, nm[2:]))
    loads.append('if (v%d) out_flop <= n%d_%s;' % (S - 1, S, stages[-1][1][0][0][2:]))
    if not x3:
        for l in loads:
            w('            ' + l)
    w('        end')
    w('    end')
    if x3:
        facts['resets_dropped'] = [r for r, _, _ in in_flops] + \
            ['p%d_*' % s for s in range(1, S)] + ['out_flop']
        facts['enables_dropped'] = ['p%d_*' % s for s in range(1, S)]
        w('    // data registers: no reset (X3)')
        w('    always_ff @(posedge clk) begin')
        for l in loads:
            w('        ' + l)
        w('    end')
    w('    assign output_valid = v%d;' % S)
    w('    assign out = out_flop;')
    w('endmodule')
    facts['latency'] = S + (0 if fold else 1)
    return '\n'.join(L) + '\n', facts


def run_pass(v5_path, structure_path, records_path, out_dir, xs=None, top_name=None):
    import os
    import yaml
    xs = list(ALL_X if xs is None else xs)
    with open(structure_path) as f:
        st = json.load(f)
    mod = st['module']
    with open(v5_path) as f:
        text = f.read()
    with open(records_path) as f:
        records = yaml.safe_load(f)
    idx = _clause_index(records)
    prefix, stages, tports = parse_v5(text, mod)
    if len(stages) != st['stages']:
        raise ValueError('structure.json says %d stages, V5 has %d' % (st['stages'], len(stages)))
    applied, report = [], []
    for x in xs:
        clauses, why = REASONS[x]
        missing = [c for c in clauses if c not in idx]
        unconsumed = [c for c in clauses if c in idx and x not in idx[c]]
        ent = {'x': x, 'clauses': clauses, 'reason': why}
        if missing:
            ent.update(status='skipped', detail='clauses not in records: %s' % missing)
        elif x == 'X5':
            ent.update(status='n/a', detail='A0: %d stages, nodes/stage %s, fully unrolled'
                       % (st['stages'], st['nodes_per_stage']))
        else:
            ent.update(status='applied')
            if unconsumed:
                ent['note'] = 'clause contract does not list %s in consumed_by: %s' % (x, unconsumed)
            applied.append(x)
        report.append(ent)
    top, facts = build_top(mod, top_name or mod, stages, tports, applied)
    pre_bits = sum(r['bits'] for r in st['registers'])
    changes = {
        'X6': 'key_width -> 0, key[255:128] -> 0 at stage 0',
        'X2': 'in_key/in_key_width flops removed; stage 0 reads key/key_width ports (CSR)',
        'X1': 'in_block_ flops removed; stage 0 reads block_ port (channel buffer)',
        'X3': 'p1_* load enables removed; data-register resets removed (valid resets kept)',
        'X5': 'none',
    }
    for ent in report:
        ent['change'] = changes[ent['x']] if ent['status'] == 'applied' else 'none'
    os.makedirs(out_dir, exist_ok=True)
    tag = ''.join(x for x in sorted(applied)) or 'none'
    sv = os.path.join(out_dir, '%s.cosynth.sv' % mod)
    with open(sv, 'w') as f:
        f.write('// fw.hdl.cosynth pass on %s: %s\n' % (os.path.basename(v5_path), ', '.join(applied)))
        f.write(prefix)
        f.write(top)
    rep = {'module': mod, 'top': top_name or mod, 'records': os.path.abspath(records_path),
           'v5_in': os.path.abspath(v5_path), 'structure': os.path.abspath(structure_path),
           'requested': xs, 'applied': applied, 'transforms': report,
           'pre': {'latency': st['latency'], 'register_bits': pre_bits},
           'post': {'latency': facts['latency'], 'register_bits_removed': facts['removed_flop_bits'],
                    'register_bits': pre_bits - facts['removed_flop_bits'],
                    'v0_folded': facts['v0_folded'], 'removed_flops': facts['removed_flops'],
                    'resets_dropped': facts['resets_dropped'], 'enables_dropped': facts['enables_dropped']},
           'output': os.path.abspath(sv)}
    if facts['v0_folded']:
        rep['transforms'].append({'x': 'X1+X2+X6 fold', 'status': 'applied',
                                  'clauses': ['C1.block_stable', 'C3.key_stable_op', 'C3.mode_fixed'],
                                  'reason': 'no input flop remains; v0 folded into input_valid',
                                  'change': 'latency %d -> %d' % (st['latency'], facts['latency'])})
    with open(os.path.join(out_dir, 'cosynth_pass.json'), 'w') as f:
        json.dump(rep, f, indent=1)
    with open(os.path.join(out_dir, 'cosynth_pass.md'), 'w') as f:
        f.write('# cosynth pass: %s (%s)\n\n| X | status | change | clauses | reason |\n|---|---|---|---|---|\n'
                % (mod, ', '.join(applied)))
        for e in rep['transforms']:
            f.write('| %s | %s | %s | %s | %s |\n' % (e['x'], e['status'], e['change'],
                                                     ', '.join(e['clauses']), e['reason']))
        f.write('\nlatency %d -> %d; register bits %d -> %d\n' % (
            st['latency'], facts['latency'], pre_bits, rep['post']['register_bits']))
    return rep
