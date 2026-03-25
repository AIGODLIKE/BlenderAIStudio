import bpy
import math

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from ..gui.app.renderer import imgui
from ..gui.app.style import Const
from ..gui.widgets import CustomWidgets
from ...utils.image_processor import ImageProcessor
from ...utils import get_image_size, calc_appropriate_aspect_ratio, calc_appropriate_resolution
if TYPE_CHECKING:
    from ..studio import AIStudio


COST_PER_RUN = 6
FOOTER_ICON_BTN_WIDTH = 68
FOOTER_ICON_BTN_HEIGHT = 56


@dataclass
class TextEditRow:
    original: str = ""
    replacement: str = ""


class EditTextPanel:
    def __init__(self):
        self._visible: bool = False
        self._pending_open: bool = False
        self._image_path: str = ""
        self._rows: list[TextEditRow] = []
        self._ocr_loading: bool = False

    @property
    def visible(self) -> bool:
        return self._visible

    def open(self, image_path: str):
        self._image_path = image_path
        self._rows = []
        self._pending_open = True

    def close(self):
        self._visible = False
        self._rows.clear()
        self._image_path = ""

    def _add_empty_row(self):
        self._rows.append(TextEditRow())

    def _add_content_row(self, content: str):
        row = TextEditRow()
        row.original = content
        self._rows.append(row)

    def _request_ocr(self, app: "AIStudio", image_path: str):
        if self._ocr_loading:
            app.push_info_message("OCR is already running")
            return
        self._ocr_loading = True
        # 压缩图片
        image_path = ImageProcessor.compress_image_to_tempfile(image_path)
        if not image_path:
            app.push_info_message("Failed to compress image")
            self._ocr_loading = False
            return

        client = app.client

        old_model_name = client.current_model_name
        client.current_model_name = "API"
        item, _task = client.add_ocr_task(image_path, app.state)
        client.current_model_name = old_model_name

        def read_text_to_string(text_file: str) -> str:
            encodings = ["utf-8", "gbk", "gb2312", "gb18030", "utf-16", "utf-32"]
            path = Path(text_file)
            if not path.exists():
                return ""
            for encoding in encodings:
                try:
                    return path.read_text(encoding)
                except UnicodeDecodeError:
                    continue
            return ""

        def _poll_job():
            if item and not item.is_finished():
                return 1.0
            self._ocr_loading = False
            text_file = item.get_output_file_text()
            text = read_text_to_string(text_file)
            if not text:
                return
            for output in text.split("\n"):
                if not output.strip():
                    continue
                self._add_content_row(output.strip())

        bpy.app.timers.register(_poll_job)

    def draw(self, app: "AIStudio"):
        popup_id = "##EditTextPanel"
        if self._pending_open:
            imgui.open_popup(popup_id)
            self._pending_open = False

        imgui.set_next_window_size((720 * Const.SCALE, 0), imgui.Cond.ALWAYS)

        flags = imgui.WindowFlags.NO_RESIZE
        flags |= imgui.WindowFlags.NO_COLLAPSE
        flags |= imgui.WindowFlags.NO_TITLE_BAR
        flags |= imgui.WindowFlags.NO_SAVED_SETTINGS
        imgui.push_style_var(imgui.StyleVar.FRAME_PADDING, Const.FRAME_P)
        imgui.push_style_var(imgui.StyleVar.ITEM_SPACING, Const.ITEM_S)
        imgui.push_style_color(imgui.Col.MODAL_WINDOW_DIM_BG, Const.MODAL_WINDOW_DIM_BG)
        if imgui.begin_popup_modal(popup_id, False, flags)[0]:
            self._visible = True
            self._draw_column_headers()
            self._draw_rows()
            self._draw_footer(app)
            imgui.end_popup()
        else:
            self._visible = False
        imgui.pop_style_var(2)
        imgui.pop_style_color(1)

    def _calc_col_width(self):
        avail_w = imgui.get_content_region_avail()[0]
        btn_h = self._calc_item_height()
        pair_w = avail_w - btn_h - imgui.get_style().item_spacing[0] * 2
        return pair_w * 0.5

    def _calc_item_height(self):
        return imgui.get_text_line_height() + imgui.get_style().frame_padding[1] * 2

    def _draw_column_headers(self):
        imgui.push_style_color(imgui.Col.TEXT, Const.GRAY)

        imgui.text("修改前")
        imgui.same_line(self._calc_col_width() + imgui.get_style().item_spacing[0] * 2)
        imgui.text("修改后")

        imgui.pop_style_color()

    def _draw_rows(self):
        mlt_flags = imgui.InputTextFlags.WORD_WRAP
        card_r = Const.RP_FRAME_INNER_R

        remove_idx = -1
        for i, row in enumerate(self._rows):
            imgui.push_id(f"##editrow_{i}")

            imgui.push_style_color(imgui.Col.FRAME_BG, Const.FRAME_BG)
            imgui.push_style_var(imgui.StyleVar.SCROLLBAR_SIZE, 0)
            imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, card_r)

            col_w = self._calc_col_width()
            btn_h = self._calc_item_height()
            orig_h = self._calc_multiline_height(row.original, col_w)
            repl_h = self._calc_multiline_height(row.replacement, col_w)
            row_h = max(orig_h, repl_h)

            _, row.original = imgui.input_text_multiline("##orig", row.original, (col_w, row_h), mlt_flags)
            imgui.same_line()
            _, row.replacement = imgui.input_text_multiline("##repl", row.replacement, (col_w, row_h), mlt_flags)
            imgui.same_line()

            imgui.push_id(f"close_{i}")
            if self._draw_close_button(btn_h):
                remove_idx = i
            imgui.pop_id()

            imgui.pop_style_var(2)
            imgui.pop_style_color(1)
            imgui.pop_id()

        if remove_idx >= 0:
            _ = self._rows.pop(remove_idx)

    def _calc_multiline_height(self, text: str, col_w: float) -> float:
        style = imgui.get_style()
        fp_x, fp_y = style.frame_padding
        wrap_w = max(1.0, col_w - fp_x - style.scrollbar_size)
        text_h = imgui.calc_text_size(text or " ", wrap_width=wrap_w)[1]
        return text_h + fp_y * 2

    def _draw_close_button(self, btn_h: float) -> bool:
        btn_size = btn_h, btn_h
        img_size = btn_h * 0.7
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
        clicked = CustomWidgets.icon_label_button("image_tools/close", "", "CENTER", btn_size, img_size)
        imgui.pop_style_var(1)
        imgui.pop_style_color(3)
        return clicked

    def _draw_footer(self, app: "AIStudio"):
        iw = imgui.get_style().item_spacing[0]
        avail_w = self._calc_col_width()
        btn_w = (avail_w - iw * 2) / 3
        btn_h = self._calc_item_height()
        btn_size = btn_w, btn_h
        img_size = btn_h * 0.7

        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)

        imgui.push_id("footer_add")
        if CustomWidgets.icon_label_button("image_tools/add", "", "CENTER", btn_size, img_size):
            self._add_empty_row()
        if imgui.is_item_hovered():
            imgui.set_tooltip("新建一行")
        imgui.pop_id()

        imgui.same_line()
        imgui.push_id("footer_paste")
        if CustomWidgets.icon_label_button("image_tools/copy", "", "CENTER", btn_size, img_size):
            # 粘贴结果
            content = bpy.context.window_manager.clipboard or ""
            for slice in content.split("\n"):
                if not slice.strip():
                    continue
                self._add_content_row(slice.strip())
            if not content:
                app.push_error_message("Clipboard is Empty!")
        if imgui.is_item_hovered():
            imgui.set_tooltip("从剪贴板粘贴识别结果")
        imgui.pop_id()

        imgui.same_line()
        imgui.push_id("footer_ocr")
        if CustomWidgets.icon_label_button("image_tools/ocr", "", "CENTER", btn_size, img_size):
            self._request_ocr(app, self._image_path)
        if self._ocr_loading:
            pmin = imgui.get_item_rect_min()
            pmax = imgui.get_item_rect_max()
            dl = imgui.get_window_draw_list()
            self._display_prompt_reverse_running_effect(pmin, pmax, dl)
        if imgui.is_item_hovered():
            imgui.set_tooltip("OCR 识别")
        imgui.pop_id()

        imgui.pop_style_color(3)
        imgui.same_line()

        self._draw_run_button(app, avail_w, btn_h)
        imgui.same_line()
        self._draw_cancel_button()

        imgui.pop_style_var(1)

    def _display_prompt_reverse_running_effect(self, pmin, pmax, dl: imgui.DrawList):
        cx = (pmin[0] + pmax[0]) * 0.5
        cy = (pmin[1] + pmax[1]) * 0.5
        radius = (pmax[0] - pmin[0]) * 0.25
        t = imgui.get_time()
        start_angle = t * 4.0
        end_angle = start_angle + math.pi * 1.5
        col = imgui.get_color_u32((1.0, 1.0, 1.0, 0.9))
        dl.path_clear()
        dl.path_arc_to((cx, cy), radius, start_angle, end_angle, 32)
        dl.path_stroke(col, 0, 3.0)

    def _draw_run_button(self, app: "AIStudio", w: float, h: float):
        has_content = any(r.original.strip() or r.replacement.strip() for r in self._rows)
        if has_content:
            imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON_ACTIVE)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.CLOSE_BUTTON_HOVERED)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_SELECTED)
        else:
            imgui.push_style_color(imgui.Col.BUTTON, Const.GRAY)
            imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.GRAY)
            imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.GRAY)

        label = f"运行({COST_PER_RUN}/次)"
        app.font_manager.push_h1_font(24)
        if imgui.button(label, (w, h)):
            if has_content:
                self._apply_edits(app)
                imgui.close_current_popup()
                self.close()
            else:
                app.push_error_message("替换项错误或无替换项")
        app.font_manager.pop_font()
        imgui.pop_style_color(3)

    def _draw_cancel_button(self):
        btn_h = self._calc_item_height()
        btn_size = btn_h, btn_h
        img_size = btn_h * 0.7
        imgui.push_id("footer_cancel")
        imgui.push_style_color(imgui.Col.BUTTON, Const.BUTTON)
        imgui.push_style_color(imgui.Col.BUTTON_HOVERED, Const.BUTTON_HOVERED)
        imgui.push_style_color(imgui.Col.BUTTON_ACTIVE, Const.BUTTON_ACTIVE)
        imgui.push_style_var(imgui.StyleVar.FRAME_ROUNDING, Const.RP_FRAME_INNER_R)
        clicked = CustomWidgets.icon_label_button("image_tools/exit", "", "CENTER", btn_size, img_size)
        imgui.pop_style_var(1)
        imgui.pop_style_color(3)
        imgui.pop_id()

        if clicked:
            imgui.close_current_popup()
            self.close()

    def _apply_edits(self, app: "AIStudio"):
        edits = self.get_edit_results()
        # 1. 拼接
        prompt = ",".join([f'将图片中的文本"{e0}"替换成"{e1}"' for e0, e1 in edits])
        # 2. 添加
        if not prompt:
            app.push_error_message("Prompt is Empty!")
            return

        img_size = get_image_size(self._image_path)
        if not img_size:
            app.push_error_message("Image Parse Error")
            return
        aspect_ration = calc_appropriate_aspect_ratio(*img_size)
        resolution = calc_appropriate_resolution(*img_size)
        original_model = app.client.current_model_name
        app.client.current_model_name = "NanoBananaPro"
        app.client.add_edit_text_task(
            prompt,
            app.state,
            [self._image_path],
            aspect_ration,
            resolution,
        )
        app.client.current_model_name = original_model

    def get_edit_results(self) -> list[tuple[str, str]]:
        return [(r.original, r.replacement) for r in self._rows if r.original.strip() or r.replacement.strip()]
