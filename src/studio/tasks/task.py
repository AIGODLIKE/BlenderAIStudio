"""

使用示例：
    # 1. 创建任务
    from .tasks import GeminiImageGenerationTask

    task = GeminiImageGenerationTask(
        api_key="your-api-key",
        image_path="/path/to/depth.png",
        user_prompt="1girl",
        width=1024,
        height=1024
    )

    # 2. 注册回调
    def on_progress(event_data):
        print(f"进度: {event_data['progress']['percentage']*100}%")

    task.register_callback("progress_updated", on_progress)

    # 3. 提交到管理器
    manager = TaskManager.get_instance()
    task_id = manager.submit_task(task)

    # 4. 查询任务状态
    task = manager.get_task(task_id)
    if task.is_finished():
        if task.result.is_success():
            image_data = task.result.get_data()
            print("任务完成！")
        else:
            error_msg = task.result.error_message
            print(f"任务失败: {error_msg}")
"""

import time
import uuid
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, Future


# ============================================================================
# 核心数据类
# ============================================================================


class TaskState(Enum):
    """任务状态枚举"""

    NONE = "none"  # 空
    PENDING = "pending"  # 等待执行
    PREPARING = "preparing"  # 准备中
    RUNNING = "running"  # 执行中
    PROCESSING = "processing"  # 后处理中
    COMPLETED = "completed"  # 成功完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 用户取消

    def get_display_name(self, lang: str = "zh") -> str:
        """获取状态显示名称"""
        names = {
            "zh": {
                TaskState.PENDING: "等待中",
                TaskState.PREPARING: "准备中",
                TaskState.RUNNING: "执行中",
                TaskState.PROCESSING: "处理中",
                TaskState.COMPLETED: "已完成",
                TaskState.FAILED: "失败",
                TaskState.CANCELLED: "已取消",
            },
            "en": {
                TaskState.PENDING: "Pending",
                TaskState.PREPARING: "Preparing",
                TaskState.RUNNING: "Running",
                TaskState.PROCESSING: "Processing",
                TaskState.COMPLETED: "Completed",
                TaskState.FAILED: "Failed",
                TaskState.CANCELLED: "Cancelled",
            },
        }
        names["zh_Hans"] = names["zh"]
        names["zh_CN"] = names["zh"]
        names["en_US"] = names["en"]
        return names.get(lang, names["en"]).get(self, self.value)

    def get_color(self) -> Tuple[float, float, float, float]:
        """获取状态对应的UI颜色 (RGBA)"""
        colors = {
            TaskState.PENDING: (0.5, 0.5, 0.5, 1.0),  # 灰色
            TaskState.PREPARING: (0.4, 0.6, 0.9, 1.0),  # 蓝色
            TaskState.RUNNING: (0.26, 0.81, 0.49, 1.0),  # 绿色
            TaskState.PROCESSING: (0.9, 0.7, 0.3, 1.0),  # 橙色
            TaskState.COMPLETED: (0.26, 0.81, 0.49, 1.0),  # 绿色
            TaskState.FAILED: (0.9, 0.3, 0.3, 1.0),  # 红色
            TaskState.CANCELLED: (0.6, 0.6, 0.6, 1.0),  # 深灰色
        }
        return colors.get(self, (1.0, 1.0, 1.0, 1.0))

    def is_terminal(self) -> bool:
        """是否为终止状态"""
        return self in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}

    def is_active(self) -> bool:
        """是否为活跃状态（未完成）"""
        return not self.is_terminal()


@dataclass
class TaskProgress:
    """任务进度信息"""

    current_step: int = 0
    total_steps: int = 1
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def percentage(self) -> float:
        """完成百分比 (0.0-1.0)"""
        if self.total_steps <= 0:
            return 0.0
        return min(1.0, max(0.0, self.current_step / self.total_steps))

    def update(self, step: Optional[int] = None, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """更新进度信息"""
        if step is not None:
            self.current_step = step
        if message is not None:
            self.message = message
        if details is not None:
            self.details.update(details)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "percentage": self.percentage,
            "message": self.message,
            "details": self.details.copy(),
        }


@dataclass
class TaskResult:
    """任务执行结果"""

    success: bool
    data: Any = None
    error: Optional[Exception] = None
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_success(self) -> bool:
        """判断是否成功"""
        return self.success

    def get_data(self, default: Any = None) -> Any:
        """安全获取数据"""
        return self.data if self.success else default

    def get_error_info(self) -> Tuple[Optional[Exception], str]:
        """获取错误详情"""
        return self.error, self.error_message

    @classmethod
    def success_result(cls, data: Any, metadata: Optional[Dict[str, Any]] = None) -> "TaskResult":
        """创建成功结果"""
        return cls(success=True, data=data, metadata=metadata or {})

    @classmethod
    def failure_result(cls, error: Exception, message: str = "", metadata: Optional[Dict[str, Any]] = None) -> "TaskResult":
        """创建失败结果"""
        return cls(success=False, error=error, error_message=message or str(error), metadata=metadata or {})


