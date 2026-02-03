import dataclasses as dc
import enum
import platform
import subprocess
from typing import Generator, Dict, List, Any


class DeviceType(enum.Enum):
    CPU: str = 'CPU'
    HIP: str = 'HIP'
    OptiX: str = 'OPTIX'
    CUDA: str = 'CUDA'
    Metal: str = 'METAL'
    OneAPI: str = 'ONEAPI'


@dc.dataclass
class Device:
    name: str
    type: DeviceType
    is_display: bool

    def to_dict(self) -> Dict[str, object]:
        if self.type == DeviceType.CPU:
            return {'name': self.name, 'type': self.type.value}
        else:
            return {
                'name': self.name,
                'type': self.type.value,
                'is_display': self.is_display,
            }


def get_cpu_name() -> str:
    """tests\performance\api\device.py:L9"""
    # Get full CPU name.
    if platform.system() == "Windows":
        return platform.processor()
    elif platform.system() == "Darwin":
        cmd = ['/usr/sbin/sysctl', "-n", "machdep.cpu.brand_string"]
        return subprocess.check_output(cmd).strip().decode('utf-8', 'ignore')
    else:
        with open('/proc/cpuinfo') as f:
            for line in f:
                if line.startswith('model name'):
                    return line.split(':')[1].strip()
    return "Unknown CPU"


def get_gpu_device(args: None) -> list:
    """tests\performance\api\device.py:L25"""
    # Get the list of available Cycles GPU devices.
    import bpy

    prefs = bpy.context.preferences
    if 'cycles' not in prefs.addons.keys():
        return []
    cprefs = prefs.addons['cycles'].preferences

    result = []

    for device_type, _, _, _ in cprefs.get_device_types(bpy.context):
        cprefs.compute_device_type = device_type
        devices = cprefs.get_devices_for_type(device_type)
        index = 0
        for device in devices:
            if device.type == device_type:
                result.append({'type': device.type, 'name': device.name, 'index': index})
                if device.type in {"HIP", "METAL", "ONEAPI"}:
                    result.append({'type': f"{device.type}-RT", 'name': device.name, 'index': index})
                if device.type in {"OPTIX"}:
                    result.append({'type': f"{device.type}-OSL", 'name': device.name, 'index': index})
                index += 1

    return result


def _get_devices_for_type(type: DeviceType) -> Generator[Any, None, None]:
    try:
        import _cycles
        available_devices = _cycles.available_devices(type.value)
    except ValueError:
        # Ignore compute device type which is not supported by the current Cycles version.
        return

    for device in available_devices:
        # Device is a non-strictly-typed tuple. Element with index 1 is the type
        # of the device.
        if device[1] != type.value:
            continue
        yield device


def get_all_devices():
    all_devices = {
        "CPU": [],
        "GPU": [],
    }

    used_devices = []

    for type in DeviceType:
        for name, *_ in _get_devices_for_type(type):
            if name in used_devices:
                continue
            used_devices.append(name)
            if DeviceType(type) == DeviceType.CPU:
                all_devices["CPU"].append(name)
            else:
                all_devices["GPU"].append(name)
    return {
        "CPU": ";".join(all_devices["CPU"]),
        "GPU": ";".join(all_devices["GPU"]),
    }


