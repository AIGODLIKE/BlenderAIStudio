import bpy
import webbrowser
import tempfile
from enum import Enum
from pathlib import Path
from typing import Iterable
from .gui.texture import TexturePool
from .gui.app.app import AppHud
from .gui.app.renderer import imgui
from .gui.app.style import Const
from .tasks import (
    Task,
    TaskResult,
    TaskState,
    TaskManager,
    GeminiImageGenerationTask,
)
from .wrapper import with_child, BaseAdapter, WidgetDescriptor, DescriptorFactory
from ..i18n import PROP_TCTX
from ..preferences import get_pref
from ..utils.render import render_scene_to_png, render_scene_depth_to_png
from ..timer import Timer


def get_tool_panel_width():
    for region in bpy.context.area.regions:
        if region.type != "TOOLS":
            continue
        return region.width
    return 0


class StudioImagesDescriptor(WidgetDescriptor):
    ptype = "STUDIO_IMAGES"

    def display(self, wrapper, app):
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child("##Image", (0, 0), child_flags=self.flags):
            imgui.text(self.display_name)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)

            with with_child("##Inner", (0, 0), child_flags=self.flags):
                imgui.push_style_var(imgui.StyleVar.CELL_PADDING, imgui.get_style().item_spacing)
                imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, (0, 0))
                imgui.push_style_color(imgui.Col.TABLE_BORDER_STRONG, Const.TRANSPARENT)
                imgui.begin_table("##Table", 3, imgui.TableFlags.BORDERS)
                for i in range(3):
                    imgui.table_setup_column(f"##Column{i}", imgui.TableColumnFlags.WIDTH_STRETCH, 0, i)
                for i, img in enumerate(self.value):
                    imgui.table_next_column()
                    imgui.push_id(f"##Image{i}")
                    self.display_image_with_close(img, i)
                    imgui.pop_id()

                if len(self.value) < self.widget_def.get("limit", 999):
                    imgui.table_next_column()
                    imgui.push_id("##Upload")
                    self.display_upload_image()
                    imgui.pop_id()
                imgui.end_table()

                imgui.pop_style_var(2)
                imgui.pop_style_color(1)
            imgui.same_line()
            imgui.pop_style_color()
        imgui.pop_style_color(1)

    def display_upload_image(self):
        bw = bh = imgui.get_content_region_avail()[0]
        icon = TexturePool.get_tex_id("image_new")
        tex = TexturePool.get_tex(icon)
        fbw = tex.width / max(tex.width, tex.height) if tex else 1
        fbh = tex.height / max(tex.width, tex.height) if tex else 1
        imgui.begin_group()
        imgui.set_next_item_allow_overlap()
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        clicked = imgui.button(f"##{self.title}_{self.widget_name}1", (bw, bh))
        iw, ih = (bw * fbw, bh * fbh)
        pmin = imgui.get_item_rect_min()
        pmini = (pmin[0] + (bw - iw) / 2, pmin[1] + (bh - ih) / 2)
        pmax = imgui.get_item_rect_max()
        pmaxi = (pmax[0] - (bw - iw) / 2, pmax[1] - (bh - ih) / 2)
        dl = imgui.get_window_draw_list()
        dl.add_image_rounded(icon, pmini, pmaxi, (0, 0), (1, 1), 0xFFFFFFFF, 15)
        imgui.pop_style_color(3)
        if clicked:
            pos = imgui.get_mouse_pos()
            imgui.set_next_window_pos((pos[0] - 40, pos[1] + 50), cond=imgui.Cond.ALWAYS)
            self.adapter.on_image_action(self.widget_name, "upload_image")
        imgui.end_group()

    def display_image_with_close(self, img_path: str = "", index=-1):
        if not img_path:
            return
        bw = bh = imgui.get_content_region_avail()[0]
        icon = TexturePool.get_tex_id(img_path)
        tex = TexturePool.get_tex(icon)
        fbw = tex.width / max(tex.width, tex.height) if tex else 1
        fbh = tex.height / max(tex.width, tex.height) if tex else 1
        imgui.begin_group()
        imgui.set_next_item_allow_overlap()
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        clicked = imgui.button(f"##{self.title}_{self.widget_name}1", (bw, bh))
        iw, ih = (bw * fbw, bh * fbh)
        pmin = imgui.get_item_rect_min()
        pmini = (pmin[0] + (bw - iw) / 2, pmin[1] + (bh - ih) / 2)
        pmax = imgui.get_item_rect_max()
        pmaxi = (pmax[0] - (bw - iw) / 2, pmax[1] - (bh - ih) / 2)
        dl = imgui.get_window_draw_list()
        dl.add_image_rounded(icon, pmini, pmaxi, (0, 0), (1, 1), 0xFFFFFFFF, 15)
        col = (84 / 255, 84 / 255, 84 / 255, 1)
        is_hovered = False
        if imgui.is_item_active():
            col = (67 / 255, 207 / 255, 124 / 255, 1)
        elif imgui.is_mouse_hovering_rect(pmin, pmax):
            col = (67 / 255, 207 / 255, 124 / 255, 1)
            is_hovered = True
        col = imgui.get_color_u32(col)
        dl.add_rect((pmin[0] + 1, pmin[1] + 1), (pmax[0] - 1, pmax[1] - 1), col, 15, thickness=4)
        imgui.pop_style_color(3)
        if clicked:
            pos = imgui.get_mouse_pos()
            imgui.set_next_window_pos((pos[0] - 40, pos[1] + 50), cond=imgui.Cond.ALWAYS)
            self.adapter.on_image_action(self.widget_name, "replace_image", index)

        imgui.same_line()
        pos = imgui.get_cursor_pos()
        bw2, bh2 = 30, 30
        isx = imgui.get_style().cell_padding[0]
        imgui.set_cursor_pos((pos[0] - bw2, pos[1]))

        imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)

        if imgui.button(f"##{self.title}_{self.widget_name}x", (bw2, bh2)):
            self.adapter.on_image_action(self.widget_name, "delete_image", index)
        imgui.pop_style_color(3)
        if is_hovered:
            imgui.set_cursor_pos(pos)
            col = (67 / 255, 207 / 255, 124 / 255, 1)
            if imgui.is_item_active():
                col = Const.CLOSE_BUTTON_ACTIVE
            elif imgui.is_item_hovered():
                col = Const.CLOSE_BUTTON_HOVERED
            col = imgui.get_color_u32(col)
            icon = TexturePool.get_tex_id("close")
            dl = imgui.get_window_draw_list()
            dl.add_image(icon, imgui.get_item_rect_min(), imgui.get_item_rect_max(), col=col)
        imgui.same_line()
        imgui.dummy((isx, 0))
        imgui.end_group()


