from __future__ import annotations

import math
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from bpy.app.translations import pgettext_iface as iface
from slimgui import imgui

from .gui.app.app import App
from .gui.app.style import Const
from .gui.texture import TexturePool
from .gui.widgets import with_child


class PropertyType(Enum):
    NONE = "NONE"
    INT = "INT"
    FLOAT = "FLOAT"
    COLOR = "COLOR"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    COMBO = "COMBO"
    STRING = "STRING"
    IMAGE = "IMAGE"


class BaseAdapter:
    def __init__(self, name: str = "") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def get_ctxt(self) -> str:
        return ""

    def get_meta(self, prop: str) -> dict[str, Any]:
        return {}

    def get_value(self, prop: str) -> Any:
        raise NotImplementedError

    def set_value(self, prop: str, value: Any) -> None:
        raise NotImplementedError

    def on_image_action(self, prop: str, action: str) -> None:
        pass


class WidgetDescriptor:
    ptype: PropertyType = PropertyType.NONE

    def __init__(self, widget_name: str, owner: Any):
        self.owner = owner
        self.adapter: BaseAdapter = owner.adapter
        self.widget_name = widget_name
        self.widget_def = self.adapter.get_meta(self.widget_name)
        self.col_bg = (0.2, 0.2, 0.2, 1.0)
        self.col_widget = (0.4, 0.4, 0.4, 1.0)
        self.flags = 0
        self.flags |= imgui.ChildFlags.FRAME_STYLE
        self.flags |= imgui.ChildFlags.AUTO_RESIZE_Y
        self.flags |= imgui.ChildFlags.ALWAYS_AUTO_RESIZE

    @property
    def display_name(self):
        name = self.widget_def.get("display_name", self.widget_name)
        return iface(name, self.adapter.get_ctxt())

    @property
    def value(self):
        return self.adapter.get_value(self.widget_name)

    @value.setter
    def value(self, value):
        self.adapter.set_value(self.widget_name, value)

    @property
    def title(self):
        return self.adapter.name

    @property
    def hide_title(self) -> bool:
        return self.widget_def.get("hide_title", False)

    @property
    def category(self):
        return self.widget_def.get("category", "")

    @property
    def visible_when(self):
        """获取可见性条件配置

        Returns:
            dict | None: 条件字典，如 {"input_source": "BlenderRender"}
        """
        return self.widget_def.get("visible_when", None)

    def is_visible(self) -> bool:
        """判断当前是否应该显示

        支持的条件格式：
        1. 单个值：{"input_source": "BlenderRender"}
        2. 多个值（OR）：{"input_source": ["BlenderRender", "LocalFile"]}
        3. 多个条件（AND）：{"input_source": "BlenderRender", "enable_advanced": True}

        Returns:
            bool: True 表示应该显示，False 表示应该隐藏
        """
        visible_when = self.visible_when

        # 没有条件，默认显示
        if not visible_when:
            return True

        # 检查所有条件是否满足（AND 逻辑）
        for key, expected_value in visible_when.items():
            try:
                current_value = self.adapter.get_value(key)
            except (KeyError, AttributeError):
                # 依赖的参数不存在，默认隐藏
                return False

            # 支持多个值（OR 逻辑）
            if isinstance(expected_value, list):
                if current_value not in expected_value:
                    return False
            else:
                # 单个值（精确匹配）
                if current_value != expected_value:
                    return False

        # 所有条件都满足
        return True

    def display_begin(self, wrapper, app: App):
        imgui.push_id(f"{self.title}_{self.widget_name}")

    def display(self, wrapper, app: App):
        pass

    def display_end(self, wrapper, app: App):
        imgui.pop_id()


class IntDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.INT

    def display(self, wrapper, app: App):
        cfg = {
            "default": 0,
            "min": -65535,
            "max": +65535,
            "step": 1,
        }
        cfg.update(self.widget_def)
        imgui.push_style_var(imgui.StyleVar.GRAB_ROUNDING, Const.GRAB_R)
        imgui.push_style_color(imgui.Col.TEXT, (1, 1, 1, 0.7))
        imgui.push_style_color(imgui.Col.SLIDER_GRAB, Const.SLIDER_NORMAL)
        imgui.push_style_color(imgui.Col.SLIDER_GRAB_ACTIVE, Const.SLIDER_ACTIVE)
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child("##Int", (0, 0), child_flags=self.flags):
            if not self.hide_title:
                imgui.text(self.display_name)
            imgui.push_item_width(-1)
            vmin = max(-(2**30), int(cfg.get("min", -65535)))
            vmax = min(2**30 - 1, int(cfg.get("max", +65535)))
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)
            _, val = imgui.slider_int(f"##{self.widget_name}", int(self.value), vmin, vmax, f"{self.display_name} [%d]")
            self.value = val
            imgui.pop_style_var(1)
            imgui.pop_style_color(1)
            imgui.pop_item_width()
        imgui.pop_style_var(1)
        imgui.pop_style_color(4)


class FloatDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.FLOAT

    def display(self, wrapper, app: App):
        cfg = {
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "default": 0.0,
        }
        cfg.update(self.widget_def)
        imgui.push_style_var(imgui.StyleVar.GRAB_ROUNDING, Const.GRAB_R)
        imgui.push_style_color(imgui.Col.TEXT, (1, 1, 1, 0.7))
        imgui.push_style_color(imgui.Col.SLIDER_GRAB, Const.SLIDER_NORMAL)
        imgui.push_style_color(imgui.Col.SLIDER_GRAB_ACTIVE, Const.SLIDER_ACTIVE)
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child("##Float", (0, 0), child_flags=self.flags):
            if not self.hide_title:
                imgui.text(self.display_name)
            imgui.push_item_width(-1)
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)
            vmin = cfg.get("min", 0.0)
            vmin = max(vmin, -imgui.FLT_MIN * 0.5)
            vmax = cfg.get("max", 1.0)
            vmax = min(vmax, imgui.FLT_MAX * 0.5)
            _, val = imgui.slider_float(f"##{self.widget_name}", self.value, vmin, vmax, f"{self.display_name} [%.2f]")
            self.value = val
            imgui.pop_style_color(1)
            imgui.pop_style_var(1)
            imgui.pop_item_width()
        imgui.pop_style_var(1)
        imgui.pop_style_color(4)


class BoolDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.BOOLEAN

    def display(self, wrapper, app: App):
        _, val = imgui.checkbox(self.display_name, bool(self.value))
        self.value = val


class EnumDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.ENUM

    def display(self, wrapper, app: App):
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child("##Enum", (0, 0), child_flags=self.flags):
            if not self.hide_title:
                imgui.text(self.display_name)
            imgui.push_item_width(-1)
            imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, Const.RP_FRAME_P[0])
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
            imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, (0, Const.RP_FRAME_P[0]))
            imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0)
            imgui.push_style_var(imgui.StyleVar.POPUP_ROUNDING, 12)
            imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, Const.RP_CHILD_IS)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)
            imgui.push_style_color(imgui.Col.BUTTON, (0, 0, 0, 0))
            preview = iface(self.value, self.adapter.get_ctxt())
            if imgui.begin_combo(f"##{self.widget_name}", preview):
                for item in self.widget_def.get("options", []):
                    is_selected = self.value == item
                    translated_item = iface(item, self.adapter.get_ctxt())
                    if is_selected:
                        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
                    if imgui.button(translated_item, (-imgui.FLT_MIN, 0)):
                        self.value = item
                        imgui.close_current_popup()
                    if is_selected:
                        imgui.pop_style_color()
                imgui.end_combo()
            imgui.pop_style_color(2)
            imgui.pop_style_var(6)
            imgui.pop_item_width()
        imgui.pop_style_color(1)


class ComboDescriptor(EnumDescriptor):
    ptype: PropertyType = PropertyType.COMBO


class StringDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.STRING
    # 存储拖拽状态，key 为 widget_name（临时状态，不需要持久化）
    _drag_states: Dict[str, bool] = {}
    _drag_start_y: Dict[str, float] = {}
    _drag_start_height: Dict[str, float] = {}
    # 存储高度值，key 为 height_key（内存存储，不持久化）
    _heights: Dict[str, float] = {}

    def _get_height(self, height_key: str) -> float:
        """获取指定 widget 的高度值，如果不存在则返回默认值 240"""
        return self._heights.get(height_key, 240.0)

    def _set_height(self, height_key: str, height: float) -> None:
        """设置指定 widget 的高度值"""
        self._heights[height_key] = height

    def _pop_height(self, height_key: str) -> None:
        """删除指定 widget 的高度值"""
        self._heights.pop(height_key, None)

    def display(self, wrapper, app: App):
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        multiline = self.widget_def.get("multiline", False)
        resizable = self.widget_def.get("resizable", False)

        # 如果 resizable=True，multiline 应该自动为 True
        if not multiline:
            resizable = False

        # 获取或初始化高度值
        height_key = str(id(self.value))
        child_height = self._get_height(height_key) if multiline else 0

        with with_child("##String", (0, child_height), child_flags=self.flags):
            if not self.hide_title:
                imgui.text(self.display_name)
            imgui.push_style_var(imgui.StyleVar.SCROLLBAR_ROUNDING, Const.CHILD_SB_R)
            imgui.push_style_var(imgui.StyleVar.SCROLLBAR_SIZE, Const.CHILD_SB_S)
            imgui.push_style_var(imgui.StyleVar.SCROLLBAR_PADDING, Const.CHILD_SB_P)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)
            imgui.push_style_color(imgui.Col.SCROLLBAR_BG, Const.CHILD_SB_BG)
            imgui.push_style_color(imgui.Col.SCROLLBAR_GRAB, Const.CHILD_SB_GRAB)
            imgui.push_style_color(imgui.Col.SCROLLBAR_GRAB_ACTIVE, Const.CHILD_SB_GRAB_ACTIVE)
            imgui.push_style_color(imgui.Col.SCROLLBAR_GRAB_HOVERED, Const.CHILD_SB_GRAB_HOVERED)
            app.font_manager.push_content_font()
            if multiline:
                mlt_flags = imgui.InputTextFlags.WORD_WRAP
                changed, val = imgui.input_text_multiline(f"##{self.widget_name}", str(self.value), (-1, -1), mlt_flags)
            else:
                imgui.push_item_width(imgui.get_content_region_avail()[0])
                changed, val = imgui.input_text(f"##{self.widget_name}", str(self.value))
                imgui.pop_item_width()
            if changed:
                self.value = val
                self._pop_height(height_key)
                height_key = str(id(self.value))
                self._set_height(height_key, child_height)
            app.font_manager.pop_font()
            imgui.pop_style_var(3)
            imgui.pop_style_color(5)

            # 如果 resizable=True，绘制并处理控制柄
            if resizable and multiline:
                self._draw_resize_grip(height_key, child_height)

        imgui.pop_style_color(1)

    def _draw_resize_grip(self, height_key: str, current_height: float):
        """绘制并处理调整大小的控制柄（右下角三角形，直角处圆角，视觉指向右下）"""
        # 调整大小控制柄：右下角三角形（带圆角）
        GRIP_TRIANGLE_SIZE = 24.0   # 三角形边长（直角边长度）
        GRIP_CORNER_RADIUS = 16.0    # 右下角圆角半径
        GRIP_MARGIN = 4.0           # 距裁剪区域边缘的最小间距
        min_height = 100.0
        size = GRIP_TRIANGLE_SIZE
        r = min(GRIP_CORNER_RADIUS, size * 0.5)
        margin = GRIP_MARGIN

        draw_list = imgui.get_window_draw_list()
        clip_min = draw_list.get_clip_rect_min()
        clip_max = draw_list.get_clip_rect_max()

        # 三角形锚点：裁剪区域右下角，留 margin
        right = clip_max[0] - margin
        bottom = clip_max[1] - margin

        # 确保三角形完整在裁剪区域内
        right = max(clip_min[0] + size, min(right, clip_max[0]))
        bottom = max(clip_min[1] + size, min(bottom, clip_max[1]))

        # 像素对齐：对抗锯齿边缘更稳定（减少“台阶感/闪烁”）
        right = math.floor(right) + 0.5
        bottom = math.floor(bottom) + 0.5

        grip_min_x = right - size
        grip_min_y = bottom - size

        mouse_pos = imgui.get_mouse_pos()
        mouse_x, mouse_y = mouse_pos[0], mouse_pos[1]

        is_hovered = (grip_min_x <= mouse_x <= right and grip_min_y <= mouse_y <= bottom)

        is_dragging = height_key in self._drag_states and self._drag_states[height_key]

        if imgui.is_mouse_clicked(imgui.MouseButton.LEFT) and is_hovered:
            self._drag_states[height_key] = True
            self._drag_start_y[height_key] = mouse_y
            self._drag_start_height[height_key] = current_height

        if is_dragging:
            if imgui.is_mouse_down(imgui.MouseButton.LEFT):
                delta_y = mouse_y - self._drag_start_y[height_key]
                new_height = self._drag_start_height[height_key] + delta_y
                new_height = max(min_height, new_height)
                self._set_height(height_key, new_height)
            else:
                self._drag_states[height_key] = False

        # 按钮配色：正常 / 悬停 / 激活（拖拽中）
        if is_dragging:
            grip_color = imgui.get_color_u32(Const.BUTTON_ACTIVE)
        elif is_hovered:
            hover = Const.BUTTON_ACTIVE[0] * 0.8, Const.BUTTON_ACTIVE[1] * 0.8, Const.BUTTON_ACTIVE[2] * 0.8, 1
            grip_color = imgui.get_color_u32(hover)
        else:
            normal = Const.BUTTON_ACTIVE[0] * 0.7, Const.BUTTON_ACTIVE[1] * 0.7, Const.BUTTON_ACTIVE[2] * 0.7, 1
            grip_color = imgui.get_color_u32(normal)

        style = imgui.get_style()
        old_aa_fill = style.anti_aliased_fill
        old_aa_lines = style.anti_aliased_lines
        old_curve_tol = style.curve_tessellation_tol
        old_circle_err = style.circle_tessellation_max_error
        try:
            style.anti_aliased_fill = True
            style.anti_aliased_lines = True
            # 更细的曲线细分（仅在本次绘制期间临时调低误差）
            style.curve_tessellation_tol = min(old_curve_tol, 1.0)
            style.circle_tessellation_max_error = min(old_circle_err, 0.20)

            # 对 90° 圆弧显式加密分段，避免小半径时“折线感”
            num_segments = max(12, int(r * 2.0))

            def _build_grip_path() -> None:
                draw_list.path_clear()
                draw_list.path_line_to((right - size, bottom))
                draw_list.path_line_to((right - r, bottom))
                draw_list.path_arc_to((right - r, bottom - r), r, math.pi * 0.5, 0.0, num_segments)
                draw_list.path_line_to((right, bottom - size))

            _build_grip_path()
            draw_list.path_fill_convex(grip_color)
            _build_grip_path()
            draw_list.path_stroke(grip_color, thickness=1.0)
        finally:
            style.anti_aliased_fill = old_aa_fill
            style.anti_aliased_lines = old_aa_lines
            style.curve_tessellation_tol = old_curve_tol
            style.circle_tessellation_max_error = old_circle_err


class ImageDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.IMAGE

    def display(self, wrapper, app: App):
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child("##Image", (0, 0), child_flags=self.flags):
            if not self.hide_title:
                imgui.text(f"{getattr(self.owner, 'display_name', '')}: {self.display_name}")
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)
            with with_child("##Inner", (0, 0), child_flags=self.flags):
                imgui.push_style_var_x(imgui.StyleVar.CELL_PADDING, 0)
                imgui.push_id(f"##Prop_{self.title}_{self.widget_name}_1")
                self.display_image_with_close()
                imgui.pop_id()
                imgui.pop_style_var(1)
            imgui.pop_style_color()
        imgui.pop_style_color(1)

    def display_image_with_close(self):
        bw, bh = 102, 102
        img_path = self.value
        has_image = True
        if not img_path or not Path(str(img_path)).exists():
            img_path = "image_new"
            has_image = False
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
            imgui.open_popup(f"##{self.title}_{self.widget_name}_edit")
        if has_image:
            imgui.same_line()
            pos = imgui.get_cursor_pos()
            bw2, bh2 = 30, 30
            isx = imgui.get_style().item_spacing[0]
            imgui.set_cursor_pos((pos[0] - isx - bw2 / 2, pos[1] - bh2 / 2 + 9))

            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)

            if imgui.button(f"##{self.title}_{self.widget_name}x", (bw2, bh2)):
                self.adapter.on_image_action(self.widget_name, "delete_image")
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
        self.display_image_editor()

    def display_image_editor(self):
        s = 54 * Const.SCALE
        img_s = 30 * Const.SCALE
        p = 6 * Const.SCALE
        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, (p, p))
        imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, (0, 0))
        imgui.push_style_var(imgui.StyleVar.CELL_PADDING, (p / 2, 0))
        imgui.push_style_var(imgui.StyleVar.POPUP_ROUNDING, s / 2 + p)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, s / 2)
        imgui.push_style_color(imgui.Col.POPUP_BG, (0, 186 / 255, 173 / 255, 1))
        imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON)
        if imgui.begin_popup(f"##{self.title}_{self.widget_name}_edit"):
            btn_types = [
                "image_from_mat",
                "image_from_file",
                "image_from_canvas",
                "image_from_viewport",
                "image_from_render",
            ]
            imgui.begin_table("EditTable", len(btn_types))
            for btn_type in btn_types:
                imgui.table_next_column()
                if imgui.button(f"##{btn_type}", (s, s)):
                    self.adapter.on_image_action(self.widget_name, btn_type)
                    imgui.close_current_popup()
                size = imgui.get_item_rect_size()
                ipos = imgui.get_item_rect_min()
                pos = ipos[0] + (size[0] - img_s) / 2, ipos[1] + (size[1] - img_s) / 2
                color = imgui.get_color_u32((1, 1, 1, 1))
                icon = TexturePool.get_tex_id(btn_type)
                dl = imgui.get_window_draw_list()
                dl.add_image(icon, pos, (pos[0] + img_s, pos[1] + img_s), col=color)
            imgui.end_table()
            imgui.end_popup()
        imgui.pop_style_var(5)
        imgui.pop_style_color(4)


class ColorDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.COLOR

    def display(self, wrapper, app: App):
        # 实现颜色选择器
        color = self.value
        if not hasattr(color, "__iter__"):
            return
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child(f"##{self.title}_{self.widget_name}", (0, 0), child_flags=self.flags):
            if not self.hide_title:
                imgui.text(self.display_name)
            imgui.push_item_width(120)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)
            imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, (0, 0))
            with with_child("##Color", (0, 0), child_flags=self.flags):
                imgui.pop_style_var()
                flags = imgui.ColorEditFlags.ALPHA_BAR
                flags |= imgui.ColorEditFlags.PICKER_HUE_WHEEL
                flags |= imgui.ColorEditFlags.NO_INPUTS
                label = f"  {self.display_name}"
                if len(color) == 3:
                    changed, new_col = imgui.color_edit3(label, color, flags)
                else:
                    changed, new_col = imgui.color_edit4(label, color, flags)
                if changed:
                    self.value = new_col
            imgui.pop_style_color()
            imgui.pop_item_width()
        imgui.pop_style_color(1)


class DescriptorFactory:
    _registry: Dict[str, type] = {}

    @classmethod
    def register(cls, wtype: str, descriptor_class: type):
        cls._registry[wtype] = descriptor_class

    @classmethod
    def create(cls, wname: str, wtype: str, owner: Any) -> WidgetDescriptor:
        desctype = cls._registry.get(wtype, WidgetDescriptor)
        descriptor = desctype(wname, owner)
        return descriptor


# 注册通用控件类型
DescriptorFactory.register(PropertyType.INT.name, IntDescriptor)
DescriptorFactory.register(PropertyType.FLOAT.name, FloatDescriptor)
DescriptorFactory.register(PropertyType.COLOR.name, ColorDescriptor)
DescriptorFactory.register(PropertyType.BOOLEAN.name, BoolDescriptor)
DescriptorFactory.register(PropertyType.ENUM.name, EnumDescriptor)
DescriptorFactory.register(PropertyType.COMBO.name, ComboDescriptor)
DescriptorFactory.register(PropertyType.STRING.name, StringDescriptor)
DescriptorFactory.register(PropertyType.IMAGE.name, ImageDescriptor)
