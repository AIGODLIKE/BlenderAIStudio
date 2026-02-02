import bpy
import time
import tempfile
from contextlib import contextmanager
from pathlib import Path
from traceback import print_exc
from uuid import uuid4
from bpy.app.translations import pgettext as _T
from ..timer import Timer
from ..utils import get_temp_folder

from .. import logger


def check_scene_camera_with_exception(scene: bpy.types.Scene):
    if scene.camera:
        return
    raise Exception(_T("No Camera in Scene") + " -> " + scene.name)


@contextmanager
def with_scene_render_output_settings(scene: bpy.types.Scene, image_path: str):
    render = scene.render
    old = render.filepath
    old_fmt = render.image_settings.file_format
    render.filepath = image_path
    if bpy.app.version >= (5, 0):
        old_media_type = render.image_settings.media_type
        render.image_settings.media_type = "IMAGE"
    render.image_settings.file_format = "PNG"

    last_display_type = bpy.context.preferences.view.render_display_type  # 渲染不弹出
    bpy.context.preferences.view.render_display_type = "NONE"
    try:
        yield
    finally:
        render.filepath = old
        if bpy.app.version >= (5, 0):
            render.image_settings.media_type = old_media_type
        render.image_settings.file_format = old_fmt
        bpy.context.preferences.view.render_display_type = last_display_type


@contextmanager
def silent_rendering():
    last_display_type = bpy.context.preferences.view.render_display_type  # 渲染不弹出
    bpy.context.preferences.view.render_display_type = "NONE"
    try:
        yield
    finally:
        if hasattr(bpy.context.preferences.view, "render_display_type"):
            setattr(bpy.context.preferences.view, "render_display_type", last_display_type)


def render_scene_viewport_opengl_to_png(context: dict, image_path: str):
    scene: bpy.types.Scene = context["scene"]
    space_data: bpy.types.SpaceView3D = context["space_data"]
    check_scene_camera_with_exception(scene)
    with bpy.context.temp_override(**context):
        with with_scene_render_output_settings(scene, image_path):
            old_engine = scene.render.engine
            old_show_overlays = space_data.overlay.show_overlays
            for engine in ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "EEVEE"]:
                try:
                    scene.render.engine = engine
                    break
                except Exception:
                    continue
            space_data.overlay.show_overlays = False
            bpy.ops.render.opengl(write_still=True, view_context=True)
            scene.render.engine = old_engine
            space_data.overlay.show_overlays = old_show_overlays
    return image_path


def render_scene_to_png(scene: bpy.types.Scene, image_path: str):
    check_scene_camera_with_exception(scene)
    render = scene.render
    old = render.filepath
    old_fmt = render.image_settings.file_format

    render.filepath = image_path
    if bpy.app.version >= (5, 0):
        old_media_type = render.image_settings.media_type
        render.image_settings.media_type = "IMAGE"
    render.image_settings.file_format = "PNG"

    def restore():
        logger.info("restore render setting")
        ren = scene.render
        setattr(ren, "filepath", old)
        if bpy.app.version >= (5, 0):
            setattr(ren.image_settings, "media_type", old_media_type)
        setattr(ren.image_settings, "file_format", old_fmt)

    def on_finish(_sce):
        bpy.app.timers.register(restore, first_interval=5, persistent=False)
        bpy.app.handlers.render_complete.remove(on_finish)

    bpy.app.handlers.render_complete.append(on_finish)
    with silent_rendering():
        bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)


def render_scene_depth_to_png(scene: bpy.types.Scene, image_path: str):
    """
    渲染相机视角下的深度图
    """
    check_scene_camera_with_exception(scene)
    bpy.context.view_layer.use_pass_mist = True
    old_tree = get_comp_node_tree(scene)
    ensure_comp_node_tree(scene)
    tree: bpy.types.NodeTree = get_comp_node_tree(scene)

    for node in tree.nodes:
        tree.nodes.remove(node)

    render_layer = tree.nodes.new(type="CompositorNodeRLayers")
    if bpy.app.version >= (5, 0):
        output = tree.nodes.new(type="NodeGroupOutput")
        tree.interface.new_socket(name="Output", in_out="OUTPUT", socket_type="NodeSocketColor")
        tree.links.new(render_layer.outputs["Mist"], output.inputs[0])
    else:
        output = tree.nodes.new(type="CompositorNodeComposite")
        tree.links.new(render_layer.outputs["Mist"], output.inputs["Image"])
    render = scene.render
    old_filepath = render.filepath
    old_fmt = render.image_settings.file_format

    render.filepath = image_path
    if bpy.app.version >= (5, 0):
        old_media_type = render.image_settings.media_type
        render.image_settings.media_type = "IMAGE"
    render.image_settings.file_format = "PNG"

    def restore():
        logger.info("restore render setting")
        ren = scene.render
        setattr(ren, "filepath", old_filepath)
        setattr(ren.image_settings, "file_format", old_fmt)
        if bpy.app.version >= (5, 0):
            setattr(ren.image_settings, "media_type", old_media_type)
            setattr(scene, "compositing_node_group", old_tree)
            bpy.data.node_groups.remove(tree)

    def on_finish(_sce):
        bpy.app.timers.register(restore, first_interval=5, persistent=False)
        bpy.app.handlers.render_complete.remove(on_finish)

    bpy.app.handlers.render_complete.append(on_finish)
    with silent_rendering():
        bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)


