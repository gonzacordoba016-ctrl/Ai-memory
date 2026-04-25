# agent/quality_estimator.py
# Estima tiempo de respuesta para "modo calidad" — calidad > velocidad.
# El objetivo es informar al usuario upfront cuánto tardará el agente
# en entregar bien hecho, antes de empezar a procesar.

import re
from typing import Dict, List

# Fases canónicas que el agente atraviesa, con su nombre legible
PHASE_LABELS = {
    "understanding":      "Entendiendo el pedido",
    "routing":            "Decidiendo qué agentes usar",
    "generating_circuit": "Generando circuito (LLM)",
    "validating":         "Validando reglas eléctricas y completando faltantes",
    "rendering":          "Renderizando esquemático y PCB",
    "responding":         "Componiendo respuesta",
}

# Costos base por fase en segundos (estimación conservadora SMART model)
_PHASE_BASE_COST = {
    "understanding":       1,
    "routing":             1,
    "generating_circuit": 35,   # gpt-4o ~30-45s para JSON estructurado
    "validating":          2,
    "rendering":           2,
    "responding":          5,
}

# Keywords que disparan circuit_design pipeline
_CIRCUIT_KEYWORDS = (
    "circuito", "esquemático", "esquematico", "pcb", "schematic",
    "diseña", "diseñá", "armar", "armá", "hace el", "hacé el",
    "controlador", "fuente de alimentación", "fuente conmutada",
    "fuente lineal", "amplificador", "preamplificador",
)
_AC_KEYWORDS    = ("220vac", "220 vac", "220v", "110vac", "110v", "230vac",
                   "red eléctrica", "red electrica", "corriente alterna")
_SIMPLE_QUERY   = ("hola", "gracias", "cómo estás", "como estas", "qué hora", "que hora")


def _count_loads(query: str) -> int:
    """Detecta N (cantidad de cargas / relays / electroválvulas) si está en el texto."""
    q = query.lower()
    # Patrones tipo "7 relays", "5 electroválvulas", "para 12 motores"
    m = re.search(r"\b(\d{1,2})\s+(?:relays?|electroválvulas?|electrovalvulas?|"
                  r"válvulas?|valvulas?|motores?|cargas?|salidas?|leds?)\b", q)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 32 else 0
    return 0


def estimate_quality_time(query: str) -> Dict:
    """
    Devuelve estimación de tiempo + fases que el agente atravesará.

    Returns:
        {
          "seconds":   int (estimado total),
          "phases":    list[{"name": str, "label": str, "estimated_seconds": int}],
          "complexity": "simple" | "medium" | "complex",
          "reasoning": str (frase humana del por qué de la estimación),
        }
    """
    q = (query or "").lower().strip()

    # — Caso trivial: saludos / pregunta corta sin keywords técnicos —
    if len(q) < 25 and any(s in q for s in _SIMPLE_QUERY):
        return {
            "seconds":    3,
            "phases":     [_phase("understanding"), _phase("responding", 2)],
            "complexity": "simple",
            "reasoning":  "Pedido simple, respuesta directa.",
        }

    is_circuit = any(kw in q for kw in _CIRCUIT_KEYWORDS)
    has_ac     = any(kw in q for kw in _AC_KEYWORDS)
    n_loads    = _count_loads(q)

    if not is_circuit:
        # Consulta general (búsqueda, cálculo, hardware sin diseño nuevo)
        return {
            "seconds":    8,
            "phases":     [_phase("understanding"), _phase("routing"),
                           _phase("responding", 6)],
            "complexity": "simple",
            "reasoning":  "Consulta general — no requiere diseño de circuito.",
        }

    # — Diseño de circuito: estimación detallada —
    phases: List[Dict] = [
        _phase("understanding"),
        _phase("routing"),
        _phase("generating_circuit"),  # base 35s
        _phase("validating"),
        _phase("rendering"),
        _phase("responding"),
    ]

    # Ajustes por complejidad
    extra = 0
    reasons: List[str] = []
    if has_ac:
        extra += 12
        reasons.append("entrada AC requiere etapa de conversión validada")
        # bump validating phase
        for p in phases:
            if p["name"] == "validating":
                p["estimated_seconds"] += 4
    if n_loads >= 4:
        per_load = 4
        extra += per_load * n_loads
        reasons.append(f"{n_loads} cargas — cada relay con flyback + control + conector")
        for p in phases:
            if p["name"] == "generating_circuit":
                p["estimated_seconds"] += per_load * n_loads
    elif n_loads >= 2:
        extra += 6
        reasons.append(f"{n_loads} cargas — circuito multi-canal")

    if "i2c" in q or "spi" in q or "uart" in q:
        extra += 8
        reasons.append("comunicación serial — pinout específico")
        for p in phases:
            if p["name"] == "generating_circuit":
                p["estimated_seconds"] += 6

    total = sum(p["estimated_seconds"] for p in phases)
    complexity = "complex" if total > 70 else ("medium" if total > 30 else "simple")

    if not reasons:
        reasons.append("circuito estándar")

    return {
        "seconds":    total,
        "phases":     phases,
        "complexity": complexity,
        "reasoning":  "Diseño de circuito — " + "; ".join(reasons) + ".",
    }


def _phase(name: str, override_seconds: int = None) -> Dict:
    return {
        "name":              name,
        "label":             PHASE_LABELS.get(name, name),
        "estimated_seconds": override_seconds if override_seconds is not None
                             else _PHASE_BASE_COST.get(name, 5),
    }
