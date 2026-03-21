#!/usr/bin/env python3
"""
Stratum — Hardware Memory Engine
Instalador automático

Uso:
    python install.py              # instalación completa
    python install.py --no-ollama  # sin instalar Ollama
    python install.py --dev        # modo desarrollo (sin abrir browser)
"""

import os
import sys
import subprocess
import platform
import shutil
import time
import argparse
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────
REQUIRED_PYTHON = (3, 10)
OLLAMA_MODEL    = "qwen2.5:7b"
DEFAULT_PORT    = 8000
REPO_URL        = "https://github.com/tuusuario/stratum"  # cambiar cuando publiques

COLORS = {
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "red":    "\033[91m",
    "cyan":   "\033[96m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}

def c(text, color):
    if platform.system() == "Windows":
        return text  # Windows no siempre soporta ANSI sin configuración
    return f"{COLORS[color]}{text}{COLORS['reset']}"

def log(msg, level="info"):
    prefix = {
        "info":    c("  →", "cyan"),
        "success": c("  ✓", "green"),
        "warning": c("  !", "yellow"),
        "error":   c("  ✗", "red"),
        "step":    c("\n▶", "bold"),
    }.get(level, "  ")
    print(f"{prefix} {msg}")

def run(cmd, check=True, capture=False, shell=False):
    """Ejecuta un comando y retorna el resultado."""
    try:
        result = subprocess.run(
            cmd if shell else cmd.split() if isinstance(cmd, str) else cmd,
            check=check,
            capture_output=capture,
            text=True,
            shell=shell,
        )
        return result
    except subprocess.CalledProcessError as e:
        return e

def run_output(cmd):
    """Ejecuta y retorna stdout."""
    try:
        result = subprocess.run(
            cmd if isinstance(cmd, list) else cmd.split(),
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return ""


# ── CHECKS ────────────────────────────────────────────────

def check_python():
    log("Verificando Python...", "step")
    v = sys.version_info
    if v < REQUIRED_PYTHON:
        log(f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ requerido. Tenés {v.major}.{v.minor}", "error")
        sys.exit(1)
    log(f"Python {v.major}.{v.minor}.{v.micro} ✓", "success")


def check_pip():
    log("Verificando pip...", "step")
    result = run_output([sys.executable, "-m", "pip", "--version"])
    if not result:
        log("pip no encontrado", "error")
        sys.exit(1)
    log(f"pip disponible ✓", "success")


def install_dependencies():
    log("Instalando dependencias Python...", "step")

    requirements = Path("requirements.txt")
    if not requirements.exists():
        log("requirements.txt no encontrado — creando uno básico", "warning")
        requirements.write_text(
            "fastapi==0.115.0\nuvicorn[standard]==0.30.0\npython-dotenv==1.0.1\n"
            "requests==2.32.3\nqdrant-client==1.9.1\nsentence-transformers==3.0.1\n"
            "numpy>=1.24.0\nnetworkx==3.3\nduckduckgo-search==6.2.13\n"
            "python-multipart==0.0.9\npdfplumber==0.11.0\npypdf==4.3.1\n"
            "pyserial==3.5\ntqdm==4.66.4\n"
        )

    result = run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt",
                  "--break-system-packages", "-q"], check=False)
    if hasattr(result, 'returncode') and result.returncode != 0:
        # Intentar sin el flag
        result = run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
                     check=False)

    log("Dependencias instaladas ✓", "success")


