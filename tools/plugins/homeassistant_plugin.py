# tools/plugins/homeassistant_plugin.py
#
# Plugin de integración con Home Assistant para Stratum.
# Sincroniza dispositivos Stratum como entidades en Home Assistant via HTTP webhooks.
#
# Configuración (variables de entorno):
#   HA_WEBHOOK_URL  — URL del webhook HA (ej: http://homeassistant.local:8123/api/webhook/stratum)
#   HA_TOKEN        — Long-Lived Access Token de Home Assistant (opcional, para REST API directa)
#   HA_BASE_URL     — URL base de HA para REST API (ej: http://homeassistant.local:8123)

import json
import os
import urllib.request
import urllib.error
from datetime import datetime

PLUGIN_NAME        = "homeassistant"
PLUGIN_DESCRIPTION = "Integración con Home Assistant — sincroniza dispositivos Stratum como entidades HA"
PLUGIN_VERSION     = "1.0"


def _get_config() -> dict:
    return {
        "webhook_url": os.getenv("HA_WEBHOOK_URL", ""),
        "token":       os.getenv("HA_TOKEN", ""),
        "base_url":    os.getenv("HA_BASE_URL", "").rstrip("/"),
    }


def _ha_post(url: str, payload: dict, token: str = "") -> dict:
    """Hace un POST HTTP a Home Assistant. Sin dependencias externas."""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "body": body[:200]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Tool 1: Enviar estado de una entidad ──────────────────────────────────────

def ha_send_state(entity_id: str, state: str, attributes: str = "{}") -> str:
    """Envía el estado de una entidad a Home Assistant.

    Usa HA_BASE_URL + HA_TOKEN si están configurados (REST API).
    Si no, usa HA_WEBHOOK_URL como fallback.
    """
    cfg = _get_config()
    if not cfg["base_url"] and not cfg["webhook_url"]:
        return (
            "⚠️ Home Assistant no configurado. "
            "Definí HA_BASE_URL + HA_TOKEN (o HA_WEBHOOK_URL) en las variables de entorno."
        )

    try:
        attrs = json.loads(attributes) if isinstance(attributes, str) else attributes
    except json.JSONDecodeError:
        attrs = {}

    attrs["updated_by"] = "stratum"
    attrs["updated_at"] = datetime.utcnow().isoformat()

    # REST API directa (preferida)
    if cfg["base_url"] and cfg["token"]:
        url = f"{cfg['base_url']}/api/states/{entity_id}"
        result = _ha_post(url, {"state": state, "attributes": attrs}, token=cfg["token"])
    else:
        # Webhook fallback
        result = _ha_post(cfg["webhook_url"], {
            "action": "set_state",
            "entity_id": entity_id,
            "state": state,
            "attributes": attrs,
        })

    if result.get("ok"):
        return f"✅ Estado '{state}' enviado a {entity_id} (HTTP {result.get('status')})"
    return f"❌ Error enviando estado: {result.get('error', result)}"


# ── Tool 2: Listar dispositivos como entidades HA ─────────────────────────────

def ha_get_devices() -> str:
    """Lista los dispositivos registrados en Stratum formateados como entidades Home Assistant."""
    try:
        from database.hardware_memory import HardwareMemory
        hw = HardwareMemory()
        devices = hw.list_devices() or []
    except Exception as e:
        return f"❌ No se pudo acceder a la base de datos de dispositivos: {e}"

    if not devices:
        return "No hay dispositivos registrados en Stratum."

    lines = ["Dispositivos Stratum → entidades Home Assistant:\n"]
    for dev in devices:
        name = dev.get("device_name", "unknown")
        port = dev.get("port", "?")
        platform = dev.get("platform", "arduino")
        entity_id = f"sensor.stratum_{name.lower().replace(' ', '_').replace('-', '_')}"
        lines.append(
            f"• {name} ({platform}, {port})\n"
            f"  entity_id: {entity_id}\n"
            f"  estado sugerido: online/offline\n"
        )

    lines.append(
        "\nUsar ha_sync_all() para sincronizar todos, "
        "o ha_send_state(entity_id, state) para uno individual."
    )
    return "\n".join(lines)


# ── Tool 3: Sincronizar todos los dispositivos ────────────────────────────────

def ha_sync_all() -> str:
    """Sincroniza todos los dispositivos Stratum con Home Assistant."""
    cfg = _get_config()
    if not cfg["base_url"] and not cfg["webhook_url"]:
        return (
            "⚠️ Home Assistant no configurado. "
            "Definí HA_BASE_URL + HA_TOKEN (o HA_WEBHOOK_URL) en las variables de entorno."
        )

    try:
        from database.hardware_memory import HardwareMemory
        hw = HardwareMemory()
        devices = hw.list_devices() or []
    except Exception as e:
        return f"❌ No se pudo acceder a la base de datos: {e}"

    if not devices:
        return "No hay dispositivos para sincronizar."

    results = []
    for dev in devices:
        name = dev.get("device_name", "unknown")
        platform = dev.get("platform", "arduino")
        last_seen = dev.get("last_seen", "")
        entity_id = f"sensor.stratum_{name.lower().replace(' ', '_').replace('-', '_')}"

        # Estado: 'online' si fue visto en las últimas 24h, 'offline' si no
        state = "online" if last_seen else "offline"
        attrs = json.dumps({
            "platform": platform,
            "port": dev.get("port", ""),
            "last_seen": last_seen,
            "micropython": dev.get("micropython", False),
        })
        result = ha_send_state(entity_id, state, attrs)
        results.append(f"{name}: {result}")

    return "Sincronización completa:\n" + "\n".join(results)


# ── Registro de tools ─────────────────────────────────────────────────────────

PLUGIN_TOOLS = [
    {
        "function":    ha_send_state,
        "name":        "ha_send_state",
        "description": "Envía el estado de una entidad a Home Assistant (requiere HA_BASE_URL+HA_TOKEN o HA_WEBHOOK_URL)",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type":        "string",
                    "description": "ID de la entidad HA (ej: sensor.stratum_arduino_uno)"
                },
                "state": {
                    "type":        "string",
                    "description": "Estado a enviar (ej: online, offline, 23.5)"
                },
                "attributes": {
                    "type":        "string",
                    "description": "JSON con atributos adicionales (opcional, ej: {\"unit\": \"°C\"})"
                }
            },
            "required": ["entity_id", "state"]
        }
    },
    {
        "function":    ha_get_devices,
        "name":        "ha_get_devices",
        "description": "Lista los dispositivos Stratum formateados como entidades de Home Assistant",
        "parameters": {
            "type":       "object",
            "properties": {},
            "required":   []
        }
    },
    {
        "function":    ha_sync_all,
        "name":        "ha_sync_all",
        "description": "Sincroniza todos los dispositivos registrados en Stratum con Home Assistant",
        "parameters": {
            "type":       "object",
            "properties": {},
            "required":   []
        }
    },
]
