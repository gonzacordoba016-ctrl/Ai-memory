"""
Reglas declarativas del Constraint Engine.

Cada regla es una función registrada con `@rule_registry.register(...)`.
Recibe un `ValidationContext` y rinde `ValidationIssue`.

Migrado desde `electrical_drc.py` (18 checks) + `mcu_pinout_validator.py`.
"""
from __future__ import annotations

import re
from typing import Iterator

from tools.eda.constraint_engine import (
    ValidationContext,
    rule_registry,
)
from tools.eda.ir import Severity, ValidationIssue


# ────────────────────────────────────────────────────────────────────────────
# Helpers compartidos
# ────────────────────────────────────────────────────────────────────────────

_LED_TYPES = {"led", "led_rgb", "led_red", "led_green", "led_blue",
              "led_yellow", "led_white", "diodo_led"}
_RESISTOR_TYPES = {"resistor", "resistencia", "res"}
_CAPACITOR_TYPES = {"capacitor", "cap", "capacitor_electrolytic",
                    "capacitor_ceramic", "capacitor_polarized"}
_RELAY_TYPES = {"relay", "relay_module", "ssr", "rele", "relé"}
_DIODE_TYPES = {"diode", "1n4007", "1n4148", "1n5819", "schottky_diode",
                "flyback_diode"}
_FUSE_TYPES = {"fuse", "fusible", "polyfuse", "resettable_fuse"}
_HIGH_CURRENT_TYPES = {"motor", "relay", "solenoid", "heater", "led_strip",
                       "servo", "stepper", "dc_motor", "motor_driver"}
_AC_KEYWORDS = ("220", "110", "230", "240", "ac", "mains", "red ", "vac")
_5V_SENSORS = {"hc_sr04"}
_RAW_MOTOR_TYPES = {"motor", "dc_motor", "stepper"}
_MOTOR_DRIVER_TYPES = {"l298n", "drv8825", "a4988", "motor_driver", "tb6600"}
_WIFI_MCUS = {"esp32", "esp8266"}
_3V3_MCUS = {"esp32", "esp8266", "raspberry_pi_pico", "stm32"}


def _parse_cap_uf(value: str | None) -> float:
    """Parsea valores como '100uF', '0.1uF', '470µF', '100nF'. Devuelve µF."""
    if not value:
        return 0.0
    v = value.lower().replace("µ", "u").strip()
    m = re.match(r"^([\d.]+)\s*(uf|u|nf|n|pf|p)?$", v)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = m.group(2) or "uf"
    if unit in ("nf", "n"):
        return num / 1000.0
    if unit in ("pf", "p"):
        return num / 1_000_000.0
    return num


def _issue(code: str, severity: Severity, message: str, **kw) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, message=message, **kw)


