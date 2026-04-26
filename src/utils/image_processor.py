"""图像处理工具模块

提供图像缩放、JPG/PNG 格式转换等常用功能。
全程使用 OpenImageIO (OIIO)，不依赖 Pillow 等外部图像库。

注意：Blender OIIO binding 的已知限制
- JPG quality 属性无效，压缩质量固定
- PNG compression 属性无效
"""

import base64
import os
import shutil
import tempfile
import OpenImageIO as oiio
import numpy as np

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Sequence

try:
    from .. import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ─── 类型别名 ───────────────────────────────────────────────────────────────


ImageFormat = Literal["jpg", "jpeg", "png"]

# 上传前压缩：最长边递减序列(像素)
_UPLOAD_MAX_DIMENSION_STEPS: tuple[int, ...] = (4096, 3072, 2048, 1536, 1024, 768, 512, 384, 256)


def guess_image_mime_type(path: str | Path) -> str:
    """根据扩展名返回 image/* MIME(用于 Base64 / API)。"""
    ext = Path(path).suffix.lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "webp":
        return "image/webp"
    if ext == "gif":
        return "image/gif"
    return "image/png"


# ─── OIIO 内部工具 ───────────────────────────────────────────────────────────


def _oiio_write(buf: oiio.ImageBuf, path: str) -> bool:
    """将 ImageBuf 写入文件，按扩展名自动推断格式。"""
    try:
        ok = buf.write(path)
        if not ok and buf.has_error:
            err = buf.geterror().strip()
            if err:
                logger.warning(f"_oiio_write error: {err}")
        return ok
    except Exception as e:
        logger.warning(f"_oiio_write exception: {e}")
        return False


def _oiio_new_buf(w: int, h: int, channels: int) -> oiio.ImageBuf:
    """创建指定尺寸的空 ImageBuf。"""
    spec = oiio.ImageSpec(w, h, channels, oiio.UINT8)
    return oiio.ImageBuf(spec)


def _oiio_buf_from_array(arr: np.ndarray) -> oiio.ImageBuf:
    """从 numpy 数组创建 ImageBuf（HWC）。"""
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    h, w = arr.shape[:2]
    ch = arr.shape[2] if arr.ndim == 3 else 1
    spec = oiio.ImageSpec(w, h, ch, oiio.UINT8)
    buf = oiio.ImageBuf(spec)
    roi = oiio.ROI(0, w, 0, h, 0, 1)
    buf.set_pixels(roi, arr)
    return buf


@dataclass
class PreparedUpload:
    """prepare_images_for_upload 的返回结果。

    paths: 与输入顺序一致的最终文件路径(可能为压缩后的临时文件)。
    temp_files: 需要调用方在适当时机删除的临时文件路径(例如请求发送完成后)。
    """

    paths: list[str]
    temp_files: list[str] = field(default_factory=list)

# ─── ImageProcessor ───────────────────────────────────────────────────────────


