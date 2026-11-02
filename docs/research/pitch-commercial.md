# High-level synthesis for RTL teams: SystemVerilog + fw-hdl + XLS

*Pitch for commercial design teams, 2026-11-01. Background:
[xls-vs-fw-hdl.md](xls-vs-fw-hdl.md) (comparison) and
[designer-ramp-to-xls.md](designer-ramp-to-xls.md) (plan and status).*

---

> **Keep writing SystemVerilog. Stop hand-pipelining it.**
>
> With fw-hdl you write a block's behavior as SystemVerilog classes and instantiate it in
> your RTL like any other module. You simulate and verify it with your own simulator,
> testbench and waves. Then Google's XLS compiler generates the pipelined RTL behind that
> same module, with the same ports, and it goes to your synthesis flow like the rest of
> your design.
>
> You get XLS's QoR without the DSLX language, without a separate C++ model, and without
> an integration wall at the end.

---

## 1. Why high-level synthesis keeps stalling in RTL teams

Most RTL teams have tried HLS, or decided not to. The reasons are rarely about QoR. They
are about everything around the compiler:

1. **A new language.** C++ with pragmas, or a new DSL. The designers who know the
   micro-architecture are not the ones fluent in it, and the code doesn't look like
   anything else in the repo.
2. **A model that lives somewhere else.** The HLS source runs in its own simulator or a C++
   test harness. To get it into the SoC testbench, someone writes a DPI wrapper by hand,
   untimed, and keeps it in sync.
3. **An integration wall.** The block only meets the rest of the chip once RTL comes out of
   the compiler. That's the slowest simulation and the latest point to find out the
   interface or the throughput is wrong.
4. **Debug across a seam.** A failure in the SoC sim shows up in generated RTL with mangled
   names. The designer then has to reproduce it in a different tool, in a different
   language.

**XLS** (Google's open-source "medium-level synthesis" compiler) has excellent QoR, a
strong optimizer and scheduler, and real formal tooling. But it inherits all four problems:
- Its language is DSLX.
- Its pre-RTL simulators run in XLS's own tools, not in your SystemVerilog simulator.
- The only SystemVerilog it produces is the final RTL.
- It has no DPI or transaction-level model output, upstream or in the xlsynth distribution.

## 2. The fw-hdl path

```
  your RTL design                                    your back end
 ┌────────────────────────────────────────┐         ┌──────────────┐
 │  hand RTL ─► [ my_block ] ─► hand RTL   │         │ Fusion / DC  │
 │                 │                       │         │ Genus / ...  │
 └─────────────────┼───────────────────────┘         └──────▲───────┘
                   │  same module name, same ready/valid pins │
     ┌─────────────┴──────────────┬───────────────────────────┘
     │ model view                 │ RTL view
     │ SV classes on the          │ XLS-generated pipelined RTL
     │ fw-hdl runtime             │ (SV class ─► XLS IR ─► opt ─► schedule ─► codegen)
     └────────────────────────────┘
          select by file list; the parent RTL and the testbench do not change
```

You write SystemVerilog. XLS does the scheduling, pipelining and optimization. fw-hdl
connects the two: it translates your classes into XLS's internal representation (no DSLX
in between), wraps them so they look like a module, and runs the same tests at every level.

## 3. What your first week looks like

**Day 1: write the block.** Pick something you'd normally write as an FSM plus datapath:
a checksum, a run-length encoder, a crypto round, a packet-field extractor.
- Write it as a class with input and output ports and a `forever` loop: get, compute,
  put.
- Class members are your registers.
- `typedef struct packed`, functions, `case` and fixed loops all work the way you expect.
- You don't draw a pipeline diagram or count flops.

**Day 2: drop it into your design.** The block's module shell has the exact port list XLS
will generate: clock, reset, and `data`/`_vld`/`_rdy` per channel. Instantiate it where the
hand-written block would go. Your existing RTL drives it, and you see real ready/valid
traffic in your waves.

