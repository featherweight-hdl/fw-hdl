"""pre == post equivalence for the co-synthesis pass (fw.hdl.cosynth.rewrite).

1. X6 lemma (combinational, ABC iprove on the real stage modules, composed):
     S(key, 0, blk) == S({0, key[127:0]}, 0, blk),  S = stage1 o stage0
   plus a sanity mutant (zero key[127:0] instead) that must FAIL.
2. Sequential harness (SBY) of the pre top and the post top with abstract
   stages (the same abstraction in both):
     stage0 = injective normalize: {kw==0 ? {0,key[127:0]} : key, kw, block}
              (sound for the real stage 0 by the X6 lemma),
     stage<s>, s>0 = projection (concat of inputs >> OFF) -- one proof per OFF,
              the OFFs together cover every bit of the stage input.
   Assumptions (the contract clauses, restated at the core pins):
     input_valid only when not busy (C1.one_in_flight),
     key/key_width/block equal to their values at op start while busy
     (C3.key_stable_op, C3.mode_fixed, C1.block_stable), key_width == 0 (X6).
   Assertion: post output_valid/out equal pre's, shifted by the latency
   difference (1 if v0 was folded); out compared only when output_valid.
   Mutants: wrong latency shift must FAIL; without the key/block stability
   assumptions the proof must FAIL unless v0 was folded.
"""
import json
import os
import re
import subprocess
import time

from .rewrite import parse_v5


def _top_text(text, mod, newname):
    m = re.search(r'^module %s\(.*?^endmodule' % re.escape(mod), text, re.M | re.S)
    return re.sub(r'^module %s\(' % re.escape(mod), 'module %s(' % newname, m.group(0), count=1)


def _run(cmd, cwd, log, timeout):
    t0 = time.monotonic()
    try:
        with open(log, 'w') as f:
            rc = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        rc = 'timeout'
    return rc, round(time.monotonic() - t0, 1)


def _lemma(pre, mod, stages, outdir, timeout, mutant=False):
    """X6 lemma over the composed stages (stage<S-1> o ... o stage0, no flops):
    with key_width=0 the result does not depend on key[255:128]. (Stage 0 alone
    is NOT invariant: some of its outputs carry key words that the last stage
    ignores for AES-128.) Proved by ABC `iprove` on the miter AIG."""
    ins0 = stages[0][0]
    key_w = dict(ins0)['r_key']
    blk_w = dict(ins0)['r_block_']
    lo = 128
    k2 = ("{%d'b0, key[%d:0]}" % (key_w - lo, lo - 1)) if not mutant else \
         ("{key[%d:%d], %d'b0}" % (key_w - 1, lo, lo))
    ow = sum(w for _, w in stages[-1][1])
    def chain(n, k):
        t = []
        for s, (ins, outs) in enumerate(stages):
            for nm, w in outs:
                t.append('    wire [%d:0] %s_s%d_%s;' % (w - 1, n, s, nm[2:]))
            c = []
            for nm, w in ins:
                if s == 0:
                    v = {'r_key': k, 'r_key_width': "2'b0", 'r_block_': 'blk'}[nm]
                else:
                    v = '%s_s%d_%s' % (n, s - 1, nm[2:])
                c.append('.%s(%s)' % (nm, v))
            c += ['.%s(%s_s%d_%s)' % (nm, n, s, nm[2:]) for nm, _ in outs]
            t.append('    %s__stage%d u_%s%d(%s);' % (mod, s, n, s, ', '.join(c)))
        return '\n'.join(t) + '\n', '%s_s%d_%s' % (n, len(stages) - 1, stages[-1][1][0][0][2:])
    name = 'x6_lemma' + ('_mut' if mutant else '')
    sv = os.path.join(outdir, name + '.sv')
    ta, oa = chain('a', 'key')
    tb, ob = chain('b', k2)
    with open(sv, 'w') as f:
        f.write('module %s(input [%d:0] key, input [%d:0] blk, output bad);\n' % (name, key_w - 1, blk_w - 1))
        f.write(ta + tb + '    assign bad = (%s != %s);\nendmodule\n' % (oa, ob))
    aig = os.path.join(outdir, name + '.aig')
    ys = os.path.join(outdir, name + '.ys')
    with open(ys, 'w') as f:
        f.write('read_verilog -sv %s %s\nhierarchy -top %s\nproc\nflatten\nopt\ntechmap\nopt -fast\n'
                'aigmap\nwrite_aiger -zinit %s\n' % (pre, sv, name, aig))
    t0 = time.monotonic()
    rc, _ = _run(['yosys', '-q', '-l', os.path.join(outdir, name + '.log'), ys], outdir,
                 os.path.join(outdir, name + '.out'), timeout)
    st = 'ERROR(yosys rc=%s)' % rc
    if rc == 0:
        rc2, _ = _run(['yosys-abc', '-c', 'read_aiger %s; strash; print_stats; iprove -v' % aig], outdir,
                      os.path.join(outdir, name + '.abc.log'), timeout)
        t = open(os.path.join(outdir, name + '.abc.log')).read()
        if rc2 == 'timeout':
            st = 'TIMEOUT'
        elif re.search(r'Networks are equivalent|UNSAT|proved', t, re.I) and 'NOT' not in t:
            st = 'PASS'
        elif re.search(r'NOT equivalent|SATISFIABLE|disproved|counter', t, re.I):
            st = 'FAIL'
        else:
            st = 'UNKNOWN(rc=%s)' % rc2
    return {'status': st, 'seconds': round(time.monotonic() - t0, 1),
            'kind': 'combinational, composed stages, ABC iprove (unbounded)',
            'expect': 'FAIL' if mutant else 'PASS', 'files': [os.path.basename(sv), os.path.basename(ys)]}


