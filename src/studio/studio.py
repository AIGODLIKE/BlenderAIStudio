import bpy
import json
import math
import platform
import re
import subprocess
import time
import webbrowser
from bpy.app.translations import pgettext, pgettext_iface as iface
from datetime import datetime
from enum import Enum
from pathlib import Path
from shutil import copyfile
from traceback import print_exc

from .account import Account
from .clients import StudioHistoryItem, StudioHistory
from .clients.universal_client import UniversalClient
from .config.model_registry import ModelRegistry
from .gui.app.animation import AnimationSystem, Easing, Tween, Sequence
from .gui.app.app import AppHud
from .gui.app.renderer import imgui
from .gui.app.style import Const
from .gui.texture import TexturePool
from .gui.widgets import CustomWidgets, with_child
from .tasks import TaskState
from .wrapper import BaseAdapter, WidgetDescriptor, DescriptorFactory
from ..i18n import STUDIO_TCTX
from ..preferences import AuthMode
from ..logger import logger
from ..timer import Timer
from ..utils import get_addon_version, get_pref


def _T(msg, ctxt=STUDIO_TCTX):
    t = iface(msg, ctxt)
    if t == msg:
        return iface(msg)
    return t


def get_tool_panel_width():
    for region in bpy.context.area.regions:
        if region.type != "TOOLS":
            continue
        return region.width
    return 0


def get_header_panel_height():
    for region in bpy.context.area.regions:
        if region.type != "HEADER":
            continue
        return region.height


def edit_image_with_meta_and_context(file_path, meta, context):
    try:
        with bpy.context.temp_override(**context):
            bpy.ops.bas.open_image_in_new_window("INVOKE_DEFAULT", image_path=file_path, data=meta)
    except Exception as e:
        logger.error(f"编辑图片失败: {e}")
        print_exc()


def open_dir(path):
    """
    bpy.ops.wm.url_open(url=path)
    """
    open_util = 'explorer "%s"'
    if platform.system() != "Windows":
        open_util = 'open /"%s"'

    try:
        subprocess.run(open_util % path, shell=True, check=True)
    except Exception as e:
        print(e.args)
        print_exc()


class AppHelperDraw:
    def draw_tips_with_title(self: AppHud, tips: list[str], title: str):
        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.WINDOW_R)
        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, Const.WINDOW_P)
        imgui.begin_tooltip()

        self.font_manager.push_h1_font(24)
        imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)
        imgui.text(title)
        imgui.pop_style_color()
        self.font_manager.pop_font()

        self.font_manager.push_h5_font(24)
        for tip in tips:
            imgui.text_wrapped(tip)
        self.font_manager.pop_font()

        imgui.end_tooltip()
        imgui.pop_style_var(2)


class StudioImagesDescriptor(WidgetDescriptor):
    ptype = "IMAGE_LIST"

    def display(self, wrapper, app):
        imgui.push_style_color(imgui.Col.FRAME_BG, self.col_bg)
        with with_child("##Image", (0, 0), child_flags=self.flags):
            imgui.text(self.display_name)
            imgui.push_style_color(imgui.Col.FRAME_BG, self.col_widget)

            with with_child("##Inner", (0, 0), child_flags=self.flags):
                imgui.push_style_var(imgui.StyleVar.CELL_PADDING, imgui.get_style().item_spacing)
                imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, (0, 0))
                imgui.push_style_color(imgui.Col.TABLE_BORDER_STRONG, Const.TRANSPARENT)
                if imgui.begin_table("##Table", 3, imgui.TableFlags.BORDERS):
                    for i in range(3):
                        imgui.table_setup_column(f"##Column{i}", imgui.TableColumnFlags.WIDTH_STRETCH, 0, i)
                    for i, img in enumerate(self.value):
                        imgui.table_next_column()
                        imgui.push_id(f"##Image{i}")
                        self.display_image_with_close(app, img, i)
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

    def display_image_with_close(self, app, img_path: str = "", index=-1):
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
            imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.CHILD_R)
            imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, (12, 12))
            imgui.begin_tooltip()
            tex = TexturePool.get_tex(icon)
            file_name = Path(img_path).stem
            imgui.text(f"{file_name} [{tex.width}x{tex.height}]")
            imgui.dummy((0, imgui.get_style().frame_padding[1]))
            canvas_tex_width = app.screen_scale * tex.width
            canvas_tex_height = app.screen_scale * tex.height
            canvas_width = app.screen_width * 0.7
            canvas_height = app.screen_height * 0.7
            if canvas_tex_width > canvas_width:
                canvas_tex_scale = canvas_width / canvas_tex_width
                canvas_tex_height *= canvas_tex_scale
                canvas_tex_width *= canvas_tex_scale
            if canvas_tex_height > canvas_height:
                canvas_tex_scale = canvas_height / canvas_tex_height
                canvas_tex_height *= canvas_tex_scale
                canvas_tex_width *= canvas_tex_scale
            aw = imgui.get_content_region_avail()[0]
            if canvas_tex_width < aw:
                canvas_tex_scale = aw / canvas_tex_width
                canvas_tex_height *= canvas_tex_scale
                canvas_tex_width *= canvas_tex_scale
            imgui.invisible_button("FakeButton", (canvas_tex_width, canvas_tex_height))
            pmin = imgui.get_item_rect_min()
            pmax = imgui.get_item_rect_max()
            dl = imgui.get_window_draw_list()
            dl.add_image_rounded(icon, pmin, pmax, (0, 0), (1, 1), 0xFFFFFFFF, Const.CHILD_R * 0.8)
            imgui.end_tooltip()
            imgui.pop_style_var(2)
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


