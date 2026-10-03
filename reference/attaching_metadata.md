# Attaching Meta-data

Metadata -- type-specific data that is only interpreted
by knowledgeable processors -- is critical in design and 
verification flows. fw-hdl must provide first-class support
and enable generators.

## Example meta-data
- Reference to related PSS
  - source-relative paths
  - dv-kit references
- Reference to 

Metadata is attached to component types. This happens in two ways:
- Declared within a view of the component (base or derived)
- Attached to the type. The semantics are that of type extension in the PSS sense
  - bind is a closure class that 'applies' the meta-data to an instance of the type

- Hmm... Meta-data may be conditional. For example, we might bring in
  different filesets based on parameters?

