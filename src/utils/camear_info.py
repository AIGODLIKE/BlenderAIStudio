from math import acos, atan2, degrees, sqrt

import bpy
from bpy.app.translations import pgettext as _T
from mathutils import Vector

from .property import get_bl_property


def _focal_length_descriptor(lens_mm: float) -> str:
    """根据焦距毫米数返回镜头类型描述词"""
    if lens_mm < 24:
        return "超广角"
    if lens_mm < 35:
        return "广角"
    if lens_mm < 85:
        return "标准"
    if lens_mm < 135:
        return "中焦"
    return "长焦"


def _compute_relative_angles(camera_obj: bpy.types.Object, ref_obj: bpy.types.Object) -> dict | None:
    """
    按 ComfyUI-qwenmultiangle 的轨道相机模型计算角度。
    主体为原点，相机在轨道上绕主体旋转。
    - 以 -Y 轴为前方基准（0°），Blender 前视图沿 -Y 观测，水平面 XZ 中对应 -Z 为 0°
    - horizontal (0°~360°): 0°=-Z(正前)，90°=+X(右)，180°=+Z(背)，270°=-X(左)
    - vertical (-30°~60°): 相机俯仰，负=仰拍，正=俯拍
    """
    cam_loc = Vector(camera_obj.matrix_world.translation)
    ref_loc = ref_obj.matrix_world.translation.copy()
    # 从主体指向相机的向量（相机在轨道上的位置）
    v = cam_loc - ref_loc
    dist = v.length
    if dist < 1e-6:
        return None  # 相机与主体重合

    # 以 -Y 为 0°：水平角在 XY 平面（绕 Z 轴），俯仰角为 Z 分量（上下）
    horiz_xy = sqrt(v.x * v.x + v.y * v.y)
    # 水平角：XY 平面，0°=-Y(正前)，90°=+X(右)，180°=+Y(背)，270°=-X(左)
    horizontal = degrees(atan2(v.x, -v.y))
    if horizontal < 0:
        horizontal += 360
    # 俯仰角：v.z 为正=相机在上方(俯拍)，负=下方(仰拍)
    vertical = degrees(atan2(v.z, horiz_xy)) if horiz_xy > 1e-6 else (90.0 if v.z > 0 else -90.0)

    # 镜头倾斜角：世界 Z 轴与相机上方向的夹角，带正负；正=顺时针，负=逆时针
    cam_matrix = camera_obj.matrix_world.to_3x3()
    cam_up = cam_matrix @ Vector((0, 1, 0))
    cam_forward = cam_matrix @ Vector((0, 0, -1))
    world_z = Vector((0, 0, 1))
    cross_up_z = cam_up.cross(world_z)
    dot_val = max(-1, min(1, cam_up.dot(world_z)))
    angle = degrees(acos(dot_val))
    sign = 1 if cross_up_z.dot(cam_forward) >= 0 else -1
    tilt = angle * sign

    return {"distance": dist, "horizontal": horizontal, "vertical": vertical, "tilt": tilt}


def _angles_to_direction_labels(horizontal: float, vertical: float) -> tuple[str, str]:
    """根据水平角、俯仰角返回方位描述标签（正面/右前/仰拍/略俯等）"""
    v_clamped = max(-30, min(60, round(vertical)))

    if horizontal < 22.5 or horizontal >= 337.5:
        h_direction = "正面"
    elif horizontal < 67.5:
        h_direction = "右前"
    elif horizontal < 112.5:
        h_direction = "右侧"
    elif horizontal < 157.5:
        h_direction = "右后"
    elif horizontal < 202.5:
        h_direction = "背面"
    elif horizontal < 247.5:
        h_direction = "左后"
    elif horizontal < 292.5:
        h_direction = "左侧"
    else:
        h_direction = "左前"

    if v_clamped < -15:
        v_direction = "仰拍"
    elif v_clamped < 15:
        v_direction = "平视"
    elif v_clamped < 45:
        v_direction = "略俯"
    else:
        v_direction = "俯拍"

    return h_direction, v_direction


def _get_orientation_rel(context, camera_obj) -> dict | None:
    """获取相机相对于方位参照物的角度数据，无参照物时返回 None"""
    ref_obj = getattr(context.scene.blender_ai_studio_property, "orientation_reference_object", None)
    if ref_obj and ref_obj.name in context.scene.objects:
        return _compute_relative_angles(camera_obj, ref_obj)
    return None


def _format_orientation_display(rel: dict) -> str:
    """将相对角度格式化为简短 UI 显示字符串"""
    v = rel["vertical"]
    v_str = "俯仰%.0f度" % v if abs(v) < 0.5 else "俯仰%s%.0f度" % ("向下" if v > 0 else "向上", abs(v))
    h = "水平旋转%.0f度" % rel["horizontal"]
    parts = [v_str]
    t = rel.get("tilt", 0)
    if abs(t) >= 0.5:
        parts.append("%s旋转%.0f度" % ("顺时针" if t > 0 else "逆时针", abs(t)))
    return ",".join(parts)


