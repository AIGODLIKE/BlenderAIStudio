import bpy

from .history import StudioHistory, StudioHistoryItem, sync_history_timer

__all__ = [
    "StudioHistory",
    "StudioHistoryItem",
]


def register():
    bpy.app.timers.register(sync_history_timer, first_interval=1, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(sync_history_timer):
        bpy.app.timers.unregister(sync_history_timer)
