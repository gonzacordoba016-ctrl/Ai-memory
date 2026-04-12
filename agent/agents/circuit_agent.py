# agent/agents/circuit_agent.py

import json
import re
from typing import Dict, Any, Optional, List
from core.logger import get_logger
from core.config import LLM_MODEL_SMART
from database.circuit_design import CircuitDesignManager
from tools.hardware_detector import resolve_component_type
from llm.openrouter_client import _call_llm

logger = get_logger(__name__)

CIRCUIT_PARSE_PROMPT = """Eres un experto en electrónica embebida. Tu tarea es generar una netlist JSON completa y lista para fabricación a partir de una descripción en lenguaje natural.

Descripción del circuito: "{description}"
Microcontrolador principal: "{mcu}"

REGLAS OBLIGATORIAS — aplica siempre todas:
1. Incluí TODAS las conexiones de alimentación (VCC y GND para cada componente).
2. Cada LED DEBE tener su propia resistencia limitadora de corriente en serie (220Ω–470Ω para 5V, 68Ω–100Ω para 3.3V). Calculá el valor: R = (Vcc - Vled) / Iled, donde Iled≈20mA.
3. Agregá capacitores de desacople (100nF cerámico) entre VCC y GND cerca de cada IC.
4. Si usás I2C (SDA/SCL), incluí resistencias pull-up (4.7kΩ a VCC) en ambas líneas.
5. Si usás sensores DHT / DS18B20 / one-wire, incluí pull-up de 10kΩ en la línea de datos.
6. Nombrá los componentes con IDs únicos: U1, U2... para ICs/MCU; R1, R2... para resistencias; C1, C2... para capacitores; D1, D2... para LEDs/diodos; SW1... para botones/switches; MOD1... para módulos.
7. Cada net debe tener un nombre descriptivo (VCC, GND, SDA, SCL, LED_ANODE, TRIG, ECHO, DATA, etc.).
8. "power" debe indicar la fuente real (ej: "5V USB", "7-12V DC barrel jack", "3.7V LiPo").
9. Si el circuito tiene riesgos (voltaje AC, corriente alta, componentes de 3.3V conectados a 5V), incluílos en "warnings".

Devuelve SOLO el JSON válido, sin texto antes ni después, sin bloques markdown:
{{
  "name": "nombre descriptivo del proyecto",
  "description": "descripción en 1 oración de qué hace el circuito",
  "components": [
    {{"id": "U1", "name": "{mcu}", "type": "arduino_uno"}},
    {{"id": "R1", "name": "Resistencia LED 220Ω", "type": "resistor", "value": "220"}},
    {{"id": "D1", "name": "LED Rojo", "type": "led", "color": "red"}},
    {{"id": "C1", "name": "Cap desacople 100nF", "type": "capacitor", "value": "100n"}}
  ],
  "nets": [
    {{"name": "VCC_5V",  "nodes": ["U1.5V", "R1.1", "C1.1"]}},
    {{"name": "GND",     "nodes": ["U1.GND", "D1.K", "C1.2"]}},
    {{"name": "LED_DRV", "nodes": ["U1.13", "R1.2"]}},
    {{"name": "LED_A",   "nodes": ["R1.2", "D1.A"]}}
  ],
  "power": "5V USB",
  "warnings": []
}}"""

