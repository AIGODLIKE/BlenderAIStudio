import bpy


class Privacy:
    init_privacy: bpy.props.BoolProperty(default=False)
    version_data: bpy.props.BoolProperty(default=False, name="Version Data",
                                         description="勾选后我们会收集Blender版本号及插件版本号")
    save_generated_images_to_cloud: bpy.props.BoolProperty(default=True, name="保留稳定模式生成的图片到云端",
                                                           description="勾选后将会将生成完成的图片保留到云端,避免生成图片丢失")