class StudioHistoryViewer:
    def __init__(self, app: "AIStudio", history: StudioHistory) -> None:
        self.history = history
        self.app = app

    def draw_all(self):
        for item in self.history.items:
            self._draw(item)

    def draw_first(self):
        if not self.history.items:
            return
        item = self.history.items[0]
        self._draw(item)

    def _draw(self, item: StudioHistoryItem):
        item.update_elapsed_time()
        col_bg = Const.WINDOW_BG
        col_widget = Const.FRAME_BG
        flags = 0
        flags |= imgui.ChildFlags.FRAME_STYLE
        flags |= imgui.ChildFlags.AUTO_RESIZE_Y
        flags |= imgui.ChildFlags.ALWAYS_AUTO_RESIZE
        imgui.push_style_color(imgui.Col.FRAME_BG, col_bg)
        imgui.push_style_var_y(imgui.StyleVar.CELL_PADDING, 0)
        imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, Const.CHILD_P[1])
        with with_child(f"##Item_{item.index}", (0, 0), child_flags=flags):
            imgui.push_style_color(imgui.Col.FRAME_BG, col_widget)

            # 标题栏
            style = imgui.get_style()
            imgui.push_style_var_y(imgui.StyleVar.FRAME_PADDING, imgui.get_style().frame_padding[1] * 0.5)
            if imgui.begin_table("##Header", 5):
                imgui.table_setup_column("##Ele1", imgui.TableColumnFlags.WIDTH_FIXED, 0, 0)
                imgui.table_setup_column("##Ele2", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 1)
                imgui.table_setup_column("##Ele3", imgui.TableColumnFlags.WIDTH_FIXED, 0, 2)
                imgui.table_setup_column("##Ele4", imgui.TableColumnFlags.WIDTH_FIXED, 0, 3)
                imgui.table_setup_column("##Ele5", imgui.TableColumnFlags.WIDTH_FIXED, 0, 4)

                self.app.font_manager.push_h1_font(24)
                imgui.table_next_column()
                imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)
                imgui.align_text_to_frame_padding()
                imgui.text(f"#{item.index:03d}")
                imgui.pop_style_color()
                self.app.font_manager.pop_font()

                imgui.table_next_column()
                imgui.dummy((0, 0))

                bh = imgui.get_frame_height()
                bw = bh * 2
                isize = bh - 12
                fr = imgui.get_style().frame_rounding
                imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, fr * 2)

                # 复制按钮
                imgui.table_next_column()
                prompt = item.get_prompt()
                if CustomWidgets.icon_label_button("prompt_copy", "", "CENTER", (bw, bh), isize=isize):
                    if prompt:
                        bpy.context.window_manager.clipboard = prompt
                        self.app.push_info_message(_T("Prompt Copied!"))
                    else:
                        self.app.push_info_message(_T("No Prompt Found!"))
                if imgui.is_item_hovered():
                    title = _T("Copy Prompt")
                    tip = _T("Click to copy the prompt to clipboard.")
                    imgui.set_next_window_size((550, 0))
                    AppHelperDraw.draw_tips_with_title(self.app, [tip], title)
                # 详情按钮
                imgui.table_next_column()
                old_show_detail = item.show_detail
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_SELECTED)
                if old_show_detail:
                    imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON_SELECTED)
                if CustomWidgets.icon_label_button("image_detail", "", "CENTER", (bw, bh), isize=isize):
                    item.show_detail = not item.show_detail
                if imgui.is_item_hovered():
                    title = _T("Details")
                    tip = _T("View generated image details like prompt, generation time, etc.")
                    imgui.set_next_window_size((550, 0))
                    AppHelperDraw.draw_tips_with_title(self.app, [tip], title)
                if old_show_detail:
                    imgui.pop_style_color(1)
                imgui.pop_style_color(1)

                # 删除按钮
                imgui.table_next_column()
                if CustomWidgets.icon_label_button("delete", "", "CENTER", (bw, bh), isize=isize):
                    self.remove_item(item)
                if imgui.is_item_hovered():
                    title = _T("Delete History")
                    tip = _T("Click to delete the history in the queue, but leave the generated image.")
                    imgui.set_next_window_size((550, 0))
                    AppHelperDraw.draw_tips_with_title(self.app, [tip], title)
                imgui.pop_style_var(1)

                imgui.end_table()

            imgui.pop_style_var(1)
            imgui.dummy((0, 0))

            # 图片
            if imgui.begin_table("##Content", 2):
                h1 = imgui.get_text_line_height() * 4
                w1 = h1 * 207 / 126
                imgui.table_setup_column("##Ele1", imgui.TableColumnFlags.WIDTH_FIXED, w1, 0)
                imgui.table_setup_column("##Ele2", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 1)

                imgui.table_next_column()
                imgui.push_style_color(imgui.Col.FRAME_BG, col_widget)
                imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
                with with_child("##Image", (w1, h1), child_flags=flags):
                    imgui.push_style_color(imgui.Col.FRAME_BG, col_bg)
                    imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
                    imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
                    imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
                    bw, bh = imgui.get_content_region_avail()
                    icon = TexturePool.get_tex_id(item.get_output_file_image())
                    tex = TexturePool.get_tex(icon)
                    tex_aspect_ratio = tex.width / tex.height
                    btn_aspect_ratio = bw / bh
                    uvmin = (0, 0)
                    uvmax = (1, 1)
                    if tex_aspect_ratio > btn_aspect_ratio:
                        clip_uv_x = abs(tex.width - (tex.height / bh) * bw) / tex.width * 0.5
                        uvmin = (clip_uv_x, 0)
                        uvmax = (1 - clip_uv_x, 1)
                    else:
                        clip_uv_y = abs(tex.height - (tex.width / bw) * bh) / tex.height * 0.5
                        uvmin = (0, clip_uv_y)
                        uvmax = (1, 1 - clip_uv_y)
                    if imgui.button("##FakeButton", (bw, bh)):
                        self.copy_image(item.get_output_file_image())
                        self.app.push_info_message(_T("Image Copied!"))
                    pmin = imgui.get_item_rect_min()
                    pmax = imgui.get_item_rect_max()
                    dl = imgui.get_window_draw_list()
                    dl.add_image_rounded(icon, pmin, pmax, uvmin, uvmax, 0xFFFFFFFF, 12)
                    if imgui.is_item_hovered():
                        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.CHILD_R)
                        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, (12, 12))
                        imgui.begin_tooltip()
                        tex = TexturePool.get_tex(icon)
                        file_name = Path(item.get_output_file_image()).stem
                        imgui.text(f"{file_name} [{tex.width}x{tex.height}]")
                        imgui.dummy((0, 0))
                        canvas_tex_width = self.app.screen_scale * tex.width
                        canvas_tex_height = self.app.screen_scale * tex.height
                        canvas_width = self.app.screen_width * 0.7
                        canvas_height = self.app.screen_height * 0.7
                        if canvas_tex_width > canvas_width:
                            canvas_tex_scale = canvas_width / canvas_tex_width
                            canvas_tex_height *= canvas_tex_scale
                            canvas_tex_width *= canvas_tex_scale
                        if canvas_tex_height > canvas_height:
                            canvas_tex_scale = canvas_height / canvas_tex_height
                            canvas_tex_height *= canvas_tex_scale
                            canvas_tex_width *= canvas_tex_scale
                        aw = imgui.get_content_region_avail()[0]
                        if canvas_tex_width < aw:
                            canvas_tex_scale = aw / canvas_tex_width
                            canvas_tex_height *= canvas_tex_scale
                            canvas_tex_width *= canvas_tex_scale
                        imgui.invisible_button("FakeButton", (canvas_tex_width, canvas_tex_height))
                        pmin = imgui.get_item_rect_min()
                        pmax = imgui.get_item_rect_max()
                        dl = imgui.get_window_draw_list()
                        dl.add_image_rounded(icon, pmin, pmax, (0, 0), (1, 1), 0xFFFFFFFF, Const.CHILD_R * 0.8)
                        imgui.end_tooltip()
                        imgui.pop_style_var(2)
                    imgui.pop_style_color(4)
                imgui.pop_style_var(1)
                imgui.pop_style_color(1)

                imgui.table_next_column()
                imgui.push_style_color(imgui.Col.FRAME_BG, col_widget)
                imgui.push_style_var(imgui.StyleVar.CELL_PADDING, Const.CELL_P)
                imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
                imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, (Const.CELL_P[0] * 2, Const.CELL_P[1]))
                with with_child("##Buttons", (0, h1), child_flags=flags):
                    imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R / 2)
                    imgui.push_style_color(imgui.Col.BUTTON, col_bg)
                    if imgui.begin_table("##Buttons", 1):
                        imgui.table_setup_column("##Ele1", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 0)
                        # 编辑
                        if True:
                            style = imgui.get_style()
                            bh = h1 / 2 - style.cell_padding[1] * 2 - style.frame_padding[1]
                            imgui.table_next_column()
                            if CustomWidgets.icon_label_button("image_edit", _T("Edit"), "LEFT", (0, bh)):
                                image = item.get_output_file_image()
                                meta = item.stringify()
                                context = bpy.context.copy()
                                Timer.put((edit_image_with_meta_and_context, image, meta, context))
                            if imgui.is_item_hovered():
                                title = _T("Edit Image")
                                tip = _T("Open image editor and edit current image.")
                                imgui.set_next_window_size((720, 0))
                                AppHelperDraw.draw_tips_with_title(self.app, [tip], title)

                        # 导出
                        if True:
                            style = imgui.get_style()
                            bh = h1 / 2 - style.cell_padding[1] * 2 - style.frame_padding[1]
                            imgui.table_next_column()
                            if CustomWidgets.icon_label_button("image_export", _T("Save"), "LEFT", (0, bh)):
                                self.export_image(item.get_output_file_image())
                            if imgui.is_item_hovered():
                                title = _T("Export Image")
                                tip = _T("Click to export the image to disk.")
                                imgui.set_next_window_size((720, 0))
                                AppHelperDraw.draw_tips_with_title(self.app, [tip], title)
                        imgui.end_table()
                    imgui.pop_style_var(1)
                    imgui.pop_style_color(1)
                imgui.pop_style_var(3)
                imgui.pop_style_color(1)

                imgui.end_table()
            if item.show_detail:
                imgui.text(_T("Prompt"))
                prompt = item.get_prompt() or "No prompt found"
                h = imgui.get_text_line_height()

                # 提示词
                mlt_flags = imgui.InputTextFlags.WORD_WRAP
                text_box_height = h * 5 + imgui.get_style().frame_padding[1] * 2
                _, _ = imgui.input_text_multiline("##prompt", prompt, (-1, text_box_height), mlt_flags)
                icon = TexturePool.get_tex_id(item.get_output_file_image())
                tex = TexturePool.get_tex(icon)
                tex_width = tex.width
                tex_height = tex.height

                # 图片信息
                stem = Path(item.get_output_file_image()).stem
                icon = TexturePool.get_tex_id("roster")
                imgui.dummy((0, 0))
                imgui.image(icon, (h, h))
                imgui.same_line()
                imgui.text(stem)

                icon = TexturePool.get_tex_id("image_info_resolution")
                imgui.dummy((0, 0))
                imgui.image(icon, (h, h))
                imgui.same_line()
                imgui.text(f"{tex_width}*{tex_height} px (72dpi)")

                icon = TexturePool.get_tex_id("image_info_vendor")
                imgui.dummy((0, 0))
                imgui.image(icon, (h, h))
                imgui.same_line()
                imgui.text(_T("Generated by %s") % item.model)

                icon = TexturePool.get_tex_id("image_info_timestamp")
                imgui.dummy((0, 0))
                imgui.image(icon, (h, h))
                imgui.same_line()
                imgui.text(datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S"))

            imgui.pop_style_color(1)
        imgui.pop_style_var(2)
        imgui.pop_style_color(1)

    def remove_item(self, item: StudioHistoryItem):
        self.history.remove(item)

    def copy_image(self, image_path):
        def copy_image_callback(image_path: str):
            image = bpy.data.images.get(image_path)
            should_remove = False

            if not image or image.filepath != image_path:
                image = bpy.data.images.load(image_path)
                should_remove = True

            with bpy.context.temp_override(edit_image=image):
                bpy.ops.image.clipboard_copy()

            if should_remove:
                bpy.data.images.remove(image)

        Timer.put((copy_image_callback, image_path))

    def export_image(self, image_path):
        in_file = image_path

        def export_image_callback(file_path: str):
            copyfile(in_file, file_path)
            print("导出图片到：", file_path)

        from .ops import FileCallbackRegistry

        callback_id = FileCallbackRegistry.register_callback(export_image_callback)
        bpy.ops.bas.file_exporter("INVOKE_DEFAULT", callback_id=callback_id)


class StudioWrapper:
    """
    材质节点描述器：封装材质节点及其可控属性
    """

    def __init__(self):
        self.studio_client: UniversalClient = None
        self.display_name: str = ""
        self.widgets: dict[str, list[WidgetDescriptor]] = {}
        self.adapter: BaseAdapter = None

    @property
    def title(self):
        return self.studio_client.model_name if self.studio_client else ""

    def load(self, client: UniversalClient):
        self.studio_client = client
        self.adapter = client
        self.display_name = client.model_name
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
    HISTORY = "history"


class StorePanel:
    PRODUCTS = []

    def __init__(self, app: "AIStudio"):
        self.app = app
        self.redeem_panel = RedeemPanel(app)
        self.init()

    def init(self):
        if self.PRODUCTS:
            return
        products_path = Path(__file__).parent / "config/products.json"
        try:
            json_data = json.loads(products_path.read_text(encoding="utf-8"))
            self.PRODUCTS.clear()
            self.PRODUCTS.extend(json_data)
        except Exception as e:
            print("加载产品信息失败：", e)

    @property
    def should_draw_redeem(self):
        return self.redeem_panel.should_draw_redeem

    @should_draw_redeem.setter
    def should_draw_redeem(self, value):
        self.redeem_panel.should_draw_redeem = value

    def draw(self):
        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, Const.LP_WINDOW_P)
        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.WINDOW_R)

        imgui.push_style_color(imgui.Col.WINDOW_BG, Const.RP_L_BOX_BG)
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.MODAL_WINDOW_DIM_BG, Const.MODAL_WINDOW_DIM_BG)

        self.redeem_panel.draw()

        imgui.pop_style_var(2)
        imgui.pop_style_color(5)

    def draw_login_panel(self):
        if self.app.state.is_logged_in():
            return
        flags = 0
        flags |= imgui.ChildFlags.FRAME_STYLE
        flags |= imgui.ChildFlags.AUTO_RESIZE_Y
        flags |= imgui.ChildFlags.ALWAYS_AUTO_RESIZE

        with with_child("##Login", (0, 0), child_flags=flags):
            self.app.font_manager.push_h3_font()
            bh = imgui.get_text_line_height_with_spacing() * 2
            if self.app.state.is_waiting_for_login():
                label = _T("Waiting for login") + "." * round(imgui.get_time() // 0.5 % 4)
                imgui.button(label, (-imgui.FLOAT_MIN, bh))
            else:
                if imgui.button(_T("Login/Register"), (-imgui.FLOAT_MIN, bh)):
                    self.app.state.login()
            self.app.font_manager.pop_font()
        # --- 底部: 警告信息 (单行全宽) ---
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.WINDOW_BG)
        isize = 24
        label = _T("Support Tool Dev")
        CustomWidgets.icon_label_button("account_warning", label, "CENTER", (0, 54), isize)
        imgui.pop_style_color(3)

    def draw_login(self):
        if not self.app.state.is_logged_in():
            return

    def draw_account(self):
        if not self.app.state.is_logged_in():
            return

        with with_child("Outer", (0, 0), imgui.ChildFlags.FRAME_STYLE | imgui.ChildFlags.AUTO_RESIZE_Y):
            bh = 45
            fpx = imgui.get_style().frame_padding[0]
            isize = 24
            aw = imgui.get_content_region_avail()[0]
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R * 0.5)
            imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, imgui.get_style().frame_padding)

            # --- 表格 1: 邮箱 + 登出
            bw = aw - bh - imgui.get_style().item_spacing[0]
            CustomWidgets.icon_label_button(
                "account_email",
                self.app.state.nickname,
                "BETWEEN",
                (bw, bh),
                isize,
                fpx * 2,
            )
            imgui.same_line()
            if CustomWidgets.icon_label_button("account_logout", "", "CENTER", (bh, bh), isize):
                self.app.state.logout()

            # --- 表格 2: Token + 刷新
            bw = aw - bh - imgui.get_style().item_spacing[0]
            CustomWidgets.icon_label_button(
                "account_token",
                str(self.app.state.credits),
                "BETWEEN",
                (bw, bh),
                isize,
                fpx * 2,
            )
            imgui.same_line()
            if CustomWidgets.icon_label_button("account_refresh", "", "CENTER", (bh, bh), isize):
                self.app.state.fetch_credits()

            # --- 表格 3: 功能按钮 (50% + 50%) ---
            bw = (aw - imgui.get_style().item_spacing[0]) * 0.5
            label = _T("Buy", STUDIO_TCTX)
            if CustomWidgets.icon_label_button("account_buy", label, "CENTER", (bw, bh), isize):
                print("获取冰糕")
                imgui.open_popup("##Buy")
            self.draw_buy()
            imgui.same_line()
            label = _T("Redeem")
            if CustomWidgets.icon_label_button("account_certificate", label, "CENTER", (bw, bh), isize):
                self.should_draw_redeem = True
            self.draw()
            imgui.pop_style_var(2)

        # --- 底部: 警告信息 (单行全宽) ---
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.WINDOW_BG)
        # 服务器状态
        if True:
            label = _T("Server Status") + ":"
            if self.app.state.services_connected:
                connect_state = _T("Connected")
                icon = "cloud_blue"
                text_col = Const.BUTTON_SELECTED
            else:
                connect_state = _T("Disconnected")
                icon = "cloud_gray"
                text_col = Const.DISABLE

            # 1. 基础尺寸与位置计算
            width = imgui.get_content_region_avail()[0]
            height = 54
            screen_pos = imgui.get_cursor_screen_pos()

            imgui.button(f"##btn_{icon}_{label}", (width, height))

            dl = imgui.get_window_draw_list()
            tex_id = TexturePool.get_tex_id(icon)

            icon_w = imgui.get_text_line_height()
            gap = icon_w * 0.25 if label else 0  # 图标与文字间距

            text_size1 = imgui.calc_text_size(label)
            text_size2 = imgui.calc_text_size(connect_state)

            # 整体居中: ..[Icon + Text]..
            content_w = icon_w + gap + text_size1[0] + gap + text_size2[0]
            start_x = screen_pos[0] + (width - content_w) / 2
            icon_x = start_x
            text_x = start_x + icon_w + gap

            height = imgui.get_item_rect_size()[1]
            icon_y = screen_pos[1] + (height - icon_w) / 2
            dl.add_image(tex_id, (icon_x, icon_y), (icon_x + icon_w, icon_y + icon_w))

            # 文字1
            if True:
                text_y = screen_pos[1] + (height - text_size1[1]) / 2
                tex_col = imgui.get_style_color_vec4(imgui.Col.TEXT)
                col = imgui.get_color_u32(tex_col)
                dl.add_text((text_x, text_y), col, label)

            text_x += text_size1[0] + gap

            # 文字2
            if True:
                text_y = screen_pos[1] + (height - text_size2[1]) / 2
                col = imgui.get_color_u32(text_col)
                dl.add_text((text_x, text_y), col, connect_state)
        # 警告信息
        if True:
            label = _T("Proceeds → open source")
            CustomWidgets.icon_label_button("account_warning", label, "CENTER", (0, 54), isize)
            imgui.pop_style_color(3)

    def draw_buy(self):
        window_size = 1680, 713
        hh = get_header_panel_height() / self.app.screen_scale
        sw = self.app.screen_width
        sh = self.app.screen_height
        window_pos = (sw - window_size[0]) / 2, (sh - window_size[1] + hh) / 2
        imgui.set_next_window_pos(window_pos, imgui.Cond.ONCE)
        imgui.set_next_window_size(window_size, imgui.Cond.ALWAYS)
        flags = 0
        flags |= imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SCROLL_WITH_MOUSE
        flags |= imgui.WindowFlags.NO_SCROLLBAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS
        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, Const.LP_WINDOW_P)
        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.WINDOW_R)

        imgui.push_style_color(imgui.Col.WINDOW_BG, Const.RP_L_BOX_BG)
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.MODAL_WINDOW_DIM_BG, Const.MODAL_WINDOW_DIM_BG)

        style = imgui.get_style()
        if imgui.begin_popup_modal("##Buy", False, flags)[0]:
            imgui.push_style_var(imgui.StyleVar.CELL_PADDING, (style.window_padding[0] * 0.5, 0))
            # 标题
            if True:
                self.app.font_manager.push_h1_font()

                imgui.push_style_var_y(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                imgui.button(_T("AGL STORE"))
                imgui.same_line()

                icon = TexturePool.get_tex_id("settings_header")
                tex = TexturePool.get_tex(icon)
                scale = imgui.get_text_line_height() / tex.height
                imgui.image_button("Buy", icon, (tex.width * scale, tex.height * scale), tint_col=Const.BUTTON_SELECTED)
                imgui.pop_style_color(3)
                imgui.same_line()

                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                bh = imgui.get_text_line_height()
                label = _T("The more, the cheaper.")
                bw = imgui.calc_text_size(label)[0] + bh * 1.5
                CustomWidgets.icon_label_button("account_warning", label, "CENTER", (bw, bh))
                imgui.pop_style_color(3)
                imgui.same_line()

                h = imgui.get_frame_height()
                aw = imgui.get_content_region_avail()[0]
                imgui.dummy((aw - style.item_spacing[0] - h, 0))
                imgui.same_line()
                imgui.push_style_color(imgui.Col.BUTTON, Const.CLOSE_BUTTON_NORMAL)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.CLOSE_BUTTON_ACTIVE)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.CLOSE_BUTTON_HOVERED)
                if CustomWidgets.colored_image_button("##CloseBtn", "close", (h, h)):
                    imgui.close_current_popup()
                imgui.pop_style_var(1)
                imgui.pop_style_color(3)
                self.app.font_manager.pop_font()

            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            # 购买规格
            products = self.PRODUCTS
            if imgui.begin_table("##BuyTable", len(products), imgui.TableFlags.SIZING_STRETCH_SAME):
                for config in products:
                    imgui.table_next_column()
                    if self.draw_product_card(config):
                        imgui.close_current_popup()
                        self.buy_product(config)

                imgui.end_table()

            imgui.pop_style_var(1)
            imgui.end_popup()

        imgui.pop_style_var(2)
        imgui.pop_style_color(5)

    def draw_product_card(self, config: dict[str, str]):
        product = config["id"]
        icon = config["icon"]
        name = config["name"]
        cert = config["certificate"]
        color = config["color"]
        price = config["price"]

        style = imgui.get_style()
        imgui.push_id(f"Product_{product}")
        imgui.begin_group()
        dl = imgui.get_window_draw_list()

        screen_pos = imgui.get_cursor_screen_pos()
        aw, ah = imgui.get_content_region_avail()
        clicked = imgui.invisible_button("##ProductCard", (aw, ah))
        hovered = imgui.is_item_hovered()

        tex = TexturePool.get_tex_id(f"{icon}_gray")
        if hovered:
            tex = TexturePool.get_tex_id(icon)

        pmin = imgui.get_item_rect_min()
        pmax = imgui.get_item_rect_max()
        dl.add_image_rounded(tex, pmin, pmax, (0, 0), (1, 1), 0xFFFFFFFF, style.frame_rounding * 2)

        imgui.set_cursor_pos((screen_pos[0] + style.frame_padding[0], screen_pos[1] + style.frame_padding[1]))
        col = imgui.get_color_u32((1, 1, 1, 1))
        font_manager = self.app.font_manager
        # 信息1
        if True:
            label = _T(name)
            font_manager.push_h1_font(24)
            label_width = imgui.calc_text_size(label)[0]
            dl.add_text((screen_pos[0] + (aw - label_width) * 0.5, screen_pos[1] + 400), col, label)
            font_manager.pop_font()
        # 信息2
        if True:
            label = _T("[ Ice Pops x %s ]") % cert
            font_manager.push_h1_font(36)
            label_width = imgui.calc_text_size(label)[0]
            dl.add_text((screen_pos[0] + (aw - label_width) * 0.5, screen_pos[1] + 447), col, label)
            font_manager.pop_font()

        imgui.separator()

        # 底部横条
        if True:
            flags = imgui.DrawFlags.ROUND_CORNERS_BOTTOM_LEFT | imgui.DrawFlags.ROUND_CORNERS_BOTTOM_RIGHT
            col = color if hovered else (56 / 255, 56 / 255, 56 / 255, 1)
            col = imgui.get_color_u32(col)
            dl.add_rect_filled((pmin[0], pmax[1] - 70), pmax, col, style.frame_rounding * 2, flags)
        # 底部文字
        if True:
            label = f"￥{price}"
            font_manager.push_h1_font(30)
            lw, lh = imgui.calc_text_size(label)
            col = imgui.get_color_u32((1, 1, 1, 1))
            dl.add_text((pmin[0] + (aw - lw) * 0.5, pmax[1] - 70 + (70 - lh) * 0.5), col, label)
            font_manager.pop_font()

        imgui.end_group()
        imgui.pop_id()
        return clicked

    def buy_product(self, product: dict):
        url = product.get("url")
        if url:
            webbrowser.open(url)
        print(f"购买 {product['name']}")


