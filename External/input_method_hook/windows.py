import time
import ctypes
from ctypes import wintypes, Structure, byref, windll, CFUNCTYPE, POINTER, c_int, c_void_p, c_longlong

from typing import Callable, Optional
from collections import deque
from .ime import IMEManager

# Windows 常量
IME_CMODE_NATIVE = 0x0001
GCS_COMPSTR = 0x0008
GCS_RESULTSTR = 0x0800
WM_IME_COMPOSITION = 0x010F
WM_IME_STARTCOMPOSITION = 0x010E
WM_IME_ENDCOMPOSITION = 0x010F
WM_CHAR = 0x0102
CFS_POINT = 0x0002
WH_GETMESSAGE = 3
PM_NOREMOVE = 0x0000

# 类型定义
LRESULT = c_longlong
HHOOK = c_void_p

# MSG 结构体


class MSG(Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class COMPOSITIONFORM(Structure):
    """IME 组合窗口位置结构"""

    _fields_ = [
        ("dwStyle", wintypes.DWORD),
        ("ptCurrentPos", wintypes.POINT),
        ("rcArea", wintypes.RECT),
    ]


# 消息钩子回调函数类型
HOOKPROC = CFUNCTYPE(c_void_p, c_int, c_void_p, c_void_p)


class WindowsIMEManager(IMEManager):
    def __init__(self):
        super().__init__()

        self.imm32 = None
        self.user32 = None
        try:
            self.imm32 = windll.imm32
            self.user32 = windll.user32

            # 设置 CallNextHookEx 的参数类型
            self.user32.CallNextHookEx.argtypes = [
                HHOOK,  # hhk
                c_int,  # nCode
                wintypes.WPARAM,  # wParam
                wintypes.LPARAM,  # lParam
            ]
            self.user32.CallNextHookEx.restype = LRESULT

        except Exception:
            raise RuntimeError("无法加载 Windows IMM32/User32 DLL")

        self._himc = None
        self._initialized = False
        self._hwnd = None

        # 消息钩子相关
        self._hook_handle = None
        self._hook_callback = None  # 保持引用防止被回收

        # 内部输入缓冲队列
        self._input_queue: deque = deque(maxlen=100)  # 最多缓存100个输入

    def _get_foreground_window(self) -> int:
        """获取前台窗口句柄"""
        return self.user32.GetForegroundWindow()

    def _message_hook_proc(self, nCode: int, wParam, lParam) -> int:
        """消息钩子回调函数"""
        if nCode >= 0:
            # 获取消息结构
            msg = ctypes.cast(lParam, POINTER(MSG)).contents

            # 处理 IME 组合消息
            if msg.message == WM_IME_COMPOSITION:
                if msg.lParam & GCS_RESULTSTR:
                    # 有确认的输入结果
                    result = self._get_result_string_from_ime(msg.hwnd)
                    if result:
                        # 将结果放入队列
                        self._input_queue.append(result)
                        # 如果设置了外部回调,也调用它
                        if self.commit_callback:
                            self.commit_callback(result)
                elif msg.lParam & GCS_COMPSTR:
                    # 正在组合输入(预览)
                    comp_str = self._get_composition_string_from_ime(msg.hwnd)
                    if comp_str and self.composition_callback:
                        self.composition_callback(comp_str)

            elif msg.message == WM_IME_STARTCOMPOSITION:
                # 开始输入法组合
                pass

            elif msg.message == WM_IME_ENDCOMPOSITION:
                # 结束输入法组合
                pass

            elif msg.message == WM_CHAR:
                # 处理普通字符输入(英文等)
                # 注意: WM_CHAR 会在 IME 输入后也触发,需要过滤
                # 此处简化处理,实际应用中可能需要更细致的判断
                if msg.wParam < 128:
                    # 只处理 ASCII 字符
                    char = chr(msg.wParam)
                    if char.isprintable():
                        # 将字符放入队列
                        self._input_queue.append(char)
                        # 如果设置了外部回调,也调用它
                        if self.commit_callback:
                            self.commit_callback(char)

        # 调用下一个钩子
        return self.user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _get_result_string_from_ime(self, hwnd: int) -> str:
        """从 IME 上下文获取结果字符串"""
        himc = self.imm32.ImmGetContext(hwnd)
        if not himc:
            return ""

        try:
            length = self.imm32.ImmGetCompositionStringW(himc, GCS_RESULTSTR, None, 0)
            if length <= 0:
                return ""

            buffer = ctypes.create_unicode_buffer(length // 2 + 1)
            actual_length = self.imm32.ImmGetCompositionStringW(himc, GCS_RESULTSTR, buffer, length)

            if actual_length > 0:
                return buffer.value
            return ""
        finally:
            self.imm32.ImmReleaseContext(hwnd, himc)

    def _get_composition_string_from_ime(self, hwnd: int) -> str:
        """从 IME 上下文获取组合字符串"""
        himc = self.imm32.ImmGetContext(hwnd)
        if not himc:
            return ""

        try:
            length = self.imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)
            if length <= 0:
                return ""

            buffer = ctypes.create_unicode_buffer(length // 2 + 1)
            actual_length = self.imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, buffer, length)

            if actual_length > 0:
                return buffer.value
            return ""
        finally:
            self.imm32.ImmReleaseContext(hwnd, himc)

    def _initialize_if_needed(self) -> bool:
        """按需初始化 IME 上下文"""
        if self._initialized:
            return True

        self._hwnd = self._get_foreground_window()
        if not self._hwnd:
            return False

        # 获取当前窗口的输入法上下文
        self._himc = self.imm32.ImmGetContext(self._hwnd)
        if not self._himc:
            # 如果没有上下文，创建一个新的
            self._himc = self.imm32.ImmCreateContext()
            if self._himc:
                self.imm32.ImmAssociateContext(self._hwnd, self._himc)

        if self._himc:
            self._initialized = True

        return self._initialized

    def enable_ime(self) -> bool:
        """启用输入法"""
        # 自动安装钩子
        if not self._hook_handle:
            self.install_message_hook()

        if not self._initialize_if_needed():
            return False

        hwnd = self._get_foreground_window()
        himc = self.imm32.ImmGetContext(hwnd)

        if not himc:
            himc = self.imm32.ImmAssociateContext(hwnd, self._himc)

        if not himc:
            return False

        try:
            # 获取当前转换模式
            conversion = wintypes.DWORD()
            sentence = wintypes.DWORD()
            self.imm32.ImmGetConversionStatus(himc, byref(conversion), byref(sentence))

            # 设置为中文输入模式
            conversion.value |= IME_CMODE_NATIVE
            self.imm32.ImmSetConversionStatus(himc, conversion.value, sentence.value)

            return True
        finally:
            self.imm32.ImmReleaseContext(hwnd, himc)

    def disable_ime(self) -> bool:
        """禁用输入法"""
        if not self._initialized:
            return False

        hwnd = self._get_foreground_window()
        himc = self.imm32.ImmGetContext(hwnd)

        if not himc:
            return False

        try:
            # 获取当前转换模式
            conversion = wintypes.DWORD()
            sentence = wintypes.DWORD()
            self.imm32.ImmGetConversionStatus(himc, byref(conversion), byref(sentence))

            # 禁用中文输入模式
            conversion.value &= ~IME_CMODE_NATIVE
            self.imm32.ImmSetConversionStatus(himc, conversion.value, sentence.value)

            return True
        finally:
            self.imm32.ImmReleaseContext(hwnd, himc)

    def get_ime_state(self) -> int:
        """获取输入法状态

        Returns:
            1: 启用
            0: 禁用
            -1: 错误
        """
        if not self._initialized:
            return -1

        hwnd = self._get_foreground_window()
        himc = self.imm32.ImmGetContext(hwnd)

        if not himc:
            return -1

        try:
            conversion = wintypes.DWORD()
            sentence = wintypes.DWORD()
            self.imm32.ImmGetConversionStatus(himc, byref(conversion), byref(sentence))

            return 1 if (conversion.value & IME_CMODE_NATIVE) else 0
        finally:
            self.imm32.ImmReleaseContext(hwnd, himc)

    def get_composition_string(self) -> str:
        """获取当前组字串（输入过程中的预览文本）"""
        if not self._initialized:
            return ""

        hwnd = self._get_foreground_window()
        himc = self.imm32.ImmGetContext(hwnd)

        if not himc:
            return ""

        try:
            # 获取组合字符串长度（字节数）
            length = self.imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)

            if length <= 0:
                return ""

            # 分配缓冲区并获取组合字符串
            buffer = ctypes.create_unicode_buffer(length // 2 + 1)
            actual_length = self.imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, buffer, length)

            if actual_length > 0:
                return buffer.value

            return ""
        finally:
            self.imm32.ImmReleaseContext(hwnd, himc)

    def get_result_string(self, consume: bool = True) -> str:
        """获取结果字符串(确认输入的文本)

        通过内部队列获取输入,每次调用返回一个输入字符串

        Args:
            consume: 是否消费该文本,默认为 True

        Returns:
            输入的文本,如果队列为空则返回空字符串
        """
        if not self._input_queue:
            return ""

        if consume:
            return self._input_queue.popleft()
        else:
            return self._input_queue[0]

    def set_composition_position(self, x: int, y: int):
        """设置候选窗口位置"""
        if not self._initialized:
            return

        hwnd = self._get_foreground_window()
        himc = self.imm32.ImmGetContext(hwnd)

        if not himc:
            return

        try:
            # 设置组合窗口位置
            comp_form = COMPOSITIONFORM()
            comp_form.dwStyle = CFS_POINT
            comp_form.ptCurrentPos.x = x
            comp_form.ptCurrentPos.y = y

            self.imm32.ImmSetCompositionWindow(himc, byref(comp_form))
        finally:
            self.imm32.ImmReleaseContext(hwnd, himc)

    def refresh_input_method(self):
        """刷新输入法状态"""
        if not self._initialized:
            return

        # 先禁用再启用
        self.disable_ime()
        time.sleep(0.05)
        self.enable_ime()

    def set_commit_callback(self, callback: Optional[Callable[[str], None]]):
        """设置输入回调函数(可选)

        Args:
            callback: 回调函数,接收一个字符串参数(输入的文本)
                     如果不需要回调,只使用 get_result_string() 获取,可以不设置
        """
        self.commit_callback = callback

    def install_message_hook(self) -> bool:
        """安装消息钩子(内部自动调用,通常不需要手动调用)

        Returns:
            是否成功安装
        """
        if self._hook_handle:
            return True  # 已经安装

        # 创建回调函数(保持引用)
        self._hook_callback = HOOKPROC(self._message_hook_proc)

        # 获取当前线程 ID
        kernel32 = windll.kernel32
        thread_id = kernel32.GetCurrentThreadId()

        # 安装 GetMessage 钩子
        self._hook_handle = self.user32.SetWindowsHookExW(
            WH_GETMESSAGE,
            self._hook_callback,
            None,  # hMod
            thread_id,
        )

        return self._hook_handle is not None

    def uninstall_message_hook(self) -> bool:
        """卸载消息钩子

        Returns:
            是否成功卸载
        """
        if not self._hook_handle:
            return True

        result = self.user32.UnhookWindowsHookEx(self._hook_handle)
        self._hook_handle = None
        self._hook_callback = None

        return bool(result)

    def reset_result_tracking(self):
        """重置结果追踪状态(已废弃,仅为兼容性保留)"""
        pass

    def cleanup(self):
        """清理资源"""
        # 卸载钩子
        self.uninstall_message_hook()

        if self._himc:
            self.imm32.ImmDestroyContext(self._himc)
            self._himc = None

        self._initialized = False
        self._input_queue.clear()
        self.composition_callback = None
        self.commit_callback = None

    def __del__(self):
        """析构函数"""
        self.cleanup()
