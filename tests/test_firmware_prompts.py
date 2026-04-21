# tests/test_firmware_prompts.py
# Verifica que los prompts de firmware_generator incluyen las instrucciones
# de producción (watchdog, OTA, STATE serial) sin llamar al LLM.
import pytest
from tools.firmware_generator import PLATFORM_PROMPTS, _clean_code


class TestPlatformPrompts:
    def test_all_platforms_defined(self):
        expected = {"arduino:avr", "esp32:esp32", "esp8266:esp8266", "micropython"}
        assert expected.issubset(set(PLATFORM_PROMPTS.keys()))

    def test_arduino_has_watchdog(self):
        prompt = PLATFORM_PROMPTS["arduino:avr"]
        assert "wdt" in prompt.lower() or "watchdog" in prompt.lower()

    def test_arduino_has_state_serial(self):
        prompt = PLATFORM_PROMPTS["arduino:avr"]
        assert "STATE:" in prompt

    def test_esp32_has_watchdog(self):
        prompt = PLATFORM_PROMPTS["esp32:esp32"]
        assert "wdt" in prompt.lower() or "watchdog" in prompt.lower()

    def test_esp32_has_ota(self):
        prompt = PLATFORM_PROMPTS["esp32:esp32"]
        assert "ArduinoOTA" in prompt or "OTA" in prompt

    def test_esp32_has_state_serial(self):
        prompt = PLATFORM_PROMPTS["esp32:esp32"]
        assert "STATE:" in prompt

    def test_esp8266_has_watchdog(self):
        prompt = PLATFORM_PROMPTS["esp8266:esp8266"]
        assert "wdt" in prompt.lower() or "watchdog" in prompt.lower()

    def test_esp8266_has_ota(self):
        prompt = PLATFORM_PROMPTS["esp8266:esp8266"]
        assert "OTA" in prompt or "ArduinoOTA" in prompt

    def test_esp8266_has_state_serial(self):
        prompt = PLATFORM_PROMPTS["esp8266:esp8266"]
        assert "STATE:" in prompt

    def test_micropython_has_watchdog(self):
        prompt = PLATFORM_PROMPTS["micropython"]
        assert "WDT" in prompt or "watchdog" in prompt.lower()

    def test_micropython_has_state_serial(self):
        prompt = PLATFORM_PROMPTS["micropython"]
        assert "STATE:" in prompt

    def test_micropython_has_error_handling(self):
        prompt = PLATFORM_PROMPTS["micropython"]
        assert "try" in prompt or "except" in prompt


class TestCleanCode:
    def test_removes_backtick_block(self):
        raw = "```cpp\nint x = 1;\n```"
        cleaned = _clean_code(raw)
        assert "```" not in cleaned
        assert "int x = 1;" in cleaned

    def test_removes_language_marker(self):
        raw = "```arduino\nvoid setup(){}\n```"
        cleaned = _clean_code(raw)
        assert "```" not in cleaned

    def test_preserves_code_content(self):
        raw = "void setup() {}\nvoid loop() {}"
        cleaned = _clean_code(raw)
        assert "void setup" in cleaned
        assert "void loop" in cleaned

    def test_strips_leading_trailing_whitespace(self):
        raw = "\n\nvoid setup(){}\n\n"
        cleaned = _clean_code(raw)
        assert not cleaned.startswith("\n")
        assert not cleaned.endswith("\n")

    def test_empty_input(self):
        cleaned = _clean_code("")
        assert cleaned == ""
