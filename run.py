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

# ── Colores ANSI ─────────────────────────────────────────────────────────────

_WIN = sys.platform == "win32"

def _c(text, code):
    return text if _WIN else f"\033[{code}m{text}\033[0m"

def ok(msg):   print(f"  {_c('✓', 92)} {msg}")
def warn(msg): print(f"  {_c('!', 93)} {msg}")
def err(msg):  print(f"  {_c('✗', 91)} {msg}")
def info(msg): print(f"  {_c('→', 96)} {msg}")
def step(msg): print(f"\n{_c(msg, 1)}")


# =============================================================================
# SERVE
# =============================================================================

def cmd_serve(port: int, reload: bool) -> None:
    """Levanta el servidor FastAPI completo con todos los módulos activos."""
    from dotenv import load_dotenv
    load_dotenv(override=True)

    os.environ["AETHERMIND_AGENT_ID"] = "56dd50bb-dba1-42fc-b46a-d9cefa170500"
    os.environ["AETHERMIND_ENV"]      = "development"

    # Railway y otros PaaS inyectan PORT como variable de entorno
    port = int(os.getenv("PORT", str(port)))

    # Validar configuración antes de arrancar
    try:
        from core.config import validate_config
        validate_config()
    except (EnvironmentError, ValueError) as e:
        err(f"Error de configuración:\n{e}")
        sys.exit(1)

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
# SETUP
# =============================================================================

def cmd_setup(no_ollama: bool) -> None:
    """Instala dependencias, configura arduino-cli y crea el .env si no existe."""
    import subprocess
    import shutil
    import time
    from pathlib import Path

    OLLAMA_MODEL = "qwen2.5:7b"

    print(f"\n{_c('STRATUM — Setup', 96)}\n")

    # ── Python ────────────────────────────────────────────────────────
    step("Verificando Python...")
    v = sys.version_info
    if v < (3, 10):
        err(f"Python 3.10+ requerido. Tenés {v.major}.{v.minor}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

    # ── Dependencias ──────────────────────────────────────────────────
    step("Instalando dependencias Python...")
    req = Path("requirements.txt")
    if not req.exists():
        err("requirements.txt no encontrado")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
        check=False
    )
    if result.returncode != 0:
        warn("Algunos paquetes no se instalaron correctamente. Revisá requirements.txt")
    else:
        ok("Dependencias instaladas")

    # ── Directorios ───────────────────────────────────────────────────
    step("Creando directorios...")
    for d in ["database", "memory_db", "agent_files/firmware",
              "agent_files/knowledge", "api/static"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    ok("Directorios listos")

    # ── .env ─────────────────────────────────────────────────────────
    step("Configurando .env...")
    env_path = Path(".env")
    if env_path.exists():
        info(".env ya existe — no se sobreescribe")
    else:
        env_path.write_text(
            f"LLM_PROVIDER=ollama\n"
            f"OLLAMA_MODEL={OLLAMA_MODEL}\n"
            f"LLM_MODEL_FAST={OLLAMA_MODEL}\n"
            f"LLM_MODEL_SMART={OLLAMA_MODEL}\n"
            f"OLLAMA_BASE_URL=http://localhost:11434\n"
            f"MEMORY_DB_PATH=./database/memory.db\n"
            f"VECTOR_DB_PATH=./memory_db\n"
            f"VECTOR_COLLECTION=agent_memory\n"
            f"QDRANT_URL=\n"
            f"MEMORY_DECAY_RATE=0.01\n"
            f"DEBUG=true\n"
            f"LOG_LEVEL=INFO\n"
        )
        ok(".env creado")

    # ── Ollama ────────────────────────────────────────────────────────
    if no_ollama:
        warn("Ollama omitido (--no-ollama)")
    else:
        step("Verificando Ollama...")
        if not shutil.which("ollama"):
            warn("Ollama no encontrado.")
            if sys.platform == "win32":
                info("Descargalo desde: https://ollama.com/download")
            elif sys.platform == "darwin":
                subprocess.run(["brew", "install", "ollama"], check=False)
            else:
                subprocess.run("curl -fsSL https://ollama.com/install.sh | sh",
                               shell=True, check=False)
        else:
            ok("Ollama encontrado")
            models_out = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True
            ).stdout
            if OLLAMA_MODEL not in models_out:
                info(f"Descargando {OLLAMA_MODEL} (~4.7GB, puede tardar)...")
                subprocess.run(["ollama", "pull", OLLAMA_MODEL], check=False)
                ok(f"Modelo {OLLAMA_MODEL} listo")
            else:
                ok(f"Modelo {OLLAMA_MODEL} disponible")

    # ── arduino-cli ───────────────────────────────────────────────────
    step("Verificando arduino-cli...")
    if shutil.which("arduino-cli"):
        version = subprocess.run(
            ["arduino-cli", "version"], capture_output=True, text=True
        ).stdout.strip()
        ok(f"arduino-cli: {version}")
        subprocess.run(["arduino-cli", "core", "update-index"],
                       capture_output=True, check=False)
        installed = subprocess.run(
            ["arduino-cli", "core", "list"], capture_output=True, text=True
        ).stdout
        if "arduino:avr" not in installed:
            info("Instalando core Arduino AVR...")
            subprocess.run(["arduino-cli", "core", "install", "arduino:avr"],
                           check=False)
            ok("Core Arduino AVR instalado")
        else:
            ok("Core Arduino AVR disponible")
    else:
        warn("arduino-cli no encontrado (necesario para compilar/flashear firmware)")
        if sys.platform == "win32":
            info("Descargalo desde: https://arduino.github.io/arduino-cli/latest/installation/")
        elif sys.platform == "darwin":
            info("brew install arduino-cli")
        else:
            info("curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh")

    # ── Verificación final ────────────────────────────────────────────
    step("Verificando paquetes Python...")
    missing = []
    for pkg in ["fastapi", "uvicorn", "qdrant_client", "sentence_transformers",
                "networkx", "serial", "dotenv"]:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    if missing:
        warn(f"Paquetes faltantes: {', '.join(missing)}")
        info("Ejecutá: pip install -r requirements.txt")
    else:
        ok("Todos los paquetes disponibles")

    print(f"\n{_c('Setup completo.', 92)} "
          f"Iniciá el proyecto con: {_c('python run.py', 96)}\n")


