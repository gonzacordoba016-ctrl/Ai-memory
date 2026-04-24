# cli/status.py — comando `python run.py status`

import json
import sqlite3
from pathlib import Path

from cli.utils import _c, ok, warn, info, step, _get_paths, _fmt_size


def cmd_status() -> int:
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
