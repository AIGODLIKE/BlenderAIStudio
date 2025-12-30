import bpy
import re
import time
import webbrowser
import math
import platform
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from shutil import copyfile
from traceback import print_exc

from .clients import StudioHistoryItem, StudioHistory, StudioClient
from .gui.app.animation import AnimationSystem, Easing, Tween, Sequence
from .gui.app.app import AppHud
from .gui.app.renderer import imgui
from .gui.app.style import Const
from .gui.texture import TexturePool
from .gui.widgets import CustomWidgets, with_child
from .account import AuthMode, Account
from .tasks import TaskState
from .wrapper import BaseAdapter, WidgetDescriptor, DescriptorFactory
from ..preferences import get_pref
from ..timer import Timer
from ..utils import get_version


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
    except Exception:
        print_exc()


def open_dir(path):
    open_util = 'explorer "%s"'
    if platform.system() != "Windows":
        open_util = 'open /"%s"'

    try:
        subprocess.run(open_util % path, shell=True, check=True)
    except Exception:
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


class StudioHistoryItemViewer:
    def __init__(self, item: StudioHistoryItem) -> None:
        self.item = item

    def draw(self, app: "AIStudio"):
        col_bg = Const.WINDOW_BG
        col_widget = Const.FRAME_BG
        flags = 0
        flags |= imgui.ChildFlags.FRAME_STYLE
        flags |= imgui.ChildFlags.AUTO_RESIZE_Y
        flags |= imgui.ChildFlags.ALWAYS_AUTO_RESIZE
        imgui.push_style_color(imgui.Col.FRAME_BG, col_bg)
        with with_child(f"##Item_{self.item.index}", (0, 0), child_flags=flags):
            imgui.push_style_color(imgui.Col.FRAME_BG, col_widget)

            # 标题栏
            if imgui.begin_table("##Header", 3):
                imgui.table_setup_column("##Ele1", imgui.TableColumnFlags.WIDTH_FIXED, 0, 0)
                imgui.table_setup_column("##Ele2", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 1)
                imgui.table_setup_column("##Ele3", imgui.TableColumnFlags.WIDTH_FIXED, 0, 2)

                app.font_manager.push_h1_font(24)
                imgui.table_next_column()
                imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)
                imgui.text(f"#{self.item.index:03d}")
                imgui.pop_style_color()
                app.font_manager.pop_font()

                imgui.table_next_column()
                imgui.dummy((0, 0))

                imgui.table_next_column()
                file_name = Path(self.item.output_file).stem
                imgui.text(file_name)

                imgui.end_table()

            # 图片
            if imgui.begin_table("##Content", 2):
                aw = imgui.get_content_region_avail()[0]
                w1 = 207 / 354 * aw
                h1 = 126 / 207 * w1
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
                    icon = TexturePool.get_tex_id(self.item.output_file)
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
                    imgui.button("##FakeButton", (bw, bh))
                    pmin = imgui.get_item_rect_min()
                    pmax = imgui.get_item_rect_max()
                    dl = imgui.get_window_draw_list()
                    dl.add_image_rounded(icon, pmin, pmax, uvmin, uvmax, 0xFFFFFFFF, 12)
                    if imgui.is_item_hovered():
                        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.CHILD_R)
                        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, (12, 12))
                        imgui.begin_tooltip()
                        tex = TexturePool.get_tex(icon)
                        file_name = Path(self.item.output_file).stem
                        imgui.text(f"{file_name} [{tex.width}x{tex.height}]")
                        imgui.dummy((0, 0))
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
                            label = "编辑"
                            style = imgui.get_style()
                            bh = h1 / 2 - style.cell_padding[1] * 2 - style.frame_padding[1]
                            imgui.table_next_column()
                            if imgui.button("##编辑", (-imgui.FLT_MIN, bh)):
                                print("编辑图片")
                                image = self.item.output_file
                                meta = self.item.stringify()
                                context = bpy.context.copy()
                                Timer.put((edit_image_with_meta_and_context, image, meta, context))
                            if imgui.is_item_hovered():
                                title = "编辑图像"
                                tip = "打开图像编辑器，编辑当前图像。（可执行重绘、融图等编辑操作）"
                                imgui.set_next_window_size((720, 0))
                                AppHelperDraw.draw_tips_with_title(app, [tip], title)
                            dl = imgui.get_window_draw_list()
                            pmin = imgui.get_item_rect_min()
                            pmax = imgui.get_item_rect_max()
                            lh = imgui.get_text_line_height()
                            text_width = imgui.calc_text_size(label)[0]
                            pcenter = (pmin[0] + pmax[0]) * 0.5, (pmin[1] + pmax[1]) * 0.5
                            content_width = text_width + lh + style.item_spacing[0]
                            content_height = lh

                            icon = TexturePool.get_tex_id("image_edit")
                            ipmin = pcenter[0] - content_width * 0.5, pcenter[1] - content_height * 0.5
                            ipmax = ipmin[0] + content_height, pcenter[1] + content_height * 0.5
                            dl.add_image(icon, ipmin, ipmax)

                            col = imgui.get_color_u32(imgui.get_style().colors[imgui.Col.TEXT])
                            tpos = pcenter[0] - content_width * 0.5 + lh + style.item_spacing[0], pcenter[1] - content_height * 0.5
                            dl.add_text(tpos, col, label)

                        # 细节
                        if True:
                            label = "详情"
                            style = imgui.get_style()
                            bh = h1 / 2 - style.cell_padding[1] * 2 - style.frame_padding[1]

                            imgui.table_next_column()
                            old_show_detail = self.item.show_detail
                            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_SELECTED)
                            if old_show_detail:
                                imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON_SELECTED)
                            if imgui.button("##详情", (-imgui.FLT_MIN, bh)):
                                self.item.show_detail = not self.item.show_detail
                            if imgui.is_item_hovered():
                                title = "图像详情"
                                tip = "查看图像生成信息，例如提示词、生成时间等内容"
                                imgui.set_next_window_size((550, 0))
                                AppHelperDraw.draw_tips_with_title(app, [tip], title)
                            if old_show_detail:
                                imgui.pop_style_color(1)
                            imgui.pop_style_color(1)

                            dl = imgui.get_window_draw_list()
                            pmin = imgui.get_item_rect_min()
                            pmax = imgui.get_item_rect_max()
                            lh = imgui.get_text_line_height()
                            text_width = imgui.calc_text_size(label)[0]
                            pcenter = (pmin[0] + pmax[0]) * 0.5, (pmin[1] + pmax[1]) * 0.5
                            content_width = text_width + lh + style.item_spacing[0]
                            content_height = lh

                            icon = TexturePool.get_tex_id("image_detail")
                            ipmin = pcenter[0] - content_width * 0.5, pcenter[1] - content_height * 0.5
                            ipmax = ipmin[0] + content_height, pcenter[1] + content_height * 0.5
                            dl.add_image(icon, ipmin, ipmax)

                            col = imgui.get_color_u32(imgui.get_style().colors[imgui.Col.TEXT])
                            tpos = pcenter[0] - content_width * 0.5 + lh + style.item_spacing[0], pcenter[1] - content_height * 0.5
                            dl.add_text(tpos, col, label)

                        imgui.end_table()
                    imgui.pop_style_var(1)
                    imgui.pop_style_color(1)
                imgui.pop_style_var(3)
                imgui.pop_style_color(1)

                imgui.end_table()
            if self.item.show_detail:
                imgui.text("提示词")
                prompt = self.item.metadata.get("prompt", "No prompt found")
                h = imgui.get_text_line_height()
                imgui.same_line(imgui.get_content_region_avail()[0] - h)
                # 复制按钮
                if True:
                    icon = TexturePool.get_tex_id("prompt_copy")
                    imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                    imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                    imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                    if imgui.button("##copy", (h, h)):
                        bpy.context.window_manager.clipboard = prompt
                    imgui.pop_style_color(3)
                    col = (1, 1, 1, 1)
                    if imgui.is_item_active():
                        col = Const.BUTTON_SELECTED
                    elif imgui.is_item_hovered():
                        col = Const.CLOSE_BUTTON_HOVERED
                    col = imgui.get_color_u32(col)
                    dl = imgui.get_window_draw_list()
                    pmin = imgui.get_item_rect_min()
                    pmax = imgui.get_item_rect_max()
                    dl.add_image(icon, pmin, pmax, col=col)

                # 提示词
                mlt_flags = imgui.InputTextFlags.WORD_WRAP
                h = 133 / 354 * imgui.get_content_region_avail()[0]
                _, _ = imgui.input_text_multiline("##prompt", prompt, (-1, h), mlt_flags)
                h = imgui.get_text_line_height()
                icon = TexturePool.get_tex_id(self.item.output_file)
                tex = TexturePool.get_tex(icon)
                tex_width = tex.width
                tex_height = tex.height

                # 图片信息
                icon = TexturePool.get_tex_id("image_info_resolution")
                imgui.dummy((0, 0))
                imgui.image(icon, (h, h))
                imgui.same_line()
                imgui.text(f"{tex_width}*{tex_height} px (72dpi)")

                icon = TexturePool.get_tex_id("image_info_vendor")
                imgui.dummy((0, 0))
                imgui.image(icon, (h, h))
                imgui.same_line()
                imgui.text(f"{self.item.vendor}生成")

                icon = TexturePool.get_tex_id("image_info_timestamp")
                imgui.dummy((0, 0))
                imgui.image(icon, (h, h))
                imgui.same_line()
                imgui.text(datetime.fromtimestamp(self.item.timestamp).strftime("%Y-%m-%d %H:%M:%S"))
                imgui.dummy((0, 0))
                # 复制/导出
                fp = imgui.get_style().frame_padding
                imgui.push_style_var_x(imgui.StyleVar.ITEM_SPACING, fp[0])
                aw = imgui.get_content_region_avail()
                bw = (aw[0] - fp[0]) * 0.5

                if CustomWidgets.icon_label_button("prompt_copy", "复制", "CENTER", (bw, 0)):
                    self.copy_image()
                imgui.same_line()
                if CustomWidgets.icon_label_button("image_export", "导出", "CENTER", (bw, 0)):
                    self.export_image()
                imgui.pop_style_var()

            imgui.pop_style_color(1)
        imgui.pop_style_color(1)

    def copy_image(self):
        image_path = self.item.output_file

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

    def export_image(self):
        def export_image_callback(file_path: str):
            copyfile(self.item.output_file, file_path)
            print("导出图片到：", file_path)

        from .ops import FileCallbackRegistry

        callback_id = FileCallbackRegistry.register_callback(export_image_callback)
        bpy.ops.bas.file_exporter("INVOKE_DEFAULT", callback_id=callback_id)


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
    HISTORY = "history"


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
        imgui.push_style_var(imgui.StyleVar.WINDOW_PADDING, Const.LP_WINDOW_P)
        imgui.push_style_var(imgui.StyleVar.WINDOW_ROUNDING, Const.WINDOW_R)

        imgui.push_style_color(imgui.Col.WINDOW_BG, Const.RP_L_BOX_BG)
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.MODAL_WINDOW_DIM_BG, Const.MODAL_WINDOW_DIM_BG)

        self.draw_redeem()
        self.draw_redeem_confirm()
        self.draw_redeem_ok()
        self.draw_redeem_error()

        imgui.pop_style_var(2)
        imgui.pop_style_color(5)

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
                imgui.button("使用兑换券")
                imgui.pop_style_var(1)
                imgui.same_line()

                icon = TexturePool.get_tex_id("settings_header")
                tex = TexturePool.get_tex(icon)
                scale = imgui.get_text_line_height() / tex.height
                imgui.image_button("Redeem", icon, (tex.width * scale, tex.height * scale), tint_col=Const.BUTTON_SELECTED)
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
            imgui.text("请输入兑换码")
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
                if imgui.button("兑换", (101, 0)):
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
                imgui.button("确认兑换？")
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
            redeem_value = self.get_redeem_value()
            imgui.text(f"兑换后，您将获得{redeem_value}冰糕(积分)")
            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))

            imgui.table_next_column()
            if imgui.button("确定", (101, 0)):
                imgui.close_current_popup()
                self.should_draw_redeem_confirm = False
                if self.is_redeem_code_valid():
                    self.should_draw_redeem_success = True
                    print("兑换成功")
                else:
                    self.should_draw_redeem_error = True
                    print("兑换码无效")

            self.draw_redeem_ok()
            self.draw_redeem_error()

            imgui.same_line()

            if imgui.button("取消", (101, 0)):
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
                imgui.button("兑换成功~")
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
            redeem_value = self.get_redeem_value()
            imgui.text(f"您已获得{redeem_value}冰糕(积分)，注意刷新")
            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            if imgui.button("知道啦"):
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
                imgui.button("兑换失败~QAQ")
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

            imgui.text("兑换码错误或已被使用，请检查或联系客服")
            if imgui.button("退出", (101, 0)):
                imgui.close_current_popup()
                self.clear_redeem()
            imgui.end_popup()

    def get_redeem_value(self) -> int:
        if not self.is_redeem_code_valid():
            return 0
        pat = "BG([0-9]{3})-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12}"
        try:
            redeem_value = int(re.match(pat, self.redeem_code).group(1))
        except Exception:
            redeem_value = 0
        return redeem_value

    def is_redeem_code_valid(self) -> bool:
        pat = "BG[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12}"
        return bool(re.match(pat, self.redeem_code))


