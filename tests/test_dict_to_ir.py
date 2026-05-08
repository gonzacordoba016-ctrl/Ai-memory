"""Tests de paridad para el adaptador dict_to_ir.

Estructural: el Circuit producido por dict_to_ir debe matchear
semánticamente al IR golden escrito a mano (mismo set de componentes
y nets, ignorando net_class que el dict no transporta).

DRC parity: ejecutar electrical_drc sobre el dict y constraint_engine
sobre el IR adaptado debe producir el mismo set de violation codes.
"""
from __future__ import annotations

import pytest

from _golden_fixtures import ALL_FIXTURES
from _golden_fixtures_dict import ALL_FIXTURES_DICT
from tools.eda.ir.legacy import dict_to_ir


FIXTURE_NAMES = ["blink_led_esp32", "i2c_oled_dht22_esp32", "motor_l298n_arduino"]

# Gap semántico aceptado entre motores DRC: el legacy dispara NO_DECOUPLING_CAP
# cuando un MCU no tiene caps en absoluto; el nuevo motor (rules.py:169-184) solo
# dispara si HAY caps pero ninguno en VCC. Diferencia intencional — la nueva
# regla es menos estridente para circuitos minimalistas.
EXPECTED_LEGACY_ONLY: dict[str, set[str]] = {
    "blink_led_esp32": {"NO_DECOUPLING_CAP"},
    "i2c_oled_dht22_esp32": set(),
    "motor_l298n_arduino": {"NO_DECOUPLING_CAP"},
}


# ── Estructural ──────────────────────────────────────────────────────────────


class TestDictToIRStructural:

    @pytest.mark.parametrize("name", FIXTURE_NAMES)
    def test_metadata_matches(self, name):
        ir_golden = ALL_FIXTURES[name]()
        ir_from_dict = dict_to_ir(ALL_FIXTURES_DICT[name]())
        assert ir_from_dict.metadata.title == ir_golden.metadata.title
        assert ir_from_dict.metadata.mcu == ir_golden.metadata.mcu

    @pytest.mark.parametrize("name", FIXTURE_NAMES)
    def test_components_match(self, name):
        ir_golden = ALL_FIXTURES[name]()
        ir_from_dict = dict_to_ir(ALL_FIXTURES_DICT[name]())
        golden = {(c.ref, c.type, c.value) for c in ir_golden.components}
        produced = {(c.ref, c.type, c.value) for c in ir_from_dict.components}
        assert produced == golden

    @pytest.mark.parametrize("name", FIXTURE_NAMES)
    def test_nets_match(self, name):
        ir_golden = ALL_FIXTURES[name]()
        ir_from_dict = dict_to_ir(ALL_FIXTURES_DICT[name]())
        # Set de (net_name, frozenset((ref, pin))). Ignoramos net_class.
        def _key(net):
            return (net.name, frozenset((n.ref, n.pin) for n in net.nodes))
        golden = {_key(n) for n in ir_golden.nets}
        produced = {_key(n) for n in ir_from_dict.nets}
        assert produced == golden


# ── DRC parity ───────────────────────────────────────────────────────────────


class TestDRCParity:
    """Mismo set de violation codes entre legacy (dict) y nuevo motor (IR)."""

    @pytest.mark.parametrize("name", FIXTURE_NAMES)
    def test_violation_code_set_matches(self, name):
        from tools.electrical_drc import run_drc as legacy_drc
        from tools.eda.constraint_engine import run_drc as new_drc

        dict_fixture = ALL_FIXTURES_DICT[name]()
        ir_adapted = dict_to_ir(dict_fixture)

        legacy_result = legacy_drc(dict_fixture)
        new_result = new_drc(ir_adapted)

        # legacy expone errors/warnings/info; el nuevo motor además expone "issues".
        def _all_codes(result: dict) -> set[str]:
            codes: set[str] = set()
            for bucket in ("errors", "warnings", "info"):
                for i in result.get(bucket, []):
                    codes.add(i["code"])
            return codes

        legacy_codes = _all_codes(legacy_result)
        new_codes = _all_codes(new_result)

        only_legacy = legacy_codes - new_codes
        only_new = new_codes - legacy_codes
        expected_legacy_only = EXPECTED_LEGACY_ONLY[name]
        assert only_legacy == expected_legacy_only, (
            f"DRC legacy-only inesperado para {name}: "
            f"got={sorted(only_legacy)}, expected={sorted(expected_legacy_only)}"
        )
        assert only_new == set(), (
            f"DRC new-only inesperado para {name}: got={sorted(only_new)}"
        )
