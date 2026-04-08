# tools/schematic_renderer.py

import svgwrite
from typing import Dict, Any, List, Tuple
import math
from core.logger import get_logger

logger = get_logger(__name__)

class SchematicRenderer:
    def __init__(self):
        self.component_symbols = {
            'resistor': self._draw_resistor,
            'led': self._draw_led,
            'capacitor': self._draw_capacitor,
            'arduino_uno': self._draw_arduino_uno,
            'button': self._draw_button,
            'generic': self._draw_generic_component
        }

    def render_schematic_svg(self, circuit_data: Dict[str, Any], width: int = 800, height: int = 600) -> str:
        """
        Renderiza un esquemático SVG a partir de los datos del circuito.
        """
        try:
            dwg = svgwrite.Drawing(size=(width, height))
            
            # Fondo
            dwg.add(dwg.rect(insert=(0, 0), size=(width, height), fill='#1e1e1e'))
            
            # Título del circuito
            title = circuit_data.get('name', 'Circuito sin nombre')
            dwg.add(dwg.text(title, insert=(20, 30), font_size=20, fill='white', font_family='Arial'))
            
            # Descripción
            desc = circuit_data.get('description', '')
            dwg.add(dwg.text(desc, insert=(20, 55), font_size=14, fill='#cccccc', font_family='Arial'))
            
            # Posicionar componentes: usar posiciones guardadas si existen
            saved_positions = circuit_data.get("positions", {})
            if saved_positions:
                positions = {
                    comp_id: (p["x"], p["y"])
                    for comp_id, p in saved_positions.items()
                    if isinstance(p, dict) and "x" in p and "y" in p
                }
                # Para componentes sin posición guardada, calcular automáticamente
                missing = [c for c in circuit_data['components'] if c['id'] not in positions]
                if missing:
                    auto = self._calculate_component_positions(missing, width, height)
                    positions.update(auto)
            else:
                positions = self._calculate_component_positions(circuit_data['components'], width, height)

            # Dibujar componentes con id en el elemento SVG para drag & drop
            for comp in circuit_data['components']:
                pos = positions.get(comp['id'], (100, 100))
                self._draw_component(dwg, comp, pos)
            
            # Dibujar conexiones (nets)
            self._draw_connections(dwg, circuit_data.get('nets', []), positions)
            
            # Leyenda
            self._add_legend(dwg, width, height)
            
            return dwg.tostring()
            
        except Exception as e:
            logger.error(f"Error renderizando esquemático: {str(e)}")
            # Retornar SVG de error
            error_dwg = svgwrite.Drawing(size=(width, height))
            error_dwg.add(error_dwg.rect(insert=(0, 0), size=(width, height), fill='#1e1e1e'))
            error_dwg.add(error_dwg.text("Error generando esquemático", insert=(50, 50), 
                                       font_size=20, fill='red', font_family='Arial'))
            return error_dwg.tostring()

    def _calculate_component_positions(self, components: List[Dict], width: int, height: int) -> Dict[str, Tuple[int, int]]:
        """Calcula posiciones óptimas para los componentes."""
        positions = {}
        grid_x, grid_y = 80, 80
        margin_x, margin_y = 100, 100
        cols = max(1, (width - 2*margin_x) // grid_x)
        
        for i, comp in enumerate(components):
            col = i % cols
            row = i // cols
            x = margin_x + col * grid_x
            y = margin_y + row * grid_y
            positions[comp['id']] = (x, y)
            
        return positions

    def _draw_component(self, dwg, component: Dict[str, Any], position: Tuple[int, int]):
        """Dibuja un componente individual."""
        x, y = position
        comp_type = component.get('resolved_type', component.get('type', 'generic'))
        
        # Dibujar marco del componente
        rect = dwg.rect(insert=(x-25, y-15), size=(50, 30), 
                        fill='#2d2d2d', stroke='#00ff00', stroke_width=1)
        dwg.add(rect)
        
        # Dibujar símbolo específico si existe
        draw_func = self.component_symbols.get(comp_type, self._draw_generic_component)
        draw_func(dwg, x, y, component)
        
        # Etiqueta del componente
        label = f"{component['id']}: {component.get('name', comp_type)}"
        dwg.add(dwg.text(label, insert=(x-25, y+45), font_size=10, fill='white', font_family='Arial'))

    def _draw_resistor(self, dwg, x: int, y: int, component: Dict[str, Any]):
        """Dibuja el símbolo de una resistencia."""
        # Zigzag de resistencia
        points = [(x-20, y), (x-15, y-5), (x-10, y+5), (x-5, y-5), 
                  (x, y+5), (x+5, y-5), (x+10, y+5), (x+15, y-5), (x+20, y)]
        line = dwg.polyline(points, stroke='white', fill='none', stroke_width=2)
        dwg.add(line)
        
        # Valor si existe
        value = component.get('value', '')
        unit = component.get('unit', '')
        if value:
            dwg.add(dwg.text(f"{value}{unit}", insert=(x-15, y-20), 
                           font_size=8, fill='#ffff00', font_family='Arial'))

    def _draw_led(self, dwg, x: int, y: int, component: Dict[str, Any]):
        """Dibuja el símbolo de un LED."""
        # Triángulo del diodo
        points = [(x-15, y-10), (x+15, y), (x-15, y+10)]
        triangle = dwg.polygon(points, fill='none', stroke='white', stroke_width=2)
        dwg.add(triangle)
        
        # Flechas de luz
        dwg.add(dwg.line(start=(x+18, y-8), end=(x+25, y-15), 
                        stroke='#ffff00', stroke_width=1))
        dwg.add(dwg.line(start=(x+20, y-5), end=(x+27, y-12), 
                        stroke='#ffff00', stroke_width=1))
        dwg.add(dwg.line(start=(x+22, y-2), end=(x+29, y-9), 
                        stroke='#ffff00', stroke_width=1))

    def _draw_capacitor(self, dwg, x: int, y: int, component: Dict[str, Any]):
        """Dibuja el símbolo de un capacitor."""
        # Dos líneas paralelas
        dwg.add(dwg.line(start=(x-10, y-15), end=(x-10, y+15), 
                        stroke='white', stroke_width=2))
        dwg.add(dwg.line(start=(x+10, y-15), end=(x+10, y+15), 
                        stroke='white', stroke_width=2))
        # Línea de conexión
        dwg.add(dwg.line(start=(x-10, y), end=(x+10, y), 
                        stroke='white', stroke_width=2))

    def _draw_arduino_uno(self, dwg, x: int, y: int, component: Dict[str, Any]):
        """Dibuja el símbolo de Arduino Uno."""
        # Rectángulo principal
        rect = dwg.rect(insert=(x-30, y-20), size=(60, 40), 
                        fill='#334455', stroke='white', stroke_width=2)
        dwg.add(rect)
        
        # Etiqueta
        dwg.add(dwg.text("ARDUINO", insert=(x-25, y-5), 
                       font_size=8, fill='white', font_family='Arial'))
        dwg.add(dwg.text("UNO", insert=(x-15, y+5), 
                       font_size=8, fill='white', font_family='Arial'))

    def _draw_button(self, dwg, x: int, y: int, component: Dict[str, Any]):
        """Dibuja el símbolo de un botón."""
        # Dos líneas paralelas separadas
        dwg.add(dwg.line(start=(x-15, y-5), end=(x-5, y-5), 
                        stroke='white', stroke_width=2))
        dwg.add(dwg.line(start=(x+5, y-5), end=(x+15, y-5), 
                        stroke='white', stroke_width=2))
        # Puntos de conexión
        dwg.add(dwg.circle(center=(x-15, y-5), r=2, fill='white'))
        dwg.add(dwg.circle(center=(x+15, y-5), r=2, fill='white'))

    def _draw_generic_component(self, dwg, x: int, y: int, component: Dict[str, Any]):
        """Dibuja un componente genérico."""
        rect = dwg.rect(insert=(x-20, y-10), size=(40, 20), 
                        fill='#444444', stroke='white', stroke_width=1)
        dwg.add(rect)
        # Cruz en el centro
        dwg.add(dwg.line(start=(x-10, y), end=(x+10, y), 
                        stroke='white', stroke_width=1))
        dwg.add(dwg.line(start=(x, y-10), end=(x, y+10), 
                        stroke='white', stroke_width=1))

    def _draw_connections(self, dwg, nets: List[Dict], positions: Dict[str, Tuple[int, int]]):
        """Dibuja las conexiones entre componentes."""
        colors = ['#ff5555', '#55ff55', '#5555ff', '#ffff55', '#ff55ff']
        
        for i, net in enumerate(nets):
            color = colors[i % len(colors)]
            nodes = net.get('nodes', [])
            
            if len(nodes) < 2:
                continue
                
            # Convertir nodos a coordenadas
            coords = []
            for node in nodes:
                comp_id = node.split('.')[0]
                if comp_id in positions:
                    coords.append(positions[comp_id])
            
            if len(coords) >= 2:
                # Dibujar líneas entre puntos
                for j in range(len(coords)-1):
                    start = coords[j]
                    end = coords[j+1]
                    dwg.add(dwg.line(start=start, end=end, 
                                    stroke=color, stroke_width=2))
                
                # Etiqueta de la red
                mid_x = sum(c[0] for c in coords) / len(coords)
                mid_y = sum(c[1] for c in coords) / len(coords) - 20
                dwg.add(dwg.text(net.get('name', f'Net{i}'), 
                               insert=(mid_x, mid_y), 
                               font_size=10, fill=color, font_family='Arial'))

    def _add_legend(self, dwg, width: int, height: int):
        """Agrega leyenda con colores de redes."""
        legend_x, legend_y = width - 150, height - 80
        dwg.add(dwg.text("Leyenda:", insert=(legend_x, legend_y), 
                       font_size=12, fill='white', font_family='Arial'))
        
        # Colores de ejemplo
        colors = ['#ff5555', '#55ff55', '#5555ff', '#ffff55']
        labels = ['VCC', 'GND', 'Señal', 'Control']
        
        for i, (color, label) in enumerate(zip(colors, labels)):
            y_pos = legend_y + 20 + i*15
            dwg.add(dwg.rect(insert=(legend_x, y_pos-8), size=(12, 8), fill=color))
            dwg.add(dwg.text(label, insert=(legend_x+20, y_pos), 
                           font_size=10, fill='white', font_family='Arial'))
