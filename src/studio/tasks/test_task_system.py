"""
Task 系统测试模块

用于验证 Task 系统的基本功能
"""

import time
from task import Task, TaskResult, TaskManager, TaskState


class DummyTask(Task):
    """测试用的虚拟任务"""

    def __init__(self, task_name: str = "测试任务", steps: int = 5, should_fail: bool = False):
        super().__init__(task_name)
        self.progress.total_steps = steps
        self.should_fail = should_fail

    def prepare(self) -> bool:
        """准备阶段"""
        self.update_progress(0, "准备中...")
        time.sleep(0.1)
        return True

    def execute(self) -> TaskResult:
        """执行阶段"""
        try:
            for i in range(1, self.progress.total_steps + 1):
                if self.is_cancelled():
                    return TaskResult.failure_result(Exception("Task cancelled"), "任务被取消")

                self.update_progress(i, f"执行步骤 {i}/{self.progress.total_steps}")
                time.sleep(0.2)

                # 模拟失败
                if self.should_fail and i == 3:
                    raise Exception("模拟的任务失败")

            return TaskResult.success_result(data={"message": "任务成功完成", "steps": self.progress.total_steps}, metadata={"elapsed": self.get_elapsed_time()})

        except Exception as e:
            return TaskResult.failure_result(e, f"执行失败: {str(e)}")

    def cleanup(self) -> None:
        """清理阶段"""
        print(f"[DummyTask] {self.task_name} 清理完成")


def test_basic_task():
    """测试基本任务执行"""
    print("\n=== 测试1: 基本任务执行 ===")

    task = DummyTask("基本测试任务", steps=3)

    # 注册回调
    def on_state_changed(event_data):
        print(f"状态变化: {event_data['old_state'].value} -> {event_data['new_state'].value}")

    def on_progress(event_data):
        progress = event_data["progress"]
        print(f"进度更新: {progress['percentage'] * 100:.0f}% - {progress['message']}")

    task.register_callback("state_changed", on_state_changed)
    task.register_callback("progress_updated", on_progress)

    # 提交任务
    manager = TaskManager.get_instance()
    task_id = manager.submit_task(task)

    # 等待完成
    while not task.is_finished():
        time.sleep(0.1)

    # 检查结果
    assert task.state == TaskState.COMPLETED
    assert task.result.is_success()
    print(f"✓ 任务完成，id: {task_id}, 耗时: {task.get_elapsed_time():.2f}s")
    print(f"✓ 结果数据: {task.result.get_data()}")


def test_task_failure():
    """测试任务失败"""
    print("\n=== 测试2: 任务失败处理 ===")

    task = DummyTask("失败测试任务", steps=5, should_fail=True)

    manager = TaskManager.get_instance()
    task_id = manager.submit_task(task)

    while not task.is_finished():
        time.sleep(0.1)

    assert task.state == TaskState.FAILED
    assert not task.result.is_success()
    print(f"✓ 任务失败，id: {task_id}, 错误信息: {task.result.error_message}")


def test_task_cancellation():
    """测试任务取消"""
    print("\n=== 测试3: 任务取消 ===")

    task = DummyTask("取消测试任务", steps=10)

    manager = TaskManager.get_instance()
    task_id = manager.submit_task(task)
    print(f"任务已提交: {task_id}")

    # 等待一会儿后取消
    time.sleep(0.3)
    print(f"调用 cancel(), 当前状态: {task.state.value}")
    success = task.cancel()
    print(f"cancel() 返回: {success}, 取消后状态: {task.state.value}")

    # 等待任务完成，最多等待52秒（避免死循环）
    max_wait = 5
    waited = 0
    while not task.is_finished() and waited < max_wait:
        time.sleep(0.1)
        waited += 0.1
        if waited % 1 == 0:  # 每秒打印一次
            print(f"等待中... 已等待 {waited:.1f}s, 状态: {task.state.value}")

    if not task.is_finished():
        print(f"\u2717 超时！任务仍未完成，最终状态: {task.state.value}")
        raise AssertionError("任务取消测试超时")

    print(f"任务已完成，最终状态: {task.state.value}")
    assert success
    assert task.state == TaskState.CANCELLED
    print("✓ 任务成功取消")


def test_concurrent_tasks():
    """测试并发任务"""
    print("\n=== 测试4: 并发任务执行 ===")

    manager = TaskManager.get_instance(max_concurrent=3)

    tasks = [DummyTask(f"并发任务 {i + 1}", steps=3) for i in range(5)]

    task_ids = []
    for task in tasks:
        task_id = manager.submit_task(task)
        task_ids.append(task_id)

    # 等待所有任务完成
    while manager.get_active_tasks():
        time.sleep(0.1)

    # 验证结果
    completed = sum(1 for t in tasks if t.state == TaskState.COMPLETED)
    print(f"✓ 完成 {completed}/{len(tasks)} 个任务")

    # 清理已完成任务
    cleared = manager.clear_finished_tasks()
    print(f"✓ 清理了 {cleared} 个已完成任务")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Task 系统测试开始")
    print("=" * 60)

    try:
        test_basic_task()
        test_task_failure()
        test_task_cancellation()
        test_concurrent_tasks()

        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
    finally:
        # 关闭管理器
        TaskManager.get_instance().shutdown()


if __name__ == "__main__":
    run_all_tests()
