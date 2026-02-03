import bpy

modules = [
    "gui",
    "ops",
    "ime",
    "account",
    "clients",
]

reg, unreg = bpy.utils.register_submodule_factory(__package__, modules)


def register():
    reg()


def unregister():
    unreg()
