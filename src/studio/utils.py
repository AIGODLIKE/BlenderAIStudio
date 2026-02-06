import bpy
import mimetypes
import time
from pathlib import Path
from datetime import datetime
from traceback import print_exc
from ..utils import get_temp_folder
from ..logger import logger
from ..timer import Timer


def save_mime_typed_datas_to_temp_files(mime_typed_datas: list[tuple[str, str | bytes]]) -> list[str]:
    """保存 MIME 类型数据到临时文件

    Args:
        mime_typed_datas: MIME 类型数据，每个元素为 (mime_type, data) 元组

    Returns:
        保存的文件路径列表
    """
    temp_folder = get_temp_folder(prefix="generate")
    timestamp = time.time()
    time_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d%H%M%S")
    saved_files = []

    for idx, (mime_type, data) in enumerate(mime_typed_datas):
        ext = mimetypes.guess_extension(mime_type) or ""
        # 使用索引避免多个文件名冲突
        if len(mime_typed_datas) > 1:
            save_file = Path(temp_folder, f"Gen_{time_str}_{idx}{ext}")
        else:
            save_file = Path(temp_folder, f"Gen_{time_str}{ext}")

        if isinstance(data, bytes):
            save_file.write_bytes(data)
        elif isinstance(data, str):
            save_file.write_text(data, encoding="utf-8")

        logger.info(f"结果已保存到: {save_file.as_posix()}")
        saved_files.append((mime_type, save_file.as_posix()))

    return saved_files


def load_images_into_blender(outputs: list[tuple[str, str]]):
    for mime_type, file_path in outputs:
        if mime_type.startswith("image/"):

            def load_image_into_blender(file_path: str):
                try:
                    bpy.data.images.load(file_path)
                except Exception:
                    print_exc()

            Timer.put((load_image_into_blender, file_path))
