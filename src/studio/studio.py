import bpy
from enum import Enum
from typing import Iterable
from .gui.texture import TexturePool
from .gui.app.app import AppHud
from .gui.app.renderer import imgui
from .gui.app.style import Const
from .wrapper import with_child, BaseAdapter, WidgetDescriptor, DescriptorFactory
from ..i18n import PROP_TCTX


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
                imgui.push_style_var_x(imgui.StyleVar.CELL_PADDING, 0)
                imgui.begin_table("##Table", 3)
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

                imgui.pop_style_var(1)
            imgui.same_line()
            imgui.pop_style_color()
        imgui.pop_style_color(1)

    def display_upload_image(self):
        bw, bh = 102, 102
        icon = TexturePool.get_tex_id("image_new")
        tex = TexturePool.get_tex(icon)
        fbw = tex.width / max(tex.width, tex.height) if tex else 1
        fbh = tex.height / max(tex.width, tex.height) if tex else 1
        imgui.begin_group()
        imgui.set_next_item_allow_overlap()
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        clicked = imgui.button(f"##{self.title}_{self.widget_name}1", (bw * fbw, bh * fbh))
        pmin = imgui.get_item_rect_min()
        pmax = imgui.get_item_rect_max()
        dl = imgui.get_window_draw_list()
        dl.add_image(icon, pmin, pmax)
        imgui.pop_style_color(3)
        if clicked:
            pos = imgui.get_mouse_pos()
            imgui.set_next_window_pos((pos[0] - 40, pos[1] + 50), cond=imgui.Cond.ALWAYS)
            self.adapter.on_image_action(self.widget_name, "upload_image")
        imgui.end_group()

    def display_image_with_close(self, img_path: str = "", index=-1):
        if not img_path:
            return
        bw, bh = 102, 102
        icon = TexturePool.get_tex_id(img_path)
        tex = TexturePool.get_tex(icon)
        fbw = tex.width / max(tex.width, tex.height) if tex else 1
        fbh = tex.height / max(tex.width, tex.height) if tex else 1
        imgui.begin_group()
        imgui.set_next_item_allow_overlap()
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        clicked = imgui.button(f"##{self.title}_{self.widget_name}1", (bw * fbw, bh * fbh))
        pmin = imgui.get_item_rect_min()
        pmax = imgui.get_item_rect_max()
        dl = imgui.get_window_draw_list()
        dl.add_image(icon, pmin, pmax)
        imgui.pop_style_color(3)
        if clicked:
            pos = imgui.get_mouse_pos()
            imgui.set_next_window_pos((pos[0] - 40, pos[1] + 50), cond=imgui.Cond.ALWAYS)
            self.adapter.on_image_action(self.widget_name, "replace_image", index)

        imgui.same_line()
        pos = imgui.get_cursor_pos()
        bw2, bh2 = 30, 30
        isx = imgui.get_style().item_spacing[0]
        imgui.set_cursor_pos((pos[0] - isx - bw2 / 2, pos[1] - bh2 / 2 + 9))

        imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)

        if imgui.button(f"##{self.title}_{self.widget_name}x", (bw2, bh2)):
            self.adapter.on_image_action(self.widget_name, "delete_image", index)
        imgui.pop_style_color(3)
        imgui.set_cursor_pos(pos)
        col = Const.SLIDER_NORMAL
        if imgui.is_item_active():
            col = Const.CLOSE_BUTTON_ACTIVE
        elif imgui.is_item_hovered():
            col = Const.CLOSE_BUTTON_HOVERED
        col = imgui.get_color_u32(col)
        icon = TexturePool.get_tex_id("close")
        dl = imgui.get_window_draw_list()
        dl.add_image(icon, imgui.get_item_rect_min(), imgui.get_item_rect_max(), col=col)
        imgui.set_cursor_pos(pos)
        imgui.end_group()


class StudioClient(BaseAdapter):
    VENDOR = ""

    def __init__(self) -> None:
        self._name = self.VENDOR

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


class NanoBanana(StudioClient):
    VENDOR = "NanoBanana"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.input_image = "CameraRender"
        self.prompt = ""
        self.reference_images: list[str] = []
        self.size_config = "Auto"
        self.resolution = "1K"
        self.api_key = ""
        self.meta = {
            "input_image": {
                "display_name": "Input Image",
                "category": "Input",
                "type": "ENUM",
                "options": [
                    "CameraRender",
                    "CameraDepth",
                ],
            },
            "prompt": {
                "display_name": "Prompt",
                "category": "Input",
                "type": "STRING",
                "multiline": True,
                "default": "",
            },
            "reference_images": {
                "display_name": "Reference Images",
                "category": "Input",
                "type": StudioImagesDescriptor.ptype,
                "limit": 12,
            },
            "size_config": {
                "display_name": "Size Config",
                "category": "Input",
                "type": "ENUM",
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
                "multiline": False,
                "default": "",
            },
        }

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
        self.widgets: dict[str, WidgetDescriptor] = {}
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
            self.widgets[prop_name] = widget
        self.adapter = None


class AIStudioPanelType(Enum):
    NONE = "none"
    GENERATION = "generation"
    SETTINGS = "settings"


class AIStudio(AppHud):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_panel = AIStudioPanelType.GENERATION
        self.clients = {c.VENDOR: c() for c in StudioClient.__subclasses__()}
        self.active_client = NanoBanana.VENDOR

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

        if True:
            self.font_manager.push_h1_font()
            imgui.text("无限之心")
            imgui.same_line()
            imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)
            imgui.text(" BETA ")
            imgui.pop_style_color()
            self.font_manager.pop_font()
            imgui.same_line()
            self.draw_panel_close_button()
            imgui.dummy(dummy_size)

        # 生成面板
        if True:
            imgui.dummy(dummy_size)
            self.font_manager.push_h2_font()
            imgui.text("引擎")
            self.font_manager.pop_font()
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
                wrapper = StudioWrapper()
                wrapper.load(self.clients[self.active_client])

                for widget in wrapper.widgets.values():
                    if widget.category != "Input":
                        continue
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
                label = "  开始AI渲染"
                label_size = imgui.calc_text_size(label)
                if imgui.button("##开始AI渲染", (full_width, gen_btn_height)):
                    print("开始AI渲染")
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

        imgui.pop_style_var(1)

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

        if True:
            self.font_manager.push_h1_font()
            imgui.text("设置")
            imgui.same_line()
            imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)
            imgui.text(" SETTINGS ")
            imgui.pop_style_color()
            self.font_manager.pop_font()
            imgui.same_line()
            self.draw_panel_close_button()
            imgui.dummy(dummy_size)
        imgui.pop_style_var(1)

    def draw_panel_close_button(self):
        # 关闭按钮
        h = imgui.get_text_line_height_with_spacing()
        aw = imgui.get_content_region_avail()[0]
        imgui.dummy((aw - Const.LP_WINDOW_P[0] - h * 0.5, h))
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
        pmax = imgui.get_item_rect_max()
        dl.add_image(icon, pmin, pmax, col=col)


DescriptorFactory.register(StudioImagesDescriptor.ptype, StudioImagesDescriptor)
