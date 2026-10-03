 Review packages/fw-hdl, packages/fw-proto-wb. We use the notion of a protocol kit to capture a
  protocol at the operaiton level, and how those operations map to the signal level. But, I think
  we could benefit another way: automating RTL assembly from an SPL description. I'm thinking we
  may want to take a page from IP-XACT and define a base protocol with parameters, then extend
  (add views to) it with classes that contribute 'methods', 'signals', etc. 

We need the base protocol class to be a concrete class so we can reference its 'type'.
View-specific classes often have utilities or required data.

- need a protocol base class that can report registered views (?)
- view is often
  - protocol, implements X

Core requirements:
- Validate that two ports can connect:
  - same protocol
  - same parameters
  - same view
- 

- Port just expresses protocol+params in its type declaration
- Adapters/Annotators are responsible for adding view information
  on each role-related 
- Sort of like a 'wrap' to enable accessing
- Should support runtime diagnosis of incorrect connections
  - p<T> <-> e<T>
  - But, to communicate, we need an adapter
  - That adapter communicates the view requirements/capabilities

The end goal is to be able to netlist a SPL model of RTL cores as a
flat RTL netlist -- using behavioral constructs, etc to make more
efficient / programmable

The evaluator for the target environment determines whether it 
can make sense of the description
- RTL <-> RTL -> direct netlist
- RTL <-> SPL -> identify boundary and insert transactor

Implies that we do need to register transactors as abstractors.

Transactor is SV module (T) -- fortunately, never namespaced

# SPL <-> RTL 
`fw_abstractor_spl_rtl(T, T_if, T_if_path, )


We must be able to attach things to our ports/exports
- Mostly exports -- eg address spaces