class RedeemPanel:
    def __init__(self, app: "AIStudio"):
        self.app = app
        self.redeem_code = ""
        self.should_draw_redeem = False
        self.should_draw_redeem_confirm = False
        self.should_draw_redeem_success = False
        self.should_draw_redeem_error = False

    def begin_redeem(self):
        self.redeem_code = ""
        self.should_draw_redeem = True
        self.should_draw_redeem_confirm = False
        self.should_draw_redeem_success = False
        self.should_draw_redeem_error = False

    def clear_redeem(self):
        self.redeem_code = ""
        self.should_draw_redeem = False
        self.should_draw_redeem_confirm = False
        self.should_draw_redeem_success = False
        self.should_draw_redeem_error = False

    def draw(self):
        self.draw_redeem()
        self.draw_redeem_confirm()
        self.draw_redeem_ok()
        self.draw_redeem_error()

    def draw_redeem(self):
        if self.should_draw_redeem:
            imgui.open_popup("##Redeem", imgui.PopupFlags.NO_REOPEN)
        imgui.set_next_window_size((575, -imgui.FLT_MIN), imgui.Cond.ALWAYS)
        flags = 0
        flags |= imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SCROLL_WITH_MOUSE
        flags |= imgui.WindowFlags.NO_SCROLLBAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS

        style = imgui.get_style()
        if imgui.begin_popup_modal("##Redeem", False, flags)[0]:
            imgui.push_style_var(imgui.StyleVar.CELL_PADDING, (style.window_padding[0] * 0.5, 0))
            # 标题
            if True:
                self.app.font_manager.push_h1_font()

                imgui.push_style_var_y(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.button(_T("Use Redeem Code"))
                imgui.pop_style_var(1)
                imgui.same_line()

                icon = TexturePool.get_tex_id("redeem_header")
                tex = TexturePool.get_tex(icon)
                scale = imgui.get_text_line_height() / tex.height
                imgui.image_button(
                    "Redeem",
                    icon,
                    (tex.width * scale, tex.height * scale),
                    tint_col=Const.BUTTON_SELECTED,
                )
                imgui.pop_style_color(3)
                imgui.same_line()

                h = imgui.get_frame_height()
                aw = imgui.get_content_region_avail()[0]
                imgui.dummy((aw - style.item_spacing[0] - h, 0))
                imgui.same_line()
                imgui.push_style_color(imgui.Col.BUTTON, Const.CLOSE_BUTTON_NORMAL)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.CLOSE_BUTTON_ACTIVE)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.CLOSE_BUTTON_HOVERED)
                if CustomWidgets.colored_image_button("##CloseBtn", "close", (h, h)):
                    imgui.close_current_popup()
                    self.clear_redeem()
                imgui.pop_style_var(1)
                imgui.pop_style_color(3)
                self.app.font_manager.pop_font()

            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            imgui.text(_T("Please enter your redeem code"))
            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            # 兑换规格
            imgui.push_style_color(imgui.Col.FRAME_BG, Const.FRAME_BG)
            imgui.push_style_var_x(imgui.StyleVar.CELL_PADDING, Const.CELL_P[0] / 2)
            if imgui.begin_table("##BuyTable", 2, imgui.TableFlags.SIZING_STRETCH_SAME):
                imgui.table_setup_column("##Ele1", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 0)
                imgui.table_setup_column("##Ele2", imgui.TableColumnFlags.WIDTH_FIXED, 0, 1)

                imgui.table_next_column()
                imgui.push_item_width(-imgui.FLT_MIN)
                _, self.redeem_code = imgui.input_text("##RedeemCode", self.redeem_code)
                imgui.pop_item_width()

                imgui.table_next_column()
                if imgui.button(_T("Use"), (101, 0)):
                    imgui.close_current_popup()
                    self.should_draw_redeem = False
                    self.should_draw_redeem_confirm = True
                self.draw_redeem_confirm()

                imgui.end_table()
            imgui.pop_style_color(1)
            imgui.pop_style_var(1)

            imgui.pop_style_var(1)
            imgui.end_popup()

    def draw_redeem_confirm(self):
        if self.should_draw_redeem_confirm:
            imgui.open_popup("##RedeemConfirm", imgui.PopupFlags.NO_REOPEN)
        imgui.set_next_window_size((575, -imgui.FLT_MIN), imgui.Cond.ALWAYS)
        flags = 0
        flags |= imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SCROLL_WITH_MOUSE
        flags |= imgui.WindowFlags.NO_SCROLLBAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS
        style = imgui.get_style()
        if imgui.begin_popup_modal("##RedeemConfirm", False, flags)[0]:
            # 标题
            if True:
                self.app.font_manager.push_h1_font()

                imgui.push_style_var_y(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)

                imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.button(_T("Confirm to Redeem?"))
                imgui.pop_style_var(1)

                imgui.pop_style_color(3)
                imgui.same_line()

                h = imgui.get_frame_height()
                aw = imgui.get_content_region_avail()[0]
                imgui.dummy((aw - style.item_spacing[0] - h, 0))
                imgui.same_line()
                imgui.push_style_color(imgui.Col.BUTTON, Const.CLOSE_BUTTON_NORMAL)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.CLOSE_BUTTON_ACTIVE)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.CLOSE_BUTTON_HOVERED)
                if CustomWidgets.colored_image_button("##CloseBtn", "close", (h, h)):
                    imgui.close_current_popup()
                    self.clear_redeem()
                imgui.pop_style_color(3)

                imgui.pop_style_var(1)
                self.app.font_manager.pop_font()

            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            redeem_value = self.redeem_to_credits()
            imgui.text(_T("You will redeem %s ice pops(credits)") % redeem_value)
            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))

            imgui.table_next_column()
            if imgui.button(_T("OK"), (101, 0)):
                imgui.close_current_popup()
                self.should_draw_redeem_confirm = False
                if self.is_redeem_code_valid():
                    self.should_draw_redeem_success = True
                    credits = self.app.state.redeem_credits(self.redeem_code)
                    if credits > 0:
                        print("兑换成功")
                    else:
                        print("兑换失败")
                else:
                    self.should_draw_redeem_error = True
                    print("兑换码无效")

            self.draw_redeem_ok()
            self.draw_redeem_error()

            imgui.same_line()

            if imgui.button(_T("Cancel"), (101, 0)):
                imgui.close_current_popup()
                self.clear_redeem()

            imgui.end_popup()

    def draw_redeem_ok(self):
        if self.should_draw_redeem_success:
            imgui.open_popup("##RedeemOk", imgui.PopupFlags.NO_REOPEN)
        imgui.set_next_window_size((575, -imgui.FLT_MIN), imgui.Cond.ALWAYS)
        flags = 0
        flags |= imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SCROLL_WITH_MOUSE
        flags |= imgui.WindowFlags.NO_SCROLLBAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS
        style = imgui.get_style()
        if imgui.begin_popup_modal("##RedeemOk", False, flags)[0]:
            # 标题
            if True:
                self.app.font_manager.push_h1_font()

                imgui.push_style_var_y(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.button(_T("Redeem Success!"))
                imgui.pop_style_var(1)
                imgui.pop_style_color(3)
                imgui.same_line()

                h = imgui.get_frame_height()
                aw = imgui.get_content_region_avail()[0]
                imgui.dummy((aw - style.item_spacing[0] - h, 0))
                imgui.same_line()
                imgui.push_style_color(imgui.Col.BUTTON, Const.CLOSE_BUTTON_NORMAL)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.CLOSE_BUTTON_ACTIVE)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.CLOSE_BUTTON_HOVERED)
                if CustomWidgets.colored_image_button("##CloseBtn", "close", (h, h)):
                    imgui.close_current_popup()
                    self.clear_redeem()
                imgui.pop_style_var(1)
                imgui.pop_style_color(3)
                self.app.font_manager.pop_font()

            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            redeem_value = self.redeem_to_credits()
            imgui.text(_T("You have obtained %s ice pops(credits)") % redeem_value)
            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            if imgui.button(_T("Got it!")):
                self.should_draw_redeem_success = False
                imgui.close_current_popup()
                self.clear_redeem()

            imgui.end_popup()

    def draw_redeem_error(self):
        if self.should_draw_redeem_error:
            imgui.open_popup("##RedeemError", imgui.PopupFlags.NO_REOPEN)
        imgui.set_next_window_size((575, -imgui.FLT_MIN), imgui.Cond.ALWAYS)
        flags = 0
        flags |= imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SCROLL_WITH_MOUSE
        flags |= imgui.WindowFlags.NO_SCROLLBAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS
        style = imgui.get_style()
        if imgui.begin_popup_modal("##RedeemError", False, flags)[0]:
            # 标题
            if True:
                self.app.font_manager.push_h1_font()

                imgui.push_style_var_y(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.button(_T("Redeem Failed ~ QAQ"))
                imgui.pop_style_var(1)
                imgui.pop_style_color(3)
                imgui.same_line()

                h = imgui.get_frame_height()
                aw = imgui.get_content_region_avail()[0]
                imgui.dummy((aw - style.item_spacing[0] - h, 0))
                imgui.same_line()
                imgui.push_style_color(imgui.Col.BUTTON, Const.CLOSE_BUTTON_NORMAL)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.CLOSE_BUTTON_ACTIVE)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.CLOSE_BUTTON_HOVERED)
                if CustomWidgets.colored_image_button("##CloseBtn", "close", (h, h)):
                    imgui.close_current_popup()
                    self.clear_redeem()
                imgui.pop_style_var(1)
                imgui.pop_style_color(3)
                self.app.font_manager.pop_font()

            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            imgui.text(_T("Redeem Code Error or Already Used."))
            imgui.text(_T("Please Check or Contact Customer Service."))
            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            if imgui.button(_T("Exit"), (101, 0)):
                imgui.close_current_popup()
                self.clear_redeem()
            imgui.end_popup()

    def redeem_to_credits(self) -> int:
        if not self.is_redeem_code_valid():
            return 0
        pat = "BG([0-9]{3})-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12}"
        try:
            redeem_value = int(re.match(pat, self.redeem_code).group(1))
            credits_value = self.app.state.redeem_to_credits_table.get(redeem_value, 0)
        except Exception:
            credits_value = 0
        return credits_value

    def is_redeem_code_valid(self) -> bool:
        pat = "BG[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12}"
        return bool(re.match(pat, self.redeem_code))


