#!/usr/bin/env python3
"""
run.py — Punto de entrada único de Stratum

Comandos:
  python run.py                        → inicia el servidor (modo por defecto)
  python run.py serve                  → inicia el servidor
  python run.py serve --port 8080      → puerto personalizado
  python run.py serve --no-reload      → sin hot-reload

  python run.py setup                  → instala dependencias y configura el entorno
  python run.py setup --no-ollama      → omite la instalación de Ollama

  python run.py status                 → estado de la memoria
  python run.py export                 → backup a ZIP
  python run.py export -o mi_bkp.zip   → backup con nombre específico
  python run.py import mi_bkp.zip      → restaurar backup
  python run.py import mi_bkp.zip --merge  → fusionar sin sobreescribir
  python run.py reset --confirm        → borrar toda la memoria (pide confirmación)
"""

import os
import sys
import argparse

# ── Fix encoding Windows (cp1252 no soporta → ✓ ✗) ──────────────────────────
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from cli.utils import _c, info, warn


# =============================================================================
# SERVE
# =============================================================================

def cmd_serve(port: int, reload: bool) -> None:
    """Levanta el servidor FastAPI completo con todos los módulos activos."""
    from dotenv import load_dotenv
    load_dotenv(override=True)  # .env local tiene prioridad; Railway no usa .env

    # Railway y otros PaaS inyectan PORT como variable de entorno
    port = int(os.getenv("PORT", str(port)))

    # Crear directorios de persistencia si no existen (Railway Volume o local)
    for _path_var, _default in [
        ("MEMORY_DB_PATH",  "./database/memory.db"),
        ("VECTOR_DB_PATH",  "./memory_db"),
        ("GRAPH_DB_PATH",   "./database/graph_memory.json"),
    ]:
        _dir = os.path.dirname(os.getenv(_path_var, _default))
        if _dir:
            try:
                os.makedirs(_dir, exist_ok=True)
            except OSError:
                pass  # sin permiso (ej: Railway sin Volume) — los módulos usarán ruta por defecto

    # Validar configuración antes de arrancar (advertencia, no crash)
    try:
        from core.config import validate_config
        validate_config()
    except (EnvironmentError, ValueError) as e:
        warn(f"Config incompleta (el servidor levanta igual): {e}")

    print(f"\n{_c('STRATUM — Hardware Memory Engine', 96)}")
    info(f"Servidor en http://localhost:{port}")
    info(f"Viewer de circuitos: http://localhost:{port}/api/circuits/viewer")
    info(f"Health check:        http://localhost:{port}/api/health")
    info("Presioná Ctrl+C para detener\n")

    import uvicorn
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        reload_dirs=["agent", "api", "core", "database", "infrastructure",
                     "llm", "memory", "tools", "knowledge"] if reload else None,
    )


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Stratum — Hardware Memory Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run.py                        iniciar servidor (puerto 8000)
  python run.py serve --port 8080      iniciar en otro puerto
  python run.py serve --no-reload      sin hot-reload (producción)
  python run.py setup                  instalar dependencias y configurar
  python run.py setup --no-ollama      setup sin Ollama
  python run.py status                 ver estado de la memoria
  python run.py export                 backup a ZIP
  python run.py export -o bkp.zip      backup con nombre específico
  python run.py import bkp.zip         restaurar backup
  python run.py import bkp.zip --merge fusionar con memoria existente
  python run.py reset --confirm        borrar toda la memoria
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # serve
    p_serve = sub.add_parser("serve", help="Iniciar el servidor (por defecto)")
    p_serve.add_argument("--port", type=int, default=8000, help="Puerto (default: 8000)")
    p_serve.add_argument("--no-reload", action="store_true", help="Deshabilitar hot-reload")

    # setup
    p_setup = sub.add_parser("setup", help="Instalar dependencias y configurar el entorno")
    p_setup.add_argument("--no-ollama", action="store_true", help="Omitir instalación de Ollama")

    # status
    sub.add_parser("status", help="Ver estado de la memoria")

    # export
    p_export = sub.add_parser("export", help="Exportar memoria a ZIP")
    p_export.add_argument("--output", "-o", help="Nombre del archivo de salida")

    # import
    p_import = sub.add_parser("import", help="Importar memoria desde ZIP")
    p_import.add_argument("file", help="Archivo ZIP de backup")
    p_import.add_argument("--merge", action="store_true",
                          help="Fusionar con memoria existente")

    # reset
    p_reset = sub.add_parser("reset", help="Borrar toda la memoria")
    p_reset.add_argument("--confirm", action="store_true",
                         help="Confirmar el reset (obligatorio)")

    # bridge
    p_bridge = sub.add_parser("bridge", help="Iniciar el Hardware Bridge Client (programación remota)")
    p_bridge.add_argument("--url",   required=True, help="URL del backend Stratum (ej: https://stratum.up.railway.app)")
    p_bridge.add_argument("--token", default=os.getenv("BRIDGE_TOKEN", ""), help="Token de autenticación (BRIDGE_TOKEN)")

    args = parser.parse_args()

    # Sin subcomando → serve por defecto
    if not args.command:
        cmd_serve(port=8000, reload=True)
        return

    if args.command == "serve":
        cmd_serve(port=args.port, reload=not args.no_reload)

    elif args.command == "setup":
        from cli.setup import cmd_setup
        cmd_setup(no_ollama=args.no_ollama)

    elif args.command == "status":
        from cli.status import cmd_status
        sys.exit(cmd_status())

    elif args.command == "export":
        from cli.backup import cmd_export
        sys.exit(cmd_export(getattr(args, "output", None)))

    elif args.command == "import":
        from cli.backup import cmd_import
        sys.exit(cmd_import(args.file, getattr(args, "merge", False)))

    elif args.command == "reset":
        from cli.reset import cmd_reset
        sys.exit(cmd_reset(getattr(args, "confirm", False)))

    elif args.command == "bridge":
        from tools.hardware_bridge_client import run_bridge
        import asyncio
        asyncio.run(run_bridge(args.url, args.token))


if __name__ == "__main__":
    main()
