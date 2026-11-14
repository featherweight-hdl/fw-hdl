"""A binding with no root classes: fw-hdl's weavers only add package-level code
(``on_design``), so no class is a woven target. sv-weave requires a binding."""
from sv_weave.plugin import Binding


class FwHdlBinding(Binding):
    name = "fw-hdl"
    version = "0.1"
    roots = ()