class Bubble:
    def __init__(
        self,
        anim_system: AnimationSystem,
        text: str,
        pos: tuple[float, float] = (0, 0),
        duration: float = 15,
        icon: str = "account_warning",
    ) -> None:
        self.text = text
        self.icon = icon
        self.x = pos[0]
        self.y = pos[1]
        self.duration = duration
        self.alpha = 1.0
        self.shake_x = 0.0
        self.is_alive = True

        # 使用 Parallel 组合多个并行效果
        # 1. 位置持续向上
        anim_system.add(
            Sequence(
                [
                    Tween(0, 0, duration=self.duration * 0.7),
                    Tween(
                        self.y,
                        self.y - 120,
                        duration=self.duration * 0.3,
                        easing=Easing.ease_out_quad,
                        on_update=lambda v: setattr(self, "y", v),
                    ),
                ]
            )
        )

        # 2. 初始抖动效果
        def apply_shake(t: float) -> None:
            self.shake_x = math.sin(time.time() * 40) * 5 * (1 - t)

        anim_system.add(Tween(0, 1, duration=self.duration * 0.2, on_update=apply_shake))

        # 3. 延迟后淡出并销毁
        anim_system.add(
            Sequence(
                [
                    Tween(0, 0, duration=self.duration * 0.7),  # 等待 1.2 秒
                    Tween(
                        1.0,
                        0.0,
                        duration=self.duration * 0.3,
                        easing=Easing.ease_out_quad,
                        on_update=lambda v: setattr(self, "alpha", v),
                    ),
                ]
            )
        ).on_complete(self._destroy)

    def _destroy(self) -> None:
        self.is_alive = False

    def draw(self, app: "AIStudio") -> None:
        """渲染逻辑"""
        if not self.is_alive:
            return

        wp = imgui.get_style().window_padding
        lh = imgui.get_text_line_height_with_spacing()
        text_size = imgui.calc_text_size(self.text)
        icon_size = text_size[1]
        spacing = lh * 0.5
        content_size = icon_size + spacing + text_size[0], text_size[1]

        x = self.x + (app.screen_width - content_size[0]) / 2 + self.shake_x
        y = self.y + app.screen_height - lh * 2

        dl = imgui.get_foreground_draw_list()

        text_col = imgui.get_color_u32(imgui.Col.TEXT, self.alpha)
        bg_col = imgui.get_color_u32(imgui.Col.WINDOW_BG, self.alpha)
        icon_col = imgui.get_color_u32(imgui.Col.TEXT, self.alpha)

        p_min = (x - wp[0], y - wp[1])
        p_max = (x + content_size[0] + wp[0], y + content_size[1] + wp[1])

        rounding = imgui.get_style().frame_rounding
        # 绘制背景和边框
        dl.add_rect_filled(p_min, p_max, bg_col, rounding=rounding)

        icon = TexturePool.get_tex_id(self.icon)
        p_min = x, y + (content_size[1] - icon_size) / 2
        p_max = p_min[0] + icon_size, p_min[1] + icon_size
        dl.add_image(icon, p_min, p_max, col=icon_col)

        dl.add_text((x + spacing + icon_size, y), text_col, self.text)