# =============================================================================
# STATUS
# =============================================================================

def cmd_status() -> int:
    import json
    import sqlite3
    from pathlib import Path

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    paths = _get_paths()

    print(f"\n{_c('STRATUM — Estado de memoria', 96)}\n")

    # SQLite
    if paths["sql_db"].exists():
        try:
            conn = sqlite3.connect(paths["sql_db"])
            facts = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            msgs  = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            try:
                devices  = conn.execute("SELECT COUNT(*) FROM hardware_devices").fetchone()[0]
                flashes  = conn.execute("SELECT COUNT(*) FROM firmware_history").fetchone()[0]
                circuits = conn.execute("SELECT COUNT(*) FROM circuit_context").fetchone()[0]
                projects = conn.execute("SELECT COUNT(*) FROM project_library").fetchone()[0]
                last_dev = conn.execute(
                    "SELECT device_name, last_seen FROM hardware_devices "
                    "ORDER BY last_seen DESC LIMIT 1"
                ).fetchone()
            except Exception:
                devices = flashes = circuits = projects = 0
                last_dev = None
            conn.close()

            step(f"SQLite  ({_fmt_size(paths['sql_db'])})")
            info(f"Hechos:       {facts}")
            info(f"Mensajes:     {msgs}")
            info(f"Dispositivos: {devices}")
            info(f"Flashes:      {flashes}")
            info(f"Circuitos:    {circuits}")
            info(f"Biblioteca:   {projects} proyectos")
            if last_dev:
                info(f"Último device: {last_dev[0]} ({last_dev[1][:10]})")
        except Exception as e:
            warn(f"No pude leer SQLite: {e}")
    else:
        warn(f"SQLite no encontrada en {paths['sql_db']}")

    # Grafo
    if paths["graph_db"].exists():
        try:
            g = json.loads(paths["graph_db"].read_text(encoding="utf-8"))
            step(f"Grafo  ({_fmt_size(paths['graph_db'])})")
            info(f"Nodos: {len(g.get('nodes', []))} | Aristas: {len(g.get('edges', []))}")
        except Exception:
            warn("No pude leer el grafo")
    else:
        warn("graph_memory.json no encontrado")

    # Vector DB
    if paths["vector_db"].exists():
        files = list(paths["vector_db"].rglob("*"))
        total = sum(f.stat().st_size for f in files if f.is_file())
        step("Vector DB")
        info(f"{total // 1024}KB — {len(files)} archivos")
        ok("Qdrant local disponible")
    else:
        warn("Vector DB no encontrada")

    # Backups
    backups = sorted(Path(".").glob("stratum_backup_*.zip"), reverse=True)
    if backups:
        step("Backups disponibles")
        for b in backups[:5]:
            info(f"{b.name} ({_fmt_size(b)})")

    print()
    return 0


