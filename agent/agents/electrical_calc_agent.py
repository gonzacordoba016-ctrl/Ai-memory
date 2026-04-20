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

            # ── Paso 5: Explicar con LLM ──────────────────────────────────────
            response = await self._explain(task, result, stock_info)
            return response

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