def check_ollama(skip=False):
    log("Verificando Ollama...", "step")

    if skip:
        log("Ollama omitido (--no-ollama)", "warning")
        return False

    # Verificar si está instalado
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        log("Ollama no encontrado. Instalando...", "warning")
        _install_ollama()
    else:
        log(f"Ollama encontrado en {ollama_path} ✓", "success")

    # Verificar que el servicio está corriendo
    result = run(["ollama", "list"], check=False, capture=True)
    if hasattr(result, 'returncode') and result.returncode != 0:
        log("Iniciando servicio Ollama...", "info")
        if platform.system() == "Windows":
            subprocess.Popen(["ollama", "serve"],
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(["ollama", "serve"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)

    # Verificar modelo
    models_output = run_output(["ollama", "list"])
    if OLLAMA_MODEL not in models_output:
        log(f"Descargando modelo {OLLAMA_MODEL} (esto puede tardar varios minutos)...", "info")
        log("El modelo pesa ~4.7GB. Podés cancelar con Ctrl+C y continuar después.", "warning")
        result = run(["ollama", "pull", OLLAMA_MODEL], check=False)
        if hasattr(result, 'returncode') and result.returncode == 0:
            log(f"Modelo {OLLAMA_MODEL} descargado ✓", "success")
        else:
            log(f"No se pudo descargar {OLLAMA_MODEL}. Podés descargarlo manualmente con: ollama pull {OLLAMA_MODEL}", "warning")
    else:
        log(f"Modelo {OLLAMA_MODEL} disponible ✓", "success")

    return True


def _install_ollama():
    system = platform.system()
    if system == "Windows":
        log("Descargá Ollama desde: https://ollama.com/download", "warning")
        log("Instalalo y volvé a correr este script.", "warning")
        input("Presioná Enter cuando hayas instalado Ollama...")
    elif system == "Darwin":
        run("brew install ollama", check=False, shell=True)
    else:
        run("curl -fsSL https://ollama.com/install.sh | sh", check=False, shell=True)


def check_arduino_cli():
    log("Verificando arduino-cli...", "step")

    arduino_path = shutil.which("arduino-cli")
    if arduino_path:
        version = run_output(["arduino-cli", "version"])
        log(f"arduino-cli encontrado: {version} ✓", "success")
        _setup_arduino_cli()
        return

    log("arduino-cli no encontrado. Instrucciones de instalación:", "warning")
    system = platform.system()
    if system == "Windows":
        log("  1. Descargá arduino-cli desde: https://arduino.github.io/arduino-cli/latest/installation/", "info")
        log("  2. Extraé arduino-cli.exe en C:\\arduino-cli\\", "info")
        log("  3. Agregá C:\\arduino-cli\\ al PATH", "info")
    elif system == "Darwin":
        log("  brew install arduino-cli", "info")
    else:
        log("  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh", "info")

    log("arduino-cli es necesario para compilar y flashear firmware.", "warning")
    log("Podés instalarlo después y el resto del sistema funciona sin él.", "info")


def _setup_arduino_cli():
    """Inicializa arduino-cli y instala el core de Arduino AVR."""
    log("Configurando arduino-cli...", "info")

    # Init config si no existe
    config_result = run(["arduino-cli", "config", "init"], check=False, capture=True)

    # Update index
    run(["arduino-cli", "core", "update-index"], check=False, capture=True)

    # Instalar arduino:avr si no está
    installed = run_output(["arduino-cli", "core", "list"])
    if "arduino:avr" not in installed:
        log("Instalando core Arduino AVR...", "info")
        run(["arduino-cli", "core", "install", "arduino:avr"], check=False)
        log("Core Arduino AVR instalado ✓", "success")
    else:
        log("Core Arduino AVR ya instalado ✓", "success")


def create_env():
    log("Creando archivo .env...", "step")

    env_path = Path(".env")
    if env_path.exists():
        log(".env ya existe — no se sobreescribe", "info")
        return

    env_content = f"""# Stratum — Hardware Memory Engine
# Configuración generada automáticamente por install.py

# ── LLM ──────────────────────────────────────────────────
LLM_PROVIDER=ollama
OLLAMA_MODEL={OLLAMA_MODEL}
OLLAMA_BASE_URL=http://localhost:11435

# ── MEMORIA ───────────────────────────────────────────────
MEMORY_DB_PATH=./database/memory.db
VECTOR_DB_PATH=./memory_db
VECTOR_COLLECTION=agent_memory
MEMORY_DECAY_RATE=0.01

# ── HARDWARE ──────────────────────────────────────────────
GRAPH_DB_PATH=./database/graph_memory.json

# ── DEBUG ─────────────────────────────────────────────────
DEBUG=true
LOG_LEVEL=INFO
"""
    env_path.write_text(env_content)
    log(".env creado ✓", "success")


def create_directories():
    log("Creando estructura de directorios...", "step")

    dirs = [
        "database",
        "memory_db",
        "agent_files",
        "agent_files/firmware",
        "agent_files/knowledge",
        "api/static",
        "eval",
        "knowledge",
    ]

    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Crear __init__.py donde sean necesarios
    inits = ["database", "knowledge", "agent/agents", "eval"]
    for pkg in inits:
        init = Path(pkg) / "__init__.py"
        if not init.exists():
            init.touch()

    log("Directorios creados ✓", "success")


def verify_installation():
    log("Verificando instalación...", "step")

    checks = []

    # Python packages
    packages = ["fastapi", "uvicorn", "qdrant_client", "sentence_transformers",
                "networkx", "serial", "dotenv"]
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_"))
            checks.append((pkg, True))
        except ImportError:
            checks.append((pkg, False))

    failed = [p for p, ok in checks if not ok]
    if failed:
        log(f"Paquetes faltantes: {', '.join(failed)}", "warning")
        log("Ejecutá: pip install -r requirements.txt", "info")
    else:
        log("Todos los paquetes Python disponibles ✓", "success")

    # Archivos críticos
    critical_files = [
        "main.py",
        "api/server.py",
        "agent/agent_controller.py",
        "core/config.py",
    ]
    for f in critical_files:
        if not Path(f).exists():
            log(f"Archivo faltante: {f}", "warning")

    return len(failed) == 0


def print_banner():
    banner = """
╔══════════════════════════════════════════════════════╗
║                                                      ║
║   STRATUM — Hardware Memory Engine                   ║
║   Instalador v1.0.0                                  ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
"""
    print(c(banner, "cyan"))


def print_summary(port, ollama_ok):
    summary = f"""
╔══════════════════════════════════════════════════════╗
║   Instalación completa                               ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║   Para iniciar Stratum:                              ║
║                                                      ║
║   uvicorn api.server:app --port {port}                ║
║                                                      ║
║   Luego abrí: http://localhost:{port}                 ║
║                                                      ║"""

    if not ollama_ok:
        summary += f"""
║   ⚠  Ollama no está instalado.                       ║
║      Instalalo y descargá el modelo:                 ║
║      ollama pull {OLLAMA_MODEL:<35}║"""

    summary += """
║                                                      ║
╚══════════════════════════════════════════════════════╝
"""
    print(c(summary, "green"))


def launch_server(port, dev_mode):
    if dev_mode:
        log(f"Modo dev: server NO iniciado automáticamente", "info")
        log(f"Inicialo con: uvicorn api.server:app --reload --port {port}", "info")
        return

    log(f"Iniciando servidor en puerto {port}...", "step")
    log("Presioná Ctrl+C para detener", "info")
    time.sleep(1)

    # Abrir browser
    try:
        import webbrowser
        time.sleep(2)
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass

    # Lanzar uvicorn
    os.execvp(sys.executable, [
        sys.executable, "-m", "uvicorn",
        "api.server:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--reload",
    ])


# ── MAIN ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Stratum — Hardware Memory Engine Installer"
    )
    parser.add_argument("--no-ollama", action="store_true",
                        help="Saltar instalación de Ollama")
    parser.add_argument("--dev", action="store_true",
                        help="Modo desarrollo (no inicia el servidor)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Puerto del servidor (default: {DEFAULT_PORT})")
    parser.add_argument("--verify-only", action="store_true",
                        help="Solo verificar la instalación existente")
    args = parser.parse_args()

    print_banner()

    if args.verify_only:
        verify_installation()
        return

    # Pasos de instalación
    check_python()
    check_pip()
    create_directories()
    install_dependencies()
    ollama_ok = check_ollama(skip=args.no_ollama)
    check_arduino_cli()
    create_env()
    ok = verify_installation()

    print_summary(args.port, ollama_ok)

    if ok and not args.dev:
        launch = input("\n¿Iniciar Stratum ahora? [S/n]: ").strip().lower()
        if launch in ("", "s", "y", "si", "yes"):
            launch_server(args.port, args.dev)
    elif args.dev:
        log("Setup completo. Modo dev activo.", "success")


if __name__ == "__main__":
    main()