"""图像处理工具模块

提供图像缩放、JPG/PNG 格式转换等常用功能。
全程使用 OpenImageIO (OIIO)，不依赖 Pillow 等外部图像库。

注意：Blender OIIO binding 的已知限制
- JPG quality 属性无效，压缩质量固定
- PNG compression 属性无效
"""

import os
import shutil
import tempfile
import OpenImageIO as oiio
import numpy as np

from pathlib import Path
from typing import Literal

try:
    from .. import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ─── 类型别名 ───────────────────────────────────────────────────────────────


ImageFormat = Literal["jpg", "jpeg", "png"]


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

        default_fmt = Path(input_path).suffix.lower().lstrip(".")
        max_dimension = max_dimension or cls.MAX_DIMENSION
        out_fmt = format or cls._detect_format(output_path) or default_fmt

        tmp = tempfile.NamedTemporaryFile(suffix="." + out_fmt, delete=False)
        intermediate_path = tmp.name
        tmp.close()

        try:
            if not cls.resize_by_max_dimension(input_path, intermediate_path, max_dimension):
                cls._copy_file(input_path, intermediate_path)
            cls._write_oiio(intermediate_path, output_path)
        finally:
            try:
                os.remove(intermediate_path)
            except OSError:
                pass

        return output_path if os.path.exists(output_path) else None

    @classmethod
    def convert_format(cls, input_path: str, output_path: str) -> bool:
        """转换图像格式（按 output_path 扩展名自动识别）"""
        return cls._write_oiio(input_path, output_path)

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
