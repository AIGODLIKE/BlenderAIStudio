from math import degrees

from bpy.app.translations import pgettext as _T

from .property import get_bl_property


def _format_light(light_obj, light):
    """格式化单个灯光信息"""
    items = ["灯光%s" % light_obj.name]

    # 类型
    light_type_map = {
        "POINT": "点光",
        "SPOT": "聚光",
        "AREA": "面光",
        "SUN": "太阳光",
    }
    light_type = get_bl_property(light, "type", None)
    if light_type is not None:
        items.append("类型%s" % light_type_map.get(light_type, light_type))

    # 位置、旋转（欧拉）、缩放
    loc = get_bl_property(light_obj, "location", None)
    if loc is not None:
        items.append("位置(%.3f,%.3f,%.3f)" % (loc.x, loc.y, loc.z))
    rot = get_bl_property(light_obj, "rotation_euler", None)
    if rot is not None:
        items.append("旋转(%.2f°,%.2f°,%.2f°)" % (degrees(rot.x), degrees(rot.y), degrees(rot.z)))
    scale = get_bl_property(light_obj, "scale", None)
    if scale is not None:
        items.append("缩放(%.3f,%.3f,%.3f)" % (scale.x, scale.y, scale.z))

    # 强度（功率）
    energy = get_bl_property(light, "energy", None)
    if energy is not None:
        items.append("功率%.2fW" % energy)

    exposure = get_bl_property(light, "exposure", None)
    if exposure is not None:
        items.append("曝光%.2f" % exposure)

    # 衰减
    use_custom = get_bl_property(light, "use_custom_distance", False)
    if use_custom:
        cutoff = get_bl_property(light, "cutoff_distance", None)
        if cutoff is not None:
            items.append("自定义衰减距离%.2fm" % cutoff)

    # 系数
    diff = get_bl_property(light, "diffuse_factor", None)
    spec = get_bl_property(light, "specular_factor", None)
    trans = get_bl_property(light, "transmission_factor", None)
    vol = get_bl_property(light, "volume_factor", None)
    if diff is not None:
        items.append("漫反射系数%.2f" % diff)
    if spec is not None:
        items.append("高光系数%.2f" % spec)
    if trans is not None:
        items.append("透射系数%.2f" % trans)
    if vol is not None:
        items.append("体积系数%.2f" % vol)

    # 阴影
    use_shadow = get_bl_property(light, "use_shadow", None)
    if use_shadow is not None:
        items.append("阴影%s" % ("开" if use_shadow else "关"))

    # 节点着色器
    use_nodes = get_bl_property(light, "use_nodes", False)
    if use_nodes:
        items.append("使用节点")

    # 色温/颜色
    use_temp = get_bl_property(light, "use_temperature", False)
    if use_temp:
        temp = get_bl_property(light, "temperature", None)
        if temp is not None:
            items.append("色温%.0fK" % temp)
    else:
        color = get_bl_property(light, "color", None)
        if color is not None:
            items.append("颜色(%.3f,%.3f,%.3f)" % (color.r, color.g, color.b))

    # 软硬
    soft_size = get_bl_property(light, "shadow_soft_size", None)
    if soft_size is not None and soft_size > 0:
        items.append("软阴影(尺寸%.4f)" % soft_size)
    else:
        # 聚光有 spot_blend 控制边缘柔和度
        if light_type == "SPOT":
            blend = get_bl_property(light, "spot_blend", None)
            if blend is not None:
                items.append("边缘柔和度%.2f" % blend)
        items.append("硬阴影")

    # 阴影细节（点光/聚光/面光）
    shadow_filter = get_bl_property(light, "shadow_filter_radius", None)
    if shadow_filter is not None and shadow_filter > 0:
        items.append("阴影滤波%.2f" % shadow_filter)

    # 聚光特有：锥角、方形
    if light_type == "SPOT":
        spot_size = get_bl_property(light, "spot_size", None)
        if spot_size is not None:
            items.append("锥角%.2f°" % degrees(spot_size))
        use_square = get_bl_property(light, "use_square", None)
        if use_square:
            items.append("方形光斑")

    # 面光特有：形状、尺寸、扩散、归一化
    if light_type == "AREA":
        shape_map = {"SQUARE": "方形", "RECTANGLE": "矩形", "DISK": "圆盘", "ELLIPSE": "椭圆"}
        shape = get_bl_property(light, "shape", None)
        if shape is not None:
            items.append("形状%s" % shape_map.get(shape, shape))
        size = get_bl_property(light, "size", None)
        size_y = get_bl_property(light, "size_y", None)
        if size is not None and size_y is not None:
            items.append("尺寸%.3f×%.3f" % (size, size_y))
        spread = get_bl_property(light, "spread", None)
        if spread is not None:
            items.append("扩散角%.2f°" % degrees(spread))
        normalize = get_bl_property(light, "normalize", None)
        if normalize is not None:
            items.append("强度归一化%s" % ("开" if normalize else "关"))

    # 太阳光特有：角度
    if light_type == "SUN":
        angle = get_bl_property(light, "angle", None)
        if angle is not None:
            items.append("太阳角度%.2f°" % degrees(angle))

    return ",".join(items)


def get_light_info(context):
    light_objs = [o for o in context.scene.objects if o.type == "LIGHT"]
    if not light_objs:
        raise Exception(_T("No Light in Scene"))

    parts = []
    for light_obj in light_objs:
        light = get_bl_property(light_obj, "data", None)
        if light is None:
            continue
        parts.append(_format_light(light_obj, light))
    text = "; ".join(parts)
    return f"灯光信息[{text}],共有{len(light_objs)}个灯光"
