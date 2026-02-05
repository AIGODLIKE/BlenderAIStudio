import bpy


def find_ai_image_editor_space_data():
    # bpy.context.region.active_panel_category
    panel_data = []
    for area in bpy.context.screen.areas:
        if area.type == "IMAGE_EDITOR":
            for region in area.regions:
                if region.type == "TOOLS":
                    if region.active_panel_category == "Image":
                        panel_data.append(area.spaces[0])
    return panel_data
