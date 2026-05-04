"""
CircuitSynthesizer — síntesis determinística de netlists por composición de bloques.

El LLM extrae el SPEC (mcu + lista de bloques).
Esta clase construye CÓMO se conectan, iterando cada bloque con su handler.
Sin LLM para topología → cero nets duplicadas, cero flotantes, protecciones garantizadas.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Tablas de VCC por MCU ───────────────────────────────────────────────────

_MCU_VCC_PIN: Dict[str, str] = {
    "arduino uno":        "5V",
    "arduino nano":       "5V",
    "arduino mega":       "5V",
    "esp32":              "3V3",
    "esp8266":            "3V3",
    "stm32":              "3V3",
    "raspberry pi pico":  "3V3",
}


def _mcu_key(mcu: str) -> str:
    return mcu.lower().strip()


# ─── Constraints eléctricos por MCU ──────────────────────────────────────────

@dataclass
class ElectricalConstraints:
    gpio_max_ma: float        # Max corriente por GPIO (mA)
    total_max_ma: float       # Max corriente total de todos los GPIOs (mA)
    supported_vcc: List[float]  # Voltajes VCC soportados (V)


_MCU_ELECTRICAL_CONSTRAINTS: Dict[str, ElectricalConstraints] = {
    "arduino uno":        ElectricalConstraints(40.0,  200.0,  [5.0]),
    "arduino nano":       ElectricalConstraints(40.0,  200.0,  [5.0]),
    "arduino mega":       ElectricalConstraints(40.0,  200.0,  [5.0]),
    "esp32":              ElectricalConstraints(40.0,  1200.0, [3.3]),
    "esp8266":            ElectricalConstraints(12.0,  300.0,  [3.3]),
    "stm32":              ElectricalConstraints(25.0,  150.0,  [3.3]),
    "raspberry pi pico":  ElectricalConstraints(12.0,  51.0,   [3.3]),
}


# ─── Normalización de nets de poder ──────────────────────────────────────────

_GND_NAMES: frozenset = frozenset({
    "GND", "GROUND", "AGND", "DGND", "GND_REF", "VSS", "0V",
})
_GND_SUFFIX_RE = re.compile(r'_GND$|_GROUND$', re.IGNORECASE)

# Solo nombres genéricos sin voltaje explícito se normalizan.
# VCC_5V, VCC_3V3, VCC_12V son intencionales y no se tocan.
_VCC_GENERIC_NAMES: frozenset = frozenset({
    "VCC", "VDD", "POWER", "SUPPLY", "VCC_LOCAL", "VDD_LOCAL",
})

# Mapeo de descripciones en lenguaje natural → tipos de bloque conocidos.
# Usado por _find_handler cuando el LLM emite nombres no normalizados.
BLOCK_TYPE_ALIASES: Dict[str, str] = {
    "sensor de humedad de suelo": "moisture_sensor",
    "sensor de temperatura":      "dht22",
    "sensor de presion":          "bmp280",
    "sensor de presión":          "bmp280",
    "pantalla":                   "oled",
    "display":                    "oled",
    "motor paso a paso":          "stepper",
    "valvula":                    "relay",
    "válvula":                    "relay",
    "bomba":                      "relay",
    "ventilador":                 "relay",
}


# ─── Primitivas de construcción ──────────────────────────────────────────────

@dataclass
class _Net:
    name: str
    nodes: List[str] = field(default_factory=list)

    def connect(self, *nodes: str) -> "_Net":
        for n in nodes:
            if n not in self.nodes:
                self.nodes.append(n)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "nodes": self.nodes}


class CircuitBuilder:
    """
    Constructor de netlists programático.

    Garantías:
    - Ningún nodo puede aparecer en dos nets distintas (collision guard).
    - Ningún componente queda flotante (detectado en build).
    - Nets de poder se normalizan automáticamente en connect():
        * Variantes de tierra (LED_GND, AGND…) → "GND"
        * Variantes genéricas de VCC (VCC, POWER…) → vcc_net canónica
    """

    def __init__(self, name: str, description: str, power: str = "5V USB",
                 vcc_net: str = "VCC_5V"):
        self.name = name
        self.description = description
        self.power = power
        self._vcc_net = vcc_net
        self._components: List[Dict[str, Any]] = []
        self._nets: Dict[str, _Net] = {}
        self._all_nodes: Dict[str, str] = {}

    def _normalize_net_name(self, name: str) -> str:
        upper = name.upper()
        if upper in _GND_NAMES or _GND_SUFFIX_RE.search(name):
            return "GND"
        if upper in _VCC_GENERIC_NAMES:
            return self._vcc_net
        return name

    def add_component(self, id: str, name: str, type: str, **attrs) -> str:
        self._components.append({"id": id, "name": name, "type": type, **attrs})
        return id

    def net(self, name: str) -> _Net:
        if name not in self._nets:
            self._nets[name] = _Net(name)
        return self._nets[name]

    def connect(self, net_name: str, *nodes: str) -> "_Net":
        net_name = self._normalize_net_name(net_name)
        n = self.net(net_name)
        for node in nodes:
            if node in self._all_nodes and self._all_nodes[node] != net_name:
                raise ValueError(
                    f"Colisión de nodo: '{node}' ya está en net "
                    f"'{self._all_nodes[node]}', no puede ir también en '{net_name}'"
                )
            self._all_nodes[node] = net_name
        n.connect(*nodes)
        return n

    def build(self) -> Dict[str, Any]:
        connected_ids = {node.split(".")[0] for node in self._all_nodes}
        comp_ids = {c["id"] for c in self._components}
        floating = comp_ids - connected_ids
        warnings = [f"Componente flotante: {cid}" for cid in sorted(floating)]

        return {
            "name": self.name,
            "description": self.description,
            "components": self._components,
            "nets": [n.to_dict() for n in self._nets.values() if n.nodes],
            "power": self.power,
            "warnings": warnings,
            "_synthesized": True,
        }


# ─── PinAllocator ─────────────────────────────────────────────────────────────

class PinAllocator:
    """
    Asigna pines del MCU por función eléctrica sin hardcodeo en los handlers.
    Trackea pines usados para evitar conflictos entre bloques.

    Uso:
        allocator = PinAllocator("ESP32")
        sda = allocator.allocate("I2C_SDA")          # → "GPIO21"
        led = allocator.allocate("GPIO_OUTPUT")       # → "GPIO2"
        led2 = allocator.allocate("GPIO_OUTPUT")      # → "GPIO4" (siguiente libre)
        led3 = allocator.allocate("GPIO_OUTPUT", "GPIO5")  # pin específico solicitado
    """

    _PIN_TABLE: Dict[str, Dict[str, List[str]]] = {
        "arduino uno": {
            "I2C_SDA":     ["A4"],
            "I2C_SCL":     ["A5"],
            "SPI_MOSI":    ["D11"],
            "SPI_MISO":    ["D12"],
            "SPI_SCK":     ["D13"],
            "SPI_CS":      ["D10", "D9", "D8"],
            "UART_TX":     ["D1"],
            "UART_RX":     ["D0"],
            "GPIO_OUTPUT": ["D2","D3","D4","D5","D6","D7","D8","D9","D10","D11","D12","D13"],
            "PWM_OUTPUT":  ["D3","D5","D6","D9","D10","D11"],
            "ADC_INPUT":   ["A0","A1","A2","A3"],
        },
        "arduino nano": {
            "I2C_SDA":     ["A4"],
            "I2C_SCL":     ["A5"],
            "SPI_MOSI":    ["D11"],
            "SPI_MISO":    ["D12"],
            "SPI_SCK":     ["D13"],
            "SPI_CS":      ["D10", "D9", "D8"],
            "UART_TX":     ["D1"],
            "UART_RX":     ["D0"],
            "GPIO_OUTPUT": ["D2","D3","D4","D5","D6","D7","D8","D9","D10","D11","D12","D13"],
            "PWM_OUTPUT":  ["D3","D5","D6","D9","D10","D11"],
            "ADC_INPUT":   ["A0","A1","A2","A3"],
        },
        "arduino mega": {
            "I2C_SDA":     ["D20"],
            "I2C_SCL":     ["D21"],
            "SPI_MOSI":    ["D51"],
            "SPI_MISO":    ["D50"],
            "SPI_SCK":     ["D52"],
            "SPI_CS":      ["D53", "D49", "D48", "D47"],
            "UART_TX":     ["D18", "D16", "D14"],
            "UART_RX":     ["D19", "D17", "D15"],
            "GPIO_OUTPUT": ["D2","D3","D4","D5","D6","D7","D8","D9","D10","D11","D12","D13"],
            "PWM_OUTPUT":  ["D2","D3","D4","D5","D6","D7","D8","D9","D10","D11","D12","D13"],
            "ADC_INPUT":   ["A0","A1","A2","A3","A4","A5","A6","A7"],
        },
        "esp32": {
            "I2C_SDA":     ["GPIO21"],
            "I2C_SCL":     ["GPIO22"],
            "SPI_MOSI":    ["GPIO23"],
            "SPI_MISO":    ["GPIO19"],
            "SPI_SCK":     ["GPIO18"],
            "SPI_CS":      ["GPIO5", "GPIO15", "GPIO0", "GPIO27"],
            "UART_TX":     ["GPIO17", "GPIO10"],
            "UART_RX":     ["GPIO16", "GPIO9"],
            "GPIO_OUTPUT": ["GPIO2","GPIO4","GPIO5","GPIO12","GPIO13","GPIO14","GPIO15","GPIO16","GPIO17","GPIO18"],
            "PWM_OUTPUT":  ["GPIO2","GPIO4","GPIO5","GPIO12","GPIO13","GPIO14","GPIO15","GPIO16"],
            "ADC_INPUT":   ["GPIO32","GPIO33","GPIO34","GPIO35","GPIO36","GPIO39"],
        },
        "esp8266": {
            "I2C_SDA":     ["GPIO4"],
            "I2C_SCL":     ["GPIO5"],
            "SPI_MOSI":    ["GPIO13"],
            "SPI_MISO":    ["GPIO12"],
            "SPI_SCK":     ["GPIO14"],
            "SPI_CS":      ["GPIO15", "GPIO4"],
            "UART_TX":     ["GPIO1"],
            "UART_RX":     ["GPIO3"],
            "GPIO_OUTPUT": ["GPIO0","GPIO2","GPIO4","GPIO5","GPIO12","GPIO13","GPIO14","GPIO15"],
            "PWM_OUTPUT":  ["GPIO4","GPIO5","GPIO12","GPIO13","GPIO14"],
            "ADC_INPUT":   ["A0"],
        },
        "stm32": {
            "I2C_SDA":     ["PB7","PB9","PC9"],
            "I2C_SCL":     ["PB6","PB8","PA8"],
            "SPI_MOSI":    ["PA7", "PB15"],
            "SPI_MISO":    ["PA6", "PB14"],
            "SPI_SCK":     ["PA5", "PB13"],
            "SPI_CS":      ["PA4", "PA15", "PB12"],
            "UART_TX":     ["PA9", "PA2", "PB10"],
            "UART_RX":     ["PA10", "PA3", "PB11"],
            "GPIO_OUTPUT": ["PA0","PA1","PA2","PA3","PA4","PA5","PA6","PA7","PB0","PB1"],
            "PWM_OUTPUT":  ["PA0","PA1","PA2","PA3","PA6","PA7","PB0","PB1"],
            "ADC_INPUT":   ["PA0","PA1","PA2","PA3","PA4","PA5","PA6","PA7"],
        },
        "raspberry pi pico": {
            "I2C_SDA":     ["GP4","GP6","GP8","GP10","GP12","GP14","GP16","GP18","GP20","GP26"],
            "I2C_SCL":     ["GP5","GP7","GP9","GP11","GP13","GP15","GP17","GP19","GP21","GP27"],
            "SPI_MOSI":    ["GP3", "GP11", "GP19"],
            "SPI_MISO":    ["GP4", "GP12", "GP16"],
            "SPI_SCK":     ["GP2", "GP10", "GP18"],
            "SPI_CS":      ["GP5", "GP13", "GP17", "GP21"],
            "UART_TX":     ["GP0", "GP4", "GP8", "GP12"],
            "UART_RX":     ["GP1", "GP5", "GP9", "GP13"],
            "GPIO_OUTPUT": ["GP0","GP1","GP2","GP3","GP6","GP7","GP8","GP9","GP10","GP11","GP12","GP13"],
            "PWM_OUTPUT":  ["GP0","GP1","GP2","GP3","GP4","GP5","GP6","GP7"],
            "ADC_INPUT":   ["GP26","GP27","GP28"],
        },
    }

    def __init__(self, mcu: str):
        self._mcu = _mcu_key(mcu)
        self._used: set = set()
        self._pins = self._PIN_TABLE.get(self._mcu, {})

    def allocate(self, function: str, requested: Optional[str] = None) -> str:
        """
        Asigna el próximo pin libre para la función dada.
        Si `requested` está especificado y libre, lo usa directamente.
        Raises ValueError si no hay pines disponibles para esa función.
        """
        if requested and requested not in self._used:
            self._used.add(requested)
            return requested

        pool = self._pins.get(function, [])
        for pin in pool:
            if pin not in self._used:
                self._used.add(pin)
                return pin

        raise ValueError(
            f"PinAllocator: sin pines disponibles para {function!r} "
            f"en '{self._mcu}'. Usados: {sorted(self._used)}"
        )

    def release(self, pin: str) -> None:
        self._used.discard(pin)


# ─── Contexto de síntesis ────────────────────────────────────────────────────

@dataclass
class _SynthesisContext:
    """Estado mutable compartido entre todos los block handlers de un mismo circuito."""
    mcu: str
    vcc: float
    pin_allocator: PinAllocator = field(default=None)  # type: ignore[assignment]
    _counters: Dict[str, int] = field(default_factory=dict)
    _i2c_pullups_added: bool = False
    _i2c_sda_pin: str = ""
    _i2c_scl_pin: str = ""
    _spi_added: bool = False
    _spi_mosi_pin: str = ""
    _spi_miso_pin: str = ""
    _spi_sck_pin: str = ""
    _unknown_blocks: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.pin_allocator is None:
            self.pin_allocator = PinAllocator(self.mcu)

    def next_id(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}{n}"

    @property
    def vcc_net(self) -> str:
        return "VCC_3V3" if "3" in _MCU_VCC_PIN.get(_mcu_key(self.mcu), "5V") else "VCC_5V"

    @property
    def mcu_vcc_pin(self) -> str:
        return _MCU_VCC_PIN.get(_mcu_key(self.mcu), "5V")

    # ── Bus helpers ───────────────────────────────────────────────────────────

    def get_or_create_i2c_bus(self, b: CircuitBuilder, block: Dict[str, Any]) -> None:
        """Inicializa bus I2C (pull-ups + pines). Idempotente: solo una vez por circuito."""
        if self._i2c_pullups_added:
            return
        sda = self.pin_allocator.allocate("I2C_SDA", block.get("sda_pin"))
        scl = self.pin_allocator.allocate("I2C_SCL", block.get("scl_pin"))
        self._i2c_sda_pin, self._i2c_scl_pin = sda, scl
        r_sda = self.next_id("R")
        r_scl = self.next_id("R")
        b.add_component(r_sda, "Pull-up SDA 4.7kΩ", "resistor",
                        value="4700", unit="Ω", current_ma=1.0)
        b.add_component(r_scl, "Pull-up SCL 4.7kΩ", "resistor",
                        value="4700", unit="Ω", current_ma=1.0)
        b.connect(self.vcc_net, f"{r_sda}.1", f"{r_scl}.1")
        b.connect("I2C_SDA", f"U1.{sda}", f"{r_sda}.2")
        b.connect("I2C_SCL", f"U1.{scl}", f"{r_scl}.2")
        self._i2c_pullups_added = True

    def get_or_create_spi_bus(self, b: CircuitBuilder, block: Dict[str, Any]) -> str:
        """
        Inicializa bus SPI si no existe. MOSI/MISO/SCK son compartidos.
        Retorna el net name de CS exclusivo para este dispositivo.
        """
        if not self._spi_added:
            mosi = self.pin_allocator.allocate("SPI_MOSI", block.get("mosi_pin"))
            miso = self.pin_allocator.allocate("SPI_MISO", block.get("miso_pin"))
            sck  = self.pin_allocator.allocate("SPI_SCK",  block.get("sck_pin"))
            self._spi_mosi_pin, self._spi_miso_pin, self._spi_sck_pin = mosi, miso, sck
            b.connect("SPI_MOSI", f"U1.{mosi}")
            b.connect("SPI_MISO", f"U1.{miso}")
            b.connect("SPI_SCK",  f"U1.{sck}")
            self._spi_added = True
        # CS exclusivo por dispositivo
        cs_pin = self.pin_allocator.allocate("SPI_CS", block.get("cs_pin"))
        cs_idx = self.next_id("CS")[2:]  # "CS1" → "1"
        cs_net = f"SPI_CS{cs_idx}"
        b.connect(cs_net, f"U1.{cs_pin}")
        return cs_net

    def get_or_create_uart(self, b: CircuitBuilder, block: Dict[str, Any]) -> str:
        """
        Asigna TX/RX dedicados para un canal UART (no compartidos).
        Retorna el índice del canal ("1", "2", ...) para nombrar nets.
        """
        tx = self.pin_allocator.allocate("UART_TX", block.get("tx_pin"))
        rx = self.pin_allocator.allocate("UART_RX", block.get("rx_pin"))
        uid = self.next_id("UART")[4:]  # "UART1" → "1"
        b.connect(f"UART{uid}_TX", f"U1.{tx}")
        b.connect(f"UART{uid}_RX", f"U1.{rx}")
        return uid


# ─── CircuitSynthesizer ──────────────────────────────────────────────────────

class CircuitSynthesizer:
    """
    Síntesis determinística de netlists por composición de bloques.

    El LLM emite un spec:
        {
            "mcu": "ESP32",
            "blocks": [
                {"type": "sensor", "model": "BMP280", "interface": "I2C"},
                {"type": "output", "model": "LED"}
            ]
        }

    synthesize(spec) crea el circuito base, itera los bloques, aplica el
    handler de cada uno, y ejecuta validate_structure + validate_electrical_constraints
    antes de devolver.

    Para agregar un bloque nuevo: implementar _add_<modelo>_block y
    registrarlo en _find_handler.
    """

    def synthesize(self, spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        mcu = spec.get("mcu", "Arduino Uno")
        blocks = spec.get("blocks", [])
        if not blocks:
            return None

        vcc_pin = _MCU_VCC_PIN.get(_mcu_key(mcu), "5V")
        vcc = float(spec.get("vcc", 3.3 if "3" in vcc_pin else 5.0))
        ctx = _SynthesisContext(mcu=mcu, vcc=vcc)
        ctx._counters["U"] = 1  # U1 reservado para MCU

        block_labels = [b.get("model", b.get("type", "?")) for b in blocks]
        b = CircuitBuilder(
            name=f"{mcu} — {', '.join(block_labels)}",
            description=f"Circuito compuesto: MCU={mcu}, bloques={', '.join(block_labels)}.",
            power=f"{vcc}V USB",
            vcc_net=ctx.vcc_net,
        )

        b.add_component("U1", mcu, "microcontroller")
        b.connect("GND", "U1.GND")
        b.connect(ctx.vcc_net, f"U1.{ctx.mcu_vcc_pin}")

        for block in blocks:
            handler = self._find_handler(block)
            if handler is None:
                label = block.get("model", block.get("type", "desconocido"))
                ctx._unknown_blocks.append(label)
                continue
            handler(b, block, ctx)

        result = b.build()
        result["_mcu"] = mcu
        result["_vcc"] = vcc

        if ctx._unknown_blocks:
            result["warnings"].append(
                f"Bloques sin handler (ignorados): {', '.join(ctx._unknown_blocks)}"
            )

        self.validate_structure(result)
        self.validate_electrical_constraints(result)
        return result

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _find_handler(self, block: Dict[str, Any]) -> Optional[Callable]:
        model     = block.get("model", "").lower().replace("-", "").replace(" ", "")
        model_raw = block.get("model", "").lower().strip()
        iface     = block.get("interface", "").lower()
        btype     = block.get("type", "").lower()

        model_map: Dict[str, Callable] = {
            "bmp280":         self._add_i2c_sensor_block,
            "sht31":          self._add_i2c_sensor_block,
            "mpu6050":        self._add_i2c_sensor_block,
            "oled":           self._add_i2c_sensor_block,
            "dht22":          self._add_dht22_block,
            "dht11":          self._add_dht22_block,
            "moisturesensor": self._add_moisture_sensor_block,
            "fc28":           self._add_moisture_sensor_block,
            "yl69":           self._add_moisture_sensor_block,
            "led":            self._add_led_block,
            "relay":          self._add_relay_block,
            "srd05vdc":       self._add_relay_block,
            "srd5vdc":        self._add_relay_block,
        }
        if model in model_map:
            return model_map[model]

        if btype == "sensor" and iface == "i2c":
            return self._add_i2c_sensor_block
        if btype == "sensor" and iface == "spi":
            return self._add_spi_sensor_block
        if btype in ("uart", "serial", "uart_device"):
            return self._add_uart_device_block
        if btype in ("output", "indicator"):
            return self._add_led_block
        if btype in ("relay", "switch", "actuator"):
            return self._add_relay_block

        # Intentar resolver via BLOCK_TYPE_ALIASES antes de marcar como sin handler
        alias_target = BLOCK_TYPE_ALIASES.get(model_raw)
        if alias_target:
            mapped_model = alias_target.replace("-", "").replace(" ", "")
            if mapped_model in model_map:
                logger.warning(
                    "[CircuitSynthesizer] '%s' resuelto via alias → '%s'",
                    model_raw, alias_target,
                )
                return model_map[mapped_model]
            logger.warning(
                "[CircuitSynthesizer] Alias '%s'→'%s' encontrado pero sin handler. "
                "Sugerencia: implementar _add_%s_block",
                model_raw, alias_target, alias_target.replace(" ", "_"),
            )
            return None

        label = block.get("model", block.get("type", "desconocido"))
        logger.warning(
            "[CircuitSynthesizer] Bloque '%s' sin handler. "
            "Sugerencia: agregar a BLOCK_TYPE_ALIASES o implementar _add_%s_block",
            label, label.lower().replace(" ", "_"),
        )
        return None

    # ── Block handlers ────────────────────────────────────────────────────────

    def _add_led_block(
        self,
        b: CircuitBuilder,
        block: Dict[str, Any],
        ctx: _SynthesisContext,
    ) -> None:
        """
        LED + resistencia limitadora. R = (Vcc - Vf) / If.
        Si corriente > 40 mA o requires_driver=True → inserta transistor NPN driver.
        """
        vf    = float(block.get("vf", 2.0))
        i_ma  = float(block.get("led_current_ma", 20.0))
        color = block.get("color", block.get("led_color", ""))
        gpio  = ctx.pin_allocator.allocate("GPIO_OUTPUT", block.get("gpio_pin"))

        r_ohm = max(100, round((ctx.vcc - vf) / (i_ma / 1000.0) / 10) * 10)
        r_id  = ctx.next_id("R")
        d_id  = ctx.next_id("D")
        idx   = d_id[1:]

        # LED siempre presente en ambos paths
        b.add_component(d_id, f"LED{' ' + color if color else ''} 5mm", "led",
                        value=str(vf), unit="V", current_ma=i_ma,
                        **{"color": color.lower()} if color else {})

        requires_driver = block.get("requires_driver", i_ma > 40.0)

        if requires_driver:
            # Alta corriente: VCC → R_limit → LED.A; LED.K → Q.C (driver NPN)
            # R_limit está en el lado VCC (no en GPIO) → current_ma no aplica al GPIO
            b.add_component(r_id,  f"Resistencia limitadora {r_ohm}Ω", "resistor",
                            value=str(r_ohm), unit="Ω")
            q_id  = ctx.next_id("Q")
            rb_id = ctx.next_id("R")
            b.add_component(q_id,  f"NPN 2N2222 driver LED{idx}", "transistor_npn",
                            value="2N2222")
            b.add_component(rb_id, f"Base R LED{idx} 1kΩ", "resistor",
                            value="1000", unit="Ω", current_ma=2.0)
            b.connect(ctx.vcc_net,          f"{r_id}.1")
            b.connect(f"LED{idx}_ANODE",    f"{r_id}.2",  f"{d_id}.A")
            b.connect(f"LED{idx}_COLL",     f"{d_id}.K",  f"{q_id}.C")
            b.connect(f"LED{idx}_BASE",     f"U1.{gpio}", f"{rb_id}.1")
            b.connect(f"LED{idx}_BASE_IN",  f"{rb_id}.2", f"{q_id}.B")
            b.connect("GND",                f"{q_id}.E")
        else:
            # Corriente estándar: GPIO → R → LED → GND
            # R_limit está en el net GPIO → current_ma para validación eléctrica
            b.add_component(r_id, f"Resistencia limitadora {r_ohm}Ω", "resistor",
                            value=str(r_ohm), unit="Ω", current_ma=i_ma)
            b.connect(f"LED{idx}_CTRL",  f"U1.{gpio}", f"{r_id}.1")
            b.connect(f"LED{idx}_ANODE", f"{r_id}.2",  f"{d_id}.A")
            b.connect("GND", f"{d_id}.K")

    def _add_i2c_sensor_block(
        self,
        b: CircuitBuilder,
        block: Dict[str, Any],
        ctx: _SynthesisContext,
    ) -> None:
        """
        Sensor I2C genérico.
        Pull-ups 4.7kΩ solo se agregan la primera vez (bus I2C compartido).
        Cada sensor tiene su propio capacitor de desacoplo 100nF.
        """
        model    = block.get("model", "Sensor I2C")
        i2c_addr = block.get("i2c_address", block.get("address", "0x76"))

        u_id = ctx.next_id("U")
        c_id = ctx.next_id("C")

        b.add_component(u_id, f"{model} Sensor", "sensor_i2c",
                        i2c_address=i2c_addr, current_ma=1.5)
        b.add_component(c_id, f"Desacoplo {model} 100nF", "capacitor",
                        value="100", unit="nF")

        # Bus I2C compartido: pull-ups y pines solo una vez
        ctx.get_or_create_i2c_bus(b, block)

        b.connect(ctx.vcc_net, f"{u_id}.VCC", f"{c_id}.1")
        b.connect("I2C_SDA",  f"{u_id}.SDA")
        b.connect("I2C_SCL",  f"{u_id}.SCL")
        b.connect("GND", f"{u_id}.GND", f"{c_id}.2")

    def _add_spi_sensor_block(
        self,
        b: CircuitBuilder,
        block: Dict[str, Any],
        ctx: _SynthesisContext,
    ) -> None:
        """
        Sensor SPI genérico.
        MOSI/MISO/SCK compartidos. CS exclusivo por dispositivo.
        """
        model = block.get("model", "Sensor SPI")
        u_id  = ctx.next_id("U")
        c_id  = ctx.next_id("C")

        b.add_component(u_id, f"{model}", "sensor_spi", current_ma=2.0)
        b.add_component(c_id, f"Desacoplo {model} 100nF", "capacitor",
                        value="100", unit="nF")

        cs_net = ctx.get_or_create_spi_bus(b, block)

        b.connect(ctx.vcc_net, f"{u_id}.VCC", f"{c_id}.1")
        b.connect("SPI_MOSI", f"{u_id}.MOSI")
        b.connect("SPI_MISO", f"{u_id}.MISO")
        b.connect("SPI_SCK",  f"{u_id}.SCK")
        b.connect(cs_net,     f"{u_id}.CS")
        b.connect("GND", f"{u_id}.GND", f"{c_id}.2")

    def _add_uart_device_block(
        self,
        b: CircuitBuilder,
        block: Dict[str, Any],
        ctx: _SynthesisContext,
    ) -> None:
        """
        Dispositivo UART genérico. TX/RX dedicados (sin compartir entre dispositivos).
        Nota: MCU.TX → device.RX; MCU.RX → device.TX (cruzado).
        """
        model = block.get("model", "UART Device")
        u_id  = ctx.next_id("U")
        c_id  = ctx.next_id("C")

        b.add_component(u_id, f"{model}", "uart_device", current_ma=5.0)
        b.add_component(c_id, f"Desacoplo {model} 100nF", "capacitor",
                        value="100", unit="nF")

        uid = ctx.get_or_create_uart(b, block)

        b.connect(ctx.vcc_net,       f"{u_id}.VCC", f"{c_id}.1")
        b.connect(f"UART{uid}_TX",   f"{u_id}.RX")   # MCU TX → device RX
        b.connect(f"UART{uid}_RX",   f"{u_id}.TX")   # MCU RX → device TX
        b.connect("GND", f"{u_id}.GND", f"{c_id}.2")

    def _add_dht22_block(
        self,
        b: CircuitBuilder,
        block: Dict[str, Any],
        ctx: _SynthesisContext,
    ) -> None:
        """DHT22/DHT11 temperatura+humedad. GPIO single-bus + pull-up 4.7kΩ."""
        model = block.get("model", "DHT22")
        gpio  = ctx.pin_allocator.allocate("GPIO_OUTPUT", block.get("gpio_pin"))
        u_id  = ctx.next_id("U")
        r_id  = ctx.next_id("R")
        c_id  = ctx.next_id("C")

        b.add_component(u_id, f"{model} Temp/Humidity", "sensor_i2c", current_ma=2.5)
        b.add_component(r_id, f"Pull-up {model} DATA 4.7kΩ", "resistor",
                        value="4700", unit="Ω", current_ma=1.0)
        b.add_component(c_id, f"Desacoplo {model} 100nF", "capacitor",
                        value="100", unit="nF")

        data_net = f"{u_id}_DATA"
        b.connect(ctx.vcc_net, f"{u_id}.VCC", f"{r_id}.1", f"{c_id}.1")
        b.connect(data_net,    f"U1.{gpio}", f"{r_id}.2", f"{u_id}.DATA")
        b.connect("GND",       f"{u_id}.GND", f"{c_id}.2")

    def _add_moisture_sensor_block(
        self,
        b: CircuitBuilder,
        block: Dict[str, Any],
        ctx: _SynthesisContext,
    ) -> None:
        """FC-28/YL-69 sensor de humedad de suelo. Salida analógica → ADC."""
        model   = block.get("model", "FC-28")
        adc_pin = ctx.pin_allocator.allocate("ADC_INPUT", block.get("gpio_pin"))
        u_id    = ctx.next_id("U")
        c_id    = ctx.next_id("C")

        b.add_component(u_id, f"{model} Soil Moisture", "sensor_i2c", current_ma=5.0)
        b.add_component(c_id, f"Desacoplo {model} 100nF", "capacitor",
                        value="100", unit="nF")

        aout_net = f"{u_id}_AOUT"
        b.connect(ctx.vcc_net, f"{u_id}.VCC", f"{c_id}.1")
        b.connect(aout_net,    f"U1.{adc_pin}", f"{u_id}.AOUT")
        b.connect("GND",       f"{u_id}.GND", f"{c_id}.2")

    def _add_relay_block(
        self,
        b: CircuitBuilder,
        block: Dict[str, Any],
        ctx: _SynthesisContext,
    ) -> None:
        """
        Relay con transistor driver NPN + diodo flyback.
        Siempre determinístico: nunca conectar relay directamente a GPIO.
        """
        gpio  = ctx.pin_allocator.allocate("GPIO_OUTPUT", block.get("gpio_pin"))
        rl_id = ctx.next_id("RL")
        idx   = rl_id[2:]
        label = f"RL{idx}"

        b.add_component(rl_id, f"Relay {block.get('model', 'SRD-05VDC')}", "relay",
                        value="5V", current_ma=70.0)

        # Bobina: COIL_A → VCC, COIL_B → colector del transistor
        b.connect(ctx.vcc_net, f"{rl_id}.COIL_A")
        coll_net = self._add_transistor_driver(b, ctx, gpio, label)
        b.connect(coll_net, f"{rl_id}.COIL_B")

        # Diodo flyback a través de la bobina (K→VCC, A→colector)
        self._add_flyback_diode(b, ctx, ctx.vcc_net, coll_net, label)

        # Contactos de salida (carga)
        b.connect(f"{label}_COM", f"{rl_id}.COM")
        b.connect(f"{label}_NO",  f"{rl_id}.NO")

    # ── Subcircuit helpers ────────────────────────────────────────────────────

    def _add_transistor_driver(
        self,
        b: CircuitBuilder,
        ctx: _SynthesisContext,
        gpio: str,
        load_id: str,
    ) -> str:
        """
        Transistor NPN (2N2222) entre GPIO y carga inductiva.
        Retorna el net name del colector para conectar la carga.
        GPIO solo provee ~2 mA de corriente de base.
        """
        q_id  = ctx.next_id("Q")
        rb_id = ctx.next_id("R")
        b.add_component(q_id,  f"NPN 2N2222 {load_id}", "transistor_npn", value="2N2222")
        b.add_component(rb_id, f"Base R {load_id} 1kΩ",  "resistor",
                        value="1000", unit="Ω", current_ma=2.0)
        coll_net = f"{load_id}_COLL"
        b.connect(f"{load_id}_BASE",    f"U1.{gpio}", f"{rb_id}.1")
        b.connect(f"{load_id}_BASE_IN", f"{rb_id}.2", f"{q_id}.B")
        b.connect(coll_net,             f"{q_id}.C")
        b.connect("GND",                f"{q_id}.E")
        return coll_net

    def _add_flyback_diode(
        self,
        b: CircuitBuilder,
        ctx: _SynthesisContext,
        coil_high_net: str,
        coil_low_net: str,
        load_id: str,
    ) -> None:
        """
        1N4007 a través de la bobina de una carga inductiva.
        Cátodo al lado positivo (VCC), ánodo al lado del driver (colector).
        """
        d_id = ctx.next_id("D")
        b.add_component(d_id, f"Flyback 1N4007 {load_id}", "diode", value="1N4007")
        b.connect(coil_high_net, f"{d_id}.K")
        b.connect(coil_low_net,  f"{d_id}.A")

    # ── Validación estructural pre-DRC ────────────────────────────────────────

    def validate_structure(self, circuit: Dict[str, Any]) -> None:
        """
        Verifica invariantes básicos antes de devolver la netlist.
        No reemplaza el DRC eléctrico — es la primera línea de defensa.

        Verifica:
        1. Ningún componente flotante (sin ningún pin en ninguna net)
        2. Todos los ICs tienen al menos un pin en GND y uno en VCC_*
        3. No hay nets vacías (sin nodos)

        Raises ValueError con descripción detallada si alguna verificación falla.
        """
        components = circuit.get("components", [])
        nets = circuit.get("nets", [])
        errors: List[str] = []

        # Índice: node_str → net_name
        node_to_net: Dict[str, str] = {
            node: net["name"]
            for net in nets
            for node in net.get("nodes", [])
        }

        # Índice: component_id → set de net_names a las que está conectado
        comp_nets: Dict[str, set] = {}
        for node, net_name in node_to_net.items():
            cid = node.split(".")[0]
            comp_nets.setdefault(cid, set()).add(net_name)

        comp_ids = {c["id"] for c in components}

        # 1. Componentes flotantes
        floating = comp_ids - set(comp_nets.keys())
        if floating:
            errors.append(f"Componentes flotantes: {', '.join(sorted(floating))}")

        # 2. ICs sin VCC o sin GND
        ic_types = {
            "microcontroller", "sensor_i2c", "sensor_spi", "uart_device",
            "voltage_regulator", "ic",
        }
        for comp in components:
            if comp.get("type") not in ic_types:
                continue
            cid = comp["id"]
            nets_for_comp = comp_nets.get(cid, set())
            if "GND" not in nets_for_comp:
                errors.append(f"{cid} ({comp['type']}) no tiene pin en GND")
            if not any(n.startswith("VCC_") for n in nets_for_comp):
                errors.append(f"{cid} ({comp['type']}) no tiene pin en ninguna net VCC_*")

        # 3. Nets vacías
        empty = [n["name"] for n in nets if not n.get("nodes")]
        if empty:
            errors.append(f"Nets vacías: {', '.join(empty)}")

        if errors:
            raise ValueError(
                "validate_structure falló:\n" +
                "\n".join(f"  • {e}" for e in errors)
            )

    # ── Validación eléctrica ──────────────────────────────────────────────────

    def validate_electrical_constraints(self, circuit: Dict[str, Any]) -> None:
        """
        Verifica límites eléctricos reales del MCU:
        1. Corriente por GPIO no excede gpio_max_ma
        2. Corriente total de todos los GPIOs no excede total_max_ma
        3. VCC es compatible con el MCU

        Corre después de validate_structure. Raises ValueError si falla.

        La corriente por GPIO se estima desde el atributo current_ma de los
        componentes directamente conectados a pines U1.* en nets de señal
        (excluyendo GND y VCC_*).
        """
        mcu_name    = _mcu_key(circuit.get("_mcu", ""))
        constraints = _MCU_ELECTRICAL_CONSTRAINTS.get(mcu_name)
        if constraints is None:
            return  # MCU desconocido → no podemos validar

        vcc    = float(circuit.get("_vcc", 5.0))
        errors: List[str] = []

        # 1. Compatibilidad de voltaje
        if not any(abs(vcc - sv) < 0.15 for sv in constraints.supported_vcc):
            errors.append(
                f"VCC={vcc}V no soportado por '{mcu_name}'. "
                f"Soportados: {constraints.supported_vcc}"
            )

        # 2. Corriente por GPIO
        nets       = circuit.get("nets", [])
        components = circuit.get("components", [])
        comp_by_id = {c["id"]: c for c in components}

        gpio_current: Dict[str, float] = {}

        for net in nets:
            # Net de poder → ignorar
            net_upper = net["name"].upper()
            if net_upper == "GND" or net_upper.startswith("VCC_"):
                continue

            # Buscar pines U1 en esta net
            gpio_pins = [
                node.split(".")[1]
                for node in net.get("nodes", [])
                if node.startswith("U1.")
            ]
            if not gpio_pins:
                continue

            gpio_pin = gpio_pins[0]

            # Sumar current_ma de componentes directamente en esta net (no U1)
            net_draw = sum(
                float(comp_by_id[node.split(".")[0]].get("current_ma", 0.0))
                for node in net.get("nodes", [])
                if not node.startswith("U1.")
                and node.split(".")[0] in comp_by_id
            )

            if net_draw > 0:
                gpio_current[gpio_pin] = gpio_current.get(gpio_pin, 0.0) + net_draw

        # 3. Check per-GPIO
        for pin, current in gpio_current.items():
            if current > constraints.gpio_max_ma:
                errors.append(
                    f"GPIO {pin} sobrecargado: {current:.1f} mA "
                    f"(máx {constraints.gpio_max_ma} mA para {mcu_name})"
                )

        # 4. Check corriente total
        total_ma = sum(gpio_current.values())
        if total_ma > constraints.total_max_ma:
            errors.append(
                f"Corriente total MCU excedida: {total_ma:.1f} mA "
                f"(máx {constraints.total_max_ma} mA para {mcu_name})"
            )

        if errors:
            raise ValueError(
                "validate_electrical_constraints falló:\n" +
                "\n".join(f"  • {e}" for e in errors)
            )

    # ── Backward-compat wrappers ──────────────────────────────────────────────

    def led_with_resistor(
        self,
        mcu: str = "Arduino Uno",
        gpio_pin: str = "D9",
        vcc: float = 5.0,
        vf: float = 2.0,
        led_current_ma: float = 20.0,
        led_color: str = "Rojo",
    ) -> Dict[str, Any]:
        return self.synthesize({
            "mcu": mcu, "vcc": vcc,
            "blocks": [{"type": "output", "model": "LED", "gpio_pin": gpio_pin,
                        "vf": vf, "led_current_ma": led_current_ma, "color": led_color}],
        })

    def bmp280_i2c(
        self,
        mcu: str = "Arduino Uno",
        sda_pin: str = "A4",
        scl_pin: str = "A5",
        vcc: float = 3.3,
        i2c_address: str = "0x76",
    ) -> Dict[str, Any]:
        return self.synthesize({
            "mcu": mcu, "vcc": vcc,
            "blocks": [{"type": "sensor", "model": "BMP280", "interface": "I2C",
                        "sda_pin": sda_pin, "scl_pin": scl_pin,
                        "i2c_address": i2c_address}],
        })
