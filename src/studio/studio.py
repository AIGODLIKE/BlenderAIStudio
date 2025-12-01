import bpy
from enum import Enum
from .gui.texture import TexturePool
from .gui.app.app import AppHud
from .gui.app.renderer import imgui
from .gui.app.style import Const


def get_tool_panel_width():
    for region in bpy.context.area.regions:
        if region.type != "TOOLS":
            continue
        return region.width
    return 0


class AIStudioPanelType(Enum):
    NONE = "none"
    GENERATION = "generation"
    SETTINGS = "settings"


class AIStudio(AppHud):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_panel = AIStudioPanelType.GENERATION

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
                AIStudioPanelType.GENERATION: "AIStudioPanel/generation",
                AIStudioPanelType.SETTINGS: "AIStudioPanel/settings",
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
            imgui.text("生成")
            imgui.same_line()
            imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)
            imgui.text(" GENERATE ")
            imgui.pop_style_color()
            self.font_manager.pop_font()
            imgui.same_line()
            self.draw_panel_close_button()
            imgui.dummy(dummy_size)
        imgui.pop_style_var(1)

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