# ============================================================================
# 抽象基类
# ============================================================================


class Task(ABC):
    """
    任务抽象基类

    定义所有任务的标准接口和生命周期管理。
    子类需要实现 prepare(), execute(), cleanup() 方法。
    """

    def __init__(self, task_name: str):
        """
        初始化任务

        Args:
            task_name: 任务名称
        """
        self.task_id: str = str(uuid.uuid4())
        self.task_name: str = task_name
        self.state: TaskState = TaskState.PENDING
        self.progress: TaskProgress = TaskProgress()
        self.result: Optional[TaskResult] = None

        # 时间戳
        self.created_at: float = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

        # 回调函数字典 {event_name: [callback_functions]}
        self._callbacks: Dict[str, List[Callable]] = {}

        # 取消标志
        self._cancelled: bool = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------------
    # 抽象方法 - 子类必须实现
    # ------------------------------------------------------------------------

    @abstractmethod
    def prepare(self) -> bool:
        """
        执行前准备

        用于：
        - 验证参数
        - 检查资源可用性
        - 预加载必要数据

        Returns:
            准备成功返回 True，失败返回 False
        """
        pass

    @abstractmethod
    def execute(self) -> TaskResult:
        """
        执行主要逻辑

        任务的核心方法，执行实际的工作。
        应在执行过程中调用 update_progress() 更新进度。

        Returns:
            TaskResult 对象
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """
        清理资源

        职责:
        - 关闭文件句柄
        - 释放网络连接
        - 删除临时文件
        - 释放内存

        无论任务成功或失败都会被调用
        """
        pass

    # ------------------------------------------------------------------------
    # 公共方法 - 提供给外部使用
    # ------------------------------------------------------------------------

    def cancel(self) -> bool:
        """
        取消任务

        Returns:
            如果任务可以被取消返回 True，否则返回 False
        """
        with self._lock:
            if self.state.is_terminal():
                return False
            self._cancelled = True
            return True

    def is_cancelled(self) -> bool:
        """检查任务是否被取消"""
        with self._lock:
            return self._cancelled

    def set_state(self, new_state: TaskState) -> None:
        """
        更新状态并触发回调

        Args:
            new_state: 新状态
        """
        with self._lock:
            old_state = self.state
            self.state = new_state

            # 更新时间戳
            if new_state == TaskState.RUNNING and self.started_at is None:
                self.started_at = time.time()
            elif new_state.is_terminal() and self.finished_at is None:
                self.finished_at = time.time()

        # 触发回调（在锁外执行，避免死锁）
        self._trigger_callback(
            "state_changed",
            {
                "old_state": old_state,
                "new_state": new_state,
                "task": self,
            },
        )

    def update_progress(self, step: Optional[int] = None, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """
        更新进度

        Args:
            step: 当前步骤编号
            message: 进度描述
            details: 额外详情
        """
        self.progress.update(step, message, details)
        self._trigger_callback(
            "progress_updated",
            {
                "progress": self.progress.to_dict(),
                "task": self,
            },
        )

    def register_callback(self, event: str, callback: Callable) -> None:
        """
        注册回调函数

        支持的事件：
        - state_changed: 状态改变
        - progress_updated: 进度更新
        - completed: 任务完成
        - failed: 任务失败

        Args:
            event: 事件名称
            callback: 回调函数 callback(event_data: dict)
        """
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def get_elapsed_time(self) -> float:
        """
        获取已用时间（秒）

        Returns:
            已用时间，如果未开始返回 0
        """
        if self.started_at is None:
            return 0.0
        end_time = self.finished_at if self.finished_at else time.time()
        return end_time - self.started_at

    def is_finished(self) -> bool:
        """是否已完成（成功/失败/取消）"""
        return self.state.is_terminal()

    def get_info(self) -> Dict[str, Any]:
        """
        获取任务信息摘要

        Returns:
            任务信息字典
        """
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "state": self.state.value,
            "state_display": self.state.get_display_name(),
            "progress": self.progress.to_dict(),
            "elapsed_time": self.get_elapsed_time(),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    # ------------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------------

    def _trigger_callback(self, event: str, event_data: Dict[str, Any]) -> None:
        """
        触发回调函数

        Args:
            event: 事件名称
            event_data: 事件数据
        """
        callbacks = self._callbacks.get(event, [])
        for callback in callbacks:
            try:
                callback(event_data)
            except Exception as e:
                # 回调失败不应该影响任务执行
                print(f"[Task] Callback error for event '{event}': {e}")

    def _run(self) -> TaskResult:
        """
        内部执行方法（由 TaskManager 调用）

        Returns:
            TaskResult 对象
        """
        try:
            # 检查是否已取消
            if self.is_cancelled():
                return TaskResult.failure_result(Exception("Task cancelled before execution"), "任务在执行前被取消")

            # 准备阶段
            self.set_state(TaskState.PREPARING)
            if not self.prepare():
                self.set_state(TaskState.FAILED)
                return TaskResult.failure_result(Exception("Task preparation failed"), "任务准备失败")

            # 检查是否被取消
            if self.is_cancelled():
                return TaskResult.failure_result(Exception("Task cancelled during preparation"), "任务在准备阶段被取消")

            # 执行阶段
            self.set_state(TaskState.RUNNING)
            result = self.execute()

            # 后处理阶段
            if result.is_success() and not self.is_cancelled():
                self.set_state(TaskState.PROCESSING)

            # 设置最终状态
            if self.is_cancelled():
                self.set_state(TaskState.CANCELLED)
                self._trigger_callback("cancelled", {"task": self, "result": None})
                return TaskResult.failure_result(Exception("Task cancelled during execution"), "任务在执行过程中被取消")
            elif result.is_success():
                self.set_state(TaskState.COMPLETED)
                self._trigger_callback("completed", {"task": self, "result": result})
            else:
                self.set_state(TaskState.FAILED)
                self._trigger_callback("failed", {"task": self, "result": result})

            self.result = result
            return result

        except Exception as e:
            self.set_state(TaskState.FAILED)
            result = TaskResult.failure_result(e, f"任务执行异常: {str(e)}")
            self.result = result
            self._trigger_callback("failed", {"task": self, "result": result})
            return result

        finally:
            # 清理资源
            try:
                self.cleanup()
            except Exception as e:
                print(f"[Task] Cleanup error: {e}")


# ============================================================================
# 任务管理器
# ============================================================================


class TaskManager:
    """
    任务管理器(单例)

    职责:
    - 任务的提交和调度
    - 线程池管理
    - 任务生命周期跟踪
    - 并发控制
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self, max_concurrent: int = 3):
        """
        初始化任务管理器

        Args:
            max_concurrent: 最大并发任务数
        """
        self.tasks: Dict[str, Task] = {}
        self.futures: Dict[str, Future] = {}
        self.max_concurrent = max_concurrent
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._shutdown = False

    @classmethod
    def get_instance(cls, max_concurrent: int = 3) -> "TaskManager":
        """
        获取单例实例

        Args:
            max_concurrent: 最大并发数（仅首次创建时有效）

        Returns:
            TaskManager 实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(max_concurrent)
        return cls._instance

    def submit_task(self, task: Task) -> str:
        if self._shutdown:
            raise RuntimeError("TaskManager has been shut down")

        task_id = task.task_id
        self.tasks[task_id] = task

        # 提交到线程池
        future = self.executor.submit(self._run_task, task)
        self.futures[task_id] = future

        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task:
            return task.cancel()
        return False

    def get_all_tasks(self) -> List[Task]:
        return list(self.tasks.values())

    def get_active_tasks(self) -> List[Task]:
        return [task for task in self.tasks.values() if task.state.is_active()]

    def get_finished_tasks(self) -> List[Task]:
        return [task for task in self.tasks.values() if task.is_finished()]

    def clear_finished_tasks(self) -> int:
        finished_ids = [tid for tid, task in self.tasks.items() if task.is_finished()]
        for task_id in finished_ids:
            self.tasks.pop(task_id, None)
            self.futures.pop(task_id, None)
        return len(finished_ids)

    def shutdown(self, wait: bool = True) -> None:
        """
        关闭管理器

        Args:
            wait: 是否等待所有任务完成
        """
        self._shutdown = True
        self.executor.shutdown(wait=wait)

    def _run_task(self, task: Task) -> TaskResult:
        try:
            return task._run()
        except Exception as e:
            # 处理未捕获的异常
            return self._handle_task_error(task, e)

    def _handle_task_error(self, task: Task, error: Exception) -> TaskResult:
        """
        统一错误处理

        Args:
            task: 任务对象
            error: 异常对象

        Returns:
            TaskResult
        """
        error_msg = f"任务执行错误: {str(error)}"
        print(f"[TaskManager] Task {task.task_id} error: {error}")

        task.set_state(TaskState.FAILED)
        result = TaskResult.failure_result(error, error_msg)
        task.result = result

        return result
