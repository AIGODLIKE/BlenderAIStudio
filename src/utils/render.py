import bpy
from uuid import uuid4
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
    with with_scene_render_output_settings(scene, image_path):
        bpy.ops.render.render(write_still=True)
    if bpy.app.version >= (5, 0):
        scene.compositing_node_group = old_tree
        bpy.data.node_groups.remove(tree)


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
