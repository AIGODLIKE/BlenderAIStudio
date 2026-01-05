import bpy

modules = [
    "gui",
    "ops",
    "ime",
    "account",
]

reg, unreg = bpy.utils.register_submodule_factory(__package__, modules)



from ..utils import debug_time
import time
@debug_time
def register():
    print("a",time.time())
    reg()
    print("b",time.time())

def unregister():
    unreg()
