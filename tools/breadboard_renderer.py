# tools/breadboard_renderer.py

from typing import Dict, Any, List, Tuple
import json
from core.logger import get_logger

logger = get_logger(__name__)

class BreadboardRenderer:
    def __init__(self):
        # Dimensiones estándar de breadboard
        self.BOARD_WIDTH = 830   # mm aproximado
        self.BOARD_HEIGHT = 530  # mm aproximado
        self.HOLE_SPACING = 2.54 # mm entre agujeros
        self.HOLES_PER_ROW = 63
        self.POWER_RAILS_HEIGHT = 40

    def render_breadboard_3d(self, circuit_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera datos para renderizar breadboard en 3D (compatible con Three.js).
        Retorna un diccionario con geometrías y posiciones.
        """
        try:
            # Preparar datos para Three.js
            scene_data = {
                "board": self._generate_board_geometry(),
                "components": self._place_components_3d(circuit_data),
                "wires": self._generate_wires_3d(circuit_data),
                "metadata": {
                    "title": circuit_data.get("name", "Circuito sin nombre"),
                    "description": circuit_data.get("description", "")
                }
            }
            
            return scene_data
            
        except Exception as e:
            logger.error(f"Error generando escena 3D: {str(e)}")
            return {
                "error": True,
                "message": f"Error al generar vista 3D: {str(e)}"
            }

    def _generate_board_geometry(self) -> Dict[str, Any]:
        """Genera la geometría base del breadboard."""
        return {
            "type": "breadboard",
            "dimensions": {
                "width": self.BOARD_WIDTH,
                "height": self.BOARD_HEIGHT,
                "thickness": 10  # mm
            },
            "holes": self._generate_holes_pattern(),
            "power_rails": self._generate_power_rails(),
            "material": {
                "color": "#f0d9b5",
                "texture": "plastic"
            }
        }

    def _generate_holes_pattern(self) -> List[Dict[str, Any]]:
        """Genera patrón de agujeros para el breadboard."""
        holes = []
        
        # Agujeros principales (filas a-e y f-j)
        for row_group in range(2):  # Grupo superior e inferior
            for row in range(5):    # Filas a-e
                for col in range(self.HOLES_PER_ROW):
                    x = col * self.HOLE_SPACING + 30  # Margen izquierdo
                    y = row * self.HOLE_SPACING + 50 + (row_group * 200)  # Posición vertical
                    
                    hole = {
                        "id": f"{chr(97+row+(row_group*5))}{col+1}",
                        "position": [x, y, 0],
                        "connected": False,
                        "component": None
                    }
                    holes.append(hole)
                    
        return holes

    def _generate_power_rails(self) -> List[Dict[str, Any]]:
        """Genera rieles de poder (+ y -)."""
        rails = []
        
        # Riel positivo (rojo)
        rails.append({
            "id": "positive_rail",
            "start": [30, 20, 0],
            "end": [30 + (self.HOLES_PER_ROW * self.HOLE_SPACING), 20, 0],
            "color": "#ff0000",
            "label": "+"
        })
        
        # Riel negativo (azul)
        rails.append({
            "id": "negative_rail",
            "start": [30, self.BOARD_HEIGHT - 20, 0],
            "end": [30 + (self.HOLES_PER_ROW * self.HOLE_SPACING), self.BOARD_HEIGHT - 20, 0],
            "color": "#0000ff",
            "label": "-"
        })
        
        return rails

    def _place_components_3d(self, circuit_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Coloca componentes en coordenadas 3D."""
        components_3d = []
        
        # Asignar posiciones iniciales (esto sería más sofisticado en producción)
        base_x, base_y = 100, 100
        spacing = 50
        
        for i, component in enumerate(circuit_data.get("components", [])):
            x = base_x + (i % 8) * spacing
            y = base_y + (i // 8) * spacing
            z = 5  # Altura sobre el breadboard
            
            comp_3d = {
                "id": component["id"],
                "type": component.get("resolved_type", component.get("type")),
                "name": component.get("name"),
                "position": [x, y, z],
                "rotation": [0, 0, 0],
                "scale": [1, 1, 1],
                "model": self._get_component_model(component),
                "pins": self._get_component_pins(component)
            }
            
            components_3d.append(comp_3d)
            
        return components_3d

    def _get_component_model(self, component: Dict[str, Any]) -> Dict[str, Any]:
        """Obtiene el modelo 3D para un componente."""
        comp_type = component.get("resolved_type", component.get("type"))
        
        models = {
            "resistor": {
                "geometry": "cylinder",
                "material": {"color": "#cc6600"},
                "dimensions": {"radius": 1, "height": 10}
            },
            "led": {
                "geometry": "cylinder",
                "material": {"color": component.get("color", "#ff0000")},
                "dimensions": {"radius": 1.5, "height": 8}
            },
            "capacitor": {
                "geometry": "cylinder",
                "material": {"color": "#ffffff"},
                "dimensions": {"radius": 2, "height": 12}
            },
            "arduino_uno": {
                "geometry": "box",
                "material": {"color": "#334455"},
                "dimensions": {"width": 70, "height": 50, "depth": 5}
            },
            "button": {
                "geometry": "box",
                "material": {"color": "#aaaaaa"},
                "dimensions": {"width": 8, "height": 8, "depth": 5}
            }
        }
        
        return models.get(comp_type, {
            "geometry": "box",
            "material": {"color": "#888888"},
            "dimensions": {"width": 10, "height": 5, "depth": 5}
        })

    def _get_component_pins(self, component: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Define los pines de conexión para un componente."""
        comp_type = component.get("resolved_type", component.get("type"))
        
        pin_configs = {
            "resistor": [
                {"id": "1", "position": [-5, 0, 0], "connection": None},
                {"id": "2", "position": [5, 0, 0], "connection": None}
            ],
            "led": [
                {"id": "A", "position": [0, -4, 0], "connection": None},  # Ánodo
                {"id": "K", "position": [0, 4, 0], "connection": None}   # Cátodo
            ],
            "capacitor": [
                {"id": "1", "position": [0, -6, 0], "connection": None},
                {"id": "2", "position": [0, 6, 0], "connection": None}
            ],
            "arduino_uno": self._get_arduino_pins(),
            "button": [
                {"id": "1", "position": [-4, -4, 0], "connection": None},
                {"id": "2", "position": [4, -4, 0], "connection": None}
            ]
        }
        
        return pin_configs.get(comp_type, [])

    def _get_arduino_pins(self) -> List[Dict[str, Any]]:
        """Define los pines del Arduino Uno."""
        pins = []
        # Pines digitales (2-13)
        for i in range(2, 14):
            pins.append({
                "id": str(i),
                "position": [-30 + (i-2)*5, -25, 0],
                "connection": None
            })
        
        # Pines analógicos (A0-A5)
        for i in range(6):
            pins.append({
                "id": f"A{i}",
                "position": [-30 + i*5, 25, 0],
                "connection": None
            })
            
        return pins

    def _generate_wires_3d(self, circuit_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Genera conexiones entre componentes basadas en nets."""
        wires = []
        colors = ["#ff5555", "#55ff55", "#5555ff", "#ffff55", "#ff55ff"]
        
        for i, net in enumerate(circuit_data.get("nets", [])):
            color = colors[i % len(colors)]
            nodes = net.get("nodes", [])
            
            if len(nodes) < 2:
                continue
                
            # En una implementación real, conectaríamos los pines específicos
            # Por ahora creamos conexiones visuales entre componentes
            wire = {
                "id": f"wire_{i}",
                "net_name": net.get("name", f"net_{i}"),
                "color": color,
                "paths": self._calculate_wire_paths(nodes, circuit_data),
                "type": "jumper"  # Tipo de cable
            }
            
            wires.append(wire)
            
        return wires

    def _calculate_wire_paths(self, nodes: List[str], circuit_data: Dict[str, Any]) -> List[List[float]]:
        """Calcula las rutas de los cables entre nodos."""
        # Esta sería una implementación simplificada
        # En realidad necesitaría mapear nodos a pines específicos
        paths = []
        
        # Por simplicidad, conectamos puntos medios
        for i in range(len(nodes) - 1):
            # Coordenadas dummy para demostración
            start = [100 + i*20, 150, 5]
            end = [120 + i*20, 150, 5]
            paths.append([start, end])
            
        return paths
