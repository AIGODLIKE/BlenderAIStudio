import bpy


class ApiKey:
    def get_api_key(self):
        """获取api key"""
        model = bpy.context.scene.blender_ai_studio_property.model
        key = f"api_key_{model}"
        if api_key := getattr(self, key, None):
            return api_key
        try:
            properties = self.bl_system_properties_get()
            if key in properties:
                return properties[key]
        except Exception as e:
            print(e.args)
        return ""

    def set_api_key(self, value):
        """设置api key"""
        model = bpy.context.scene.blender_ai_studio_property.model
        key = f"api_key_{model}"
        try:
            self[key] = value
            setattr(self, key, value)
        except Exception as e:
            properties = self.bl_system_properties_get()
            properties[key] = value
            print(e.args)

    api_key: bpy.props.StringProperty(
        name="API Key",
        subtype="PASSWORD",
        get=get_api_key,
        set=set_api_key,
    )

    def draw_api(self, layout):
        box = layout.box()
        box.label(text="API Key")

        model = bpy.context.scene.blender_ai_studio_property.model
        box.label(text=model)

        column = layout.column()
        column.prop(self, "api_key")
        if getattr(self, "api_key", "") == "":
            column.label(text="Please input your API Key")
