# cli/setup.py — comando `python run.py setup`

import subprocess
import shutil
import sys
from pathlib import Path

from cli.utils import _c, ok, warn, err, info, step


def cmd_setup(no_ollama: bool) -> None:
    """Instala dependencias, configura arduino-cli y crea el .env si no existe."""
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
