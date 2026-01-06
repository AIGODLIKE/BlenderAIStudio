import sys
from .ime import IMEManager


class DummyIMEManager(IMEManager):
    pass


def create_ime_manager() -> IMEManager:
    """工厂函数创建平台特定的IME管理器"""
    if sys.platform == "darwin":
        from .macosx import MacOSIMEManager

        return MacOSIMEManager()
    elif sys.platform == "win32":
        from .windows import WindowsIMEManager

        return WindowsIMEManager()
    elif sys.platform.startswith("linux"):
        from .linux import LinuxIMEManager

        return LinuxIMEManager()
    else:
        return DummyIMEManager()


# 全局输入法管理器实例
input_manager = create_ime_manager()
