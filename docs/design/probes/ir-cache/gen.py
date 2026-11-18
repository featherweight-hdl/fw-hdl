import sys
N=int(sys.argv[1]); K=int(sys.argv[2]); NW=int(sys.argv[3])  # lanes, stages/lane, distinct widths
widths=[8,12,16,24,32,48,64][:NW]
o=[]
o.append('`timescale 1ns/1ps\n`include "fw_hdl_macros.svh"\npackage scenario;\nimport fw_hdl_pkg::*;\n`include "test_proc.svh"\n')
o.append('''class src #(type T=bit[7:0]) extends fw_component implements fw_step_if;
 typedef src#(T) this_t;
 `fw_component_param_utils(src)
 fw_output #(T) n;
 virtual function void build(); n = fw_output #(T)::create("n", this); endfunction
 virtual function void step(); n.write(n.read() + 1); endfunction
endclass
class stage #(type T=bit[7:0]) extends fw_component implements fw_comb_if, fw_step_if;
 typedef stage#(T) this_t;
 `fw_component_param_utils(stage)
 fw_input #(T) i; fw_output #(T) o; fw_output #(T) q;
 virtual function void build();
  i = fw_input #(T)::create("i", this); o = fw_output #(T)::create("o", this); q = fw_output #(T)::create("q", this);
 endfunction
 virtual function void comb(); o.write(i.read() + q.read()); endfunction
 virtual function void step(); q.write(o.read() ^ i.read()); endfunction
endclass
class lane #(type T=bit[7:0]) extends fw_component;
 typedef lane#(T) this_t;
 `fw_component_param_utils(lane)
 src#(T) s;
''')
o.append(' stage#(T) '+', '.join(f's{k}' for k in range(K))+';\n')
o.append(' virtual function void build();\n  s = src#(T)::create("s", this);\n')
for k in range(K): o.append(f'  s{k} = stage#(T)::create("s{k}", this);\n')
o.append(' endfunction\n virtual function void connect();\n  s0.i.connect(s.n);\n')
for k in range(1,K): o.append(f'  s{k}.i.connect(s{k-1}.o);\n')
o.append(' endfunction\nendclass\n')
o.append('class top extends test_proc_top;\n `fw_component_utils(top)\n')
for n in range(N): o.append(f' lane#(bit[{widths[n%NW]-1}:0]) l{n};\n')
o.append(' virtual function void build();\n  super.build();\n')
for n in range(N): o.append(f'  l{n} = lane#(bit[{widths[n%NW]-1}:0])::create("l{n}", this);\n')
o.append(' endfunction\nendclass\nendpackage\n')
open('top.sv','w').write(''.join(o))
