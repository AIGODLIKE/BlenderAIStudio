import ctypes
import ctypes.util
import bpy
from typing import Optional, Callable
from .ime import IMEManager


class ObjCRuntime:
    """Objective-C 运行时封装"""

    def __init__(self):
        self.objc = ctypes.CDLL(ctypes.util.find_library("objc"))
        self._setup_objc()

    def _setup_objc(self):
        """设置 Objective-C 函数"""
        # objc_getClass
        self.objc_getClass = self.objc.objc_getClass
        self.objc_getClass.restype = ctypes.c_void_p
        self.objc_getClass.argtypes = [ctypes.c_char_p]

        # sel_registerName
        self.sel_registerName = self.objc.sel_registerName
        self.sel_registerName.restype = ctypes.c_void_p
        self.sel_registerName.argtypes = [ctypes.c_char_p]

        # objc_msgSend - 无参数
        self.msgSend = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", self.objc))

        # objc_msgSend - 1个对象参数
        self.msgSend_id = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", self.objc))

    def get_class(self, name: str) -> int:
        """获取 Objective-C 类"""
        return self.objc_getClass(name.encode())

    def sel(self, name: str) -> int:
        """获取 selector"""
        return self.sel_registerName(name.encode())

    def call(self, obj: int, selector_name: str) -> int:
        """调用无参数方法"""
        return self.msgSend(obj, self.sel(selector_name))

    def call_with_obj(self, obj: int, selector_name: str, arg: int) -> bool:
        """调用带对象参数的方法"""
        return self.msgSend_id(obj, self.sel(selector_name), arg)


class GHOSTBridge:
    """GHOST API 桥接"""

    def __init__(self):
        self.blender_lib = None
        self._setup_ghost_functions()

    def _get_blender_executable(self) -> str:
        """获取 Blender 可执行文件路径"""
        return bpy.app.binary_path

    def _setup_ghost_functions(self):
        """设置 GHOST 函数签名"""
        try:
            exe_path = self._get_blender_executable()
            self.blender_lib = ctypes.CDLL(exe_path)

            # GHOST_BeginIME(windowhandle, x, y, w, h, complete)
            self.GHOST_BeginIME = self.blender_lib.GHOST_BeginIME
            self.GHOST_BeginIME.argtypes = [
                ctypes.c_void_p,  # GHOST_WindowHandle
                ctypes.c_int32,  # x
                ctypes.c_int32,  # y
                ctypes.c_int32,  # w
                ctypes.c_int32,  # h
                ctypes.c_bool,  # complete
            ]
            self.GHOST_BeginIME.restype = None

            # GHOST_EndIME(windowhandle)
            self.GHOST_EndIME = self.blender_lib.GHOST_EndIME
            self.GHOST_EndIME.argtypes = [ctypes.c_void_p]
            self.GHOST_EndIME.restype = None
        except Exception as e:
            print(f"❌ GHOST API 桥接失败: {e}")
            raise


