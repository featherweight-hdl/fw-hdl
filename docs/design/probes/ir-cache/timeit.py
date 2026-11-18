import sys, time, io, os
from pathlib import Path
t0=time.perf_counter()
from fw.hdl.fe.sv import elab as E
from fw.hdl.fe.sv.api import spec_dir
from fw.hdl.fe.sv.emit import emit_sv
from zuspec.ir.core.serializer import IRSerializer
from zuspec.ir.core.deserializer import IRDeserializer
T={}; T['import']=time.perf_counter()-t0
sc=spec_dir()/"conformance"
# instrument sv_compile and rt.elaborate
orig_compile=E.sv_compile
def tc(*a,**k):
    s=time.perf_counter(); r=orig_compile(*a,**k); T['parse+compile(pyslang)']=time.perf_counter()-s; return r
E.sv_compile=tc
from fw.hdl.fe.sv import rt as R
orig_el=R.FeRt.elaborate
depth=[0]
def te(self,*a,**k):
    depth[0]+=1
    s=time.perf_counter(); r=orig_el(self,*a,**k)
    depth[0]-=1
    if depth[0]==0: T['interp elaborate']=T.get('interp elaborate',0)+time.perf_counter()-s
    return r
R.FeRt.elaborate=te
s=time.perf_counter()
r=E.elaborate([sys.argv[1]], top="scenario::top", incdirs=[str(sc/"proc_counter"), str(sc/"_lib")])
T['elaborate total']=time.perf_counter()-s
assert r.ok, "\n".join(map(str,r.diags))
s=time.perf_counter(); ctx,top=r.to_ir(); T['to_ir (parameterized)']=time.perf_counter()-s
s=time.perf_counter(); y=IRSerializer().serialize(ctx,None); T['serialize']=time.perf_counter()-s
s=time.perf_counter()
try:
    c2=IRDeserializer().deserialize(y); T['deserialize']=time.perf_counter()-s
except Exception as e: T['deserialize']=f'FAIL {type(e).__name__}: {str(e)[:80]}'
s=time.perf_counter(); res=emit_sv(ctx, top, Path("gen"), top_module="ptop"); T['emit_sv']=time.perf_counter()-s
T['zir bytes']=len(y); T['types']=len(ctx.type_m); T['sv files']=len(res.files)
for k,v in T.items(): print(f"{k:28s} {v:.3f}" if isinstance(v,float) else f"{k:28s} {v}")
