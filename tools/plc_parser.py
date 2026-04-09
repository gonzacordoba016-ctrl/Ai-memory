# tools/plc_parser.py
# Parser básico de lógica ladder para PLCs industriales
# Soporta texto descriptivo y notación ladder ASCII

import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Tipos de elementos en lógica ladder
# ─────────────────────────────────────────────────────────────────────────────

ELEMENT_TYPES = {
    # Contactos (entradas)
    "NO":  "Contacto Normalmente Abierto",
    "NC":  "Contacto Normalmente Cerrado",
    "XIC": "Examine If Closed (NO)",
    "XIO": "Examine If Open (NC)",
    # Bobinas (salidas)
    "OTE": "Output Energize",
    "OTL": "Output Latch",
    "OTU": "Output Unlatch",
    "( )": "Bobina de salida",
    # Temporizadores
    "TON": "Timer On Delay",
    "TOF": "Timer Off Delay",
    "RTO": "Retentive Timer On",
    # Contadores
    "CTU": "Counter Up",
    "CTD": "Counter Down",
    "RES": "Reset",
    # Comparadores
    "EQU": "Equal",
    "NEQ": "Not Equal",
    "GRT": "Greater Than",
    "LES": "Less Than",
    "GEQ": "Greater Than or Equal",
    "LEQ": "Less Than or Equal",
    # Matemáticos
    "ADD": "Add",
    "SUB": "Subtract",
    "MUL": "Multiply",
    "DIV": "Divide",
    "MOV": "Move",
}


# ─────────────────────────────────────────────────────────────────────────────
# Parser de texto descriptivo en español/inglés
# ─────────────────────────────────────────────────────────────────────────────

def parse_ladder_text(text: str) -> dict:
    """
    Parsea una descripción textual de lógica ladder.
    Soporta descripciones en lenguaje natural y notación básica.

    Ejemplo:
        "Si el sensor S1 está activo Y el botón B2 está presionado, activar la bomba M1
         con un temporizador TON de 5 segundos"
    """
    rungs = []
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]

    for line in lines:
        rung = _parse_rung_line(line)
        if rung:
            rungs.append(rung)

    if not rungs:
        # Intentar parsear como bloque de texto completo
        rung = _parse_rung_line(text)
        if rung:
            rungs.append(rung)

    # Extraer variables únicas
    all_vars = set()
    for r in rungs:
        all_vars.update(r.get("inputs", []))
        all_vars.update(r.get("outputs", []))

    return {
        "type":       "ladder",
        "rungs":      rungs,
        "rung_count": len(rungs),
        "variables":  sorted(all_vars),
        "raw":        text,
    }