class ImageProcessor:
    """图像处理器

    支持图像缩放、JPG/PNG 格式转换，全程使用 OpenImageIO (OIIO)。

    Attributes:
        MAX_DIMENSION: 支持的最大边长 (4096)
        MAX_FILE_SIZE_MB: 最大文件大小 (20MB)
    """

    MAX_DIMENSION: int = 4096
    MAX_FILE_SIZE_MB: int = 20

    # ─── 公开 API ─────────────────────────────────────────────────────────────

    @classmethod
    def get_image_size(cls, filepath: str) -> tuple[int, int] | None:
        """获取图像尺寸"""
        try:
            buf = oiio.ImageBuf(filepath)
            if not buf.initialized:
                err = buf.geterror().strip()
                if err:
                    logger.warning(f"get_image_size failed: {err}")
                return None
            spec = buf.spec()
            return spec.width, spec.height
        except Exception as e:
            logger.warning(f"get_image_size failed: {e}")
            return None

    @classmethod
    def get_file_size_mb(cls, filepath: str) -> float:
        """获取文件大小（MB）"""
        return os.path.getsize(filepath) / (1024 * 1024)

    @classmethod
    def resize_by_max_dimension(
        cls,
        input_path: str,
        output_path: str,
        max_dimension: int | None = None,
    ) -> bool:
        """按最长边缩放图像"""
        if max_dimension is None:
            max_dimension = cls.MAX_DIMENSION

        size = cls.get_image_size(input_path)
        if size is None:
            return False
        w, h = size

        if max(w, h) <= max_dimension:
            return cls._copy_oiio(input_path, output_path)

        scale = max_dimension / max(w, h)
        return cls._resize_oiio(input_path, output_path, int(round(w * scale)), int(round(h * scale)))

    @classmethod
    def compress_by_quality(
        cls,
        input_path: str,
        output_path: str,
        max_size_mb: float | None = None,
        format: ImageFormat | None = None,
    ) -> bool:
        """质量压缩图像

        Args:
            max_size_mb: 目标大小（OIIO 不可控，保留接口兼容）
        """
        out_format = format or cls._detect_format(output_path)
        if out_format not in ("jpg", "jpeg", "png"):
            return cls._copy_file(input_path, output_path)
        return cls._write_oiio(input_path, output_path)

    @classmethod
    def compress_image_to_tempfile(
        cls,
        input_path: str,
        max_dimension: int | None = None,
        max_size_mb: float | None = None,
        format: ImageFormat | None = None,
    ) -> str:
        """压缩图片到临时文件"""
        default_fmt = Path(input_path).suffix.lower().lstrip(".")
        max_dimension = max_dimension or cls.MAX_DIMENSION
        out_fmt = format or cls._detect_format(input_path) or default_fmt

        tmp = tempfile.NamedTemporaryFile(suffix="." + out_fmt, delete=False)
        tmp.close()
        output_path = tmp.name

        try:
            if not cls.resize_by_max_dimension(input_path, output_path, max_dimension):
                cls._copy_file(input_path, output_path)
        except Exception as e:
            logger.warning(f"compress_image_to_tempfile failed: {e}")
            return ""

        return output_path

    @classmethod
    def compress_image(
        cls,
        input_path: str,
        output_path: str | None = None,
        max_dimension: int | None = None,
        max_size_mb: float | None = None,
        format: ImageFormat | None = None,
    ) -> str | None:
        """缩放 + 质量压缩

        Args:
            max_size_mb: 目标大小（OIIO 不可控，保留接口兼容）
        """
        if not output_path:
            output_path = input_path

        intermediate_path = cls.compress_image_to_tempfile(input_path, max_dimension, max_size_mb, format)
        if not intermediate_path:
            return None
        try:
            return shutil.copy2(intermediate_path, output_path)
        finally:
            try:
                os.remove(intermediate_path)
            except OSError:
                pass

    @classmethod
    def convert_format(cls, input_path: str, output_path: str) -> bool:
        """转换图像格式（按 output_path 扩展名自动识别）"""
        return cls._write_oiio(input_path, output_path)

    @classmethod
    def prepare_images_for_upload(
        cls,
        paths: Sequence[str | None],
        total_size_limit_bytes: int | None = None,
    ) -> PreparedUpload:
        """将多张图片在总字节数限制下做压缩(PNG 无透明可转 JPG + 按最长边递减缩放)。

        - 未超限：记录日志并原样返回路径。
        - 超限：循环尝试 PNG->JPG(仅全不透明 PNG)与按最长边缩放，每步打日志；仍超限则 ``ValueError``。

        Args:
            paths: 文件路径序列(忽略 None / 空串)。
            total_size_limit_bytes: 总大小上限，默认 20MB。

        Returns:
            PreparedUpload: ``paths`` 为与输入**非空路径**同序的结果；``temp_files`` 为临时文件列表。
        """
        limit = total_size_limit_bytes if total_size_limit_bytes is not None else cls.MAX_FILE_SIZE_MB * 1024 * 1024

        ordered: list[str] = []
        for raw in paths:
            if not raw:
                continue
            p = str(Path(raw))
            if not os.path.isfile(p):
                raise FileNotFoundError(p)
            ordered.append(p)

        if not ordered:
            return PreparedUpload(paths=[], temp_files=[])

        def total_bytes(ps: list[str]) -> int:
            return cls._total_paths_bytes(ps)

        initial_total = total_bytes(ordered)
        if initial_total <= limit:
            logger.info(
                "图片总大小未超限，无需压缩: 合计 %.2f MB (限制 %.2f MB)",
                initial_total / (1024 * 1024),
                limit / (1024 * 1024),
            )
            return PreparedUpload(paths=list(ordered), temp_files=[])

        current_paths = list(ordered)
        temp_files: list[str] = []
        png_jpg_attempted: set[int] = set()

        initial_snapshot: list[dict] = []
        for p in ordered:
            wh = cls.get_image_size(p)
            initial_snapshot.append(
                {
                    "path": p,
                    "size": os.path.getsize(p),
                    "wh": wh,
                }
            )

        def make_temp_path(suffix: str) -> str:
            t = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            t.close()
            temp_files.append(t.name)
            return t.name

        def replace_path_everywhere(old_path: str, new_path: str) -> None:
            """将所有引用同一磁盘路径的槽位更新为 new_path，并删除我们创建的 old 临时文件。"""
            nonlocal current_paths, temp_files
            if old_path == new_path:
                return
            if old_path in temp_files:
                try:
                    os.remove(old_path)
                except OSError:
                    pass
                temp_files.remove(old_path)
            for j in range(len(current_paths)):
                if current_paths[j] == old_path:
                    current_paths[j] = new_path

        safety = 0
        while total_bytes(current_paths) > limit and safety < 200:
            safety += 1
            progressed = False
            before_step = total_bytes(current_paths)

            # 1) PNG -> JPG(仅全不透明)
            for i, p in enumerate(current_paths):
                if i in png_jpg_attempted:
                    continue
                if Path(p).suffix.lower() != ".png":
                    png_jpg_attempted.add(i)
                    continue
                if not cls.png_is_fully_opaque(p):
                    logger.info("保留PNG(含透明通道): %s 跳过格式转换", p)
                    png_jpg_attempted.add(i)
                    continue
                tmp_jpg = make_temp_path(".jpg")
                if cls.convert_format(p, tmp_jpg):
                    old_sz = os.path.getsize(p)
                    new_sz = os.path.getsize(tmp_jpg)
                    pct = round((1.0 - new_sz / old_sz) * 100, 1) if old_sz else 0.0
                    logger.info(
                        "PNG->JPG: %s %.2f MB -> %.2f MB (-%s%%)",
                        Path(p).name,
                        old_sz / (1024 * 1024),
                        new_sz / (1024 * 1024),
                        pct,
                    )
                    replace_path_everywhere(p, tmp_jpg)
                    png_jpg_attempted.add(i)
                    progressed = True
                else:
                    try:
                        os.remove(tmp_jpg)
                    except OSError:
                        pass
                    if tmp_jpg in temp_files:
                        temp_files.remove(tmp_jpg)
                    png_jpg_attempted.add(i)

            if total_bytes(current_paths) <= limit:
                break

            # 2) 按最长边递减缩放
            cur_max = cls._current_max_edge(current_paths)
            target = cls._next_resize_target(cur_max)
            if target is None:
                break

            for i, p in enumerate(current_paths):
                wh = cls.get_image_size(p)
                if not wh:
                    continue
                w, h = wh
                if max(w, h) <= target:
                    continue
                suffix = Path(p).suffix.lower() or ".png"
                tmp_out = make_temp_path(suffix)
                before_sz = os.path.getsize(p)
                if cls.resize_by_max_dimension(p, tmp_out, max_dimension=target):
                    after_sz = os.path.getsize(tmp_out)
                    wh2 = cls.get_image_size(tmp_out)
                    w2, h2 = wh2 if wh2 else (0, 0)
                    logger.info(
                        "缩放: %s %dx%d (%.2f MB) -> %dx%d (%.2f MB) 最长边<=%d",
                        Path(p).name,
                        w,
                        h,
                        before_sz / (1024 * 1024),
                        w2,
                        h2,
                        after_sz / (1024 * 1024),
                        target,
                    )
                    replace_path_everywhere(p, tmp_out)
                    progressed = True
                else:
                    try:
                        os.remove(tmp_out)
                    except OSError:
                        pass
                    if tmp_out in temp_files:
                        temp_files.remove(tmp_out)

            after_step = total_bytes(current_paths)
            if not progressed and after_step >= before_step:
                break

        final_total = total_bytes(current_paths)
        if final_total > limit:
            raise ValueError(
                f"图片总大小在压缩后仍超过限制: {final_total / (1024 * 1024):.2f} MB > {limit / (1024 * 1024):.2f} MB"
            )

        init_mb = initial_total / (1024 * 1024)
        fin_mb = final_total / (1024 * 1024)
        saved = round((1.0 - final_total / initial_total) * 100, 1) if initial_total else 0.0
        logger.info(
            "压缩摘要: 原始合计 %.2f MB -> 压缩后 %.2f MB (节省 %s%%)",
            init_mb,
            fin_mb,
            saved,
        )
        for i, snap in enumerate(initial_snapshot):
            orig_p = snap["path"]
            fin_p = current_paths[i]
            o_sz = snap["size"]
            f_sz = os.path.getsize(fin_p)
            o_wh = snap["wh"]
            f_wh = cls.get_image_size(fin_p)
            o_wh_s = f"{o_wh[0]}x{o_wh[1]}" if o_wh else "?"
            f_wh_s = f"{f_wh[0]}x{f_wh[1]}" if f_wh else "?"
            ratio = round((1.0 - f_sz / o_sz) * 100, 1) if o_sz else 0.0
            logger.info(
                "  [%d] %s: %s %.2f MB (%s) -> %.2f MB (%s) 压缩率 %s%%",
                i,
                Path(orig_p).name,
                Path(orig_p).name,
                o_sz / (1024 * 1024),
                o_wh_s,
                f_sz / (1024 * 1024),
                f_wh_s,
                ratio,
            )

        return PreparedUpload(paths=current_paths, temp_files=temp_files)

    @classmethod
    def image_to_base64(
        cls,
        path: str,
        *,
        output_format: Literal["gemini", "raw", "data_url"] = "gemini",
    ) -> dict | str:
        """将图片文件编码为 Base64。

        Args:
            path: 图片路径。
            output_format:
                - gemini: ``{"inline_data": {"mime_type", "data"}}``
                - raw: 纯 base64 字符串
                - data_url: ``data:image/...;base64,...``
        """
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(path)
        mime = guess_image_mime_type(p)
        raw_b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        size_mb = round(len(raw_b64) / (1024 * 1024), 2)
        logger.info(f"image_to_base64: mime={mime} base64_size_mb={size_mb} path={path}")
        if output_format == "gemini":
            return {"inline_data": {"mime_type": mime, "data": raw_b64}}
        if output_format == "raw":
            return raw_b64
        return f"data:{mime};base64,{raw_b64}"


    @classmethod
    def _total_paths_bytes(cls, paths: Sequence[str]) -> int:
        return sum(os.path.getsize(p) for p in paths if p and os.path.isfile(p))

    # ─── OIIO 实现 ────────────────────────────────────────────────────────────

    @classmethod
    def _copy_oiio(cls, input_path: str, output_path: str) -> bool:
        """OIIO 读取再写出（用于无操作保存）"""
        buf = oiio.ImageBuf(input_path)
        if not buf.initialized:
            err = buf.geterror().strip()
            if err:
                logger.warning(f"_copy_oiio: cannot load {input_path}: {err}")
            return cls._copy_file(input_path, output_path)
        return _oiio_write(buf, output_path)

    @classmethod
    def _resize_oiio(cls, input_path: str, output_path: str, new_w: int, new_h: int) -> bool:
        """OIIO 图像缩放"""
        src = oiio.ImageBuf(input_path)
        if not src.initialized:
            err = src.geterror().strip()
            if err:
                logger.warning(f"_resize_oiio: cannot load {input_path}: {err}")
            else:
                logger.warning(f"_resize_oiio: cannot load {input_path}")
            return False

        dst = _oiio_new_buf(new_w, new_h, src.spec().nchannels)
        if not dst.initialized:
            return False

        oiio.ImageBufAlgo.resize(dst, src)
        if dst.has_error:
            logger.warning(f"resize error: {dst.geterror()}")

        return _oiio_write(dst, output_path)

    @classmethod
    def _write_oiio(cls, input_path: str, output_path: str) -> bool:
        """OIIO 读取再写出（用于格式转换或质量压缩）"""
        buf = oiio.ImageBuf(input_path)
        if not buf.initialized:
            err = buf.geterror().strip()
            if err:
                logger.warning(f"_write_oiio: cannot load {input_path}: {err}")
            return cls._copy_file(input_path, output_path)
        return _oiio_write(buf, output_path)

    # ─── 工具方法 ─────────────────────────────────────────────────────────────

    @classmethod
    def _detect_format(cls, filepath: str) -> ImageFormat | None:
        """根据文件扩展名推断格式"""
        ext = Path(filepath).suffix.lower().lstrip(".")
        if ext in ("jpg", "jpeg", "png"):
            return ext  # type: ignore
        return None

    @classmethod
    def _copy_file(cls, src: str, dst: str) -> bool:
        try:
            shutil.copy2(src, dst)
            return True
        except Exception as e:
            logger.warning(f"_copy_file failed: {e}")
            return False


