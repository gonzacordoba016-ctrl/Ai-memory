# memory/fact_extractor.py

import json
from database.sql_memory import store_fact
from core.logger import logger
from llm.async_client import call_llm_text

EXTRACTION_PROMPT = """Analizá el siguiente mensaje del usuario y extraé datos personales relevantes.

Devolvé ÚNICAMENTE un JSON con los campos que encuentres. Si no hay datos relevantes, devolvé {{}}.

Campos posibles:
- user_name: nombre del usuario
- user_age: edad
- user_job: trabajo o profesión
- user_company: empresa donde trabaja
- user_email: email
- user_location: ciudad o país
- user_language: idioma preferido
- user_interests: intereses o hobbies (como string)
- partner_name: nombre de la pareja del usuario

Mensaje: "{message}"

Respondé solo con el JSON, sin explicaciones ni markdown."""

KEYWORDS = [
    "me llamo", "mi nombre", "tengo ", "trabajo", "empresa",
    "email", "vivo", "ciudad", "país", "me gusta", "mi pareja",
    "mi novia", "mi novio", "soy ", "años", "ahora trabajo",
    "conseguí trabajo", "me mudé", "cambié",
]


async def extract_facts(text: str) -> dict:
    """Extrae hechos del texto del usuario de forma async."""
    if len(text) < 15:
        return {}
    if not any(kw in text.lower() for kw in KEYWORDS):
        return {}

    try:
        content = await call_llm_text(
            messages=[{
                "role":    "user",
                "content": EXTRACTION_PROMPT.format(message=text),
            }],
            temperature=0,
            timeout=30,
            agent_id="fact-extractor",
            agent_name="FactExtractor",
        )

        if not content:
            return {}

        content = content.replace("```json", "").replace("```", "").strip()
        facts   = json.loads(content)

        for key, value in facts.items():
            if value:
                try:
                    from memory.memory_consolidator import memory_consolidator
                    result = memory_consolidator.process_new_fact(key, str(value))
                    if result.get("changed"):
                        logger.info(f"Hecho actualizado: {key} '{result['old']}' → '{result['new']}'")
                except Exception as e:
                    logger.error(f"Error consolidando hecho: {e}")

                store_fact(key, str(value))
                logger.info(f"Hecho extraído: {key} = {value}")

        return facts

    except Exception as e:
        logger.error(f"Error extrayendo hechos: {e}")
        return {}