def _abstract(mod, stages, off):
    L = []
    for s, (ins, outs) in enumerate(stages):
        iw = sum(w for _, w in ins)
        ow = sum(w for _, w in outs)
        ports = ['input wire [%d:0] %s' % (w - 1, n) for n, w in ins] + \
                ['output wire [%d:0] %s' % (w - 1, n) for n, w in outs]
        L.append('module %s__stage%d(%s);' % (mod, s, ', '.join(ports)))
        if s == 0:
            names = [n for n, _ in ins]
            kw = 'r_key_width'
            key_w = dict(ins)['r_key']
            L.append("    wire [%d:0] k = (%s == 0) ? {%d'b0, r_key[127:0]} : r_key;" % (key_w - 1, kw, key_w - 128))
            cat = '{' + ', '.join('k' if n == 'r_key' else n for n in names) + '}'
            L.append('    wire [%d:0] c = %s;' % (iw - 1, cat))
            L.append('    assign {%s} = %d\'(c);' % (', '.join(n for n, _ in outs), ow))
        else:
            cat = '{' + ', '.join(n for n, _ in ins) + '}'
            L.append('    wire [%d:0] c = %s;' % (iw - 1, cat))
            L.append('    assign {%s} = %d\'(c >> %d);' % (', '.join(n for n, _ in outs), ow, off))
        L.append('endmodule')
    return '\n'.join(L) + '\n'


def _harness(shift, stable=True):
    a = []
    a.append('module cs_equiv(input clk, input input_valid, input [255:0] key, input [1:0] key_width,')
    a.append('                input [127:0] block_);')
    a.append('    reg init = 1\'b1; reg [1:0] age = 2\'d0;')
    a.append('    always @(posedge clk) begin init <= 1\'b0; if (age != 2\'d3) age <= age + 2\'d1; end')
    a.append('    wire rst = init;')
    a.append('    wire pre_ov, post_ov; wire [127:0] pre_out, post_out;')
    a.append('    pre_top  u_pre (.clk(clk), .rst(rst), .input_valid(input_valid), .key(key), .key_width(key_width), .block_(block_), .output_valid(pre_ov), .out(pre_out));')
    a.append('    post_top u_post(.clk(clk), .rst(rst), .input_valid(input_valid), .key(key), .key_width(key_width), .block_(block_), .output_valid(post_ov), .out(post_out));')
    a.append('    reg busy; reg [255:0] key_q; reg [127:0] blk_q;')
    a.append('    always @(posedge clk) begin')
    a.append('        if (rst) busy <= 1\'b0;')
    a.append('        else if (input_valid) begin busy <= 1\'b1; key_q <= key; blk_q <= block_; end')
    a.append('        else if (pre_ov) busy <= 1\'b0;')
    a.append('    end')
    a.append('    always @* begin')
    a.append('        assume (key_width == 2\'d0);                         // X6 premise (MODE=0)')
    a.append('        if (init) assume (!input_valid);')
    a.append('        if (!init && busy) assume (!input_valid);           // C1.one_in_flight')
    if stable:
        a.append('        if (!init && busy) assume (key == key_q);           // C3.key_stable_op')
        a.append('        if (!init && busy) assume (block_ == blk_q);        // C1.block_stable')
    a.append('    end')
    if shift:
        a.append('    reg post_ov_d; reg [127:0] post_out_d;')
        a.append('    always @(posedge clk) begin post_ov_d <= post_ov; post_out_d <= post_out; end')
        a.append('    always @* if (age >= 2\'d2) begin')
        a.append('        assert (post_ov_d == pre_ov);')
        a.append('        if (pre_ov) assert (post_out_d == pre_out);')
        a.append('    end')
    else:
        a.append('    always @* if (age >= 2\'d1) begin')
        a.append('        assert (post_ov == pre_ov);')
        a.append('        if (pre_ov) assert (post_out == pre_out);')
        a.append('    end')
    a.append('endmodule')
    return '\n'.join(a) + '\n'


