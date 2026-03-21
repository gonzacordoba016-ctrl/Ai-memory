# core/prompt_builder.py

from datetime import datetime


def format_history(history):
    text = ""
    for msg in history:
        role    = msg["role"]
        content = msg["content"]
        text   += f"{'Usuario' if role == 'user' else 'Asistente'}: {content}\n"
    return text


def format_memories(memories):
    if not memories:
        return ""
    text = "Memorias relevantes:\n"
    for m in memories:
        text += f"- {m}\n"
    return text


def format_facts(facts):
    if not facts:
        return ""
    text = "Datos conocidos del usuario:\n"
    for key, value in facts.items():
        text += f"- {key}: {value}\n"
    return text


def build_prompt(user_input, history, memories, facts, graph_context="", user_profile_context=""):

    now   = datetime.now()
    fecha = now.strftime("%A %d de %B de %Y, %H:%M hs")

    system_prompt = f"""Eres AI Memory Engine, un asistente de IA local con memoria persistente.
Corrés 100% en la PC del usuario usando Ollama — no sos ChatGPT, Claude ni ningún servicio cloud.
Tu nombre es AI Memory Engine. Nunca digas que sos un asistente de Alibaba Cloud ni de ninguna otra empresa.

Hoy es {fecha}.

Tu objetivo es ayudar al usuario usando:
- Los datos que ya sabés de él (hechos persistidos)
- Las relaciones entre entidades que conocés (grafo de memoria)
- Recuerdos de conversaciones pasadas
- El historial de esta sesión

Reglas:
- Respondé siempre en el idioma del usuario
- Sé directo y conciso — no hagas preguntas innecesarias
- Si sabés algo sobre el usuario, usalo naturalmente en la respuesta
- Si no sabés algo, decilo claramente sin inventar
- Nunca rompas el personaje ni menciones modelos de lenguaje subyacentes"""

    sections = [
        system_prompt,
        user_profile_context,          # ← perfil del usuario (adaptación dinámica)
        format_facts(facts),
        graph_context,
        format_memories(memories),
        f"Historial:\n{format_history(history)}",
        f"Usuario: {user_input}\n\nAsistente:",
    ]

    return "\n\n".join(s for s in sections if s.strip())