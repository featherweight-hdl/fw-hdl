fw-hdl is a design for capturing hardware designs, but it's
more than just a SystemC-like class library: it's a specification
architected to support multiple interpretations and implementations.

An example of the goal:
- We want simulator vendors to be able to recognize the classes 
  and interfaces and provide native-optimized implementations
- We want to use sv-weave to generate per-component implementations
  in SystemVerilog that can be used in any simulator
- We want to implement a lowering to optimized C that we can
  use as a fast system model
- Obviously, we want to lower to synthesizable RTL

It is expected that many, if not most, implementations will interpret
a fw-hdl-based description statically. Even if the end goal is dynamic
execution, a static-analysis pass will be used to optimize the representation.

To this end, we need to carefully separate the user-facing specification
and minimum-bar execution semantics from implementation classes. 
For example:
- a comb method is registered one of two ways:
  - component implements the 'comb' interface
  - a closure is attached to the component
- a comb method executes at least every time one of its
  sampled input variables changes. 
  - This leaves open the possibility that it may be evaluated
    many times -- including many NOP evaluations.

Class-library types fall into two categories:
- Classes that are constructed, but not implemented by a design.
  These are declared as interface classes and constructed via 
  a factory pattern. This removes implementation from core fw-hdl
  and, conceptually, allows an implementation to cause its runtime
  class to be created. This also supports per-instance injection
  of implementation.
- Classes that act as base classes for user-defined types. These
  should be kept minimal, with APIs implemented in terms of an
  implementation interface that is factory-constructed

Initial targets:
- 'Plain SV' tool that uses sv-weave to process user input and develop 
  optimized component implementations, and assemble pure-SV implementations
  that connect existing RTL with fw-hdl and execute on a stock SV simulator
- Synthesis engine that lowers input to Verilog RTL
  - Companion tool that emits formal properties for a stock formal tool
- Formal engine that evalutes properties expressed on a fw-hdl representation
- Software-model tool that produces a fast model implemented in C

