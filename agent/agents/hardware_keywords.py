# agent/agents/hardware_keywords.py — constantes de intent y keywords para HardwareAgent

import unicodedata


def _normalize(s: str) -> str:
    """Elimina tildes/acentos para matching insensible a tildes."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


MODIFY_KEYWORDS = [
    "modificá", "modifica", "cambiá", "cambia", "actualizá", "actualiza",
    "agregá", "agrega", "añadí", "añadi", "quitá", "quita", "sacá", "saca",
    "hacelo más", "hacelo menos", "hacelo más rápido", "más rápido",
    "más lento", "más brillante", "más suave", "más fuerte",
    "agregá el sensor", "agrega el sensor", "agregá wifi", "agrega wifi",
    "agregá mqtt", "agrega mqtt", "agregá ota", "agrega ota",
    "cambiá el pin", "cambia el pin", "cambiá el delay", "cambia el delay",
    "modificá el código", "modifica el código", "actualizá el firmware",
    "el código anterior", "en el código que me diste", "en ese código",
    "al firmware anterior", "al código anterior",
]

INTENT_PROMPT = """Clasificá esta consulta de hardware en UNA sola palabra:

- save_decision: guardar una decisión de diseño, razonamiento técnico, por qué elegí un componente
- save_circuit:  guardar, asociar o registrar un circuito/foto para un dispositivo
- query:         consultar historial de dispositivos YA REGISTRADOS, qué firmware tiene cargado, cuántas veces se flasheó
- program:       flashear, subir o cargar código a un dispositivo físico YA CONECTADO por USB (blink, servo, sensor, WiFi, MQTT)
- signal:        leer señal analógica, voltaje, osciloscopio, monitorear pin
- debug:         corregir error, algo no funciona, falla, arreglar, diagnosticar
- design:        ESCRIBIR código/ejemplo/función/firmware para un microcontrolador (aunque no esté conectado), diseñar circuito, asesoramiento técnico, dimensionar componentes, potencia, motor, PLC, regulador, fuente, esquema, cálculos eléctricos
- modify:        MODIFICAR, cambiar, actualizar o agregar algo AL CÓDIGO/FIRMWARE ANTERIOR que ya se generó en esta sesión

Ejemplos:
- "escribí un ejemplo en C para ESP32" → design
- "qué tiene programado el arduino" → query
- "flasheá el firmware" → program
- "calculá la resistencia" → design
- "hacelo más rápido" → modify
- "agregá wifi al código anterior" → modify

Consulta: "{task}"

