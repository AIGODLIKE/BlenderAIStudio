import gpu
import OpenImageIO as oiio
from pathlib import Path

ICON_PATH = Path(__file__).parent.joinpath("icons")


class TexturePool:
    TEXTURE_MAP: dict[str, gpu.types.GPUTexture] = {}
    TEXTURE_ID_MAP: dict[int, gpu.types.GPUTexture] = {}

    @staticmethod
    def read_image_to_tex(file_path):
        file_path = Path(file_path)
        if not file_path.exists():
            file_path = ICON_PATH.joinpath(f"{file_path}.png")
        if not file_path.exists():
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
    def get_tex(cls, tex_id) -> gpu.types.GPUTexture | None:
        return cls.TEXTURE_ID_MAP.get(tex_id, None)
