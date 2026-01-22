import bpy

from .loader import load_translations
from .translations.zh_HANS import PANEL_TCTX, PROP_TCTX, OPS_TCTX, STUDIO_TCTX

__all__ = [
    "PROP_TCTX",
    "PANEL_TCTX",
    "OPS_TCTX",
    "STUDIO_TCTX",
]


def register():
    translations = load_translations()
    try:
        bpy.app.translations.register(__name__, translations)
    except RuntimeError:  # 出现这种情一般是注销插件时出现了错误，没有正常注销，然后出现了相同的翻译
        print("i18n register error", __name__)


def unregister():
    bpy.app.translations.unregister(__name__)
