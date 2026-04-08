# tools/pcb_renderer.py

from typing import Dict, Any, List, Tuple
import xml.etree.ElementTree as ET
from core.logger import get_logger

logger = get_logger(__name__)

class PCBRenderer:
    def __init__(self):
        self.mm_to_px = 3.7795275591  # Conversión de mm a pixels (96 DPI)
        self.board_thickness = 1.6  # mm

    def render_pcb_svg(self, circuit_data: Dict[str, Any]) -> str:
        """
        Genera un layout PCB en formato SVG para fabricación.
        """
        try:
            # Dimensiones del PCB (basadas en componentes)
            width_mm, height_mm = self._calculate_pcb_dimensions(circuit_data)
            
            # Crear SVG
            svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" 
                                width="{width_mm * self.mm_to_px}" 
                                height="{height_mm * self.mm_to_px}" 
                                viewBox="0 0 {width_mm} {height_mm}">
                <defs>
                    <style>
                        .pcb-board {{ fill: #336699; }}
                        .copper {{ fill: #b87333; }}
                        .silkscreen {{ fill: none; stroke: white; stroke-width: 0.1; }}
                        .drill {{ fill: black; }}
                    </style>
                </defs>
                
                <!-- Board outline -->
                <rect x="0" y="0" width="{width_mm}" height="{height_mm}" class="pcb-board" />
                
                <!-- Copper layers -->
                {self._render_copper_traces(circuit_data)}
                
                <!-- Components -->
                {self._render_components_pcb(circuit_data)}
                
                <!-- Silkscreen -->
                {self._render_silkscreen(circuit_data)}
                
                <!-- Drill holes -->
                {self._render_drill_holes(circuit_data)}
            </svg>'''
            
            return svg_content
            
        except Exception as e:
            logger.error(f"Error generando PCB SVG: {str(e)}")
            return f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><text x="10" y="50" fill="red">Error: {str(e)}</text></svg>'

    def _calculate_pcb_dimensions(self, circuit_data: Dict[str, Any]) -> Tuple[float, float]:
        """Calcula dimensiones óptimas del PCB."""
        # Basado en componentes y espacio necesario
        components = circuit_data.get("components", [])
        num_components = len(components)
        
        # Estimación simple: 20mm por componente + margen
        width = max(30, num_components * 10)  # mm
        height = max(20, num_components * 8)   # mm
        
        return (width + 10, height + 10)

    def _render_copper_traces(self, circuit_data: Dict[str, Any]) -> str:
        """Renderiza las trazas de cobre."""
        traces = []
        
        for i, net in enumerate(circuit_data.get("nets", [])):
            nodes = net.get("nodes", [])
            if len(nodes) < 2:
                continue
                
            # Crear trazas entre nodos
            for j in range(len(nodes) - 1):
                x1, y1 = 20 + j * 15, 20 + i * 10
                x2, y2 = 35 + j * 15, 20 + i * 10
                
                trace = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#b87333" stroke-width="0.8" />'
                traces.append(trace)
                
        return "\n".join(traces)

    def _render_components_pcb(self, circuit_data: Dict[str, Any]) -> str:
        """Renderiza componentes en el PCB."""
        components = []
        
        for i, component in enumerate(circuit_data.get("components", [])):
            x = 20 + (i % 6) * 15
            y = 20 + (i // 6) * 15
            
            comp_type = component.get("resolved_type", component.get("type"))
            
            if comp_type == "resistor":
                comp_svg = f'<rect x="{x-3}" y="{y-1}" width="6" height="2" fill="#cc6600" />'
            elif comp_type == "led":
                comp_svg = f'<circle cx="{x}" cy="{y}" r="2" fill="{component.get("color", "#ff0000")}" />'
            elif comp_type == "capacitor":
                comp_svg = f'<rect x="{x-2}" y="{y-3}" width="4" height="6" fill="#ffffff" stroke="#000000" />'
            else:
                comp_svg = f'<rect x="{x-2.5}" y="{y-2.5}" width="5" height="5" fill="#888888" />'
                
            components.append(comp_svg)
            
        return "\n".join(components)

    def _render_silkscreen(self, circuit_data: Dict[str, Any]) -> str:
        """Renderiza la serigrafía del PCB."""
        silkscreen = []
        
        # Borde del PCB
        width_mm, height_mm = self._calculate_pcb_dimensions(circuit_data)
        border = f'<rect x="1" y="1" width="{width_mm-2}" height="{height_mm-2}" class="silkscreen" />'
        silkscreen.append(border)
        
        # Etiquetas de componentes
        for i, component in enumerate(circuit_data.get("components", [])):
            x = 20 + (i % 6) * 15
            y = 20 + (i // 6) * 15 + 8
            
            label = f'<text x="{x}" y="{y}" font-size="2" fill="white" text-anchor="middle">{component["id"]}</text>'
            silkscreen.append(label)
            
        return "\n".join(silkscreen)

    def _render_drill_holes(self, circuit_data: Dict[str, Any]) -> str:
        """Renderiza los agujeros de perforación."""
        holes = []
        
        # Agujeros para cada componente (simplificado)
        for i, component in enumerate(circuit_data.get("components", [])):
            x = 20 + (i % 6) * 15
            y = 20 + (i // 6) * 15
            
            # Dos agujeros por componente (TH)
            hole1 = f'<circle cx="{x-1.5}" cy="{y}" r="0.5" class="drill" />'
            hole2 = f'<circle cx="{x+1.5}" cy="{y}" r="0.5" class="drill" />'
            
            holes.extend([hole1, hole2])
            
        return "\n".join(holes)

    def generate_gerber_files(self, circuit_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Genera archivos Gerber para fabricación profesional.
        Retorna diccionario con contenidos de archivos.
        """
        try:
            gerber_files = {}
            
            # GBO - Bottom Copper Layer
            gerber_files["copper_bottom.gbr"] = self._generate_copper_layer(circuit_data, "bottom")
            
            # GTL - Top Copper Layer
            gerber_files["copper_top.gbr"] = self._generate_copper_layer(circuit_data, "top")
            
            # GTO - Top Silkscreen
            gerber_files["silkscreen_top.gto"] = self._generate_silkscreen_layer(circuit_data)
            
            # GBL - Bottom Soldermask
            gerber_files["soldermask_bottom.gbo"] = self._generate_soldermask_layer(circuit_data)
            
            # TXT - Drill file
            gerber_files["drills.txt"] = self._generate_drill_file(circuit_data)
            
            # GKO - Outline
            gerber_files["outline.gko"] = self._generate_outline_file(circuit_data)
            
            return gerber_files
            
        except Exception as e:
            logger.error(f"Error generando archivos Gerber: {str(e)}")
            return {"error.log": f"Error generating Gerber files: {str(e)}"}

    def _generate_copper_layer(self, circuit_data: Dict[str, Any], layer: str) -> str:
        """Genera capa de cobre en formato Gerber."""
        # Formato Gerber simplificado
        gerber = "G04 Gerber File *\n"
        gerber += "%FSLAX26Y26*%\n"  # Format specification
        gerber += "G01*\n"  # Linear interpolation
        
        # Contenido de trazas (simplificado)
        for i, net in enumerate(circuit_data.get("nets", [])):
            gerber += f"D{i+10}* X{i*100000} Y{i*100000} D02*\n"  # Move to start
            gerber += f"X{(i+1)*100000} Y{(i+1)*100000} D01*\n"    # Draw line
            
        gerber += "M02*"  # End of file
        return gerber

    def _generate_silkscreen_layer(self, circuit_data: Dict[str, Any]) -> str:
        """Genera capa de serigrafía en formato Gerber."""
        gerber = "G04 Silkscreen Layer *\n"
        gerber += "%FSLAX26Y26*%\n"
        gerber += "G01*\n"
        
        # Etiquetas de componentes
        for i, component in enumerate(circuit_data.get("components", [])):
            x = i * 100000
            y = i * 100000
            text = component.get("id", "CMP")
            gerber += f"X{x} Y{y} D02*G04 {text}*\n"
            
        gerber += "M02*"
        return gerber

    def _generate_soldermask_layer(self, circuit_data: Dict[str, Any]) -> str:
        """Genera capa de máscara de soldadura en formato Gerber."""
        gerber = "G04 Soldermask Layer *\n"
        gerber += "%FSLAX26Y26*%\n"
        gerber += "G01*\n"
        
        # Cubrir todo con máscara verde (simplificado)
        width_mm, height_mm = self._calculate_pcb_dimensions(circuit_data)
        gerber += f"X0 Y0 D02*X{int(width_mm*1000)} Y0 D01*X{int(width_mm*1000)} Y{int(height_mm*1000)} D01*X0 Y{int(height_mm*1000)} D01*X0 Y0 D01*\n"
        
        gerber += "M02*"
        return gerber

    def _generate_drill_file(self, circuit_data: Dict[str, Any]) -> str:
        """Genera archivo de perforaciones en formato Excellon."""
        excellon = "M48\n"
        excellon += "FMAT,2\n"
        excellon += "ICI,OFF\n"
        
        # Herramientas
        excellon += "T1C0.8\n"  # Taladro de 0.8mm
        excellon += "%\n"
        excellon += "T1\n"
        
        # Posiciones de agujeros
        for i, component in enumerate(circuit_data.get("components", [])):
            x = 10.0 + (i % 6) * 5.0
            y = 10.0 + (i // 6) * 5.0
            excellon += f"X{x:.3f}Y{y:.3f}\n"
            
        excellon += "M30\n"
        return excellon

    def _generate_outline_file(self, circuit_data: Dict[str, Any]) -> str:
        """Genera archivo de contorno del PCB."""
        width_mm, height_mm = self._calculate_pcb_dimensions(circuit_data)
        
        gerber = "G04 Outline Layer *\n"
        gerber += "%FSLAX26Y26*%\n"
        gerber += "G01*\n"
        
        # Rectángulo del contorno
        gerber += f"X0 Y0 D02*X{width_mm*1000} Y0 D01*X{width_mm*1000} Y{height_mm*1000} D01*X0 Y{height_mm*1000} D01*X0 Y0 D01*\n"
        
        gerber += "M02*"
        return gerber
