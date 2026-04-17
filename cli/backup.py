# cli/backup.py — comandos `python run.py export` y `python run.py import`

import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cli.utils import _c, ok, warn, err, info, step, _get_paths, _fmt_size, _zip_dir, _unzip_dir, _safe_hostname


def _export_env_sanitized(zf, env_path):
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


def cmd_export(output_path: str | None) -> int:
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


def cmd_import(zip_path: str, merge: bool) -> int:
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
        err("El archivo no es un ZIP válido")
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
                ok("SQLite restaurada")
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
