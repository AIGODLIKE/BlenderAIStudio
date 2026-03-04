import bpy
import math
import time
import tempfile
from contextlib import contextmanager
from pathlib import Path
from traceback import print_exc
from uuid import uuid4
from bpy.app.translations import pgettext as _T
from mathutils import Euler, Vector
from threading import Lock
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


def _get_objects_bounding_box(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    all_coords: list[Vector] = []
    for obj in objects:
        for corner in obj.bound_box:
            all_coords.append(obj.matrix_world @ Vector(corner))

    if not all_coords:
        raise ValueError("Selected objects have no bounding box data")

    bb_min = Vector(
        (
            min(c.x for c in all_coords),
            min(c.y for c in all_coords),
            min(c.z for c in all_coords),
        )
    )
    bb_max = Vector(
        (
            max(c.x for c in all_coords),
            max(c.y for c in all_coords),
            max(c.z for c in all_coords),
        )
    )
    return bb_min, bb_max


# 三视图视角定义
#   w_axis / h_axis: 投影平面对应的世界坐标轴索引 (0=X, 1=Y, 2=Z)
#   depth_axis: 深度方向的世界坐标轴索引
#
# 约定与 Blender Numpad 视角一致:
#   Front (Numpad 1): 从 -Y 看向 +Y → euler (π/2, 0, π)
#   Right (Numpad 3): 从 +X 看向 -X → euler (π/2, 0, π/2)
#   Top   (Numpad 7): 从 +Z 看向 -Z → euler (0, 0, 0)
THREE_VIEW_SPECS = [
    {  # 正视图 (Front): 相机在 -Y 侧, 看向 +Y → 投影到 XZ 平面
        "name": "front",
        "euler": (math.pi / 2, 0, math.pi),
        "w_axis": 0,
        "h_axis": 2,
        "depth_axis": 1,
    },
    {  # 右视图 (Right): 相机在 +X 侧, 看向 -X → 投影到 YZ 平面
        "name": "right",
        "euler": (math.pi / 2, 0, math.pi / 2),
        "w_axis": 1,
        "h_axis": 2,
        "depth_axis": 0,
    },
    {  # 顶视图 (Top): 相机在 +Z 侧, 看向 -Z → 投影到 XY 平面
        "name": "top",
        "euler": (0, 0, 0),
        "w_axis": 0,
        "h_axis": 1,
        "depth_axis": 2,
    },
]


def _render_three_views(
    context: dict,
    objects: list[bpy.types.Object],
    resolution: int = 1024,
    padding: float = 1.05,
) -> list[str]:
    """对指定物体进行正交三视图渲染（正视图、侧视图、顶视图）。

    算法要点:
        1. 计算所有物体联合包围盒 (AABB)
        2. 对每个视角, 取 AABB 在该视角投影平面上的宽度和高度
        3. 以宽高比自适应渲染分辨率, ortho_scale 取较大边使物体铺满画面
        4. 从 euler 角自动推导相机观察方向, 沿反方向偏移放置相机
        5. 渲染完成后删除临时相机, 恢复所有设置

    Args:
        scene: Blender 场景
        objects: 要渲染的物体列表
        resolution: 输出图片的长边像素数
        padding: 包围盒到画面边缘的留白比例 (>1.0), 例如 1.05 表示 5% 留白

    Returns:
        三张渲染图片的路径列表 [front, right, top]
    """
    bb_min, bb_max = _get_objects_bounding_box(objects)
    bb_size = bb_max - bb_min
    bb_center = (bb_min + bb_max) / 2

    max_dim = max(bb_size.x, bb_size.y, bb_size.z)
    if max_dim < 1e-6:
        raise ValueError("Selected objects have zero or near-zero bounding box")

    temp_folder = get_temp_folder(prefix="three_view")
    image_paths: list[str] = []
    created_objects: list[bpy.types.Object] = []

    scene: bpy.types.Scene = context["scene"]
    old_camera = scene.camera
    old_res_x = scene.render.resolution_x
    old_res_y = scene.render.resolution_y
    old_engine = scene.render.engine

    for engine in ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "EEVEE"]:
        try:
            scene.render.engine = engine
            break
        except Exception:
            continue

    try:
        for spec in THREE_VIEW_SPECS:
            view_name = spec["name"]
            euler_tuple = spec["euler"]
            w_axis = spec["w_axis"]
            h_axis = spec["h_axis"]
            depth_axis = spec["depth_axis"]

            view_width = bb_size[w_axis] * padding
            view_height = bb_size[h_axis] * padding
            view_depth = bb_size[depth_axis]

            if view_width < 1e-6:
                view_width = max_dim * padding
            if view_height < 1e-6:
                view_height = max_dim * padding
            if view_depth < 1e-6:
                view_depth = max_dim

            aspect = view_width / view_height

            if aspect >= 1.0:
                res_x = resolution
                res_y = max(1, round(resolution / aspect))
                ortho_scale = view_width
            else:
                res_x = max(1, round(resolution * aspect))
                res_y = resolution
                ortho_scale = view_height

            scene.render.resolution_x = res_x
            scene.render.resolution_y = res_y

            cam_data = bpy.data.cameras.new(f"_three_view_{view_name}")
            cam_data.type = "ORTHO"
            cam_data.ortho_scale = ortho_scale
            cam_data.sensor_fit = "AUTO"
            cam_data.clip_start = 0.001
            cam_data.clip_end = view_depth * 2 + max_dim * 4

            cam_obj = bpy.data.objects.new(f"_three_view_{view_name}", cam_data)
            scene.collection.objects.link(cam_obj)
            created_objects.append(cam_obj)

            cam_obj.rotation_euler = euler_tuple

            # 从 euler 推导观察方向, 相机沿观察方向的反方向偏移
            look_dir = -(cam_obj.rotation_euler.to_matrix() @ Vector((0, 0, 1)))
            cam_distance = view_depth / 2 + max_dim * 2
            cam_obj.location = bb_center - look_dir * cam_distance

            scene.camera = cam_obj

            image_path = str(Path(temp_folder) / f"three_view_{view_name}.png")
            with with_scene_render_output_settings(scene, image_path):
                with silent_rendering():
                    bpy.ops.render.render(write_still=True)
            image_paths.append(image_path)
    finally:
        scene.camera = old_camera
        scene.render.resolution_x = old_res_x
        scene.render.resolution_y = old_res_y
        scene.render.engine = old_engine

        for obj in created_objects:
            cam_data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.cameras.remove(cam_data)

    return image_paths


