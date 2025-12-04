import os

import bpy.utils.previews

previews_icons = bpy.utils.previews.new()  # 用于存所有的缩略图
thumbnail_suffix = [".png", ".jpg"]  # 缩略图后缀列表


def get_dat_icon(name):
    return os.path.normpath(os.path.join(os.path.dirname(__file__), name))


def load_icons():
    """预加载图标
    在启动blender或是启用插件时加载图标
    """
    from os.path import dirname, join, isfile
    for root, dirs, files in os.walk(dirname(__file__)):
        for file in files:
            icon_path = join(root, file)
            is_file = isfile(icon_path)
            is_icon = file[-4:] in thumbnail_suffix

            name = file[:-4].lower()
            if is_icon and is_file:
                previews_icons.load(name, icon_path, "IMAGE", )


def clear():
    previews_icons.clear()


def register():
    load_icons()


def unregister():
    clear()
