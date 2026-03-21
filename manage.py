# manage.py
#
# Herramienta CLI para gestión de memoria de Stratum.
# Independiente del servidor — se puede correr con el servidor apagado.
#
# Uso:
#   python manage.py export                          → stratum_backup_YYYYMMDD_HHMMSS.zip
#   python manage.py export --output mi_backup.zip
#   python manage.py import stratum_backup.zip
#   python manage.py import stratum_backup.zip --merge   → fusiona sin sobreescribir
#   python manage.py status                          → resumen del estado actual
#   python manage.py reset --confirm                 → borra toda la memoria

import os
import sys
import json
import shutil
import sqlite3
import zipfile
import argparse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# ── Colores CLI ───────────────────────────────────────────────────────────────
G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
C = "\033[96m"
B = "\033[1m"
X = "\033[0m"

def ok(msg):   print(f"  {G}✓{X} {msg}")
def warn(msg): print(f"  {Y}!{X} {msg}")
def err(msg):  print(f"  {R}✗{X} {msg}")
def info(msg): print(f"  {C}→{X} {msg}")
def step(msg): print(f"\n{B}{msg}{X}")


# ── Rutas ─────────────────────────────────────────────────────────────────────

def _get_paths() -> dict:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return {
        "sql_db":    Path(os.getenv("MEMORY_DB_PATH", "./database/memory.db")),
        "vector_db": Path(os.getenv("VECTOR_DB_PATH", "./memory_db")),
        "graph_db":  Path(os.getenv("GRAPH_DB_PATH",  "./database/graph_memory.json")),
        "knowledge": Path("./agent_files/knowledge"),
        "env":       Path(".env"),
    }


# =============================================================================
# EXPORT
# =============================================================================

