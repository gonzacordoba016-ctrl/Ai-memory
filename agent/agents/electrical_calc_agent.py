# agent/agents/electrical_calc_agent.py
#
# Agente de cálculo de ingeniería eléctrica/electrónica para Stratum.
# Flujo: clasificar tipo → extraer parámetros → calcular con fórmulas Python → explicar con LLM.
# El LLM NO hace las cuentas — Python las hace. El LLM solo interpreta y explica.

import json
import re
from core.logger import logger
from llm.async_client import call_llm_text
from tools.electrical_formulas import FORMULA_REGISTRY


# ── Prompt de clasificación ────────────────────────────────────────────────────

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


# ── Prompts de extracción de parámetros por tipo ──────────────────────────────

EXTRACT_PROMPTS = {
    "resistor_for_led": """Extraé los parámetros para calcular resistencia de LED.
JSON con claves: vcc (float, voltios fuente), vled (float, caída en LED), iled_ma (float, corriente en mA).
Valores típicos si no se mencionan: vled=2.0 para rojo/amarillo, vled=3.3 para azul/blanco, iled_ma=20.
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


# ── Prompt de explicación final ───────────────────────────────────────────────

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


class ElectricalCalcAgent:
    """Agente de cálculo de ingeniería eléctrica/electrónica."""

    name = "ElectricalCalcAgent"

    async def run(self, task: str, stock_db=None) -> str:
        """
        Ejecuta el flujo completo: clasificar → extraer → calcular → explicar.
        stock_db: instancia de ComponentStockDB (opcional, para buscar componentes cercanos).
        """
        try:
            # ── Paso 1: Clasificar tipo de cálculo ───────────────────────────
            formula_key = await self._classify(task)
            logger.info(f"[ElectricalCalc] Tipo: {formula_key}")

            if formula_key == "unknown" or formula_key not in FORMULA_REGISTRY:
                return None  # No es un cálculo — dejar al HardwareAgent/LLM

            # ── Paso 2: Extraer parámetros ───────────────────────────────────
            params = await self._extract_params(task, formula_key)
            if params is None:
                return None

            # ── Paso 3: Calcular con fórmula Python ──────────────────────────
            formula_fn = FORMULA_REGISTRY[formula_key]
            result = formula_fn(**params)
            logger.info(f"[ElectricalCalc] Resultado: {result}")

            # ── Paso 4: Buscar en stock ───────────────────────────────────────
            stock_info = ""
            if stock_db and result.get("std_value"):
                stock_info = await self._find_in_stock(stock_db, formula_key, result)

            # ── Paso 5: Explicar con LLM ──────────────────────────────────────
            response = await self._explain(task, result, stock_info)
            return response

        except Exception as e:
            logger.error(f"[ElectricalCalc] Error: {e}")
            return None

    async def _classify(self, task: str) -> str:
        prompt = CLASSIFY_PROMPT.replace("{task}", task)
        raw = await call_llm_text(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            timeout=15.0,
            agent_id="electrical_calc",
            agent_name="ElectricalCalc",
        )
        key = raw.strip().lower().split()[0] if raw.strip() else "unknown"
        # Fallback por keywords si el LLM devuelve algo inesperado
        if key not in FORMULA_REGISTRY and key != "unknown":
            key = self._keyword_classify(task)
        return key

    def _keyword_classify(self, task: str) -> str:
        """Clasificación por keywords como fallback."""
        t = task.lower()
        if any(w in t for w in ["led", "diodo led"]):
            return "resistor_for_led"
        if any(w in t for w in ["divisor", "voltage divider"]):
            return "resistor_voltage_divider"
        if any(w in t for w in ["buck", "reductor", "step down"]):
            return "buck_converter"
        if any(w in t for w in ["boost", "elevador", "step up"]):
            return "boost_converter"
        if any(w in t for w in ["transformador", "transformer", "relación de transformación"]):
            return "transformer_turns_ratio"
        if any(w in t for w in ["autonomía", "autonomia", "cuánto dura", "cuanto dura"]):
            return "battery_autonomy"
        if any(w in t for w in ["fusible", "fuse"]):
            return "fuse_rating"
        if any(w in t for w in ["disipador", "heat sink", "heatsink"]):
            return "heat_sink_required"
        if any(w in t for w in ["vfd", "variador", "rpm"]):
            return "vfd_frequency_for_rpm"
        if any(w in t for w in ["torque"]):
            return "motor_torque"
        if any(w in t for w in ["ohm", "ley de ohm"]):
            return "ohms_law"
        if any(w in t for w in ["paso bajo", "low pass"]):
            return "low_pass_rc"
        if any(w in t for w in ["paso alto", "high pass"]):
            return "high_pass_rc"
        if any(w in t for w in ["inversor", "inverting"]):
            return "inverting_amp"
        if any(w in t for w in ["no inversor", "non inverting"]):
            return "non_inverting_amp"
        return "unknown"

    async def _extract_params(self, task: str, formula_key: str) -> dict | None:
        """Extrae parámetros numéricos de la consulta via LLM."""
        extract_prompt = EXTRACT_PROMPTS.get(formula_key)
        if not extract_prompt:
            return {}

        prompt = extract_prompt.replace("{task}", task)
        raw = await call_llm_text(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            timeout=20.0,
            agent_id="electrical_calc",
            agent_name="ElectricalCalc",
        )

        # Extraer JSON del texto
        json_match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if not json_match:
            logger.warning(f"[ElectricalCalc] No se pudo extraer JSON de: {raw[:100]}")
            return None

        try:
            params = json.loads(json_match.group())
            # Limpiar Nones explícitos
            return {k: v for k, v in params.items() if v is not None}
        except json.JSONDecodeError as e:
            logger.warning(f"[ElectricalCalc] JSON inválido: {e}")
            return None

    async def _find_in_stock(self, stock_db, formula_key: str, result: dict) -> str:
        """Busca en el stock de componentes el valor más cercano al calculado."""
        try:
            std_val = result.get("std_value")
            if not std_val:
                return ""

            # Determinar categoría según tipo de cálculo
            cat_map = {
                "resistor_for_led":         "resistencia",
                "resistor_voltage_divider": "resistencia",
                "resistor_power":           "resistencia",
                "capacitor_filter":         "capacitor",
                "rc_time_constant":         "capacitor",
                "low_pass_rc":              "capacitor",
                "high_pass_rc":             "resistencia",
                "buck_converter":           "inductor",
                "boost_converter":          "inductor",
                "fuse_rating":              "fusible",
            }
            category = cat_map.get(formula_key, "")
            if not category:
                return ""

            items = stock_db.search_components(category) or []
            if not items:
                return ""

            # Encontrar el más cercano al valor estándar
            def parse_value(item):
                val_str = str(item.get("value", "0")).replace(",", ".").strip()
                num = re.search(r'[\d.]+', val_str)
                return float(num.group()) if num else 0.0

            closest = min(items, key=lambda x: abs(parse_value(x) - float(std_val)), default=None)
            if closest:
                return (f"\nComponente en stock: **{closest['name']}** "
                        f"(valor: {closest.get('value','?')}, "
                        f"qty: {closest.get('quantity','?')}, "
                        f"categoría: {closest.get('category','?')})")
        except Exception as e:
            logger.warning(f"[ElectricalCalc] Error buscando stock: {e}")
        return ""

    async def _explain(self, task: str, result: dict, stock_info: str) -> str:
        """Formatea la respuesta final con LLM."""
        prompt = EXPLAIN_PROMPT.format(
            task=task,
            result_json=json.dumps(result, ensure_ascii=False, indent=2),
            stock_info=stock_info if stock_info else "(Sin información de stock disponible)",
        )
        response = await call_llm_text(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            timeout=30.0,
            agent_id="electrical_calc",
            agent_name="ElectricalCalc",
        )
        return response or "No se pudo generar la explicación."


# ── Instancia singleton ────────────────────────────────────────────────────────

_electrical_calc_agent = None


def get_electrical_calc_agent() -> ElectricalCalcAgent:
    global _electrical_calc_agent
    if _electrical_calc_agent is None:
        _electrical_calc_agent = ElectricalCalcAgent()
    return _electrical_calc_agent
