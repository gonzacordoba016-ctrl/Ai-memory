# database/hardware_memory.py
#
# Facade: importa las 4 clases de tabla y expone la misma interfaz pública
# que tenía HardwareMemory antes del refactoring.
# Todos los callers externos usan esta clase sin modificaciones.

from database.hardware_devices  import HardwareDevicesDB
from database.hardware_firmware import HardwareFirmwareDB
from database.hardware_circuits import HardwareCircuitsDB
from database.hardware_projects import HardwareProjectsDB


class HardwareMemory:

    def __init__(self):
        self._devices  = HardwareDevicesDB()
        self._firmware = HardwareFirmwareDB()
        self._circuits = HardwareCircuitsDB()
        self._projects = HardwareProjectsDB()

    # ======================
    # DISPOSITIVOS
    # ======================

    def register_device(self, device: dict, user_id: str = "default"):
        return self._devices.register_device(device, user_id)

    def get_all_devices(self, user_id: str = "default") -> list[dict]:
        return self._devices.get_all_devices(user_id)

    def get_device_info(self, device_name: str, user_id: str = "default") -> dict | None:
        return self._devices.get_device_info(device_name, user_id)

    # ======================
    # FIRMWARE
    # ======================

    def save_firmware(self, device_name: str, task: str, code: str,
                      filename: str = "", success: bool = True,
                      serial_out: str = "", notes: str = "", user_id: str = "default"):
        self._firmware.save_firmware(
            device_name, task, code, filename, success, serial_out, notes, user_id
        )
        if success and code:
            self._projects._auto_save_to_library(task, code, device_name)

    def get_device_history(self, device_name: str, limit: int = 10) -> list[dict]:
        return self._firmware.get_device_history(device_name, limit)

    def get_current_firmware(self, device_name: str) -> dict | None:
        return self._firmware.get_current_firmware(device_name)

    def get_recent_failures(self, device_name: str, limit: int = 3) -> list[str]:
        return self._firmware.get_recent_failures(device_name, limit)

    def get_similar_firmware(self, task: str, limit: int = 3) -> list[dict]:
        return self._firmware.get_similar_firmware(task, limit)

    # ======================
    # ESTADÍSTICAS
    # ======================

    def get_stats(self) -> dict:
        devices  = self._devices.count()
        total    = self._firmware.count_total()
        success  = self._firmware.count_success()
        library  = self._projects.count()
        circuits = self._circuits.count()
        return {
            "devices":       devices,
            "total_flashes": total,
            "successful":    success,
            "failed":        total - success,
            "library":       library,
            "circuits":      circuits,
        }

    # ======================
    # CONTEXTO DEL CIRCUITO
    # ======================

    def save_circuit_context(self, device_name: str, context: dict, user_id: str = "default") -> bool:
        return self._circuits.save_circuit_context(device_name, context, user_id)

    def get_circuit_context(self, device_name: str, user_id: str = "default") -> dict | None:
        return self._circuits.get_circuit_context(device_name, user_id)

    def get_all_circuits(self, user_id: str = "default") -> list[dict]:
        return self._circuits.get_all_circuits(user_id)

    def get_circuit_history(self, device_name: str) -> list[dict]:
        return self._circuits.get_circuit_history(device_name)

    def update_circuit_note(self, device_name: str, note: str) -> bool:
        return self._circuits.update_circuit_note(device_name, note)

    def format_circuit_for_prompt(self, device_name: str) -> str:
        return self._circuits.format_circuit_for_prompt(device_name)

    # ======================
    # BIBLIOTECA DE PROYECTOS
    # ======================

    def save_to_library(self, name: str, description: str, code: str,
                        platform: str, tags: list[str] = []) -> int:
        return self._projects.save_to_library(name, description, code, platform, tags)

    def search_library(self, query: str, platform: str = None) -> list[dict]:
        return self._projects.search_library(query, platform)

    def get_library(self, platform: str = None) -> list[dict]:
        return self._projects.get_library(platform)

    def use_from_library(self, project_id: int) -> dict | None:
        return self._projects.use_from_library(project_id)

    def delete_from_library(self, project_id: int) -> bool:
        return self._projects.delete_from_library(project_id)


hardware_memory = HardwareMemory()
