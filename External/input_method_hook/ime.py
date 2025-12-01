import ctypes
from pathlib import Path


# 加载C++ DLL
dll_path = Path(__file__).parent / "input_method.dll"


class InputMethodManager:
    def __init__(self):
        self.dll = None
        self.input_callback = None
        self.current_text = ""
        self.load_dll()

    def load_dll(self):
        try:
            self.dll = ctypes.WinDLL(dll_path.as_posix())

            # 设置函数原型
            self.dll.InitializeInputMethod.restype = ctypes.c_bool
            self.dll.InitializeInputMethod.argtypes = []

            self.dll.SetInputMethodState.restype = ctypes.c_bool
            self.dll.SetInputMethodState.argtypes = [ctypes.c_bool]

            self.dll.GetInputMethodState.restype = ctypes.c_int
            self.dll.GetInputMethodState.argtypes = []

            self.dll.RefreshInputMethod.restype = ctypes.c_bool
            self.dll.RefreshInputMethod.argtypes = []

            self.dll.CleanupInputMethod.restype = None
            self.dll.CleanupInputMethod.argtypes = []

            self.dll.InstallMessageHook.restype = ctypes.c_bool
            self.dll.InstallMessageHook.argtypes = []

            self.dll.UninstallMessageHook.restype = None
            self.dll.UninstallMessageHook.argtypes = []

            self.dll.GetCompositionString.restype = ctypes.c_bool
            self.dll.GetCompositionString.argtypes = [ctypes.c_wchar_p, ctypes.c_int]

            self.dll.GetResultString.restype = ctypes.c_bool
            self.dll.GetResultString.argtypes = [ctypes.c_wchar_p, ctypes.c_int]

            # 回调函数类型
            self.CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_wchar_p)
            self.dll.SetInputCallback.argtypes = [self.CALLBACK]
            self.dll.SetInputCallback.restype = None

            # 初始化
            if self.dll.InitializeInputMethod():
                print("输入法管理器初始化成功")
                # 安装消息钩子
                if self.dll.InstallMessageHook():
                    print("消息钩子安装成功")
                else:
                    print("消息钩子安装失败")
            else:
                print("输入法管理器初始化失败")

        except Exception as e:
            print(f"加载DLL失败: {e}")
            self.dll = None

    def set_input_callback(self, callback):
        """设置输入回调函数"""
        if self.dll and callback:
            self.input_callback = callback

            # 包装回调函数
            def wrapped_callback(text):
                if self.input_callback:
                    self.input_callback(text)

            self.callback_func = self.CALLBACK(wrapped_callback)
            self.dll.SetInputCallback(self.callback_func)

    def enable_chinese_input(self):
        if self.dll:
            return self.dll.SetInputMethodState(True)
        return False

    def disable_chinese_input(self):
        if self.dll:
            return self.dll.SetInputMethodState(False)
        return False

    def refresh_input_method(self):
        if self.dll:
            return self.dll.RefreshInputMethod()
        return False

    def get_input_method_state(self):
        if self.dll:
            return self.dll.GetInputMethodState()
        return -1

    def get_composition_string(self):
        """获取当前组合字符串（预览文本）"""
        if self.dll:
            buffer = ctypes.create_unicode_buffer(256)
            if self.dll.GetCompositionString(buffer, 256):
                return buffer.value
        return ""

    def get_result_string(self):
        """获取结果字符串"""
        if self.dll:
            buffer = ctypes.create_unicode_buffer(256)
            if self.dll.GetResultString(buffer, 256):
                return buffer.value
        return ""


# 全局输入法管理器实例
input_manager = InputMethodManager()
