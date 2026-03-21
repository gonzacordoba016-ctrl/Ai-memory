# tools/serial_monitor.py
#
# Lee output del dispositivo via puerto serial.

import serial
import threading
import time
from core.logger import logger


def read_serial(port: str, baudrate: int = 9600, duration: int = 5) -> str:
    """
    Lee el output del dispositivo por N segundos.
    Retorna el texto recibido.
    """
    try:
        # Esperar que el dispositivo se reinicie después del flash
        time.sleep(2)

        with serial.Serial(port, baudrate, timeout=1) as ser:
            output   = []
            deadline = time.time() + duration

            while time.time() < deadline:
                if ser.in_waiting:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line:
                        output.append(line)
                        logger.info(f"[Serial] {line}")
                else:
                    time.sleep(0.05)

        if not output:
            return "Sin output del dispositivo en el monitor serial."

        return "\n".join(output)

    except serial.SerialException as e:
        return f"Error abriendo puerto serial {port}: {e}"
    except Exception as e:
        return f"Error en monitor serial: {e}"


def send_serial(port: str, message: str, baudrate: int = 9600) -> str:
    """Envía un mensaje al dispositivo via serial."""
    try:
        with serial.Serial(port, baudrate, timeout=2) as ser:
            ser.write((message + "\n").encode("utf-8"))
            time.sleep(0.5)
            response = ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
        return response or "Mensaje enviado (sin respuesta inmediata)"
    except Exception as e:
        return f"Error enviando mensaje: {e}"