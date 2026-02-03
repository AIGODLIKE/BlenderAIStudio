import bpy

from .base import StudioHistoryItem, StudioHistory
from .universal_client import UniversalClient
from .history import StatusManager

__all__ = [
    "StudioHistoryItem",
    "StudioHistory",
    "UniversalClient",
    "StatusManager",
]

modules = [
    "history",
]

reg, unreg = bpy.utils.register_submodule_factory(__package__, modules)


def register():
    reg()


def unregister():
    unreg()
