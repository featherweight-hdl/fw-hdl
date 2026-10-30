"""dv-flow pytask wrapper of the co-synthesis pass (fw.hdl.cosynth.rewrite).

Inputs: synth.xls.Lower's V5 (systemVerilogSource, attribute view=v5) and
xlsLowerStructure for `module`, and the contract records (a fileset of type
`cosynthRecords`). Output: systemVerilogSource with the rewritten V5
(`<m>.cosynth.sv`, attribute view=cosynth), the report (`cosynthReport`:
cosynth_pass.json/.md) and, with passthrough_other, the other modules' SV.
"""
import os
from dv_flow.mgr import FileSet, TaskDataInput, TaskDataResult, TaskMarker, SeverityE, TaskRunCtxt


def _err(msg):
    return TaskDataResult(status=1, changed=False, output=[],
                          markers=[TaskMarker(msg=msg, severity=SeverityE.Error)])


async def Pass(ctxt: TaskRunCtxt, input: TaskDataInput) -> TaskDataResult:
    from . import rewrite
    p = input.params
    mod = p.module
    v5 = struct = recs = None
    others = []
    for fs in getattr(input, 'inputs', []) or []:
        files = [os.path.join(fs.basedir, f) for f in fs.files]
        attrs = list(getattr(fs, 'attributes', []) or [])
        if fs.filetype == 'xlsLowerStructure' and ('module=%s' % mod) in attrs:
            struct = files[0]
        elif fs.filetype == 'cosynthRecords':
            recs = files[0]
        elif fs.filetype == 'systemVerilogSource':
            if ('module=%s' % mod) in attrs and 'view=v5' in attrs:
                v5 = files[0]
            else:
                others.append(fs)
    if not (v5 and struct and recs):
        return _err('cosynth.Pass: need V5 + structure for %s and cosynthRecords (have v5=%s struct=%s recs=%s)'
                    % (mod, v5, struct, recs))
    os.makedirs(input.rundir, exist_ok=True)
    try:
        rep = rewrite.run_pass(v5, struct, recs, input.rundir, list(p.xs), p.top or None)
    except ValueError as e:
        return _err('cosynth.Pass: %s' % e)
    ctxt.info('%s: applied %s; latency %d -> %d; register bits %d -> %d' % (
        mod, rep['applied'], rep['pre']['latency'], rep['post']['latency'],
        rep['pre']['register_bits'], rep['post']['register_bits']))
    out = [FileSet(src=input.name, filetype='systemVerilogSource', basedir=input.rundir,
                   files=[os.path.basename(rep['output'])], params={'module': mod},
                   attributes=['module=%s' % mod, 'view=cosynth']),
           FileSet(src=input.name, filetype='cosynthReport', basedir=input.rundir,
                   files=['cosynth_pass.json', 'cosynth_pass.md'], attributes=['module=%s' % mod])]
    if p.passthrough_other:
        out += others
    return TaskDataResult(status=0, changed=True, output=out)
