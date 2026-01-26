import bpy


class ApiKey:
    nano_banana_api: bpy.props.StringProperty(
        name="Nano Banana API Key",
        subtype="PASSWORD",
    )
    dream_api: bpy.props.StringProperty(
        name="Dream API Key",
        subtype="PASSWORD",
    )
    seedream_api: bpy.props.StringProperty(
        name="Seedream API Key",
        subtype="PASSWORD",
    )

    def draw_api(self, layout):
        box = layout.box()
        box.label(text="API Key")

        self.draw_item_api_key(box, "nano_banana_api")
        box.separator(type="LINE")
        self.draw_item_api_key(box, "dream_api")
        box.separator(type="LINE")
        self.draw_item_api_key(box, "seedream_api")

    def draw_item_api_key(self, layout, key):
        """绘制单个api Key"""
        column = layout.column()
        column.prop(self, key)
        if getattr(self, key, "None") == "":
            column.label(text="Please input your API Key")

    def from_model_get_api_key(self, model: str) -> str:
        """根据模型获取对应的api key"""
        if model in ("gemini-3-pro-image-preview",):
            return self.nano_banana_api
        elif model in ("dream-studio-image-preview", "dream-studio-image-preview-v2"):
            return self.dream_api
        elif model in ("seedream-image-preview",):
            return self.seedream_api
        return ""
