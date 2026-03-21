# tools/signal_reader.py
#
# Lee señales analógicas del Arduino en tiempo real.
# El Arduino debe tener cargado el firmware de telemetría (signal_firmware).
# Envía datos via WebSocket para visualización en Stratum.

import serial
import threading
import time
import json
from datetime import datetime, timezone
from core.logger import logger
from memory.vector_memory import store_memory

# Firmware que debe estar en el Arduino para enviar señales
SIGNAL_FIRMWARE = """
// Firmware de telemetría — envía señales analógicas via Serial
// Generado por Stratum Hardware Memory Engine

void setup() {
  Serial.begin(9600);
}

void loop() {
  int a0 = analogRead(A0);
  int a1 = analogRead(A1);
  int a2 = analogRead(A2);
  float voltage = a0 * (5.0 / 1023.0);

  Serial.print("{");
  Serial.print("\\"a0\\":");  Serial.print(a0);
  Serial.print(",\\"a1\\":");  Serial.print(a1);
  Serial.print(",\\"a2\\":");  Serial.print(a2);
  Serial.print(",\\"v\\":");   Serial.print(voltage, 3);
  Serial.print(",\\"t\\":");   Serial.print(millis());
  Serial.println("}");

  delay(100);
}
"""


class SignalReader:

    def __init__(self):
        self._thread    = None
        self._running   = False
        self._port      = None
        self._baudrate  = 9600
        self._callbacks = []
        self._buffer    = []
        self._max_buffer = 500

    def start(self, port: str, baudrate: int = 9600):
        """Inicia la lectura de señal en background."""
        if self._running:
            self.stop()

        self._port     = port
        self._baudrate = baudrate
        self._running  = True
        self._buffer   = []

        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info(f"[Signal] Iniciando lectura en {port}")

    def stop(self):
        """Detiene la lectura."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("[Signal] Lectura detenida")

    def add_callback(self, fn):
        """Agrega callback que se llama con cada punto de datos."""
        self._callbacks.append(fn)

    def get_buffer(self) -> list[dict]:
        """Retorna los últimos N puntos del buffer."""
        return list(self._buffer)

    def get_signal_firmware(self) -> str:
        """Retorna el firmware de telemetría para cargar al Arduino."""
        return SIGNAL_FIRMWARE

    def _read_loop(self):
        """Loop de lectura serial en thread separado."""
        try:
            with serial.Serial(self._port, self._baudrate, timeout=1) as ser:
                logger.info(f"[Signal] Conectado a {self._port}")
                anomaly_count  = 0
                baseline_sum   = 0
                baseline_count = 0

                while self._running:
                    if ser.in_waiting:
                        try:
                            line = ser.readline().decode("utf-8", errors="ignore").strip()
                            if line.startswith("{"):
                                data = json.loads(line)
                                data["ts"] = datetime.now(timezone.utc).isoformat()

                                # Detectar anomalías
                                a0 = data.get("a0", 0)
                                if baseline_count > 20:
                                    baseline = baseline_sum / baseline_count
                                    if abs(a0 - baseline) > baseline * 0.3:
                                        data["anomaly"] = True
                                        anomaly_count  += 1
                                        logger.info(f"[Signal] Anomalía detectada: a0={a0} baseline={baseline:.0f}")
                                        self._store_anomaly(data, baseline)

                                baseline_sum   += a0
                                baseline_count += 1

                                # Guardar en buffer circular
                                self._buffer.append(data)
                                if len(self._buffer) > self._max_buffer:
                                    self._buffer.pop(0)

                                # Notificar callbacks
                                for cb in self._callbacks:
                                    try:
                                        cb(data)
                                    except Exception:
                                        pass

                        except (json.JSONDecodeError, ValueError):
                            pass
                    else:
                        time.sleep(0.01)

        except serial.SerialException as e:
            logger.error(f"[Signal] Error serial: {e}")
        except Exception as e:
            logger.error(f"[Signal] Error inesperado: {e}")
        finally:
            self._running = False

    def _store_anomaly(self, data: dict, baseline: float):
        """Guarda anomalías en memoria vectorial."""
        try:
            ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            text = (
                f"[Señal - {ts}] Anomalía detectada en {self._port}. "
                f"Valor: {data.get('a0')} (baseline: {baseline:.0f}). "
                f"Voltaje: {data.get('v', 0):.2f}V"
            )
            store_memory(text, metadata={
                "type":     "signal_anomaly",
                "port":     self._port,
                "value":    data.get("a0"),
                "baseline": baseline,
            })
        except Exception:
            pass


signal_reader = SignalReader()