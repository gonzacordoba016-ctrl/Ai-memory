"""Adaptador legacy: dict del CircuitSynthesizer → Circuit IR.

Permite que el constraint_engine (que consume IR tipado) opere sobre los
dicts producidos por el synthesizer histórico, desbloqueando la migración
desde tools/electrical_drc.py.
"""
from __future__ import annotations

from typing import Any

from tools.eda.ir import (
    Circuit,
    CircuitMetadata,
    Component,
    Net,
    Node,
)


# Campos del dict que ya están mapeados a slots tipados del Component.
# El resto va a `properties`.
_COMPONENT_RESERVED = {"id", "type", "resolved_type", "value"}


def _infer_net_class(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd",
                            "+5v", "+3.3v", "12v", "+12v")):
        return "power"
    if any(k in n for k in ("gnd", "ground", "agnd", "dgnd", "pgnd")):
        return "ground"
    return "signal"


def _split_node(s: str) -> tuple[str, str] | None:
    # "U1.GPIO2" → ("U1", "GPIO2"). Si hay más puntos, todos los siguientes
    # son parte del pin (poco común, pero defensivo).
    if "." not in s:
        return None
    ref, _, pin = s.partition(".")
    if not ref or not pin:
        return None
    return ref, pin


def dict_to_ir(circuit_dict: dict) -> Circuit:
    """Adapta un dict del CircuitSynthesizer a Circuit IR.

    Falla fuerte si el dict no tiene `components` o `nets`, o si un nodo
    de net referencia un componente inexistente. No inyecta pines en
    Component (el constraint_engine resuelve pinout vía registry).
    """
    if "components" not in circuit_dict:
        raise ValueError("dict_to_ir: falta clave 'components'")
    if "nets" not in circuit_dict:
        raise ValueError("dict_to_ir: falta clave 'nets'")

    metadata = CircuitMetadata(
        title=circuit_dict.get("name", "") or "",
        mcu=circuit_dict.get("_mcu"),
        power=circuit_dict.get("power"),
        description=circuit_dict.get("description", "") or "",
    )

    components: list[Component] = []
    seen_refs: set[str] = set()
    for c in circuit_dict["components"]:
        ref = c.get("id")
        if not ref:
            raise ValueError(f"dict_to_ir: componente sin 'id': {c!r}")
        ctype = c.get("resolved_type") or c.get("type")
        if not ctype:
            raise ValueError(f"dict_to_ir: componente {ref} sin 'type'")
        properties: dict[str, Any] = {
            k: v for k, v in c.items() if k not in _COMPONENT_RESERVED
        }
        components.append(Component(
            ref=ref,
            type=ctype,
            value=c.get("value"),
            properties=properties,
        ))
        seen_refs.add(ref)

    nets: list[Net] = []
    for n in circuit_dict["nets"]:
        name = n.get("name")
        if not name:
            raise ValueError(f"dict_to_ir: net sin 'name': {n!r}")
        nodes: list[Node] = []
        for raw in n.get("nodes", []):
            parsed = _split_node(raw)
            if parsed is None:
                # Nodos sin "." son legacy (solo ref, sin pin). El IR
                # exige PinId no vacío — saltamos silenciosamente.
                continue
            ref, pin = parsed
            if ref not in seen_refs:
                raise ValueError(
                    f"dict_to_ir: net '{name}' referencia componente "
                    f"inexistente: {ref}"
                )
            nodes.append(Node(ref=ref, pin=pin))
        nets.append(Net(
            name=name,
            nodes=nodes,
            net_class=_infer_net_class(name),
        ))

    return Circuit(
        metadata=metadata,
        components=components,
        nets=nets,
    )
