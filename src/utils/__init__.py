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


def register():
    pass


def unregister():
    pass