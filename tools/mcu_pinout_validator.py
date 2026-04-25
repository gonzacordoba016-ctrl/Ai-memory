# tools/mcu_pinout_validator.py
#
# Verifica post-generación que los pines usados en el netlist existan en el
# MCU declarado. Detecta errores como U1.D14 cuando U1 es Arduino Nano (D0-D13).
# Lógica Python pura — sin LLM, sin I/O.

from __future__ import annotations
from typing import Any

# ── Pines válidos por MCU ────────────────────────────────────────────────────

_POWER_PINS = {"VCC", "GND", "VIN", "5V", "3V3", "3.3V", "AREF", "RESET", "RST"}

MCU_VALID_PINS: dict[str, set[str]] = {
    "arduino_uno": (
        {f"D{i}" for i in range(14)} |        # D0-D13
        {f"A{i}" for i in range(6)} |          # A0-A5
        _POWER_PINS
    ),
    "arduino_nano": (
        {f"D{i}" for i in range(14)} |        # D0-D13
        {f"A{i}" for i in range(8)} |          # A0-A7
        _POWER_PINS
    ),
    "arduino_mega": (
        {f"D{i}" for i in range(54)} |        # D0-D53
        {f"A{i}" for i in range(16)} |         # A0-A15
        _POWER_PINS
    ),
    "esp32": (
        {f"GPIO{i}" for i in (
            0, 1, 2, 3, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19,
            21, 22, 23, 25, 26, 27, 32, 33, 34, 35, 36, 37, 38, 39,
        )} |
        _POWER_PINS | {"EN"}
    ),
    "esp8266": (
        {f"GPIO{i}" for i in (0, 2, 4, 5, 12, 13, 14, 15, 16)} |
        {"A0"} |
        _POWER_PINS | {"EN"}
    ),
    "raspberry_pi_pico": (
        {f"GP{i}" for i in range(29)} |        # GP0-GP28
        _POWER_PINS | {"VBUS", "VSYS", "RUN"}
    ),
    "stm32": (
        # Genérico: pines tipo PA0-PA15, PB0-PB15, PC0-PC15
        {f"P{port}{i}" for port in "ABCD" for i in range(16)} |
        _POWER_PINS
    ),
}

# Aliases — el LLM a veces escribe el tipo de forma distinta
_TYPE_ALIASES: dict[str, str] = {
    "arduino": "arduino_uno",
    "arduino uno": "arduino_uno",
    "arduino_nano": "arduino_nano",
    "arduino nano": "arduino_nano",
    "nano": "arduino_nano",
    "arduino_mega": "arduino_mega",
    "arduino mega": "arduino_mega",
    "mega": "arduino_mega",
    "uno": "arduino_uno",
    "esp32": "esp32",
    "esp8266": "esp8266",
    "rp2040": "raspberry_pi_pico",
    "pico": "raspberry_pi_pico",
    "raspberry_pi_pico": "raspberry_pi_pico",
    "raspberry pi pico": "raspberry_pi_pico",
    "stm32": "stm32",
}


def _normalize_mcu_type(raw: str) -> str | None:
    """Mapea el tipo crudo del componente a una clave de MCU_VALID_PINS."""
    if not raw:
        return None
    key = raw.lower().strip()
    if key in MCU_VALID_PINS:
        return key
    return _TYPE_ALIASES.get(key)


def _normalize_pin(pin: str) -> str:
    """Normaliza nombres de pin para matching tolerante."""
    return pin.upper().strip().replace(" ", "")


def validate_pinout(circuit: dict) -> list[str]:
    """
    Verifica que cada nodo U.PIN use un pin que exista en el MCU declarado.

    Args:
        circuit: dict con 'components' y 'nets'.

    Returns:
        Lista de strings con warnings (formato `[Pinout] ...`).
        Vacía si no hay errores o si no hay MCUs reconocibles.
    """
    components: list[dict] = circuit.get("components") or []
    nets: list[dict] = circuit.get("nets") or []

    # Mapear ID de componente → clave de MCU validable
    mcu_type_by_id: dict[str, str] = {}
    for c in components:
        ctype_raw = c.get("resolved_type") or c.get("type") or ""
        mcu_key = _normalize_mcu_type(ctype_raw)
        if mcu_key:
            mcu_type_by_id[c.get("id")] = mcu_key

    if not mcu_type_by_id:
        return []

    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()  # evitar warnings duplicados (mismo cid+pin)

    for net in nets:
        for node in net.get("nodes", []):
            if "." not in node:
                continue
            cid, pin = node.split(".", 1)
            mcu_key = mcu_type_by_id.get(cid)
            if not mcu_key:
                continue

            valid = MCU_VALID_PINS[mcu_key]
            pin_norm = _normalize_pin(pin)

            # Match directo o equivalencias VCC↔3V3↔5V
            if pin_norm in valid:
                continue
            if pin_norm in ("VCC", "3V3", "3.3V", "5V") and any(p in valid for p in ("VCC", "3V3", "5V")):
                continue

            key = (cid, pin_norm)
            if key in seen:
                continue
            seen.add(key)

            sample = sorted(p for p in valid if p not in _POWER_PINS)[:6]
            warnings.append(
                f"[Pinout] {cid} ({mcu_key}): pin '{pin}' no existe en este MCU. "
                f"Pines válidos (muestra): {', '.join(sample)}…"
            )

    return warnings
