"""在线更新插件
插件id: 2006941642182885376
"""
import json
import os
import pathlib
import tempfile
import time

import bpy
from bpy.app.translations import pgettext_iface as iface

from . import logger
from .logger import close_logger
from .utils import get_addon_version_str, get_pref, get_addon_version, str_version_to_int, calculate_md5, start_blender
from .utils.async_request import GetRequestThread, DownloadZipRequestThread

VERSION_URL = f"https://api-addon.acggit.com/v1/sys/version"
DOWNLOAD_URL = f"https://launcher.aigodlike.com/v1/launcher/addons/download?addonId=2006941642182885376&addonVersion="


class UpdateService:
    """在线更新插件
    {"responseId": "2010511048972435456", "code": 1000, "data": {
    "updateNode": "v0.0.6 2026-1-9\n优化: 参考图选择,可以多选图片作为参考图\n优化: 缓存文件夹目录命名规则\n优化: 运行检查错误提\n修复: 部分用户渲染崩溃bug\n\nv0.0.5 2026-1-7 \n修复渲染bug\n\nv0.0.4 2026-1-7\n优化渲染阻塞,在进行渲染时可取消\n优化整体流程,场景无相机时进行提示\n修复缓存文件夹设置无效bug\n\nv0.0.3 2025-1-5\n修复打开缓存目录bug\n修复blender启动卡顿bug\n\nv0.0.2  2026-1-5\n支持保存生成历史记录\n\nV0.0.1 2026/01/02\n测试版发布",
    "versions": [
        {"version": "0.0.5", "supportedBlenderVersions": ["5.0.1", "5.0.0", "4.5.3", "4.5.2", "4.5.1", "4.5.0"],
         "downloadType": 1, "downloadFileIdf": 2008822655007850496, "md5": "0d18f08dccf782b886ec257975c89b2b"},
    """
    version_info = None
    is_refreshing = False  # 正在刷新中

    @staticmethod
    def update_addon_version_info() -> None:
        """更新插件版本信息"""
        cls = UpdateService

        def on_request_finished(result, error):
            if error:
                print(f"获取插件版本信息失败 {type(error).__name__}: {error}")
                cls.is_refreshing = False
            else:
                # 存储版本信息
                try:
                    res = json.loads(result)
                    cls.version_info = json.loads(result)
                    vs = res['data']['versions']
                    logger.info(f"请求版本信息成功, 获取到 {len(vs)} 个版本数据")
                except Exception as e:
                    print(f"解析版本信息失败: {e}")
                finally:
                    cls.is_refreshing = False

        if cls.is_refreshing:
            return
        cls.is_refreshing = True
        GetRequestThread(VERSION_URL, on_request_finished).start()

    @staticmethod
    def get_last_version_data() -> dict | None:
        """获取最新版本"""
        cls = UpdateService
        try:
            if cls.version_info:
                versions = cls.version_info['data']['versions']
                versions.sort(key=lambda x: x['version'], reverse=True)
                return versions[0]
        except Exception as e:
            print(f"获取插件版本信息失败: {e}")
        return None

    @staticmethod
    def get_last_version() -> str:
        """获取最新版本号"""
        cls = UpdateService
        try:
            if last_version_data := cls.get_last_version_data():
                last_version = last_version_data.get("version", "unknown")
                return last_version
        except Exception as e:
            print(f"获取最新版本失败: {e}")
        return "unknown"

    @staticmethod
    def get_update_log() -> str:
        """反回更新日志"""
        cls = UpdateService
        try:
            update_log = cls.version_info['data']['updateLog']
            return update_log
        except Exception as e:
            print(f"更新日志失败: {e}")
            return "unknown"

    @staticmethod
    def is_update_available():
        """检查是否有更新可用
        用版本int元组来对比
        string的话不正确
        """
        cls = UpdateService
        try:
            install_version = get_addon_version()
            if last := cls.get_last_version_data():
                return str_version_to_int(last['version']) > install_version
        except Exception as e:
            print(f"检查更新失败: {e}")
            return False

    @staticmethod
    def draw_update_info(layout: bpy.types.UILayout):
        cls = UpdateService

        col = layout.column()

        if last_version_data := cls.get_last_version_data():
            last_version = last_version_data.get("version", "unknown")
            md5 = last_version_data.get("md5", "unknown")

            col.label(text=f"{iface('Current version')}: {get_addon_version_str()}")
            col.label(text=f"{iface('Latest version')}: {last_version}")
            is_update_available = cls.is_update_available()
            if OnlineUpdateAddon.draw_update_info_state(col):
                return
            if is_update_available:
                text = iface("Update to %s") % last_version
                cc = col.column()
                cc.alert = True
                cc.label(text="A new version is available!")
                ops = col.operator(OnlineUpdateAddon.bl_idname, text=text, )
                ops.version = last_version
                ops.md5 = md5
            else:
                text = "Check for updates" if not cls.is_refreshing else "Under inspection..."
                col.operator(UpdateAddonUpdateVersionInfo.bl_idname, text=text)
            cls.draw_update_log(col)
        else:
            col.label(text="Error in obtaining updated data")
            col.active = not cls.is_refreshing
            text = "Retrieve again" if not cls.is_refreshing else "Fetching..."
            col.operator(UpdateAddonUpdateVersionInfo.bl_idname, text=text)

    @staticmethod
    def draw_update_log(layout: bpy.types.UILayout):
        cls = UpdateService
        update_log = cls.get_update_log()
        pref = get_pref()
        is_expand = pref.expand_update_log
        icon = "DOWNARROW_HLT" if is_expand else "RIGHTARROW"
        co = layout.box().column(align=True)
        co.row().prop(pref, "expand_update_log", text="Changelog", expand=True, emboss=False, icon=icon)
        sp = update_log.split("\n")
        logs = sp if pref.expand_update_log else sp[:sp.index("")] + ["...", ]
        c = co.column()
        for text in logs:
            c.label(text=text)

    @classmethod
    def draw_update_info_panel(cls, layout: bpy.types.UILayout):
        if cls.is_update_available():
            if OnlineUpdateAddon.draw_update_info_state(layout):
                return
            box = layout.box()
            col = box.column()
            col.alert = True
            col.label(text=iface("Update available"))
            cls.draw_update_log(box)

            if last_version_data := cls.get_last_version_data():
                last_version = last_version_data.get("version", "unknown")
                md5 = last_version_data.get("md5", "unknown")

                ops = box.operator(OnlineUpdateAddon.bl_idname, text=iface("Update to %s") % last_version)
                ops.version = last_version
                ops.md5 = md5


