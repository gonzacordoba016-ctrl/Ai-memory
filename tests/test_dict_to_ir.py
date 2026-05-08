"""Tests estructurales del adaptador dict_to_ir.

El Circuit producido por dict_to_ir debe matchear semánticamente al IR golden
escrito a mano (mismo set de componentes y nets, ignorando net_class que el
dict no transporta).
"""
from __future__ import annotations

import pytest

from _golden_fixtures import ALL_FIXTURES
from _golden_fixtures_dict import ALL_FIXTURES_DICT
from tools.eda.ir.legacy import dict_to_ir


FIXTURE_NAMES = ["blink_led_esp32", "i2c_oled_dht22_esp32", "motor_l298n_arduino"]


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