def cmd_export(output_path: str | None) -> int:
    step("Exportando memoria de Stratum...")

    paths    = _get_paths()
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(output_path) if output_path else Path(f"stratum_backup_{ts}.zip")

    manifest = {
        "stratum_backup": True,
        "version":        "1.0",
        "created_at":     datetime.now(timezone.utc).isoformat(),
        "hostname":       _safe_hostname(),
        "contents":       [],
    }

    with zipfile.ZipFile(out_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        # 1. SQLite — memoria principal
        if paths["sql_db"].exists():
            _export_sqlite(zf, paths["sql_db"], manifest)
        else:
            warn(f"SQLite no encontrada en {paths['sql_db']}")

        # 2. Grafo NetworkX
        if paths["graph_db"].exists():
            zf.write(paths["graph_db"], "stratum_backup/graph_memory.json")
            manifest["contents"].append("graph_memory.json")
            ok(f"Grafo exportado ({paths['graph_db'].stat().st_size // 1024}KB)")
        else:
            warn("graph_memory.json no encontrado")

        # 3. Vector DB (directorio Qdrant local)
        if paths["vector_db"].exists() and any(paths["vector_db"].iterdir()):
            count = _export_directory(zf, paths["vector_db"], "stratum_backup/vector_db")
            manifest["contents"].append(f"vector_db/ ({count} archivos)")
            ok(f"Vector DB exportada ({count} archivos)")
        else:
            warn("Vector DB no encontrada o vacía")

        # 4. Knowledge files
        if paths["knowledge"].exists():
            count = _export_directory(zf, paths["knowledge"], "stratum_backup/knowledge")
            if count:
                manifest["contents"].append(f"knowledge/ ({count} archivos)")
                ok(f"Knowledge base exportada ({count} archivos)")

        # 5. .env (sin valores sensibles — solo claves)
        if paths["env"].exists():
            _export_env_sanitized(zf, paths["env"])
            manifest["contents"].append(".env.template")

        # 6. Manifest
        zf.writestr("stratum_backup/manifest.json",
                    json.dumps(manifest, indent=2, ensure_ascii=False))

    size_mb = out_file.stat().st_size / (1024 * 1024)
    ok(f"Backup creado: {C}{out_file}{X} ({size_mb:.1f}MB)")
    print()
    return 0


def _export_sqlite(zf: zipfile.ZipFile, db_path: Path, manifest: dict):
    """Exporta SQLite y agrega un resumen legible al manifest."""
    zf.write(db_path, "stratum_backup/memory.db")

    # Leer stats para el manifest
    try:
        conn  = sqlite3.connect(db_path)
        facts = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        msgs  = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        try:
            devices = conn.execute("SELECT COUNT(*) FROM hardware_devices").fetchone()[0]
            flashes = conn.execute("SELECT COUNT(*) FROM firmware_history").fetchone()[0]
            circuits = conn.execute("SELECT COUNT(*) FROM circuit_context").fetchone()[0]
        except Exception:
            devices = flashes = circuits = 0
        conn.close()

        manifest["stats"] = {
            "facts":     facts,
            "messages":  msgs,
            "devices":   devices,
            "flashes":   flashes,
            "circuits":  circuits,
        }
        manifest["contents"].append("memory.db")
        ok(f"SQLite exportada — {facts} hechos, {msgs} mensajes, {devices} dispositivos, {flashes} flashes")
    except Exception as e:
        warn(f"No pude leer stats de SQLite: {e}")
        manifest["contents"].append("memory.db")


def _export_directory(zf: zipfile.ZipFile, src: Path, zip_prefix: str) -> int:
    count = 0
    for file in src.rglob("*"):
        if file.is_file():
            zf.write(file, f"{zip_prefix}/{file.relative_to(src)}")
            count += 1
    return count


def _export_env_sanitized(zf: zipfile.ZipFile, env_path: Path):
    """Exporta el .env reemplazando valores sensibles con placeholders."""
    sensitive = {"api_key", "token", "secret", "password", "passwd"}
    lines = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            if any(s in key.lower() for s in sensitive):
                lines.append(f"{key}=<REDACTED>")
            else:
                lines.append(line)
        else:
            lines.append(line)
    zf.writestr("stratum_backup/.env.template", "\n".join(lines))


def _safe_hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"


# =============================================================================
# IMPORT
# =============================================================================

def cmd_import(zip_path: str, merge: bool) -> int:
    step(f"Importando backup: {zip_path}")

    zip_file = Path(zip_path)
    if not zip_file.exists():
        err(f"Archivo no encontrado: {zip_path}")
        return 1

    if not zipfile.is_zipfile(zip_file):
        err(f"El archivo no es un ZIP válido: {zip_path}")
        return 1

    with zipfile.ZipFile(zip_file, "r") as zf:
        # Validar que es un backup de Stratum
        if "stratum_backup/manifest.json" not in zf.namelist():
            err("Este ZIP no parece ser un backup de Stratum (falta manifest.json)")
            return 1

        manifest = json.loads(zf.read("stratum_backup/manifest.json"))
        if not manifest.get("stratum_backup"):
            err("manifest.json inválido")
            return 1

        created = manifest.get("created_at", "desconocido")
        host    = manifest.get("hostname", "desconocido")
        stats   = manifest.get("stats", {})

        info(f"Backup creado: {created}")
        info(f"Host origen:   {host}")
        if stats:
            info(f"Contenido:     {stats.get('facts',0)} hechos, "
                 f"{stats.get('messages',0)} mensajes, "
                 f"{stats.get('devices',0)} dispositivos, "
                 f"{stats.get('flashes',0)} flashes")

        mode = "fusión (--merge)" if merge else "sobreescritura"
        print(f"\n  Modo: {Y}{mode}{X}")

        if not merge:
            confirm = input(f"\n  {Y}¿Sobreescribir la memoria actual? [s/N]:{X} ").strip().lower()
            if confirm not in ("s", "si", "yes", "y"):
                warn("Importación cancelada.")
                return 0

        paths = _get_paths()

        # 1. SQLite
        if "stratum_backup/memory.db" in zf.namelist():
            _import_sqlite(zf, paths["sql_db"], merge)

        # 2. Grafo
        if "stratum_backup/graph_memory.json" in zf.namelist():
            _import_graph(zf, paths["graph_db"], merge)

        # 3. Vector DB
        vector_files = [n for n in zf.namelist() if n.startswith("stratum_backup/vector_db/")]
        if vector_files:
            _import_directory(zf, vector_files, "stratum_backup/vector_db/", paths["vector_db"], merge)
            ok(f"Vector DB importada ({len(vector_files)} archivos)")

        # 4. Knowledge
        knowledge_files = [n for n in zf.namelist() if n.startswith("stratum_backup/knowledge/")]
        if knowledge_files:
            _import_directory(zf, knowledge_files, "stratum_backup/knowledge/", paths["knowledge"], merge)
            ok(f"Knowledge base importada ({len(knowledge_files)} archivos)")

    ok("Importación completa. Reiniciá Stratum para aplicar los cambios.")
    print()
    return 0


def _import_sqlite(zf: zipfile.ZipFile, target: Path, merge: bool):
    target.parent.mkdir(parents=True, exist_ok=True)

    if not merge:
        # Sobreescritura directa
        target.write_bytes(zf.read("stratum_backup/memory.db"))
        ok(f"SQLite restaurada en {target}")
        return

    # Modo merge: fusionar facts, conversations y hardware sin duplicar
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(zf.read("stratum_backup/memory.db"))
        tmp_path = tmp.name

    try:
        src_conn = sqlite3.connect(tmp_path)
        dst_conn = sqlite3.connect(target)

        # Merge facts (INSERT OR IGNORE — no sobreescribe hechos existentes)
        facts = src_conn.execute("SELECT key, value FROM facts").fetchall()
        dst_conn.executemany(
            "INSERT OR IGNORE INTO facts (key, value) VALUES (?, ?)", facts
        )

        # Merge conversations (solo las que no existen por timestamp+content)
        convs = src_conn.execute(
            "SELECT role, content, timestamp FROM conversations"
        ).fetchall()
        dst_conn.executemany(
            "INSERT OR IGNORE INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
            convs
        )

        # Merge hardware_devices
        try:
            devices = src_conn.execute(
                "SELECT device_name, port, fqbn, platform, first_seen, last_seen FROM hardware_devices"
            ).fetchall()
            dst_conn.executemany(
                "INSERT OR IGNORE INTO hardware_devices (device_name, port, fqbn, platform, first_seen, last_seen) VALUES (?,?,?,?,?,?)",
                devices
            )
        except Exception:
            pass

        # Merge firmware_history
        try:
            firmware = src_conn.execute(
                "SELECT device_name, task, code, filename, success, serial_out, timestamp, notes FROM firmware_history"
            ).fetchall()
            dst_conn.executemany(
                "INSERT OR IGNORE INTO firmware_history (device_name, task, code, filename, success, serial_out, timestamp, notes) VALUES (?,?,?,?,?,?,?,?)",
                firmware
            )
        except Exception:
            pass

        # Merge circuit_context (INSERT OR IGNORE — no pisa circuitos existentes)
        try:
            circuits = src_conn.execute(
                "SELECT device_name, project_name, description, components, connections, power, notes, version, updated_at FROM circuit_context"
            ).fetchall()
            dst_conn.executemany(
                "INSERT OR IGNORE INTO circuit_context (device_name, project_name, description, components, connections, power, notes, version, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                circuits
            )
        except Exception:
            pass

        dst_conn.commit()
        src_conn.close()
        dst_conn.close()

        merged = len(facts) + len(convs)
        ok(f"SQLite fusionada — {len(facts)} hechos + {len(convs)} mensajes importados")

    finally:
        os.unlink(tmp_path)


def _import_graph(zf: zipfile.ZipFile, target: Path, merge: bool):
    target.parent.mkdir(parents=True, exist_ok=True)
    imported = json.loads(zf.read("stratum_backup/graph_memory.json"))

    if not merge or not target.exists():
        target.write_bytes(zf.read("stratum_backup/graph_memory.json"))
        ok(f"Grafo restaurado ({len(imported.get('nodes', []))} nodos)")
        return

    # Merge: combinar nodos y aristas sin duplicar
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))

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

        target.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        ok(f"Grafo fusionado — +{len(new_nodes)} nodos, +{len(new_edges)} aristas")

    except Exception as e:
        warn(f"No pude fusionar el grafo, sobreescribiendo: {e}")
        target.write_bytes(zf.read("stratum_backup/graph_memory.json"))