Respondé SOLO con una de estas 8 palabras: save_decision, save_circuit, query, program, signal, debug, design, modify"""


# ── KEYWORDS exhaustivas por categoría ───────────────────────────────────────

SAVE_DECISION_KEYWORDS = [
    "guardá la decisión", "guarda la decisión",
    "guardá el razonamiento", "guarda el razonamiento",
    "guardá por qué", "guarda por qué",
    "registrá la decisión", "registra la decisión",
    "guardá la razón", "guarda la razón",
    "anotá que", "anota que",
]

SAVE_CIRCUIT_KEYWORDS = [
    "guardá el circuito", "guarda el circuito",
    "guardá este circuito", "guarda este circuito",
    "asociá el circuito", "asocia el circuito",
    "guardá la foto", "guarda la foto",
    "registrá el circuito", "registra el circuito",
    "guardá el esquema", "guarda el esquema",
]

QUERY_KEYWORDS = [
    # Consultas directas de memoria
    "qué tiene", "que tiene", "qué tenía", "que tenia",
    "qué tengo", "que tengo", "qué había", "que habia",
    "qué programé", "que programe", "qué cargué", "que cargue",
    "qué subí", "que subi", "qué flasheé", "que flashee",
    "tenía programado", "tenia programado", "había cargado",
    # Historial
    "historial", "versiones", "versión anterior", "último firmware",
    "ultimo firmware", "última versión", "ultima version",
    "cuántas veces", "cuantas veces", "cuántos flashes", "cuantos flashes",
    "registro de", "log de", "actividad de",
    # Dispositivos
    "dispositivos", "registrados", "conocidos", "conectados",
    "qué dispositivos", "que dispositivos", "cuáles dispositivos",
    "mis dispositivos", "mis arduinos", "mis esp",
    # Info general
    "firmware actual", "código actual", "qué tiene cargado",
    "que tiene cargado", "qué sabe", "que sabe",
    "información sobre", "info sobre", "detalles de",
    "estado del", "estado de",
    # Biblioteca
    "proyectos guardados", "biblioteca", "proyectos disponibles",
    "qué proyectos", "que proyectos",
    # Circuito
    "circuito", "componentes", "conexiones del",
    "qué componentes", "que componentes",
    "esquema", "diagrama",
]

SIGNAL_KEYWORDS = [
    "señal", "senal", "señales", "senales",
    "analógica", "analogica", "analógico", "analogico",
    "voltaje", "voltage", "volt", "volts",
    "osciloscopio", "osciloscopo", "oscilloscope",
    "leer pin", "leer a0", "leer a1", "leer a2",
    "monitorear señal", "monitorear senal",
    "capturar señal", "medir voltaje", "medir corriente",
    "sensor analógico", "sensor analogico",
    "adc", "pwm output", "frecuencia",
]

DEBUG_KEYWORDS = [
    # Errores genéricos
    "error", "errores", "falla", "fallas", "fallo",
    "no funciona", "no anda", "no compila",
    "no flashea", "no sube", "upload failed",
    "no responde", "se colgó", "se congela", "se reinicia",
    # Acciones de debug
    "arreglá", "arregla", "arreglame", "corregí", "corrige",
    "corregime", "arreglar", "corregir", "reparar",
    "debug", "debuggear", "depurar", "diagnosticar",
    "revisar", "verificar el código",
    # Síntomas hardware
    "no enciende", "no prende", "no parpadea", "no se mueve",
    "no lee", "no detecta", "no envía", "no envia",
    "no conecta", "no responde al serial",
    "led apagado", "pin no funciona",
    # Síntomas código
    "el código falla", "codigo falla", "código da error",
    "syntax error", "compilation error", "linker error",
    "undefined reference", "not declared",
    "loop infinito", "crash", "exception",
]

PROGRAM_KEYWORDS = [
    # Acciones de programación directa sobre dispositivo
    "flashear", "flasheá",
    "subí", "subi", "subir firmware",
    "cargar firmware", "cargá el firmware",
    # Control de hardware embebido
    "hacer parpadear", "que parpadee", "que encienda el led", "que apague el led",
    "que lea el sensor", "que mida el sensor", "que envíe por serial",
    "blink", "leer sensor", "escribir pin",
    "comunicación serial", "wifi esp", "bluetooth esp", "mqtt",
]

DESIGN_KEYWORDS = [
    # Escritura de código/ejemplos para microcontroladores
    "escribí", "escribi", "escribime", "generá", "genera", "generame",
    "dame un ejemplo", "dame código", "dame codigo", "dame el código",
    "creá un ejemplo", "crea un ejemplo", "mostrá", "mostra",
    "hacé un programa", "hace un programa", "necesito un código",
    "código para", "codigo para", "ejemplo en c", "ejemplo de codigo",
    "función para", "funcion para", "rutina para",
    # Diseño y asesoramiento técnico
    "quiero programar mi circuito", "diseñar", "dimensionar", "calcular",
    "qué componente", "que componente", "qué usar", "que usar",
    "cómo programar", "como programar", "cómo controlar", "como controlar",
    "circuito de potencia", "circuito de fuerza", "circuito de control",
    "motor de", "motor trifásico", "motor monofásico", "15hp", "10hp", "5hp",
    "variador de frecuencia", "variador", "vfd", "arrancador", "contactor",
    "relé térmico", "rele termico", "guardamotor",
    "fuente de alimentación", "fuente switching", "transformador",
    "regulador de tensión", "lm317", "lm7805",
    "circuito integrado", "amplificador", "opamp",
    "automatizar", "automatización industrial", "plc ladder",
    "cómo funciona", "como funciona", "qué es", "que es",
    "asesorá", "asesorame", "recomendá", "recomendame",
    "qué necesito", "que necesito", "qué utilizo", "que utilizo",
    "explicame", "explicá", "cómo hago", "como hago",
]
