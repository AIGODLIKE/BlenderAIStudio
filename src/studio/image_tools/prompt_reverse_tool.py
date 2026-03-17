from bpy.app.translations import pgettext_iface as iface
from typing import TYPE_CHECKING

from .base import ImageTool, ToolState
from ...timer import Timer

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


class PromptReverseTool(ImageTool):
    """对参考图执行提示词反求，结果追加到提示词输入框"""

    _running: dict[str, bool] = {}

    @property
    def name(self) -> str:
        return "prompt_reverse"

    @property
    def display_name(self) -> str:
        return "反求提示词"

    @property
    def icon(self) -> str:
        return "prompt_reverse"

    @property
    def tooltips(self) -> list[str]:
        return [
            "消耗积分反求当前参考图的提示词",
            "并添加到提示词末尾",
        ]

    def get_state(self, wrapper: "StudioWrapper") -> ToolState:
        if self._running.get(wrapper.model_name, False):
            return ToolState.RUNNING
        return ToolState.IDLE

    def execute(
        self,
        image_path: str,
        image_index: int,
        images: list[str],
        wrapper: "StudioWrapper",
        app: "AIStudio",
    ) -> None:
        if not app.state.is_logged_in():
            app.push_error_message(iface("Please login first"))
            return

        model_name = wrapper.model_name
        if self._running.get(model_name, False):
            app.push_info_message(iface("Prompt reverse is already running, ignore click"))
            return

        self._running[model_name] = True
        manager = app.state.prompt_reverse_manager
        prompt_widget = self._find_prompt_widget(wrapper)

        def _on_success(content: str):
            def _append():
                self._running[model_name] = False
                if not content or prompt_widget is None:
                    return
                current = prompt_widget.value
                prompt_widget.value = current.rstrip() + " " + content if current.strip() else content

            Timer.put(_append)

        def _on_error(msg: str):
            def _show():
                self._running[model_name] = False
                app.push_error_message(msg)

            Timer.put(_show)

        manager.submit_task(
            image_path=image_path,
            on_success=_on_success,
            on_error=_on_error,
            prompt="",
        )
        app.push_info_message(iface("Prompt reverse task submitted, please wait..."))

    @staticmethod
    def _find_prompt_widget(wrapper: "StudioWrapper"):
        """从 wrapper 中查找 prompt 控件"""
        for widget in wrapper.get_widgets_by_category("Input"):
            if widget.widget_name == "prompt":
                return widget
        return None
