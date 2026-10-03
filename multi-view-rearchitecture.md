# Multi-View Architecture

Featherweight HDL is designed from the ground up to support multiple component views.
Defining components as multi-view is optional, since multi-view components are more
verbose. 

## Ports and Protocols
It is highly recommended to define protocols in layers, since they will typically
be used (at some point) with multi-view components
fw_proto_if
-> view implementation
-> parameters
- A protocol is a typed class marker that implements fw_proto_if
  - Compile-time comparison of logical protocol
- A protocol view extends the protocol to provide an implementation
  - 

## Components
Components come in two flavors: single- and multi-view. The degenerate case of a
multi-view component is a multi-view-ready component with a single view.

The primary difference between single- and multi-view components are in how 
interfaces (ports/exports) are defined. A multi-view component specifies abstract
protocol types for the ports/exports. An abstract type cannot be implemented, so
the base view is only valid once an implementation is selected. (open question:
is there value in making an interface-instance passive?)

Views of a multi-view component are classes that extend from the interface view.

```
class my_component extends fw_component;
  `fw_component_type(my_component)
  fw_port #(wb_proto_t) p;
endclass

class my_component_spl extends my_component;
  `fw_component_view(spl, my_component_spl, my_component)
  fw_port_view #(wb_proto_t, wb_proto_spl_t) p;

  function new(string name, fw_component p);
    super.new(name, p);
    p = new("p", this, super.p);
  endfunction

endclass
```

In both cases, the type registration must result in a static field with 
name 'type_t' that holds the type object for the component or view. This
object must have a method named 'create' that creates an instance of the
proper object type.

Note that ports on the component view shadow ports on the interface component.
(open question: there maybe value in dual-paramterizing port views so that we can compile-time check the 'base' port protocol)

The type registration causes the view to be connected to its interface for runtime checks.
Note that a 

## Blackbox Components

A blackbox component captures information about how interface ports and the component
instance map.

I'm thinking that we'll want fw_component to support attaching meta-data. In the case
of an RTL component, meta-data specifies the instance layout and interface port <-> 
signal mapping. For example:

```
class my_component_rtl extends my_component;
  fw_port_view #(fw_proto_t, wb_proto_rtl_t) p;
  `fw_component_view(rtl, my_component_rtl, my_component)

  // TBD: determine when to add this
  virtual function void connect();
    fw_blackbox_comp inst = new();
    attach(inst);
  endfunction

endclass

```

## View Selection

The type registration macro establishes a type factory that the views register themselves with.
View selection is 

## Component Parameters

Components can be parameterized. This is handled via a special 'params' class with
a static constructor method (to fill defaults). We might want a registration scheme
for parameter fields such that we can programmatically construct parameter sets.

```
class fw_component_param #(type Tparam=fw_params) extends fw_component;
  function new(string name, fw_component parent, Tparam params=Tparam::create());
  endfunction
endclass

```

A parameterized component s
A parameterized component uses a 

## Build Phasing
- Must be able to hierarchically control view construction
- Must leave space for our version of CHISEL diplomacy

Because super.new must be the first statement in a constructor, we must use an independent 
process for build to allow a component tree to control view select (the factory) for 
the sub-tree. 
- do_build
  - push view context (copied from parent)
  - invoke build() 
    - which may alter view selection
    - which constructs children via type factories
  - invoke do_build of children
  - pop view context

Note: a critical element to pin down is the elaboration process
- We must leave space for our version of Diplomacy (see reference/)
- We must support 

# Proof Point Example 1
- Two components (single, no views)
- Both black-box modules around RTL
- Both have RTL-protocol ports
- Class runtime elaboration should fail -- but why?
  - Only 
  - 

# Proof Point Example
- Two components
- Same simple protocol used between the two
- 