def get_orientation_reference_object_info(context, camera_obj) -> str | None:
    """返回方位参照物的简短显示信息，用于 UI；无参照物时返回 None"""
    rel = _get_orientation_rel(context, camera_obj)
    return _format_orientation_display(rel) if rel else None


def get_camera_info(context):
    """
    生成符合提示词风格的自然语言相机描述，可直接嵌入「生成一张[场景描述]的图像，...」类提示。
    示例：使用18毫米广角焦距的透视相机拍摄，水平旋转337度，俯仰向下65度，顺时针旋转30度，
    浅景深，光圈为f/2.8，焦点清晰地聚焦在1.77米外，背景模糊
    """
    if not (camera_obj := context.scene.camera):
        raise Exception(_T("No Camera in Scene"))

    parts = []
    camera = get_bl_property(camera_obj, "data", None)
    if camera is None:
        return "使用透视相机拍摄"

    camera_type = get_bl_property(camera, "type", "PERSP")
    camera_type_map = {"PERSP": "透视", "ORTHO": "正交", "PANO": "全景", "CUSTOM": "自定义"}
    cam_type_cn = camera_type_map.get(camera_type, camera_type)

    # 1. 焦距描述（仅透视相机用毫米焦距，FOV 时用视场角）
    lens_unit = get_bl_property(camera, "lens_unit", "MILLIMETERS")
    lens_mm = get_bl_property(camera, "lens", None) if camera_type == "PERSP" and lens_unit == "MILLIMETERS" else None
    if lens_mm is not None:
        desc = _focal_length_descriptor(lens_mm)
        parts.append("使用%.0f毫米%s焦距的%s相机拍摄" % (lens_mm, desc, cam_type_cn))
    elif camera_type == "PERSP" and lens_unit == "FOV":
        angle_rad = get_bl_property(camera, "angle", None)
        if angle_rad is not None:
            parts.append("使用透视相机拍摄，视场角%.1f度" % degrees(angle_rad))
        else:
            parts.append("使用%s相机拍摄" % cam_type_cn)
    elif camera_type == "ORTHO":
        ortho_scale = get_bl_property(camera, "ortho_scale", None)
        if ortho_scale is not None:
            parts.append("使用正交相机拍摄，正交缩放%.3f" % ortho_scale)
        else:
            parts.append("使用正交相机拍摄")
    else:
        parts.append("使用%s相机拍摄" % cam_type_cn)

    # 2. 水平/俯仰/倾斜（需方位参照物，含方位标签）
    rel = _get_orientation_rel(context, camera_obj)
    if rel:
        h_dir, v_dir = _angles_to_direction_labels(rel["horizontal"], rel["vertical"])
        # parts.append("水平旋转%.0f度" % rel["horizontal"])
        v = rel["vertical"]
        parts.append(f"{h_dir}视角")
        parts.append(f"{v_dir}")
        # parts.append(
        #     f"{v_dir}%s%.0f度" % ("向下" if v > 0 else ("向上" if v < 0 else ""),
        #                           abs(v) if abs(v) >= 0.5 else 0))
        t = rel.get("tilt", 0)
        if abs(t) >= 0.5:
            parts.append("%s旋转%.0f度" % ("顺时针" if t > 0 else "逆时针", abs(t)))

    # 3. 景深、光圈、对焦距离
    dof = get_bl_property(camera, "dof", None)
    use_dof = False
    focus_distance_m = None
    aperture_fstop = None
    if dof is not None:
        use_dof = bool(get_bl_property(dof, "use_dof", False))
        if use_dof:
            focus_obj = get_bl_property(dof, "focus_object", None)
            if focus_obj is not None:
                cam_loc = camera_obj.matrix_world.translation
                focus_loc = focus_obj.matrix_world.translation
                focus_distance_m = (Vector(focus_loc) - Vector(cam_loc)).length
            else:
                focus_distance_m = get_bl_property(dof, "focus_distance", None)
            aperture_fstop = get_bl_property(dof, "aperture_fstop", None)

    if use_dof:
        parts.append("浅景深")
        if aperture_fstop is not None:
            parts.append("光圈为f/%.1f" % aperture_fstop)
        # if focus_distance_m is not None:
        #     parts.append("焦点清晰地聚焦在%.2f米外" % focus_distance_m)
        parts.append("背景模糊")

    info = ",".join(parts)
    return f"相机信息({info})"


def try_set_camera_orientation_reference(app: "AIStudio"):
    """尝试设置相机参照的主体"""
    context = bpy.context

    ao = context.active_object
    ai = context.scene.blender_ai_studio_property
    if ao:
        items = []
        camera_obj = context.scene.camera

        if ao != ai.orientation_reference_object:
            ai.orientation_reference_object = ao
            items.append(f"已将相机主体参考设置为{ao.name}")
        if camera_obj:
            if ref_info := get_camera_info(context):
                items.append(ref_info)
        items.append("您也可以在相机属性中手动指定主体")
        if app:
            app.push_info_message(",".join(items))
    else:
        if app:
            app.push_info_message("请选择一个物体作为相机主体")
