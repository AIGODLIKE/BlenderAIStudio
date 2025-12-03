"""
volcengine
https://www.volcengine.com/docs/82379/1541523?lang=zh
火山引擎

curl -X POST https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedream-4-0-250828",
    "prompt": "星际穿越，黑洞，黑洞里冲出一辆快支离破碎的复古列车，抢视觉冲击力，电影大片，末日既视感，动感，对比色，oc渲染，光线追踪，动态模糊，景深，超现实主义，深蓝，画面通过细腻的丰富的色彩层次塑造主体与场景，质感真实，暗黑风背景的光影效果营造出氛围，整体兼具艺术幻想感，夸张的广角透视效果，耀光，反射，极致的光影，强引力，吞噬",
    "size": "2K",
    "sequential_image_generation": "disabled",
    "stream": false,
    "response_format": "url",
    "watermark": true
}'

不同模型支持的图片生成能力简介
doubao-seedream-4.0
    生成组图（组图：基于您输入的内容，生成的一组内容关联的图片；需配置sequential_image_generation为auto）
    多图生组图，根据您输入的 多张参考图片（2-10）+文本提示词 生成一组内容关联的图片（输入的参考图数量+最终生成的图片数量≤15张）。
    单图生组图，根据您输入的 单张参考图片+文本提示词 生成一组内容关联的图片（最多生成14张图片）。
    文生组图，根据您输入的 文本提示词 生成一组内容关联的图片（最多生成15张图片）。
    生成单图（配置sequential_image_generation为disabled）
    多图生图，根据您输入的 多张参考图片（2-10）+文本提示词 生成单张图片。
    单图生图，根据您输入的 单张参考图片+文本提示词 生成单张图片。
    文生图，根据您输入的 文本提示词 生成单张图片。
doubao-seedream-3.0-t2i
    文生图，根据您输入的 文本提示词 生成单张图片。
doubao-seededit-3.0-i2i
    图生图，根据您输入的 单张参考图片+文本提示词 生成单张图片。
"""
import os

import requests

api_key = os.environ.get('VOLCENGINE_API_KEY', '').strip()


class Volcengine:
    def __init__(self, api_key: str, api_secret: str):
        self.api_secret = api_secret
        self.url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

    def image(self, ):
        response = requests.post(self.url, headers=self.headers, json=payload, timeout=300)


if __name__ == "__main__":
    print("api_key", api_key)
