import bpy

from .logger import logger

modules = [
    # 模块列表
    "i18n",
    "studio",
    "timer",
    "ui",
    "ops",
    "property",
    "preferences",
    "icons",
    "update",
    "online_update_addon"
]

reg, unreg = bpy.utils.register_submodule_factory(__package__, modules)


def register():
    reg()
    logger.debug(f"{__package__} registered")


def unregister():
    unreg()
    logger.debug(f"{__package__} unregistered")