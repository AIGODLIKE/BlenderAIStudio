import json
import time
import traceback

import bpy

from .core import Account
from .network import get_session
from ...logger import (
    LOGFILE,
    logger,
    get_recent_logger_text,
    get_recent_console_text,
)
from ...utils import get_addon_version_str, get_pref


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _read_log_file(max_chars=60000) -> str:
    try:
        if not LOGFILE.exists():
            return ""
        text = LOGFILE.read_text(encoding="utf-8", errors="ignore")
        return _truncate_text(text, max_chars=max_chars)
    except Exception as e:
        logger.error(f"读取日志文件失败: {e}")
        return ""


def _collect_scene_history() -> dict:
    data = {
        "generate_history": "[]",
        "edit_history": [],
    }
    try:
        scene = bpy.context.scene
        if not scene:
            return data
        prop = scene.blender_ai_studio_property
        data["generate_history"] = _truncate_text(prop.generate_history or "[]", max_chars=60000)
        for item in prop.edit_history[-10:]:
            data["edit_history"].append(
                {
                    "task_id": item.task_id,
                    "name": item.name,
                    "running_state": item.running_state,
                    "running_message": item.running_message,
                    "generation_time": item.generation_time,
                    "generation_model": item.generation_model,
                    "prompt": item.prompt,
                }
            )
    except Exception as e:
        logger.error(f"收集 Scene 历史失败: {e}")
    return data


def _collect_studio_history() -> list[dict]:
    try:
        from ..clients.history.history import StudioHistory

        history = StudioHistory.get_instance()
        items = [item.data for item in history.items]
        return items[-10:]
    except Exception as e:
        logger.error(f"收集 StudioHistory 失败: {e}")
        return []


def _collect_preferences() -> dict:
    data = {
        "output_cache_dir_not_writable": False,
        "output_cache_dir": "",
        "account_auth_mode": "",
        "account_pricing_strategy": "",
        "disable_system_prompt": False,
    }
    try:
        pref = get_pref()
        data["output_cache_dir_not_writable"] = bool(getattr(pref, "output_cache_dir_not_writable", False))
        data["output_cache_dir"] = str(getattr(pref, "output_cache_dir", "") or "")
        data["account_auth_mode"] = str(getattr(pref, "account_auth_mode", "") or "")
        data["account_pricing_strategy"] = str(getattr(pref, "account_pricing_strategy", "") or "")
        data["disable_system_prompt"] = bool(getattr(pref, "disable_system_prompt", False))
    except Exception as e:
        logger.error(f"收集 preferences 失败: {e}")
    return data


def build_error_report_info() -> str:
    info = {
        "timestamp": int(time.time()),
        "blender_version": bpy.app.version_string,
        "addon_version": get_addon_version_str(),
        "preferences": _collect_preferences(),
        "logger_recent": get_recent_logger_text(limit=100000),
        "console_recent": get_recent_console_text(limit=100000),
        "logger_file_tail": _read_log_file(max_chars=100000),
        "scene_history": _collect_scene_history(),
        "studio_history_items": _collect_studio_history(),
    }
    text = json.dumps(info, ensure_ascii=False, indent=2)
    return _truncate_text(text, max_chars=20000000)


def upload_error_report_async(ops):
    account = Account.get_instance()
    if not account.token:
        raise RuntimeError("Token is empty, please login first")

    url = f"{account.service_url}/sys/error-report"
    headers = {
        "X-Auth-T": account.token,
        "Content-Type": "application/json",
    }
    payload = {
        "info": build_error_report_info(),
    }

    def run():
        try:
            session = get_session()
            resp = session.post(url, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            logger.info("日志上报成功")
            if ops:
                ops.report({"INFO"}, "日志上报成功")
        except Exception as e:
            text = f"日志上报失败: {e}"
            if ops:
                ops.report({"INFO"}, text)
            logger.error(text)
            traceback.print_exc()

    # Thread(target=run, daemon=True).start()
    run()
