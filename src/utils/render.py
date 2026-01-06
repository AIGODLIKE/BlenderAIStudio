import bpy
from uuid import uuid4
from pathlib import Path
from contextlib import contextmanager
from bpy.app.translations import pgettext as _T
from traceback import print_exc


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
    try:
        yield
    finally:
        render.filepath = old
        if bpy.app.version >= (5, 0):
            render.image_settings.media_type = old_media_type
        render.image_settings.file_format = old_fmt


def render_scene_viewport_opengl_to_png(scene: bpy.types.Scene, image_path: str, view_context: bool):
    check_scene_camera_with_exception(scene)
    with with_scene_render_output_settings(scene, image_path):
        bpy.ops.render.opengl(write_still=True, view_context=view_context)


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

    def on_finish(_sce):
        render.filepath = old
        if bpy.app.version >= (5, 0):
            render.image_settings.media_type = old_media_type
        render.image_settings.file_format = old_fmt

    bpy.app.handlers.render_complete.append(on_finish)
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
    old = render.filepath
    old_fmt = render.image_settings.file_format

    render.filepath = image_path
    if bpy.app.version >= (5, 0):
        old_media_type = render.image_settings.media_type
        render.image_settings.media_type = "IMAGE"
    render.image_settings.file_format = "PNG"

    def on_finish(_sce):
        render.filepath = old
        if bpy.app.version >= (5, 0):
            render.image_settings.media_type = old_media_type
        render.image_settings.file_format = old_fmt
        if bpy.app.version >= (5, 0):
            scene.compositing_node_group = old_tree
            bpy.data.node_groups.remove(tree)
        bpy.app.handlers.render_complete.remove(on_finish)

    bpy.app.handlers.render_complete.append(on_finish)
    bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)


def ensure_comp_node_tree(sce: bpy.types.Scene):
    if bpy.app.version >= (5, 0):
        tree = bpy.data.node_groups.new("Render Layers" + uuid4().hex, "CompositorNodeTree")
        sce.compositing_node_group = tree
    else:
        sce.use_nodes = True


def get_comp_node_tree(sce: bpy.types.Scene) -> bpy.types.CompositorNodeTree:
    if bpy.app.version >= (5, 0):
        return sce.compositing_node_group
    return sce.node_tree


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


if __name__ == "__main__":
    render_agent = RenderAgent()

    def on_complete(sce):
        print("on_complete", sce)

    def on_post(sce):
        print("on_post", sce)

    def on_write(sce):
        print("Render Finished")

    render_agent.on_complete(on_complete)
    render_agent.on_post(on_post)
    render_agent.on_write(on_write)

    render_agent.attach()
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.render.filepath = Path.home().joinpath("Desktop/output/test.png").as_posix()
    bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)
    # render_agent.detach()
