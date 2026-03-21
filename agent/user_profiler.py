# agent/user_profiler.py
#
# Modelo mental del usuario — infiere y persiste un perfil estructurado
# a partir de las conversaciones, sin que el usuario declare nada explícitamente.
#
# El perfil se actualiza silenciosamente en cada interacción y se inyecta
# en el system prompt para que el agente adapte sus respuestas automáticamente.
#
# Campos del perfil:
#   expertise       → "principiante" / "intermedio" / "avanzado"
#   platforms       → ["arduino", "esp32", "plc", ...] plataformas más usadas
#   preferred_lang  → "c++" / "python" / "micropython" / ...
#   response_style  → "conciso" / "detallado" / "con_ejemplos"
#   active_projects → lista de proyectos mencionados recientemente
#   session_count   → cuántas sesiones ha tenido
#   last_topics     → últimos 5 temas tratados

import json
from datetime import datetime, timezone
from core.logger import logger

# ── Heurísticas estáticas para detectar expertise ─────────────────────────────
# Se evalúan sobre el texto del usuario sin llamar al LLM

BEGINNER_SIGNALS = [
    "no sé cómo", "no entiendo", "qué es", "cómo se hace", "primer proyecto",
    "primera vez", "me ayudás", "explicame", "qué significa", "no sé programar",
    "nunca usé", "estoy empezando", "soy nuevo", "aprendo",
]

ADVANCED_SIGNALS = [
    "interrupción", "interrupt", "dma", "registro", "register", "bitwise",
    "protocolo i2c", "spi bus", "uart", "watchdog", "pwm avanzado",
    "timer overflow", "freeRTOS", "mutex", "semáforo", "heap", "stack pointer",
    "linker", "bootloader", "jtag", "oscilloscope", "logic analyzer",
    "protocolo modbus", "canbus", "profibus", "plc ladder", "scada",
]

PLATFORM_KEYWORDS = {
    "arduino":     ["arduino", "uno", "mega", "nano", "atmega"],
    "esp32":       ["esp32", "esp-idf", "espressif"],
    "esp8266":     ["esp8266", "nodemcu", "wemos"],
    "raspberrypico": ["pico", "rp2040", "micropython pico"],
    "stm32":       ["stm32", "bluepill", "nucleo", "cubemx"],
    "plc":         ["plc", "ladder", "siemens", "allen bradley", "codesys", "modbus"],
    "raspberry":   ["raspberry pi", "raspbian", "gpio python"],
}

STYLE_SIGNALS = {
    "conciso":      ["resumido", "corto", "sin tanto detalle", "breve", "directo"],
    "detallado":    ["explicame todo", "paso a paso", "con detalles", "completo"],
    "con_ejemplos": ["con ejemplo", "mostrame", "dame un ejemplo", "ilustrá"],
}