**Day 3: verify it with what you already have.** Your SVUnit tests, UVM agents and
scoreboards connect to the same pins. Then:
- `$display`, assertions and the simulator debugger work on the class code directly.
- If two blocks talk through a FIFO that is too shallow, the model deadlocks *now*, in your
  simulator, with a SystemVerilog call stack. You don't find out in RTL three weeks later.

**Day 4: ask "is it fast enough?"** Set a target clock period, and optionally the
throughput (II) and latency. XLS schedules the block and fw-hdl feeds the result back:
- pipeline stages, latency and critical path, in a report
- a timed model whose latency comes from that schedule, which your system simulation can
  use before any RTL exists

Change the clock target and rerun: the same tests pass at the new latency.

**Day 5: generate the RTL.** One flow step produces:
- XLS's pipelined RTL behind the same module
- with your reset style, ready for your synthesis tool

Then:
- Switch the file list from the model to the RTL and rerun the *same* tests.
- Run them again on gates if you like.
- Generated RTL lines point back to your SV source lines.

## 4. The same block, two ways

Here is a run-length encoder from the XLS examples, ported to SystemVerilog. Both versions
compile through XLS.

**XLS DSLX (original)**
```rust
pub proc RunLengthEncoder<SYMBOL_WIDTH: u32, COUNT_WIDTH: u32> {
    input_r: chan<EncInData<SYMBOL_WIDTH>> in;
    output_s: chan<EncOutData<SYMBOL_WIDTH, COUNT_WIDTH>> out;
    init {( RunLengthEncoderState<SYMBOL_WIDTH, COUNT_WIDTH> {
              prev_symbol: bits[SYMBOL_WIDTH]:0, prev_count: bits[COUNT_WIDTH]:0,
              prev_last: false } )}
    config (input_r: chan<EncInData<SYMBOL_WIDTH>> in,
            output_s: chan<EncOutData<SYMBOL_WIDTH, COUNT_WIDTH>> out) {(input_r, output_s)}

    next (state: RunLengthEncoderState<SYMBOL_WIDTH, COUNT_WIDTH>) {
        let (input_tok, input) = recv_if(join(), input_r, !state.prev_last, zero_input);
        let prev_symbol_valid = state.prev_count != bits[COUNT_WIDTH]:0;
        ...
        let data_tok = send_if(input_tok, output_s, do_send, data);
        RunLengthEncoderState { prev_symbol: symbol, prev_count: count, prev_last: last }
    }
}
```

**SystemVerilog with fw-hdl**
```systemverilog
class RunLengthEncoder #(int unsigned SYMBOL_WIDTH = 32, int unsigned COUNT_WIDTH = 2)
        extends fw_component implements fw_runnable;
    fw_port #(fw_get_if #(EncInData))  input_r;
    fw_port #(fw_put_if #(EncOutData)) output_s;

    bit [SYMBOL_WIDTH-1:0] prev_symbol = '0;   // registers: plain class members
    bit [COUNT_WIDTH-1:0]  prev_count  = '0;
    bit                    prev_last   = 1'b0;

    virtual task run();
        forever begin
            EncInData input_ = '{symbol: '0, last: 1'b0};
            if (!prev_last) input_r.t.get(input_);        // blocking receive
            prev_symbol_valid = prev_count != '0;
            ...
            if (do_send)                                   // blocking send
                output_s.t.put('{symbol: prev_symbol, count: prev_count, last: prev_last});
            prev_symbol = symbol; prev_count = count; prev_last = last;
        end
    endtask
endclass
```

What an RTL designer notices:
- **The state is just registers.** In SV, state is class members that you assign. In DSLX,
  state is threaded through `next` as an immutable value, with `init` and `config` blocks.
- **The I/O is just I/O.** `get` and `put` under an `if` read the way the hardware behaves.
  DSLX makes you thread tokens (`join()`, `input_tok`) to order side effects.
- **Composition is just wiring.** Connecting an encoder to a decoder through a FIFO is a
  `fw_channel #(T, DEPTH)` and two `connect()` calls. You can see that channel and debug it
  in your simulator. In DSLX it's a `spawn` inside a `config` block.
- **It runs in your simulator.** The SV version is plain IEEE 1800 code, with no
  preprocessing, and it runs in your SV simulator next to your RTL. The DSLX version runs
  in XLS's interpreter.

