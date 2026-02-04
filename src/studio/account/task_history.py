from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    NONE = "NONE"
    SUCCESS = "SUCCESS"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"

    def is_success(self) -> bool:
        return self == self.SUCCESS

    def is_running(self) -> bool:
        return self == self.RUNNING

    def is_failed(self) -> bool:
        return self == self.FAILED

    def is_unknown(self) -> bool:
        return self == self.UNKNOWN

    def is_error(self) -> bool:
        return self == self.ERROR


@dataclass
class TaskStatusData:
    """任务状态数据（从 API 响应解析得到）

    这是临时的 DTO (Data Transfer Object)，用于在网络层和业务层之间传递数据。
    """

    task_id: str
    state: TaskStatus = TaskStatus.NONE
    urls: Optional[list[str]] = None  # 结果下载地址
    progress: float = 0.0
    error_message: str = ""


@dataclass
class TaskHistoryData:
    """
    任务历史数据（持久化模型）
    """

    state: TaskStatus = TaskStatus.NONE
    outputs: list[tuple[str, str]] = field(default_factory=list)  # [(mime_type, file_path), ...]
    progress: float = 0.0
    error_message: str = ""
    finished_at: float = 0.0
    task_id: str = ""
    result: list[tuple[str, bytes]] = field(default_factory=list)  # 原始结果数据（可选）


class AccountTaskHistory:
    """账户任务历史管理器

    职责：
    - 存储任务历史记录
    - 提供查询接口
    - 不包含业务逻辑（纯数据层）
    """

    def __init__(self):
        self.task_history_map: dict[str, TaskHistoryData] = {}

    def ensure_task_history(self, task_id: str) -> TaskHistoryData:
        if task_id not in self.task_history_map:
            self.task_history_map[task_id] = TaskHistoryData(
                state=TaskStatus.NONE,
                outputs=[],
                progress=0.0,
                error_message="",
                finished_at=0.0,
                task_id=task_id,
            )
        return self.task_history_map[task_id]

    def fetch_task_history(self, task_ids: list[str]) -> dict[str, TaskHistoryData]:
        result: dict[str, TaskHistoryData] = {}
        for task_id in task_ids:
            if task_id in self.task_history_map:
                result[task_id] = deepcopy(self.task_history_map[task_id])
        return result

    def get_task(self, task_id: str) -> Optional[TaskHistoryData]:
        return self.task_history_map.get(task_id)

    def find_needs_sync_tasks(self) -> list[TaskHistoryData]:
        return [t for t in self.task_history_map.values() if t.state in (TaskStatus.UNKNOWN, TaskStatus.RUNNING)]
