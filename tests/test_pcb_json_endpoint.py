from api.routers.circuits import _build_pcb_json


def test_build_pcb_json_exposes_board_components_and_traces():
    circuit = {
        "name": "PCB JSON",
        "components": [
            {"id": "U1", "type": "esp32", "name": "ESP32"},
            {"id": "U2", "type": "bmp280", "name": "BMP280"},
            {"id": "S1", "type": "dht22", "name": "DHT22"},
            {"id": "OLED1", "type": "oled", "name": "OLED"},
        ],
        "nets": [
            {"name": "GND", "nodes": ["U1.GND", "U2.GND", "S1.GND", "OLED1.GND"]},
            {"name": "VCC_3V3", "nodes": ["U1.3V3", "U2.VCC", "S1.VCC", "OLED1.VCC"]},
            {"name": "I2C_SDA", "nodes": ["U1.GPIO21", "U2.SDA", "OLED1.SDA"]},
            {"name": "I2C_SCL", "nodes": ["U1.GPIO22", "U2.SCL", "OLED1.SCL"]},
        ],
    }

    payload = _build_pcb_json(circuit)

    assert payload["board"]["width_mm"] > 0
    assert payload["board"]["height_mm"] > 0
    assert payload["board"]["thickness_mm"] == 1.6
    assert {c["id"] for c in payload["components"]} == {"U1", "U2", "S1", "OLED1"}
    assert all("x_mm" in c and "y_mm" in c for c in payload["components"])
    assert payload["traces"]
    assert {t["layer"] for t in payload["traces"]} <= {"top", "bottom"}


def test_build_pcb_json_infers_specific_type_from_generic_sensor_name():
    circuit = {
        "name": "Legacy generic sensors",
        "components": [
            {"id": "U1", "type": "esp32", "name": "ESP32"},
            {"id": "U2", "type": "sensor", "name": "BMP280 Sensor"},
            {"id": "U3", "type": "sensor_i2c", "name": "DHT22 Temp/Humidity"},
            {"id": "U4", "type": "module", "name": "OLED Sensor"},
        ],
        "nets": [
            {"name": "GND", "nodes": ["U1.GND", "U2.GND", "U3.GND", "U4.GND"]},
            {"name": "VCC_3V3", "nodes": ["U1.3V3", "U2.VCC", "U3.VCC", "U4.VCC"]},
        ],
    }

    payload = _build_pcb_json(circuit)
    types_by_id = {c["id"]: c["type"] for c in payload["components"]}

    assert types_by_id["U2"] == "bmp280"
    assert types_by_id["U3"] == "dht22"
    assert types_by_id["U4"] == "oled"
