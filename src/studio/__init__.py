import bpy
from .ops import AIStudioEntry

__all__ = [
    "AIStudioEntry",
]

modules = [
    "ops",
    "gui",
    "ime",
]

reg, unreg = bpy.utils.register_submodule_factory(__package__, modules)


def register():
    reg()


def unregister():
    unreg()