def ensure_comp_node_tree(sce: bpy.types.Scene):
    if bpy.app.version >= (5, 0):
        tree = bpy.data.node_groups.new("Render Layers" + uuid4().hex, "CompositorNodeTree")
        sce.compositing_node_group = tree
    else:
        sce.use_nodes = True


def get_comp_node_tree(sce: bpy.types.Scene) -> bpy.types.CompositorNodeTree:
    """获取合成节点树"""
    if bpy.app.version >= (5, 0):
        return sce.compositing_node_group
    return sce.node_tree


def check_image_valid(image_path: str) -> bool:
    """验证图片是否有效
    如果图片无法加载或是加载的宽或高为0
    那么这个图片就是错误的
    """
    try:
        image = bpy.data.images.load(image_path, check_existing=True)
        w, h = image.size[:]
        if w == 0 or h == 0:
            return False
        bpy.data.images.remove(image)
        return True
    except Exception as e:
        print(e.args)
        return False


class RenderAgent:
    def __init__(self):
        self._cancel_cb = None
        self._complete_cb = None
        self._post_cb = None
        self._write_cb = None

    def clear_callbacks(self):
        self._cancel_cb = None
        self._complete_cb = None
        self._post_cb = None
        self._write_cb = None

    def attach(self):
        bpy.app.handlers.render_cancel.append(self._cancel)
        bpy.app.handlers.render_complete.append(self._complete)
        bpy.app.handlers.render_post.append(self._post)
        bpy.app.handlers.render_write.append(self._write)

    def detach(self):
        if self._cancel in bpy.app.handlers.render_cancel:
            bpy.app.handlers.render_cancel.remove(self._cancel)
        if self._complete in bpy.app.handlers.render_complete:
            bpy.app.handlers.render_complete.remove(self._complete)
        if self._post in bpy.app.handlers.render_post:
            bpy.app.handlers.render_post.remove(self._post)
        if self._write in bpy.app.handlers.render_write:
            bpy.app.handlers.render_write.remove(self._write)
        self.clear_callbacks()

    def on_cancel(self, cb):
        self._cancel_cb = cb

    def on_complete(self, cb):
        self._complete_cb = cb

    def on_post(self, cb):
        self._post_cb = cb

    def on_write(self, cb):
        self._write_cb = cb

    def _cancel(self, sce, _):
        if self._cancel_cb:
            try:
                self._cancel_cb(sce)
            except Exception:
                print_exc()
        self.detach()

    def _complete(self, sce, _):
        if self._complete_cb:
            try:
                self._complete_cb(sce)
            except Exception:
                print_exc()
        self.detach()

    def _post(self, sce, _):
        if self._post_cb:
            try:
                self._post_cb(sce)
            except Exception:
                print_exc()

    def _write(self, sce, _):
        if self._write_cb:
            try:
                self._write_cb(sce)
            except Exception:
                print_exc()
        self.detach()


