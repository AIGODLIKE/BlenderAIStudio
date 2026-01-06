"""
SequenceTask - 顺序任务组合器

用于将多个 Task 按顺序组合执行，支持：
- 子任务顺序执行
- 进度聚合
- 数据传递
- 失败处理策略
- 取消传播

使用示例：
    # 创建子任务
    task1 = GeminiImageGenerationTask(...)
    task2 = GeminiImageEditTask(...)
    task3 = GeminiStyleTransferTask(...)

    # 创建顺序任务
    seq_task = SequenceTask(
        task_name="图像处理流水线",
        tasks=[task1, task2, task3],
        stop_on_failure=True,  # 遇到失败停止
        pass_data=True  # 传递数据到下一个任务
    )

    # 提交执行
    manager = TaskManager.get_instance()
    task_id = manager.submit_task(seq_task)
"""

from typing import List, Optional, Any, Dict, Callable

try:
    from .task import Task, TaskResult, TaskState
except ImportError:
    from task import Task, TaskResult, TaskState


class SequenceTask(Task):
    """
    顺序任务组合器

    将多个子任务按顺序执行，每个子任务完成后执行下一个。
    可以配置失败处理策略和数据传递方式。
    """

    def __init__(
        self,
        task_name: str,
        tasks: List[Task],
        stop_on_failure: bool = True,
        pass_data: bool = False,
        data_transformer: Optional[Callable[[Any, Task], Dict[str, Any]]] = None,
    ):
        """
        初始化顺序任务

        Args:
            task_name: 任务名称
            tasks: 子任务列表（按执行顺序）
            stop_on_failure: 遇到失败是否停止（False=继续执行后续任务）
            pass_data: 是否将前一个任务的结果传递给下一个任务
            data_transformer: 数据转换器函数，用于自定义如何将前一个任务的结果
                            转换为下一个任务的参数。签名: (prev_result, next_task) -> dict
        """
        super().__init__(task_name)

        if not tasks:
            raise ValueError("tasks 列表不能为空")

        self.tasks = tasks
        self.stop_on_failure = stop_on_failure
        self.pass_data = pass_data
        self.data_transformer = data_transformer

        # 子任务执行结果
        self.task_results: List[Optional[TaskResult]] = [None] * len(tasks)

        # 当前执行到的子任务索引
        self.current_task_index: int = -1

        # 设置总步骤数（所有子任务的步骤数之和）
        total_steps = sum(task.progress.total_steps for task in tasks)
        self.progress.total_steps = total_steps

        # 为每个子任务注册回调，聚合进度
        self._setup_subtask_callbacks()

    def _setup_subtask_callbacks(self) -> None:
        """为所有子任务设置进度回调"""
        for i, task in enumerate(self.tasks):
            # 计算该任务之前所有任务的步骤总数
            steps_before = sum(t.progress.total_steps for t in self.tasks[:i])

            def make_progress_callback(task_index: int, offset: int):
                def on_progress(event_data):
                    # 聚合进度：前面任务的总步骤 + 当前任务的进度
                    progress = event_data["progress"]
                    aggregated_step = offset + progress["current_step"]

                    # 更新 SequenceTask 的进度
                    self.update_progress(
                        step=aggregated_step,
                        message=f"[{task_index + 1}/{len(self.tasks)}] {progress['message']}",
                        details={
                            "current_task_index": task_index,
                            "current_task_name": self.tasks[task_index].task_name,
                            "subtask_progress": progress,
                        },
                    )

                return on_progress

            # 注册回调
            task.register_callback("progress_updated", make_progress_callback(i, steps_before))

    def prepare(self) -> bool:
        """
        准备阶段 - 验证所有子任务

        Returns:
            准备成功返回 True
        """
        try:
            self.update_progress(0, "准备顺序任务...")

            # 验证子任务列表
            if not self.tasks:
                self.update_progress(message="错误: 没有子任务")
                return False

            # 检查所有子任务的状态
            for i, task in enumerate(self.tasks):
                if task.state != TaskState.PENDING:
                    self.update_progress(message=f"警告: 子任务 {i + 1} ({task.task_name}) 状态不是 PENDING")

            self.update_progress(message=f"准备完成，共 {len(self.tasks)} 个子任务")
            return True

        except Exception as e:
            self.update_progress(message=f"准备失败: {str(e)}")
            return False

    def execute(self) -> TaskResult:
        """
        执行阶段 - 按顺序执行所有子任务

        Returns:
            TaskResult 对象
        """
        completed_count = 0
        failed_count = 0
        cancelled_count = 0

        all_results = []
        previous_result = None

        try:
            for i, task in enumerate(self.tasks):
                # 检查是否被取消
                if self.is_cancelled():
                    self.update_progress(message=f"顺序任务被取消（已完成 {completed_count}/{len(self.tasks)} 个子任务）")
                    return TaskResult.failure_result(Exception("SequenceTask cancelled"), f"顺序任务被取消，已完成 {completed_count} 个子任务")

                self.current_task_index = i
                self.update_progress(message=f"开始执行子任务 {i + 1}/{len(self.tasks)}: {task.task_name}")

                # 如果启用数据传递，将前一个任务的结果传递给当前任务
                if self.pass_data and previous_result is not None and previous_result.is_success():
                    self._apply_data_to_task(previous_result, task)

                # 执行子任务（调用内部 _run 方法，包含完整生命周期）
                result = task._run()
                self.task_results[i] = result
                all_results.append(result)

                # 处理执行结果
                if result.is_success():
                    completed_count += 1
                    previous_result = result
                    self.update_progress(message=f"子任务 {i + 1} 完成: {task.task_name}")
                elif task.state == TaskState.CANCELLED:
                    cancelled_count += 1
                    self.update_progress(message=f"子任务 {i + 1} 被取消: {task.task_name}")
                    if self.stop_on_failure:
                        break
                else:
                    failed_count += 1
                    self.update_progress(message=f"子任务 {i + 1} 失败: {task.task_name} - {result.error_message}")
                    if self.stop_on_failure:
                        break

            # 构建最终结果
            success = failed_count == 0 and cancelled_count == 0

            result_data = {
                "total_tasks": len(self.tasks),
                "completed": completed_count,
                "failed": failed_count,
                "cancelled": cancelled_count,
                "results": all_results,
                "final_result": previous_result.data if previous_result and previous_result.is_success() else None,
            }

            metadata = {
                "stop_on_failure": self.stop_on_failure,
                "pass_data": self.pass_data,
                "task_names": [t.task_name for t in self.tasks],
                "elapsed_times": [t.get_elapsed_time() for t in self.tasks],
            }

            if success:
                return TaskResult.success_result(data=result_data, metadata=metadata)
            else:
                error_msg = f"顺序任务未全部完成: {completed_count} 完成, {failed_count} 失败, {cancelled_count} 取消"
                return TaskResult.failure_result(Exception("SequenceTask partial failure"), error_msg, metadata={**metadata, **result_data})

        except Exception as e:
            error_msg = f"顺序任务执行异常: {str(e)}"
            self.update_progress(message=error_msg)
            return TaskResult.failure_result(e, error_msg)

    def cleanup(self) -> None:
        """
        清理资源 - 清理所有子任务
        """
        for task in self.tasks:
            try:
                task.cleanup()
            except Exception as e:
                print(f"[SequenceTask] 清理子任务失败 {task.task_name}: {e}")

    def cancel(self) -> bool:
        """
        取消任务 - 取消当前任务和所有未执行的子任务

        Returns:
            是否成功取消
        """
        success = super().cancel()

        if success:
            # 取消当前正在执行的任务
            if 0 <= self.current_task_index < len(self.tasks):
                current_task = self.tasks[self.current_task_index]
                current_task.cancel()

            # 取消所有未执行的任务
            for i in range(self.current_task_index + 1, len(self.tasks)):
                self.tasks[i].cancel()

        return success

    def _apply_data_to_task(self, previous_result: TaskResult, next_task: Task) -> None:
        """
        将前一个任务的结果应用到下一个任务

        Args:
            previous_result: 前一个任务的结果
            next_task: 下一个任务
        """
        if self.data_transformer:
            # 使用自定义转换器
            try:
                transformed_data = self.data_transformer(previous_result.data, next_task)
                # 将转换后的数据作为属性设置到任务上
                for key, value in transformed_data.items():
                    if hasattr(next_task, key):
                        setattr(next_task, key, value)
            except Exception as e:
                print(f"[SequenceTask] 数据转换失败: {e}")
        else:
            # 默认行为：尝试将结果数据设置为 next_task 的 input_data 属性
            if hasattr(next_task, "input_data"):
                next_task.input_data = previous_result.data

    def get_subtask_results(self) -> List[Optional[TaskResult]]:
        """
        获取所有子任务的结果

        Returns:
            子任务结果列表
        """
        return self.task_results.copy()

    def get_completed_tasks(self) -> List[Task]:
        """
        获取已完成的子任务列表

        Returns:
            已完成的子任务列表
        """
        return [task for i, task in enumerate(self.tasks) if self.task_results[i] and self.task_results[i].is_success()]

    def get_failed_tasks(self) -> List[Task]:
        """
        获取失败的子任务列表

        Returns:
            失败的子任务列表
        """
        return [task for i, task in enumerate(self.tasks) if self.task_results[i] and not self.task_results[i].is_success()]
