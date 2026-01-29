def get_bl_property(self, key, default):
    """通用方法,获取Blender属性"""
    if value := getattr(self, key, None):
        return value
    try:
        properties = self.bl_system_properties_get()
        if key in properties:
            return properties[key]
    except Exception as e:
        print(e.args)
        print("get_bl_property error", self, key, e.args)
    return default


def set_bl_property(self, key, value):
    """通用方法,设置Blender属性"""
    try:
        self[key] = value
        setattr(self, key, value)
    except Exception as e:
        properties = self.bl_system_properties_get()
        properties[key] = value
        print("set_bl_property error", self, key, value, e.args)
