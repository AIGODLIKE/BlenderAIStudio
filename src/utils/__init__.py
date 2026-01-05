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
    "get_version",
    "calc_appropriate_aspect_ratio",
    "refresh_image_preview",
]


def get_custom_icon(name="None"):
    """
    获取自定义图标
    load icon
    :param name:
    :return: int icon_id
    """
    from ..icons import previews_icons
    return previews_icons[name.lower()].icon_id


def get_version():
    from ...__init__ import bl_info

    return bl_info.get("version", (0, 0, 0))


def get_pref():
    from ... import __package__ as base_name
    return bpy.context.preferences.addons[base_name].preferences


def get_api():
    pref = get_pref()
    return pref.nano_banana_api


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

    def wap(*args, **kwargs):
        if print_time:
            st = time.time()
        func_return = func(*args, **kwargs)
        if print_time:
            et = time.time()
            s = et - st
            print(f"dt {func.__module__} {func.__name__} {(s * 1000):.2f}ms", )
        return func_return

    return wap


def register():
    pass


def unregister():
    pass