def _import_directory(zf: zipfile.ZipFile, files: list, zip_prefix: str, target: Path, merge: bool):
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        rel = name[len(zip_prefix):]
        if not rel:
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not merge or not dest.exists():
            dest.write_bytes(zf.read(name))


# =============================================================================
# STATUS
# =============================================================================

def cmd_status() -> int:
    step("Estado actual de Stratum")

    paths = _get_paths()

    # SQLite
    if paths["sql_db"].exists():
        try:
            conn    = sqlite3.connect(paths["sql_db"])
            facts   = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            msgs    = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            try:
                devices  = conn.execute("SELECT COUNT(*) FROM hardware_devices").fetchone()[0]
                flashes  = conn.execute("SELECT COUNT(*) FROM firmware_history").fetchone()[0]
                circuits = conn.execute("SELECT COUNT(*) FROM circuit_context").fetchone()[0]
                projects = conn.execute("SELECT COUNT(*) FROM project_library").fetchone()[0]

                # Último dispositivo
                last_dev = conn.execute(
                    "SELECT device_name, last_seen FROM hardware_devices ORDER BY last_seen DESC LIMIT 1"
                ).fetchone()
            except Exception:
                devices = flashes = circuits = projects = 0
                last_dev = None
            conn.close()

            print(f"\n  {B}SQLite{X} ({_fmt_size(paths['sql_db'])})")
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
            g     = json.loads(paths["graph_db"].read_text(encoding="utf-8"))
            nodes = len(g.get("nodes", []))
            edges = len(g.get("edges", []))
            print(f"\n  {B}Grafo{X} ({_fmt_size(paths['graph_db'])})")
            info(f"Nodos: {nodes} | Aristas: {edges}")
        except Exception:
            warn("No pude leer el grafo")
    else:
        warn("graph_memory.json no encontrado")

    # Vector DB
    if paths["vector_db"].exists():
        files = list(paths["vector_db"].rglob("*"))
        total = sum(f.stat().st_size for f in files if f.is_file())
        print(f"\n  {B}Vector DB{X} ({total // 1024}KB, {len(files)} archivos)")
        ok("Qdrant local disponible")
    else:
        warn("Vector DB no encontrada")

    # Backups existentes
    backups = sorted(Path(".").glob("stratum_backup_*.zip"), reverse=True)
    if backups:
        print(f"\n  {B}Backups disponibles{X}")
        for b in backups[:5]:
            info(f"{b.name} ({_fmt_size(b)})")
    else:
        warn("No hay backups locales")

    print()
    return 0


