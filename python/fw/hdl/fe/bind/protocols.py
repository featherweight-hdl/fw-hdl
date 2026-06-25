"""Std-transactor knowledge table — Option B (DESIGN §3).

KNOWN DEBT.  This table hard-codes the hardware meaning of the std transactor
bridges.  That meaning actually lives in the SV transactor *interface bodies*
(``src/std/fw_put_xtor_if.sv`` is the source of truth for what ``put`` does), so
this table:
  1. can silently go stale if a transactor body changes;
  2. does NOT scale to user-defined transactors/protocols — anything not listed
     here is unsupported;
  3. encodes pin direction/role by convention rather than reading the SV.

It is acceptable only for v1 because we own ``src/std`` and target a single
protocol.  **Migration trigger → replace with interface-body elaboration
(Option A):** the *first* of — a second std protocol needs lowering (get/reqrsp),
a user-defined transactor must synthesize, or an entry here diverges from its SV
body.  Only this module is replaced by Option A; ``elaborate.py`` (which reads
the bindings structurally) stays.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, Optional


@dc.dataclass(frozen=True)
class ProtocolSpec:
    """How a std transactor bridge maps an API call to a pin.

    Attributes
    ----------
    protocol:
        Short protocol name (e.g. ``put``).
    method:
        API method the class calls (e.g. ``out.t.put(v)`` -> ``put``).
    data_port:
        Name of the transactor-interface port carrying the data value; tracing
        its connection in the ``*_top`` module yields the real module pin.
    pin_dir:
        Module-pin direction (``output`` / ``input``).
    registered:
        ``put`` registers the value on the clock edge — a 1-cycle, no-handshake
        **beat** that occupies its own FSM state (DESIGN §1/§7).
    """

    protocol: str
    method: str
    data_port: str
    pin_dir: str
    registered: bool


# Keyed by the bridge class name (``fw_put_xtor_bridge#(T)`` -> ``fw_put_xtor_bridge``).
STD_TRANSACTORS: Dict[str, ProtocolSpec] = {
    "fw_put_xtor_bridge": ProtocolSpec(
        protocol="put", method="put", data_port="out",
        pin_dir="output", registered=True,
    ),
}


def lookup(bridge_name: str) -> Optional[ProtocolSpec]:
    return STD_TRANSACTORS.get(bridge_name)
