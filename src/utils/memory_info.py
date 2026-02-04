import platform


def get_total_system_memory():
    """
    纯标准库获取系统总物理内存（单位：字节）
    支持 Windows / Linux / macOS
    无第三方依赖，无Blender专属API
    """
    sys_type = platform.system()
    total_bytes = 0

    try:
        if sys_type == "Windows":
            # Windows 平台：使用ctypes调用Kernel32系统API
            import ctypes
            # 定义内存状态结构体
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            mem_status = MEMORYSTATUSEX()
            mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            # 调用系统函数
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status))
            total_bytes = mem_status.ullTotalPhys

        elif sys_type == "Linux":
            # Linux 平台：读取/proc/meminfo系统文件
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        # 格式：MemTotal:       16384000 kB
                        kb_value = int(line.split()[1])
                        total_bytes = kb_value * 1024
                        break

        elif sys_type == "Darwin":
            # macOS 平台：执行sysctl系统命令
            import subprocess
            result = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            total_bytes = int(result.strip())

    except Exception as e:
        print(f"获取系统内存失败：{str(e)}")
        return 0

    return total_bytes


def format_memory_info():
    """格式化输出内存信息，转换为GB单位"""
    GB = 1024 ** 3
    # 获取数据
    total_mem = get_total_system_memory()
    if total_mem > 0:
        return f"{round(total_mem / GB, 2)} GB"
    else:
        return "获取失败"


# 执行主函数
if __name__ == "__main__":
    print(format_memory_info())