# ────────────────────────────────────────────────────────────────────────────
# 1. NO_POWER_NET
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("NO_POWER_NET", description="Cada circuito debe tener VCC y GND")
def check_no_power_net(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    has_vcc = any(ctx.is_vcc_net(n.name) for n in ctx.circuit.nets)
    has_gnd = any(ctx.is_gnd_net(n.name) for n in ctx.circuit.nets)
    if not has_vcc:
        yield _issue("NO_POWER_NET", Severity.ERROR,
                     "No hay net de alimentación (VCC/5V/3V3/VIN). "
                     "Todo circuito necesita una net de alimentación.")
    if not has_gnd:
        yield _issue("NO_POWER_NET", Severity.ERROR,
                     "No hay net de tierra (GND). "
                     "Todo circuito necesita una referencia a GND.")


# ────────────────────────────────────────────────────────────────────────────
# 2. SHORT_CIRCUIT — VCC y GND no pueden compartir nodos
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("SHORT_CIRCUIT", description="VCC y GND comparten nodos directamente")
def check_short_circuit(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    vcc_nodes: set[tuple[str, str]] = set()
    gnd_nodes: set[tuple[str, str]] = set()
    for net in ctx.circuit.nets:
        if ctx.is_vcc_net(net.name):
            vcc_nodes |= {(n.ref, n.pin) for n in net.nodes}
        if ctx.is_gnd_net(net.name):
            gnd_nodes |= {(n.ref, n.pin) for n in net.nodes}
    intersect = vcc_nodes & gnd_nodes
    for ref, pin in intersect:
        yield _issue("SHORT_CIRCUIT", Severity.ERROR,
                     f"Cortocircuito: {ref}.{pin} aparece en VCC y GND simultáneamente.",
                     component=ref, pin=pin)


# ────────────────────────────────────────────────────────────────────────────
# 3. LED_WITHOUT_RESISTOR
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("LED_WITHOUT_RESISTOR")
def check_led_resistor(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    led_refs = ctx.refs_of_types(*_LED_TYPES)
    res_refs = ctx.refs_of_types(*_RESISTOR_TYPES)
    if not led_refs:
        return
    for led_ref in led_refs:
        led_nets = ctx.nets_of_ref.get(led_ref, set())
        # Si no hay ninguna resistencia en alguna de sus nets → falta limitador.
        has_r = any(
            ctx.refs_in_net.get(n, set()) & res_refs
            for n in led_nets
        )
        if not has_r:
            yield _issue("LED_WITHOUT_RESISTOR", Severity.ERROR,
                         f"{led_ref}: LED sin resistencia limitadora. "
                         f"R = (Vsupply - Vf) / If — típicamente 220-470Ω para 20mA.",
                         component=led_ref)


# ────────────────────────────────────────────────────────────────────────────
# 4. ISOLATED_COMPONENT
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("ISOLATED_COMPONENT")
def check_isolated(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for ref in ctx.comp_by_ref:
        if not ctx.nets_of_ref.get(ref):
            yield _issue("ISOLATED_COMPONENT", Severity.WARNING,
                         f"{ref}: componente sin conexiones a ninguna net.",
                         component=ref)


# ────────────────────────────────────────────────────────────────────────────
# 5. DUPLICATE_NET_NODE — pin del mismo componente en >1 net
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("DUPLICATE_NET_NODE")
def check_duplicate_node(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    seen: dict[tuple[str, str], str] = {}
    for net in ctx.circuit.nets:
        for node in net.nodes:
            key = (node.ref, node.pin)
            if key in seen:
                yield _issue("DUPLICATE_NET_NODE", Severity.ERROR,
                             f"{node.ref}.{node.pin} aparece en nets "
                             f"'{seen[key]}' y '{net.name}'.",
                             component=node.ref, pin=node.pin)
            else:
                seen[key] = net.name


# ────────────────────────────────────────────────────────────────────────────
# 6. NO_DECOUPLING_CAP — ICs sin cap de bypass cerca de VCC
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("NO_DECOUPLING_CAP")
def check_decoupling(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    ic_refs = ctx.refs_of_category("ic", "mcu", "power")
    cap_refs = ctx.refs_of_types(*_CAPACITOR_TYPES)
    if not ic_refs or not cap_refs:
        return
    # Si hay ICs y NO hay ningún cap en VCC, alertar genéricamente (info).
    vcc_nets = [n for n in ctx.circuit.nets if ctx.is_vcc_net(n.name)]
    has_cap_on_vcc = any(
        ctx.refs_in_net.get(n.name, set()) & cap_refs
        for n in vcc_nets
    )
    if not has_cap_on_vcc:
        yield _issue("NO_DECOUPLING_CAP", Severity.INFO,
                     "ICs/MCUs presentes sin capacitor de desacople en VCC. "
                     "Recomendado: 100nF entre VCC y GND cerca de cada IC.")


# ────────────────────────────────────────────────────────────────────────────
# 7. NO_I2C_PULLUP
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("NO_I2C_PULLUP")
def check_i2c_pullup(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    sda_nets = ctx.nets_named("sda")
    scl_nets = ctx.nets_named("scl")
    if not (sda_nets and scl_nets):
        return
    res_refs = ctx.refs_of_types(*_RESISTOR_TYPES)
    sda_has_r = any(ctx.refs_in_net.get(n.name, set()) & res_refs for n in sda_nets)
    scl_has_r = any(ctx.refs_in_net.get(n.name, set()) & res_refs for n in scl_nets)
    if not (sda_has_r and scl_has_r):
        yield _issue("NO_I2C_PULLUP", Severity.WARNING,
                     "Bus I2C sin resistencias pull-up en SDA/SCL. "
                     "Agregá 4.7kΩ entre SDA→VCC y SCL→VCC.")


# ────────────────────────────────────────────────────────────────────────────
# 8. NO_ONEWIRE_PULLUP
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("NO_ONEWIRE_PULLUP")
def check_onewire_pullup(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    onewire_refs = ctx.refs_of_types("ds18b20")
    if not onewire_refs:
        return
    res_refs = ctx.refs_of_types(*_RESISTOR_TYPES)
    for ref in onewire_refs:
        for net_name in ctx.nets_of_ref.get(ref, set()):
            if ctx.is_vcc_net(net_name) or ctx.is_gnd_net(net_name):
                continue
            if not (ctx.refs_in_net.get(net_name, set()) & res_refs):
                yield _issue("NO_ONEWIRE_PULLUP", Severity.WARNING,
                             f"{ref}: bus One-Wire sin pull-up 4.7kΩ. "
                             f"Sin pull-up el bus DQ no sube → sensor no responde.",
                             component=ref)
                break


# ────────────────────────────────────────────────────────────────────────────
# 9. HIGH_CURRENT_NO_FUSE
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("HIGH_CURRENT_NO_FUSE")
def check_high_current_fuse(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    high = ctx.refs_of_types(*_HIGH_CURRENT_TYPES)
    fuses = ctx.refs_of_types(*_FUSE_TYPES)
    if high and not fuses:
        names = list(high)[:3]
        yield _issue("HIGH_CURRENT_NO_FUSE", Severity.WARNING,
                     f"Carga de alta corriente ({', '.join(names)}) sin fusible. "
                     f"Agregá un fusible de protección en la alimentación.")


# ────────────────────────────────────────────────────────────────────────────
# 10. VOLTAGE_MISMATCH — mismo componente en 5V y 3.3V
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("VOLTAGE_MISMATCH")
def check_voltage_mismatch(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    has_5v = ctx.has_net_named("5v")
    has_3v3 = ctx.has_net_named("3.3v", "3v3")
    if not (has_5v and has_3v3):
        return
    refs_5v: set[str] = set()
    refs_3v3: set[str] = set()
    for net in ctx.circuit.nets:
        if "5v" in net.name.lower():
            refs_5v |= ctx.refs_in_net.get(net.name, set())
        if "3.3v" in net.name.lower() or "3v3" in net.name.lower():
            refs_3v3 |= ctx.refs_in_net.get(net.name, set())
    mixed = refs_5v & refs_3v3
    mcus = ctx.refs_of_category("mcu")
    for ref in mixed - mcus:
        yield _issue("VOLTAGE_MISMATCH", Severity.WARNING,
                     f"{ref}: componente conectado a nets de 5V y 3.3V. "
                     f"Verificá compatibilidad de niveles lógicos.",
                     component=ref)


# ────────────────────────────────────────────────────────────────────────────
# 11. MISSING_RESET_CAP
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("MISSING_RESET_CAP")
def check_reset_cap(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    mcus = ctx.refs_of_category("mcu")
    if not mcus:
        return
    cap_refs = ctx.refs_of_types(*_CAPACITOR_TYPES)
    reset_nets = ctx.nets_named("reset", "rst")
    if not reset_nets:
        return
    for rnet in reset_nets:
        if not (ctx.refs_in_net.get(rnet.name, set()) & cap_refs):
            yield _issue("MISSING_RESET_CAP", Severity.INFO,
                         "Pin RESET sin capacitor de filtro. "
                         "Recomendado 100nF entre RESET y GND.")
            return


# ────────────────────────────────────────────────────────────────────────────
# 12. OVERCURRENT_PIN — múltiples LEDs en mismo pin MCU
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("OVERCURRENT_PIN")
def check_overcurrent_pin(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    mcus = ctx.refs_of_category("mcu")
    leds = ctx.refs_of_types(*_LED_TYPES)
    if not (mcus and leds):
        return
    for net in ctx.circuit.nets:
        in_net = ctx.refs_in_net.get(net.name, set())
        if not (in_net & mcus and in_net & leds):
            continue
        leds_here = list(in_net & leds)
        if len(leds_here) > 1:
            yield _issue("OVERCURRENT_PIN", Severity.ERROR,
                         f"Pin '{net.name}': {len(leds_here)} LEDs en el mismo pin. "
                         f"Máximo 1 LED por pin (40mA). Usá MOSFET para múltiples.",
                         net=net.name)


# ────────────────────────────────────────────────────────────────────────────
# 13. SIGNAL_5V_ON_3V3_GPIO — sensor 5V (HC-SR04) en MCU 3.3V sin level shifter
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("SIGNAL_5V_ON_3V3_GPIO")
def check_5v_on_3v3(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    mcus_3v3 = {ref for ref in ctx.refs_of_category("mcu")
                if ctx.comp_by_ref[ref].type.lower() in _3V3_MCUS}
    sensors_5v = ctx.refs_of_types(*_5V_SENSORS)
    if not (mcus_3v3 and sensors_5v):
        return
    # Si comparten alguna net no-power, alertar.
    for sref in sensors_5v:
        snets = ctx.nets_of_ref.get(sref, set())
        for nname in snets:
            if ctx.is_vcc_net(nname) or ctx.is_gnd_net(nname):
                continue
            if ctx.refs_in_net.get(nname, set()) & mcus_3v3:
                yield _issue("SIGNAL_5V_ON_3V3_GPIO", Severity.ERROR,
                             f"{sref}: sensor 5V conectado directamente a GPIO 3.3V "
                             f"en net '{nname}'. Usá divisor 1k+2k a GND.",
                             component=sref, net=nname)
                break


# ────────────────────────────────────────────────────────────────────────────
# 14. MOTOR_DIRECT_TO_MCU — motor crudo conectado al MCU sin driver
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("MOTOR_DIRECT_TO_MCU")
def check_motor_direct(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    raw_motors = ctx.refs_of_types(*_RAW_MOTOR_TYPES)
    drivers = ctx.refs_of_types(*_MOTOR_DRIVER_TYPES)
    mcus = ctx.refs_of_category("mcu")
    if not (raw_motors and mcus):
        return
    if drivers:
        return  # hay un driver — asumimos que está bien conectado
    for mref in raw_motors:
        mnets = ctx.nets_of_ref.get(mref, set())
        for nname in mnets:
            if ctx.is_vcc_net(nname) or ctx.is_gnd_net(nname):
                continue
            if ctx.refs_in_net.get(nname, set()) & mcus:
                yield _issue("MOTOR_DIRECT_TO_MCU", Severity.ERROR,
                             f"{mref}: motor conectado directamente al MCU. "
                             f"Agregá un driver (L298N/DRV8825/MOSFET).",
                             component=mref, net=nname)
                return


# ────────────────────────────────────────────────────────────────────────────
# 15. ESP_WIFI_NO_BULK_CAP
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("ESP_WIFI_NO_BULK_CAP")
def check_esp_bulk(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    wifi_mcus = {ref for ref in ctx.refs_of_category("mcu")
                 if ctx.comp_by_ref[ref].type.lower() in _WIFI_MCUS}
    if not wifi_mcus:
        return
    cap_refs = ctx.refs_of_types(*_CAPACITOR_TYPES)
    # Bulk cap = electrolytic O cap con value >= 10uF
    bulk_caps = set()
    for ref in cap_refs:
        c = ctx.comp_by_ref[ref]
        if c.type.lower() in {"capacitor_electrolytic", "cap_electrolytic"}:
            bulk_caps.add(ref)
        elif _parse_cap_uf(c.value) >= 10:
            bulk_caps.add(ref)
    vcc_nets = [n for n in ctx.circuit.nets if ctx.is_vcc_net(n.name)]
    has_bulk = any(
        ctx.refs_in_net.get(n.name, set()) & bulk_caps
        for n in vcc_nets
    )
    if not has_bulk:
        names = list(wifi_mcus)[:2]
        yield _issue("ESP_WIFI_NO_BULK_CAP", Severity.WARNING,
                     f"{', '.join(names)}: ESP/WiFi sin capacitor bulk en VCC. "
                     f"Picos de 350mA causan brownout. Agregá 100µF + 100nF.",
                     component=names[0])


# ────────────────────────────────────────────────────────────────────────────
# 16. MCU_MISSING_VCC / MCU_MISSING_GND
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("MCU_MISSING_POWER")
def check_mcu_power(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for ref in ctx.refs_of_category("mcu"):
        nets = ctx.nets_of_ref.get(ref, set())
        if not any(ctx.is_vcc_net(n) for n in nets):
            yield _issue("MCU_MISSING_VCC", Severity.ERROR,
                         f"{ref}: MCU sin conexión a VCC. "
                         f"Conectá un pin VCC/3V3/5V/VIN.",
                         component=ref)
        if not any(ctx.is_gnd_net(n) for n in nets):
            yield _issue("MCU_MISSING_GND", Severity.ERROR,
                         f"{ref}: MCU sin conexión a GND.",
                         component=ref)


# ────────────────────────────────────────────────────────────────────────────
# 17. RELAY_FLYBACK_POLARITY
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("RELAY_FLYBACK")
def check_relay_flyback(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    relays = ctx.refs_of_types(*_RELAY_TYPES)
    diodes = ctx.refs_of_types(*_DIODE_TYPES)
    if not relays:
        return
    # Relays "module" traen flyback integrado — usar registry para skipear.
    pure_relays = {ref for ref in relays
                   if ctx.comp_by_ref[ref].type.lower() == "relay"}
    if not pure_relays:
        return
    if not diodes:
        for r in pure_relays:
            yield _issue("RELAY_NO_FLYBACK", Severity.ERROR,
                         f"{r}: relé sin diodo flyback. "
                         f"El back-EMF del coil quema el MCU al apagar el relé. "
                         f"Agregá 1N4007: cátodo al control, ánodo a GND.",
                         component=r)
        return
    # Verificar polaridad: cátodo del diodo en net del control, ánodo en GND.
    relay_nets: set[str] = set()
    for r in pure_relays:
        relay_nets |= ctx.nets_of_ref.get(r, set())
    for d in diodes:
        cathode_in_ctrl = anode_in_gnd = False
        cathode_in_gnd = anode_in_ctrl = False
        for net in ctx.circuit.nets:
            for node in net.nodes:
                if node.ref != d:
                    continue
                pin = node.pin.lower()
                in_ctrl = (net.name in relay_nets and not ctx.is_gnd_net(net.name))
                in_gnd = ctx.is_gnd_net(net.name)
                if pin in ("cathode", "k", "2"):
                    cathode_in_ctrl = cathode_in_ctrl or in_ctrl
                    cathode_in_gnd = cathode_in_gnd or in_gnd
                if pin in ("anode", "a", "1"):
                    anode_in_ctrl = anode_in_ctrl or in_ctrl
                    anode_in_gnd = anode_in_gnd or in_gnd
        if cathode_in_gnd and anode_in_ctrl:
            yield _issue("RELAY_FLYBACK_BAD_POLARITY", Severity.ERROR,
                         f"{d}: diodo flyback con polaridad invertida "
                         f"(ánodo al control, cátodo a GND). "
                         f"Correcto: cátodo al control, ánodo a GND.",
                         component=d)


# ────────────────────────────────────────────────────────────────────────────
# 18. AC_CONNECTOR_NO_FUSE
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("AC_CONNECTOR_NO_FUSE")
def check_ac_fuse(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    ac_conns = set()
    for ref, c in ctx.comp_by_ref.items():
        if ctx.category_of(ref) != "connector":
            continue
        cname = (c.value or c.ref or "").lower()
        # Buscar también en metadata.title del circuito por keywords AC.
        text = cname + " " + " ".join(str(v).lower() for v in c.properties.values())
        if any(kw in text for kw in _AC_KEYWORDS):
            ac_conns.add(ref)
    if not ac_conns:
        return
    fuses = ctx.refs_of_types(*_FUSE_TYPES)
    if not fuses:
        names = list(ac_conns)[:2]
        yield _issue("AC_CONNECTOR_NO_FUSE", Severity.ERROR,
                     f"Conector AC ({', '.join(names)}) sin fusible aguas arriba. "
                     f"Riesgo de incendio. Agregá fusible 5×20mm en serie con L.",
                     component=names[0])
        return
    # Hay fusible, pero ¿comparte net con el conector AC?
    inline = False
    for ac in ac_conns:
        for nname in ctx.nets_of_ref.get(ac, set()):
            if ctx.refs_in_net.get(nname, set()) & fuses:
                inline = True
                break
        if inline:
            break
    if not inline:
        yield _issue("AC_CONNECTOR_FUSE_NOT_INLINE", Severity.WARNING,
                     "Conector AC presente y hay fusible, pero el fusible no "
                     "comparte net con el conector. Verificá que esté en serie con L.")


# ────────────────────────────────────────────────────────────────────────────
# 19. PIN_INVALID — pin del MCU no existe en el registry
# ────────────────────────────────────────────────────────────────────────────


@rule_registry.register("PIN_INVALID")
def check_pin_invalid(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """Validador de pinout — reemplaza tools/mcu_pinout_validator.py."""
    for ref in ctx.refs_of_category("mcu"):
        spec = ctx.spec_by_ref.get(ref)
        if not spec or not spec.mcu:
            continue
        for nname in ctx.nets_of_ref.get(ref, set()):
            net = ctx.circuit.net(nname)
            if not net:
                continue
            for node in net.nodes:
                if node.ref != ref:
                    continue
                if not _pin_acceptable(spec, node.pin):
                    yield _issue("PIN_INVALID", Severity.ERROR,
                                 f"{ref}.{node.pin}: pin no existe en "
                                 f"{spec.display_name or spec.type}.",
                                 component=ref, pin=node.pin, net=nname)


@rule_registry.register("PIN_FORBIDDEN")
def check_pin_forbidden(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """Pin existe pero está marcado como forbidden (ej: ESP32 GPIO6-11)."""
    for ref in ctx.refs_of_category("mcu"):
        spec = ctx.spec_by_ref.get(ref)
        if not spec or not spec.mcu:
            continue
        for nname in ctx.nets_of_ref.get(ref, set()):
            net = ctx.circuit.net(nname)
            if not net:
                continue
            for node in net.nodes:
                if node.ref != ref:
                    continue
                if spec.is_pin_forbidden(node.pin):
                    yield _issue("PIN_FORBIDDEN", Severity.ERROR,
                                 f"{ref}.{node.pin}: pin reservado en "
                                 f"{spec.display_name or spec.type} "
                                 f"(ej. flash interno). No usar.",
                                 component=ref, pin=node.pin, net=nname)


@rule_registry.register("PIN_INPUT_ONLY_MISUSE")
def check_pin_input_only(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """Pin marcado como input-only usado para output (heurística por nombre de net)."""
    for ref in ctx.refs_of_category("mcu"):
        spec = ctx.spec_by_ref.get(ref)
        if not spec or not spec.mcu:
            continue
        for nname in ctx.nets_of_ref.get(ref, set()):
            net = ctx.circuit.net(nname)
            if not net:
                continue
            # Output hint: net name like CTRL/EN/PWM/OUT/LED/RELAY → output-bound
            output_like = any(kw in nname.upper()
                              for kw in ("CTRL", "_EN", "PWM", "OUT", "LED", "RELAY"))
            if not output_like:
                continue
            for node in net.nodes:
                if node.ref != ref:
                    continue
                if spec.is_pin_input_only(node.pin):
                    yield _issue("PIN_INPUT_ONLY_MISUSE", Severity.ERROR,
                                 f"{ref}.{node.pin}: pin input-only usado para output "
                                 f"(net '{nname}').",
                                 component=ref, pin=node.pin, net=nname)


def _pin_acceptable(spec, pin: str) -> bool:
    """¿El pin existe en el spec, ya sea por número o nombre?"""
    if spec.pin(pin):
        return True
    # Aceptar power/reset shortcuts (VCC/GND/5V/3V3/VIN/RESET) sin estar listados.
    if pin.upper() in {"VCC", "GND", "5V", "3V3", "3.3V", "VIN", "VDD",
                       "AREF", "RESET", "RST", "EN"}:
        return True
    # Para Mega: aceptar D0-D53, A0-A15 por rango.
    if spec.type == "arduino_mega":
        if re.fullmatch(r"D([0-9]|[1-4][0-9]|5[0-3])", pin):
            return True
        if re.fullmatch(r"A([0-9]|1[0-5])", pin):
            return True
    # Para STM32: aceptar PA0-PA15 / PB0-PB15 / PC13-15.
    if spec.type == "stm32":
        if re.fullmatch(r"P[A-D]([0-9]|1[0-5])", pin):
            return True
    return False
