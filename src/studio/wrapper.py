from __future__ import annotations
from traceback import print_exc
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Tuple
from slimgui import imgui
from bpy.app.translations import pgettext
from .gui.app.style import Const
from .gui.app.app import App
from .gui.texture import TexturePool


# 通用子窗口包装
@contextmanager
def with_child(str_id: str, size: Tuple[float, float] = (0.0, 0.0), child_flags: imgui.ChildFlags = imgui.ChildFlags.NONE, window_flags: imgui.WindowFlags = imgui.WindowFlags.NONE):
    imgui.begin_child(str_id, size, child_flags, window_flags)
    try:
        yield
    except Exception:
        print_exc()
    imgui.end_child()


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
        return pgettext(name, self.adapter.get_ctxt())

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
    def category(self):
        return self.widget_def.get("category", "")

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
            imgui.push_item_width(-1)
            imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, Const.RP_FRAME_P[0])
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
            imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, Const.RP_CHILD_IS)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)
            preview = pgettext(self.value, self.adapter.get_ctxt())
            if imgui.begin_combo(f"##{self.widget_name}", preview):
                for item in self.widget_def.get("options", []):
                    is_selected = self.value == item
                    translated_item = pgettext(item, self.adapter.get_ctxt())
                    if imgui.selectable(translated_item, is_selected)[0]:
                        self.value = item
                    if is_selected:
                        imgui.set_item_default_focus()
                imgui.end_combo()
            imgui.pop_style_color()
            imgui.pop_style_var(3)
            imgui.pop_item_width()
        imgui.pop_style_color(1)


class ComboDescriptor(EnumDescriptor):
    ptype: PropertyType = PropertyType.COMBO


class StringDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.STRING

    def display(self, wrapper, app: App):
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        multiline = self.widget_def.get("multiline", False)
        child_width = 240 if multiline else 0
        with with_child("##String", (0, child_width), child_flags=self.flags):
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
            app.font_manager.pop_font()
            imgui.pop_style_var(3)
            imgui.pop_style_color(5)
        imgui.pop_style_color(1)


class ImageDescriptor(WidgetDescriptor):
    ptype: PropertyType = PropertyType.IMAGE

    def display(self, wrapper, app: App):
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child("##Image", (0, 0), child_flags=self.flags):
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
