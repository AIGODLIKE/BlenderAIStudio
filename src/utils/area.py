import bpy


def find_ai_image_editor_space_data():
    # bpy.context.region.active_panel_category
    panel_data = []
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "IMAGE_EDITOR":
                for region in area.regions:
                    if region.type == "UI":
                        if region.active_panel_category == "AIStudio":
                            panel_data.append(area.spaces[0])
    return panel_data


if __name__ == "__main__":
    print(find_ai_image_editor_space_data())
