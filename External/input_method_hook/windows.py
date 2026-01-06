import ctypes

from ctypes import wintypes, POINTER, Structure, byref, c_wchar, c_long
from typing import Optional, Callable, Dict
from .ime import IMEManager

# Windows常量
WM_IME_COMPOSITION = 0x010F
WM_IME_STARTCOMPOSITION = 0x010D
WM_IME_ENDCOMPOSITION = 0x010E
WM_IME_CHAR = 0x0286

GCS_COMPSTR = 0x0008
GCS_RESULTSTR = 0x0800
GCS_CURSORPOS = 0x0080


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


class COMPOSITIONFORM(Structure):
    _fields_ = [("dwStyle", wintypes.DWORD), ("ptCurrentPos", POINT), ("rcArea", wintypes.RECT)]


class WindowsIMEManager(IMEManager):
    """轻量级Blender IME管理器，不使用独立消息循环"""

    def __init__(self):
        # 加载系统DLL
        self.user32 = ctypes.windll.user32
        self.imm32 = ctypes.windll.imm32

        # 设置函数原型
        self._setup_api()

        # 状态管理
        self.hwnd: Optional[wintypes.HWND] = None
        self.himc: Optional[wintypes.HANDLE] = None
        self.composition_string = ""
        self.result_string = ""
        self.is_composing = False
        self.is_enabled = False

        # 回调函数
        self.composition_callback: Optional[Callable[[str], None]] = None
        self.commit_callback: Optional[Callable[[str], None]] = None

        # 获取Blender窗口句柄
        self._get_blender_window()

    def _setup_api(self):
        """设置Windows API函数原型"""
        # IMM32函数
        self.imm32.ImmGetContext.argtypes = [wintypes.HWND]
        self.imm32.ImmGetContext.restype = wintypes.HANDLE

        self.imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
        self.imm32.ImmReleaseContext.restype = wintypes.BOOL

        self.imm32.ImmGetCompositionStringW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
        self.imm32.ImmGetCompositionStringW.restype = c_long

        self.imm32.ImmSetOpenStatus.argtypes = [wintypes.HANDLE, wintypes.BOOL]
        self.imm32.ImmSetOpenStatus.restype = wintypes.BOOL

        self.imm32.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
        self.imm32.ImmGetOpenStatus.restype = wintypes.BOOL

        self.imm32.ImmSetCompositionWindow.argtypes = [wintypes.HANDLE, POINTER(COMPOSITIONFORM)]
        self.imm32.ImmSetCompositionWindow.restype = wintypes.BOOL

        # User32函数
        self.user32.GetActiveWindow.restype = wintypes.HWND
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        self.user32.FindWindowW.restype = wintypes.HWND

    def _get_blender_window(self) -> bool:
        """获取Blender主窗口句柄"""
        try:
            self.hwnd = self.user32.GetForegroundWindow()

            if not self.hwnd:
                self.hwnd = self.user32.FindWindowW(None, None)  # 可以尝试特定的窗口标题

            if self.hwnd:
                print(f"Found Blender window: {self.hwnd}")
                return True
            else:
                print("Failed to find Blender window")
                return False

        except Exception as e:
            print(f"Error getting Blender window: {e}")
            return False

    def enable_ime(self) -> bool:
        """启用IME"""
        if not self.hwnd:
            if not self._get_blender_window():
                return False

        try:
            # 获取输入法上下文
            self.himc = self.imm32.ImmGetContext(self.hwnd)
            if not self.himc:
                print("Failed to get IME context")
                return False

            # 启用输入法
            result = self.imm32.ImmSetOpenStatus(self.himc, True)
            if result:
                self.is_enabled = True
                print("IME enabled successfully")
                return True
            else:
                print("Failed to enable IME")
                return False

        except Exception as e:
            print(f"Error enabling IME: {e}")
            return False

    def disable_ime(self) -> bool:
        """禁用IME"""
        try:
            if self.himc:
                # 禁用输入法
                self.imm32.ImmSetOpenStatus(self.himc, False)

                # 释放上下文
                if self.hwnd:
                    self.imm32.ImmReleaseContext(self.hwnd, self.himc)

                self.himc = None

            self.is_enabled = False
            self.is_composing = False
            self.composition_string = ""

            print("IME disabled")
            return True

        except Exception as e:
            print(f"Error disabling IME: {e}")
            return False

    def set_composition_position(self, x: int, y: int):
        """设置候选窗口位置"""
        if not self.himc:
            return False

        try:
            comp_form = COMPOSITIONFORM()
            comp_form.dwStyle = 0x0002  # CFS_POINT
            comp_form.ptCurrentPos.x = x
            comp_form.ptCurrentPos.y = y

            result = self.imm32.ImmSetCompositionWindow(self.himc, byref(comp_form))
            return bool(result)

        except Exception as e:
            print(f"Error setting composition position: {e}")
            return False

    def poll_ime_status(self) -> Dict[str, any]:
        """轮询IME状态，在Blender的modal中调用"""
        result = {
            "composition_changed": False,
            "result_available": False,
            "composition_string": "",
            "result_string": "",
        }

        if not self.himc:
            return result

        try:
            # 检查组字字符串
            comp_str = self._get_composition_string(GCS_COMPSTR)
            if comp_str != self.composition_string:
                self.composition_string = comp_str
                result["composition_changed"] = True
                result["composition_string"] = comp_str

                if comp_str:
                    self.is_composing = True
                else:
                    self.is_composing = False

            # 检查结果字符串
            result_str = self._get_composition_string(GCS_RESULTSTR)
            if result_str:
                self.result_string = result_str
                result["result_available"] = True
                result["result_string"] = result_str

                # 清空组字字符串
                self.composition_string = ""
                self.is_composing = False

        except Exception as e:
            print(f"Error polling IME status: {e}")

        return result

    def _get_composition_string(self, flag: int) -> str:
        """获取组字或结果字符串"""
        if not self.himc:
            return ""

        try:
            # 获取字符串长度（字节数）
            length = self.imm32.ImmGetCompositionStringW(self.himc, flag, None, 0)

            if length <= 0:
                return ""

            # 分配缓冲区
            buffer = (c_wchar * (length // 2))()

            # 获取实际字符串
            actual_length = self.imm32.ImmGetCompositionStringW(self.himc, flag, byref(buffer), length)

            if actual_length > 0:
                return buffer.value
            else:
                return ""

        except Exception as e:
            print(f"Error getting composition string: {e}")
            return ""

    def get_composition_string(self) -> str:
        """获取当前组字串"""
        return self.composition_string

    def get_result_string(self) -> str:
        """获取结果字符串"""
        return self.result_string

    def is_ime_composing(self) -> bool:
        """检查是否正在组字"""
        return self.is_composing

    def cleanup(self):
        """清理资源"""
        self.disable_ime()
