# cli/utils.py — helpers compartidos de consola y rutas

import os
import sys
from pathlib import Path
from database import get_db_path

_WIN = sys.platform == "win32"


def _c(text, code):
    return text if _WIN else f"\033[{code}m{text}\033[0m"


def ok(msg):   print(f"  {_c('OK', 92)} {msg}")
def warn(msg): print(f"  {_c('!', 93)} {msg}")
def err(msg):  print(f"  {_c('X', 91)} {msg}")
def info(msg): print(f"  {_c('->', 96)} {msg}")
def step(msg): print(f"\n{_c(msg, 1)}")


def _get_paths() -> dict:
    return {
        "sql_db":    Path(get_db_path("memory.db")),
        "vector_db": Path(os.getenv("VECTOR_DB_PATH", "./memory_db")),
        "graph_db":  Path(os.getenv("GRAPH_DB_PATH",  "./database/graph_memory.json")),
        "knowledge": Path("./agent_files/knowledge"),
        "env":       Path(".env"),
    }


def _zip_dir(zf, src, zip_prefix: str) -> int:
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
    p = Path(path)
    size = p.stat().st_size if p.is_file() else sum(
        f.stat().st_size for f in p.rglob("*") if f.is_file()
    )
    if size < 1024:         return f"{size}B"
    if size < 1024 * 1024:  return f"{size // 1024}KB"
    return f"{size / (1024*1024):.1f}MB"