class BlenderRenderHelper:
    """
    渲染辅助工具
    负责根据 itype 渲染 Blender 场景，返回渲染结果路径。
    """

    def __init__(self):
        self.is_rendering = False
        self.render_cancel = False
        self.rendering_time_start = 0

    def cancel(self):
        self.render_cancel = True

    def render(self, itype: str, context: dict) -> str:
        """根据类型渲染场景

        Args:
            itype: 输入图像类型
                - CameraRender: 从相机渲染
                - CameraDepth: 从相机深度渲染
                - FastRender: 快速渲染
                - NoInput: 不渲染，返回空字符串

        Returns:
            渲染结果的文件路径，如果不需要渲染则返回空字符串

        Raises:
            ValueError: 场景没有相机
            RuntimeError: 渲染失败
        """
        if itype == "NoInput":
            return ""

        # 创建临时文件
        temp_folder = get_temp_folder(prefix="generate")
        temp_image_path = tempfile.NamedTemporaryFile(suffix=".png", prefix="Render", delete=False, dir=temp_folder)
        image_path = temp_image_path.name

        if itype == "CameraRender":
            self._wait_for_rendering()
            self._render_camera(image_path, context)
        elif itype == "CameraDepth":
            self._wait_for_rendering()
            self._render_depth(image_path, context)
        elif itype == "FastRender":
            self._wait_for_rendering()
            self._render_opengl_viewport(image_path, context)
        else:
            raise ValueError(f"Unknown input image type: {itype}")

        return image_path

    def _is_other_rendering(self):
        return bpy.app.is_job_running("RENDER")

    def _wait_for_rendering(self):
        """等待渲染完成"""
        if self._is_other_rendering():
            logger.info("Other rendering is running, waiting for completion")
        while self._is_other_rendering():
            time.sleep(0.1)

    def _render_camera(self, output_path: str, context: dict):
        """渲染相机视图"""
        scene: bpy.types.Scene = context["scene"]

        if not scene.camera:
            raise ValueError("Scene Camera Not Found")

        render_agent = RenderAgent()
        self.is_rendering = True
        self.rendering_time_start = time.time()

        def on_write(_sce):
            if not check_image_valid(output_path):
                self.render_cancel = True

            self.is_rendering = False
            render_agent.detach()
            logger.info("Render completed")

        render_agent.on_write(on_write)
        render_agent.attach()
        Timer.put((render_scene_to_png, scene, output_path))

        # 等待渲染完成
        while self.is_rendering:
            time.sleep(0.1)

        # 检查是否取消
        if self.render_cancel:
            self.render_cancel = False
            raise RuntimeError("Render Canceled")

    def _render_depth(self, output_path: str, context: dict):
        """渲染深度图"""
        scene: bpy.types.Scene = context["scene"]

        if not scene.camera:
            raise ValueError("Scene Camera Not Found")

        render_agent = RenderAgent()
        self.is_rendering = True
        self.rendering_time_start = time.time()

        def on_write(_sce):
            if not check_image_valid(output_path):
                self.render_cancel = True

            self.is_rendering = False
            render_agent.detach()
            logger.info("Depth render completed")

        render_agent.on_write(on_write)
        render_agent.attach()
        Timer.put((render_scene_depth_to_png, scene, output_path))

        # 等待渲染完成
        while self.is_rendering:
            time.sleep(0.1)

        # 检查是否取消
        if self.render_cancel:
            self.render_cancel = False
            raise RuntimeError("Render Canceled")

    def _render_opengl_viewport(self, output_path: str, context: dict):
        """渲染 OpenGL 视图"""
        scene: bpy.types.Scene = context["scene"]

        if not scene.camera:
            raise ValueError("Scene Camera Not Found")

        Timer.wait_run(render_scene_viewport_opengl_to_png)(context, output_path)
        time.sleep(1)  # 给用户反应时间
        # 检查是否取消
        if self.render_cancel:
            self.render_cancel = False
            raise RuntimeError("Render Canceled")

    def get_rendering_time(self) -> float:
        """获取渲染耗时"""
        if self.rendering_time_start == 0:
            return 0
        return time.time() - self.rendering_time_start


if __name__ == "__main__":
    render_agent = RenderAgent()

    def on_complete(sce):
        print("on_complete", sce)

    def on_post(sce):
        print("on_post", sce)

    def on_write(sce):
        print("Render Finished")

    def on_cancel(sce):
        print("Render Cancel")

    bpy.app.handlers.render_cancel.append(on_cancel)
    bpy.app.handlers.render_complete.append(on_complete)
    bpy.app.handlers.render_post.append(on_post)
    bpy.app.handlers.render_write.append(on_write)

    render_agent.on_complete(on_complete)
    render_agent.on_post(on_post)
    render_agent.on_write(on_write)
    render_agent.on_cancel(on_write)

    render_agent.attach()
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.render.filepath = Path.home().joinpath("Desktop/output/test.png").as_posix()
    bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)
    # render_agent.detach()
