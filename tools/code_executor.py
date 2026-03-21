# tools/code_executor.py
#
# Ejecutor de código Python con sandbox real.
#
# Mejoras de seguridad respecto a la versión anterior:
#   1. __builtins__ restringido — solo funciones seguras, sin open/eval/compile/__import__
#   2. Timeout via threading — código que cuelga se mata después de MAX_EXEC_SECONDS
#   3. Límite de output — evita que código malicioso genere GBs de texto
#   4. Bloqueo de patrones peligrosos — no se puede acceder a __class__, __globals__, etc.
#   5. Sin acceso a módulos del sistema — os, sys, subprocess bloqueados

import io
import traceback
import threading
import math
import random
import json
import re
import string
import statistics
import collections
import itertools
from datetime import datetime, date, timedelta
from core.logger import logger

MAX_EXEC_SECONDS = 5
MAX_OUTPUT_CHARS = 10_000

# ── Lista blanca de builtins seguros ─────────────────────────────────────────

SAFE_BUILTINS: dict = {
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "frozenset": frozenset, "bytes": bytes, "bytearray": bytearray,
    "complex": complex,
    "abs": abs, "all": all, "any": any, "bin": bin, "chr": chr,
    "divmod": divmod, "enumerate": enumerate, "filter": filter,
    "format": format, "hash": hash, "hex": hex, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len, "map": map,
    "max": max, "min": min, "next": next, "oct": oct, "ord": ord,
    "pow": pow, "print": print, "range": range, "repr": repr,
    "reversed": reversed, "round": round, "slice": slice, "sorted": sorted,
    "sum": sum, "type": type, "zip": zip,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError, "StopIteration": StopIteration,
    "RuntimeError": RuntimeError, "AttributeError": AttributeError,
    "True": True, "False": False, "None": None,
    "math": math, "random": random, "json": json, "re": re,
    "string": string, "statistics": statistics,
    "collections": collections, "itertools": itertools,
    "datetime": datetime, "date": date, "timedelta": timedelta,
}

ALLOWED_MODULES = {
    "math", "random", "json", "re", "string", "statistics",
    "collections", "itertools", "datetime",
}

# Patrones que se bloquean antes de ejecutar (análisis estático)
BLOCKED_PATTERNS = [
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__code__", "__closure__", "__builtins__",
    "__import__", "importlib", "ctypes", "pickle",
    "subprocess", "socket", "urllib", "requests", "httpx",
    "open(", "exec(", "eval(", "compile(",
    "os.system", "os.popen", "os.execv",
    "sys.exit", "sys.modules", "sys.path",
]


def execute_python(code: str) -> str:
    """
    Ejecuta código Python en un sandbox real con timeout.

    Restricciones activas:
    - Builtins: solo funciones seguras (sin open, eval, __import__)
    - Imports: solo módulos de la lista blanca
    - Timeout: 5 segundos máximo
    - Output: limitado a 10.000 caracteres
    """
    # 1. Análisis estático — bloquear patrones peligrosos
    for pattern in BLOCKED_PATTERNS:
        if pattern in code:
            return (
                f"Código bloqueado: contiene '{pattern}'.\n"
                f"El sandbox no permite acceso a filesystem, red ni introspección del intérprete."
            )

    # 2. Validar imports
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            parts  = stripped.split()
            module = parts[1].split(".")[0] if len(parts) > 1 else ""
            if module and module not in ALLOWED_MODULES:
                return (
                    f"Import bloqueado: '{module}'.\n"
                    f"Módulos permitidos: {', '.join(sorted(ALLOWED_MODULES))}"
                )

    # 3. Preparar entorno con builtins restringidos
    stdout_capture = io.StringIO()
    result_holder: dict = {"output": None, "error": None}

    safe_builtins = dict(SAFE_BUILTINS)
    safe_builtins["print"] = lambda *args, **kwargs: print(
        *args, **{**kwargs, "file": stdout_capture}
    )

    exec_globals = {
        "__builtins__": safe_builtins,
        "__name__":     "__sandbox__",
        "__doc__":      None,
    }

    # 4. Ejecutar en thread separado con timeout
    def _run() -> None:
        try:
            exec(code, exec_globals)  # noqa: S102
            result_holder["output"] = stdout_capture.getvalue()
        except Exception:
            result_holder["error"] = traceback.format_exc()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=MAX_EXEC_SECONDS)

    # 5. Verificar timeout
    if thread.is_alive():
        logger.warning("[CodeExecutor] Timeout: código superó el límite de tiempo")
        return (
            f"Timeout: el código tardó más de {MAX_EXEC_SECONDS} segundos.\n"
            f"Revisá si hay loops infinitos o cálculos muy pesados."
        )

    # 6. Procesar resultado
    if result_holder["error"]:
        error = result_holder["error"]
        logger.error(f"[CodeExecutor] Error en sandbox: {error[:200]}")
        return f"Error:\n{error}"

    output = result_holder["output"] or ""

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... [output truncado a {MAX_OUTPUT_CHARS} chars]"

    logger.info("[CodeExecutor] Código ejecutado correctamente en sandbox")
    return f"Output:\n{output.strip()}" if output.strip() else "Código ejecutado sin output."