# agent/agents/vision_agent.py
#
# Agente de visión para análisis de circuitos electrónicos.
# Usa LLaVA (modelo multimodal) corriendo en Ollama para:
#   1. Identificar componentes, pines y conexiones en una imagen
#   2. Estructurar el resultado como circuit_context
#   3. Guardarlo en hardware_memory para uso futuro del HardwareAgent

import base64
import json as _json
import os
import requests
from core.logger import logger
from core.config import get_llm_headers
from database.hardware_memory import hardware_memory

# Modelo de visión — LLaVA corre en Ollama como cualquier otro modelo
# El usuario puede sobreescribirlo en .env con VISION_MODEL=llava:13b
VISION_MODEL   = os.getenv("VISION_MODEL", "llava:7b")
OLLAMA_BASE    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
VISION_API_URL = f"{OLLAMA_BASE}/api/generate"   # Ollama native API (soporta imágenes)

VISION_PROMPT = """Sos un experto en electrónica y circuitos. Analizá esta imagen de un circuito electrónico/eléctrico.

Identificá con precisión:
1. Todos los componentes visibles (nombre, tipo, número si está visible)
2. En qué pines o terminales están conectados
3. Las conexiones entre componentes (cables, pistas PCB)
4. La alimentación del circuito (5V, 3.3V, 12V, batería, etc.)
5. El propósito general del circuito

Respondé SOLO con un JSON válido, sin markdown, sin explicaciones, con esta estructura exacta:
{
  "project_name": "nombre descriptivo del proyecto",
  "description": "qué hace este circuito en una oración",
  "components": [
    {"name": "nombre del componente", "type": "tipo (sensor/actuador/controlador/pasivo/display/etc)", "pin": "pin o terminal donde está conectado", "notes": "observaciones relevantes"}
  ],
  "connections": [
    {"from": "origen", "to": "destino", "description": "qué hace esta conexión"}
  ],
  "power": "fuente de alimentación detectada o 'desconocida'",
  "confidence": "alta/media/baja",
  "notes": "observaciones importantes sobre el circuito, posibles problemas o aspectos a tener en cuenta"
}"""