# ─── 测试 ───────────────────────────────────────────────────────────────────


class ImageProcessorTests:
    """ImageProcessor 单元测试（仅在直接运行本文件时执行）"""

    @staticmethod
    def _create_test_image(
        output_path: str,
        width: int = 512,
        height: int = 512,
        channels: int = 3,
        pattern: str = "gradient",
    ) -> str:
        """生成测试用图片（纯 OIIO）"""
        if pattern == "gradient":
            row = np.linspace(0, 255, width, dtype=np.uint8)
            pixels = np.stack([row] * height, axis=0)
            if channels == 3:
                pixels = np.stack([pixels, pixels * 0, pixels * 0], axis=-1)
            else:
                alpha = np.full((height, width), 255, dtype=np.uint8)
                pixels = np.stack([pixels, pixels * 0, pixels * 0, alpha], axis=-1)
        elif pattern == "random":
            pixels = np.random.randint(0, 256, (height, width, channels), dtype=np.uint8)
        else:
            color = [200, 100, 50, 255][:channels]
            pixels = np.full((height, width, channels), color, dtype=np.uint8)

        buf = _oiio_buf_from_array(pixels)
        _oiio_write(buf, output_path)
        return output_path

    @classmethod
    def run(cls) -> bool:
        """运行全部测试"""
        test_dir = tempfile.mkdtemp(prefix="image_processor_test_")
        print(f"[TEST] temp dir: {test_dir}")

        def pass_(condition: bool, msg: str) -> None:
            if not condition:
                raise AssertionError(f"FAILED: {msg}")
            print(f"  PASS  {msg}")

        def pass_equal(a, b, msg: str) -> None:
            if a != b:
                raise AssertionError(f"FAILED: {msg}  ({a!r} != {b!r})")
            print(f"  PASS  {msg}  ({a!r} == {b!r})")

        def pass_exists(path: str, msg: str) -> None:
            if not os.path.exists(path):
                raise AssertionError(f"FAILED: {msg}  (file not found: {path})")
            print(f"  PASS  {msg}  ({os.path.basename(path)})")

        try:
            # test_get_image_size
            print("\n=== test_get_image_size ===")
            img_1k = os.path.join(test_dir, "img_1k.png")
            cls._create_test_image(img_1k, 1024, 768, channels=3, pattern="gradient")
            w, h = ImageProcessor.get_image_size(img_1k)
            pass_equal(w, 1024, "width")
            pass_equal(h, 768, "height")

            # test_get_file_size_mb
            print("\n=== test_get_file_size_mb ===")
            size_mb = ImageProcessor.get_file_size_mb(img_1k)
            pass_(0 < size_mb < 5, f"file size reasonable ({size_mb:.3f} MB)")

            # test_resize_downscale
            print("\n=== test_resize_downscale ===")
            img_8k = os.path.join(test_dir, "img_8k.png")
            cls._create_test_image(img_8k, 8192, 4096, channels=3, pattern="random")
            out = os.path.join(test_dir, "resized.png")
            ok = ImageProcessor.resize_by_max_dimension(img_8k, out, max_dimension=4096)
            pass_(ok, "resize returns True")
            pass_exists(out, "output file created")
            w2, h2 = ImageProcessor.get_image_size(out)
            pass_equal(max(w2, h2), 4096, "longest side == 4096")

            # test_resize_noop
            print("\n=== test_resize_noop ===")
            img_small = os.path.join(test_dir, "img_small.png")
            cls._create_test_image(img_small, 512, 512, channels=3, pattern="solid")
            out_small = os.path.join(test_dir, "small_noop.png")
            ok = ImageProcessor.resize_by_max_dimension(img_small, out_small, max_dimension=4096)
            pass_(ok, "noop returns True")
            w3, h3 = ImageProcessor.get_image_size(out_small)
            pass_equal(w3, 512, "width unchanged")
            pass_equal(h3, 512, "height unchanged")

            # test_compress_jpg
            print("\n=== test_compress_jpg ===")
            large_jpg = os.path.join(test_dir, "large.jpg")
            cls._create_test_image(large_jpg, 2048, 2048, channels=3, pattern="random")
            out_jpg = os.path.join(test_dir, "compressed.jpg")
            ok = ImageProcessor.compress_by_quality(large_jpg, out_jpg, max_size_mb=0.5)
            pass_(ok, "compress returns True")
            pass_exists(out_jpg, "compressed file created")
            sz_jpg = ImageProcessor.get_file_size_mb(out_jpg)
            pass_(0 < sz_jpg < 20, f"JPG size reasonable ({sz_jpg:.2f} MB)")

            # test_compress_png
            print("\n=== test_compress_png ===")
            large_png = os.path.join(test_dir, "large.png")
            cls._create_test_image(large_png, 2048, 2048, channels=4, pattern="gradient")
            out_png = os.path.join(test_dir, "compressed.png")
            ok = ImageProcessor.compress_by_quality(large_png, out_png, max_size_mb=2.0)
            pass_(ok, "PNG compress returns True")
            pass_exists(out_png, "compressed file created")

            # test_compress_image_pipeline
            print("\n=== test_compress_image_pipeline ===")
            huge_png = os.path.join(test_dir, "huge.png")
            cls._create_test_image(huge_png, 8192, 8192, channels=3, pattern="random")
            out_pipeline = os.path.join(test_dir, "pipeline_out.png")
            result = ImageProcessor.compress_image(huge_png, output_path=out_pipeline, max_dimension=4096, max_size_mb=5.0)
            pass_(result is not None, "returns output path")
            pass_exists(result, "pipeline output exists")
            w_final, h_final = ImageProcessor.get_image_size(result)
            pass_equal(max(w_final, h_final), 4096, "longest side == 4096")
            # OIIO PNG 压缩不可控，仅验证文件存在
            pass_(ImageProcessor.get_file_size_mb(result) < 50, f"output < 50 MB ({ImageProcessor.get_file_size_mb(result):.2f} MB)")

            # test_convert_format
            print("\n=== test_convert_format ===")
            src_png = os.path.join(test_dir, "src_for_convert.png")
            cls._create_test_image(src_png, 512, 512, channels=3, pattern="solid")
            out_jpg2 = os.path.join(test_dir, "converted.jpg")
            ok = ImageProcessor.convert_format(src_png, out_jpg2)
            pass_(ok, "PNG->JPG returns True")
            pass_exists(out_jpg2, "JPG file created")

            out_png2 = os.path.join(test_dir, "converted_back.png")
            ok = ImageProcessor.convert_format(out_jpg2, out_png2)
            pass_(ok, "JPG->PNG returns True")
            pass_exists(out_png2, "PNG file created")

            # test_nonexistent
            print("\n=== test_nonexistent_file ===")
            size = ImageProcessor.get_image_size("/__nonexistent_12345__.png")
            pass_equal(size, None, "nonexistent returns None")

            print("\n" + "=" * 60)
            print("ALL TESTS PASSED")
            print("=" * 60)
            return True

        except Exception as e:
            print(f"\nTEST FAILED: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            print(f"\n[TEST] cleaned: {test_dir}")


def register():
    pass


def unregister():
    pass


if __name__ == "__main__":
    ImageProcessorTests.run()
