import bpy
from queue import Queue

from .. import debug_time
from ...External.input_method_hook import input_manager

IME_BUFFER = Queue()


class IM_OT_enable_chinese_input(bpy.types.Operator):
    """在3D Viewport中启用中文输入法"""

    bl_idname = "input_method.enable_chinese_input"
    bl_label = "启用中文输入"

    def execute(self, context):
        if input_manager.enable_chinese_input():
            self.report({"INFO"}, "中文输入法已启用")
        else:
            self.report({"ERROR"}, "无法启用中文输入法")
        return {"FINISHED"}


class IM_OT_disable_chinese_input(bpy.types.Operator):
    """禁用中文输入法"""

    bl_idname = "input_method.disable_chinese_input"
    bl_label = "禁用中文输入"

    def execute(self, context):
        if input_manager.disable_chinese_input():
            self.report({"INFO"}, "中文输入法已禁用")
        else:
            self.report({"ERROR"}, "无法禁用中文输入法")
        return {"FINISHED"}


class IM_OT_refresh_input_method(bpy.types.Operator):
    """刷新输入法状态"""

    bl_idname = "input_method.refresh_input"
    bl_label = "刷新输入法"

    def execute(self, context):
        if input_manager.refresh_input_method():
            self.report({"INFO"}, "输入法状态已刷新")
        else:
            self.report({"ERROR"}, "无法刷新输入法")
        return {"FINISHED"}


class IM_OT_test_input(bpy.types.Operator):
    """测试输入法输入"""

    bl_idname = "input_method.test_input"
    bl_label = "测试输入"

    def execute(self, context):
        # 设置输入回调
        def on_input_received(text):
            print(f"接收到输入: {text}")
            # 在这里处理接收到的文本
            # 例如：更新3D文本对象、设置属性等
            if text.strip():
                print(f"输入: {text}")

        input_manager.set_input_callback(on_input_received)
        input_manager.enable_chinese_input()

        self.report({"INFO"}, "输入法测试已启动，请在3D视图中输入")
        return {"FINISHED"}


class IM_OT_create_text_object(bpy.types.Operator):
    """创建3D文本对象并启用中文输入"""

    bl_idname = "input_method.create_text_object"
    bl_label = "创建可输入文本对象"

    text_content: bpy.props.StringProperty(name="文本内容", default="中文文本")

    def execute(self, context):
        # 创建文本对象
        bpy.ops.object.text_add()
        text_obj = context.active_object
        text_obj.name = "ChineseText"

        # 设置文本内容
        text_obj.data.body = self.text_content

        # 设置输入回调来更新文本对象
        def update_text_object(new_text):
            if new_text.strip():
                text_obj.data.body = new_text
                print("Receive: ", new_text)
                # 强制更新视图
                bpy.context.view_layer.update()

        input_manager.set_input_callback(update_text_object)
        input_manager.enable_chinese_input()

        self.report({"INFO"}, "文本对象已创建，可以输入中文")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class IM_PT_input_method_panel(bpy.types.Panel):
    """输入法控制面板"""

    bl_label = "中文输入法控制"
    bl_idname = "IM_PT_input_method_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "工具"

    def draw(self, context):
        layout = self.layout

        # 显示当前状态
        state = input_manager.get_input_method_state()
        status_text = "未知"
        if state == 1:
            status_text = "中文输入已启用"
        elif state == 0:
            status_text = "英文输入"

        layout.label(text=f"状态: {status_text}")

        # 显示当前组合文本
        composition = input_manager.get_composition_string()
        result = input_manager.get_result_string()
        if composition:
            layout.label(text=f"正在输入: {composition}")
        if result:
            layout.label(text=f"输入结果: {result}")

        # 操作按钮
        row = layout.row()
        row.operator(IM_OT_enable_chinese_input.bl_idname)
        row.operator(IM_OT_disable_chinese_input.bl_idname)

        layout.operator(IM_OT_refresh_input_method.bl_idname)
        layout.separator()
        layout.operator(IM_OT_test_input.bl_idname)
        layout.operator(IM_OT_create_text_object.bl_idname)
        layout.operator(IM_OT_modal_input_operator.bl_idname)


# 模态操作符，用于实时输入
class IM_OT_modal_input_operator(bpy.types.Operator):
    """模态输入操作符"""

    bl_idname = "input_method.modal_input"
    bl_label = "模态中文输入"
    text: bpy.props.StringProperty(default="")

    def modal(self, context, event):
        if event.type == "ESC":
            return self.cancel(context)
        elif event.type == "RET" or event.type == "NUMPAD_ENTER":
            return self.execute(context)

        return {"PASS_THROUGH"}

    def execute(self, context):
        # 设置输入回调
        def on_input_received(text):
            IME_BUFFER.put(text)
            self.text += text
            print("接收到输入: ", text)
            # 可以在这里实时更新UI或对象

        input_manager.set_input_callback(on_input_received)
        input_manager.enable_chinese_input()

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        input_manager.disable_chinese_input()
        return {"CANCELLED"}


# 自动处理输入法状态
@bpy.app.handlers.persistent
def on_load_pre(dummy):
    input_manager.refresh_input_method()


@bpy.app.handlers.persistent
def on_save_pre(dummy):
    input_manager.refresh_input_method()


@debug_time
def register():
    bpy.utils.register_class(IM_OT_enable_chinese_input)
    bpy.utils.register_class(IM_OT_disable_chinese_input)
    bpy.utils.register_class(IM_OT_refresh_input_method)
    bpy.utils.register_class(IM_OT_test_input)
    bpy.utils.register_class(IM_OT_create_text_object)
    bpy.utils.register_class(IM_OT_modal_input_operator)
    bpy.utils.register_class(IM_PT_input_method_panel)

    bpy.app.handlers.load_pre.append(on_load_pre)
    bpy.app.handlers.save_pre.append(on_save_pre)

    input_manager.refresh_input_method()


def unregister():
    bpy.utils.unregister_class(IM_OT_enable_chinese_input)
    bpy.utils.unregister_class(IM_OT_disable_chinese_input)
    bpy.utils.unregister_class(IM_OT_refresh_input_method)
    bpy.utils.unregister_class(IM_OT_test_input)
    bpy.utils.unregister_class(IM_OT_create_text_object)
    bpy.utils.unregister_class(IM_OT_modal_input_operator)
    bpy.utils.unregister_class(IM_PT_input_method_panel)

    if on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(on_load_pre)
    if on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(on_save_pre)

    if input_manager.dll:
        input_manager.dll.CleanupInputMethod()