class CircuitAgent:
    def __init__(self):
        self.circuit_manager = CircuitDesignManager()

    def parse_circuit(self, description: str, mcu: str = "Arduino Uno") -> Optional[Dict[str, Any]]:
        """
        Parsea una descripción de circuito en lenguaje natural y devuelve su representación estructurada.
        """
        try:
            # Construye el prompt con la descripción
            prompt = CIRCUIT_PARSE_PROMPT.format(description=description, mcu=mcu)

            # Consulta al LLM para obtener el JSON estructurado
            messages = [{"role": "user", "content": prompt}]
            response = _call_llm(messages, model=LLM_MODEL_SMART)
            
            # Extraer contenido de la respuesta
            content = response["choices"][0]["message"]["content"]
            
            # Limpiar posibles markdown wrappers
            content = self._clean_json_content(content)
            
            # Parsear JSON
            circuit_data = json.loads(content)
            
            # Validaciones básicas
            required_keys = ["name", "description", "components", "nets"]
            for key in required_keys:
                if key not in circuit_data:
                    logger.warning(f"Falta campo requerido '{key}' en la respuesta del LLM.")
                    return None

            # Resolución de tipos de componentes usando alias
            for comp in circuit_data["components"]:
                resolved_type = resolve_component_type(comp.get("type"))
                comp["resolved_type"] = resolved_type or comp["type"]

            # Calcular valores faltantes (ej: resistencia para LED)
            self._calculate_missing_values(circuit_data)

            # Validar el circuito (cortocircuitos, pines duplicados)
            warnings = self._validate_circuit(circuit_data)
            if warnings:
                circuit_data.setdefault("warnings", []).extend(warnings)

            # DRC eléctrico automático
            try:
                from tools.electrical_drc import run_drc
                drc_result = run_drc(circuit_data)
                circuit_data["drc"] = drc_result
                if not drc_result["passed"]:
                    for err in drc_result["errors"]:
                        circuit_data.setdefault("warnings", []).append(
                            f"[DRC] {err['code']}: {err['message']}"
                        )
            except Exception as drc_err:
                logger.warning(f"DRC falló silenciosamente: {drc_err}")

            # Guardar diseño en DB
            design_id = self.circuit_manager.save_design(circuit_data)

            # Añadir ID al resultado para referencia futura
            circuit_data["design_id"] = design_id

            logger.info(f"Circuito guardado correctamente bajo ID {design_id}")
            return circuit_data

        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON del LLM: {str(e)}")
            logger.debug(f"Contenido recibido: {content}")
            return None
        except Exception as e:
            logger.exception(f"Error al parsear el circuito: {str(e)}")
            return None

    def _clean_json_content(self, content: str) -> str:
        """Limpia contenido JSON de posibles wrappers de markdown."""
        # Eliminar ```json ... ``` si existe
        match = re.search(r'```(?:json)?\s*({.*})\s*```', content, re.DOTALL)
        if match:
            return match.group(1)
        return content

    def _calculate_missing_values(self, circuit_data: Dict[str, Any]) -> None:
        """Calcula y completa valores faltantes. Auto-agrega resistencias para LEDs si el LLM las omitió."""
        components = circuit_data["components"]
        nets = circuit_data.get("nets", [])
        warnings = circuit_data.setdefault("warnings", [])

        led_ids = [c["id"] for c in components if c.get("type") == "led"]
        resistor_ids = {c["id"] for c in components if c.get("type") == "resistor"}

        for led_id in led_ids:
            # Verificar si el LED está en serie con alguna resistencia en las nets
            led_nets = [n for n in nets if any(led_id in node for node in n.get("nodes", []))]
            has_resistor = any(
                any(r_id in node for node in net.get("nodes", []))
                for net in led_nets
                for r_id in resistor_ids
            )
            if not has_resistor:
                # Auto-agregar resistencia de 220Ω
                new_id = f"R_auto{led_id}"
                components.append({
                    "id": new_id,
                    "name": f"Resistencia limitadora {led_id} 220Ω",
                    "type": "resistor",
                    "value": "220",
                    "auto_added": True,
                })
                warnings.append(
                    f"[Auto] Se agregó resistencia {new_id} (220Ω) en serie con {led_id} — "
                    "verificá el valor según Vcc y el color del LED"
                )

    def _validate_circuit(self, circuit_data: Dict[str, Any]) -> List[str]:
        """Realiza validaciones simples sobre la netlist generada."""
        warnings = []

        # Verificar nodos duplicados
        nodes_used = set()
        for net in circuit_data.get("nets", []):
            for node in net["nodes"]:
                if node in nodes_used:
                    warnings.append(f"Nodo duplicado detectado: {node}")
                else:
                    nodes_used.add(node)

        # Verificar componentes desconectados
        connected_nodes = set()
        for net in circuit_data.get("nets", []):
            for node in net["nodes"]:
                connected_nodes.add(node.split('.')[0])  # Solo el ID del componente
        
        component_ids = {comp["id"] for comp in circuit_data.get("components", [])}
        disconnected = component_ids - connected_nodes
        for comp_id in disconnected:
            warnings.append(f"Componente {comp_id} no está conectado en ninguna red")

        return warnings

    def get_circuit_by_id(self, design_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un circuito previamente guardado por su ID."""
        return self.circuit_manager.get_design(design_id)

    def list_all_circuits(self) -> List[Dict[str, Any]]:
        """Lista todos los circuitos guardados."""
        return self.circuit_manager.list_designs()
