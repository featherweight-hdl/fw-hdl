# Representing signals

RTL descriptions are implemented in terms of local signals,
ports, and port bundles. All signals support read and write.

fw_signal #(T) - works on any scalar quantity
fw_output #(T)
fw_input #(T)
fw_inout #(T)

Signals are read and written as a unit. It might be worth exploring
a path for masked accesses as well (?). 

A bundle class is a class (but, which base class) that collects
a set of ports with directions. The directions should be specified
with respect to 'initiator' direction

fw_bundle #(T) -- Wraps a bundle class and retains directionality
fw_mirror #(T) -- Wraps a bundle class and reverses directionality

fw_bundle and fw_mirror can be connected. I'm thinking that 
bundle and bundle and mirror and mirror can be used to forward a 
bundle through the hierarchy. Need to think about how to 
detect incorrect connections -- two initiators connected directly
to each other. Maybe a dedicated call conveying directionality
makes sense. Maybe not.

I'd like it if we could form bind maps like data instead of multiple
statements. Sort of a 'bulk connect' that takes a map of connection
tuples. The pattern used should emphasize ergonomics over algorithmic
efficiency.


