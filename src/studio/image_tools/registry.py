from .base import ImageTool


class ImageToolRegistry:
    """参考图工具注册表

    统一管理所有 ImageTool 实例，保证注册顺序即为菜单显示顺序。
    """

    _tools: list[ImageTool] = []

    @classmethod
    def register(cls, tool: ImageTool) -> None:
        if any(t.name == tool.name for t in cls._tools):
            return
        cls._tools.append(tool)

    @classmethod
    def get_tools(cls) -> list[ImageTool]:
        return list(cls._tools)

    @classmethod
    def clear(cls) -> None:
        cls._tools.clear()
