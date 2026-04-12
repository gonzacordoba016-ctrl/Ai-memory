# tools/electrical_drc.py
#
# Motor de verificación eléctrica (DRC — Design Rule Check) para Stratum.
# Analiza un circuito y retorna errores/advertencias antes de fabricarlo.
# Lógica Python pura — sin LLM, sin I/O.

from __future__ import annotations
from typing import Any

# ── Tipos de componente por categoría ────────────────────────────────────────

_MCU_TYPES = {
    "arduino_uno", "arduino_nano", "arduino_mega", "arduino_mini",
    "arduino_leonardo", "arduino_due", "arduino_zero", "arduino_micro",
    "esp32", "esp8266", "raspberry_pi_pico", "stm32", "teensy",
    "adafruit_feather", "seeeduino_xiao",
}

_LED_TYPES = {
    "led", "led_rgb", "led_red", "led_green", "led_blue",
    "led_yellow", "led_white", "diodo_led",
}

_RESISTOR_TYPES = {"resistor", "resistencia", "res"}

_CAPACITOR_TYPES = {"capacitor", "cap", "capacitor_electrolytic", "capacitor_ceramic"}

_IC_TYPES = _MCU_TYPES | {
    "ic", "shift_register", "mux", "demux", "logic_gate",
    "opamp", "comparator", "555_timer", "ne555", "lm317",
    "voltage_regulator", "buck_converter", "boost_converter",
}

_I2C_MODULES = {
    "oled", "oled_128x64", "oled_display", "bmp280", "mpu6050",
    "ds3231", "rtc", "pcf8574", "i2c_lcd", "ads1115",
}

_ONEWIRE_MODULES = {"ds18b20", "ds18b20_sensor", "temperature_sensor_onewire"}

_HIGH_CURRENT_TYPES = {
    "motor", "relay", "solenoid", "heater", "led_strip",
    "servo", "stepper", "dc_motor", "motor_driver",
}

_FUSE_TYPES = {"fuse", "fusible", "polyfuse", "resettable_fuse"}

# ── Nombres de net de poder ───────────────────────────────────────────────────

