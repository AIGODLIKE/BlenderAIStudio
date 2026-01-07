import time
import ctypes
from ctypes import wintypes, Structure, byref, windll, CFUNCTYPE, POINTER, c_int, c_void_p, c_longlong

from typing import Callable, Optional
from collections import deque
from .ime import IMEManager

# Windows 常量
IME_CMODE_NATIVE = 0x0001
GCS_COMPSTR = 0x0008  # 获取当前的组合字符串, 正在编辑但未确认的字符串（用户正在输入的内容）
GCS_RESULTSTR = 0x0800  # 获取结果字符串, 用户确认完成输入后的最终字符串
WM_IME_COMPOSITION = 0x010F
WM_IME_STARTCOMPOSITION = 0x010E
WM_IME_ENDCOMPOSITION = 0x010F
WM_CHAR = 0x0102
CFS_POINT = 0x0002
WH_GETMESSAGE = 3
WH_CALLWNDPROC = 4

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
        self._ime_enabled = False
        self._hwnd = None

        # 消息钩子相关
        self._hook_handle = None
        self._hook_callback = None  # 保持引用防止被回收
        self._callwndproc_hook_handle = None
        self._callwndproc_hook_callback = None

        # 内部输入缓冲队列
        self._input_queue: deque = deque(maxlen=100)  # 最多缓存100个输入

        # 输入法状态追踪
        self._composition_active = False  # 是否正在组字
        self._last_comp_string = ""  # 上次的组字字符串
        self._last_poll_time = 0  # 上次轮询时间

    def _get_foreground_window(self) -> int:
        """获取前台窗口句柄"""
        return self.user32.GetForegroundWindow()

    def _message_hook_proc(self, nCode: int, wParam, lParam) -> int:
        """消息钩子回调函数"""
        if self._ime_enabled and nCode >= 0:
            # 获取消息结构
            msg = ctypes.cast(lParam, POINTER(MSG)).contents

            # 处理 IME 组合消息
            if msg.message == WM_IME_COMPOSITION:
                if msg.lParam & GCS_RESULTSTR:
                    # 有确认的输入结果
                    result = self._get_result_string_from_ime(msg.hwnd)
                    if result:
                        # 将结果放入队列
                        # self._input_queue.append(result) # 已移至 _poll_input 中处理
                        # 如果设置了外部回调,也调用它
                        if self.commit_callback:
                            self.commit_callback(result)
                        self._composition_active = False
                elif msg.lParam & GCS_COMPSTR:
                    # 正在组合输入(预览)
                    comp_str = self._get_composition_string_from_ime(msg.hwnd)
                    if comp_str and self.composition_callback:
                        self.composition_callback(comp_str)
                    self._last_comp_string = comp_str
                    self._composition_active = True

            elif msg.message == WM_IME_STARTCOMPOSITION:
                # 开始输入法组合
                self._composition_active = True
                self._last_comp_string = ""

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
                        self._enqueue_input(char)
        return self.user32.CallNextHookEx(
            None,
            nCode,
            wintypes.WPARAM(wParam if wParam is not None else 0),
            wintypes.LPARAM(lParam if lParam is not None else 0),
        )

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
            self._ime_enabled = True
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
            self._ime_enabled = False

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
        # 主动轮询输入法状态(每50ms检查一次)
        current_time = time.time()
        if current_time - self._last_poll_time > 0.05:  # 50ms轮询间隔
            self._last_poll_time = current_time
            self._poll_input()

        return self._dequeue_input(consume)

    def _poll_input(self):
        """
        主动检查组字状态并获取结果
        """
        if not self._composition_active:
            return

        hwnd = self._get_foreground_window()
        if not hwnd:
            return

        # 先尝试获取当前的组字字符串
        current_comp_str = self._get_composition_string_from_ime(hwnd)

        # 如果组字字符串消失了,说明已经提交
        result = self._last_comp_string
        if not current_comp_str and result:
            self._proc_input_string(result)
            return

        # 尝试获取结果字符串
        result = self._get_result_string_from_ime(hwnd)
        self._proc_input_string(result)

    def _proc_input_string(self, result: str):
        if not result:
            return
        # 避免重复添加
        self._push_input(result)
        self._composition_active = False
        self._last_comp_string = ""

    def _push_input(self, result: str):
        if not self._input_queue or self._input_queue[-1] != result:
            self._enqueue_input(result)

    def _enqueue_input(self, result: str):
        self._input_queue.append(result)
        if self.commit_callback:
            self.commit_callback(result)

    def _dequeue_input(self, consume: bool = True) -> str:
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

        # 同时安装 CallWndProc 钩子(捕获更多消息)
        self._callwndproc_hook_callback = HOOKPROC(self._message_hook_proc)
        self._callwndproc_hook_handle = self.user32.SetWindowsHookExW(
            WH_CALLWNDPROC,
            self._callwndproc_hook_callback,
            None,
            thread_id,
        )

        return self._hook_handle is not None

    def uninstall_message_hook(self) -> bool:
        """卸载消息钩子

        Returns:
            是否成功卸载
        """
        result1 = True
        result2 = True

        if self._hook_handle:
            result1 = self.user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None
            self._hook_callback = None

        if self._callwndproc_hook_handle:
            result2 = self.user32.UnhookWindowsHookEx(self._callwndproc_hook_handle)
            self._callwndproc_hook_handle = None
            self._callwndproc_hook_callback = None

        return bool(result1 and result2)

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
