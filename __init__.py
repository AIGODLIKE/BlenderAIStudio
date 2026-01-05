bl_info = {
    "name": "Blender AI Studio",
    "author": "幻之境开发小组",
    "version": (0, 0, 2),
    "blender": (4, 0, 0),
    "location": "3DView->Panel",
    "category": "AI",
}

import bpy  # noqa: E402

modules = [
    "src",
    "ops",
]

reg, unreg = bpy.utils.register_submodule_factory(__package__, modules)


def register():
    reg()


def unregister():
    unreg()
