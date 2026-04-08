#!/usr/bin/env python3
# tools/hardware_bridge_client.py
#
# Cliente del Hardware Bridge — corre en la PC del usuario.
# Se conecta al backend remoto (Railway o local) y ejecuta jobs de hardware
# (detect, compile, flash, serial) usando los recursos locales de la PC.
#
# Uso:
#   python run.py bridge --url https://stratum.up.railway.app --token <token>
#   python run.py bridge --url http://localhost:8000              # test local
#
# Dependencias extra: websockets (ya en requirements.txt)

import asyncio
import json
import os
import sys
import traceback
from datetime import datetime

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    print("ERROR: Falta el paquete 'websockets'. Instalalo con: pip install websockets")
    sys.exit(1)

# ── Logging simple ─────────────────────────────────────────────────────────────

def _log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "●", "WARN": "▲", "ERROR": "✗", "OK": "✓"}.get(level, "·")
    print(f"[{ts}] {prefix} {msg}", flush=True)


# ── Handlers de cada tipo de job ───────────────────────────────────────────────

async def _handle_detect(job: dict) -> dict:
    try:
        from tools.hardware_detector import detect_devices
        devices = await asyncio.to_thread(detect_devices)
        return {"success": True, "devices": devices}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_generate(job: dict) -> dict:
    try:
        from tools.firmware_generator import generate_firmware
        task        = job.get("task", "")
        device_name = job.get("device_name", "")
        circuit_ctx = job.get("circuit_context", {})
        code = await asyncio.to_thread(generate_firmware, task, device_name, circuit_ctx)
        return {"success": True, "code": code}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_compile(job: dict) -> dict:
    try:
        from tools.firmware_flasher import compile_firmware
        code   = job.get("code", "")
        board  = job.get("board", "arduino:avr:uno")
        result = await asyncio.to_thread(compile_firmware, code, board)
        return result  # ya tiene success, hex_path, error, etc.
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_flash(job: dict) -> dict:
    try:
        from tools.firmware_flasher import flash_firmware
        hex_path = job.get("hex_path", "")
        port     = job.get("port", "")
        board    = job.get("board", "arduino:avr:uno")
        result   = await asyncio.to_thread(flash_firmware, hex_path, port, board)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_serial(job: dict) -> dict:
    try:
        from tools.hardware_detector import read_serial
        port     = job.get("port", "")
        baudrate = job.get("baudrate", 9600)
        duration = job.get("duration", 3)
        output   = await asyncio.to_thread(read_serial, port, baudrate, duration)
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_program(job: dict) -> dict:
    """
    Job completo: generate → compile → flash.
    El backend envía task + device context, el bridge ejecuta todo el pipeline.
    """
    try:
        from tools.firmware_generator import generate_firmware
        from tools.firmware_flasher   import compile_firmware, flash_firmware
        from tools.hardware_detector  import detect_devices

        task        = job.get("task", "")
        device_name = job.get("device_name", "")
        circuit_ctx = job.get("circuit_context", {})
        port        = job.get("port", "")
        board       = job.get("board", "arduino:avr:uno")

        _log(f"Generando firmware para: {task[:60]}")
        code = await asyncio.to_thread(generate_firmware, task, device_name, circuit_ctx)

        _log("Compilando firmware...")
        compile_result = await asyncio.to_thread(compile_firmware, code, board)
        if not compile_result.get("success"):
            return {**compile_result, "code": code}

        # Detectar puerto si no se especificó
        if not port:
            _log("Detectando dispositivos...")
            devices = await asyncio.to_thread(detect_devices)
            connected = [d for d in devices if not d.get("_offline")]
            if not connected:
                return {"success": False, "error": "No hay dispositivos conectados", "code": code}
            port = connected[0]["port"]
            _log(f"Usando puerto {port}")

        _log(f"Flasheando en {port}...")
        flash_result = await asyncio.to_thread(flash_firmware, compile_result["hex_path"], port, board)
        return {**flash_result, "code": code, "port": port}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Dispatch de tipos de job
_HANDLERS = {
    "detect":   _handle_detect,
    "generate": _handle_generate,
    "compile":  _handle_compile,
    "flash":    _handle_flash,
    "serial":   _handle_serial,
    "program":  _handle_program,
}


async def _handle_job(job: dict) -> dict:
    job_id   = job.get("job_id", "?")
    job_type = job.get("type", "")
    _log(f"Job recibido: {job_type} [{job_id[:8]}]")

    handler = _HANDLERS.get(job_type)
    if not handler:
        return {"job_id": job_id, "success": False, "error": f"Tipo de job desconocido: {job_type}"}

    try:
        result = await handler(job)
    except Exception as e:
        result = {"success": False, "error": f"Error interno: {e}"}
        traceback.print_exc()

    result["job_id"] = job_id
    status = "OK" if result.get("success") else "ERROR"
    _log(f"Job {job_type} [{job_id[:8]}] → {status}: {result.get('error', '')}", level=status)
    return result


# ── Loop de conexión con backoff ───────────────────────────────────────────────

async def run_bridge(remote_url: str, token: str = "", retry_delay: float = 3.0) -> None:
    ws_url = remote_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
    ws_url += "/ws/hardware-bridge"
    if token:
        ws_url += f"?token={token}"

    _log(f"Hardware Bridge iniciando — conectando a {ws_url}")

    current_delay = retry_delay

    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=30) as ws:
                _log(f"Conectado al backend Stratum — esperando jobs...", level="OK")
                current_delay = retry_delay  # reset backoff

                while True:
                    try:
                        raw = await ws.recv()
                    except ConnectionClosed:
                        _log("Conexión cerrada por el servidor", level="WARN")
                        break

                    try:
                        job = json.loads(raw)
                    except json.JSONDecodeError:
                        _log(f"JSON inválido recibido: {raw[:80]}", level="WARN")
                        continue

                    # Procesar job y enviar resultado sin bloquear el loop
                    asyncio.create_task(_process_and_reply(ws, job))

        except OSError as e:
            _log(f"No se pudo conectar: {e} — reintentando en {current_delay:.0f}s", level="WARN")
        except Exception as e:
            _log(f"Error inesperado: {e} — reintentando en {current_delay:.0f}s", level="ERROR")

        await asyncio.sleep(current_delay)
        current_delay = min(current_delay * 2, 60)  # backoff hasta 60s


async def _process_and_reply(ws, job: dict) -> None:
    result = await _handle_job(job)
    try:
        await ws.send(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        _log(f"Error enviando resultado: {e}", level="ERROR")


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Stratum Hardware Bridge Client")
    parser.add_argument("--url",   required=True, help="URL del backend (ej: https://stratum.up.railway.app)")
    parser.add_argument("--token", default=os.getenv("BRIDGE_TOKEN", ""), help="Token de autenticación (BRIDGE_TOKEN)")
    args = parser.parse_args()

    try:
        asyncio.run(run_bridge(args.url, args.token))
    except KeyboardInterrupt:
        _log("Bridge detenido por el usuario.", level="WARN")


if __name__ == "__main__":
    main()