class UpdateAddonUpdateVersionInfo(bpy.types.Operator):
    """更新插件信息"""
    bl_idname = "bas.update_addon_version_info"
    bl_label = "Update Addon Info"

    timer = None
    time = 0

    def invoke(self, context, event):
        self.execute(context)
        context.window_manager.modal_handler_add(self)
        self.timer = context.window_manager.event_timer_add(1, window=context.window)
        self.time = 0
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "TIMER":
            self.time += 1
        if self.time > 30:
            self.exit(context)
            self.report({"ERROR"}, "Check version timeout")
            return {"FINISHED"}
        elif not UpdateService.is_refreshing:  # 不在刷新中,已获取到数据
            if UpdateService.is_update_available():
                text = bpy.app.translations.pgettext_iface("Update available %s")
                self.report({"INFO"}, text % UpdateService.get_last_version())
            else:
                self.report({"INFO"}, "No updates available")
            self.exit(context)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def exit(self, context):
        if self.timer:
            context.window_manager.event_timer_remove(self.timer)
        if context.area:
            context.area.tag_redraw()

    def execute(self, context):
        UpdateService.update_addon_version_info()
        return {"FINISHED"}


class OnlineUpdateAddon(bpy.types.Operator, UpdateService):
    """
    1.获取下载链接
    2.下载更新文件到本地
    3.安装更新
    4.重启弹窗
    """
    bl_idname = "bas.online_update_addon"
    bl_label = "Online Update Addon"
    version: bpy.props.StringProperty(default="")
    md5: bpy.props.StringProperty(default="")

    error_message = ""
    download_info = None  # {"responseId":"xx","code":1000,"data":"https://ocdn-blender-launcher.aigodlike.com/addons/2009558539403526144?Expires=xx&OSSAccessKeyId=xx&Signature=xx"}
    timer = None
    start_time = 0
    is_downloading = False
    is_update_finished = False  # 更新完成
    update_info = []  # [{text:str,level:str}]

    @classmethod
    def draw_update_info_state(cls, layout: bpy.types.UILayout):
        if cls.update_info:
            column = layout.box().column(align=True)
            for i in cls.update_info:
                text = i.get("text", "emm")
                alert = i.get("level", "E") == "ERROR"

                column.alert = False
                column.label(text=text)
                column.alert = alert
            return True
        return False

    def invoke(self, context, event):
        if self.__class__.update_info:  # 避免多次点击
            return {"CANCELLED"}
        context.window_manager.progress_begin(0, 4)
        context.window_manager.progress_update(0)
        self.start_time = time.time()

        download_url = DOWNLOAD_URL + self.version

        def on_request_finished(result, error):
            if error:
                self.error_message = str(error)
                logger.error(self.error_message)
            else:
                try:
                    # logger.info(result)
                    self.download_info = json.loads(result)
                    self.push_info("Successfully obtained download address")
                    context.window_manager.progress_update(1)
                except Exception as e:
                    self.error_message = str(e)
                    logger.error(self.error_message)

        logger.info(f"Start online update to {self.version}")
        # logger.info(f"download_url:{download_url}")
        GetRequestThread(download_url, on_request_finished).start()
        self.timer = context.window_manager.event_timer_add(1 / 30, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        try:
            if context.area:
                context.area.tag_redraw()

            if event.type == "ESC":  # 按了退出按钮
                self.push_info("Cancel update")
                self.exit(context)
                return {"CANCELLED"}
            elif self.is_update_finished:  # 更新完成
                self.exit(context)
                bpy.ops.bas.restart("INVOKE_DEFAULT")  # 让用户重启BLender
                return {"FINISHED"}
            elif self.error_message:  # 出现错误
                self.exit(context)
                self.report({"ERROR"}, self.error_message)
                return {"FINISHED"}
            elif self.download_info and isinstance(self.download_info, dict) and not self.is_downloading:
                self.start_download(context)
        except Exception as e:
            es = str(e)
            self.exit(context)
            self.push_info(es, "ERROR")
            self.report({"ERROR"}, es)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def start_download(self, context):
        try:
            self.push_info("Start downloading updates")
            self.is_downloading = True
            context.window_manager.progress_update(1)

            def on_downloaded(file_path, error):
                self.push_info("Download finished")
                context.window_manager.progress_update(2)
                if error:
                    self.error_message = str(error)
                else:
                    self.check_zip(file_path)

            url = self.download_info["data"]
            code = self.download_info["code"]
            if code != 1000:
                self.error_message = "Download failed"
                return

            download_folder = os.path.abspath(tempfile.mkdtemp(prefix="bas_online_update_addon_"))
            download_file_path = os.path.join(download_folder, "BlenderAIStudio.zip")

            DownloadZipRequestThread(url, download_file_path, on_downloaded).start()
        except Exception as e:
            print(e.args)

    def check_zip(self, zip_file_path):
        self.push_info("Verifying the file")
        bpy.context.window_manager.progress_update(3)
        md5 = self.md5
        file_md5 = calculate_md5(zip_file_path)
        if md5 != file_md5:
            self.error_message = "MD5 verification of the downloaded file failed"
        else:
            self.push_info("Verifying completed!!!")

            def on_install():
                self.background_install_update(zip_file_path)

            bpy.app.timers.register(on_install, first_interval=0.1)

    def background_install_update(self, zip_file_path):
        """
        后台新开一个Blender安装更新包
        "${this.blenderPath}" --background --python-expr ""
        """
        try:
            self.push_info("Start installing updates")
            close_logger()  # 安装更新前要取消日志文件占用
            target = self.get_install_target(bpy.context)
            logger.info(f"{target} {zip_file_path}")
            bpy.ops.preferences.addon_install("EXEC_DEFAULT", filepath=zip_file_path, overwrite=True, target=target)

            # 安装完成
            bpy.context.window_manager.progress_update(4)
            text = "Update completed!"
            self.push_info(text)
            self.push_info(f"用时:{time.time() - self.start_time:.2f}s")
            self.report({"INFO"}, text)
            self.is_update_finished = True
        except Exception as e:
            self.push_info(f"安装更新失败: {e}", "ERROR")
            print(e.args)
            self.error_message = str(e)

    def exit(self, context):
        context.window_manager.event_timer_remove(self.timer)
        context.window_manager.progress_end()

        def clear_info():
            OnlineUpdateAddon.update_info.clear()

        bpy.app.timers.register(clear_info, first_interval=5)

    def execute(self, context):
        start_blender()
        return {"FINISHED"}

    @staticmethod
    def reload_addon():
        import addon_utils
        addon_utils.modules(refresh=True)
        bpy.utils.refresh_script_paths()

    @staticmethod
    def get_python_command(zip_file_path):
        blender_path = bpy.app.binary_path
        im = "import bpy;import os,sys"
        install = f"bpy.ops.preferences.addon_install('EXEC_DEFAULT', filepath=r'{zip_file_path}', overwrite=True, enable_on_install=True)"
        python_command = f"{im};{install};print('Online Update Addon Run Finished', file=sys.stderr);quit(0);"
        return f"\"{blender_path}\" --background --factory-startup --python-expr \"{python_command}\""

    @classmethod
    def push_info(cls, text, level="INFO"):
        if level == "ERROR":
            logger.error(iface(text))
        else:
            logger.info(iface(text))
        cls.update_info.append({"text": text, "level": level})

    @staticmethod
    def get_install_target(context):
        # scripts\startup\bl_operators\userpref.py L:672
        # bpy.types.PREFERENCES_OT_addon_install._target_path_items
        default_target = 'DEFAULT'
        from .. import __file__ as addon_path
        paths = context.preferences.filepaths
        absolute_addon = pathlib.Path(addon_path).parent.parent.parent.absolute()
        print("addon_path", addon_path)
        print("absolute_addon", absolute_addon)
        for index, item in enumerate(paths.script_directories):
            print("item.directory", item.directory, pathlib.Path(item.directory).absolute())
            if pathlib.Path(item.directory).absolute() == absolute_addon:
                print("absolute_addon", absolute_addon)
                return item.name
        return default_target


class Restart(bpy.types.Operator):
    bl_idname = "bas.restart"
    bl_label = "Restart Blender"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, title="Update completed",
                                                     message="Do you want to restart the program to apply the updates? (Remember to save your files)")

    def execute(self, context):
        bpy.ops.wm.quit_blender()
        start_blender()
        return {"FINISHED"}


class_list = [
    UpdateAddonUpdateVersionInfo,
    OnlineUpdateAddon,
    Restart,
]

register_class, unregister_class = bpy.utils.register_classes_factory(class_list)


def register():
    OnlineUpdateAddon.update_addon_version_info()
    register_class()


def unregister():
    unregister_class()