class StudioClient(BaseAdapter):
    VENDOR = ""

    def __init__(self) -> None:
        self._name = self.VENDOR
        self.help_url = ""
        self.task_manager = TaskManager.get_instance()
        self.task_id: str = ""
        self.is_task_submitting = False

    def get_ctxt(self) -> str:
        return PROP_TCTX

    def get_value(self, prop: str):
        return getattr(self, prop)

    def set_value(self, prop: str, value):
        setattr(self, prop, value)

    def get_properties(self) -> list[str]:
        return []

    def draw_generation_panel(self):
        pass

    def draw_setting_panel(self):
        pass

    def draw_history_panel(self):
        pass

    def new_generate_task(self):
        pass

    def query_task_status(self) -> dict:
        if not self.task_id:
            return {}
        if not (task := self.task_manager.get_task(self.task_id)):
            return {}
        return task.get_info()

    def query_task_result(self):
        if not self.task_id:
            return None
        # 无任务
        if not (task := self.task_manager.get_task(self.task_id)):
            return None
        # 未完成
        if not task.is_finished():
            return
        # 无结果
        if not (result := task.result):
            return None
        # 执行失败
        if not result.is_success():
            error_msg = result.error_message
            print(f"任务失败: {error_msg}")
            return None
        image_data = result.get_data()
        print("任务完成！")
        return image_data


