from bpy.app.translations import pgettext as _T
from math import degrees

from .property import get_bl_property


def get_camera_info(context):
    if camera_obj := context.scene.camera:
        items = ["相机%s" % camera_obj.name]

        # 活动相机对象本身（位置、旋转、缩放）
        for (vk, text) in [
            ("location", "位置(%.3f, %.3f, %.3f)"),
            ("rotation_euler", "旋转(%.2f°, %.2f°, %.2f°)"),
            ("scale", "缩放(%.3f, %.3f, %.3f)"),
        ]:
            value = get_bl_property(camera_obj, vk, None)
            if value is not None:
                if vk == "location" or vk == "scale":
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

            clip_start = get_bl_property(camera, "clip_start", None)
            clip_end = get_bl_property(camera, "clip_end", None)
            if clip_start is not None and clip_end is not None:
                items.append("裁剪范围%.3f~%.3fm" % (clip_start, clip_end))

            shift_x = get_bl_property(camera, "shift_x", None)
            shift_y = get_bl_property(camera, "shift_y", None)
            if shift_x is not None and shift_y is not None:
                items.append("镜头偏移(%.3f,%.3f)" % (shift_x, shift_y))

            display_size = get_bl_property(camera, "display_size", None)
            if display_size is not None:
                items.append("视图显示尺寸%.2f" % display_size)

            passepartout_alpha = get_bl_property(camera, "passepartout_alpha", None)
            if passepartout_alpha is not None:
                items.append("取景框遮罩透明度%.2f" % passepartout_alpha)

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

            # 全景/自定义相机
            if camera_type == "PANO":
                pano_map = {
                    "EQUIRECTANGULAR": "等距柱状",
                    "EQUIANGULAR_CUBEMAP_FACE": "等角立方体贴图",
                    "MIRRORBALL": "镜面球",
                    "FISHEYE_EQUIDISTANT": "鱼眼等距",
                    "FISHEYE_EQUISOLID": "鱼眼等立体",
                    "FISHEYE_LENS_POLYNOMIAL": "鱼眼多项式",
                    "CENTRAL_CYLINDRICAL": "中心柱面",
                }
                pano_type = get_bl_property(camera, "panorama_type", None)
                if pano_type is not None:
                    items.append("全景类型%s" % pano_map.get(pano_type, pano_type))
                fisheye_fov = get_bl_property(camera, "fisheye_fov", None)
                if fisheye_fov is not None:
                    items.append("鱼眼视场%.2f°" % degrees(fisheye_fov))
                fisheye_lens = get_bl_property(camera, "fisheye_lens", None)
                if fisheye_lens is not None:
                    items.append("鱼眼焦距%.2fmm" % fisheye_lens)
                lat_min = get_bl_property(camera, "latitude_min", None)
                lat_max = get_bl_property(camera, "latitude_max", None)
                if lat_min is not None and lat_max is not None:
                    items.append("纬度范围%.2f°~%.2f°" % (degrees(lat_min), degrees(lat_max)))
                lon_min = get_bl_property(camera, "longitude_min", None)
                lon_max = get_bl_property(camera, "longitude_max", None)
                if lon_min is not None and lon_max is not None:
                    items.append("经度范围%.2f°~%.2f°" % (degrees(lon_min), degrees(lon_max)))

            if camera_type == "CUSTOM":
                custom_mode = get_bl_property(camera, "custom_mode", None)
                if custom_mode is not None:
                    items.append("自定义模式%s" % ("内部" if custom_mode == "INTERNAL" else "外部"))
                custom_filepath = get_bl_property(camera, "custom_filepath", None)
                if custom_filepath:
                    items.append("自定义着色器%s" % custom_filepath)

            bg_images = get_bl_property(camera, "background_images", None)
            if bg_images is not None and len(bg_images) > 0:
                items.append("背景图%d张" % len(bg_images))

            # 显示选项
            show_opts = []
            for (key, label) in [
                ("show_background_images", "背景图"),
                ("show_limits", "裁剪限制"),
                ("show_mist", "雾效"),
                ("show_name", "名称"),
                ("show_passepartout", "取景框遮罩"),
                ("show_safe_areas", "安全区"),
                ("show_safe_center", "中心安全区"),
                ("show_sensor", "感光器"),
                ("show_composition_thirds", "三分线"),
                ("show_composition_center", "中心线"),
                ("show_composition_center_diagonal", "对角中心"),
                ("show_composition_golden", "黄金比"),
                ("show_composition_golden_tria_a", "黄金三角A"),
                ("show_composition_golden_tria_b", "黄金三角B"),
                ("show_composition_harmony_tri_a", "和谐三角A"),
                ("show_composition_harmony_tri_b", "和谐三角B"),
            ]:
                v = get_bl_property(camera, key, None)
                if v is not None and v:
                    show_opts.append(label)
            if show_opts:
                items.append("显示开:%s" % ",".join(show_opts))

            # 立体
            stereo = get_bl_property(camera, "stereo", None)
            if stereo is not None:
                conv_dist = get_bl_property(stereo, "convergence_distance", None)
                if conv_dist is not None:
                    items.append("立体聚交距离%.3f" % conv_dist)
                interoc = get_bl_property(stereo, "interocular_distance", None)
                if interoc is not None:
                    items.append("立体瞳距%.4f" % interoc)
                conv_mode = get_bl_property(stereo, "convergence_mode", None)
                if conv_mode:
                    items.append("立体聚交模式%s" % conv_mode)
                pivot = get_bl_property(stereo, "pivot", None)
                if pivot:
                    items.append("立体轴心%s" % pivot)
        info = ",".join(items)
        return f"相机信息({info})"
    else:
        raise Exception(_T("No Camera in Scene"))

