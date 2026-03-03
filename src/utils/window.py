import ctypes
import sys

from ctypes import wintypes


def foreground_image_edit_window():
    """1.获取当前窗口
    2.查找有没有活动的窗口
    3.设置聚焦
    """

    if sys.platform == "win32":
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 获取当前进程ID
        current_pid = kernel32.GetCurrentProcessId()

        # 回调函数枚举窗口
        def enum_windows_callback(hwnd):

            # 获取窗口的进程ID
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            # 如果窗口属于当前进程
            if pid.value == current_pid:
                # 获取窗口标题
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value
                    # print(title)
                    is_image = title in ("图像编辑器...", "Image Editor", "Image Editor...", "图像编辑器")
                    if is_image:
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                        return False
            return True

        # 定义回调类型
        ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
        )

        # 创建回调实例
        callback = ENUM_WINDOWS_PROC(enum_windows_callback)

        # 枚举所有窗口
        user32.EnumWindows(callback, 0)
    else:
        print("此脚本仅支持Windows系统", __name__)


if __name__ == "__main__":
    print("foreground_image_edit_window")
    foreground_image_edit_window()
    print()
