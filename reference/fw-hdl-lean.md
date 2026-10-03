# Featherweight-HDL Lean

The current fw-hdl borrows significantly from UVM:
- mandatory user-declared 'new'
- separate build for construction

We want to setup the ergonomics of construction such that:
- components whose shape* does not depend on parameters are largely declarative
- add on 'build' to deal with component-involved parameter-defined shape
- connect 

* component-involved shape: factory settings, comp elems in an array, etc

```
class my_component extends fw_component;
  `fw_component_type_begin(my_component)
    `fw_field_port(my_api, p);
    `fw_field_export(my_api, e);
  `fw_component_type_end
endclass

class my_component_param extends fw_component_param #(fw_component_param);
  `fw_component_type_param_begin(my_component)
    `fw_field_port_param(my_api, p, this.params.w);
    `fw_field_export_pram(my_api, e, this.params.w);
  `fw_component_type_param_end
endclass

```

This is equivalent to:
```
class my_component extends fw_component;
  // creation of 'type' static field
  fw_port #(my_api) p = new("p", this); // For component, we need <type>::type::create()
  fw_export #(my_api) e = new("e", this);

  function new(string name, fw_component parent);
    super.new(name, parent);
  end
endclass

class my_component_param extends fw_component_param #(fw_component_param);
  `fw_component_type_param_begin(my_component)
    `fw_field_port_param(my_api, p, this.params.w);
    `fw_field_export_pram(my_api, e, this.params.w);
  `fw_component_type_param_end

endclass

```

# Component Views and Factories

All types must be registered. All fields must be constructed via a factory.

```
class my_component extends fw_component;
  `fw_component_type_begin(my_component)
    `fw_field_port(my_api, p);
  `fw_component_type_end
endclass

class my_component_spl extends my_component;
  `fw_component_view_begin(my_component_spl, my_component, spl)
    `fw_field_port_view(my_api_spl, p);
    begin // insert code in the constructor
    end
  `fw_component_view_end
endclass
```

So, when we use the component

```
class my_top extends my_component;
  `fw_component_type_begin(my_top)
    `fw_field(my_component, c1);
  `fw_component_type_end
endclass
```

'c1' will create the selected view at runtime. This is mostly useful for
controlling cases in which the SV actually needs to run. Any static case
is elaborated. Note how the view creates a type-local 'view' of the port
that has a different type -- related by inheritance to the base type.

We need to give thought to how parameters are resolved. A parameterized
component declares a parameter type (inner class) and has a reference
to a parameter instance. 

Anything that is parameterized references via an accessor field. This 
allows the value to be changed without impacting the consumers.

So, we have something like: fw_param_accessor_f #(params_t) params;

