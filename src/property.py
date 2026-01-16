from __future__ import annotations

import time
from datetime import datetime

import bpy

from .i18n import PROP_TCTX
from .studio.account import Account
from .utils import get_custom_icon, time_diff_to_str, calc_appropriate_aspect_ratio, refresh_image_preview, get_pref


class ImageItem(bpy.types.PropertyGroup):
    image: bpy.props.PointerProperty(type=bpy.types.Image, name="图片")


class ImageProperty(bpy.types.PropertyGroup):
    """
    图片属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    is_mask_image: bpy.props.BoolProperty(name="Is Mask Image", default=False)


class History:
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    generated_image: bpy.props.PointerProperty(type=bpy.types.Image, name="生成的图片")

    generation_time: bpy.props.StringProperty()
    generation_vendor: bpy.props.StringProperty()
    history: bpy.props.CollectionProperty(type=SceneProperty)

    start_time: bpy.props.IntProperty(name="开始时间")
    end_time: bpy.props.IntProperty(name="结束时间")

    def start_running(self, ):
        """开始运行"""
        self.generated_image = None
        self.origin_image = None
        self.start_time = int(time.time())
        self.end_time = 0

    def stop_running(self):
        """停止运行"""
        self.end_time = int(time.time())

    def save_to_history(self):
        oi = self.origin_image
        gi = self.generated_image

        nh = self.history.add()
        nh.generation_time = nh.name = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        nh.generation_vendor = "NanoBanana生成"
        nh.origin_image = oi
        nh.generated_image = gi
        nh.prompt = self.prompt
        nh.mask_index = self.mask_index
        nh.start_time = self.start_time
        nh.end_time = self.end_time

        for ri in self.reference_images:
            nri = nh.reference_images.add()
            nri.name = ri.name
            nri.image = ri.image

        for mi in self.mask_images:
            nmi = nh.mask_images.add()
            nmi.name = mi.name
            nmi.image = mi.image
        self.mask_images.clear()

        refresh_image_preview(oi)
        refresh_image_preview(gi)

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

    def draw_history(self, layout: bpy.types.UILayout,index):
        box = layout.box()

        column = box.column()
        row = column.row(align=True)
        row.context_pointer_set("history", self)
        row.prop(self, "expand_history", text=self.name,
                 icon="RIGHTARROW" if not self.expand_history else "DOWNARROW_HLT",
                 emboss=False,
                 )
        column.label(text=self.prompt)
        if not self.expand_history:
            row.context_pointer_set("history", self)
            row.operator("bas.remove_history", icon="PANEL_CLOSE", text="", emboss=False).index = index
            return
        row.operator("bas.restore_history", icon="FILE_PARENT", text="", emboss=False)

        column = box.column()
        gi = self.generated_image
        if gi:
            row = column.row()
            w, h = gi.size
            row.label(text=f"{w}*{h} px(72dpi)", icon_value=get_custom_icon("image_info_resolution"))
        column.label(text=self.generation_vendor, icon_value=get_custom_icon("image_info_vendor"))
        column.label(text=self.generation_time, icon_value=get_custom_icon("image_info_timestamp"))
        text = bpy.app.translations.pgettext("%s reference images") % len(self.mask_images)
        column.label(text=text)
        # text = bpy.app.translations.pgettext("%s mask images") % len(self.reference_images)
        # column.label(text=text)

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
        box.context_pointer_set("history", self)
        box.operator("bas.restore_history", icon="FILE_PARENT")

    @property
    def more_history_information(self) -> str:
        r = bpy.app.translations.pgettext("%s reference images") % len(self.mask_images)
        m = bpy.app.translations.pgettext("%s mask images") % len(self.reference_images)
        prompt = bpy.app.translations.pgettext("Prompt", msgctxt=PROP_TCTX)
        return (f"{self.generation_vendor}\n" +
                f"{self.generation_time}\n" +
                f"{r}\n" +
                f"{m}\n" +
                f"\n" +
                f"{prompt}\n" +
                f"{self.prompt}\n"
                )

    generate_history: bpy.props.StringProperty(default="[]", name="3d视图的生成记录")


class State:
    running_operator: bpy.props.StringProperty()
    running_state: bpy.props.StringProperty()
    running_message: bpy.props.StringProperty()

    def clear_running_state(self):
        self.running_operator = ""
        self.running_message = ""
        self.running_state = ""

    def draw_state(self, context, layout: bpy.types.UILayout):
        oii = context.scene.blender_ai_studio_property
        column = layout.column(align=True)
        state_str = self.running_state
        time_str = ""

        if state_str == "running":
            time_str = time_diff_to_str(time_diff=time.time() - oii.start_time)
        elif state_str in ("completed", "failed"):
            time_str = time_diff_to_str(time_diff=oii.end_time - oii.start_time)
        if state_str == "failed":
            column.alert = True
        for text in (
                self.running_operator,
                bpy.app.translations.pgettext(state_str.title()) + "  " + time_str,
                self.running_message,
        ):
            if text.strip():
                column.label(text=text)
        image = context.space_data.image
        if image == self.origin_image:
            if gi := self.generated_image:
                box = column.box()
                box.context_pointer_set("image", gi)
                if gi.preview:
                    box.template_icon(gi.preview.icon_id, scale=6)
                box.operator("bas.view_image", text="View Generated Image")
        elif image == self.generated_image:
            if oi := self.origin_image:
                box = column.box()
                box.context_pointer_set("image", oi)
                if oi.preview:
                    box.template_icon(oi.preview.icon_id, scale=6)
                box.operator("bas.view_image", text="View Origin Image")


class SceneProperty(bpy.types.PropertyGroup, History, State):
    """
    生成的属性
    """
    reference_images: bpy.props.CollectionProperty(type=ImageItem, name="多张参考图", description="最大14张输入图片")
    mask_images: bpy.props.CollectionProperty(type=ImageItem, name="编辑的图片")

    expand_ui: bpy.props.BoolProperty(name="Expand Ui Images", default=True,
                                      description="是否展开图片,在显示参考图")
    expand_history: bpy.props.BoolProperty(default=False)
    mask_index: bpy.props.IntProperty(name="Mask Image Index", default=0)

    prompt: bpy.props.StringProperty(
        name="Prompt",
        maxlen=1000,
    )

    resolution: bpy.props.EnumProperty(
        name="Out Resolution",
        items=[
            ("AUTO", "Auto", "Keep original resolution"),
            ("1K", "1k", "1k resolution"),
            ("2K", "2k", "2k resolution"),
            ("4K", "4k", "4k resolution"),
        ],
        default="AUTO",
    )

    aspect_ratio: bpy.props.EnumProperty(
        name="Aspect Ratio",
        items=[
            ("AUTO", "Auto", "Auto"),
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

    def get_out_aspect_ratio(self, context):
        """获取输出比例,如果context.space_data中有image,并且是AUTO这个属性,就按这个来获取最佳的比例
        错误时反回1:1
        """
        aspect_ratio = self.aspect_ratio
        if aspect_ratio == "AUTO":
            if image := getattr(context.space_data, "image", None):
                w, h = image.size
                if w == 0 or h == 0:  # 图片没有尺寸,就返回1:1
                    return "1:1"
                return calc_appropriate_aspect_ratio(w, h)
            return "1:1"  # 图片没有找到,就返回1:1
        return aspect_ratio

    def get_out_resolution_px_by_aspect_ratio_and_resolution(self, context) -> tuple[int, int]:
        """
        获取输出分辨率(px) 从 图像比例 及分辨率(1k,2k,4k)
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
        }.get((self.get_out_aspect_ratio(context), self.get_out_resolution(context)), (0, 0))

    def get_out_resolution(self, context) -> str:
        resolution = self.resolution
        if resolution == "AUTO":
            if image := getattr(context.space_data, "image", None):
                w, h = image.size
                resolution_str = "1K"
                if w >= 4096 or h >= 4096:
                    resolution_str = "4K"
                elif w >= 2048 or h >= 2048:
                    resolution_str = "2K"
                return resolution_str
            return "1K"
        return resolution

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
                    icon_value=get_custom_icon("select_references_by_file"),
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

    def get_points_consumption(self, context):
        """
        获取消耗的价格
        [{'modelId': 'gemini-3-pro-image-preview', 'price': {'1K': 36, '2K': 36, '4K': 63}}]
        :return:
        """
        pref = get_pref()
        price_table = Account.get_instance().price_table
        if pref.is_backup_mode:
            resolution = self.get_out_resolution(bpy.context)
            model_item = [i for i in price_table if
                          isinstance(i, dict) and i.get('modelId', None) == 'gemini-3-pro-image-preview']
            if model_item:  # 模型项
                if price := model_item[0].get('price', None):  # 价格项
                    return price.get(resolution, -999)
        else:
            ...
        return -999


class_list = [
    ImageItem,
    SceneProperty,
    ImageProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(class_list)

from bpy.app.handlers import persistent


def clear_run():
    bpy.context.scene.blender_ai_studio_property.clear_running_state()


@persistent
def load_post(a, b):
    clear_run()


def register():
    register_class()
    bpy.types.Scene.blender_ai_studio_property = bpy.props.PointerProperty(type=SceneProperty)
    bpy.types.Image.blender_ai_studio_property = bpy.props.PointerProperty(type=ImageProperty)
    bpy.types.Text.blender_ai_studio_prompt_hash = bpy.props.StringProperty()
    bpy.app.timers.register(clear_run, persistent=True)
    bpy.app.handlers.load_post.append(load_post)


def unregister():
    del bpy.types.Scene.blender_ai_studio_property
    del bpy.types.Image.blender_ai_studio_property
    del bpy.types.Text.blender_ai_studio_prompt_hash
    unregister_class()
    bpy.app.handlers.load_post.remove(load_post)
