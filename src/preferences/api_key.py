import bpy

from ..utils.property import set_bl_property, get_bl_property


class ApiKey:
    def get_api_key_by_model_name(self, model_name: str):
        key = f"api_key_{model_name}"
        return get_bl_property(self, key, "")

    def set_api_key_by_model_name(self, model_name: str, value: str):
        key = f"api_key_{model_name}"
        set_bl_property(self, key, value)

    def get_api_key(self):
        """获取api key"""
        key = f"api_key_{bpy.context.scene.blender_ai_studio_property.model_name}"
        return get_bl_property(self, key, "")

    def set_api_key(self, value):
        """设置api key"""
        key = f"api_key_{bpy.context.scene.blender_ai_studio_property.model_name}"
        set_bl_property(self, key, value)

    api_key: bpy.props.StringProperty(
        name="API Key",
        subtype="PASSWORD",
        get=get_api_key,
        set=set_api_key,
    )

    def draw_api(self, layout):
        box = layout.box()
        box.label(text="API Key")

        model_name = bpy.context.scene.blender_ai_studio_property.model_name
        column = box.column()
        column.prop(self, "api_key", text=model_name)
        if self.api_key == "":
            column.label(text="Please input your API Key")

    def have_input_api_key(self, context, layout):
        """如果在api模式并且模型支持api模式"""
        if self.is_api_mode:
            if self.api_key == "":
                self.draw_api(layout)