# =============================================================================
# EXPORT
# =============================================================================

def cmd_export(output_path: str | None) -> int:
    import json
    import zipfile
    import sqlite3
    from datetime import datetime, timezone
    from pathlib import Path

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    paths = _get_paths()
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(output_path) if output_path else Path(f"stratum_backup_{ts}.zip")

    step("Exportando memoria de Stratum...")

    manifest = {
        "stratum_backup": True,
        "version":        "1.0",
        "created_at":     datetime.now(timezone.utc).isoformat(),
        "hostname":       _safe_hostname(),
        "contents":       [],
    }

    with zipfile.ZipFile(out_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        if paths["sql_db"].exists():
            zf.write(paths["sql_db"], "stratum_backup/memory.db")
            try:
                conn    = sqlite3.connect(paths["sql_db"])
                facts   = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
                msgs    = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
                try:
                    devices  = conn.execute("SELECT COUNT(*) FROM hardware_devices").fetchone()[0]
                    flashes  = conn.execute("SELECT COUNT(*) FROM firmware_history").fetchone()[0]
                    circuits = conn.execute("SELECT COUNT(*) FROM circuit_context").fetchone()[0]
                except Exception:
                    devices = flashes = circuits = 0
                conn.close()
                manifest["stats"] = {"facts": facts, "messages": msgs,
                                     "devices": devices, "flashes": flashes,
                                     "circuits": circuits}
                manifest["contents"].append("memory.db")
                ok(f"SQLite — {facts} hechos, {msgs} mensajes, {devices} dispositivos")
            except Exception as e:
                warn(f"No pude leer stats de SQLite: {e}")
        else:
            warn(f"SQLite no encontrada en {paths['sql_db']}")

        if paths["graph_db"].exists():
            zf.write(paths["graph_db"], "stratum_backup/graph_memory.json")
            manifest["contents"].append("graph_memory.json")
            ok(f"Grafo exportado ({_fmt_size(paths['graph_db'])})")

        if paths["vector_db"].exists() and any(paths["vector_db"].iterdir()):
            count = _zip_dir(zf, paths["vector_db"], "stratum_backup/vector_db")
            manifest["contents"].append(f"vector_db/ ({count} archivos)")
            ok(f"Vector DB exportada ({count} archivos)")

        if paths["knowledge"].exists():
            count = _zip_dir(zf, paths["knowledge"], "stratum_backup/knowledge")
            if count:
                manifest["contents"].append(f"knowledge/ ({count} archivos)")
                ok(f"Knowledge base exportada ({count} archivos)")

        if paths["env"].exists():
            _export_env_sanitized(zf, paths["env"])
            manifest["contents"].append(".env.template")

        zf.writestr("stratum_backup/manifest.json",
                    json.dumps(manifest, indent=2, ensure_ascii=False))

    size_mb = out_file.stat().st_size / (1024 * 1024)
    ok(f"Backup creado: {_c(str(out_file), 96)} ({size_mb:.1f}MB)")
    print()
    return 0


def _export_env_sanitized(zf, env_path):
    import zipfile
    sensitive = {"api_key", "token", "secret", "password", "passwd"}
    lines = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, _ = line.partition("=")
            if any(s in key.lower() for s in sensitive):
                lines.append(f"{key}=<REDACTED>")
            else:
                lines.append(line)
        else:
            lines.append(line)
    zf.writestr("stratum_backup/.env.template", "\n".join(lines))


# =============================================================================
# IMPORT
# =============================================================================

def cmd_import(zip_path: str, merge: bool) -> int:
    import json
    import zipfile
    import sqlite3
    import tempfile
    from pathlib import Path

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    zip_file = Path(zip_path)
    if not zip_file.exists():
        err(f"Archivo no encontrado: {zip_path}")
        return 1
    if not zipfile.is_zipfile(zip_file):
        err(f"El archivo no es un ZIP válido")
        return 1

    step(f"Importando backup: {zip_path}")

    with zipfile.ZipFile(zip_file, "r") as zf:
        if "stratum_backup/manifest.json" not in zf.namelist():
            err("Este ZIP no parece ser un backup de Stratum (falta manifest.json)")
            return 1

        manifest = json.loads(zf.read("stratum_backup/manifest.json"))
        if not manifest.get("stratum_backup"):
            err("manifest.json inválido")
            return 1

        stats = manifest.get("stats", {})
        info(f"Backup creado: {manifest.get('created_at', '?')}")
        info(f"Host origen:   {manifest.get('hostname', '?')}")
        if stats:
            info(f"Contenido:     {stats.get('facts',0)} hechos, "
                 f"{stats.get('messages',0)} mensajes, "
                 f"{stats.get('devices',0)} dispositivos")

        mode = "fusión (--merge)" if merge else "sobreescritura"
        print(f"\n  Modo: {_c(mode, 93)}")

        if not merge:
            confirm = input(f"\n  {_c('¿Sobreescribir la memoria actual? [s/N]:', 93)} ").strip().lower()
            if confirm not in ("s", "si", "yes", "y"):
                warn("Importación cancelada.")
                return 0

        paths = _get_paths()

        if "stratum_backup/memory.db" in zf.namelist():
            paths["sql_db"].parent.mkdir(parents=True, exist_ok=True)
            if not merge:
                paths["sql_db"].write_bytes(zf.read("stratum_backup/memory.db"))
                ok(f"SQLite restaurada")
            else:
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp.write(zf.read("stratum_backup/memory.db"))
                    tmp_path = tmp.name
                try:
                    src = sqlite3.connect(tmp_path)
                    dst = sqlite3.connect(paths["sql_db"])
                    facts = src.execute("SELECT key, value FROM facts").fetchall()
                    dst.executemany("INSERT OR IGNORE INTO facts (key, value) VALUES (?,?)", facts)
                    convs = src.execute("SELECT role, content, timestamp FROM conversations").fetchall()
                    dst.executemany(
                        "INSERT OR IGNORE INTO conversations (role, content, timestamp) VALUES (?,?,?)",
                        convs
                    )
                    for tbl, cols in [
                        ("hardware_devices",
                         "device_name, port, fqbn, platform, first_seen, last_seen"),
                        ("firmware_history",
                         "device_name, task, code, filename, success, serial_out, timestamp, notes"),
                        ("circuit_context",
                         "device_name, project_name, description, components, connections, power, notes, version, updated_at"),
                    ]:
                        try:
                            rows = src.execute(f"SELECT {cols} FROM {tbl}").fetchall()
                            placeholders = ",".join("?" * len(cols.split(",")))
                            dst.executemany(
                                f"INSERT OR IGNORE INTO {tbl} ({cols}) VALUES ({placeholders})",
                                rows
                            )
                        except Exception:
                            pass
                    dst.commit()
                    src.close()
                    dst.close()
                    ok(f"SQLite fusionada — {len(facts)} hechos + {len(convs)} mensajes importados")
                finally:
                    os.unlink(tmp_path)

        if "stratum_backup/graph_memory.json" in zf.namelist():
            paths["graph_db"].parent.mkdir(parents=True, exist_ok=True)
            if not merge or not paths["graph_db"].exists():
                paths["graph_db"].write_bytes(zf.read("stratum_backup/graph_memory.json"))
                ok("Grafo restaurado")
            else:
                try:
                    imported = json.loads(zf.read("stratum_backup/graph_memory.json"))
                    existing = json.loads(paths["graph_db"].read_text(encoding="utf-8"))
                    existing_nodes = {n["id"] for n in existing.get("nodes", [])}
                    existing_edges = {
                        (e["source"], e["target"], e.get("predicate", ""))
                        for e in existing.get("edges", [])
                    }
                    new_nodes = [n for n in imported.get("nodes", []) if n["id"] not in existing_nodes]
                    new_edges = [
                        e for e in imported.get("edges", [])
                        if (e["source"], e["target"], e.get("predicate", "")) not in existing_edges
                    ]
                    existing["nodes"] = existing.get("nodes", []) + new_nodes
                    existing["edges"] = existing.get("edges", []) + new_edges
                    paths["graph_db"].write_text(
                        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    ok(f"Grafo fusionado — +{len(new_nodes)} nodos, +{len(new_edges)} aristas")
                except Exception as e:
                    warn(f"No pude fusionar el grafo, sobreescribiendo: {e}")
                    paths["graph_db"].write_bytes(zf.read("stratum_backup/graph_memory.json"))

        vector_files = [n for n in zf.namelist() if n.startswith("stratum_backup/vector_db/")]
        if vector_files:
            _unzip_dir(zf, vector_files, "stratum_backup/vector_db/", paths["vector_db"], merge)
            ok(f"Vector DB importada ({len(vector_files)} archivos)")

        knowledge_files = [n for n in zf.namelist() if n.startswith("stratum_backup/knowledge/")]
        if knowledge_files:
            _unzip_dir(zf, knowledge_files, "stratum_backup/knowledge/", paths["knowledge"], merge)
            ok(f"Knowledge base importada ({len(knowledge_files)} archivos)")

    ok("Importación completa. Reiniciá Stratum para aplicar los cambios.")
    print()
    return 0


# =============================================================================
# RESET
# =============================================================================

def cmd_reset(confirm_flag: bool) -> int:
    import shutil
    from datetime import datetime

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    step("Reset de memoria")

    if not confirm_flag:
        err("Operación peligrosa. Usá: python run.py reset --confirm")
        return 1

    print(f"\n  {_c('ADVERTENCIA: Esto borrará TODA la memoria de Stratum.', 91)}")
    typed = input(f"  Escribí {_c('BORRAR TODO', 93)} para confirmar: ").strip()
    if typed != "BORRAR TODO":
        warn("Reset cancelado.")
        return 0

    paths = _get_paths()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    auto_bkp = f"stratum_pre_reset_{ts}.zip"
    info(f"Creando backup automático: {auto_bkp}")
    cmd_export(auto_bkp)

    if paths["sql_db"].exists():
        paths["sql_db"].unlink()
        ok("SQLite eliminada")
    if paths["graph_db"].exists():
        paths["graph_db"].unlink()
        ok("Grafo eliminado")
    if paths["vector_db"].exists():
        shutil.rmtree(paths["vector_db"])
        ok("Vector DB eliminada")

    ok(f"Reset completo. Backup guardado en {auto_bkp}")
    info("Reiniciá Stratum para inicializar las DBs desde cero.")
    print()
    return 0


# =============================================================================
# UTILS COMPARTIDAS
# =============================================================================

def _get_paths() -> dict:
    from pathlib import Path
    return {
        "sql_db":    Path(os.getenv("MEMORY_DB_PATH", "./database/memory.db")),
        "vector_db": Path(os.getenv("VECTOR_DB_PATH", "./memory_db")),
        "graph_db":  Path(os.getenv("GRAPH_DB_PATH",  "./database/graph_memory.json")),
        "knowledge": Path("./agent_files/knowledge"),
        "env":       Path(".env"),
    }


def _zip_dir(zf, src, zip_prefix: str) -> int:
    import zipfile
    count = 0
    for f in src.rglob("*"):
        if f.is_file():
            zf.write(f, f"{zip_prefix}/{f.relative_to(src)}")
            count += 1
    return count


def _unzip_dir(zf, files, zip_prefix, target, merge):
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        rel = name[len(zip_prefix):]
        if not rel:
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not merge or not dest.exists():
            dest.write_bytes(zf.read(name))


def _safe_hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"


def _fmt_size(path) -> str:
    from pathlib import Path
    p = Path(path)
    size = p.stat().st_size if p.is_file() else sum(
        f.stat().st_size for f in p.rglob("*") if f.is_file()
    )
    if size < 1024:         return f"{size}B"
    if size < 1024 * 1024:  return f"{size // 1024}KB"
    return f"{size / (1024*1024):.1f}MB"


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
        cmd_setup(no_ollama=args.no_ollama)

    elif args.command == "status":
        sys.exit(cmd_status())

    elif args.command == "export":
        sys.exit(cmd_export(getattr(args, "output", None)))

    elif args.command == "import":
        sys.exit(cmd_import(args.file, getattr(args, "merge", False)))

    elif args.command == "reset":
        sys.exit(cmd_reset(getattr(args, "confirm", False)))

    elif args.command == "bridge":
        from tools.hardware_bridge_client import run_bridge
        import asyncio
        asyncio.run(run_bridge(args.url, args.token))


if __name__ == "__main__":
    main()
