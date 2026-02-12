import bpy

from .account import LoginAccountAuth, LogoutAccountAuth
from .ai_edit_image import (
    ApplyAiEditImage,
    SmartFixImage,
    ReRenderImage,
)
from .history import (
    ViewImage,
    RestoreHistory,
    OpenImageInNewWindow,
    RemoveHistory,
    ClearHistory,
)
from .mask_image import DrawImageMask, ApplyImageMask, SelectMask
from .prompt_edit import (
    PromptEdit,
    PromptSave,
)
from .references_image import (
    RemoveReferenceImage,
    ReplaceReferenceImage,
    SelectReferenceImageByFile,
    SelectReferenceImageByImage,
    ClipboardPasteReferenceImage,
)
from .privacy_tips import PrivacyTips
from .update_tips import UpdateTips
from .entry_edit_image import EntryEditImage

class_list = [
    ApplyAiEditImage,
    SmartFixImage,
    ReRenderImage,

    RemoveReferenceImage,
    SelectReferenceImageByFile,
    SelectReferenceImageByImage,
    ReplaceReferenceImage,
    ClipboardPasteReferenceImage,

    SelectMask,
    DrawImageMask,
    ApplyImageMask,

    PromptEdit,
    PromptSave,

    ViewImage,
    RestoreHistory,
    OpenImageInNewWindow,
    RemoveHistory,
    ClearHistory,

    LoginAccountAuth,
    LogoutAccountAuth,

    PrivacyTips,

    UpdateTips,

    EntryEditImage,
]

register_class, unregister_class = bpy.utils.register_classes_factory(class_list)


def register():
    register_class()
    PromptSave.register_ui()


def unregister():
    unregister_class()
    PromptSave.unregister_ui()