def _parse_rung_line(line: str) -> Optional[dict]:
    """Parsea una línea/rung individual."""
    line_lower = line.lower()

    inputs = []
    outputs = []
    timers = []
    counters = []
    conditions = []
    actions = []

    # Detectar condiciones (entradas / contactos)
    # Patrones: "si X", "when X", "if X", "X activo", "X cerrado", "X = 1"
    cond_patterns = [
        r'si\s+(?:el\s+|la\s+)?(\w+)\s+(?:está\s+)?(?:activ|encend|cerrad|presionad)',
        r'if\s+(\w+)\s+(?:is\s+)?(?:activ|on|closed|pressed)',
        r'when\s+(\w+)\s+(?:is\s+)?(?:activ|on|closed)',
        r'(\w+)\s+(?:está\s+)?activ[ao]',
        r'(\w+)\s+=\s*1',
        r'\[(\w+)\]',      # notación [contacto]
        r'-\|\s*(\w+)\s*\|-',  # notación ladder ASCII -|X|-
    ]
    for pat in cond_patterns:
        for m in re.finditer(pat, line, re.IGNORECASE):
            var = m.group(1).upper()
            if var not in inputs:
                inputs.append(var)
            conditions.append({"type": "NO", "tag": var})

    # Contactos NC
    nc_patterns = [
        r'si\s+(?:el\s+|la\s+)?(\w+)\s+(?:está\s+)?(?:inactiv|apagad|abierto|no\s+activ)',
        r'if\s+(\w+)\s+(?:is\s+)?(?:not\s+activ|off|open)',
        r'(\w+)\s+(?:está\s+)?inactiv[ao]',
        r'-\|/\s*(\w+)\s*\|-',  # -|/X|-
    ]
    for pat in nc_patterns:
        for m in re.finditer(pat, line, re.IGNORECASE):
            var = m.group(1).upper()
            if var not in inputs:
                inputs.append(var)
            conditions.append({"type": "NC", "tag": var})

    # Detectar acciones (salidas / bobinas)
    action_patterns = [
        r'activ[ar]+\s+(?:la\s+|el\s+)?(\w+)',
        r'encend[er]+\s+(?:la\s+|el\s+)?(\w+)',
        r'energiz[ar]+\s+(?:la\s+|el\s+)?(\w+)',
        r'activat[e]+\s+(\w+)',
        r'turn\s+on\s+(\w+)',
        r'\(\s*(\w+)\s*\)',   # notación (bobina)
        r'--\(\s*(\w+)\s*\)--',
    ]
    for pat in action_patterns:
        for m in re.finditer(pat, line, re.IGNORECASE):
            var = m.group(1).upper()
            if var not in outputs:
                outputs.append(var)
            actions.append({"type": "OTE", "tag": var})

    # Detectar temporizadores
    timer_pattern = r'(TON|TOF|RTO)\s*(?:de\s+|of\s+)?([\d.]+)\s*(?:s|seg|segundos|seconds|ms)?'
    for m in re.finditer(timer_pattern, line, re.IGNORECASE):
        t_type = m.group(1).upper()
        t_val  = m.group(2)
        timers.append({"type": t_type, "preset": float(t_val)})

    # Detectar contadores
    counter_pattern = r'(CTU|CTD)\s*(?:hasta\s+|to\s+)?([\d]+)'
    for m in re.finditer(counter_pattern, line, re.IGNORECASE):
        c_type = m.group(1).upper()
        c_val  = m.group(2)
        counters.append({"type": c_type, "preset": int(c_val)})

    # Si no encontramos nada, retornar None
    if not conditions and not actions and not timers:
        return None

    return {
        "description": line,
        "conditions":  conditions,
        "actions":     actions,
        "timers":      timers,
        "counters":    counters,
        "inputs":      inputs,
        "outputs":     outputs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Generador de pseudocódigo estructurado (ST — Structured Text básico)
# ─────────────────────────────────────────────────────────────────────────────

def ladder_to_structured_text(ladder: dict) -> str:
    """Convierte el resultado del parser a pseudocódigo Structured Text (IEC 61131-3)."""
    lines = ["(* Generado por Stratum — Lógica Ladder *)", ""]

    for i, rung in enumerate(ladder.get("rungs", []), 1):
        lines.append(f"(* Rung {i}: {rung.get('description', '')[:60]} *)")

        conds  = rung.get("conditions", [])
        acts   = rung.get("actions", [])
        timers = rung.get("timers", [])

        if conds:
            cond_str = " AND ".join(
                f"{'NOT ' if c['type'] == 'NC' else ''}{c['tag']}"
                for c in conds
            )
            for a in acts:
                lines.append(f"IF {cond_str} THEN")
                lines.append(f"    {a['tag']} := TRUE;")
                for t in timers:
                    lines.append(f"    {t['type']}_{a['tag']}(IN := TRUE, PT := T#{t['preset']}s);")
                lines.append("ELSE")
                lines.append(f"    {a['tag']} := FALSE;")
                lines.append("END_IF;")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def parse_plc_input(text: str) -> dict:
    """
    Entry point principal. Parsea lógica ladder desde texto descriptivo.
    Retorna dict con rungs, variables y pseudocódigo ST.
    """
    ladder = parse_ladder_text(text)
    ladder["structured_text"] = ladder_to_structured_text(ladder)
    return ladder
