import bpy
from .loader import load_translations
from .translations.zh_HANS import PANEL_TCTX, PROP_TCTX, OPS_TCTX

__all__ = [
    "PROP_TCTX",
    "PANEL_TCTX",
    "OPS_TCTX",
]


def register():
    translations = load_translations()
    bpy.app.translations.register(__name__, translations)


def unregister():
    bpy.app.translations.unregister(__name__)
