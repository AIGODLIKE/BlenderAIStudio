import bpy


class ApiKey:
    """TODO 动态注册"""
    nano_banana_api: bpy.props.StringProperty(
        name="Nano Banana API Key",
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
        self.draw_item_api_key(box, "seedream_api")

    def draw_item_api_key(self, layout, key):
        """绘制单个api Key"""
        column = layout.column()
        column.prop(self, key)
        if getattr(self, key, "None") == "":
            column.label(text="Please input your API Key")

    def from_model_name_get_api_key(self, model: str) -> str:
        """根据模型名称对应的api key"""
        if model in ("NanoBananaPro",):
            return self.nano_banana_api
        elif model in ("Seedream-v4", "Seedream-v4.5"):
            return self.seedream_api
        return f"error not find api key {model}"
