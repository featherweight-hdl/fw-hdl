
# Wrap and integrate existing RTL
This phase applies fw-hdl as an RTL integration tool. Procedural 
means can be used to instance components, specify parameters, and
specify implementations.

## Features
- component
- component with struct value parameters
- extern components
- factory registration
- signals
- ports
- bundles and mirrors

## Exit criteria
- Wrap existing verilog
- Integrate, including
  - Using procedural code to value-paramterize component instances
- Generate synthesizable verilog 
  - Represents parameters -- including procedurally-specified parameters
    - Lower to 'generate' blocks

# Domains
This step formalizes how domains are defined, specified, and bound across
the hierarchy.

There are domain providers and domain consumers. Domains are communicated
across the component tree. By default, a component adopts relevant 
domains from its parent. 

Managing domains is an interesting one. Clock and reset are two domains 
that hardware is likely to always have. Power is something that some
hardware will model. There will be others as well. The question is how
to manage extensibility and propagation. I'm concerned about taking a
'union of all domains' approach. 

I could see tagging design blocks with respect to the macro in which 
they belong. There might be other physical aspects...

Clock domains are primarily relevant with respect to interfaces. Code 
that works with interfaces associated with different clock domains
infers a clock-domain crossing. 

At higher levels, we might insert timing relative to some clock 
domain. I'm comfortable having this *be* the block's sole domain.

Maybe domains are entirely structural, since attempting to mark code 
as belonging to a domain is messy.

This would leave domains as pure markers (except when they're needed
for modeling-level delays).

# Basic RTL (glue logic)
This step adds in the ability to implement logic inside a component:
- implementing fw_comb_if or fw_step_if is automatically detected
- Multiple methods may be added via a closure that implements the 
  relavant interface and sub-invokes the method. We need a macro to
  automate this, as well as an annotation in the future that sv-weave
  can leverage.

A single comb/step function pair may use local plain-data variables in
the class. comb settles first, then step is evaluated (ie NBA).

Multiple comb blocks that need to interact via shared variables must 
use fw_signal to ensure that changes re-evaluate the settling process.

A variable or signal may only be written by a single comb/step-rooted
call chain. This must be a static check to identify conflicts.



# Protocol kits

# 
  - Using factory mechanisms to change implementations
  - Passing component-type handles via value parameterization