class BubbleMessage:
    def __init__(self, text: str, icon: str = "warning") -> None:
        self.text = text
        self.icon = icon

    def make_bubble(self, app: "AIStudio") -> Bubble:
        return Bubble(app.animation_system, self.text, icon=self.icon)


class BubbleLogger:
    def __init__(self, app: "AIStudio") -> None:
        self.app = app
        self.animation_system = app.animation_system
        self.bubbles: dict[str, Bubble] = {}
        self.messages: list[BubbleMessage] = []

    def push_error_message(self, message: str):
        bubble = BubbleMessage(message, icon="warning")
        self.messages.append(bubble)

    def push_info_message(self, message: str):
        bubble = BubbleMessage(message, icon="info")
        self.messages.append(bubble)

    def draw_and_update(self):
        while self.messages:
            msg = self.messages.pop()
            self.bubbles[msg] = msg.make_bubble(self.app)
        for message, bubble in list(self.bubbles.items()):
            if bubble.is_alive:
                bubble.draw(self.app)
            else:
                self.bubbles.pop(message)


class AIStudio(AppHud):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_panel = AIStudioPanelType.GENERATION
        self.state = Account.get_instance()
        self.client = UniversalClient()
        self.store_panel = StorePanel(self)
        self.client_wrapper = StudioWrapper()
        self.bubble_logger = BubbleLogger(self)
        self.urls = {
            "Disclaimers": "https://shimo.im/docs/1d3aMnalmBf5ep3g/",
            "Feedback": "https://shimo.im/docs/vVqRM5DejgiPwd3y/",
            "Community": "https://shimo.im/docs/8Nk6ed5w6xsEzRqL/",
        }
        # 加载模型注册表
        self.model_registry = ModelRegistry.get_instance()

        # 初始化 active_client 为默认模型 Name
        self.active_client = ""
        self.refresh_client()

    def refresh_client(self):
        available_models = self.get_available_models()
        if not available_models:
            self.active_client = ""
            return
        if self.active_client in available_models:
            return

        self.active_client = available_models[0]
        self.client.current_model_name = self.active_client  # 通知 Client 切换模型

    def get_available_models(self) -> list[str]:
        """获取当前认证模式下可用的模型列表

        Returns:
            model_name列表
            例如: ["google/NanoBananaPro", ...]
        """
        current_auth_mode = self.state.auth_mode

        # 从注册表获取支持当前认证模式的模型
        models = self.model_registry.list_models(
            auth_mode=current_auth_mode,
            category="IMAGE_GENERATION",  # 目前只显示图像生成模型
        )

        result = [model.model_name for model in models]
        return result

    def calc_active_client_price(self, price_table: dict) -> int | None:
        return self.client.calc_price(price_table)

    def push_error_message(self, message: str):
        translated_msg = pgettext(message)
        self.bubble_logger.push_error_message(translated_msg)

    def push_info_message(self, message: str):
        translated_msg = pgettext(message)
        self.bubble_logger.push_info_message(translated_msg)

    def handler_draw(self, _area: bpy.types.Area):
        self.draw_studio_panel()

    def draw_studio_panel(self):
        window_size = 540, 1359
        ui_offset = get_pref().ui_offset
        window_pos = (get_tool_panel_width() + ui_offset[0]) / self.screen_scale, ui_offset[1] / self.screen_scale
        imgui.set_next_window_pos(window_pos, imgui.Cond.ONCE)
        imgui.set_next_window_size(window_size, imgui.Cond.ALWAYS)
        flags = 0
        flags |= imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SCROLL_WITH_MOUSE
        flags |= imgui.WindowFlags.NO_SCROLLBAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS

        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, Const.WINDOW_P)
        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.WINDOW_R)
        imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, Const.FRAME_P)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_R)
        imgui.push_style_var(imgui.StyleVar.CELL_PADDING, Const.RP_CELL_P)
        imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, Const.ITEM_S)

        imgui.push_style_color(imgui.Col.WINDOW_BG, Const.RP_L_BOX_BG)
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)

        istyle = imgui.get_style()
        fp = istyle.frame_padding
        item_spacing = istyle.item_spacing

        imgui.begin("##AIStudioPanel", False, flags)
        self.sync_window_pos_to_pref()

        # Error Log Bubble
        if True:
            self.draw_and_update_error_log()

        # Left
        if True:
            imgui.begin_group()
            btn_size = 40, 40
            subpanel_config = {
                AIStudioPanelType.GENERATION: "generation",
                AIStudioPanelType.HISTORY: "history",
                AIStudioPanelType.SETTINGS: "settings",
            }
            btn_size = (btn_size[0] + fp[0] * 2, btn_size[1] + fp[1] * 2)
            for subpanel in subpanel_config:
                if subpanel == AIStudioPanelType.SETTINGS:
                    imgui.invisible_button("##Dummy", (1, -(btn_size[1] + item_spacing[1])))
                    pos = imgui.get_cursor_pos()

                    self.font_manager.push_h5_font(12 * Const.SCALE)
                    line_height = imgui.get_text_line_height_with_spacing()
                    imgui.set_cursor_pos_y(pos[1] - item_spacing[1] - line_height)
                    imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                    imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                    imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                    imgui.button(f"V{'.'.join(map(str, get_addon_version()))}")
                    imgui.pop_style_color(3)
                    self.font_manager.pop_font()

                    imgui.set_cursor_pos_y(pos[1])

                icon = TexturePool.get_tex_id(subpanel_config[subpanel])
                if imgui.button(f"##Btn{subpanel}", btn_size):
                    self.active_panel = subpanel
                col = Const.CLOSE_BUTTON_NORMAL
                if imgui.is_item_active():
                    col = Const.BUTTON_ACTIVE
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

        imgui.same_line()

        # Right
        if True:
            imgui.begin_group()
            wx, wy = imgui.get_window_pos()
            ww, wh = imgui.get_window_size()
            cx = imgui.get_cursor_pos_x()

            lt = wx + cx, wy + 0
            rb = wx + ww, wy + wh
            col = imgui.get_color_u32(Const.RP_R_BOX_BG)
            r = Const.LP_WINDOW_R + 4
            dl = imgui.get_window_draw_list()
            dl.add_rect_filled(lt, rb, col, r, imgui.DrawFlags.ROUND_CORNERS_RIGHT)

            fp = istyle.frame_padding
            imgui.push_style_color(imgui.Col.FRAME_BG, Const.TRANSPARENT)
            imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, Const.LP_WINDOW_P)
            if True:
                imgui.set_cursor_pos_x(cx + fp[0])
                imgui.begin_group()
                imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, (0, 0))
                imgui.push_id("##RightInner")

                imgui.begin_group()
                self.draw_generation_panel()
                self.draw_history_panel()
                self.draw_setting_panel()
                imgui.end_group()

                imgui.pop_id()
                imgui.pop_style_var(1)
                imgui.end_group()
            imgui.pop_style_color(1)
            imgui.pop_style_var(1)

            imgui.end_group()

        imgui.end()
        imgui.pop_style_var(6)
        imgui.pop_style_color(4)

    def sync_window_pos_to_pref(self):
        # Record Window Position
        if imgui.is_window_hovered() and self.is_mouse_dragging():
            pos = imgui.get_window_pos()
            tool_panel_width = get_tool_panel_width()
            offset = pos[0] * self.screen_scale - tool_panel_width, pos[1] * self.screen_scale
            get_pref().set_ui_offset(offset)

    def draw_and_update_error_log(self):
        for error in self.client.take_errors():
            self.push_error_message(str(error))
        for error in self.state.take_errors():
            self.push_error_message(str(error))
        self.bubble_logger.draw_and_update()

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
            imgui.button(_T("AI STUDIO"))
            imgui.same_line()
            icon = TexturePool.get_tex_id("lite_header")
            tex = TexturePool.get_tex(icon)
            scale = imgui.get_text_line_height() / tex.height
            imgui.image_button("", icon, (tex.width * scale, tex.height * scale), tint_col=Const.BUTTON_SELECTED)
            imgui.pop_style_color(3)
            imgui.same_line()
            self.draw_panel_close_button()
            self.font_manager.pop_font()

        # 生成面板
        imgui.dummy(dummy_size)
        if imgui.begin_table("#Engine", 4):
            imgui.table_setup_column("#EngineEle1", imgui.TableColumnFlags.WIDTH_FIXED, 0, 0)
            imgui.table_setup_column("#EngineEle2", imgui.TableColumnFlags.WIDTH_FIXED, 0, 1)
            imgui.table_setup_column("#EngineEle3", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 2)
            imgui.table_setup_column("#EngineEle4", imgui.TableColumnFlags.WIDTH_FIXED, 0, 3)
            imgui.table_next_column()
            self.font_manager.push_h2_font()
            imgui.text(_T("Engine"))
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
            self.draw_help_button()

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
            item_spacing = imgui.get_style().item_spacing
            gen_btn_height = 79
            imgui.push_style_color(imgui.Col.FRAME_BG, (48 / 255, 48 / 255, 48 / 255, 1))
            with with_child("Outer", (0, -(gen_btn_height + item_spacing[1])), flags):
                wrapper = self.client_wrapper
                wrapper.load(self.client)  # TODO: 性能改进

                for widget in wrapper.get_widgets_by_category("Input"):
                    if not widget.is_visible():
                        continue
                    widget.col_bg = Const.WINDOW_BG
                    widget.col_widget = Const.FRAME_BG
                    widget.display_begin(widget, self)
                    widget.display(widget, self)
                    self.draw_wrapper_widget_spec(wrapper, widget)
                    widget.display_end(widget, self)

                # 从 wrapper 获取 client，如果 wrapper 是默认的，则使用 self.client
                if wrapper.studio_client is not None:
                    editor = StudioHistoryViewer(self, wrapper.studio_client.history)
                    editor.draw_first()
            imgui.pop_style_color()

            # 底部按钮
            if True:
                imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.6)
                imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, 15)
                full_width = imgui.get_content_region_avail()[0]
                self.font_manager.push_h1_font()
                status = self.client.query_status()
                # 按钮状态:
                #   1. 无状态
                #   2. 正在提交
                #   3. 正在渲染
                #   4. 停止渲染
                # "running", "processing"
                task_state: TaskState = status.get("state", "")
                is_rendering = False
                show_stop_btn = False
                label = "  " + _T("Start")
                if self.state.auth_mode == AuthMode.ACCOUNT.value:
                    price = self.client.calc_price()
                    if price is not None:
                        label += _T("(%s/use)") % price
                if self.client.is_task_submitting:
                    label = "  " + _T("Task Submitting...")
                if task_state == "running":
                    is_rendering = True
                    elapsed_time = self.client.query_task_elapsed_time()
                    label = f"  {_T('Generating')}({elapsed_time:.1f})s"
                    rmin = imgui.get_cursor_screen_pos()
                    rmax = (rmin[0] + full_width, rmin[1] + gen_btn_height)
                    if imgui.is_mouse_hovering_rect(rmin, rmax):
                        label = "  " + _T("Stop AI Rendering")
                        show_stop_btn = True
                if task_state in {"preparing", "rendering"}:
                    is_rendering = True
                    elapsed_time = status.get("elapsed_time", 0)
                    label = f"  {_T('Rendering')}({elapsed_time:.1f})s"
                    rmin = imgui.get_cursor_screen_pos()
                    rmax = (rmin[0] + full_width, rmin[1] + gen_btn_height)
                    if imgui.is_mouse_hovering_rect(rmin, rmax):
                        label = "  " + _T("Stop AI Rendering")
                        show_stop_btn = True
                col_btn = Const.SLIDER_NORMAL
                col_btn_hover = (77 / 255, 161 / 255, 255 / 255, 1)
                col_btn_active = (26 / 255, 112 / 255, 208 / 255, 1)
                if is_rendering:
                    col_btn = (255 / 255, 141 / 255, 26 / 255, 1)
                    col_btn_hover = (255 / 255, 87 / 255, 51 / 255, 1)
                    col_btn_active = (255 / 255, 131 / 255, 5 / 255, 1)
                    if show_stop_btn:
                        col_btn = (255 / 255, 116 / 255, 51 / 255, 1)
                        col_btn_hover = (255 / 255, 116 / 255, 51 / 255, 1)
                        col_btn_active = (255 / 255, 62 / 255, 20 / 255, 1)

                imgui.push_style_color(imgui.Col.BUTTON, col_btn)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, col_btn_hover)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, col_btn_active)

                label_size = imgui.calc_text_size(label)
                if imgui.button("##开始AI渲染", (full_width, gen_btn_height)):
                    if not is_rendering:
                        self.client.add_task(self.state)
                    elif show_stop_btn:
                        self.client.cancel_generate_task()

                pmin = imgui.get_item_rect_min()
                pmax = imgui.get_item_rect_max()
                inner_width = 30 + label_size[0]
                inner_height = label_size[1]
                offset_x = (pmax[0] - pmin[0] - inner_width) * 0.5
                offset_y = (pmax[1] - pmin[1] - inner_height) * 0.5
                pmin = pmin[0] + offset_x, pmin[1] + offset_y
                pmax = pmax[0] - offset_x, pmax[1] - offset_y
                icon_name = "start_ai_generate"
                if is_rendering:
                    icon_name = "ai_rendering"
                    if show_stop_btn:
                        icon_name = "stop_ai_generate"
                icon = TexturePool.get_tex_id(icon_name)
                dl = imgui.get_window_draw_list()
                dl.add_image(icon, pmin, (pmin[0] + (pmax[1] - pmin[1]), pmax[1]))
                col = imgui.get_color_u32((1, 1, 1, 1))
                dl.add_text((pmin[0] + 30, pmin[1]), col, label)
                self.font_manager.pop_font()

                imgui.pop_style_var(2)
                imgui.pop_style_color(3)

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
            imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0)
            imgui.push_style_color(imgui.Col.FRAME_BG, Const.FRAME_BG)
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)

            # 获取当前认证模式下可用的模型列表
            self.refresh_client()
            available_models = self.get_available_models()

            # 计算最大宽度
            max_item_width = 0
            for display_name in available_models:
                max_item_width = max(max_item_width, imgui.calc_text_size(display_name)[0])
            max_item_width += 2 * imgui.get_style().frame_padding[0]
            aw = imgui.get_content_region_avail()[0]
            max_item_width = max(aw, max_item_width)

            # 绘制下拉框
            if imgui.begin_combo("##Item", self.active_client):
                for model_name in available_models:
                    is_selected = self.active_client == model_name
                    if is_selected:
                        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
                    if imgui.button(model_name, (max_item_width, 0)):
                        self.active_client = model_name
                        self.client.current_model_name = model_name  # 通知 Client 切换模型
                        imgui.close_current_popup()
                    if is_selected:
                        imgui.pop_style_color()
                imgui.end_combo()
            if imgui.is_item_hovered():
                title = _T("Please Select Generation Engine")
                tip = _T(
                    "Select Engine and Fill API, You can use AI in Blender seamlessly. Note: This tool only has the function of connecting to the service. The generated content & fees are subject to the provider.")
                imgui.set_next_window_size((759, 0))
                AppHelperDraw.draw_tips_with_title(self, [tip], title)
            imgui.pop_style_color(2)
            imgui.pop_style_var(4)
            imgui.pop_item_width()
        imgui.pop_style_color(1)

    def draw_history_panel(self):
        if self.active_panel != AIStudioPanelType.HISTORY:
            return
        dummy_size = 0, 26 / 2
        imgui.push_style_var_x(imgui.StyleVar.CELL_PADDING, Const.LP_CELL_P[0])
        imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, 0)

        if True:
            self.font_manager.push_h1_font()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.button(_T("Gen"))
            imgui.same_line()
            icon = TexturePool.get_tex_id("history_header")
            tex = TexturePool.get_tex(icon)
            scale = imgui.get_text_line_height() / tex.height
            imgui.image_button("", icon, (tex.width * scale, tex.height * scale), tint_col=Const.BUTTON_SELECTED)
            imgui.pop_style_color(3)
            imgui.same_line()
            self.draw_panel_close_button()
            self.font_manager.pop_font()

        # 设置面板
        imgui.dummy(dummy_size)
        if imgui.begin_table("#Engine", 4):
            imgui.table_setup_column("#EngineEle1", imgui.TableColumnFlags.WIDTH_FIXED, 0, 0)
            imgui.table_setup_column("#EngineEle2", imgui.TableColumnFlags.WIDTH_FIXED, 0, 1)
            imgui.table_setup_column("#EngineEle3", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 2)
            imgui.table_setup_column("#EngineEle4", imgui.TableColumnFlags.WIDTH_FIXED, 0, 3)
            imgui.table_next_column()
            self.font_manager.push_h2_font()
            imgui.text(_T("List"))
            self.font_manager.pop_font()

            # 小字
            imgui.table_next_column()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.push_style_var_y(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0)
            imgui.push_font(None, 12 * Const.SCALE)
            imgui.button("List")
            imgui.pop_font()
            imgui.pop_style_var()
            imgui.pop_style_color(3)

            imgui.table_next_column()
            imgui.text("")

            imgui.table_next_column()
            self.draw_output_queue_button()

            imgui.end_table()

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

            flags = 0
            flags |= imgui.ChildFlags.FRAME_STYLE
            imgui.push_style_color(imgui.Col.FRAME_BG, (48 / 255, 48 / 255, 48 / 255, 1))
            with with_child("Outer", (0, -1), flags):
                history = StudioHistory.get_instance()
                editor = StudioHistoryViewer(self, history)
                editor.draw_all()
            imgui.pop_style_color(1)

            imgui.pop_style_var(6)
            imgui.pop_style_color(5)

        imgui.pop_style_var(2)

    def draw_setting_panel(self):
        if self.active_panel != AIStudioPanelType.SETTINGS:
            return
        dummy_size = 0, 26 / 2
        imgui.push_style_var_x(imgui.StyleVar.CELL_PADDING, Const.LP_CELL_P[0])
        imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, 0)

        if True:
            self.font_manager.push_h1_font()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.button(_T("User"))
            imgui.same_line()
            icon = TexturePool.get_tex_id("settings_header")
            tex = TexturePool.get_tex(icon)
            scale = imgui.get_text_line_height() / tex.height
            imgui.image_button("", icon, (tex.width * scale, tex.height * scale), tint_col=Const.BUTTON_SELECTED)
            imgui.pop_style_color(3)
            imgui.same_line()
            self.draw_panel_close_button()
            self.font_manager.pop_font()

        # 设置面板
        imgui.dummy(dummy_size)
        if imgui.begin_table("#Engine", 4):
            imgui.table_setup_column("#EngineEle1", imgui.TableColumnFlags.WIDTH_FIXED, 0, 0)
            imgui.table_setup_column("#EngineEle2", imgui.TableColumnFlags.WIDTH_FIXED, 0, 1)
            imgui.table_setup_column("#EngineEle3", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 2)
            imgui.table_setup_column("#EngineEle4", imgui.TableColumnFlags.WIDTH_FIXED, 0, 3)
            imgui.table_next_column()
            self.font_manager.push_h2_font()
            imgui.text(_T("Service"))
            self.font_manager.pop_font()

            # 小字
            imgui.table_next_column()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            imgui.push_style_var_y(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0)
            imgui.push_font(None, 12 * Const.SCALE)
            imgui.button("API")
            imgui.pop_font()
            imgui.pop_style_var()
            imgui.pop_style_color(3)

            imgui.table_next_column()
            imgui.text("")

            imgui.table_next_column()
            self.draw_help_button()

            imgui.end_table()
        # 显示API/账号
        if True:
            imgui.dummy((dummy_size[0], dummy_size[1] - 8))

            imgui.push_style_var_y(imgui.StyleVar.WINDOW_PADDING, 24)
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
            imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, Const.CHILD_P)
            imgui.push_style_var(imgui.StyleVar.FRAME_BORDER_SIZE, Const.CHILD_BS)
            imgui.push_style_var(imgui.StyleVar.POPUP_ROUNDING, 24)
            imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, Const.CHILD_P[0])

            imgui.push_style_color(imgui.Col.FRAME_BG, Const.WINDOW_BG)
            imgui.push_style_color(imgui.Col.POPUP_BG, Const.POPUP_BG)
            imgui.push_style_color(imgui.Col.HEADER, Const.BUTTON)
            imgui.push_style_color(imgui.Col.HEADER_ACTIVE, Const.BUTTON_ACTIVE)
            imgui.push_style_color(imgui.Col.HEADER_HOVERED, Const.BUTTON_HOVERED)
            self.draw_auth()
            self.draw_account_panel()
            self.draw_api_panel()

            imgui.pop_style_var(6)
            imgui.pop_style_color(5)

        # 其他内容
        imgui.dummy(dummy_size)
        if True:
            imgui.push_style_var_y(imgui.StyleVar.ITEM_SPACING, 26)
            self.font_manager.push_h1_font()
            for misc in ["Disclaimers", "Feedback", "Community"]:
                imgui.push_id(misc)
                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                imgui.button(_T(misc))
                imgui.pop_style_color(3)

                imgui.same_line()

                aw = imgui.get_content_region_avail()[0]
                bh = imgui.get_text_line_height()
                bw = aw - bh - imgui.get_style().item_spacing[0]
                imgui.invisible_button("##" + misc, (bw, bh))

                imgui.same_line()

                imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
                imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.WINDOW_R)
                if CustomWidgets.icon_label_button("url", "", "CENTER", (bh, bh), bh * 0.65):
                    url = self.urls.get(misc, "")
                    if url:
                        webbrowser.open(url)
                imgui.pop_style_var(1)
                imgui.pop_style_color(1)
                imgui.pop_id()
            self.font_manager.pop_font()
            imgui.pop_style_var()

        imgui.pop_style_var(2)

    def draw_account_panel(self):
        if self.state.auth_mode != AuthMode.ACCOUNT.value:
            return
        self.store_panel.draw_login_panel()
        self.store_panel.draw_account()

    def draw_help_button(self):
        help_url = self.state.help_url
        if not help_url:
            return
        imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.75)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        self.font_manager.push_h1_font(24)
        label = " " + _T("Help")
        label_size = imgui.calc_text_size(label)
        if imgui.button(f"##{label}", (112, 44)):
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

    def draw_output_queue_button(self):
        help_url = self.client.help_url
        if not help_url:
            return
        imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.75)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)

        self.font_manager.push_h1_font(24)
        label = _T("Output")
        label_size = imgui.calc_text_size(label)
        fp = imgui.get_style().window_padding
        icon_size = imgui.get_text_line_height_with_spacing()
        spacing = imgui.get_style().item_spacing
        bw = label_size[0] + spacing[0] + icon_size + fp[0]
        if CustomWidgets.icon_label_button("folder", label, "CENTER", (bw, 44)):
            open_dir(get_pref().output_cache_dir)
        self.font_manager.pop_font()
        imgui.pop_style_color(4)
        imgui.pop_style_var(2)

    def draw_auth(self):
        flags = 0
        flags |= imgui.ChildFlags.FRAME_STYLE
        flags |= imgui.ChildFlags.AUTO_RESIZE_Y
        flags |= imgui.ChildFlags.ALWAYS_AUTO_RESIZE
        imgui.push_style_color(imgui.Col.FRAME_BG, Const.WINDOW_BG)
        with with_child("##Auth", (0, 0), child_flags=flags):
            imgui.push_item_width(-1)
            imgui.push_style_var_x(imgui.StyleVar.FRAME_PADDING, Const.RP_FRAME_P[0])
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
            imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, Const.RP_CHILD_IS)
            imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0)
            imgui.push_style_color(imgui.Col.FRAME_BG, Const.FRAME_BG)
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            items = AuthMode
            aw = imgui.get_content_region_avail()[0]
            if imgui.begin_combo("##Item", _T(AuthMode(self.state.auth_mode).display_name)):
                for item in items:
                    is_selected = self.state.auth_mode == item.value
                    if is_selected:
                        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
                    if imgui.button(_T(item.display_name), (aw, 0)):
                        self.state.auth_mode = item.value
                        self.refresh_client() # 确保客户端刷新(设置项同步)
                        imgui.close_current_popup()
                    if is_selected:
                        imgui.pop_style_color()
                imgui.end_combo()
            imgui.pop_style_color(2)
            imgui.pop_style_var(4)
            imgui.pop_item_width()
        imgui.pop_style_color(1)

    def draw_api_panel(self):
        if self.state.auth_mode != AuthMode.API.value:
            return
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.WINDOW_BG)
        isize = 24
        self.font_manager.push_h3_font(20)
        label = _T("Service from API provider.")
        CustomWidgets.icon_label_button("account_warning", label, "CENTER", (0, 54), isize)
        self.font_manager.pop_font()
        imgui.pop_style_color(3)
        flags = imgui.ChildFlags.FRAME_STYLE | imgui.ChildFlags.AUTO_RESIZE_Y
        with with_child("Outer", (0, 0), flags):
            wrapper = self.client_wrapper
            wrapper.load(self.client)  # TODO: 性能改进
            for wrapper in [wrapper]:
                widgets = wrapper.get_widgets_by_category("Settings")
                if not widgets:
                    continue
                imgui.push_style_color(imgui.Col.FRAME_BG, Const.FRAME_BG)
                with with_child("Inner", (0, 0), flags):
                    # --- 标题: 名称 + 导航按钮 ---
                    if True:
                        imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                        aw = imgui.get_content_region_avail()[0]
                        bh = imgui.get_text_line_height_with_spacing()
                        bw = aw - bh - imgui.get_style().item_spacing[0]
                        imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0)
                        self.font_manager.push_h3_font()
                        imgui.button(wrapper.display_name, (bw, bh))
                        self.font_manager.pop_font()
                        imgui.pop_style_var(1)
                        imgui.pop_style_color(3)

                        imgui.same_line()

                        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
                        if CustomWidgets.icon_label_button("url", "", "CENTER", (bh, bh), 23):
                            webbrowser.open(wrapper.studio_client.help_url)
                        imgui.pop_style_color(1)

                    imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, imgui.get_style().frame_rounding * 0.5)
                    for widget in widgets:
                        # ✅ 添加可见性判断
                        if not widget.is_visible():
                            continue

                        widget.col_bg = Const.WINDOW_BG
                        widget.col_widget = Const.WINDOW_BG
                        widget.display_begin(widget, self)
                        widget.display(widget, self)
                        widget.display_end(widget, self)
                    imgui.pop_style_var(1)
                imgui.pop_style_color(1)

    def draw_panel_close_button(self):
        # 关闭按钮
        style = imgui.get_style()
        h = imgui.get_frame_height_with_spacing()
        aw = imgui.get_content_region_avail()[0]
        imgui.dummy((aw - style.item_spacing[0] - h, 0))
        imgui.same_line()
        imgui.push_style_color(imgui.Col.BUTTON, Const.CLOSE_BUTTON_NORMAL)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.CLOSE_BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.CLOSE_BUTTON_HOVERED)
        if CustomWidgets.colored_image_button("##CloseBtn", "close", (h, h)):
            self.active_panel = AIStudioPanelType.NONE
            self.queue_shoutdown()
        imgui.pop_style_color(3)

    def draw_wrapper_widget_spec(self, wrapper: StudioWrapper, widget: WidgetDescriptor):
        if widget.widget_name == "input_image_type" and imgui.is_item_hovered():
            imgui.set_next_window_size((630, 0))
            title = _T("First Image Mode")
            tips = [
                _T("The activity camera will be used for output, please select the output mode."),
                _T("CameraRender equal to Composition Result."),
                _T("CameraDepth equal to Mist (Mist effect can be set in World > Mist Pass)."),
            ]
            AppHelperDraw.draw_tips_with_title(self, tips, title)
            return
        if widget.widget_name == "prompt":
            wp = imgui.get_style().window_padding
            psize = imgui.get_item_rect_size()
            pos = imgui.get_cursor_pos()
            imgui.set_cursor_pos_y(pos[1] - psize[1])
            imgui.begin_child("##Ovrerlay", (0, imgui.get_text_line_height_with_spacing()))
            lh = imgui.get_text_line_height() * 0.75
            imgui.invisible_button("##FakeButton", (-lh * 1.5 - wp[0], 1))
            imgui.same_line()
            imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
            if imgui.button("##Switcher", (lh * 1.5, lh)):
                wrapper.studio_client.use_internal_prompt ^= True
            imgui.pop_style_color(3)
            dl = imgui.get_window_draw_list()
            pmin = imgui.get_item_rect_min()
            pmax = imgui.get_item_rect_max()
            if wrapper.studio_client.use_internal_prompt:
                icon_name = "internal_prompt_enable"
            else:
                icon_name = "internal_prompt_disable"
            icon = TexturePool.get_tex_id(icon_name)
            dl.add_image(icon, pmin, pmax)

            if imgui.is_item_hovered():
                imgui.set_next_window_size((580, 0))
                title = _T("Prompt Optimization")
                tip = _T("Enable Prompt Optimization to improve the quality of the generated image and the safety of the content.")
                AppHelperDraw.draw_tips_with_title(self, [tip], title)
            imgui.end_child()
            imgui.set_cursor_pos(pos)
            return
        if widget.widget_name == "aspect_ratio":
            if imgui.is_item_hovered():
                imgui.set_next_window_size((450, 0))
                title = _T("Image Size Config")
                tip = _T("Set the image size for the generated image.")
                AppHelperDraw.draw_tips_with_title(self, [tip], title)
            return
        if widget.widget_name == "resolution":
            if imgui.is_item_hovered():
                imgui.set_next_window_size((710, 0))
                title = _T("Image Resolution")
                tip = _T("Set the image resolution via both image size and aspect ratio, and the larger the resolution, the longer the generation time/resource required.")
                AppHelperDraw.draw_tips_with_title(self, [tip], title)
            return

    def test_webp_animation(self):
        for i, image in enumerate(Path.home().joinpath("Desktop/webp").glob("*.webp")):
            icon = TexturePool.get_animated_tex_id(image.as_posix(), time.time() + i)
            imgui.image(icon, (387, 217))
            if imgui.is_item_hovered():
                imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.CHILD_R)
                imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, (12, 12))
                imgui.begin_tooltip()
                tex = TexturePool.get_tex(icon)
                file_name = image.stem
                imgui.text(f"{file_name} [{tex.width}x{tex.height}]")
                imgui.dummy((0, 0))
                canvas_tex_width = self.screen_scale * tex.width
                canvas_tex_height = self.screen_scale * tex.height
                canvas_width = self.screen_width * 0.7
                canvas_height = self.screen_height * 0.7
                if canvas_tex_width > canvas_width:
                    canvas_tex_scale = canvas_width / canvas_tex_width
                    canvas_tex_height *= canvas_tex_scale
                    canvas_tex_width *= canvas_tex_scale
                if canvas_tex_height > canvas_height:
                    canvas_tex_scale = canvas_height / canvas_tex_height
                    canvas_tex_height *= canvas_tex_scale
                    canvas_tex_width *= canvas_tex_scale
                aw = imgui.get_content_region_avail()[0]
                if canvas_tex_width < aw:
                    canvas_tex_scale = aw / canvas_tex_width
                    canvas_tex_height *= canvas_tex_scale
                    canvas_tex_width *= canvas_tex_scale
                imgui.invisible_button("FakeButton", (canvas_tex_width, canvas_tex_height))
                pmin = imgui.get_item_rect_min()
                pmax = imgui.get_item_rect_max()
                dl = imgui.get_window_draw_list()
                dl.add_image_rounded(icon, pmin, pmax, (0, 0), (1, 1), 0xFFFFFFFF, Const.CHILD_R * 0.8)
                imgui.end_tooltip()
                imgui.pop_style_var(2)


DescriptorFactory.register(StudioImagesDescriptor.ptype, StudioImagesDescriptor)
