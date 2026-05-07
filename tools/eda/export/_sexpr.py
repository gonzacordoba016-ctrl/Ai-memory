"""S-expression builder mínimo para output KiCad determinista."""
from __future__ import annotations

from typing import Any


def fmt(n: float, decimals: int = 4) -> str:
    """Formato numérico determinista — strip de ceros trailing."""
    s = f"{n:.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def quote(s: str) -> str:
    """Quote estilo KiCad: doble comillas con escapes mínimos."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sexpr(name: str, *children: Any) -> str:
    """Construye un S-expression `(name child1 child2 ...)`."""
    parts: list[str] = [name]
    for ch in children:
        if ch is None:
            continue
        if isinstance(ch, (int, float)):
            parts.append(fmt(ch) if isinstance(ch, float) else str(ch))
        else:
            parts.append(str(ch))
    return "(" + " ".join(parts) + ")"


def block(name: str, children: list[str], indent: int = 0) -> str:
    """Multi-line block con indentación KiCad-style."""
    pad = "  " * indent
    inner = "\n".join("  " * (indent + 1) + c for c in children)
    return f"{pad}({name}\n{inner}\n{pad})"
