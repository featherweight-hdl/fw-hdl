"""Registers fw-hdl's dv-flow packages (entry point ``dv_flow.mgr``)."""
import os


def dvfm_packages():
    d = os.path.dirname(os.path.abspath(__file__))
    return {"fw.hdl.spl": os.path.join(d, "spl.dv"),
            "fw.hdl.xls": os.path.join(d, "xls.dv"),
            "fw.hdl.api": os.path.join(d, "api.dv"),
            "fw.hdl.formal": os.path.join(d, "formal.dv")}
