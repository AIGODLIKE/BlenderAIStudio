from __future__ import annotations

import time
from datetime import datetime

import bpy

from .. import logger
from ..i18n import PROP_TCTX
from ..studio.account import Account, TaskStatus
from ..studio.config.model_registry import ModelRegistry
from ..utils import get_custom_icon, time_diff_to_str, get_pref
from ..utils.area import find_ai_image_editor_space_data
from ..utils.property import get_bl_property, set_bl_property


class ImageItem(bpy.types.PropertyGroup):
    """集合使用的项,需要使用PropertyGroup包装一下才能被CollectionProperty使用"""
    image: bpy.props.PointerProperty(type=bpy.types.Image, name="图片")


class MaskImageProperty(bpy.types.PropertyGroup):
    """
    图片属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    is_mask_image: bpy.props.BoolProperty(name="Is Mask Image", default=False)


class GeneralProperty:
    """
    参考图片属性
    在历史及生成面板都有使用
    """

    reference_images: bpy.props.CollectionProperty(type=ImageItem, name="多张参考图", description="最大14张输入图片")
    mask_images: bpy.props.CollectionProperty(type=ImageItem, name="编辑的图片")
    mask_index: bpy.props.IntProperty(name="Mask Image Index", default=0)

    prompt: bpy.props.StringProperty(name="Prompt", maxlen=10000, )


class HistoryState:
    running_operator: bpy.props.StringProperty()
    running_state: bpy.props.StringProperty(name="running    completed    failed TaskState")
    running_message: bpy.props.StringProperty()
    running_progress: bpy.props.FloatProperty(name="进度", min=0, max=1.0)

    start_time: bpy.props.IntProperty(name="开始时间")
    end_time: bpy.props.IntProperty(name="结束时间")

    @property
    def is_running(self) -> bool:
        return self.running_state == "running"

    def clear_running_state(self):
        self.running_operator = ""
        self.running_message = ""
        self.running_state = ""


class HistoryFailedCheck:
    """历史失败检查
    如果生成的过程中失败了,要检查是否正确的生成了的
    """
    task_id: bpy.props.StringProperty(name="任务ID")
    failed_check_state: bpy.props.EnumProperty(name="Failed Check State", items=[
        ("NOT_CHECKED", "未检查", ""),
        # ("FAILED", "检查失败", ""), 应该没有这种情况
        ("COMPLETED", "检查完成", ""),
        ("CHECKING", "检查中", ""),
    ], default="NOT_CHECKED")
    is_refund_points: bpy.props.BoolProperty(name="已退回积分", default=False)
    failed_check_message: bpy.props.StringProperty(name="检查信息")

    @property
    def is_have_failed_check(self) -> bool:
        """是需要错误检查的"""
        if self.running_state == "failed":  # 生成状态是错误
            if self.failed_check_state != "COMPLETED":  # 没检查完成 ,就需要一直检查
                return True
        return False

    def draw_failed_check(self, layout: bpy.types.UILayout):
        column = layout.column()
        if self.is_refund_points:
            column.label(text="已退还积分")
        if self.failed_check_message:
            for j in self.failed_check_message.split("\n"):
                column.label(text=j)


class EditHistory(HistoryState, GeneralProperty, HistoryFailedCheck, bpy.types.PropertyGroup):
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    generated_images: bpy.props.CollectionProperty(type=ImageItem, name="生成的图片")

    generation_time: bpy.props.StringProperty(name="生成时间 2025-6-6")
    generation_model: bpy.props.StringProperty(name="生成用的模型")

    expand_history: bpy.props.BoolProperty(default=False)

    def add_generated_image(self, image):
        gih = self.generated_images.add()
        gih.image = image

    def start_running(self, model_name: str):
        """开始运行"""
        self.generated_image = None
        self.origin_image = None
        self.start_time = int(time.time())
        self.end_time = 0
        self.generation_model = model_name
        self.generation_time = self.name = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def stop_running(self):
        """停止运行"""
        self.end_time = int(time.time())

    def restore_history(self, context):
        """恢复历史,将历史项里面的全部复制回来"""
        oii = context.scene.blender_ai_studio_property
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

    def draw_history(self, context, layout: bpy.types.UILayout, index):
        if self.is_running:
            self.draw_task(context, layout)
            return
        box = layout.box()

        self.draw_debug(box)
        self.draw_failed_check(box)

        column = box.column(align=True)
        row = column.row(align=True)
        row.context_pointer_set("history", self)
        row.prop(self, "expand_history", text=self.name,
                 icon="RIGHTARROW" if not self.expand_history else "DOWNARROW_HLT",
                 emboss=False,
                 )

        if self.running_state == "failed":  # 错误图标
            rr = row.row()
            rr.alert = True
            rr.label(text="", icon="ERROR")

        row.operator("bas.remove_history", icon="PANEL_CLOSE", text="", emboss=False).index = index
        row.operator("bas.restore_history", icon="FILE_PARENT", text="", emboss=False)
        if self.prompt:
            column.label(text=self.prompt)

        elif not self.expand_history:
            column.label(text="No Prompt")
            if oi := self.origin_image:
                row = box.row()
                row.context_pointer_set("image", oi)
                row.template_icon(oi.preview.icon_id, scale=5)

        if self.running_state == "failed" and self.running_message:
            for j in self.running_message.split("\n"):
                rr = column.row(align=True)
                rr.alert = True
                rr.label(text=j)
            # TODO 重试按钮
        if not self.expand_history:
            return

        column = box.column(align=True)
        if generated_images := self.generated_images:
            row = column.row()
            for i in generated_images:
                w, h = i.image.size
                row.label(text=f"{w}*{h} px(72dpi)", icon_value=get_custom_icon("image_info_resolution"))
        column.label(text=self.generation_model, icon_value=get_custom_icon("image_info_vendor"))
        column.label(text=self.generation_time, icon_value=get_custom_icon("image_info_timestamp"))
        text = bpy.app.translations.pgettext("%s reference images") % len(self.reference_images)
        column.label(text=text, icon_value=get_custom_icon("select_references_by_bl_image"))

        column = box.column(align=True)
        icon_size = 1
        if generated_images := self.generated_images:
            for gih in generated_images:
                gi = gih.image
                row = column.row()
                row.context_pointer_set("image", gi)
                row.template_icon(gi.preview.icon_id, scale=icon_size)
                row.operator("bas.view_image", text="View Generated Image")
        if oi := self.origin_image:
            row = column.row()
            row.context_pointer_set("image", oi)
            row.template_icon(oi.preview.icon_id, scale=icon_size)
            row.operator("bas.view_image", text="View Origin Image")

        box.context_pointer_set("history", self)
        box.operator("bas.restore_history", icon="FILE_PARENT")

    @property
    def more_history_information(self) -> str:
        r = bpy.app.translations.pgettext("%s reference images") % len(self.mask_images)
        m = bpy.app.translations.pgettext("%s mask images") % len(self.reference_images)
        prompt = bpy.app.translations.pgettext("Prompt", msgctxt=PROP_TCTX)
        return (f"{self.generation_model}\n" +
                f"{self.generation_time}\n" +
                f"{r}\n" +
                f"{m}\n" +
                f"\n" +
                f"{prompt}\n" +
                f"{self.prompt}\n"
                )

    def draw_task(self, context, layout: bpy.types.UILayout):
        column = layout.box().column(align=True)

        state_str = self.running_state
        time_str = ""

        if state_str == "running":
            time_str = time_diff_to_str(time_diff=time.time() - self.start_time)
        elif state_str in ("completed", "failed"):
            time_str = time_diff_to_str(time_diff=self.end_time - self.start_time)
        if state_str == "failed":
            column.alert = True
        for text in (
                self.running_operator,
                bpy.app.translations.pgettext(state_str.title()) + "  " + time_str,
                self.running_message,
        ):
            if text.strip():
                column.label(text=text)
        self.draw_debug(column)

    def draw_debug(self, layout):
        if get_pref().use_dev_ui:
            column = layout.box().column(align=True)
            column.label(text=self.task_id)
            column.prop(self, "failed_check_state")
            column.separator(type="LINE")
            column.label(text=f"is_have_failed_check:{self.is_have_failed_check}")
            column.prop(self, "is_refund_points")
            column.prop(self, "running_state")


class DynamicEnumeration:
    _model_registry = ModelRegistry.get_instance()

    def get_models_name_items(self, context):
        try:
            pref = get_pref()
            models = self._model_registry.list_models(
                auth_mode=pref.account_auth_mode,
                category="IMAGE_GENERATION",  # 目前只显示图像生成模型
            )
            return [(m.model_name, m.model_name, m.provider) for m in models]
        except Exception as e:
            print(e)
            return [("None", "None", "None"), ]

    def get_model_name(self):
        account_auth_mode = get_pref().account_auth_mode
        key = f"{account_auth_mode}_model_name"

        return get_bl_property(self, key, 0)

    def set_model_name(self, value):
        account_auth_mode = get_pref().account_auth_mode
        key = f"{account_auth_mode}_model_name"
        set_bl_property(self, key, value)

    model_name: bpy.props.EnumProperty(items=get_models_name_items, name="Model", get=get_model_name,
                                       set=set_model_name)

    def get_resolution_items(self, context) -> list[(str, str, str),]:
        try:
            model = self._model_registry.get_model(self.model_name)
            if res := model.get_parameter("resolution"):
                if options := res.get("options", None):
                    return [(i, i, i) for i in options]
        except Exception as e:
            print(e)
        return [("None", "None", "None"), ]

    def get_resolution(self):
        key = f"{self.model_name}_resolution"

        return get_bl_property(self, key, 0)

    def set_resolution(self, value):
        key = f"{self.model_name}_resolution"
        set_bl_property(self, key, value)

    resolution: bpy.props.EnumProperty(
        name="Out Resolution",
        items=get_resolution_items,
        get=get_resolution,
        set=set_resolution
    )

    def get_aspect_ratio_items(self, context) -> list[(str, str, str),]:
        """
        [
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
        """
        try:
            model = self._model_registry.get_model(self.model_name)
            if aspect_ratio := model.get_parameter("aspect_ratio"):
                if options := aspect_ratio.get("options", None):
                    return [(i, i, i) for i in options]
        except Exception as e:
            print(e)
        return [("None", "None", "None"), ]

    def get_aspect_ratio(self):
        key = f"{self.model_name}_aspect_ratio"

        return get_bl_property(self, key, 0)

    def set_aspect_ratio(self, value):
        key = f"{self.model_name}_aspect_ratio"
        set_bl_property(self, key, value)

    aspect_ratio: bpy.props.EnumProperty(
        name="Aspect Ratio",
        items=get_aspect_ratio_items,
        get=get_aspect_ratio,
        set=set_aspect_ratio
    )


class SceneFailedCheck:

    def check_all_failed(self, immediately=False):
        """在场景属性下使用
        找所有的失败问题
        immediately 立刻刷新,如果是请求的时候发生的错误就立即检查一次
        """
        account = Account.get_instance()

        have_check_task_ids = []  # 需要推送检查的id
        checking_task_ids = {}  # 需要检查有没有检查结果的id

        for history in self.edit_history:
            if history.is_have_failed_check:
                history.failed_check_state = "CHECKING"  # 将此项设置为检查中
                have_check_task_ids.append(history.task_id)
                checking_task_ids[history.task_id] = history

        if immediately:
            account.add_task_ids_to_fetch_status_now(have_check_task_ids)
        else:
            account.add_task_ids_to_fetch_status_threaded(have_check_task_ids)  # 发送检查任务

        check_result = account.fetch_task_history(checking_task_ids.keys())  # 查找检查结果
        for task_id, thd in check_result.items():
            match_history = checking_task_ids.get(task_id, None)
            if thd and match_history:
                if thd.state == TaskStatus.UNKNOWN:  # 没有发送到服务器的情况
                    match_history.failed_check_message = "Inspection stage error, points not deducted"
                    match_history.failed_check_state = "COMPLETED"
                elif thd.state == TaskStatus.FAILED:  # 生成失败的情况
                    match_history.is_refund_points = True
                    match_history.failed_check_message = "Generation failed, points not deducted\nPlease check your prompt words&reference pictures"
                    match_history.failed_check_state = "COMPLETED"
                    match_history.running_message = thd.error_message
                    # logger.info(f"生成失败 task_id:{task_id} {thd}")
                elif thd.state == TaskStatus.SUCCESS:  # 生成成功的情况
                    # 将成功的图片加载到Blender中
                    try:
                        for mime_type, file_path in thd.outputs:
                            if mime_type.startswith("image/"):
                                image = bpy.data.images.load(file_path)

                                match_history.add_generated_image(image)  # 添加生成的图片到历史
                                match_history.failed_check_message = "Retrieve image again completed"

                                if image.preview:
                                    image.preview.reload()
                                else:
                                    image.preview_ensure()

                                space_data_list = find_ai_image_editor_space_data()  # 将图片加载到图片编辑器中
                                for space_data in space_data_list:
                                    setattr(space_data, "image", image)

                                logger.info(f"Retrieve the image again task_id:{task_id} {image}")
                    except Exception as e:
                        logger.error(f"Failed to load image: task_id:{task_id}  {e}")
                    finally:
                        # 不管加不加载得成功生成的内容都是成功的,
                        match_history.running_message = ""
                        match_history.running_state = "completed"  # 标记为生成完成
                        match_history.failed_check_state = "COMPLETED"

                elif thd.state == TaskStatus.RUNNING:  # 这个图片正在生成中,这样的情况一般是在生成图片的时候强制关闭了Blender
                    match_history.failed_check_message = "Generating..."
                else:
                    logger.error(f"其他情况 task_id:{task_id} {thd.state}")
        if immediately:
            return 1
        if len(have_check_task_ids) == 0:
            return 3  # 下次检查时间 在bpy.app.timers
        return 1  # 如果有检查的图片,则返回1


class SceneProperty(bpy.types.PropertyGroup, GeneralProperty, DynamicEnumeration, SceneFailedCheck):
    """
    生成的属性
    """
    expand_ui: bpy.props.BoolProperty(name="Expand Ui Images", default=True,
                                      description="是否展开图片,在显示参考图")
    edit_history: bpy.props.CollectionProperty(type=EditHistory, name="这个是编辑的历史记录")
    generate_history: bpy.props.StringProperty(default="[]", name="3d视图的生成记录")

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

    @property
    def running_task_list(self) -> list[EditHistory]:
        """反回运行中的任务列表
        只要是在运行中就反回这个"""
        return [h for h in self.edit_history if h.is_running]

    def draw_reference_images(self, context, layout: bpy.types.UILayout):
        """绘制参考图片"""
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

        column = box.column()
        is_small_width = context.region.width < 200  # 是太小的宽度
        if alert:
            col = column.column()
            col.alert = True
            col.label(text="Too many reference images, please remove some")
            col.label(text="Up to 12 images can be selected")
        for i, item in enumerate(self.reference_images):
            if item.image:
                if is_small_width:
                    ly = column.column(align=True)
                else:
                    ly = column.row(align=True)
                ly.box().template_icon(item.image.preview.icon_id, scale=5)

                if is_small_width:
                    lay = ly.row(align=True)
                else:
                    lay = ly.column(align=True)
                lay.operator("bas.remove_reference_image", text="", icon="X",
                             ).index = i
                lay.operator("bas.replace_reference_image", text="", icon="FILE_REFRESH",
                             ).index = i
        if rl == 0:
            box.label(text="Click top right ops to reference")

    def get_points_consumption(self, context):
        """获取消耗的价格"""
        pref = get_pref()
        if pref.is_backup_mode:
            registry = ModelRegistry.get_instance()
            strategy = Account.get_instance().pricing_strategy
            resolution = "1K" if self.resolution == "None" else self.resolution  # 处理没有分辨率的时候
            price = registry.calc_price(self.model_name, strategy, resolution)
            return price or 99999
        else:
            ...
        return 99999

    def clear_task_running_state(self):
        """
        清理任务的运行状态
        只会在启动插件或加载文件时进行
        会出现这种情况一般是生成结果还没反回时Blender就被关闭了
        """
        for h in self.edit_history:
            if h.running_state not in ("completed", "failed", "cancelled"):
                h.running_state = "failed"
            if h.failed_check_state not in (
                    "NOT_CHECKED",
                    # "FAILED",
                    "COMPLETED",
            ):
                h.failed_check_state = "NOT_CHECKED"


class_list = [
    ImageItem,
    EditHistory,
    SceneProperty,
    MaskImageProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(class_list)

from bpy.app.handlers import persistent


def clear_run():
    bpy.context.scene.blender_ai_studio_property.clear_task_running_state()


@persistent
def load_post(a, b):
    clear_run()


def register():
    register_class()
    bpy.types.Scene.blender_ai_studio_property = bpy.props.PointerProperty(type=SceneProperty)
    bpy.types.Image.blender_ai_studio_property = bpy.props.PointerProperty(type=MaskImageProperty)
    bpy.types.Text.blender_ai_studio_prompt_hash = bpy.props.StringProperty()
    bpy.app.timers.register(clear_run, first_interval=0.1, persistent=True)
    bpy.app.handlers.load_post.append(load_post)


def unregister():
    del bpy.types.Scene.blender_ai_studio_property
    del bpy.types.Image.blender_ai_studio_property
    del bpy.types.Text.blender_ai_studio_prompt_hash
    unregister_class()
    bpy.app.handlers.load_post.remove(load_post)
