import gpu
import mimetypes
import numpy as np
import OpenImageIO as oiio
from pathlib import Path


ICON_PATH = Path(__file__).parent.joinpath("icons")


class TexturePool:
    TEXTURE_MAP: dict[str, gpu.types.GPUTexture] = {}
    TEXTURE_ID_MAP: dict[int, gpu.types.GPUTexture] = {}
    ANIMATED_TEXTURE_PLAYERS: dict[int, "AnimatedPlayer"] = {}

    @staticmethod
    def read_image_to_tex(file_path):
        file_path = Path(file_path)
        if not file_path.exists():
            file_path = ICON_PATH.joinpath(f"{file_path}.png")
        if not file_path.exists():
            file_path = ICON_PATH.joinpath("none.png")
        mime_type = mimetypes.guess_type(file_path.name)[0]
        if not mime_type or not mime_type.startswith("image/"):
            file_path = ICON_PATH.joinpath("none.png")
        buf = oiio.ImageBuf(file_path.as_posix())
        spec = buf.spec()
        pixels = buf.get_pixels(oiio.FLOAT)
        gpu_buf = gpu.types.Buffer("FLOAT", (spec.width, spec.height, spec.nchannels), pixels)
        tex_format_map = {
            1: "DEPTH_COMPONENT16",
            2: "RG16F",
            3: "RGB16F",
            4: "RGBA8",
        }
        tex_format = tex_format_map[spec.nchannels]
        gpu_tex = gpu.types.GPUTexture(gpu_buf.dimensions[:2], format=tex_format, data=gpu_buf)
        return gpu_tex

    @classmethod
    def push_tex(cls, tex):
        cls.TEXTURE_ID_MAP[id(tex)] = tex
        return id(tex)

    @classmethod
    def pop_tex(cls, tex_id):
        cls.TEXTURE_ID_MAP.pop(tex_id, None)

    @classmethod
    def get_tex_id(cls, img) -> int:
        if img not in cls.TEXTURE_MAP:
            cls.TEXTURE_MAP[img] = cls.read_image_to_tex(img)
        gpu_tex = cls.TEXTURE_MAP[img]
        gpu_tex_id = id(gpu_tex)
        cls.TEXTURE_ID_MAP[gpu_tex_id] = gpu_tex
        return gpu_tex_id

    @classmethod
    def get_animated_tex_id(cls, img, time) -> int:
        if img not in cls.ANIMATED_TEXTURE_PLAYERS:
            cls.ANIMATED_TEXTURE_PLAYERS[img] = AnimatedPlayer(img)
        player = cls.ANIMATED_TEXTURE_PLAYERS[img]
        gpu_tex = player.get_frame(time)

        cls.TEXTURE_MAP[img] = gpu_tex
        gpu_tex_id = id(gpu_tex)
        cls.TEXTURE_ID_MAP[gpu_tex_id] = gpu_tex

        gpu_tex_id = cls.get_tex_id(img)
        return gpu_tex_id

    @classmethod
    def get_tex(cls, tex_id) -> gpu.types.GPUTexture | None:
        return cls.TEXTURE_ID_MAP.get(tex_id, None)


