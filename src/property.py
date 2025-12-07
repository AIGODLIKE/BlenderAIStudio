from __future__ import annotations

from datetime import datetime

import bpy

from .utils import get_custom_icon


class ImageItem(bpy.types.PropertyGroup):
    image: bpy.props.PointerProperty(type=bpy.types.Image, name="图片")


class ImageProperty(bpy.types.PropertyGroup):
    """
    图片属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    is_mask_image: bpy.props.BoolProperty(name="Is Mask Image", default=False)


class SceneProperty(bpy.types.PropertyGroup):
    """
    生成的属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    generated_image: bpy.props.PointerProperty(type=bpy.types.Image, name="生成的图片")
    reference_images: bpy.props.CollectionProperty(type=ImageItem, name="多张参考图", description="最大14张输入图片")
    mask_images: bpy.props.CollectionProperty(type=ImageItem, name="编辑的图片")

    expand_ui: bpy.props.BoolProperty(name="Expand Ui Images", default=True,
                                      description="是否展开图片,在显示参考图和历史记录时使用")
    mask_index: bpy.props.IntProperty(name="Mask Image Index", default=0)

    prompt: bpy.props.StringProperty(
        name="Prompt",
        maxlen=1000,
    )

    history: bpy.props.CollectionProperty(type=SceneProperty)
    resolution: bpy.props.EnumProperty(
        name="Out Resolution",
        items=[
            ("AUTO", "Auto (Match Input)", "Keep original resolution"),
            ("1K", "1k", "1k resolution"),
            ("2K", "2k", "2k resolution"),
            ("4K", "4k", "4k resolution"),
        ],
        default="AUTO",
    )
    running_operator: bpy.props.StringProperty()
    running_state: bpy.props.StringProperty()
    running_message: bpy.props.StringProperty()
    aspect_ratio: bpy.props.EnumProperty(
        name="Aspect Ratio",
        items=[
            ("1:1", "1:1", "1:1"),
            ("2:3", "2:3", "2:3"),
            ("3:2", "3:2", "3:2"),
            ("3:4", "3:4", "3:4"),
            ("4:3", "4:3", "4:3"),
            ("4:5", "4:5", "4:5"),
            ("5:4", "5:4", "5:4"),
            ("9:16", "9:16", "9:16"),
            ("16:9", "16:9", "16:9"),
            ("21:9", "21:9", "21:9"),
        ]
    )

    def get_out_resolution(self, context) -> tuple[int, int]:
        """
        1:1	1024x1024	1210	2048x2048	1210	4096x4096	2000
        2:3	848x1264	1210	1696x2528	1210	3392x5056	2000
        3:2	1264x848	1210	2528x1696	1210	5056x3392	2000
        3:4	896x1200	1210	1792x2400	1210	3584x4800	2000
        4:3	1200x896	1210	2400x1792	1210	4800x3584	2000
        4:5	928x1152	1210	1856x2304	1210	3712x4608	2000
        5:4	1152x928	1210	2304x1856	1210	4608x3712	2000
        9:16	768x1376	1210	1536x2752	1210	3072x5504	2000
        16:9	1376x768	1210	2752x1536	1210	5504x3072	2000
        21:9	1584x672	1210	3168x1344	1210	6336x2688	2000
        https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn#aspect_ratios_and_image_size
        """
        return {
            ("1:1", "1K"): (1024, 1024),
            ("1:1", "2K"): (2048, 2048),
            ("1:1", "4K"): (4096, 4096),
            ("2:3", "1K"): (848, 1264),
            ("2:3", "2K"): (1696, 2528),
            ("2:3", "4K"): (3392, 5056),
            ("3:2", "1K"): (1264, 848),
            ("3:2", "2K"): (2528, 1696),
            ("3:2", "4K"): (5056, 3392),
            ("3:4", "1K"): (896, 1200),
            ("3:4", "2K"): (1792, 2400),
            ("3:4", "4K"): (3584, 4800),
            ("4:3", "1K"): (1200, 896),
            ("4:3", "2K"): (2400, 1792),
            ("4:3", "4K"): (4800, 3584),
            ("4:5", "1K"): (928, 1152),
            ("4:5", "2K"): (1856, 2304),
            ("4:5", "4K"): (3712, 4608),
            ("5:4", "1K"): (1152, 928),
            ("5:4", "2K"): (2304, 1856),
            ("5:4", "4K"): (4608, 3712),
            ("9:16", "1K"): (768, 1376),
            ("9:16", "2K"): (1536, 2752),
            ("9:16", "4K"): (3072, 5504),
            ("16:9", "1K"): (1376, 768),
            ("16:9", "2K"): (2752, 1536),
            ("16:9", "4K"): (5504, 3072),
            ("21:9", "1K"): (1584, 672),
            ("21:9", "2K"): (3168, 1344),
            ("21:9", "4K"): (6336, 2688),
        }.get((self.aspect_ratio, self.get_resolution_str(context)), (0, 0))

    def get_resolution_str(self, context) -> str:
        resolution = self.resolution
        if resolution == "AUTO":
            if image := context.space_data.image:
                w, h = image.size
                resolution_str = "1K"
                if w >= 4096 or h >= 4096:
                    resolution_str = "4K"
                elif w >= 2048 or h >= 2048:
                    resolution_str = "2K"
                return resolution_str
        return resolution

    def clear_running_state(self):
        self.running_operator = ""
        self.running_message = ""
        self.running_state = ""

    def save_to_history(self):
        nh = self.history.add()
        nh.name = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        nh.origin_image = self.origin_image
        nh.generated_image = self.generated_image
        nh.prompt = self.prompt
        nh.mask_index = self.mask_index

        for ri in self.reference_images:
            nri = nh.reference_images.add()
            nri.name = ri.name
            nri.image = ri.image

        for mi in self.mask_images:
            nmi = nh.mask_images.add()
            nmi.name = mi.name
            nmi.image = mi.image
        self.mask_images.clear()

    def restore_history(self, context):
        """恢复历史,将历史项里面的全部复制回来"""
        oii = context.scene.blender_ai_studio_property
        oii.origin_image = self.origin_image
        oii.generated_image = self.generated_image
        oii.prompt = self.prompt
        oii.mask_index = self.mask_index

        oii.reference_images.clear()
        for ri in self.reference_images:
            nri = oii.reference_images.add()
            nri.name = ri.name
            nri.image = ri.image

        oii.mask_images.clear()
        for mi in self.mask_images:
            nmi = oii.mask_images.add()
            nmi.name = mi.name
            nmi.image = mi.image

    @property
    def all_references_images(self) -> list[bpy.types.Image]:
        return [i.image for i in self.reference_images if i.image]

    @property
    def active_mask(self) -> bpy.types.Image | None:
        """
        获取当前使用的蒙版图片
        """
        index = self.mask_index
        if 0 <= index <= len(self.mask_images) - 1:
            return self.mask_images[index].image
        return None

    def draw_reference_images(self, context, layout: bpy.types.UILayout):
        box = layout.box()

        # 参考图头
        row = box.row()
        row.alignment = "EXPAND"
        rr = row.row()
        rr.alignment = "LEFT"
        text = bpy.app.translations.pgettext_iface("Reference Images")
        rl = len(self.reference_images)
        alert = rl > 12
        count = f" ({rl})" if rl else ""
        rr.alert = alert
        rr.prop(self, "expand_ui", text=f"{text}{count}",
                icon="RIGHTARROW" if not self.expand_ui else "DOWNARROW_HLT",
                emboss=False,
                )
        if alert:
            rr.label(text="", icon="ERROR")
        rr = row.row()
        rr.alignment = "RIGHT"
        rr.operator("bas.select_reference_image_by_image", text="",
                    emboss=False,
                    icon_value=get_custom_icon("select_references_by_bl_image")
                    )
        rr.operator("bas.select_reference_image_by_file", text="",
                    emboss=False,
                    icon_value=get_custom_icon("select_references_by_bl_image"),
                    )
        if not self.expand_ui:
            return

        """
        # row.template_ID(item, "icons", open="icons.open")
        # row.template_ID_preview(item, "icons", hide_buttons=True)
        # row.template_preview(item.icons)
        # row.template_icon_view(item, "icons")
        # row.template_image(item, "icons")
        # column.label(text=f"{context.region.width}")
        ly.template_search_preview(self, "reference_image", bpy.data, "images")
        for i in bpy.context.scene.blender_ai_studio_property.mask_images:print(i)
        """

        column = box.column()
        is_small_width = context.region.width < 200
        if alert:
            col = column.column()
            col.alert = True
            col.label(text="Too many reference images, please remove some")
            col.label(text="Up to 12 images can be selected")
        # column.prop(self, "scale")
        for i, item in enumerate(self.reference_images):
            if item.image:
                if is_small_width:
                    ly = column.column(align=True)
                else:
                    ly = column.row(align=True)
                ly.box().template_icon(item.image.preview.icon_id, scale=5)

                if is_small_width:
                    lay = ly.row(align=True)
                    # lay.scale_x = self.scale
                else:
                    lay = ly.column(align=True)
                    # lay.scale_y = self.scale
                lay.operator("bas.remove_reference_image", text="", icon="X",
                             # emboss=False
                             ).index = i
                lay.operator("bas.replace_reference_image", text="", icon="FILE_REFRESH",
                             # emboss=False
                             ).index = i
        if rl == 0:
            box.label(text="Click top right ops to reference")

    scale: bpy.props.FloatProperty(default=2.75)

    def draw_history(self, layout: bpy.types.UILayout):
        box = layout.box()

        column = box.column()
        row = column.row(align=True)
        row.context_pointer_set("history", self)
        row.prop(self, "expand_ui", text=self.name,
                 icon="RIGHTARROW" if not self.expand_ui else "DOWNARROW_HLT",
                 emboss=False,
                 )

        column.label(text=self.prompt)
        if not self.expand_ui:
            row.context_pointer_set("history", self)
            row.operator("bas.restore_history", icon="FILE_PARENT", text="",
                         emboss=False,
                         )
            return

        if oi := self.origin_image:
            row = box.row()
            row.context_pointer_set("image", oi)
            row.template_icon(oi.preview.icon_id, scale=2)
            row.operator("bas.view_image", text="View Origin Image")
        if gi := self.generated_image:
            row = box.row()
            row.context_pointer_set("image", gi)
            row.template_icon(gi.preview.icon_id, scale=2)
            row.operator("bas.view_image", text="View Generated Image")
        text = bpy.app.translations.pgettext("%s reference images") % len(self.mask_images)
        box.label(text=text)
        text = bpy.app.translations.pgettext("%s mask images") % len(self.reference_images)
        box.label(text=text)
        box.context_pointer_set("history", self)
        box.operator("bas.restore_history", icon="FILE_PARENT")


class_list = [
    ImageItem,
    SceneProperty,
    ImageProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(class_list)


def clear_run():
    bpy.context.scene.blender_ai_studio_property.clear_running_state()


def register():
    register_class()
    bpy.types.Scene.blender_ai_studio_property = bpy.props.PointerProperty(type=SceneProperty)
    bpy.types.Image.blender_ai_studio_property = bpy.props.PointerProperty(type=ImageProperty)
    bpy.types.Text.blender_ai_studio_prompt_hash = bpy.props.StringProperty()
    bpy.app.timers.register(clear_run, persistent=True)


def unregister():
    del bpy.types.Scene.blender_ai_studio_property
    del bpy.types.Image.blender_ai_studio_property
    del bpy.types.Text.blender_ai_studio_prompt_hash
    unregister_class()
