"""任务进度估算器

提供基于历史任务时间的智能进度估算功能。
"""

import math
from typing import Dict
from collections import deque
from ...logger import logger


class TaskProgressEstimator:
    """任务进度估算器

    功能：
    - 根据历史任务时间智能估算当前进度
    - 首次运行使用60秒基准，之后使用历史平均
    - 所有 Client 共享数据，使用越多越准确
    """

    # 类变量：所有 Client 共享的模型历史时间记录
    _model_history_times: Dict[str, deque] = {}
    _max_history_count = 10  # 每个模型最多保存 10 次历史记录
    _default_estimate_time = 60.0  # 默认估算时间（秒）

    @classmethod
    def record_task_completion(cls, model_name: str, elapsed_time: float):
        if not model_name or elapsed_time <= 0:
            return

        # 初始化模型的历史记录队列
        if model_name not in cls._model_history_times:
            cls._model_history_times[model_name] = deque(maxlen=cls._max_history_count)

        # 添加新记录（自动限制队列长度）
        cls._model_history_times[model_name].append(elapsed_time)
        logger.debug(f"Recorded task time for {model_name}: {elapsed_time:.2f}s (history count: {len(cls._model_history_times[model_name])})")

    @classmethod
    def estimate_progress(cls, model_name: str, current_elapsed_time: float) -> float:
        if current_elapsed_time <= 0:
            return 0.0

        # 获取估算基准时间
        estimated_total_time = cls._get_estimated_time(model_name)

        # 计算进度比例
        progress_ratio = current_elapsed_time / estimated_total_time

        progress = 0.99 * (1 - math.exp(-2 * progress_ratio))  # 指数平滑

        return min(progress, 0.99)

    @classmethod
    def _get_estimated_time(cls, model_name: str) -> float:
        # 如果没有历史记录，使用默认值
        if model_name not in cls._model_history_times or not cls._model_history_times[model_name]:
            return cls._default_estimate_time

        # 计算历史平均时间
        history = cls._model_history_times[model_name]
        avg_time = sum(history) / len(history)

        return avg_time

    @classmethod
    def get_statistics(cls, model_name: str) -> dict:
        if model_name not in cls._model_history_times or not cls._model_history_times[model_name]:
            return {
                "count": 0,
                "avg_time": cls._default_estimate_time,
                "min_time": 0,
                "max_time": 0,
            }

        history = list(cls._model_history_times[model_name])
        return {
            "count": len(history),
            "avg_time": sum(history) / len(history),
            "min_time": min(history),
            "max_time": max(history),
        }
