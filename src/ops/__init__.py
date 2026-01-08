import bpy

from .account import LoginAccountAuth, LogoutAccountAuth
from .ai_edit_image import (
    ApplyAiEditImage,
    SmartFixImage,
    ReRenderImage,
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
)
from .history import (
    ViewImage,
    RestoreHistory,
    OpenImageInNewWindow,
)

class_list = [
    ApplyAiEditImage,
    SmartFixImage,
    ReRenderImage,

    RemoveReferenceImage,
    SelectReferenceImageByFile,
    SelectReferenceImageByImage,
    ReplaceReferenceImage,

    SelectMask,
    DrawImageMask,
    ApplyImageMask,

    PromptEdit,
    PromptSave,

    ViewImage,
    RestoreHistory,
    OpenImageInNewWindow,

    LoginAccountAuth,
    LogoutAccountAuth,
]

register_class, unregister_class = bpy.utils.register_classes_factory(class_list)


def register():
    register_class()
    PromptSave.register_ui()


def unregister():
    unregister_class()
    PromptSave.unregister_ui()
