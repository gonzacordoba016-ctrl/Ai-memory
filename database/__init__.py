import os

DB_BASE = os.environ.get("DATA_DIR", "/data/database").strip('"').strip("'")

def get_db_path(name: str) -> str:
    os.makedirs(DB_BASE, exist_ok=True)
    return os.path.join(DB_BASE, name)
