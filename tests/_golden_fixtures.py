"""
Fixtures de circuitos canónicos para golden tests.

Cada fixture es un Circuit IR construido a mano que representa un caso
de uso típico (blink LED, sensor I2C, motor driver). El pipeline determinista
sobre estos fixtures debe producir output byte-equivalente entre runs.
"""
from __future__ import annotations

from tools.eda.ir import (
    Circuit,
    CircuitMetadata,
    Component,
    Net,
    Node,
)


def blink_led_esp32() -> Circuit:
    """ESP32 + R + LED — el "hello world" de microcontrollers."""
    return Circuit(
        metadata=CircuitMetadata(
            title="blink_led_esp32",
            mcu="esp32",
            domain="iot",
            description="ESP32 con LED+resistencia en GPIO2",
        ),
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="R1", type="resistor", value="220"),
            Component(ref="LED1", type="led"),
        ],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="LED1", pin="cathode")]),
            Net(name="LED_DRIVE", nodes=[Node(ref="U1", pin="GPIO2"),
                                          Node(ref="R1", pin="1")]),
            Net(name="LED_ANODE", nodes=[Node(ref="R1", pin="2"),
                                          Node(ref="LED1", pin="anode")]),
        ],
    )


def i2c_oled_dht22_esp32() -> Circuit:
    """Sistema típico IoT: ESP32 + OLED I2C + DHT22 + decoupling."""
    return Circuit(
        metadata=CircuitMetadata(
            title="i2c_oled_dht22_esp32",
            mcu="esp32",
            domain="iot",
            description="ESP32 lee DHT22 y muestra en OLED I2C",
        ),
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="DISP", type="oled_ssd1306"),
            Component(ref="S1", type="dht22"),
            Component(ref="R1", type="resistor", value="4.7k"),
            Component(ref="R2", type="resistor", value="4.7k"),
            Component(ref="R3", type="resistor", value="10k"),
            Component(ref="C1", type="capacitor_electrolytic", value="100uF"),
            Component(ref="C2", type="capacitor", value="100nF"),
        ],
        nets=[
            Net(name="VCC", nodes=[
                Node(ref="U1", pin="VCC"),
                Node(ref="DISP", pin="VCC"),
                Node(ref="S1", pin="VCC"),
                Node(ref="R1", pin="2"),
                Node(ref="R2", pin="2"),
                Node(ref="R3", pin="2"),
                Node(ref="C1", pin="+"),
                Node(ref="C2", pin="1"),
            ]),
            Net(name="GND", nodes=[
                Node(ref="U1", pin="GND"),
                Node(ref="DISP", pin="GND"),
                Node(ref="S1", pin="GND"),
                Node(ref="C1", pin="-"),
                Node(ref="C2", pin="2"),
            ]),
            Net(name="SDA", nodes=[
                Node(ref="U1", pin="GPIO21"),
                Node(ref="DISP", pin="SDA"),
                Node(ref="R1", pin="1"),
            ]),
            Net(name="SCL", nodes=[
                Node(ref="U1", pin="GPIO22"),
                Node(ref="DISP", pin="SCL"),
                Node(ref="R2", pin="1"),
            ]),
            Net(name="DHT_DATA", nodes=[
                Node(ref="U1", pin="GPIO16"),
                Node(ref="S1", pin="DATA"),
                Node(ref="R3", pin="1"),
            ]),
        ],
    )


def motor_l298n_arduino() -> Circuit:
    """Driver L298N + Arduino Uno para 1 motor DC."""
    return Circuit(
        metadata=CircuitMetadata(
            title="motor_l298n_arduino",
            mcu="arduino_uno",
            domain="actuator",
            description="Arduino Uno controla 1 motor vía L298N",
        ),
        components=[
            Component(ref="U1", type="arduino_uno"),
            Component(ref="DRV", type="l298n"),
            Component(ref="M1", type="motor"),
        ],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="DRV", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="DRV", pin="GND")]),
            Net(name="MOTOR_IN1", nodes=[Node(ref="U1", pin="D5"),
                                           Node(ref="DRV", pin="IN1")]),
            Net(name="MOTOR_IN2", nodes=[Node(ref="U1", pin="D6"),
                                           Node(ref="DRV", pin="IN2")]),
            Net(name="MOTOR_OUT", net_class="high_current",
                nodes=[Node(ref="DRV", pin="OUT1"),
                       Node(ref="M1", pin="1")]),
            Net(name="MOTOR_RET", net_class="high_current",
                nodes=[Node(ref="DRV", pin="OUT2"),
                       Node(ref="M1", pin="2")]),
        ],
    )


ALL_FIXTURES = {
    "blink_led_esp32": blink_led_esp32,
    "i2c_oled_dht22_esp32": i2c_oled_dht22_esp32,
    "motor_l298n_arduino": motor_l298n_arduino,
}