class NanoBanana(StudioClient):
    VENDOR = "NanoBanana"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.help_url = "https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn"
        self.input_image_type = "CameraRender"
        self.prompt = ""
        self.reference_images: list[str] = []
        self.size_config = "Auto"
        self.resolution = "1K"
        self.meta = {
            "input_image_type": {
                "display_name": "Input Image",
                "category": "Input",
                "type": "ENUM",
                "hide_title": False,
                "options": [
                    "CameraRender",
                    "CameraDepth",
                ],
            },
            "prompt": {
                "display_name": "Prompt",
                "category": "Input",
                "type": "STRING",
                "hide_title": False,
                "multiline": True,
                "default": "",
            },
            "reference_images": {
                "display_name": "Reference Images",
                "category": "Input",
                "type": StudioImagesDescriptor.ptype,
                "hide_title": False,
                "limit": 12,
            },
            "size_config": {
                "display_name": "Size Config",
                "category": "Input",
                "type": "ENUM",
                "hide_title": False,
                "options": [
                    "Auto",
                    "1:1",
                    "9:16",
                    "16:9",
                    "3:4",
                    "4:3",
                    "3:2",
                    "2:3",
                    "5:4",
                    "4:5",
                    "21:9",
                ],
            },
            "resolution": {
                "display_name": "Resolution",
                "category": "Input",
                "type": "ENUM",
                "hide_title": False,
                "options": [
                    "1K",
                    "2K",
                    "4K",
                ],
            },
            "api_key": {
                "display_name": "API Key",
                "category": "Settings",
                "type": "STRING",
                "hide_title": True,
                "multiline": False,
                "default": "",
            },
        }

    @property
    def api_key(self) -> str:
        return get_pref().nano_banana_api

    @api_key.setter
    def api_key(self, value: str) -> None:
        get_pref().nano_banana_api = value
        bpy.context.preferences.use_preferences_save = True

    def get_properties(self) -> Iterable[str]:
        return self.meta.keys()

    def get_meta(self, prop: str):
        return self.meta.get(prop, {})

    def on_image_action(self, prop: str, action: str, index: int = -1) -> None:
        if action == "upload_image":
            upload_image(self, prop)
        elif action == "replace_image":
            replace_image(self, prop, index)
        elif action == "delete_image":
            delete_image(self, prop, index)

    @staticmethod
    def calc_appropriate_aspect_ratio(width: int, height: int) -> str:
        aspect_ratio_presets = {
            "1:1": 1 / 1,
            "9:16": 9 / 16,
            "16:9": 16 / 9,
            "3:4": 3 / 4,
            "4:3": 4 / 3,
            "3:2": 3 / 2,
            "2:3": 2 / 3,
            "5:4": 5 / 4,
            "4:5": 4 / 5,
            "21:9": 21 / 9,
        }
        return min(aspect_ratio_presets, key=lambda k: abs(aspect_ratio_presets[k] - width / height))

    def new_generate_task(self):
        if self.is_task_submitting:
            print("有任务正在提交，请稍后")
            return
        self.is_task_submitting = True
        Timer.put(self.job)

    def job(self):
        self.is_task_submitting = False
        # 1. 创建任务
        path_dir = Path.home().joinpath("Desktop/OutputImage/AIStudio")
        path_dir.mkdir(parents=True, exist_ok=True)
        temp_image_path = path_dir.joinpath("Depth.png")
        _temp_image_path = temp_image_path.as_posix()
        # temp_image_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        # _temp_image_path = temp_image_path.name
        # 渲染图片
        scene = bpy.context.scene
        if self.input_image_type == "CameraRender":
            render_scene_to_png(scene, _temp_image_path)
        elif self.input_image_type == "CameraDepth":
            render_scene_depth_to_png(scene, _temp_image_path)
        reference_image = self.reference_images[0] if self.reference_images else None
        resolution = (1024, 1024)
        if self.resolution == "1K":
            resolution = (1024, 1024)
        elif self.resolution == "2K":
            resolution = (2048, 2048)
        elif self.resolution == "4K":
            resolution = (4096, 4096)
        size_config = self.size_config
        if size_config == "Auto":
            width = bpy.context.scene.render.resolution_x
            height = bpy.context.scene.render.resolution_y
            size_config = self.calc_appropriate_aspect_ratio(width, height)
        task = GeminiImageGenerationTask(
            api_key=self.api_key,
            image_path=_temp_image_path,
            reference_image_path=reference_image,
            user_prompt=self.prompt,
            width=resolution[0],
            height=resolution[1],
            aspect_ratio=self.size_config,
        )
        print("渲染到：", _temp_image_path)
        # temp_image_path.close()
        # if Path(_temp_image_path).exists():
        #     Path(_temp_image_path).unlink()

        # 2. 注册回调
        def on_state_changed(event_data):
            _task: Task = event_data["task"]
            old_state: TaskState = event_data["old_state"]
            new_state: TaskState = event_data["new_state"]
            print(f"状态改变: {old_state.value} -> {new_state.value}")

        def on_progress(event_data):
            {
                "current_step": 2,
                "total_steps": 4,
                "percentage": 0.5,
                "message": "正在调用 API...",
                "details": {},
            }
            _task: Task = event_data["task"]
            progress: dict = event_data["progress"]
            percent = progress["percentage"]
            message = progress["message"]
            print(f"进度: {percent * 100}% - {message}")

        def on_completed(event_data):
            # result_data = {
            #     "image_data": b"",
            #     "mime_type": "image/png",
            #     "width": 1024,
            #     "height": 1024,
            # }
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            result_data: dict = result.data
            # 存储结果
            save_file = path_dir.joinpath("Output.png")
            save_file.write_bytes(result_data["image_data"])
            print(f"任务完成: {_task.task_id}")
            # TODO 存储历史记录

        def on_failed(event_data):
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            if not result.success:
                print(result.error)

        task.register_callback("state_changed", on_state_changed)
        task.register_callback("progress_updated", on_progress)
        task.register_callback("completed", on_completed)
        task.register_callback("failed", on_failed)
        print(f"任务提交: {task.task_id}")

        # 3. 提交到管理器
        self.task_id = self.task_manager.submit_task(task)