class BlenderRenderHelper:
    """
    渲染辅助工具
    负责根据 itype 渲染 Blender 场景，返回渲染结果路径。
    """

    IS_RENDERING = False
    IS_RENDERING_LOCK = Lock()

    @classmethod
    def set_is_rendering(cls, value: bool):
        with cls.IS_RENDERING_LOCK:
            cls.IS_RENDERING = value

    @classmethod
    def get_is_rendering(cls) -> bool:
        with cls.IS_RENDERING_LOCK:
            return cls.IS_RENDERING

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
            BlenderRenderHelper.set_is_rendering(True)
            try:
                self._render_camera(image_path, context)
            finally:
                BlenderRenderHelper.set_is_rendering(False)
        elif itype == "CameraDepth":
            self._wait_for_rendering()
            BlenderRenderHelper.set_is_rendering(True)
            try:
                self._render_depth(image_path, context)
            finally:
                BlenderRenderHelper.set_is_rendering(False)
        elif itype == "FastRender":
            self._wait_for_rendering()
            BlenderRenderHelper.set_is_rendering(True)
            try:
                self._render_opengl_viewport(image_path, context)
            finally:
                BlenderRenderHelper.set_is_rendering(False)
        else:
            raise ValueError(f"Unknown input image type: {itype}")

        return image_path

    def render_three_views(self, context: dict, objects: list[bpy.types.Object] = None, resolution: int = 1024) -> list[str]:
        """渲染选中物体的三视图（正视图、侧视图、顶视图）。
        Args:
            objects: 要渲染的物体列表，若为 None 则使用当前选中物体
            resolution: 输出图片长边像素数

        Returns:
            三张渲染图片路径 [front, right, top]
        """
        if objects is None:
            objects = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
        if not objects:
            raise ValueError("No objects selected for three-view rendering")

        try:
            self._wait_for_rendering()
            BlenderRenderHelper.set_is_rendering(True)
            res = Timer.wait_run(_render_three_views)(context, objects, resolution)
        finally:
            BlenderRenderHelper.set_is_rendering(False)
        return res

    def _is_other_rendering(self):
        return bpy.app.is_job_running("RENDER") or BlenderRenderHelper.get_is_rendering()

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
            raise ValueError("Scene Camera Not Found, Please add a camera and try again")

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
            raise ValueError("Scene Camera Not Found, Please add a camera and try again")

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
            raise ValueError("Scene Camera Not Found, Please add a camera and try again")

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


@bpy.app.handlers.persistent
def reset_render_status(_, __):
    BlenderRenderHelper.set_is_rendering(False)


def register():
    bpy.app.handlers.load_post.append(reset_render_status)


def unregister():
    bpy.app.handlers.load_post.remove(reset_render_status)


# if __name__ == "__main__":
#     render_agent = RenderAgent()
#
#
#     def on_complete(sce):
#         print("on_complete", sce)
#
#
#     def on_post(sce):
#         print("on_post", sce)
#
#
#     def on_write(sce):
#         print("Render Finished")
#
#
#     def on_cancel(sce):
#         print("Render Cancel")
#
#
#     bpy.app.handlers.render_cancel.append(on_cancel)
#     bpy.app.handlers.render_complete.append(on_complete)
#     bpy.app.handlers.render_post.append(on_post)
#     bpy.app.handlers.render_write.append(on_write)
#
#     render_agent.on_complete(on_complete)
#     render_agent.on_post(on_post)
#     render_agent.on_write(on_write)
#     render_agent.on_cancel(on_write)
#
#     render_agent.attach()
#     bpy.context.scene.render.engine = "CYCLES"
#     bpy.context.scene.render.filepath = Path.home().joinpath("Desktop/output/test.png").as_posix()
#     bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)
#     # render_agent.detach()
