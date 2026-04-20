# agent/agents/electrical_calc_agent.py
#
# Agente de cálculo de ingeniería eléctrica/electrónica para Stratum.
# Flujo: clasificar tipo → extraer parámetros → calcular con fórmulas Python → explicar con LLM.
# El LLM NO hace las cuentas — Python las hace. El LLM solo interpreta y explica.

import json
import math
import re
from core.logger import logger
from llm.async_client import call_llm_text
from tools.electrical_formulas import FORMULA_REGISTRY
from agent.prompts.electrical_calc_prompts import (
    CLASSIFY_PROMPT,
    EXTRACT_PARAMS_PROMPTS,
    EXPLAIN_PROMPT,
    REQUIRED_PARAMS,
    PARAM_LABELS,
)


class ElectricalCalcAgent:
    """Agente de cálculo de ingeniería eléctrica/electrónica."""

    name = "ElectricalCalcAgent"

    async def run(self, task: str, stock_db=None) -> str:
        """
        Ejecuta el flujo completo: clasificar → extraer → calcular → explicar.
        stock_db: instancia de ComponentStockDB (opcional, para buscar componentes cercanos).
        """
        try:
            # ── Paso 1: Clasificar intención ──────────────────────────────────
            formula_key = await self._classify_intent(task)
            logger.info(f"[ElectricalCalc] Tipo: {formula_key}")

            if formula_key == "unknown" or formula_key not in FORMULA_REGISTRY:
                return None  # No es un cálculo — dejar al HardwareAgent/LLM

            # ── Paso 2: Extraer parámetros ───────────────────────────────────
            params = await self._extract_params(task, formula_key)
            if params is None:
                return None

            missing = self._check_required(formula_key, params)
            if missing:
                labels = [PARAM_LABELS.get(p, p) for p in missing]
                return f"Para calcular, necesito que me des: **{', '.join(labels)}**."

            # ── Paso 3: Calcular con fórmula Python ──────────────────────────
            formula_fn = FORMULA_REGISTRY[formula_key]
            result = formula_fn(**params)
            logger.info(f"[ElectricalCalc] Resultado: {result}")

            # ── Paso 4: Buscar en stock ───────────────────────────────────────
            stock_info = ""
            if stock_db and result.get("std_value"):
                stock_info = await self._find_in_stock(stock_db, formula_key, result)

            # ── Paso 5: Card HTML + explicación LLM ──────────────────────────
            card = self._format_card_html(formula_key, params, result, stock_info)
            explanation = await self._explain(task, result, stock_info)
            if card:
                return card + f'<div class="calc-card-explanation">{explanation}</div>'
            return explanation

        except Exception as e:
            logger.error(f"[ElectricalCalc] Error: {e}")
            return None

    # ── Validación de parámetros requeridos ──────────────────────────────────

    def _check_required(self, formula_key: str, params: dict) -> list[str]:
        """Retorna lista de parámetros requeridos que faltan (son None o ausentes)."""
        if formula_key == "ohms_law":
            present = [k for k in ("v", "i_ma", "r") if params.get(k) is not None]
            return [] if len(present) >= 2 else ["v (voltios)", "i_ma (corriente mA)", "r (resistencia Ω) — al menos 2 de estos 3"]
        required = REQUIRED_PARAMS.get(formula_key, [])
        return [p for p in required if params.get(p) is None]

    # ── Clasificación de intención ────────────────────────────────────────────

    async def _classify_intent(self, task: str) -> str:
        """Determina el tipo de cálculo eléctrico mediante LLM con fallback por keywords."""
        prompt = CLASSIFY_PROMPT.replace("{task}", task)
        raw = await call_llm_text(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            timeout=15.0,
            agent_id="electrical_calc",
            agent_name="ElectricalCalc",
            use_cache=False,
        )
        key = raw.strip().lower().split()[0] if raw.strip() else "unknown"
        if key not in FORMULA_REGISTRY and key != "unknown":
            key = self._keyword_classify(task)
        return key

    def _keyword_classify(self, task: str) -> str:
        """Clasificación por keywords como fallback cuando el LLM devuelve algo inesperado."""
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

    # ── Extracción de parámetros ──────────────────────────────────────────────

    async def _extract_params(self, task: str, formula_key: str) -> dict | None:
        """Extrae parámetros numéricos de la consulta via LLM y parsea el JSON resultante."""
        extract_prompt = EXTRACT_PARAMS_PROMPTS.get(formula_key)
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
        return self._parse_json_response(raw)

    def _parse_json_response(self, raw: str) -> dict | None:
        """Extrae y parsea el primer objeto JSON de una respuesta LLM en texto libre."""
        json_match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if not json_match:
            logger.warning(f"[ElectricalCalc] No se pudo extraer JSON de: {raw[:100]}")
            return None
        try:
            params = json.loads(json_match.group())
            return {k: v for k, v in params.items() if v is not None}
        except json.JSONDecodeError as e:
            logger.warning(f"[ElectricalCalc] JSON inválido: {e}")
            return None

    # ── Stock y explicación ───────────────────────────────────────────────────

    async def _find_in_stock(self, stock_db, formula_key: str, result: dict) -> str:
        """Busca en el stock de componentes el valor más cercano al calculado."""
        try:
            std_val = result.get("std_value")
            if not std_val:
                return ""

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

    # ── Result card HTML ──────────────────────────────────────────────────────

    _CARD_META: dict = {
        "resistor_voltage_divider": {"title": "DIVISOR DE TENSIÓN",       "formula": r"V_{out} = V_{in} \cdot \dfrac{R_2}{R_1+R_2}", "bode": None},
        "resistor_for_led":         {"title": "RESISTENCIA PARA LED",      "formula": r"R = \dfrac{V_{cc}-V_f}{I_{LED}}",             "bode": None},
        "resistor_power":           {"title": "POTENCIA EN RESISTENCIA",   "formula": r"P = I^2 \cdot R = \dfrac{V^2}{R}",            "bode": None},
        "ohms_law":                 {"title": "LEY DE OHM",                "formula": r"V = I \cdot R",                               "bode": None},
        "low_pass_rc":              {"title": "FILTRO PASO BAJO RC",       "formula": r"f_c = \dfrac{1}{2\pi R C}",                   "bode": "lowpass"},
        "high_pass_rc":             {"title": "FILTRO PASO ALTO RC",       "formula": r"f_c = \dfrac{1}{2\pi R C}",                   "bode": "highpass"},
        "capacitor_filter":         {"title": "FILTRO RC",                 "formula": r"C = \dfrac{1}{2\pi f_c R}",                   "bode": "lowpass"},
        "rc_time_constant":         {"title": "CONSTANTE DE TIEMPO RC",    "formula": r"\tau = R \cdot C",                            "bode": None},
        "capacitor_energy":         {"title": "ENERGÍA EN CAPACITOR",      "formula": r"E = \tfrac{1}{2} C V^2",                      "bode": None},
        "power_dissipation":        {"title": "POTENCIA DISIPADA",         "formula": r"P = V \cdot I",                               "bode": None},
        "buck_converter":           {"title": "CONVERTIDOR BUCK",          "formula": r"D = \dfrac{V_{out}}{V_{in}}",                 "bode": None},
        "boost_converter":          {"title": "CONVERTIDOR BOOST",         "formula": r"D = 1 - \dfrac{V_{in}}{V_{out}}",             "bode": None},
        "transformer_turns_ratio":  {"title": "TRANSFORMADOR",             "formula": r"\dfrac{N_p}{N_s} = \dfrac{V_p}{V_s}",         "bode": None},
        "inverting_amp":            {"title": "AMPLIFICADOR INVERSOR",     "formula": r"A_v = -\dfrac{R_f}{R_{in}}",                  "bode": None},
        "non_inverting_amp":        {"title": "AMPLIFICADOR NO INVERSOR",  "formula": r"A_v = 1 + \dfrac{R_2}{R_1}",                  "bode": None},
        "battery_autonomy":         {"title": "AUTONOMÍA DE BATERÍA",      "formula": r"t = \dfrac{C_{mAh}}{I_{mA}}",                 "bode": None},
        "fuse_rating":              {"title": "FUSIBLE RECOMENDADO",       "formula": r"I_{fuse} = I_{max} \times f_{seg}",           "bode": None},
        "heat_sink_required":       {"title": "DISIPADOR TÉRMICO",         "formula": r"\theta_{sa} = \dfrac{T_j - T_a}{P} - \theta_{jc}", "bode": None},
        "motor_torque":             {"title": "TORQUE DE MOTOR",           "formula": r"\tau = \dfrac{P \times 9550}{n}",             "bode": None},
        "vfd_frequency_for_rpm":    {"title": "FRECUENCIA VFD",            "formula": r"f = \dfrac{n \times p}{120}",                 "bode": None},
    }

    def _fmt_val(self, v, unit="") -> str:
        """Formatea un número con sufijo de magnitud."""
        if not isinstance(v, (int, float)):
            return str(v)
        abs_v = abs(v)
        if abs_v == 0:
            return f"0 {unit}".strip()
        if abs_v >= 1e6:
            return f"{v/1e6:.3g} M{unit}"
        if abs_v >= 1e3:
            return f"{v/1e3:.3g} k{unit}"
        if abs_v < 0.01:
            return f"{v*1000:.3g} m{unit}"
        return f"{v:.4g} {unit}".strip()

    def _format_card_html(self, formula_key: str, params: dict, result: dict, stock_info: str) -> str:
        meta = self._CARD_META.get(formula_key)
        if not meta:
            return ""

        unit     = result.get("unit", "")
        value    = result.get("value", 0)
        std      = result.get("std_value")
        warnings = result.get("warnings", [])
        formula  = meta["formula"]
        bode_type = meta.get("bode")

        # Input rows
        rows_html = ""
        for k, v in params.items():
            if v is None:
                continue
            label = PARAM_LABELS.get(k, k)
            label = label.split("(")[0].strip()
            rows_html += f'<div class="row"><span>{label}</span><span>{self._fmt_val(v)}</span></div>'

        # Bode canvas (filters only)
        bode_html = ""
        if bode_type and isinstance(value, (int, float)) and value > 0:
            fc = value
            # For capacitor_filter / low_pass_rc the result IS C or R — fc is in params
            if formula_key in ("low_pass_rc", "high_pass_rc", "capacitor_filter"):
                fc = params.get("cutoff_hz") or params.get("freq_hz") or value
            bode_html = (
                f'<div class="calc-card-bode">'
                f'<div style="font-size:8px;color:#494847;letter-spacing:.1em;margin-bottom:6px">RESPUESTA EN FRECUENCIA</div>'
                f'<canvas data-bode=\'{{"type":"{bode_type}","fc":{fc}}}\'></canvas>'
                f'</div>'
            )

        # Warnings
        warn_html = "".join(
            f'<div class="calc-result-warn">⚠ {w}</div>' for w in (warnings or [])
        )
        std_html = f'<div class="calc-result-std">→ usar {self._fmt_val(std, unit)} (E24)</div>' if std else ""

        card = (
            f'<div class="calc-card">'
            f'  <div class="calc-card-type">{meta["title"]}</div>'
            f'  <div class="calc-card-formula">\\[{formula}\\]</div>'
            f'  <div class="calc-card-body">'
            f'    <div class="calc-card-inputs">{rows_html}</div>'
            f'    <div class="calc-card-result">'
            f'      <div class="calc-result-label">RESULTADO</div>'
            f'      <div class="calc-result-value">{self._fmt_val(value)}</div>'
            f'      <div class="calc-result-unit">{unit}</div>'
            f'      {std_html}{warn_html}'
            f'    </div>'
            f'  </div>'
            f'  {bode_html}'
            f'</div>'
        )
        return card

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