_VCC_NAMES = {"vcc", "5v", "3v3", "3.3v", "vin", "vdd", "power", "+5v", "+3.3v", "12v", "+12v"}
_GND_NAMES = {"gnd", "ground", "0v", "gnd1", "gnd2", "agnd", "dgnd", "pgnd"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _comp_type(comp: dict) -> str:
    return (comp.get("resolved_type") or comp.get("type") or "").lower().strip()


def _issue(code: str, severity: str, message: str,
           component: str = "", net: str = "") -> dict:
    return {
        "code":      code,
        "severity":  severity,
        "message":   message,
        "component": component,
        "net":       net,
    }


def _net_name_lower(net: dict) -> str:
    return (net.get("name") or "").lower().strip()


def _is_vcc_net(name: str) -> bool:
    return name.lower() in _VCC_NAMES or any(v in name.lower() for v in ("vcc", "5v", "3v3", "vdd"))


def _is_gnd_net(name: str) -> bool:
    return name.lower() in _GND_NAMES or "gnd" in name.lower()


def _nodes_of(net: dict) -> list[str]:
    return net.get("nodes", net.get("pins", []))


def _comp_refs_in_net(net: dict) -> set[str]:
    """Retorna los IDs de componente conectados en este net."""
    refs = set()
    for node in _nodes_of(net):
        if "." in node:
            refs.add(node.split(".")[0])
        else:
            refs.add(node)
    return refs


# ── Motor principal ───────────────────────────────────────────────────────────

def run_drc(circuit: dict) -> dict:
    """
    Ejecuta todos los checks DRC sobre un circuito.

    Args:
        circuit: dict con keys 'components' (list) y 'nets' (list).
                 Compatible con el formato de circuit_designs de Stratum.

    Returns:
        {
          "errors":   [...],   # severidad "error"
          "warnings": [...],   # severidad "warning"
          "info":     [...],   # severidad "info"
          "passed":   bool,    # True si no hay errores críticos
          "summary":  str,
        }
    """
    components: list[dict] = circuit.get("components") or []
    nets:       list[dict] = circuit.get("nets") or []

    issues: list[dict] = []

    # Índices para acceso rápido
    comp_by_id   = {c.get("id", c.get("ref", "")): c for c in components}
    nets_by_name = {n.get("name", ""): n for n in nets}

    # Qué IDs de comp están en cada net
    net_comps: dict[str, set[str]] = {
        n.get("name", ""): _comp_refs_in_net(n) for n in nets
    }

    # Qué nets tiene cada componente
    comp_nets: dict[str, set[str]] = {}
    for net in nets:
        for ref in _comp_refs_in_net(net):
            comp_nets.setdefault(ref, set()).add(net.get("name", ""))

    # ── Check 1: NO_POWER_NET ─────────────────────────────────────────────────
    has_vcc = any(_is_vcc_net(n.get("name", "")) for n in nets)
    has_gnd = any(_is_gnd_net(n.get("name", "")) for n in nets)
    if not has_vcc:
        issues.append(_issue("NO_POWER_NET", "error",
                             "No se encontró ningún net de alimentación (VCC/5V/3V3/VDD). "
                             "Asegurate de conectar la fuente de poder."))
    if not has_gnd:
        issues.append(_issue("NO_POWER_NET", "error",
                             "No se encontró ningún net de referencia (GND). "
                             "Todos los circuitos deben tener tierra común."))

    # ── Check 2: SHORT_CIRCUIT ────────────────────────────────────────────────
    for net in nets:
        name = net.get("name", "")
        nodes = _nodes_of(net)
        node_names = [n.lower() for n in nodes]
        has_v = any(_is_vcc_net(nn) for nn in node_names)
        has_g = any(_is_gnd_net(nn) for nn in node_names)
        if has_v and has_g:
            issues.append(_issue("SHORT_CIRCUIT", "error",
                                 f"Net '{name}' conecta VCC y GND directamente — cortocircuito.",
                                 net=name))

    # ── Check 3: LED_WITHOUT_RESISTOR ─────────────────────────────────────────
    led_ids = {c.get("id") for c in components if _comp_type(c) in _LED_TYPES}
    resistor_ids = {c.get("id") for c in components if _comp_type(c) in _RESISTOR_TYPES}

    for led_id in led_ids:
        led_nets = comp_nets.get(led_id, set())
        # Buscar si en algún net del LED hay también una resistencia
        led_has_resistor = False
        for net_name in led_nets:
            net_c = net_comps.get(net_name, set())
            if net_c & resistor_ids:
                led_has_resistor = True
                break
        if not led_has_resistor:
            issues.append(_issue("LED_WITHOUT_RESISTOR", "error",
                                 f"{led_id}: LED sin resistencia limitadora de corriente. "
                                 f"Sin resistencia el LED se quema. Agregá una R en serie.",
                                 component=led_id))

    # ── Check 4: ISOLATED_COMPONENT ───────────────────────────────────────────
    for comp in components:
        cid = comp.get("id", comp.get("ref", ""))
        if cid and cid not in comp_nets:
            issues.append(_issue("ISOLATED_COMPONENT", "warning",
                                 f"{cid} ({_comp_type(comp)}): componente sin ninguna conexión.",
                                 component=cid))

    # ── Check 5: DUPLICATE_NET_NODE ───────────────────────────────────────────
    for net in nets:
        nodes = _nodes_of(net)
        seen = set()
        for node in nodes:
            if node in seen:
                issues.append(_issue("DUPLICATE_NET_NODE", "warning",
                                     f"Net '{net.get('name','')}': nodo '{node}' duplicado.",
                                     net=net.get("name", "")))
            seen.add(node)

    # ── Check 6: NO_DECOUPLING_CAP ────────────────────────────────────────────
    ic_ids = {c.get("id") for c in components if _comp_type(c) in _IC_TYPES}
    cap_ids = {c.get("id") for c in components if _comp_type(c) in _CAPACITOR_TYPES}

    for ic_id in ic_ids:
        ic_nets = comp_nets.get(ic_id, set())
        # Buscar capacitor conectado a algún net VCC del mismo IC
        vcc_nets_of_ic = {n for n in ic_nets if _is_vcc_net(n)}
        has_decoupling = False
        for net_name in vcc_nets_of_ic:
            net_c = net_comps.get(net_name, set())
            if net_c & cap_ids:
                has_decoupling = True
                break
        if not has_decoupling and vcc_nets_of_ic:
            ic_name = comp_by_id.get(ic_id, {}).get("name", ic_id)
            issues.append(_issue("NO_DECOUPLING_CAP", "warning",
                                 f"{ic_id} ({ic_name}): IC sin capacitor de desacople en VCC. "
                                 f"Agregá 100nF entre VCC y GND cerca del IC.",
                                 component=ic_id))

    # ── Check 7: NO_I2C_PULLUP ────────────────────────────────────────────────
    i2c_modules = {c.get("id") for c in components if _comp_type(c) in _I2C_MODULES}
    # También detectar por nombre de net SDA/SCL
    has_sda_net = any("sda" in n.get("name", "").lower() for n in nets)
    has_scl_net = any("scl" in n.get("name", "").lower() for n in nets)

    if i2c_modules or (has_sda_net and has_scl_net):
        # Buscar resistencias en nets SDA/SCL
        sda_nets = [n for n in nets if "sda" in n.get("name", "").lower()]
        scl_nets = [n for n in nets if "scl" in n.get("name", "").lower()]
        sda_has_r = any(net_comps.get(n.get("name",""), set()) & resistor_ids for n in sda_nets)
        scl_has_r = any(net_comps.get(n.get("name",""), set()) & resistor_ids for n in scl_nets)
        if not sda_has_r or not scl_has_r:
            issues.append(_issue("NO_I2C_PULLUP", "warning",
                                 "Bus I2C detectado sin resistencias pull-up en SDA/SCL. "
                                 "Agregá 4.7kΩ entre SDA→VCC y SCL→VCC."))

    # ── Check 8: NO_ONEWIRE_PULLUP ────────────────────────────────────────────
    onewire_modules = {c.get("id") for c in components if _comp_type(c) in _ONEWIRE_MODULES}
    if onewire_modules:
        for ow_id in onewire_modules:
            ow_nets = comp_nets.get(ow_id, set())
            data_nets = [n for n in ow_nets
                         if not _is_vcc_net(n) and not _is_gnd_net(n)]
            has_pullup = False
            for net_name in data_nets:
                net_c = net_comps.get(net_name, set())
                if net_c & resistor_ids:
                    has_pullup = True
                    break
            if not has_pullup:
                issues.append(_issue("NO_ONEWIRE_PULLUP", "warning",
                                     f"{ow_id}: sensor one-wire sin resistencia pull-up en DATA. "
                                     f"Agregá 10kΩ entre DATA y VCC.",
                                     component=ow_id))

    # ── Check 9: HIGH_CURRENT_NO_FUSE ────────────────────────────────────────
    high_current = {c.get("id") for c in components if _comp_type(c) in _HIGH_CURRENT_TYPES}
    fuses = {c.get("id") for c in components if _comp_type(c) in _FUSE_TYPES}
    if high_current and not fuses:
        names = [comp_by_id.get(cid, {}).get("name", cid) for cid in list(high_current)[:3]]
        issues.append(_issue("HIGH_CURRENT_NO_FUSE", "warning",
                             f"Carga de alta corriente ({', '.join(names)}) sin fusible. "
                             f"Agregá un fusible de protección en la alimentación."))

    # ── Check 10: VOLTAGE_MISMATCH ────────────────────────────────────────────
    # Detectar componentes 3.3V en nets de 5V
    has_5v_net  = any("5v" in n.get("name","").lower() for n in nets)
    has_33v_net = any("3.3v" in n.get("name","").lower() or
                      "3v3"  in n.get("name","").lower() for n in nets)

    if has_5v_net and has_33v_net:
        # Buscar componentes conectados a ambas nets directamente
        comps_5v  = set()
        comps_33v = set()
        for net in nets:
            nn = net.get("name", "").lower()
            if "5v" in nn:
                comps_5v  |= _comp_refs_in_net(net)
            if "3.3v" in nn or "3v3" in nn:
                comps_33v |= _comp_refs_in_net(net)
        mixed = comps_5v & comps_33v
        # Solo alertar si no son MCUs (que tienen ambas salidas)
        mixed_non_mcu = {c for c in mixed if _comp_type(comp_by_id.get(c, {})) not in _MCU_TYPES}
        for cid in mixed_non_mcu:
            cname = comp_by_id.get(cid, {}).get("name", cid)
            issues.append(_issue("VOLTAGE_MISMATCH", "warning",
                                 f"{cid} ({cname}): componente conectado a nets de 5V y 3.3V. "
                                 f"Verificá compatibilidad de niveles lógicos.",
                                 component=cid))

    # ── Check 11: MISSING_RESET_CAP ───────────────────────────────────────────
    mcu_ids = {c.get("id") for c in components if _comp_type(c) in _MCU_TYPES}
    if mcu_ids:
        reset_nets = [n for n in nets if "reset" in n.get("name","").lower()
                      or "rst" in n.get("name","").lower()]
        if reset_nets:
            for rnet in reset_nets:
                rnet_comps = net_comps.get(rnet.get("name",""), set())
                if not (rnet_comps & cap_ids):
                    issues.append(_issue("MISSING_RESET_CAP", "info",
                                         f"Pin RESET/RST sin capacitor de filtro. "
                                         f"Recomendado: 100nF entre RESET y GND para estabilidad."))
                    break

    # ── Check 12: OVERCURRENT_PIN ────────────────────────────────────────────
    # Si hay más de 3 LEDs en el mismo pin de MCU (simplificación)
    if mcu_ids and led_ids:
        mcu_pin_leds: dict[str, list[str]] = {}
        for net in nets:
            net_c = _comp_refs_in_net(net)
            mcu_in_net = net_c & mcu_ids
            leds_in_net = net_c & led_ids
            if mcu_in_net and leds_in_net:
                pin_id = net.get("name", "")
                mcu_pin_leds[pin_id] = list(leds_in_net)
        for pin, leds in mcu_pin_leds.items():
            if len(leds) > 1:
                issues.append(_issue("OVERCURRENT_PIN", "error",
                                     f"Pin '{pin}': {len(leds)} LEDs en el mismo pin MCU. "
                                     f"Máximo recomendado: 1 LED por pin (40mA). "
                                     f"Usá transistor/MOSFET para manejar múltiples LEDs.",
                                     net=pin))

    # ── Clasificar y construir respuesta ─────────────────────────────────────
    errors   = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    info     = [i for i in issues if i["severity"] == "info"]

    n_err  = len(errors)
    n_warn = len(warnings)
    n_info = len(info)

    if n_err == 0 and n_warn == 0:
        summary = "✅ DRC pasado — sin errores ni advertencias"
    elif n_err == 0:
        summary = f"⚠️ DRC con {n_warn} advertencia{'s' if n_warn>1 else ''} — no hay errores críticos"
    else:
        summary = (f"❌ DRC falló — {n_err} error{'es' if n_err>1 else ''}"
                   + (f", {n_warn} advertencia{'s' if n_warn>1 else ''}" if n_warn else ""))

    return {
        "errors":   errors,
        "warnings": warnings,
        "info":     info,
        "passed":   n_err == 0,
        "summary":  summary,
        "counts":   {"errors": n_err, "warnings": n_warn, "info": n_info},
    }
