import bpy
from pathlib import Path
from contextlib import contextmanager
from bpy.app.translations import pgettext as _T


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
    with with_scene_render_output_settings(scene, image_path):
        bpy.ops.render.render(write_still=True)


def render_scene_depth_to_png(scene: bpy.types.Scene, image_path: str):
    """
    渲染相机视角下的深度图
    """
    check_scene_camera_with_exception(scene)
    bpy.context.view_layer.use_pass_mist = True
    bpy.context.scene.use_nodes = True
    tree: bpy.types.NodeTree = bpy.context.scene.node_tree

    for node in tree.nodes:
        tree.nodes.remove(node)

    render_layer = tree.nodes.new(type="CompositorNodeRLayers")
    output = tree.nodes.new(type="CompositorNodeComposite")
    tree.links.new(render_layer.outputs["Mist"], output.inputs["Image"])
    with with_scene_render_output_settings(scene, image_path):
        bpy.ops.render.render(write_still=True)
