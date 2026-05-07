"""
Pin Allocator — asignación determinista de pines MCU.

Reemplaza la "decisión" implícita de pines que hacía el LLM por una
asignación de constraint-satisfaction sobre el Component Registry.

API:
    allocate(circuit, requests) → AllocationResult

Inputs:
    circuit:  Circuit IR. Cualquier nodo MCU ya con pin concreto cuenta
              como ocupado (no se reasigna).
    requests: lista de PinRequest. Cada una pide un pin con cierta función
              (I2C_SDA, SPI_SCK, ADC, PWM, GPIO, ...) en cierta net.

Output:
    AllocationResult:
        - circuit:     Circuit transformado con las asignaciones aplicadas.
        - assignments: lista ordenada de Assignment.
        - issues:      ValidationIssue cuando no se pudo resolver una request
                       (PIN_NO_AVAILABLE / PIN_AMBIGUOUS_REQUEST / etc.).

Determinismo:
    - Sort de requests reproducible.
    - Scoring con tiebreak alfabético del pin number.
    - Sin random, sin diccionarios desordenados en la salida.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from tools.eda.component_registry import (
    ComponentSpec,
    PinSpec,
    get_registry,
)
from tools.eda.ir import (
    Circuit,
    Net,
    Node,
    Severity,
    ValidationIssue,
)


# ────────────────────────────────────────────────────────────────────────────
# Tipos públicos
# ────────────────────────────────────────────────────────────────────────────


class PinRequest(BaseModel):
    """Pedido de asignación de un pin del MCU.

    El allocator buscará el mejor pin físico que cumpla `function`,
    evitando conflictos y respetando constraints. La asignación termina
    en un `Node(ref=mcu_ref, pin=<pin_resuelto>)` dentro de `net_name`.
    """
    model_config = ConfigDict(extra="forbid")

    mcu_ref: str
    net_name: str
    function: str  # I2C_SDA, I2C_SCL, SPI_SCK, SPI_MISO, SPI_MOSI, SPI_CS,
                   # UART_TX, UART_RX, ADC, DAC, PWM, GPIO, INT, GPIO_OUT
    bus_id: str | None = None  # agrupa requests del mismo bus físico
    require_output: bool = False  # si True, excluye pines input-only
    avoid: list[str] = Field(default_factory=list)


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcu_ref: str
    net_name: str
    pin: str
    function: str
    bus_id: str | None = None
    score: int


class AllocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    circuit: Circuit
    assignments: list[Assignment]
    issues: list[ValidationIssue]


# ────────────────────────────────────────────────────────────────────────────
# Mapping function → bus type / role
# ────────────────────────────────────────────────────────────────────────────


_BUS_OF_FUNCTION: dict[str, tuple[str, str]] = {
    # function: (bus_type_in_preferred_buses, role_field_name)
    "I2C_SDA": ("i2c", "sda"),
    "I2C_SCL": ("i2c", "scl"),
    "SPI_SCK": ("spi", "sck"),
    "SPI_MISO": ("spi", "miso"),
    "SPI_MOSI": ("spi", "mosi"),
    "SPI_CS": ("spi", "cs"),
    "UART_TX": ("uart", "tx"),
    "UART_RX": ("uart", "rx"),
}


# Para el orden determinista dentro de un bus_id.
_FUNCTION_BUS_ORDER: dict[str, int] = {
    "I2C_SDA": 0, "I2C_SCL": 1,
    "SPI_SCK": 0, "SPI_MISO": 1, "SPI_MOSI": 2, "SPI_CS": 3,
    "UART_TX": 0, "UART_RX": 1,
}


# Funciones que aceptan pines input-only (no necesitan manejar output).
# El resto (GPIO, PWM, UART_TX, SPI_SCK/MOSI/CS, I2C_SDA, I2C_SCL) requiere
# que el pin pueda manejar output.
_INPUT_ONLY_OK_FUNCTIONS = {
    "ADC", "DAC", "INT", "INPUT_ONLY",
    "UART_RX",     # el MCU recibe
    "SPI_MISO",    # en modo master, MISO es input
}


# ────────────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────────────


def allocate(
    circuit: Circuit,
    requests: Iterable[PinRequest],
) -> AllocationResult:
    requests = list(requests)
    registry = get_registry()
    issues: list[ValidationIssue] = []
    assignments: list[Assignment] = []

    # Mapa ref → ComponentSpec para los MCUs.
    mcu_spec: dict[str, ComponentSpec] = {}
    for c in circuit.components:
        spec = registry.get(c.type)
        if spec is not None and spec.category == "mcu" and spec.mcu is not None:
            mcu_spec[c.ref] = spec

    # Ocupación inicial: pines ya usados por nodos del MCU en el circuito.
    used_by_mcu: dict[str, set[str]] = {ref: set() for ref in mcu_spec}
    for net in circuit.nets:
        for node in net.nodes:
            if node.ref in mcu_spec and node.pin:
                used_by_mcu[node.ref].add(node.pin)

    # Sort determinista de requests:
    # 1. requests con bus_id primero (necesitan satisfacción coherente)
    # 2. dentro del mismo bus_id: por orden canónico (SDA antes que SCL, etc.)
    # 3. resto: por (mcu_ref, function, net_name)
    def _key(r: PinRequest) -> tuple:
        has_bus = 0 if r.bus_id else 1
        bus_order = _FUNCTION_BUS_ORDER.get(r.function, 99)
        return (has_bus, r.bus_id or "", bus_order, r.mcu_ref,
                r.function, r.net_name)
    sorted_requests = sorted(requests, key=_key)

    for req in sorted_requests:
        if req.mcu_ref not in mcu_spec:
            issues.append(ValidationIssue(
                code="PIN_REQUEST_INVALID_MCU",
                severity=Severity.ERROR,
                message=f"Request para '{req.mcu_ref}': componente no es un "
                        f"MCU registrado.",
                component=req.mcu_ref, net=req.net_name,
                rule="pin_allocator",
            ))
            continue

        spec = mcu_spec[req.mcu_ref]
        used = used_by_mcu[req.mcu_ref]

        candidates = _candidate_pins(spec, req)
        # Filtrar forbidden, used, avoid.
        avoid = set(req.avoid)
        available = [
            p for p in candidates
            if not spec.is_pin_forbidden(p.number)
            and p.number not in used
            and p.number not in avoid
        ]
        # Filtrar input-only si la función requiere output.
        if _is_output_function(req):
            available = [p for p in available
                         if not spec.is_pin_input_only(p.number)]

        if not available:
            issues.append(ValidationIssue(
                code="PIN_NO_AVAILABLE",
                severity=Severity.ERROR,
                message=f"{req.mcu_ref}/{req.net_name}: no hay pin disponible "
                        f"con función '{req.function}' (todos forbidden, "
                        f"used o sin capability).",
                component=req.mcu_ref, net=req.net_name,
                rule="pin_allocator",
            ))
            continue

        # Score y pick.
        scored = [(_score_pin(p, req, spec), p.number, p) for p in available]
        # Sort: score DESC, pin number ASC (determinista).
        scored.sort(key=lambda t: (-t[0], _pin_sort_key(t[1])))
        best_score, best_number, _ = scored[0]

        used.add(best_number)
        assignments.append(Assignment(
            mcu_ref=req.mcu_ref,
            net_name=req.net_name,
            pin=best_number,
            function=req.function,
            bus_id=req.bus_id,
            score=best_score,
        ))

    new_circuit = _apply_assignments(circuit, assignments)
    return AllocationResult(
        circuit=new_circuit,
        assignments=assignments,
        issues=issues,
    )


# ────────────────────────────────────────────────────────────────────────────
# Candidate pin selection
# ────────────────────────────────────────────────────────────────────────────


def _candidate_pins(spec: ComponentSpec, req: PinRequest) -> list[PinSpec]:
    """Pines del MCU que pueden satisfacer la función pedida."""
    fn = req.function.upper()
    out: list[PinSpec] = []

    # Casos especiales (PWM/ADC/DAC pueden estar en mcu.* en lugar de pin.functions).
    if fn == "PWM":
        for p in spec.pins:
            if "PWM" in p.functions:
                out.append(p)
                continue
            if spec.mcu and (
                "*" in spec.mcu.pwm_pins or p.number in spec.mcu.pwm_pins
            ):
                # Excluir power/reset/etc.
                if p.electrical_type.value in ("bidirectional", "output"):
                    out.append(p)
        return out

    if fn == "ADC":
        for p in spec.pins:
            if "ADC" in p.functions or "ADC1" in p.functions or "ADC2" in p.functions:
                out.append(p)
                continue
            if spec.mcu and p.number in spec.mcu.adc_pins:
                out.append(p)
        return out

    if fn == "DAC":
        for p in spec.pins:
            if "DAC" in p.functions or (spec.mcu and p.number in spec.mcu.dac_pins):
                out.append(p)
        return out

    if fn == "GPIO":
        # Cualquier pin GPIO genérico; bidireccional u output.
        for p in spec.pins:
            if "GPIO" not in p.functions:
                continue
            if p.electrical_type.value not in ("bidirectional", "output", "input"):
                continue
            out.append(p)
        return out

    # Caso estándar: la función debe estar en pin.functions.
    return [p for p in spec.pins if fn in p.functions]


# ────────────────────────────────────────────────────────────────────────────
# Scoring
# ────────────────────────────────────────────────────────────────────────────


def _score_pin(pin: PinSpec, req: PinRequest, spec: ComponentSpec) -> int:
    score = 0

    # +50 si el pin coincide con el preferred_bus para su función.
    bus_info = _BUS_OF_FUNCTION.get(req.function)
    if bus_info and spec.mcu and bus_info[0] in spec.mcu.preferred_buses:
        bus = spec.mcu.preferred_buses[bus_info[0]]
        preferred = getattr(bus, bus_info[1], None)
        if preferred and pin.number == preferred:
            score += 50

    # Penalización a strapping pins — afectan boot.
    if spec.mcu and pin.number in spec.mcu.boot_strapping_pins:
        score -= 10

    # Penalización liviana si el pin es input-only y la función puede usar output.
    if spec.mcu and pin.number in spec.mcu.input_only_pins:
        if _is_output_function(req):
            # No debería llegar acá (ya filtrado), pero por las dudas.
            score -= 100
        else:
            score -= 1

    # GPIO genérico: preferí pines "simples" (sin capabilities exclusivas)
    # para reservar los premium (I2C/SPI/ADC) para sus funciones específicas.
    if req.function.upper() == "GPIO":
        premium_caps = {"I2C_SDA", "I2C_SCL", "SPI_SCK", "SPI_MISO", "SPI_MOSI",
                        "SPI_CS", "UART_TX", "UART_RX", "ADC", "DAC", "ADC1",
                        "ADC2"}
        if not (set(pin.functions) & premium_caps):
            score += 5

    return score


def _is_output_function(req: PinRequest) -> bool:
    """¿La función requiere capacidad de manejo de output?"""
    if req.require_output:
        return True
    fn = req.function.upper()
    if fn in _INPUT_ONLY_OK_FUNCTIONS:
        return False
    return True  # default conservador: requiere output


# ────────────────────────────────────────────────────────────────────────────
# Sort key para tiebreak alfabético determinista
# ────────────────────────────────────────────────────────────────────────────


def _pin_sort_key(pin: str) -> tuple:
    """Sort 'GPIO2' antes que 'GPIO12' (numeric) cuando comparten prefijo.

    Para el caso ARDUINO con D0..D13 / A0..A5, queremos D2 antes que D10.
    Para ESP32 GPIO0..GPIO39, queremos GPIO2 antes que GPIO12.
    """
    import re
    m = re.match(r"^([A-Za-z_]*)(\d+)([A-Za-z_]*)$", pin)
    if m:
        prefix, num, suffix = m.groups()
        return (prefix, int(num), suffix)
    return (pin, 0, "")


# ────────────────────────────────────────────────────────────────────────────
# Apply assignments al Circuit
# ────────────────────────────────────────────────────────────────────────────


def _apply_assignments(
    circuit: Circuit,
    assignments: list[Assignment],
) -> Circuit:
    """Devuelve un Circuit nuevo con los nodos MCU resueltos.

    Para cada assignment (mcu_ref, net_name) → pin:
    - Si el net contiene un Node(ref=mcu_ref), reemplaza su pin.
    - Si no, agrega un Node nuevo con ese pin.
    """
    # Indice (mcu_ref, net_name) → pin asignado.
    by_pair: dict[tuple[str, str], str] = {
        (a.mcu_ref, a.net_name): a.pin for a in assignments
    }

    new_nets: list[Net] = []
    for net in circuit.nets:
        new_nodes: list[Node] = []
        replaced_for_refs: set[str] = set()
        for node in net.nodes:
            key = (node.ref, net.name)
            if key in by_pair:
                new_nodes.append(Node(ref=node.ref, pin=by_pair[key]))
                replaced_for_refs.add(node.ref)
            else:
                new_nodes.append(node)
        # Agregar nodos para asignaciones que no tenían un Node previo.
        for (mcu_ref, net_name), pin in by_pair.items():
            if net_name == net.name and mcu_ref not in replaced_for_refs:
                # Solo si no había ningún node de ese mcu_ref en este net.
                if not any(n.ref == mcu_ref for n in net.nodes):
                    new_nodes.append(Node(ref=mcu_ref, pin=pin))
                    replaced_for_refs.add(mcu_ref)
        new_nets.append(net.model_copy(update={"nodes": new_nodes}))

    return circuit.model_copy(update={"nets": new_nets})
