from bpy.app.translations import pgettext as _T
from math import degrees

from .property import get_bl_property


def get_camera_info(context):
    if camera_obj := context.scene.camera:
        items = []

        # 活动相机对象本身（位置、旋转）
        for (vk, text) in [
            ("location", "位置(%.3f, %.3f, %.3f)"),
            ("rotation_euler", "旋转(%.2f°, %.2f°, %.2f°)"),
        ]:
            value = get_bl_property(camera_obj, vk, None)
            if value is not None:
                if vk == "location":
                    items.append(text % (value.x, value.y, value.z))
                elif vk == "rotation_euler":
                    items.append(text % (degrees(value.x), degrees(value.y), degrees(value.z)))

        # Camera 数据块（焦距、景深、光圈等）
        camera = get_bl_property(camera_obj, "data", None)
        if camera is not None:
            camera_type_map = {
                "PERSP": "透视",
                "ORTHO": "正交",
                "PANO": "全景",
                "CUSTOM": "自定义",
            }

            camera_type = get_bl_property(camera, "type", None)
            if camera_type is not None:
                items.append("相机类型为%s" % camera_type_map.get(camera_type, camera_type))

            lens_unit = get_bl_property(camera, "lens_unit", None)
            if lens_unit is not None:
                items.append("镜头单位为%s" % lens_unit)

            sensor_fit_map = {
                "AUTO": "自动",
                "HORIZONTAL": "水平",
                "VERTICAL": "垂直",
            }
            sensor_fit = get_bl_property(camera, "sensor_fit", None)
            if sensor_fit is not None:
                items.append("感光器适配%s" % sensor_fit_map.get(sensor_fit, sensor_fit))

            sensor_width = get_bl_property(camera, "sensor_width", None)
            sensor_height = get_bl_property(camera, "sensor_height", None)
            if sensor_width is not None and sensor_height is not None:
                items.append("感光器尺寸%.2f×%.2fmm" % (sensor_width, sensor_height))

            if camera_type == "ORTHO":
                ortho_scale = get_bl_property(camera, "ortho_scale", None)
                if ortho_scale is not None:
                    items.append("正交缩放%.3f" % ortho_scale)
            elif lens_unit == "FOV":
                angle = get_bl_property(camera, "angle", None)
                if angle is not None:
                    items.append("视场角%.2f°" % degrees(angle))
            else:
                lens = get_bl_property(camera, "lens", None)
                if lens is not None:
                    items.append("焦距%.2fmm" % lens)

            dof = get_bl_property(camera, "dof", None)
            if dof is not None:
                use_dof = bool(get_bl_property(dof, "use_dof", False))
                items.append("景深%s" % ("开启" if use_dof else "关闭"))

                if use_dof:
                    focus_object = get_bl_property(dof, "focus_object", None)
                    if focus_object is not None:
                        cam_loc = camera_obj.matrix_world.translation
                        focus_loc = focus_object.matrix_world.translation
                        distance = (focus_loc - cam_loc).length
                        items.append("景深对焦物体%s" % focus_object.name)
                        items.append("对焦物体距相机%.3fm" % distance)
                    else:
                        focus_distance = get_bl_property(dof, "focus_distance", None)
                        if focus_distance is not None:
                            items.append("景深焦距%.3fm" % focus_distance)

                    aperture_fstop = get_bl_property(dof, "aperture_fstop", None)
                    if aperture_fstop is not None:
                        items.append("光圈F%.2f" % aperture_fstop)

                    aperture_blades = get_bl_property(dof, "aperture_blades", None)
                    if aperture_blades is not None:
                        items.append("光圈叶片%s" % aperture_blades)

                    aperture_rotation = get_bl_property(dof, "aperture_rotation", None)
                    if aperture_rotation is not None:
                        items.append("光圈旋转%.2f°" % degrees(aperture_rotation))

                    aperture_ratio = get_bl_property(dof, "aperture_ratio", None)
                    if aperture_ratio is not None:
                        items.append("光圈纵横比%.3f" % aperture_ratio)
        info = ",".join(items)
        return f"相机信息({info})"
    else:
        raise Exception(_T("No Camera in Scene"))