**And the hardware is the same or better.** On the run-length encoder, the SV source gives
XLS a *smaller* starting point: 89 vs 95 IR nodes, and 105 vs 144 flip-flops on iCE40.

## 5. Why SV + fw-hdl + XLS instead of DSLX

### 5.1 No new language, no new tool silo
- Your designers write the SystemVerilog they already know.
- Your DV engineers can read it, review it and reuse its types.
- The source lives in your RTL repo, goes through your code review, and builds with your
  file lists.

Hiring and handoff are unchanged: anyone who can read SV can maintain the block.

### 5.2 The model is a module in your design, not a program beside it
With DSLX, the only thing you can put in your SoC simulation is final RTL. Anything earlier
means a hand-written DPI wrapper over C++. With fw-hdl:
- The behavioral model *is* SystemVerilog.
- It sits behind a module with the final port list.
- Integration happens on day 2, not after synthesis.

### 5.3 Multi-process designs you can actually see
Real blocks are several processes connected by FIFOs: a parser feeding a lookup feeding a
rewriter, or a cipher fed by a DMA. In XLS's own simulators:
- FIFO depths are ignored and queues are unbounded (an open issue since 2023, #988).
- A deadlock caused by an undersized FIFO stays hidden until RTL.
- Behind a DPI wrapper, the whole network is one opaque blob.

In fw-hdl:
- Every process and every channel is a SystemVerilog object you can inspect.
- FIFO depths are honored, so a deadlock happens in the model.
- You can swap any single process for hand RTL through a transactor.

### 5.4 Performance answers before RTL, from the real compiler
fw-hdl reads XLS's actual schedule for your clock target and produces a timed model of the
block with that latency. Architects get credible latency numbers in the SoC simulation
before RTL exists. Because the timed model is generated from the same schedule XLS will
build, the numbers don't drift from the RTL. On AES, the timed model is cycle-exact with
XLS's RTL on the test vectors. It also simulates 3–5× faster than the RTL, and its cost
stays flat as you add instances (64 instances: 0.18 s vs 33 s for RTL).

### 5.5 One test, every level, your testbench
The same unedited test file runs against the class model, XLS's RTL and gate-level
netlists. 11 examples ported from the XLS repository pass with byte-identical test files
at every level, including SHA-256 at three different clock targets. A failure at gates can
be reproduced at the model level in milliseconds, with the same test and the same message.
No DPI, and no second testbench for the HLS block.

### 5.6 Adopt one function at a time
You don't have to convert a block, let alone a team:
- **Start with one function.** Take one datapath function out of a hand-written block (a
  CRC, a checksum, a round function), write it as an SV function, let XLS pipeline it, and
  instantiate the result from your existing RTL.
- **Then a whole block** when you're comfortable.
- **Then a network of blocks.**

Every step uses the same flow, and nothing you wrote earlier needs rewriting.

### 5.7 SV is as efficient as hand-written DSLX, and sometimes more
fw-hdl doesn't replace XLS's optimizer, scheduler or code generator. It feeds them the same
internal representation that DSLX would. Measured on the examples ported from the XLS
repository:

| Design | IR nodes (SV / DSLX) | iCE40 cells (SV / DSLX) | XLS equivalence check |
|---|---|---|---|
| CRC-32 | 128 / 128 | 103 / 103 | equivalent |
| FIR dot product | 70 / 70 | 2058 / 2058 | equivalent |
| IDCT (Chen) | 2019 / 2019 | 42446 / 42446 | equivalent |
| SHA-256 | 4969 / 4969 | 48255 / 48260 | partly proved (one check inconclusive) |
| Run-length encoder | 89 / 95 | 262 / 390 | n/a (procs) |
| GCD | 1592 / 1667 | 4530 / 4294 | equivalent |
| AES | 6975 / 6976 | — | inconclusive (too large to prove) |

SystemVerilog is as efficient as hand-written DSLX, and sometimes more. On most examples
the result is the same netlist. The run-length encoder comes out 33% smaller from SV, and
GCD is the one case slightly larger (+5.5% cells).

### 5.8 XLS's formal tools, in your language
XLS's equivalence checker and property prover run on what your SV compiles to. fw-hdl
already uses XLS's equivalence checker to confirm the SV port matches the DSLX original on
the examples above. Next on the roadmap: writing a property as an SV function and having
XLS prove it over all inputs. That is datapath formal without writing SVA.

## 6. What you keep from XLS

This is not "instead of XLS". It's XLS with a front end and a verification environment
built for RTL teams. You keep:
- XLS's optimizer and scheduler
- delay-model-driven pipelining
- ready/valid code generation, FIFO insertion and I/O flop options
- equivalence and property proving

As XLS improves, your blocks improve.

## 7. Common questions

**"Isn't class-based SV slow to simulate?"** The model is a transaction-level model, so it
usually runs faster than the RTL it replaces. The timed AES model runs 2.8–4.7× faster than
XLS's RTL on Verilator, and stays flat as idle instances are added.

**"What subset of SV can I use?"** These are supported:
- 2-state packed types and structs
- functions
- `if` / `case` and fixed-bound loops
- class members as state
- blocking get/put on ports, and non-blocking try-get

Code that can't become hardware is rejected with an error that points at the line. Two
examples: a `#delay`, or a get/put inside a loop. (Accepting `logic` as 2-state is on the
near-term roadmap.)

**"How do I know the RTL matches my class?"** Three layers of checking:
1. **Your SV and XLS's internal representation:** XLS's equivalence checker for functions,
   plus differential tests.
2. **XLS and its RTL:** XLS's own validation, plus your same test passing on the generated
   RTL.
3. **RTL and gates:** your normal equivalence checking (LEC).

**"Can I mix it with existing DSLX or hand RTL?"** Yes. fw-hdl builds the RTL top-level of a
network from each block's interface description, not from its Verilog. So a block from
DSLX, or hand RTL with the same ready/valid interface, plugs into the same place.

**"Which simulators?"** It's standard IEEE 1800 classes. Tested today on Verilator.
Commercial simulators (VCS, Xcelium, Questa) are on the qualification list.

**"Are we locked in?"** The source is SystemVerilog and the engine is open-source XLS. If
you ever leave, your behavioral models remain plain SV that any simulator runs.

## 8. Today vs. roadmap

| Capability | Status |
|---|---|
| SV functions and processes → XLS → pipelined RTL, at QoR parity | **Available** (11 XLS examples plus AES) |
| One test at model / RTL / gate level | **Available** |
| FIFO-depth-accurate multi-process model; deadlock found pre-RTL | **Available** |
| All-XLS process networks assembled into one RTL top | **Available** |
| Timed model from the XLS schedule (latency) | **Available** for functions (AES demo) |
| Module shell with XLS's exact pins, for drop-in use in your RTL | Roadmap: first priority |
| `logic` accepted, RTL-designer coding guide, early synthesizability check | Roadmap: first priority |
| Async/sync reset style, I/O flop options, throughput targets, constraint (SDC) hand-off for Fusion Compiler | Roadmap: next |
| Timed model with throughput (II) for processes | Roadmap |
| SV `$display` / `cover` / properties carried into RTL and formal | Roadmap |
| SRAM inference; delay model characterized for your process node | Roadmap |

## 9. The short version

| | XLS with DSLX | XLS with SystemVerilog + fw-hdl |
|---|---|---|
| Language | Learn DSLX | The SystemVerilog you already write |
| Pre-RTL model in your SoC sim | Hand-written DPI wrapper, or nothing | The model *is* SV, behind the final module pins |
| Multi-process debug | Opaque; FIFO depth ignored pre-RTL | Every process and FIFO visible; real depths |
| Performance before RTL | Static report | A timed model from XLS's schedule, inside your sim |
| Tests | Separate HLS tests + RTL tests | One test file, every level |
| Adoption | All in, per block | One function at a time |
| QoR | XLS | XLS (same IR on most examples) |

**XLS is the best open medium-level synthesis engine. fw-hdl is how an RTL team actually
uses it.**
