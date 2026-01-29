import hashlib
import os
import time

import bpy

from .pkg_installer import PkgInstaller

__all__ = [
    "PkgInstaller",
    "get_custom_icon",
    "get_text_generic_keymap",
    "get_text_window",
    "get_pref",
    "save_image_to_temp_folder",
    "png_name_suffix",
    "load_image",
    "time_diff_to_str",
    "get_addon_version",
    "get_addon_version_str",
    "calc_appropriate_aspect_ratio",
    "refresh_image_preview",
    "get_temp_folder",
    "debug_time",
]


def get_custom_icon(name="None"):
    """
    获取自定义图标
    load icon
    :param name:
    :return: int icon_id
    """
    from ..icons import get_icon
    return get_icon(name.lower())


def get_addon_version():
    from ...__init__ import bl_info

    return bl_info.get("version", (0, 0, 0))


def get_addon_version_str():
    return ".".join(map(str, get_addon_version()))


def str_version_to_int(version_str):
    return tuple(map(int, version_str.split(".")))


def get_pref():
    from ... import __package__ as base_name
    return bpy.context.preferences.addons[base_name].preferences


def get_keymap(context, keymap_name):
    kc = context.window_manager.keyconfigs
    keymaps = kc.user.keymaps
    keymap = keymaps.get(keymap_name)
    if keymap is None:
        um = kc.user.keymaps.get(keymap_name)
        keymap = keymaps.new(keymap_name, space_type=um.space_type, region_type=um.region_type)
    return keymap


def get_text_generic_keymap(context) -> bpy.types.KeyMapItem | None:
    return get_keymap(context, 'Text Generic')


def get_text_window(context: bpy.types.Context, text: bpy.types.Text) -> bpy.types.Window:
    window = get_text_editor_window(context)
    if not window:
        bpy.ops.wm.window_new()
        window = bpy.context.window_manager.windows[-1]
    area = window.screen.areas[-1]
    area.type = "TEXT_EDITOR"
    area.spaces[0].text = text


def get_text_editor_window(context: bpy.types.Context):
    windows = context.window_manager.windows.values()
    for window in windows:
        areas = window.screen.areas.values()
        area = areas[0]
        if len(areas) == 1 and area.type == "TEXT_EDITOR":
            return window
    return None


def save_image_to_temp_folder(image, temp_folder) -> str | None:
    try:
        import os

        filepath_raw = image.filepath_raw
        file_format = image.file_format
        image_path = os.path.join(temp_folder, png_name_suffix(image.name))
        try:
            image.filepath_raw = image_path
            image.file_format = 'PNG'
            try:
                image.save()
            except Exception as e:
                print(e)
                import traceback
                traceback.print_exc()
                traceback.print_stack()
                image.save_render(image_path)
            if os.path.exists(image_path):
                os.path.getsize(image_path)
            else:
                image.save_render(image_path)
        finally:
            image.filepath_raw = filepath_raw
            image.file_format = file_format
            if os.path.exists(image_path):
                return str(image_path)
            else:
                return None
    except Exception as e:
        print(e)
        import traceback
        traceback.print_exc()
        traceback.print_stack()
        return None


def png_name_suffix(name, suffix=None):
    """设置png图片的后缀"""
    # print("png_name_suffix", name, suffix)
    aa = ["jpg", "jpeg", "png", "bmp", "tif", "tiff", "tga", "exr", "hdr"]
    name = ".".join([i for i in name.split(".") if i.lower() not in aa])
    if not suffix:
        suffix = ""
    return name + suffix + ".png"


def load_image(image_path):
    for i in bpy.data.images:
        if i.filepath == image_path:
            return i
    return bpy.data.images.load(image_path, check_existing=False)


def time_diff_to_str(time_diff=None, start=None, end=None):
    """
    将时间差转换为字符串
    """
    if time_diff is not None:
        if isinstance(time_diff, (int, float)):
            total_seconds = int(time_diff)
        else:
            total_seconds = int(time_diff.total_seconds())
    elif start is not None and end is not None:
        total_seconds = int((end - start).total_seconds())
    else:
        return "0s"

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    # 构建结果字符串
    result = []
    if hours > 0:
        result.append(f"{hours}h")
    if minutes > 0:
        result.append(f"{minutes}m")
    if seconds > 0 or not result:
        result.append(f"{seconds}s")
    return "".join(result)


def calc_appropriate_aspect_ratio(width: int, height: int) -> str:
    aspect_ratio_presets = {
        "1:1": 1 / 1,
        "2:3": 2 / 3,
        "3:2": 3 / 2,
        "3:4": 3 / 4,
        "4:3": 4 / 3,
        "5:4": 5 / 4,
        "4:5": 4 / 5,
        "9:16": 9 / 16,
        "16:9": 16 / 9,
        "21:9": 21 / 9,
    }
    return min(aspect_ratio_presets, key=lambda k: abs(aspect_ratio_presets[k] - width / height))


def refresh_image_preview(image: bpy.types.Image):
    if image:
        if image.preview:
            image.preview.reload()
        else:
            image.preview_ensure()


def debug_time(func, print_time=True):
    import time
    from .. import logger

    def wap(*args, **kwargs):
        if print_time:
            st = time.time()
        func_return = func(*args, **kwargs)
        if print_time:
            et = time.time()
            s = et - st
            logger.debug(f"dt {func.__module__} {func.__name__} {(s * 1000):.2f}ms", )
        return func_return

    return wap


def get_temp_folder(suffix=None, prefix=None):
    import tempfile
    file_name = os.path.basename(bpy.data.filepath)[:-6] if bpy.data.is_saved else ''  # 'Untitled.blend' -> 'Untitled'
    time_str = time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime())
    return tempfile.mkdtemp(prefix=f"{file_name}_{time_str}_{prefix}_", suffix=suffix, dir=get_pref().output_cache_dir)


def calculate_md5(file_path, chunk_size=8192):
    """
    计算文件的 MD5 哈希值。
    这是计算的核心函数，采用分块读取以支持大文件。
    """
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()  # 返回16进制字符串


def start_blender(step=1):
    """Create a new Blender thread through subprocess

    offset

    -p, --window-geometry <sx> <sy> <w> <h>
        Open with lower left corner at <sx>, <sy> and width and height as <w>, <h>.
    https://docs.blender.org/manual/en/4.3/advanced/command_line/arguments.html#window-options
    """
    import subprocess
    bpy.ops.wm.save_userpref()

    args = [bpy.app.binary_path, ]

    window = bpy.context.window
    offset = step * 20

    args.append("-p")
    args.extend((
        str(window.x + offset),
        str(window.y - offset),
        str(window.width),
        str(window.height),
    ))

    subprocess.Popen(args)