# =============================================================================
# RESET
# =============================================================================

def cmd_reset(confirm_flag: bool) -> int:
    step("Reset de memoria")

    if not confirm_flag:
        err("Operación peligrosa. Usá: python manage.py reset --confirm")
        return 1

    print(f"\n  {R}{B}ADVERTENCIA: Esto borrará TODA la memoria de Stratum.{X}")
    typed = input(f"  Escribí {Y}BORRAR TODO{X} para confirmar: ").strip()
    if typed != "BORRAR TODO":
        warn("Reset cancelado.")
        return 0

    paths = _get_paths()

    # Hacer backup automático antes de borrar
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    auto_bkp = f"stratum_pre_reset_{ts}.zip"
    info(f"Creando backup automático: {auto_bkp}")
    cmd_export(auto_bkp)

    # Borrar SQLite
    if paths["sql_db"].exists():
        paths["sql_db"].unlink()
        ok("SQLite eliminada")

    # Borrar grafo
    if paths["graph_db"].exists():
        paths["graph_db"].unlink()
        ok("Grafo eliminado")

    # Borrar Vector DB
    if paths["vector_db"].exists():
        shutil.rmtree(paths["vector_db"])
        ok("Vector DB eliminada")

    ok(f"Reset completo. Backup guardado en {auto_bkp}")
    info("Reiniciá Stratum para inicializar las DBs desde cero.")
    print()
    return 0


# =============================================================================
# UTILS
# =============================================================================

def _fmt_size(path: Path) -> str:
    size = path.stat().st_size if path.is_file() else sum(
        f.stat().st_size for f in path.rglob("*") if f.is_file()
    )
    if size < 1024:        return f"{size}B"
    if size < 1024 * 1024: return f"{size // 1024}KB"
    return f"{size / (1024*1024):.1f}MB"


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Stratum — Gestión de memoria",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python manage.py export
  python manage.py export --output mi_backup.zip
  python manage.py import stratum_backup_20260101_120000.zip
  python manage.py import stratum_backup_20260101_120000.zip --merge
  python manage.py status
  python manage.py reset --confirm
"""
    )

    sub = parser.add_subparsers(dest="command")

    # export
    p_export = sub.add_parser("export", help="Exportar memoria a ZIP")
    p_export.add_argument("--output", "-o", help="Nombre del archivo de salida")

    # import
    p_import = sub.add_parser("import", help="Importar memoria desde ZIP")
    p_import.add_argument("file", help="Archivo ZIP de backup")
    p_import.add_argument("--merge", action="store_true",
                          help="Fusionar con memoria existente (no sobreescribir)")

    # status
    sub.add_parser("status", help="Ver estado actual de la memoria")

    # reset
    p_reset = sub.add_parser("reset", help="Borrar toda la memoria")
    p_reset.add_argument("--confirm", action="store_true",
                         help="Confirmar el reset (obligatorio)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    print(f"\n{C}{B}STRATUM — Memory Manager{X}")

    if args.command == "export":
        return cmd_export(getattr(args, "output", None))
    if args.command == "import":
        return cmd_import(args.file, getattr(args, "merge", False))
    if args.command == "status":
        return cmd_status()
    if args.command == "reset":
        return cmd_reset(getattr(args, "confirm", False))

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())