
Many approaches to raising the abstraction level of hardware design have 
focused on a single consituent: the designer. This is natural, given their
typical goal of raising design productivity. Taking this narrow focus has
costs, though. Often, designer-productivity tools introduce costs for
verification engineers by emitting difficult-to-debug code. And, the bring
no benefits to architects, verification,  or firmware. Historically, 
innovations in archtecture, verification, and firmware have been similar:
they help the target team, but either provide no value to the other teams
or may hurt.

The fw-hdl framework aims to be diferent.
- It connects 
- It raises abstraction level and productivity for design engineers
- It aids timing closure for design and integration teams
- It provides faster simulation and better formal verification to DV engineers
- It provides fast software models to firmware teams
- It provides both executable and Lean on-ramps for architects

Broad value is the north star, and we need to be able to back it up.
But, we need to start with a focus on a specific team. Ideally, it 
would be design, but this might be challenging. 
