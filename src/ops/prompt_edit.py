import bpy

from ..utils import (
    get_text_generic_keymap,
    get_text_window,
    get_pref,
    load_image,
)


def get_text_data(context) -> bpy.types.Text:
    """
    获取脚本数据块

    :param context:
    :return:
    """
    prompt = context.scene.blender_ai_studio_property.prompt

    name = "Prompt"
    text = bpy.data.texts.get(name)
    if text is None:
        text = bpy.data.texts.new(name)
    text.clear()
    text.write(prompt)
    text.blender_ai_studio_prompt_hash = str(hash(prompt))
    return text


class PromptEdit(bpy.types.Operator):
    bl_idname = "bas.prompt_edit"
    bl_label = "Prompt Edit"

    @staticmethod
    def add_save_key(context):
        keymap = get_text_generic_keymap(context)
        if keymap is not None:
            keymap.keymap_items.new(PromptSave.bl_idname, type="S", value="PRESS", ctrl=True)

    def execute(self, context):
        get_text_window(context, get_text_data(context))
        self.add_save_key(context)
        return {"FINISHED"}


def draw_save_script_button(self, context):
    layout = self.layout

    text = context.space_data.text
    prompt = context.scene.blender_ai_studio_property.prompt

    # layout.prop(text, "blender_ai_studio_prompt_hash")
    # layout.label(text=str(hash(prompt)))
    if getattr(text, "blender_ai_studio_prompt_hash", False) == str(hash(prompt)):
        row = layout.row()
        row.alert = True
        text = bpy.app.translations.pgettext("Save Prompt Ctrl + S")
        row.operator(PromptSave.bl_idname, text=text)


class PromptSave(bpy.types.Operator):
    bl_label = "Save script"
    bl_idname = "bas.prompt_save"

    @classmethod
    def poll(cls, context):
        pref = get_pref()
        prompt = context.scene.blender_ai_studio_property.prompt
        h = context.space_data.text.blender_ai_studio_prompt_hash
        hash_ok = h == str(hash(prompt))
        return hash_ok

    @staticmethod
    def register_ui():
        bpy.types.TEXT_HT_header.append(draw_save_script_button)

    @staticmethod
    def unregister_ui():
        bpy.types.TEXT_HT_header.remove(draw_save_script_button)

    def remove_save_key(self, context):
        keymap = get_text_generic_keymap(context)
        if keymap is not None:
            while True:
                ops = keymap.keymap_items.find_from_operator(self.bl_idname)
                if ops is None:
                    break
                keymap.keymap_items.remove(ops)

    def execute(self, context):
        text = context.space_data.text
        context.scene.blender_ai_studio_property.prompt = text.as_string()
        bpy.data.texts.remove(text)
        self.remove_save_key(context)
        bpy.ops.wm.window_close()
        return {"FINISHED"}
