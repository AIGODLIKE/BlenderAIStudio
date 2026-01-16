from .ime import IMEManager


class LinuxIMEManager(IMEManager):
    def enable_ime(self) -> bool:
        return False

    def disable_ime(self) -> bool:
        return False

    def get_composition_string(self) -> str:
        return ""

    def set_composition_position(self, x: int, y: int):
        pass
