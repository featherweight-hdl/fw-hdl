# Vivado synthesis of SystemVerilog classes: experiment

Run 2026-11-15 with Vivado **2024.1** (`/tools/vivado/Vivado/2024.1`),
part `xc7a35tcpg236-1`. The purpose was to check how much of UG901's
"Supported" class table actually synthesizes, and whether the result is
correct. This backs the *Existing tool support* section of `../../pitch.md`.

## Method

1. Synthesize each `t*.sv` with `run.tcl`, which runs `synth_design` and
   writes the utilization report and a functional-simulation netlist to `out/`.
2. Simulate the post-synthesis netlist in xsim against a self-checking
   testbench (`sim/tb_*.sv`, driven by `sim/run_sim.sh`). This confirms the
   synthesized logic is *correct*, not only that synthesis was accepted.

```
source /tools/vivado/Vivado/2024.1/settings64.sh
vivado -mode batch -nojournal -nolog -source run.tcl -tclargs t2_obj_state.sv
sim/run_sim.sh t2_obj_state tb_count.sv 1
```

## Results

| Test | Construct | Level | Synth | Netlist sim |
|---|---|---|---|---|
| t1_static_ns | `virtual class` with a static function, parameterized (Design Compiler style) | L1 | OK, 8 FF | PASS |
| t2_obj_state | Object built at declaration; member used as register state; method called from `always_ff` | L2 | OK, 8 FF | PASS |
| t3_obj_comb | Two objects with constructor arguments; methods used in `always_comb` | L2 | OK, 0 FF | PASS |
| t4_inherit | `extends`, `super.new()`, inherited non-virtual method | L2/L3 | OK, 8 FF | PASS |
| t5_virtual_method | Virtual method overridden in the derived class, called through the derived handle | L3 | OK, 8 FF | PASS |
| t7_virtual_class | Abstract `virtual class` with a `pure virtual` method; concrete derived class | L3 | OK, 8 FF | PASS |
| t8c_obj_member_obj | Composition: an object holding objects built in its constructor | L2 | OK, 16 FF | PASS |
| t8b_obj_generate | One object per `generate` iteration | L2 | OK, 19 FF + 8 SRL16E | PASS |
| t9_factory_param | Implementation chosen by a `parameter type`; `IMPL c = new()` | L3 (static) | OK, 8 FF | PASS |
| t10_obj_per_instance | Object inside a submodule instantiated twice: per-instance state | L2 | OK, 16 FF | PASS |
| t6_poly | Base handle assigned a derived object in `initial` | L3 (polymorphic) | **FAIL**: `Synth 8-659 type mismatch in assignment: class base vs. class down` | — |
| t6b_poly_decl | Base handle initialized from a derived handle at declaration | L3 (polymorphic) | **FAIL**: `Synth 8-659 type mismatch in initialization` | — |
| t6c_poly_new | `base c = down::new()` | L3 (polymorphic) | **FAIL**: `Synth 8-660 unable to resolve 'new'` | — |
| t8_handle_array | Array of handles filled by `new` in an `initial` loop | L2 | **FAIL**: `Synth 8-6782 new ... can only be used in class object assignment` | — |

Further restrictions found while writing the tests:
- A class member cannot be read in a continuous `assign` (`Synth 8-9181
  automatic variable ... not allowed in non-procedural context`); use
  `always_comb` instead.
- `cell` is a reserved word (a Verilog configuration keyword), so it cannot be
  used as a class name.

## Conclusions

- **Vivado does more than its documentation says.** UG901 lists virtual and
  abstract classes as *Not Supported*, yet Vivado 2024.1 correctly
  synthesized a virtual-method override (t5) and an abstract base class with a
  pure virtual method (t7). In both cases the call goes through a handle whose
  static type is the concrete class, so dispatch is trivially resolved.
- **Vivado draws the line at polymorphism.** A base-class handle can never hold
  a derived object (t6, t6b, t6c), so there is no factory-style substitution
  through a base handle. The only implementation-selection idiom that works is
  choosing the *type* statically (t9, `parameter type`).
- **Objects must be created at declaration** (`T h = new(...)`), possibly
  inside `generate`. Calling `new` procedurally, even in `initial`, is
  rejected (t8).
- **Within those limits the results are correct.** Every accepted design
  simulated correctly after synthesis. In effect, Vivado treats a class object
  as a struct of variables plus inlined functions.
- **Scope of the result.** This applies to one vendor and one FPGA flow. It
  says nothing about Synopsys/Cadence ASIC synthesis, formal tools, or other
  FPGA vendors, and the subset is undocumented: the documentation
  understates it, and code relying on it would not port.

## Pitfall recorded for anyone re-running

`xvlog` compiles the netlist and the testbench in one invocation, so the
netlist's `` `timescale 1ps/1ps `` carries over into the testbench. Without an
explicit `` `timescale `` in the testbench, its delays become picoseconds and
the whole simulation runs inside glbl's 100 ns GSR pulse, with every flop held
at 0. The testbenches now declare `` `timescale 1ns/1ps ``.