class AnimatedPlayer:
    """
    动画播放器 - 高效管理和播放 WebP 动画

    特性:
    - 帧缓存池：避免重复复制帧数据
    - GPU 纹理缓存：复用已创建的 GPU 纹理
    - 时间索引：根据时间快速定位帧
    - 循环播放支持
    """

    def __init__(self, file_path: str):
        """
        初始化动画播放器

        Args:
            file_path: WebP 动画文件路径
        """
        try:
            from ....External.animated_image_decoder import WebPDecoder
        except ImportError:
            from decoder import WebPDecoder

        # 解码动画
        self.decoder = WebPDecoder()
        self.animation = self.decoder.decode(file_path)

        if not self.animation:
            raise ValueError(f"无法解码动画文件: {file_path}")

        # 基本信息
        self.width = self.animation.width
        self.height = self.animation.height
        self.frame_count = len(self.animation.frames)

        # 计算累积时间，用于时间索引
        self._cumulative_times = [0.0]
        total_time = 0.0
        for delay in self.animation.delays:
            total_time += delay
            self._cumulative_times.append(total_time)

        self.total_duration = total_time

        # 帧数据缓存池 - 使用 numpy array 避免重复复制
        self._frame_cache: dict[int, np.ndarray] = {}

        # GPU 纹理缓存池
        self._texture_cache: dict[int, gpu.types.GPUTexture] = {}

        # 当前帧索引（用于优化）
        self._current_frame_index = 0

    def _get_frame_index_by_time(self, time: float) -> int:
        """
        根据时间获取对应的帧索引

        Args:
            time: 时间（秒），支持循环播放

        Returns:
            帧索引 (0 到 frame_count-1)
        """
        if self.total_duration <= 0:
            return 0

        # 处理循环播放
        time = time % self.total_duration

        # 二分查找对应的帧
        left, right = 0, self.frame_count
        while left < right:
            mid = (left + right) // 2
            if self._cumulative_times[mid] <= time:
                left = mid + 1
            else:
                right = mid

        frame_index = max(0, left - 1)
        return min(frame_index, self.frame_count - 1)

    def _get_frame_data_as_numpy(self, frame_index: int) -> np.ndarray:
        """
        获取帧数据作为 numpy array（使用缓存）

        Args:
            frame_index: 帧索引

        Returns:
            numpy array，形状为 (height, width, 4)，数据类型为 uint8
        """
        # 检查缓存
        if frame_index in self._frame_cache:
            return self._frame_cache[frame_index]

        # 从原始字节数据创建 numpy array
        frame_array = self.animation.frames[frame_index]

        # 缓存帧数据
        self._frame_cache[frame_index] = frame_array

        return frame_array

    def get_frame(self, time: float):
        """
        根据时间获取对应帧的 GPU 纹理

        Args:
            time: 时间（秒），自动处理循环播放

        Returns:
            GPU 纹理对象
        """
        # 获取帧索引
        frame_index = self._get_frame_index_by_time(time)
        self._current_frame_index = frame_index

        # 检查纹理缓存
        if frame_index in self._texture_cache:
            return self._texture_cache[frame_index]

        # 获取帧数据
        frame_data = self._get_frame_data_as_numpy(frame_index)

        # 创建 GPU 纹理
        buffer = gpu.types.Buffer("FLOAT", frame_data.size, frame_data.flatten().astype(np.float32) / 255.0)
        texture = gpu.types.GPUTexture((self.width, self.height), format="RGBA8", data=buffer)

        # 缓存纹理
        self._texture_cache[frame_index] = texture

        return texture

    def get_frame_by_index(self, frame_index: int):
        """
        直接通过帧索引获取 GPU 纹理

        Args:
            frame_index: 帧索引 (0 到 frame_count-1)

        Returns:
            GPU 纹理对象（Blender 环境）或 MockGPUTexture（非 Blender 环境）
        """
        frame_index = max(0, min(frame_index, self.frame_count - 1))

        # 检查纹理缓存
        if frame_index in self._texture_cache:
            return self._texture_cache[frame_index]

        # 获取帧数据
        frame_data = self._get_frame_data_as_numpy(frame_index)

        # 创建 GPU 纹理
        buffer = gpu.types.Buffer("FLOAT", frame_data.size, frame_data.flatten().astype(np.float32) / 255.0)
        texture = gpu.types.GPUTexture((self.width, self.height), format="RGBA8", data=buffer)

        # 缓存纹理
        self._texture_cache[frame_index] = texture

        return texture

    def get_frame_data(self, time: float) -> np.ndarray:
        """
        获取帧数据作为 numpy array（不创建 GPU 纹理）

        Args:
            time: 时间（秒）

        Returns:
            numpy array，形状为 (height, width, 4)
        """
        frame_index = self._get_frame_index_by_time(time)
        return self._get_frame_data_as_numpy(frame_index)

    def preload_all_frames(self):
        """
        预加载所有帧到缓存（适用于小动画）
        """
        for i in range(self.frame_count):
            self._get_frame_data_as_numpy(i)

    def preload_all_textures(self):
        """
        预加载所有帧的 GPU 纹理（适用于小动画且需要流畅播放）
        警告：会占用较多 GPU 内存
        """
        for i in range(self.frame_count):
            self.get_frame_by_index(i)

    def clear_cache(self):
        """
        清理所有缓存（释放内存）
        """
        # 清理帧数据缓存
        self._frame_cache.clear()

        # 清理 GPU 纹理缓存
        for texture in self._texture_cache.values():
            # GPU 纹理会在 Python 对象被删除时自动释放
            pass
        self._texture_cache.clear()

    def get_info(self) -> dict:
        """
        获取动画信息

        Returns:
            包含动画信息的字典
        """
        return {
            "width": self.width,
            "height": self.height,
            "frame_count": self.frame_count,
            "total_duration": self.total_duration,
            "fps": self.frame_count / self.total_duration if self.total_duration > 0 else 0,
            "cached_frames": len(self._frame_cache),
            "cached_textures": len(self._texture_cache),
        }

    def __del__(self):
        """
        析构函数 - 清理资源
        """
        self.clear_cache()
        self.animation = None

    def __repr__(self) -> str:
        return f"AnimatedPlayer({self.width}x{self.height}, {self.frame_count} frames, {self.total_duration:.2f}s)"