class ErrorLogBubble:
    def __init__(
        self,
        anim_system: AnimationSystem,
        text: str,
        pos: tuple[float, float] = (0, 0),
        duration: float = 3,
    ) -> None:
        self.text = text
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

        icon = TexturePool.get_tex_id("account_warning")
        p_min = x, y + (content_size[1] - icon_size) / 2
        p_max = p_min[0] + icon_size, p_min[1] + icon_size
        dl.add_image(icon, p_min, p_max, col=icon_col)

        dl.add_text((x + spacing + icon_size, y), text_col, self.text)


class ErrorLog:
    def __init__(self, app: "AIStudio") -> None:
        self.app = app
        self.animation_system = app.animation_system
        self.error_bubbles: dict[str, ErrorLogBubble] = {}
        self.error_messages: list[str] = []

    def push_error_message(self, message: str):
        self.error_messages.append(message)

    def draw_and_update(self):
        while self.error_messages:
            msg = self.error_messages.pop()
            bubble = ErrorLogBubble(self.animation_system, msg)
            self.error_bubbles[msg] = bubble
        for message, bubble in list(self.error_bubbles.items()):
            if bubble.is_alive:
                bubble.draw(self.app)
            else:
                self.error_bubbles.pop(message)


class AIStudio(AppHud):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_panel = AIStudioPanelType.GENERATION
        self.state = Account.get_instance()
        self.clients = {c.VENDOR: c() for c in StudioClient.__subclasses__()}
        # self.fill_fake_clients()
        self.redeem_panel = RedeemPanel(self)
        self.active_client = next(iter(self.clients)) if self.clients else ""
        self.clients_wrappers: dict[str, StudioWrapper] = {}
        self.error_log = ErrorLog(self)
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

    def get_active_client(self) -> StudioClient:
        return self.clients.get(self.active_client, StudioClient())

    def push_error_message(self, message: str):
        self.error_log.push_error_message(message)

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
                    imgui.button(f"V{'.'.join(map(str, get_version()))}")
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
        active_client = self.get_active_client()
        for error in active_client.take_errors():
            self.push_error_message(str(error))
        for error in self.state.take_errors():
            self.push_error_message(str(error))
        self.error_log.draw_and_update()

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

        # 生成面板
        imgui.dummy(dummy_size)
        if imgui.begin_table("#Engine", 4):
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
                wrapper = self.clients_wrappers.get(self.active_client, StudioWrapper())
                for widget in wrapper.get_widgets_by_category("Input"):
                    widget.col_bg = Const.WINDOW_BG
                    widget.col_widget = Const.FRAME_BG
                    widget.display_begin(widget, self)
                    widget.display(widget, self)
                    self.draw_wrapper_widget_spec(wrapper, widget)
                    widget.display_end(widget, self)
                client = wrapper.studio_client
                if client.history.items:
                    item = client.history.items[0]
                    viewer = StudioHistoryItemViewer(item)
                    viewer.draw(self)
            imgui.pop_style_color()

            # 底部按钮
            if True:
                imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.6)
                imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, 15)
                full_width = imgui.get_content_region_avail()[0]
                self.font_manager.push_h1_font()
                client = self.get_active_client()
                status = client.query_task_status()
                # 按钮状态:
                #   1. 无状态
                #   2. 正在提交
                #   3. 正在渲染
                #   4. 停止渲染
                # "running", "processing"
                task_state: TaskState = status.get("state", "")
                is_rendering = False
                show_stop_btn = False
                label = "  开始AI渲染"
                if client.is_task_submitting:
                    label = "  任务提交中"
                if task_state == "running":
                    is_rendering = True
                    elapsed_time = client.query_task_elapsed_time()
                    label = f"  渲染中({elapsed_time:.1f})s"
                    rmin = imgui.get_cursor_screen_pos()
                    rmax = (rmin[0] + full_width, rmin[1] + gen_btn_height)
                    if imgui.is_mouse_hovering_rect(rmin, rmax):
                        label = "  停止AI渲染"
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
                        client.new_generate_task(self.state)
                    elif show_stop_btn:
                        client.cancel_generate_task()

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
            items = list(self.clients)
            max_item_width = 0
            for item in items:
                max_item_width = max(max_item_width, imgui.calc_text_size(item)[0])
            max_item_width += 2 * imgui.get_style().frame_padding[0]
            aw = imgui.get_content_region_avail()[0]
            max_item_width = max(aw, max_item_width)
            if imgui.begin_combo("##Item", self.active_client):
                for item in items:
                    is_selected = self.active_client == item
                    if is_selected:
                        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
                    if imgui.button(item, (max_item_width, 0)):
                        self.active_client = item
                        imgui.close_current_popup()
                    if is_selected:
                        imgui.pop_style_color()
                imgui.end_combo()
            if imgui.is_item_hovered():
                title = "选择生成式引擎"
                tip = "选择引擎并填写API，即可无缝在Blender中使用AI.注意：本工具仅具备连接服务功能，生成内容&费用以API提供方为准."
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
            imgui.button("历史")
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
            imgui.text("队列")
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
                for item in history.items:
                    viewer = StudioHistoryItemViewer(item)
                    viewer.draw(self)
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

        # 设置面板
        imgui.dummy(dummy_size)
        if imgui.begin_table("#Engine", 4):
            imgui.table_setup_column("#EngineEle1", imgui.TableColumnFlags.WIDTH_FIXED, 0, 0)
            imgui.table_setup_column("#EngineEle2", imgui.TableColumnFlags.WIDTH_FIXED, 0, 1)
            imgui.table_setup_column("#EngineEle3", imgui.TableColumnFlags.WIDTH_STRETCH, 0, 2)
            imgui.table_setup_column("#EngineEle4", imgui.TableColumnFlags.WIDTH_FIXED, 0, 3)
            imgui.table_next_column()
            self.font_manager.push_h2_font()
            imgui.text("服务")
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
            imgui.text("免责声明")
            imgui.text("反馈问题")
            imgui.text("交流群")
            self.font_manager.pop_font()
            imgui.pop_style_var()

        imgui.pop_style_var(2)

    def draw_account_panel(self):
        if self.state.auth_mode != AuthMode.ACCOUNT:
            return
        self.draw_login_panel()
        self.draw_setting_account()

    def draw_login_panel(self):
        if self.state.is_logged_in():
            return
        flags = 0
        flags |= imgui.ChildFlags.FRAME_STYLE
        flags |= imgui.ChildFlags.AUTO_RESIZE_Y
        flags |= imgui.ChildFlags.ALWAYS_AUTO_RESIZE

        with with_child("##Login", (0, 0), child_flags=flags):
            self.font_manager.push_h3_font()
            bh = imgui.get_text_line_height_with_spacing() * 2
            if imgui.button("登录/注册", (-imgui.FLOAT_MIN, bh)):
                self.state.login()
            self.font_manager.pop_font()
        # --- 底部: 警告信息 (单行全宽) ---
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.WINDOW_BG)
        isize = 24
        CustomWidgets.icon_label_button("account_warning", "使用此服务，可支援工具开发", "CENTER", (0, 54), isize)
        imgui.pop_style_color(3)

    def draw_help_button(self):
        help_url = self.get_active_client().help_url
        if not help_url:
            return
        imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.75)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        self.font_manager.push_h1_font(24)
        label = " 帮助"
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
        help_url = self.get_active_client().help_url
        if not help_url:
            return
        imgui.push_style_var_x(imgui.StyleVar.BUTTON_TEXT_ALIGN, 0.75)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.CHILD_R)
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_color(imgui.Col.TEXT, Const.BUTTON_SELECTED)

        self.font_manager.push_h1_font(24)
        label = "缓存目录"
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
            if imgui.begin_combo("##Item", self.state.auth_mode.value):
                for item in items:
                    is_selected = self.state.auth_mode == item
                    if is_selected:
                        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
                    if imgui.button(item.value, (aw, 0)):
                        self.state.auth_mode = item
                        imgui.close_current_popup()
                    if is_selected:
                        imgui.pop_style_color()
                imgui.end_combo()
            imgui.pop_style_color(2)
            imgui.pop_style_var(4)
            imgui.pop_item_width()
        imgui.pop_style_color(1)

    def draw_setting_account(self):
        if not self.state.is_logged_in():
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
            CustomWidgets.icon_label_button("account_email", self.state.acount_name, "BETWEEN", (bw, bh), isize, fpx * 2)
            imgui.same_line()
            if CustomWidgets.icon_label_button("account_logout", "", "CENTER", (bh, bh), isize):
                self.state.logout()

            # --- 表格 2: Token + 刷新
            bw = aw - bh - imgui.get_style().item_spacing[0]
            CustomWidgets.icon_label_button("account_token", str(self.state.credits), "BETWEEN", (bw, bh), isize, fpx * 2)
            imgui.same_line()
            if CustomWidgets.icon_label_button("account_refresh", "", "CENTER", (bh, bh), isize):
                print("刷新 Token")

            # --- 表格 3: 功能按钮 (50% + 50%) ---
            bw = (aw - imgui.get_style().item_spacing[0]) * 0.5
            if CustomWidgets.icon_label_button("account_buy", "获取冰糕", "CENTER", (bw, bh), isize):
                print("获取冰糕")
                imgui.open_popup("##Buy")
            self.draw_buy()
            imgui.same_line()
            if CustomWidgets.icon_label_button("account_certificate", "兑换冰糕", "CENTER", (bw, bh), isize):
                self.redeem_panel.should_draw_redeem = True
            self.redeem_panel.draw()
            imgui.pop_style_var(2)

        # --- 底部: 警告信息 (单行全宽) ---
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.WINDOW_BG)
        CustomWidgets.icon_label_button("account_warning", "收益将 100% 用于支持开源开发", "CENTER", (0, 54), isize)
        imgui.pop_style_color(3)

    def draw_api_panel(self):
        if self.state.auth_mode != AuthMode.API:
            return
        imgui.push_style_color(imgui.Col.BUTTON, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.WINDOW_BG)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.WINDOW_BG)
        isize = 24
        self.font_manager.push_h3_font(20)
        CustomWidgets.icon_label_button("account_warning", "服务由API方提供，注意网络畅通", "CENTER", (0, 54), isize)
        self.font_manager.pop_font()
        imgui.pop_style_color(3)
        flags = imgui.ChildFlags.FRAME_STYLE | imgui.ChildFlags.AUTO_RESIZE_Y
        with with_child("Outer", (0, 0), flags):
            for wrapper in self.clients_wrappers.values():
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
                        bh = 44
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
                            print("Help")
                        imgui.pop_style_color(1)

                    imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, imgui.get_style().frame_rounding * 0.5)
                    for widget in widgets:
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
            title = "首图模式"
            tips = [
                "活动相机将被用于输出，请选择输出输出模式。",
                "相机渲染=合并结果",
                "相机深度=雾场（雾场效果可在世界环境>雾场通道设置）",
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
                title = "提示词优化"
                tip = "启用提示词优化，可提升描述准确性，以及生成内容的安全性"
                AppHelperDraw.draw_tips_with_title(self, [tip], title)
            imgui.end_child()
            imgui.set_cursor_pos(pos)
            return
        if widget.widget_name == "size_config":
            if imgui.is_item_hovered():
                imgui.set_next_window_size((450, 0))
                title = "图像比例"
                tip = "设置生成图像的长宽比，以满足生成需求"
                AppHelperDraw.draw_tips_with_title(self, [tip], title)
            return
        if widget.widget_name == "resolution":
            if imgui.is_item_hovered():
                imgui.set_next_window_size((710, 0))
                title = "图像分辨率"
                tip = "结合图像比例，设置分辨率，分辨率越大需要更多的生成时间/资源"
                AppHelperDraw.draw_tips_with_title(self, [tip], title)
            return

    def draw_buy(self):
        window_size = 1680, 713
        hh = get_header_panel_height() / self.screen_scale
        sw = self.screen_width
        sh = self.screen_height
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
                self.font_manager.push_h1_font()

                imgui.push_style_var_y(imgui.StyleVar.FRAME_PADDING, 0)
                imgui.push_style_color(imgui.Col.BUTTON, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.TRANSPARENT)
                imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.TRANSPARENT)
                imgui.button("AIGODLIKE小卖部")
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
                label = "越多人消耗冰糕，未来单次运行消耗的冰糕数越会降低↓"
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
                self.font_manager.pop_font()

            imgui.dummy((0, style.window_padding[0] - style.item_spacing[1] * 2))
            # 购买规格
            products = [
                {
                    "id": "1",
                    "name": "小型尝鲜礼包",
                    "certificate": "[ 冰糕x600 ]",
                    "color": (67 / 255, 207 / 255, 124 / 255, 1),
                    "price": "6",
                },
                {
                    "id": "2",
                    "name": "中型品鉴礼包",
                    "certificate": "[ 冰糕x3300 ]",
                    "color": (42 / 255, 130 / 255, 228 / 255, 1),
                    "price": "30",
                },
                {
                    "id": "3",
                    "name": "大型畅享礼包",
                    "certificate": "[ 冰糕x7200 ]",
                    "color": (121 / 255, 72 / 255, 234 / 255, 1),
                    "price": "60",
                },
                {
                    "id": "4",
                    "name": "巨型豪华礼包",
                    "certificate": "[ 冰糕x13000 ]",
                    "color": (255 / 255, 195 / 255, 0 / 255, 1),
                    "price": "100",
                },
            ]
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

        tex = TexturePool.get_tex_id(f"product_card_{product}_gray")
        if hovered:
            tex = TexturePool.get_tex_id(f"product_card_{product}")

        pmin = imgui.get_item_rect_min()
        pmax = imgui.get_item_rect_max()
        dl.add_image_rounded(tex, pmin, pmax, (0, 0), (1, 1), 0xFFFFFFFF, style.frame_rounding * 2)

        imgui.set_cursor_pos((screen_pos[0] + style.frame_padding[0], screen_pos[1] + style.frame_padding[1]))
        col = imgui.get_color_u32((1, 1, 1, 1))
        # 信息1
        if True:
            label = name
            self.font_manager.push_h1_font(24)
            label_width = imgui.calc_text_size(label)[0]
            dl.add_text((screen_pos[0] + (aw - label_width) * 0.5, screen_pos[1] + 400), col, label)
            self.font_manager.pop_font()
        # 信息2
        if True:
            label = cert
            self.font_manager.push_h1_font(36)
            label_width = imgui.calc_text_size(label)[0]
            dl.add_text((screen_pos[0] + (aw - label_width) * 0.5, screen_pos[1] + 447), col, label)
            self.font_manager.pop_font()

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
            self.font_manager.push_h1_font(30)
            lw, lh = imgui.calc_text_size(label)
            col = imgui.get_color_u32((1, 1, 1, 1))
            dl.add_text((pmin[0] + (aw - lw) * 0.5, pmax[1] - 70 + (70 - lh) * 0.5), col, label)
            self.font_manager.pop_font()

        imgui.end_group()
        imgui.pop_id()
        return clicked

    def buy_product(self, product: dict):
        print(f"购买 {product['name']}")

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
