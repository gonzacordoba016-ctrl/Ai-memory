"""
Tests para fixes 2026-05-07 — bugs reportados en sesión real:

1. `_keyword_route` no captaba "diseña ESP32 con un LED" / "ESP32 que lea
   un sensor BMP280" → caía a hardware en vez de circuit_design.
2. `circuit_synthesizer._find_handler` crasheaba con AttributeError cuando
   el LLM emitía `null` en `interface` / `type` / `model` (`dict.get(k, "")`
   devuelve None, no el default, cuando la key existe con value=null).
"""
from __future__ import annotations

import pytest


# ─── Bug 2: defensive null handling en _find_handler ──────────────────────


def test_find_handler_handles_null_interface():
    from tools.circuit_synthesizer import CircuitSynthesizer
    s = CircuitSynthesizer()
    block = {"model": "bmp280", "interface": None, "type": None}
    # Antes: AttributeError: 'NoneType' object has no attribute 'lower'
    handler = s._find_handler(block)
    assert handler is not None  # bmp280 → _add_i2c_sensor_block


def test_find_handler_handles_null_model():
    from tools.circuit_synthesizer import CircuitSynthesizer
    s = CircuitSynthesizer()
    block = {"model": None, "interface": "i2c", "type": None}
    # No debe crashear — devuelve None o handler genérico.
    s._find_handler(block)


def test_find_handler_handles_all_null():
    from tools.circuit_synthesizer import CircuitSynthesizer
    s = CircuitSynthesizer()
    s._find_handler({"model": None, "interface": None, "type": None})
    s._find_handler({})  # diccionario vacío


# ─── Bug 1: routing keywords ──────────────────────────────────────────────


@pytest.fixture
def orch():
    from agent.orchestrator import Orchestrator
    return Orchestrator(client_fn=lambda *a, **k: None)


def test_disena_esp32_con_led_routes_to_circuit_design(orch):
    """Antes: → ['hardware']. Ahora: → ['circuit_design'] vía regex MCU+comp."""
    result = orch._keyword_route("diseña ESP32 con un LED parpadeando en GPIO2")
    assert result == ["circuit_design"]


def test_esp32_lee_sensor_bmp280_routes_to_circuit_design(orch):
    result = orch._keyword_route(
        "ESP32 que lea un sensor BMP280 por I2C y muestre temperatura en una pantalla OLED"
    )
    assert result == ["circuit_design"]


def test_esp32_con_led_sin_verbo_routes_to_circuit_design(orch):
    """Sin verbo de creación pero con MCU + componente periférico."""
    result = orch._keyword_route("ESP32 con un LED parpadeando en GPIO2")
    assert result == ["circuit_design"]


def test_arduino_relay_lampara_routes_to_circuit_design(orch):
    result = orch._keyword_route(
        "Arduino Uno que controle un relé para prender una lámpara 220VAC"
    )
    assert result == ["circuit_design"]


def test_5_bombas_arduino_mega_routes_to_circuit_design(orch):
    """Caso histórico v4.13.0 — debe seguir cayendo a circuit_design."""
    result = orch._keyword_route(
        "5 bombas hidráulicas controladas por Arduino Mega con red eléctrica 220VAC"
    )
    assert result == ["circuit_design"]


def test_disenar_circuito_explicit_still_routes_circuit_design(orch):
    """Regresión — el regex previo (verbo + sustantivo) sigue funcionando."""
    result = orch._keyword_route(
        "Diseñame un circuito con ESP32 y BMP280"
    )
    assert result == ["circuit_design"]


# ─── No-regresión: queries de hardware no deben caer a circuit_design ────


def test_codigo_para_esp32_does_not_route_to_circuit_design(orch):
    """'código para ESP32' debe seguir siendo hardware (firmware)."""
    result = orch._keyword_route("código para ESP32 que lee un sensor")
    # No debe ser circuit_design (hardware o LLM fallback son ambos OK).
    assert result != ["circuit_design"]


def test_como_configuro_spi_does_not_route_to_circuit_design(orch):
    """Pregunta conceptual — no es pedido de diseño."""
    result = orch._keyword_route("cómo configuro la SPI en ESP32")
    assert result != ["circuit_design"]


def test_greeting_routes_to_none(orch):
    assert orch._keyword_route("hola") is None


def test_date_question_does_not_route_to_circuit_design(orch):
    """Pregunta conceptual no relacionada — no debe ser circuit_design."""
    result = orch._keyword_route("qué día es hoy")
    assert result != ["circuit_design"]
