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
JSON con claves: vin (float), vout (float), r1 (float, ohmios — si no se da usar 10000).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "resistor_power": """Extraé parámetros para potencia en resistencia.
JSON con claves: r (float, ohmios), y uno de: i_ma (float, corriente mA) o v (float, tensión V).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "capacitor_filter": """Extraé parámetros para filtro RC.
JSON con claves: freq_hz (float, frecuencia de corte en Hz), resistance (float, ohmios).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "rc_time_constant": """Extraé parámetros para constante de tiempo RC.
JSON con claves: r (float, ohmios), c_uf (float, capacitor en µF/uF).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "capacitor_energy": """Extraé parámetros para energía en capacitor.
JSON con claves: c_uf (float, µF), v (float, voltios).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "power_dissipation": """Extraé parámetros para potencia disipada.
JSON con claves: v (float, voltios), i_ma (float, corriente en mA).
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
JSON con claves: vin (float, tensión entrada V), vout (float, tensión salida V),
iout (float, corriente salida A), freq_khz (float, frecuencia kHz, default 100).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "boost_converter": """Extraé parámetros para convertidor BOOST.
JSON con claves: vin (float, tensión entrada V), vout (float, tensión salida V),
iout (float, corriente salida A), freq_khz (float, frecuencia kHz, default 100).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "transformer_turns_ratio": """Extraé parámetros para transformador.
JSON con claves: vp (float, tensión primario V), vs (float, tensión secundario V),
ip (float, corriente primario A, opcional), is_ (float, corriente secundario A, opcional).
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
JSON con claves: voltage (float, V), current (float, A), efficiency (float, 0-1, default 0.85).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "vfd_frequency_for_rpm": """Extraé parámetros para frecuencia VFD.
JSON con claves: rpm (float), poles (int, número de polos del motor, default 4).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "motor_torque": """Extraé parámetros para torque de motor.
JSON con claves: power_w (float, potencia W), rpm (float).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",

    "ohms_law": """Extraé parámetros para ley de Ohm. Al menos 2 de 3.
JSON con claves: v (float, voltios, null si no se da), i_ma (float, mA, null si no se da),
r (float, ohmios, null si no se da).
Consulta: "{task}"
Respondé SOLO con JSON válido.""",
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
