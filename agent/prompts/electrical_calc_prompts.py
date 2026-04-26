# agent/prompts/electrical_calc_prompts.py
# Todos los prompts LLM del ElectricalCalcAgent como constantes nombradas.

# ── Clasificación de intención ────────────────────────────────────────────────

CLASSIFY_PROMPT = """Clasificá esta consulta de ingeniería en UNA sola palabra.

Categorías disponibles:
- resistor_for_led:         resistencia limitadora para LED
- resistor_voltage_divider: divisor de tensión resistivo
- resistor_power:           potencia disipada en resistencia
- capacitor_filter:         capacitor para filtro RC
- rc_time_constant:         constante de tiempo RC
- capacitor_energy:         energía almacenada en capacitor
- power_dissipation:        potencia disipada (V×I)
- heat_sink_required:       disipador térmico necesario
- efficiency:               eficiencia energética
- fuse_rating:              fusible recomendado
- buck_converter:           convertidor BUCK (reductor)
- boost_converter:          convertidor BOOST (elevador)
- transformer_turns_ratio:  relación de transformación
- low_pass_rc:              filtro paso bajo RC
- high_pass_rc:             filtro paso alto RC
- lc_filter:                filtro LC segundo orden
- inverting_amp:            amplificador inversor op-amp
- non_inverting_amp:        amplificador no inversor op-amp
- voltage_follower:         seguidor de tensión (buffer)
- battery_autonomy:         autonomía de batería
- charge_time:              tiempo de carga de batería
- motor_power:              potencia mecánica de motor
- vfd_frequency_for_rpm:    frecuencia VFD para velocidad de motor
- motor_torque:             torque de motor
- ohms_law:                 ley de Ohm (V, I, R)
- unknown:                  no es un cálculo eléctrico específico

Consulta: "{task}"

Respondé SOLO con una de las palabras clave listadas."""


# ── Extracción de parámetros por tipo ────────────────────────────────────────

