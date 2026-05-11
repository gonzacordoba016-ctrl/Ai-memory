# tools/breadboard_renderer.py

from typing import Dict, Any, List, Tuple
import json
from core.logger import get_logger
from tools.design_rules import get_sheet_size
from tools.eda.pcb_draw import _compute_pcb_placement

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
        components = circuit_data.get("components", [])
        placement = self._compute_3d_placement(components, circuit_data.get("nets", []))
        
        for i, component in enumerate(components):
            x, y = placement.get(component["id"], (100 + (i % 8) * 50, 100 + (i // 8) * 50))
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

    def _compute_3d_placement(
        self,
        components: List[Dict[str, Any]],
        nets: List[Dict[str, Any]],
    ) -> Dict[str, Tuple[float, float]]:
        """Reusa el placement PCB y lo centra para la escena 3D."""
        if not components:
            return {}
        try:
            pcb_pos = _compute_pcb_placement(components, nets, get_sheet_size(len(components)))
        except Exception as exc:
            logger.warning(f"[3D] fallback placement: {exc}")
            return {}
        if not pcb_pos:
            return {}
        xs = [p[0] for p in pcb_pos.values()]
        ys = [p[1] for p in pcb_pos.values()]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        return {cid: (x - cx, y - cy) for cid, (x, y) in pcb_pos.items()}

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
            "esp32": {
                "geometry": "esp32_devkit",
                "material": {"color": "#0a2f4f", "shield": "#b8bec6",
                             "headers": "#d4a017", "antenna": "#c8a000",
                             "usb": "#888888", "silkscreen": "ESP32"},
                "dimensions": {"width": 25, "height": 48, "depth": 1.5}
            },
            "bmp280": {
                "geometry": "bmp280_breakout",
                "material": {"color": "#0a5c0a", "die": "#050505",
                             "pads": "#d4a017", "silkscreen": "BMP280"},
                "dimensions": {"width": 14, "height": 14, "depth": 1}
            },
            "dht22": {
                "geometry": "dht22",
                "material": {"color": "#f4f4f0", "slots": "#111111",
                             "pins": "#c0c0c0", "silkscreen": "DHT22"},
                "dimensions": {"width": 15, "height": 25, "depth": 7}
            },
            "mpu6050": {
                "geometry": "mpu6050_breakout",
                "material": {"color": "#0033aa", "die": "#050505",
                             "pads": "#d4a017", "silkscreen": "MPU6050"},
                "dimensions": {"width": 20, "height": 20, "depth": 1}
            },
            "ds18b20": {
                "geometry": "to92",
                "material": {"color": "#111111", "pins": "#c0c0c0",
                             "silkscreen": "DS18B20"},
                "dimensions": {"radius": 2.5, "height": 4.5, "pin_length": 8}
            },
            "hc_sr04": {
                "geometry": "hc_sr04",
                "material": {"color": "#0a5c0a", "transducers": "#c0c0c0",
                             "pins": "#d4a017", "silkscreen": "HC-SR04"},
                "dimensions": {"width": 45, "height": 20, "depth": 1}
            },
            "relay": {
                "geometry": "relay_module",
                "material": {"color": "#0a5c0a", "relay": "#111111",
                             "coil": "#8a4a22", "led": "#cc1111"},
                "dimensions": {"width": 50, "height": 26, "depth": 1}
            },
            "relay_module": {
                "geometry": "relay_module",
                "material": {"color": "#0a5c0a", "relay": "#111111",
                             "coil": "#8a4a22", "led": "#cc1111"},
                "dimensions": {"width": 50, "height": 26, "depth": 1}
            },
            "nrf24l01": {
                "geometry": "nrf24l01",
                "material": {"color": "#0033aa", "chip": "#050505",
                             "antenna": "#c8a000", "silkscreen": "NRF24L01"},
                "dimensions": {"width": 15, "height": 29, "depth": 1}
            },
            "oled": {
                "geometry": "oled_128x64",
                "material": {"color": "#111111", "screen": "#001133",
                             "pixels": "#0088ff", "pins": "#d4a017"},
                "dimensions": {"width": 27, "height": 27, "depth": 2}
            },
            "lcd": {
                "geometry": "lcd_i2c_16x2",
                "material": {"color": "#0a5c0a", "display": "#a8d65a",
                             "characters": "#3a2a10", "pins": "#d4a017"},
                "dimensions": {"width": 80, "height": 36, "depth": 1}
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
        positions = self._compute_3d_placement(
            circuit_data.get("components", []),
            circuit_data.get("nets", []),
        )
        
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
                "paths": self._calculate_wire_paths(nodes, positions, net.get("name", "")),
                "type": "jumper"  # Tipo de cable
            }
            
            wires.append(wire)
            
        return wires

    def _calculate_wire_paths(
        self,
        nodes: List[str],
        positions: Dict[str, Tuple[float, float]],
        net_name: str = "",
    ) -> List[Dict[str, Any]]:
        """Calcula las rutas de los cables entre nodos."""
        # Esta sería una implementación simplificada
        # En realidad necesitaría mapear nodos a pines específicos
        paths = []
        nl = net_name.lower()
        radius = 0.8 if any(k in nl for k in ("gnd", "vcc", "5v", "3v3", "vin")) else 0.4
        
        # Por simplicidad, conectamos puntos medios
        for i in range(len(nodes) - 1):
            # Coordenadas dummy para demostración
            id1 = nodes[i].split(".")[0]
            id2 = nodes[i + 1].split(".")[0]
            if id1 not in positions or id2 not in positions:
                continue
            x1, y1 = positions[id1]
            x2, y2 = positions[id2]
            paths.append({
                "radius": radius,
                "points": [
                    [x1, y1, 1],
                    [x1, y1, 5],
                    [x2, y2, 5],
                    [x2, y2, 1],
                ],
            })
            
        return paths