class VisionAgent:

    name        = "VisionAgent"
    description = "Analiza imágenes de circuitos y extrae componentes, pines y conexiones"

    def analyze_circuit(self, image_data: str, device_name: str = "") -> dict:
        """
        Analiza una imagen de circuito y retorna el contexto extraído.

        Args:
            image_data: Imagen en base64 (sin el prefijo data:image/...;base64,)
            device_name: Nombre del dispositivo al que asociar el circuito (opcional)

        Returns:
            {
                "success": bool,
                "circuit": dict,        # circuit_context listo para guardar
                "saved": bool,          # si se guardó en hardware_memory
                "message": str,         # resumen para mostrar al usuario
                "raw_response": str,    # respuesta cruda del modelo
            }
        """
        logger.info(f"[VisionAgent] Analizando imagen de circuito | device: {device_name or 'sin asignar'}")

        # 1. Verificar que LLaVA esté disponible
        if not self._check_vision_model():
            return {
                "success": False,
                "circuit": {},
                "saved":   False,
                "message": (
                    f"El modelo de visión '{VISION_MODEL}' no está disponible en Ollama.\n"
                    f"Instalalo con: `ollama pull {VISION_MODEL}`"
                ),
                "raw_response": "",
            }

        # 2. Llamar a LLaVA con la imagen
        raw_response = self._call_llava(image_data)
        if not raw_response:
            return {
                "success": False,
                "circuit": {},
                "saved":   False,
                "message": "No pude obtener respuesta del modelo de visión.",
                "raw_response": "",
            }

        # 3. Parsear el JSON del circuito
        circuit = self._parse_circuit(raw_response)
        if not circuit:
            return {
                "success": False,
                "circuit": {},
                "saved":   False,
                "message": f"Pude analizar la imagen pero no extraer la estructura del circuito.\nRespuesta del modelo: {raw_response[:300]}",
                "raw_response": raw_response,
            }

        # 4. Guardar en hardware_memory si se especificó un dispositivo
        saved = False
        if device_name:
            saved = hardware_memory.save_circuit_context(device_name, circuit)
            if saved:
                logger.info(f"[VisionAgent] Circuito guardado para {device_name}")

        # 5. Construir resumen legible
        message = self._build_summary(circuit, device_name, saved)

        return {
            "success":      True,
            "circuit":      circuit,
            "saved":        saved,
            "message":      message,
            "raw_response": raw_response,
        }

    def _check_vision_model(self) -> bool:
        """Verifica que LLaVA esté instalado en Ollama."""
        try:
            result = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            if result.status_code != 200:
                return False
            models = [m["name"] for m in result.json().get("models", [])]
            # Chequear si el modelo (o una variante) está disponible
            base_name = VISION_MODEL.split(":")[0]
            return any(base_name in m for m in models)
        except Exception as e:
            logger.error(f"[VisionAgent] Error verificando modelo: {e}")
            return False

    def _call_llava(self, image_base64: str) -> str:
        """Llama a LLaVA via Ollama native API con la imagen."""
        try:
            payload = {
                "model":  VISION_MODEL,
                "prompt": VISION_PROMPT,
                "images": [image_base64],
                "stream": False,
                "options": {
                    "temperature": 0.1,   # Baja temperatura para respuestas más precisas
                    "num_predict": 1024,
                }
            }

            response = requests.post(
                VISION_API_URL,
                json=payload,
                timeout=120   # Las imágenes pueden tardar más
            )
            response.raise_for_status()

            data = response.json()
            return data.get("response", "").strip()

        except requests.Timeout:
            logger.error("[VisionAgent] Timeout llamando a LLaVA")
            return ""
        except Exception as e:
            logger.error(f"[VisionAgent] Error llamando a LLaVA: {e}")
            return ""

    def _parse_circuit(self, raw: str) -> dict:
        """Parsea la respuesta del modelo y extrae el JSON del circuito."""
        try:
            # Limpiar posibles restos de markdown que el modelo pueda agregar
            clean = raw.strip()
            clean = clean.replace("```json", "").replace("```", "").strip()

            # Buscar el primer '{' y último '}' para extraer solo el JSON
            start = clean.find("{")
            end   = clean.rfind("}") + 1
            if start == -1 or end == 0:
                logger.warning("[VisionAgent] No se encontró JSON en la respuesta")
                return {}

            json_str = clean[start:end]
            circuit  = _json.loads(json_str)

            # Validar estructura mínima
            if not isinstance(circuit.get("components"), list):
                circuit["components"] = []
            if not isinstance(circuit.get("connections"), list):
                circuit["connections"] = []
            if not circuit.get("project_name"):
                circuit["project_name"] = "Circuito analizado por visión"
            if not circuit.get("power"):
                circuit["power"] = "desconocida"

            return circuit

        except _json.JSONDecodeError as e:
            logger.error(f"[VisionAgent] Error parseando JSON: {e}\nRaw: {raw[:200]}")
            return {}

    def _build_summary(self, circuit: dict, device_name: str, saved: bool) -> str:
        """Construye un resumen legible del circuito detectado."""
        lines = []

        project = circuit.get("project_name", "Circuito detectado")
        conf    = circuit.get("confidence", "media")
        lines.append(f"**{project}** (confianza: {conf})")

        if circuit.get("description"):
            lines.append(circuit["description"])

        components = circuit.get("components", [])
        if components:
            lines.append(f"\nComponentes detectados ({len(components)}):")
            for c in components[:8]:  # Máximo 8 para no saturar
                line = f"  • **{c.get('name', '?')}** ({c.get('type', '?')})"
                if c.get("pin"):
                    line += f" — pin {c['pin']}"
                lines.append(line)
            if len(components) > 8:
                lines.append(f"  ... y {len(components) - 8} más")

        if circuit.get("power") and circuit["power"] != "desconocida":
            lines.append(f"\nAlimentación: {circuit['power']}")

        if circuit.get("notes"):
            lines.append(f"\n⚠ {circuit['notes']}")

        if saved and device_name:
            lines.append(f"\n✓ Contexto guardado para **{device_name}**. La próxima vez que programes este dispositivo usaré esta información automáticamente.")
        elif not device_name:
            lines.append("\nPara asociar este circuito a un dispositivo, decime: *\"guardá el circuito para [nombre del dispositivo]\"*")

        return "\n".join(lines)


# Instancia global
vision_agent = VisionAgent()