EXTRACT_PARAMS_PROMPTS: dict[str, str] = {
    "resistor_for_led": """Extraé los parámetros para calcular resistencia de LED.
JSON con claves: vcc (float, voltios fuente), vled (float, caída en LED), iled_ma (float, corriente en mA).
Valores típicos si no se mencionan: vled=2.0 para rojo/amarillo/verde (Vf=2.0V), vled=3.2 para azul/blanco/violeta (Vf=3.2V), iled_ma=20.
Si vcc == vled o vcc < vled, usar vled=2.0 como fallback seguro y agregar advertencia.
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "resistor_voltage_divider": """Extraé parámetros para divisor de tensión.
JSON con claves: vin (float, null si no se menciona), vout (float, null si no se menciona), r1 (float, ohmios — 10000 si no se da).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "resistor_power": """Extraé parámetros para potencia en resistencia.
JSON con claves: r (float, ohmios, null si no se menciona), i_ma (float, corriente mA, null si no se menciona), v (float, tensión V, null si no se menciona).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "capacitor_filter": """Extraé parámetros para filtro RC.
JSON con claves: freq_hz (float, frecuencia de corte en Hz, null si no se menciona), resistance (float, ohmios, null si no se menciona).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "rc_time_constant": """Extraé parámetros para constante de tiempo RC.
JSON con claves: r (float, ohmios, null si no se menciona), c_uf (float, capacitor en µF/uF, null si no se menciona).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "capacitor_energy": """Extraé parámetros para energía en capacitor.
JSON con claves: c_uf (float, µF, null si no se menciona), v (float, voltios, null si no se menciona).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "power_dissipation": """Extraé parámetros para potencia disipada.
JSON con claves: v (float, voltios, null si no se menciona), i_ma (float, corriente en mA, null si no se menciona).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "heat_sink_required": """Extraé parámetros para disipador térmico.
JSON con claves: p_w (float, potencia en W), t_ambient (float, temperatura ambiente °C, default 25),
theta_jc (float, resistencia térmica junction-case del componente °C/W, default 5),
t_junction_max (float, temperatura máxima de juntura °C, default 125).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "efficiency": """Extraé parámetros para eficiencia energética.
JSON con claves: p_out (float, potencia de salida W), p_in (float, potencia de entrada W).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "fuse_rating": """Extraé parámetros para fusible.
JSON con claves: i_max (float, corriente máxima en A), safety_factor (float, default 1.25).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "buck_converter": """Extraé parámetros para convertidor BUCK.
JSON con claves: vin (float, tensión entrada V, null si no se menciona), vout (float, tensión salida V, null si no se menciona),
iout (float, corriente salida A, null si no se menciona), freq_khz (float, frecuencia kHz, default 100).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "boost_converter": """Extraé parámetros para convertidor BOOST.
JSON con claves: vin (float, tensión entrada V, null si no se menciona), vout (float, tensión salida V, null si no se menciona),
iout (float, corriente salida A, null si no se menciona), freq_khz (float, frecuencia kHz, default 100).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "transformer_turns_ratio": """Extraé parámetros para transformador.
JSON con claves:
- vp (float, tensión primario V, null si no se menciona)
- vs: tensión(es) secundaria(s) en V. Si hay UNA sola → float (ej. 12). Si hay VARIAS (multi-tap, ej. "220V a 12V y 24V") → array de floats (ej. [12, 24]). null si no se menciona.
- ip (float, corriente primario A, null si no se menciona)
- is_ (float, corriente secundario A, null si no se menciona)
Ejemplos:
  "transformador 220V a 12V"           → {"vp":220,"vs":12,"ip":null,"is_":null}
  "transformador 220V a 12V y 24V"     → {"vp":220,"vs":[12,24],"ip":null,"is_":null}
  "fuente de 220V con tomas a 12 y 24" → {"vp":220,"vs":[12,24],"ip":null,"is_":null}
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "low_pass_rc": """Extraé parámetros para filtro paso bajo RC.
JSON con claves: cutoff_hz (float, frecuencia de corte Hz), r (float, resistencia ohmios).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "high_pass_rc": """Extraé parámetros para filtro paso alto RC.
JSON con claves: cutoff_hz (float, frecuencia de corte Hz), c_uf (float, capacitor µF).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "lc_filter": """Extraé parámetros para filtro LC.
JSON con claves: cutoff_hz (float, frecuencia de corte Hz), impedance (float, impedancia ohmios, default 50).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "inverting_amp": """Extraé parámetros para amplificador inversor.
JSON con claves: r_in (float, resistencia entrada ohmios), r_feedback (float, resistencia realimentación ohmios).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "non_inverting_amp": """Extraé parámetros para amplificador no inversor.
JSON con claves: r1 (float, resistencia a GND ohmios), r2 (float, resistencia realimentación ohmios).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "battery_autonomy": """Extraé parámetros para autonomía de batería.
JSON con claves: capacity_mah (float, capacidad mAh), current_ma (float, consumo mA),
efficiency (float, eficiencia 0-1, default 0.85).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "charge_time": """Extraé parámetros para tiempo de carga.
JSON con claves: capacity_mah (float, mAh), charge_current_ma (float, corriente de carga mA),
efficiency (float, default 0.9).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "motor_power": """Extraé parámetros para potencia de motor.
JSON con claves: voltage (float, V, null si no se menciona), current (float, A, null si no se menciona), efficiency (float, 0-1, default 0.85).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "vfd_frequency_for_rpm": """Extraé parámetros para frecuencia VFD.
JSON con claves: rpm (float, null si no se menciona), poles (int, número de polos del motor, default 4).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "motor_torque": """Extraé parámetros para torque de motor.
JSON con claves: power_w (float, potencia W, null si no se menciona), rpm (float, null si no se menciona).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "ohms_law": """Extraé parámetros para ley de Ohm. Al menos 2 de 3.
JSON con claves: v (float, voltios, null si no se da), i_ma (float, mA, null si no se da),
r (float, ohmios, null si no se da).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",
}