def upload_image(client: StudioClient, prop: str):
    def upload_image_callback(file_path: str):
        client.get_value(prop).append(file_path)

    from .ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(upload_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def replace_image(client: StudioClient, prop: str, index: int = -1):
    def replace_image_callback(file_path: str):
        try:
            client.get_value(prop)[index] = file_path
        except IndexError:
            client.get_value(prop).append(file_path)

    from .ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(replace_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def delete_image(client: StudioClient, prop: str, index: int):
    client.get_value(prop).pop(index)


class Dream(StudioClient):
    VENDOR = "Dream"


class StudioWrapper:
    """
    材质节点描述器：封装材质节点及其可控属性
    """

    def __init__(self):
        self.studio_client: StudioClient = None
        self.display_name: str = ""
        self.widgets: dict[str, list[WidgetDescriptor]] = {}
        self.adapter: BaseAdapter = None

    @property
    def title(self):
        return self.studio_client.VENDOR if self.studio_client else ""

    def load(self, client: StudioClient):
        self.studio_client = client
        self.adapter = client
        self.display_name = client.VENDOR
        self.widgets.clear()

        for prop_name in client.get_properties():
            meta = client.get_meta(prop_name)
            widget_type = meta.get("type", "UNKOWN")
            widget = DescriptorFactory.create(prop_name, widget_type, self)
            widget.adapter = client
            widget.widget_def = meta
            category = widget.category
            if category not in self.widgets:
                self.widgets[category] = []
            self.widgets[category].append(widget)
        self.adapter = None

    def get_widgets_by_category(self, category: str):
        return self.widgets.get(category, [])


class AIStudioPanelType(Enum):
    NONE = "none"
    GENERATION = "generation"
    SETTINGS = "settings"


class AIStudio(AppHud):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_panel = AIStudioPanelType.GENERATION
        self.clients = {c.VENDOR: c() for c in StudioClient.__subclasses__()}
        self.fill_fake_clients()
        self.active_client = NanoBanana.VENDOR
        self.clients_wrappers: dict[str, StudioWrapper] = {}
        self.init_clients_wrapper()

    def fill_fake_clients(self):
        fake_clients = [
            "Nano Banana Pro (Gemini 3 Pro Image)",
            "FLUX.2 [pro]",
            "Seedream 4.0",
            "FLUX.2 [flex]",
            "Imagen 4 Ultra Preview 0606",
            "Nano Banana (Gemini 2.5 Flash Image)",
            "Imagen 4 Preview 0606",
            "ImagineArt 1.5 Preview",
            "FLUX.2 [dev]",
            "GPT-5",
            "Seedream 3.0",
            "Wan 2.5 Preview",
            "Vivago 2.1",
            "Qwen Image Edit 2509",
            "Kolors 2.1",
            "Lucid Origin Ultra",
            "FLUX.1 Kontext [max]",
            "Vidu Q2",
            "Lucid Origin Fast",
            "Recraft V3",
            "HunyuanImage 3.0 (Fal)",
            "Vivago 2.0",
            "Reve V1",
            "GPT Image 1 (high)",
            "FLUX.1.1 [pro] Ultra",
            "Imagen 3 (v002)",
            "Ideogram 3.0",
            "Reve Image (Halfmoon)",
            "Dreamina 3.1",
            "FLUX.1 Kontext [pro]",
            "FLUX.1.1 [pro]",
            "Imagen 4 Fast Preview 0606",
            "SRPO",
            "SeedEdit 3.0",
            "HiDream-I1-Dev",
            "HunyuanImage 2.1",
            "FLUX.1 [pro]",
            "GPT Image 1 Mini (medium)",
            "Qwen-Image",
            "Image-01",
            "HiDream-I1-Fast",
            "FIBO",
            "Midjourney v7 Alpha",
            "Midjourney v6.1",
            "Ideogram v2",
            "FLUX.1 [dev]",
            "Midjourney v6",
            "Luma Photon",
            "Ideogram v2 Turbo",
            "Stable Diffusion 3.5 Large Turbo",
            "Stable Diffusion 3.5 Large",
            "Phoenix 1.0 Ultra",
            "Firefly Image 5 Preview",
            "Ideogram v1",
            "Infinity 8B",
            "Krea 1",
            "Stable Diffusion 3 Large",
            "FLUX.1 Krea [dev]",
            "MAI Image 1",
            "Ideogram v2a",
            "FLUX.1 Kontext [dev]",
            "Ideogram v2a Turbo",
            "Firefly Image 4",
            "FLUX.1 [schnell]",
            "Playground v3 (beta)",
            "HiDream-E1.1",
            "Phoenix 0.9 Ultra",
            "Runway Gen-4 Image",
            "Phoenix 1.0 Fast",
            "Gemini 2.0 Flash Preview",
            "Recraft 20B",
            "Luma Photon Flash",
            "Gemini 2.0 Flash Experimental",
            "Playground v2.5",
            "Lumina Image v2",
            "DALLE 3 HD",
            "Firefly Image 3",
            "step1x-edit-v1p2-preview",
            "Grok 2",
            "Stable Diffusion 3.5 Medium",
            "DALLE 3",
            "Bagel",
            "Stable Diffusion 3 Medium",
            "Bria 3.2",
            "Amazon Titan G1 v2 (Standard)",
            "Sana Sprint 1.6B",
            "OmniGen V2",
            "Stable Diffusion 3 Large Turbo",
            "Stable Diffusion 1.6",
            "Amazon Titan G1 (Standard)",
            "SDXL Lightning",
            "Step1X-Edit",
            "Stable Diffusion XL 1.0",
            "HiDream-E1-Full",
            "DALLE 2",
            "Stable Diffusion 2.1",
            "Janus Pro",
            "Stable Diffusion 1.5",
        ]
        for fc in fake_clients:
            self.clients[fc] = StudioClient()

    def init_clients_wrapper(self):
        for cname, client in self.clients.items():
            wrapper = StudioWrapper()
            wrapper.load(client)
            self.clients_wrappers[cname] = wrapper

    def handler_draw(self, _area: bpy.types.Area):
        self.draw_studio_panel()

    def draw_studio_panel(self):
        window_size = 540, 1359
        window_pos = get_tool_panel_width(), 400
        imgui.set_next_window_pos(window_pos, imgui.Cond.ALWAYS)
        imgui.set_next_window_size(window_size, imgui.Cond.ALWAYS)
        flags = 0
        flags |= imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_MOVE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SCROLL_WITH_MOUSE
        flags |= imgui.WindowFlags.NO_SCROLLBAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS

        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, Const.RP_WINDOW_P)
        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.RP_WINDOW_R)
        imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, Const.RP_FRAME_P)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_R)
        imgui.push_style_var(imgui.StyleVar.CELL_PADDING, Const.RP_CELL_P)
        imgui.push_style_var_x(imgui.StyleVar.ITEM_SPACING, 0)

        imgui.push_style_color(imgui.Col.WINDOW_BG, Const.RP_L_BOX_BG)
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)

        istyle = imgui.get_style()
        fp = istyle.frame_padding
        cp = istyle.cell_padding

        imgui.begin("##AIStudioPanel", False, flags)
        # Left
        if True:
            imgui.begin_group()
            imgui.set_cursor_pos((fp[0], fp[1] - cp[1]))

            btn_size = 40, 40
            left_w = btn_size[0] + (fp[0] + fp[0]) * 2
            imgui.begin_table("CategoryTable", 1, outer_size=(left_w - fp[0], 0))
            subpanel_config = {
                AIStudioPanelType.GENERATION: "generation",
                AIStudioPanelType.SETTINGS: "settings",
            }
            for subpanel in subpanel_config:
                imgui.table_next_column()
                imgui.begin_group()
                icon = TexturePool.get_tex_id(subpanel_config[subpanel])
                if imgui.button(f"##Btn{subpanel}", (btn_size[0] + fp[0] * 2, btn_size[1] + fp[1] * 2)):
                    self.active_panel = subpanel
                col = Const.CLOSE_BUTTON_NORMAL
                if imgui.is_item_active():
                    col = Const.CLOSE_BUTTON_ACTIVE
                elif imgui.is_item_hovered():
                    col = Const.CLOSE_BUTTON_HOVERED
                if subpanel == self.active_panel:
                    col = Const.BUTTON_SELECTED
                col = imgui.get_color_u32(col)
                dl = imgui.get_window_draw_list()
                pmin = imgui.get_item_rect_min()
                pmin = pmin[0] + fp[0], pmin[1] + fp[1]
                pmax = imgui.get_item_rect_max()
                pmax = pmax[0] - fp[0], pmax[1] - fp[1]
                dl.add_image(icon, pmin, pmax, col=col)
                imgui.end_group()

            imgui.end_table()
            imgui.end_group()

        imgui.same_line()
        imgui.pop_style_var(6)

        # Right
        if True:
            wx, wy = imgui.get_window_pos()
            ww, wh = imgui.get_window_size()

            lt = wx + left_w, wy
            rb = wx + ww, wy + wh
            col = imgui.get_color_u32(Const.RP_R_BOX_BG)
            r = Const.LP_WINDOW_R + 4
            dl = imgui.get_window_draw_list()
            dl.add_rect_filled(lt, rb, col, r, imgui.DrawFlags.ROUND_CORNERS_RIGHT)

            cx, cy = imgui.get_cursor_pos()
            cx += Const.RP_R_WINDOW_P[0]
            cy += Const.RP_R_WINDOW_P[1]
            imgui.set_cursor_pos((cx, cy - cp[1]))
            imgui.begin_table("##RightInner", 1, outer_size=(ww - left_w - Const.RP_R_WINDOW_P[0] * 2, 0))

            imgui.table_next_column()
            imgui.begin_group()
            self.draw_generation_panel()
            self.draw_setting_panel()
            imgui.end_group()

            imgui.end_table()

        imgui.end()
        imgui.pop_style_color(4)

    def draw_generation_panel(self):
        if self.active_panel != AIStudioPanelType.GENERATION:
            return
        dummy_size = 0, 26 / 2
        imgui.push_style_var_x(imgui.StyleVar.CELL_PADDING, Const.LP_CELL_P[0])
        imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, 0)

        if True:
            self.font_manager.push_h1_font()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.button("无限之心")
            imgui.same_line()
            icon = TexturePool.get_tex_id("beta_header")
            tex = TexturePool.get_tex(icon)
            scale = imgui.get_text_line_height() / tex.height
            imgui.image_button("", icon, (tex.width * scale, tex.height * scale), tint_col=Const.BUTTON_SELECTED)
            imgui.pop_style_color(3)
            imgui.same_line()
            self.draw_panel_close_button()
            self.font_manager.pop_font()
            imgui.dummy(dummy_size)

        # 生成面板
        if True:
            imgui.dummy(dummy_size)
            imgui.begin_table("#Engine", 4)
            imgui.table_setup_column("#EngineEle1", imgui.TableColumnFlags.WIDTH_FIXED, 0, 0)
            imgui.table_setup_column("#EngineEle2", imgui.TableColumnFlags.WIDTH_FIXED, 0, 1)
            imgui.table_setup_column("#EngineEle3", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 2)
            imgui.table_setup_column("#EngineEle4", imgui.TableColumnFlags.WIDTH_FIXED, 0, 3)
            imgui.table_next_column()
            self.font_manager.push_h2_font()
            imgui.text("引擎")
            self.font_manager.pop_font()

            # 小字
            imgui.table_next_column()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.push_style_var_y(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0)
            imgui.push_font(None, 12 * Const.SCALE)
            imgui.button("Engine")
            imgui.pop_font()
            imgui.pop_style_var()
            imgui.pop_style_color(3)

            imgui.table_next_column()
            imgui.text("")

            imgui.table_next_column()
            imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.75)
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
            imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
            self.font_manager.push_h1_font(24)
            label = " 帮助"
            label_size = imgui.calc_text_size(label)
            if imgui.button(f"##{label}", (112, 44)):
                help_url = self.clients.get(self.active_client, StudioClient()).help_url
                if help_url:
                    webbrowser.open(help_url)

            pmin = imgui.get_item_rect_min()
            pmax = imgui.get_item_rect_max()
            icon_size = imgui.get_text_line_height()
            inner_width = icon_size + label_size[0]
            inner_height = label_size[1]
            offset_x = (pmax[0] - pmin[0] - inner_width) * 0.5
            offset_y = (pmax[1] - pmin[1] - inner_height) * 0.5
            pmin = pmin[0] + offset_x, pmin[1] + offset_y
            pmax = pmax[0] - offset_x, pmax[1] - offset_y
            icon = TexturePool.get_tex_id("help")
            dl = imgui.get_window_draw_list()
            dl.add_image(icon, pmin, (pmin[0] + icon_size, pmax[1]))
            col = imgui.get_color_u32(Const.BUTTON_SELECTED)
            dl.add_text((pmin[0] + icon_size, pmin[1]), col, label)

            self.font_manager.pop_font()
            imgui.pop_style_color(3)
            imgui.pop_style_var(2)

            imgui.end_table()
            imgui.dummy((dummy_size[0], dummy_size[1] - 8))

            imgui.push_style_var_y(imgui.StyleVar.WINDOW_PADDING, 24)
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
            imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, Const.CHILD_P)
            imgui.push_style_var(imgui.StyleVar.FRAME_BORDER_SIZE, Const.CHILD_BS)
            imgui.push_style_var(imgui.StyleVar.POPUP_ROUNDING, 24)
            imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, (8, 8))

            imgui.push_style_color(imgui.Col.FRAME_BG, Const.WINDOW_BG)
            imgui.push_style_color(imgui.Col.POPUP_BG, Const.POPUP_BG)
            imgui.push_style_color(imgui.Col.HEADER, Const.BUTTON)
            imgui.push_style_color(imgui.Col.HEADER_ACTIVE, Const.BUTTON_ACTIVE)
            imgui.push_style_color(imgui.Col.HEADER_HOVERED, Const.BUTTON_HOVERED)

            if True:
                self.draw_clients()

            flags = 0
            flags |= imgui.ChildFlags.FRAME_STYLE
            avail_rect = imgui.get_content_region_avail()
            avail_height = avail_rect[1]
            full_width = avail_rect[0]
            wp = imgui.get_style().window_padding
            item_spacing = imgui.get_style().item_spacing
            gen_btn_height = 79
            imgui.push_style_color(imgui.Col.FRAME_BG, (48 / 255, 48 / 255, 48 / 255, 1))
            with with_child("Outer", (0, avail_height - gen_btn_height - wp[1] - item_spacing[1]), flags):
                wrapper = self.clients_wrappers.get(self.active_client, StudioWrapper())
                for widget in wrapper.get_widgets_by_category("Input"):
                    widget.col_bg = Const.WINDOW_BG
                    widget.col_widget = Const.FRAME_BG
                    widget.display_begin(widget, self)
                    widget.display(widget, self)
                    widget.display_end(widget, self)
            imgui.pop_style_color()

            # 底部按钮
            if True:
                avail_rect = imgui.get_content_region_avail()
                cpos = imgui.get_cursor_pos()
                imgui.set_cursor_pos_y(cpos[1] + avail_rect[1] - gen_btn_height - wp[1])

                imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.6)
                imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, 15)
                imgui.push_style_color(imgui.Col.BUTTON, Const.SLIDER_NORMAL)

                self.font_manager.push_h1_font()
                client = self.clients.get(self.active_client, StudioClient())
                is_rendering = False
                label = "  开始AI渲染"
                if client.is_task_submitting:
                    label = "  任务提交中"
                status = client.query_task_status()
                # "running", "processing"
                task_state: TaskState = status.get("state", "")
                if task_state == "running":
                    is_rendering = True
                    label = "  正在AI渲染"
                if is_rendering:
                    imgui.push_style_color(imgui.Col.BUTTON, (255 / 255, 141 / 255, 26 / 255, 1))
                    imgui.push_style_color(imgui.Col.BUTTON_HOVERED, (255 / 255, 87 / 255, 51 / 255, 1))

                label_size = imgui.calc_text_size(label)
                if imgui.button("##开始AI渲染", (full_width, gen_btn_height)):
                    print("开始AI渲染")
                    client.new_generate_task()
                if is_rendering:
                    imgui.pop_style_color(2)
                pmin = imgui.get_item_rect_min()
                pmax = imgui.get_item_rect_max()
                inner_width = 30 + label_size[0]
                inner_height = label_size[1]
                offset_x = (pmax[0] - pmin[0] - inner_width) * 0.5
                offset_y = (pmax[1] - pmin[1] - inner_height) * 0.5
                pmin = pmin[0] + offset_x, pmin[1] + offset_y
                pmax = pmax[0] - offset_x, pmax[1] - offset_y
                icon = TexturePool.get_tex_id("start_ai_generate")
                dl = imgui.get_window_draw_list()
                dl.add_image(icon, pmin, (pmin[0] + 30, pmax[1]))
                col = imgui.get_color_u32((1, 1, 1, 1))
                dl.add_text((pmin[0] + 30, pmin[1]), col, label)
                self.font_manager.pop_font()

                imgui.pop_style_var(2)
                imgui.pop_style_color()

            imgui.pop_style_var(6)
            imgui.pop_style_color(5)

        imgui.pop_style_var(2)

    def draw_clients(self):
        flags = 0
        flags |= imgui.ChildFlags.FRAME_STYLE
        flags |= imgui.ChildFlags.AUTO_RESIZE_Y
        flags |= imgui.ChildFlags.ALWAYS_AUTO_RESIZE
        imgui.push_style_color(imgui.Col.FRAME_BG, Const.WINDOW_BG)
        with with_child("##Clients", (0, 0), child_flags=flags):
            imgui.push_item_width(-1)
            imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, Const.RP_FRAME_P[0])
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
            imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, Const.RP_CHILD_IS)
            imgui.push_style_color(imgui.Col.FRAME_BG, Const.FRAME_BG)
            items = list(self.clients)
            if imgui.begin_combo("##Item", self.active_client):
                for item in items:
                    is_selected = self.active_client == item
                    if imgui.selectable(item, is_selected)[0]:
                        self.active_client = item
                    if is_selected:
                        imgui.set_item_default_focus()
                imgui.end_combo()
            imgui.pop_style_color()
            imgui.pop_style_var(3)
            imgui.pop_item_width()
        imgui.pop_style_color(1)

    def draw_setting_panel(self):
        if self.active_panel != AIStudioPanelType.SETTINGS:
            return
        dummy_size = 0, 26 / 2
        imgui.push_style_var_x(imgui.StyleVar.CELL_PADDING, Const.LP_CELL_P[0])
        imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, (0, 0))

        if True:
            self.font_manager.push_h1_font()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.button("设置")
            imgui.same_line()
            icon = TexturePool.get_tex_id("settings_header")
            tex = TexturePool.get_tex(icon)
            scale = imgui.get_text_line_height() / tex.height
            imgui.image_button("", icon, (tex.width * scale, tex.height * scale), tint_col=Const.BUTTON_SELECTED)
            imgui.pop_style_color(3)
            imgui.same_line()
            self.draw_panel_close_button()
            self.font_manager.pop_font()
            imgui.dummy(dummy_size)

        # 设置面板
        if True:
            imgui.dummy(dummy_size)
            self.font_manager.push_h2_font()
            imgui.text("服务")
            self.font_manager.pop_font()
            imgui.dummy((dummy_size[0], dummy_size[1] - 8))

            imgui.push_style_var_y(imgui.StyleVar.WINDOW_PADDING, 24)
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
            imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, Const.CHILD_P)
            imgui.push_style_var(imgui.StyleVar.FRAME_BORDER_SIZE, Const.CHILD_BS)
            imgui.push_style_var(imgui.StyleVar.POPUP_ROUNDING, 24)
            imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, 15)

            imgui.push_style_color(imgui.Col.FRAME_BG, Const.WINDOW_BG)
            imgui.push_style_color(imgui.Col.POPUP_BG, Const.POPUP_BG)
            imgui.push_style_color(imgui.Col.HEADER, Const.BUTTON)
            imgui.push_style_color(imgui.Col.HEADER_ACTIVE, Const.BUTTON_ACTIVE)
            imgui.push_style_color(imgui.Col.HEADER_HOVERED, Const.BUTTON_HOVERED)

            for wrapper in self.clients_wrappers.values():
                imgui.text(wrapper.display_name)
                for widget in wrapper.get_widgets_by_category("Settings"):
                    widget.col_bg = Const.WINDOW_BG
                    widget.col_widget = Const.WINDOW_BG
                    widget.display_begin(widget, self)
                    widget.display(widget, self)
                    widget.display_end(widget, self)

            imgui.pop_style_var(6)
            imgui.pop_style_color(5)

            imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, 26)
            self.font_manager.push_h1_font()
            imgui.text("免责声明")
            imgui.text("反馈问题")
            imgui.text("交流群")
            self.font_manager.pop_font()
            imgui.pop_style_var()

        imgui.pop_style_var(2)

    def draw_panel_close_button(self):
        # 关闭按钮
        style = imgui.get_style()
        fp = style.frame_padding
        h = imgui.get_frame_height_with_spacing()
        aw = imgui.get_content_region_avail()[0]
        imgui.dummy((aw - style.item_spacing[0] - h, 0))
        imgui.same_line()
        imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)

        if imgui.button("##CloseBtn", (h, h)):
            self.active_panel = AIStudioPanelType.NONE
            self.queue_shoutdown()
        imgui.pop_style_color(3)
        col = Const.CLOSE_BUTTON_NORMAL
        if imgui.is_item_active():
            col = Const.CLOSE_BUTTON_ACTIVE
        elif imgui.is_item_hovered():
            col = Const.CLOSE_BUTTON_HOVERED
        col = imgui.get_color_u32(col)
        icon = TexturePool.get_tex_id("close")
        dl = imgui.get_window_draw_list()
        pmin = imgui.get_item_rect_min()
        pmin = (pmin[0] + fp[1] * 2 + 2, pmin[1] + fp[1] + 1)
        pmax = imgui.get_item_rect_max()
        pmax = (pmax[0], pmax[1] - fp[1] - 1)
        dl.add_image(icon, pmin, pmax, col=col)


DescriptorFactory.register(StudioImagesDescriptor.ptype, StudioImagesDescriptor)
