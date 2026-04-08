
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

# Forzar el contexto del agente antes de importar core.config si fuera necesario
# Pero aquí ya cargamos .env y main.py lo hace también.

from core.config import get_llm_headers, LLM_API
from llm.async_client import call_llm_text

async def test_aethermind():
    print(f"URL Gateway: {LLM_API}")
    headers = get_llm_headers(agent_name="antigravity-test")
    print(f"Headers utilizados: { {k: v if 'Authorization' not in k else 'Bearer ***' for k, v in headers.items()} }")
    
    prompt = "Hola, eres un asistente de prueba. Responde con la palabra 'OK' si recibes esto correctamente."
    print(f"Enviando prompt: {prompt}")
    
    response = await call_llm_text(
        messages=[{"role": "user", "content": prompt}],
        agent_name="antigravity-test"
    )
    
    print(f"Respuesta del LLM: {response}")
    if response:
        print("\n✅ Conexión con Aethermind Gateway exitosa.")
    else:
        print("\n❌ Error: No se recibió respuesta. Revisa los logs de core.config.")

if __name__ == "__main__":
    asyncio.run(test_aethermind())
