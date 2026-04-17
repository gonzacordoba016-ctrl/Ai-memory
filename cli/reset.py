# cli/reset.py — comando `python run.py reset`

import shutil
from datetime import datetime

from cli.utils import _c, ok, warn, err, info, step, _get_paths


def cmd_reset(confirm_flag: bool) -> int:
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

    from cli.backup import cmd_export
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