class MacOSIMEManager(IMEManager):
    """macOS 输入法管理器实现"""

    def __init__(self):
        super().__init__()
        self.objc = ObjCRuntime()
        self.ghost = GHOSTBridge()
        self._ghostwin_handle = None
        self._is_enabled = False
        self._current_x = 0
        self._current_y = 0

        # 结果字符串缓冲
        self._result_string = ""
        self.commit_callback = None
        self.composition_callback = None

        print("✅ macOS IME 管理器初始化成功")

    def _get_ghostwin_from_bpy_context(self) -> Optional[int]:
        try:
            if not bpy.context.window:
                print("❌ bpy.context.window 为 None")
                return None

            # 1. 获取 wmWindow* 的地址
            wmwindow_ptr = bpy.context.window.as_pointer()

            # 2. 内存布局:
            # struct wmWindow {
            #     wmWindow *next;   // +0  (8 bytes on 64-bit)
            #     wmWindow *prev;   // +8  (8 bytes)
            #     void *ghostwin;   // +16 (8 bytes) <- 我们要的!
            #     void *gpuctx;     // +24
            #     ...
            # }

            # 3. 读取 ghostwin 成员 (offset = 16)
            ghostwin_offset = 16
            ghostwin_ptr_address = wmwindow_ptr + ghostwin_offset

            # 4. 从内存读取 void* 值
            ghostwin = ctypes.c_void_p.from_address(ghostwin_ptr_address).value

            if not ghostwin:
                print("❌ ghostwin 为 NULL")
                return None

            print(f"✅ GHOST_WindowHandle = 0x{ghostwin:x}")
            return ghostwin

        except Exception as e:
            print(f"❌ 从 bpy.context 获取 ghostwin 失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def enable_ime(self) -> bool:
        """
        启用输入法 (完整模式)

        现在可以通过 bpy.context.window.as_pointer() 获取真正的 GHOST_WindowHandle!
        """
        try:
            # 1. 从 bpy.context 获取 GHOST_WindowHandle
            ghostwin = self._get_ghostwin_from_bpy_context()

            if not ghostwin:
                print("❌ 无法获取 GHOST_WindowHandle")
                return False

            self._ghostwin_handle = ghostwin

            # 2. 调用 GHOST_BeginIME!
            print(f"✅ 调用 GHOST_BeginIME(0x{ghostwin:x}, {self._current_x}, {self._current_y})...")
            self.ghost.GHOST_BeginIME(
                ctypes.c_void_p(ghostwin),
                ctypes.c_int32(self._current_x),
                ctypes.c_int32(self._current_y),
                ctypes.c_int32(200),
                ctypes.c_int32(20),
                ctypes.c_bool(True),
            )

            self._is_enabled = True
            print("✅ IME 已完全启用! (包括候选窗口控制)")
            return True

        except Exception as e:
            print(f"❌ 启用 IME 失败: {e}")
            return False

    def disable_ime(self) -> bool:
        """禁用输入法"""
        try:
            if not self._ghostwin_handle:
                return False

            self.ghost.GHOST_EndIME(ctypes.c_void_p(self._ghostwin_handle))
            self._is_enabled = False
            self._result_string = ""

            print("✅ IME 已禁用")
            return True

        except Exception as e:
            print(f"❌ 禁用 IME 失败: {e}")
            return False

    def is_composing(self) -> bool:
        """是否正在输入 (组字中)"""
        # macOS 下,如果 IME 已启用,就认为可能在组字
        return self._is_enabled

    def set_commit_callback(self, callback: Callable):
        """设置输入确认回调函数"""
        self.commit_callback = callback

    def set_composition_callback(self, callback: Callable):
        """设置组字过程回调函数"""
        self.composition_callback = callback

    def refresh_input_method(self):
        """刷新输入法状态"""
        if self._is_enabled and self._ghostwin_handle:
            # 重新设置位置
            self.set_composition_position(self._current_x, self._current_y)

    def get_composition_string(self) -> str:
        """获取当前组字串"""
        # macOS 下组字串由系统管理,我们无法直接获取
        # 返回空字符串
        return self.composition_string

    def get_result_string(self) -> str:
        """获取当前结果串"""
        result = self._result_string
        self._result_string = ""  # 读取后清空
        return result

    def set_composition_position(self, x: int, y: int):
        """
        设置候选窗口位置

        参数:
            x, y: 屏幕坐标(左上角为原点)
        """
        x, y = int(x), int(y)
        self._current_x = x
        self._current_y = y

        # 如果已启用且有 ghostwin,调用 GHOST_BeginIME 更新位置
        if self._is_enabled and self._ghostwin_handle:
            try:
                self.ghost.GHOST_BeginIME(
                    ctypes.c_void_p(self._ghostwin_handle),
                    ctypes.c_int32(x),
                    ctypes.c_int32(y),
                    ctypes.c_int32(200),
                    ctypes.c_int32(20),
                    ctypes.c_bool(False),  # complete=False 只更新位置
                )
            except Exception as e:
                print(f"⚠️ 更新候选窗口位置失败: {e}")

    def is_first_responder(self) -> bool:
        """检查 View 是否是第一响应者"""
        # macOS 下 IME 由系统管理,只要 GHOST_BeginIME 被调用即可
        return self._is_enabled