def _sby(outdir, name, files, engine, depth):
    mode = 'prove'
    eng = engine
    if engine.startswith('smtbmc'):
        pass
    with open(os.path.join(outdir, name + '.sby'), 'w') as f:
        f.write('[options]\nmode %s\ndepth %d\n\n[engines]\n%s\n\n[script]\n' % (mode, depth, eng))
        f.write('read -formal %s\nprep -top cs_equiv\n\n[files]\n' % ' '.join(os.path.basename(x) for x in files))
        for x in files:
            f.write('%s\n' % x)


def _sby_status(outdir, name, rc):
    st_file = os.path.join(outdir, name, 'status')
    if rc == 'timeout':
        return 'TIMEOUT'
    lg = os.path.join(outdir, name + '.log')
    if os.path.exists(lg) and 'returned FAIL' in open(lg).read():
        return 'FAIL'  # pdr counterexample; SBY cannot replay it without yices (aigsmt)
    if os.path.exists(st_file):
        s = open(st_file).read().split()
        return s[0] if s else 'UNKNOWN'
    return 'ERROR(rc=%s)' % rc


def run(pre, post, report, outdir, timeout=600, engine='abc pdr'):
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(outdir, exist_ok=True)
    outdir = os.path.abspath(outdir)
    pre, post, report = (os.path.abspath(x) for x in (pre, post, report))
    with open(report) as f:
        rep = json.load(f)
    mod = rep['module']
    pre_text = open(pre).read()
    post_text = open(post).read()
    _, stages, _ = parse_v5(pre_text, mod)
    shift = rep['pre']['latency'] - rep['post']['latency']
    tops = os.path.join(outdir, 'tops.sv')
    with open(tops, 'w') as f:
        f.write(_top_text(pre_text, mod, 'pre_top') + '\n' + _top_text(post_text, rep.get('top', mod), 'post_top') + '\n')
    last_in = sum(w for _, w in stages[-1][0])
    last_out = sum(w for _, w in stages[-1][1])
    offs = sorted(set(list(range(0, last_in - last_out + 1, last_out)) + [last_in - last_out]))
    jobs = {}
    fold = rep['post'].get('v0_folded', False)
    variants = [('seq_off%d' % o, o, True, shift, 'PASS') for o in offs]
    # mutants: wrong latency shift must FAIL (assertions are live); without the
    # key/block stability assumptions the proof must FAIL unless v0 was folded
    # (then pre and post both sample key/block in the input_valid cycle).
    variants.append(('seq_off0_mut_shift', 0, True, 1 - shift if shift in (0, 1) else 0, 'FAIL'))
    direct = any(x in rep['applied'] for x in ('X1', 'X2'))
    variants.append(('seq_off128_mut_nostable', 128, False, shift, 'FAIL' if direct and not fold else 'PASS'))
    for name, off, stable, sh, exp in variants:
        ab = os.path.join(outdir, name + '_stages.sv')
        with open(ab, 'w') as f:
            f.write(_abstract(mod, stages, off))
        hv = os.path.join(outdir, name + '_harness.sv')
        with open(hv, 'w') as f:
            f.write(_harness(sh, stable))
        _sby(outdir, name, [ab, tops, hv], engine, 20)
        jobs[name] = exp
    res = {'shift': shift, 'offsets': offs, 'engine': engine, 'checks': {}}

    def go_seq(name):
        rc, secs = _run(['sby', '-f', name + '.sby'], outdir, os.path.join(outdir, name + '.log'), timeout)
        return name, {'status': _sby_status(outdir, name, rc), 'seconds': secs, 'expect': jobs[name],
                      'kind': 'sequential, abstract stages, sby prove, %s (unbounded if PASS)' % engine}

    with ThreadPoolExecutor(max_workers=6) as ex:
        fl = ex.submit(_lemma, pre, mod, stages, outdir, timeout, False)
        fm = ex.submit(_lemma, pre, mod, stages, outdir, timeout, True)
        seqs = [ex.submit(go_seq, n) for n in jobs]
        res['checks']['x6_lemma'] = fl.result()
        res['checks']['x6_lemma_mut_lowhalf'] = fm.result()
        for s in seqs:
            n, r = s.result()
            res['checks'][n] = r
    # a check "passes" when it matched its expected verdict
    for k, v in res['checks'].items():
        v['verdict'] = v['status']
        v['status'] = 'PASS' if v['verdict'] == v['expect'] else 'MISMATCH(%s, expect %s)' % (v['verdict'], v['expect'])
    with open(os.path.join(outdir, 'equiv.json'), 'w') as f:
        json.dump(res, f, indent=1)
    return res