class UserProfiler:
    """
    Analiza las interacciones del usuario e infiere su perfil técnico.
    Persiste el perfil en sql_memory como hechos estructurados bajo
    el prefijo 'profile_'.
    """

    # Clave base en la tabla facts para el perfil serializado
    PROFILE_KEY = "user_profile_v1"

    def __init__(self, sql_memory):
        self.sql = sql_memory
        self._cache: dict | None = None   # Cache en memoria para la sesión

    # =========================================================================
    # API pública
    # =========================================================================

    def get_profile(self) -> dict:
        """Retorna el perfil actual. Usa cache de sesión si está disponible."""
        if self._cache is not None:
            return self._cache

        try:
            facts = self.sql.get_all_facts()
            raw   = facts.get(self.PROFILE_KEY, "")
            if raw:
                self._cache = json.loads(raw)
            else:
                self._cache = self._default_profile()
        except Exception:
            self._cache = self._default_profile()

        return self._cache

    def update_from_interaction(self, user_text: str, agent_response: str = ""):
        """
        Actualiza el perfil analizando el texto del usuario.
        Llamar después de cada interacción en agent_controller.
        No llama al LLM — usa solo heurísticas estáticas (zero-latency).
        """
        try:
            profile = self.get_profile()
            changed = False

            text_lower = user_text.lower()

            # 1. Detectar expertise
            new_expertise = self._infer_expertise(text_lower, profile["expertise"])
            if new_expertise != profile["expertise"]:
                logger.info(f"[Profiler] Expertise actualizado: {profile['expertise']} → {new_expertise}")
                profile["expertise"] = new_expertise
                changed = True

            # 2. Detectar plataformas mencionadas
            for platform, keywords in PLATFORM_KEYWORDS.items():
                if any(kw in text_lower for kw in keywords):
                    if platform not in profile["platforms"]:
                        profile["platforms"].append(platform)
                        logger.info(f"[Profiler] Nueva plataforma detectada: {platform}")
                        changed = True

            # 3. Detectar estilo de respuesta preferido
            for style, signals in STYLE_SIGNALS.items():
                if any(s in text_lower for s in signals):
                    if profile["response_style"] != style:
                        profile["response_style"] = style
                        logger.info(f"[Profiler] Estilo actualizado: {style}")
                        changed = True

            # 4. Detectar lenguaje preferido
            lang = self._infer_language(text_lower, profile["preferred_lang"])
            if lang != profile["preferred_lang"]:
                profile["preferred_lang"] = lang
                changed = True

            # 5. Actualizar tópicos recientes
            topic = self._extract_topic(text_lower)
            if topic and topic not in profile["last_topics"]:
                profile["last_topics"] = ([topic] + profile["last_topics"])[:5]
                changed = True

            # 6. Incrementar contador de interacciones
            profile["interaction_count"] = profile.get("interaction_count", 0) + 1
            profile["last_seen"] = datetime.now(timezone.utc).isoformat()
            changed = True

            if changed:
                self._save_profile(profile)

        except Exception as e:
            logger.error(f"[Profiler] Error actualizando perfil: {e}")

    def format_for_prompt(self) -> str:
        """
        Formatea el perfil como contexto para incluir en el system prompt.
        Retorna string vacío si el perfil es el default (sin datos útiles).
        """
        profile = self.get_profile()

        # No inyectar nada si el perfil está vacío / es reciente
        if profile["interaction_count"] < 3:
            return ""

        lines = ["Perfil del usuario (adaptá tus respuestas en base a esto):"]

        expertise = profile.get("expertise", "desconocido")
        if expertise != "desconocido":
            descriptions = {
                "principiante": "Explicá conceptos básicos, evitá jerga técnica sin definir.",
                "intermedio":   "Podés asumir conocimiento básico, pero explicá conceptos avanzados.",
                "avanzado":     "Usá terminología técnica, podés omitir explicaciones básicas.",
            }
            lines.append(f"- Nivel técnico: {expertise}. {descriptions.get(expertise, '')}")

        platforms = profile.get("platforms", [])
        if platforms:
            lines.append(f"- Plataformas que usa: {', '.join(platforms[:4])}.")

        lang = profile.get("preferred_lang", "")
        if lang:
            lines.append(f"- Lenguaje preferido: {lang}.")

        style = profile.get("response_style", "")
        style_hints = {
            "conciso":      "Sé breve y directo, sin explicaciones innecesarias.",
            "detallado":    "Da explicaciones completas paso a paso.",
            "con_ejemplos": "Incluí siempre ejemplos de código concretos.",
        }
        if style and style in style_hints:
            lines.append(f"- Estilo preferido: {style_hints[style]}")

        topics = profile.get("last_topics", [])
        if topics:
            lines.append(f"- Temas recientes: {', '.join(topics[:3])}.")

        return "\n".join(lines) if len(lines) > 1 else ""

    def get_profile_summary(self) -> dict:
        """Retorna el perfil completo para la API y la UI."""
        profile = self.get_profile()
        return {
            "expertise":         profile.get("expertise", "desconocido"),
            "platforms":         profile.get("platforms", []),
            "preferred_lang":    profile.get("preferred_lang", ""),
            "response_style":    profile.get("response_style", ""),
            "last_topics":       profile.get("last_topics", []),
            "interaction_count": profile.get("interaction_count", 0),
            "last_seen":         profile.get("last_seen", ""),
        }

    # =========================================================================
    # Heurísticas internas
    # =========================================================================

    def _infer_expertise(self, text: str, current: str) -> str:
        """
        Infiere el nivel de expertise usando señales del texto.
        Una sola señal avanzada sube el nivel. Requiere 2+ señales básicas
        para bajar (evitar falsos negativos).
        """
        adv_signals = sum(1 for s in ADVANCED_SIGNALS if s in text)
        beg_signals = sum(1 for s in BEGINNER_SIGNALS if s in text)

        if adv_signals >= 1:
            return "avanzado"
        if beg_signals >= 2:
            return "principiante"
        if beg_signals == 1 and current == "desconocido":
            return "principiante"
        if current == "desconocido" and adv_signals == 0 and beg_signals == 0:
            return "intermedio"   # Default para usuarios que escriben sin señales claras
        return current

    def _infer_language(self, text: str, current: str) -> str:
        if "micropython" in text:
            return "micropython"
        if "python" in text and "arduino" not in text:
            return "python"
        if any(kw in text for kw in ["void setup", "void loop", ".ino", "cpp", "c++"]):
            return "c++"
        if "javascript" in text or "node.js" in text:
            return "javascript"
        return current

    def _extract_topic(self, text: str) -> str:
        """Extrae el tópico principal del mensaje para last_topics."""
        topic_map = {
            "temperatura":  "sensor temperatura",
            "humedad":      "sensor humedad",
            "led":          "control LED",
            "servo":        "servo motor",
            "motor":        "control motor",
            "wifi":         "conectividad WiFi",
            "bluetooth":    "bluetooth",
            "mqtt":         "protocolo MQTT",
            "serial":       "comunicación serial",
            "i2c":          "protocolo I2C",
            "display":      "pantalla/display",
            "lcd":          "pantalla LCD",
            "sensor":       "sensores",
            "relay":        "relés",
            "interrupcion": "interrupciones",
            "pwm":          "señales PWM",
            "adc":          "conversión analógica",
            "plc":          "programación PLC",
            "modbus":       "protocolo Modbus",
        }
        for keyword, topic in topic_map.items():
            if keyword in text:
                return topic
        return ""

    # =========================================================================
    # Persistencia
    # =========================================================================

    def _default_profile(self) -> dict:
        return {
            "expertise":         "desconocido",
            "platforms":         [],
            "preferred_lang":    "",
            "response_style":    "",
            "last_topics":       [],
            "interaction_count": 0,
            "last_seen":         "",
        }

    def _save_profile(self, profile: dict):
        """Persiste el perfil en SQLite como JSON."""
        try:
            self.sql.store_fact(self.PROFILE_KEY, json.dumps(profile, ensure_ascii=False))
            self._cache = profile
        except Exception as e:
            logger.error(f"[Profiler] Error guardando perfil: {e}")