# tests/test_circuit_importer.py
import pytest
from conftest import KICAD_SCH_SAMPLE, EAGLE_SCH_SAMPLE
from tools.circuit_importer import import_kicad, import_eagle, import_circuit_file


class TestKiCadImport:
    def test_returns_dict(self):
        result = import_kicad(KICAD_SCH_SAMPLE, "test.kicad_sch")
        assert isinstance(result, dict)
        assert "error" not in result

    def test_components_extracted(self):
        result = import_kicad(KICAD_SCH_SAMPLE, "test.kicad_sch")
        assert len(result["components"]) >= 2
        ids = [c["id"] for c in result["components"]]
        assert "R1" in ids
        assert "D1" in ids

    def test_component_has_required_fields(self):
        result = import_kicad(KICAD_SCH_SAMPLE, "test.kicad_sch")
        for comp in result["components"]:
            assert "id" in comp
            assert "type" in comp
            assert "name" in comp

    def test_nets_extracted(self):
        result = import_kicad(KICAD_SCH_SAMPLE, "test.kicad_sch")
        assert len(result["nets"]) >= 1
        names = [n["name"] for n in result["nets"]]
        assert "VCC" in names

    def test_title_extracted(self):
        result = import_kicad(KICAD_SCH_SAMPLE, "test.kicad_sch")
        assert result["name"] == "Test Schematic"

    def test_source_format(self):
        result = import_kicad(KICAD_SCH_SAMPLE, "test.kicad_sch")
        assert result["source_format"] == "kicad"

    def test_invalid_content_returns_error(self):
        result = import_kicad("not a kicad file at all", "bad.kicad_sch")
        assert "error" in result

    def test_power_symbols_excluded(self):
        # Power symbols (#PWR, #FLG) should not appear as components
        result = import_kicad(KICAD_SCH_SAMPLE, "test.kicad_sch")
        ids = [c["id"] for c in result["components"]]
        assert not any(i.startswith("#") for i in ids)


class TestEagleImport:
    def test_returns_dict(self):
        result = import_eagle(EAGLE_SCH_SAMPLE, "test.sch")
        assert isinstance(result, dict)
        assert "error" not in result

    def test_components_extracted(self):
        result = import_eagle(EAGLE_SCH_SAMPLE, "test.sch")
        assert len(result["components"]) == 3
        ids = [c["id"] for c in result["components"]]
        assert "R1" in ids
        assert "C1" in ids
        assert "U1" in ids

    def test_component_value(self):
        result = import_eagle(EAGLE_SCH_SAMPLE, "test.sch")
        r1 = next(c for c in result["components"] if c["id"] == "R1")
        assert r1["value"] == "10k"

    def test_nets_with_nodes(self):
        result = import_eagle(EAGLE_SCH_SAMPLE, "test.sch")
        vcc = next(n for n in result["nets"] if n["name"] == "VCC")
        assert "R1.1" in vcc["nodes"]
        assert "U1.VCC" in vcc["nodes"]

    def test_source_format(self):
        result = import_eagle(EAGLE_SCH_SAMPLE, "test.sch")
        assert result["source_format"] == "eagle"

    def test_type_inference(self):
        result = import_eagle(EAGLE_SCH_SAMPLE, "test.sch")
        r1 = next(c for c in result["components"] if c["id"] == "R1")
        assert r1["type"] == "resistor"
        c1 = next(c for c in result["components"] if c["id"] == "C1")
        assert c1["type"] == "capacitor"


class TestDispatcher:
    def test_kicad_sch_extension(self):
        result = import_circuit_file(KICAD_SCH_SAMPLE, "circuit.kicad_sch")
        assert "error" not in result
        assert result["source_format"] == "kicad"

    def test_eagle_sch_extension_xml(self):
        result = import_circuit_file(EAGLE_SCH_SAMPLE, "circuit.sch")
        assert "error" not in result
        assert result["source_format"] == "eagle"

    def test_unsupported_extension(self):
        result = import_circuit_file("some content", "circuit.brd")
        assert "error" in result

    def test_kicad5_legacy_error(self):
        kicad5 = "EESchema Schematic File Version 4\nsome content"
        result = import_circuit_file(kicad5, "circuit.sch")
        assert "error" in result
        assert "KiCad 5" in result["error"]
