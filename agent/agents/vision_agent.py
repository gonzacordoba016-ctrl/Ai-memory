# agent/agents/vision_agent.py
#
# Agente de visión para análisis de circuitos electrónicos.
# Soporta dos backends:
#   - OpenRouter (gpt-4o-mini / gpt-4o) cuando LLM_PROVIDER=openrouter
#   - Ollama + LLaVA cuando LLM_PROVIDER=ollama

import base64
import json as _json
import os
import httpx
from core.logger import logger
from core.config import get_llm_headers
from database.hardware_memory import hardware_memory

# Modelo de visión para Ollama
VISION_MODEL_OLLAMA  = os.getenv("VISION_MODEL", "llava:7b")
OLLAMA_BASE          = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Modelo de visión para OpenRouter (gpt-4o-mini soporta imágenes)
VISION_MODEL_OPENROUTER = os.getenv("VISION_MODEL_OPENROUTER", "openai/gpt-4o-mini")
OPENROUTER_URL          = "https://openrouter.ai/api/v1/chat/completions"

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

    def analyze_circuit(self, image_data: str, device_name: str = "", mime_type: str = "image/jpeg") -> dict:
        """
        Analiza una imagen de circuito y retorna el contexto extraído.

        Args:
            image_data: Imagen en base64 (sin el prefijo data:image/...;base64,)
            device_name: Nombre del dispositivo al que asociar el circuito (opcional)
            mime_type: MIME type de la imagen (default: image/jpeg)

        Returns:
            {
                "success": bool,
                "circuit": dict,
                "saved": bool,
                "message": str,
                "raw_response": str,
            }
        """
        provider = os.getenv("LLM_PROVIDER", "ollama")
        logger.info(f"[VisionAgent] Analizando imagen | provider={provider} | device={device_name or 'sin asignar'}")

        if provider == "openrouter":
            raw_response = self._call_openrouter(image_data, mime_type)
        else:
            if not self._check_ollama_model():
                return {
                    "success": False,
                    "circuit": {},
                    "saved":   False,
                    "message": (
                        f"El modelo de visión '{VISION_MODEL_OLLAMA}' no está disponible en Ollama.\n"
                        f"Instalalo con: `ollama pull {VISION_MODEL_OLLAMA}`\n"
                        f"O configurá LLM_PROVIDER=openrouter en tu .env para usar GPT-4o-mini."
                    ),
                    "raw_response": "",
                }
            raw_response = self._call_ollama(image_data)

        if not raw_response:
            return {
                "success": False,
                "circuit": {},
                "saved":   False,
                "message": "No pude obtener respuesta del modelo de visión.",
                "raw_response": "",
            }

        circuit = self._parse_circuit(raw_response)
        if not circuit:
            return {
                "success": False,
                "circuit": {},
                "saved":   False,
                "message": f"Pude analizar la imagen pero no extraer la estructura del circuito.\nRespuesta: {raw_response[:300]}",
                "raw_response": raw_response,
            }

        # Siempre guardar el último análisis (en memoria y en DB para sobrevivir reloads)
        vision_agent._last_circuit = circuit
        try:
            from database.sql_memory import _default as _sql
            import json as _j
            _sql.store_fact("__last_vision_circuit", _j.dumps(circuit, ensure_ascii=False))
        except Exception:
            pass

        saved = False
        if device_name:
            saved = hardware_memory.save_circuit_context(device_name, circuit)
            if saved:
                logger.info(f"[VisionAgent] Circuito guardado para {device_name}")

        message = self._build_summary(circuit, device_name, saved)

        return {
            "success":      True,
            "circuit":      circuit,
            "saved":        saved,
            "message":      message,
            "raw_response": raw_response,
        }

    # ── OpenRouter (OpenAI vision API) ─────────────────────────────────────────

    def _call_openrouter(self, image_base64: str, mime_type: str = "image/jpeg") -> str:
        """Llama a OpenRouter con visión usando el formato OpenAI messages."""
        try:
            headers = get_llm_headers()
            payload = {
                "model": VISION_MODEL_OPENROUTER,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens":  1024,
            }

            response = httpx.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(f"[VisionAgent] OpenRouter respondió | model={VISION_MODEL_OPENROUTER}")
            return content.strip()

        except requests.Timeout:
            logger.error("[VisionAgent] Timeout llamando a OpenRouter vision")
            return ""
        except Exception as e:
            logger.error(f"[VisionAgent] Error llamando a OpenRouter vision: {e}")
            return ""

    # ── Ollama / LLaVA ─────────────────────────────────────────────────────────

    def _check_ollama_model(self) -> bool:
        """Verifica que LLaVA esté instalado en Ollama."""
        try:
            result = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            if result.status_code != 200:
                return False
            models   = [m["name"] for m in result.json().get("models", [])]
            base_name = VISION_MODEL_OLLAMA.split(":")[0]
            return any(base_name in m for m in models)
        except Exception as e:
            logger.error(f"[VisionAgent] Error verificando modelo Ollama: {e}")
            return False

    def _call_ollama(self, image_base64: str) -> str:
        """Llama a LLaVA via Ollama native API con la imagen."""
        try:
            payload = {
                "model":  VISION_MODEL_OLLAMA,
                "prompt": VISION_PROMPT,
                "images": [image_base64],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 1024},
            }
            response = httpx.post(
                f"{OLLAMA_BASE}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()

        except requests.Timeout:
            logger.error("[VisionAgent] Timeout llamando a LLaVA")
            return ""
        except Exception as e:
            logger.error(f"[VisionAgent] Error llamando a LLaVA: {e}")
            return ""

    # ── Parseo y resumen ────────────────────────────────────────────────────────

    def _parse_circuit(self, raw: str) -> dict:
        """Parsea la respuesta del modelo y extrae el JSON del circuito."""
        try:
            clean = raw.strip().replace("```json", "").replace("```", "").strip()
            start = clean.find("{")
            end   = clean.rfind("}") + 1
            if start == -1 or end == 0:
                logger.warning("[VisionAgent] No se encontró JSON en la respuesta")
                return {}

            circuit = _json.loads(clean[start:end])

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
            for c in components[:8]:
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
vision_agent._last_circuit = {}  # último circuito analizado (para asociar después)
