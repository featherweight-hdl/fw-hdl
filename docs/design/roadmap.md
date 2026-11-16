
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

# Prep for protocol-kit support

Protocol-kit support pulls in several features:
- associating a protocol with both a signal-bundle port and a method API
- design of a protocol API
  - request and response (or fwd/rev, egress/ingress, etc) APIs. Need to 
    settle on terminology here
  - socket design for connection
  - associated APIs and utilities
    - listener
    - transaction recorder
    - transaction classes (fwd/rev for each)
    - method to transaction and transaction to method bridges
- using sv-weave to derive method-API collateral
- transactor design -- which must bridge method/signal without latency (see current transactors)
  - Transactors for complex protocols start pointing to what we can do with higher abstraction constructs
- Generated Python collateral for cocotb and pyhdl-if

Our initial purpose for protocol kits is to wrap existing IPs
and use the connected to:
- Generate a testbench with connected transactors
  - We'll likely self-test transactors using fw-hdl-dv
- Generate a bind module with interface monitors
  - Allows us to drop in monitors on an existing design without change

- This also seems like a good time to setup the structure for
  the std package and the rv std protocol. Since derived APIs
  (eg listener) are part of the protocol, this implies that sv-weave
  becomes part of the build process

# Protocol kits
- Need R/V
- Manage association between bundle ports and protocol
- Design for transactor
-

## fw-hdl-dv setup
- Need the core of a DV library
- Must define relationships and naming schemes
  - 'fw_component' is one example. I'm assuming we'll want a DV component
- Establish the generator relationship
  - Is the 'DV projection' generated? May be a good idea vs API magic

## Verification IP
- property checkers written in terms of the API
- Generated UVM agents with monitors, etc
- Coverage monitors -- wonder if we can parameterize these...
- Generated Python collateral -- randomization and coverage
-> Hmm... Wonder if we could express constraints in terms of the API?
-> I bet we could model as constraints on request and response variables
  assert std::randomize(p1, p2) with {
    // Constraints on p1, p2 as well as (potentially) local variables
  };
  Or, I guess we could add verification transactions derived from the
  core transactions. Since they're classes, we could mark everything
  rand anyway.
  Or, perhaps it's the protocol-kit job to enforce legality

# Verification/Test Support
We want it to be very simple to connect verification to a design.
I think there are two levels:
- Use the boundary of the design directly
- Leverage a verification projection of the design

Core principle: leverage the design structure and annotated elements
to drive automated creation of verification structures.

In the simplest case, the user must be able to interact with the
design from outside. We will likely need convenience APIs shipped
with protocol kits to make this simpler on more-complex protocols.
-> Note: the primary target are developers modeling with the class library
-> Interface is the method API
-> Should be able to reach into a generic class-library runtime 
implementation and add monitors to ports, etc. Likely a good idea
to be able to traverse the structure via visitors -- VPI-like, but OOP.

In the case of wrapped RTL (with bundles), we can generate the same
view that provides a class facade connected by transactors to the RTL.

In cases where we model the design with classes, we should also be 
able to create an instrumented view of the design that gives us better 
visibility and access. This should be true across abstraction levels
as long as they were lowered from fw-hdl
- implement ports as monitors so we can subscribe
- auto-add internal transaction monitoring 
- create a RAL with automatic access (assuming address-map is annotated)
- Support RAL back-door access to registers
=> Effectively, this means we're generating a lot of the testbench
infrastructure by policy. If we don't need debug, don't even generate it

For verification, we can also use the design netlister to substitute shells
or behavioral models for elements of the design. In the case of shells, we
will want to reach down the hierarchy and access the transactors instaced there.

While fw-hdl-dv aims to provide standalone value (ie to be a lightweight UVM 
replacement), production environments will frequently use UVM. We must have 
first-class interop capabilities -- for example, generating the structural 
TB, core env (base class), and connecting up agents. We'll want verification IP
to register the existence of UVM assets such that a generator cna properly
assemble them. Why not rely on UVM directly? UVM is fairly heavyweight and 
cannot easily be changed. In addition, we are interested in leveraging the
DV specification to address applications such as checker portability and 
fast emulation environments (typically in C++). 

# Registers
Here's another place where the UVM approach is "implement this as 
class library to support programmatic access". Ours is "generate a specific
implementation based on a user spec". Our bet is that this will result
in much-more efficient and ergonomic code.

- Need to think about a DV projection. Generator (sv-weave) takes
  registers as a specification and produces a RAL with capabilities
  - Optional support for mirroring
  - Optional support for logging
  - Ensure we have a built-in backdoor path so we don't need VPI
    - Must work across multiple abstractions
- Need to think about how the design side provides support for both RTL
  and above-RTL implementations. For now, I suppose we can assume that
  registers are 'RTL register-like'. In other words, there is no latency
  in update -- we access and update from sync or comb blocks using read() 
  and write() functions that we can map to assigns in many cases.
- Registers are the first instance of ref components, where we'll effectively
  map field references to wires on the module ports to/from accessible storage.
- The register model likely needs a register-access protocol that we can
  bridge to other standard protocols. Perhaps this relationship can provide
  creation of register models with specific-protocol interfaces.
   
- 


# 
  - Using factory mechanisms to change implementations
  - Passing component-type handles via value parameterization