# ── Parámetros requeridos por tipo (null → pedir al usuario) ─────────────────
# Claves que deben tener valor numérico para que el cálculo tenga sentido.
# Los opcionales/defaults no van aquí.

REQUIRED_PARAMS: dict[str, list[str]] = {
    "resistor_for_led":         ["vcc"],
    "resistor_voltage_divider": ["vin", "vout"],
    "resistor_power":           ["r"],
    "capacitor_filter":         ["freq_hz", "resistance"],
    "rc_time_constant":         ["r", "c_uf"],
    "capacitor_energy":         ["c_uf", "v"],
    "power_dissipation":        ["v", "i_ma"],
    "buck_converter":           ["vin", "vout", "iout"],
    "boost_converter":          ["vin", "vout", "iout"],
    "transformer_turns_ratio":  ["vp", "vs"],
    "low_pass_rc":              ["cutoff_hz", "r"],
    "high_pass_rc":             ["cutoff_hz", "c_uf"],
    "lc_filter":                ["cutoff_hz"],
    "inverting_amp":            ["r_in", "r_feedback"],
    "non_inverting_amp":        ["r1", "r2"],
    "battery_autonomy":         ["capacity_mah", "current_ma"],
    "charge_time":              ["capacity_mah", "charge_current_ma"],
    "motor_power":              ["voltage", "current"],
    "vfd_frequency_for_rpm":    ["rpm"],
    "motor_torque":             ["power_w", "rpm"],
    "ohms_law":                 [],  # valida mínimo 2 de 3 en el agente
    "fuse_rating":              ["i_max"],
    "heat_sink_required":       ["p_w"],
}

PARAM_LABELS: dict[str, str] = {
    "vin": "Vin (tensión de entrada, V)",
    "vout": "Vout (tensión de salida deseada, V)",
    "r1": "R1 (resistencia superior, Ω)",
    "vcc": "Vcc (tensión de alimentación, V)",
    "r": "R (resistencia, Ω)",
    "c_uf": "C (capacitancia, µF)",
    "freq_hz": "frecuencia de corte (Hz)",
    "resistance": "R (resistencia, Ω)",
    "v": "V (tensión, V)",
    "i_ma": "I (corriente, mA)",
    "iout": "Iout (corriente de salida, A)",
    "vp": "Vp (tensión primario, V)",
    "vs": "Vs (tensión secundario, V)",
    "cutoff_hz": "frecuencia de corte (Hz)",
    "r_in": "Rin (resistencia de entrada, Ω)",
    "r_feedback": "Rf (resistencia de realimentación, Ω)",
    "r2": "R2 (resistencia de realimentación, Ω)",
    "capacity_mah": "capacidad de batería (mAh)",
    "current_ma": "consumo (mA)",
    "charge_current_ma": "corriente de carga (mA)",
    "voltage": "V (tensión, V)",
    "current": "I (corriente, A)",
    "rpm": "RPM",
    "power_w": "potencia (W)",
    "i_max": "corriente máxima (A)",
    "p_w": "potencia a disipar (W)",
}


# ── Explicación del resultado ─────────────────────────────────────────────────

EXPLAIN_PROMPT = """Sos Stratum, ingeniero electrónico senior.
El motor de cálculo Python ya calculó el resultado exacto. Tu trabajo es explicarlo claramente.

Consulta original: {task}

Resultado del cálculo:
{result_json}

{stock_info}

Instrucciones:
- Explicá el resultado en 2-4 líneas, directo al punto
- Mostrá la fórmula usada
- Si hay un valor estándar (std_value), recomendalo
- Si hay advertencias (warnings), mencionálas
- Si hay un componente en stock, mencioná que está disponible
- Si el resultado tiene campos extra (extra), incluí los más relevantes
- No inventes valores — usá SOLO los del resultado JSON
- Formato: texto limpio con negritas para los valores clave"""
