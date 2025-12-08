import bpy

from .pkg_installer import PkgInstaller

__all__ = [
    "PkgInstaller",
    "get_custom_icon"
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
        image_path = os.path.join(temp_folder, image.name)
        try:
            image.filepath_raw = image_path
            image.file_format = 'PNG'
            if not filepath_raw.endswith(".png"):  # TIPS: 临时解决没有png后缀问题
                filepath_raw += ".png"
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


def png_name_suffix(name, suffix):
    """设置png图片的后缀"""
    ...


def register():
    pass


def unregister():
    pass
