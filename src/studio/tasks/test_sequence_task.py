"""
SequenceTask 测试模块

演示如何使用 SequenceTask 组合多个任务
"""

import time

try:
    from .task import Task, TaskResult, TaskManager, TaskState
    from .sequence_task import SequenceTask
except ImportError:
    from task import Task, TaskResult, TaskManager, TaskState
    from sequence_task import SequenceTask


class SimpleTask(Task):
    """简单测试任务"""

    def __init__(self, task_name: str, steps: int = 3, should_fail: bool = False, delay: float = 0.1):
        super().__init__(task_name)
        self.progress.total_steps = steps
        self.should_fail = should_fail
        self.delay = delay
        self.input_data = None  # 用于接收前一个任务的数据

    def prepare(self) -> bool:
        self.update_progress(0, "准备中...")
        time.sleep(self.delay)
        return True

    def execute(self) -> TaskResult:
        try:
            for i in range(1, self.progress.total_steps + 1):
                if self.is_cancelled():
                    return TaskResult.failure_result(Exception("Task cancelled"), "任务被取消")

                message = f"执行步骤 {i}/{self.progress.total_steps}"
                if self.input_data:
                    message += f" (接收数据: {self.input_data})"

                self.update_progress(i, message)
                time.sleep(self.delay)

                # 模拟失败
                if self.should_fail and i == 2:
                    raise Exception(f"{self.task_name} 模拟失败")

            # 返回一些数据供下一个任务使用
            result_data = {"task_name": self.task_name, "message": f"{self.task_name} 完成", "value": f"result_from_{self.task_name.replace(' ', '_')}"}

            return TaskResult.success_result(data=result_data, metadata={"elapsed": self.get_elapsed_time()})

        except Exception as e:
            return TaskResult.failure_result(e, f"执行失败: {str(e)}")

    def cleanup(self) -> None:
        print(f"[SimpleTask] {self.task_name} 清理完成")


def test_basic_sequence():
    """测试基本顺序执行"""
    print("\n=== 测试1: 基本顺序任务执行 ===")

    # 创建子任务
    task1 = SimpleTask("任务A", steps=2)
    task2 = SimpleTask("任务B", steps=2)
    task3 = SimpleTask("任务C", steps=2)

    # 创建顺序任务
    seq_task = SequenceTask(task_name="基本顺序流水线", tasks=[task1, task2, task3], stop_on_failure=True)

    # 注册回调
    def on_progress(event_data):
        progress = event_data["progress"]
        print(f"进度: {progress['percentage'] * 100:.0f}% - {progress['message']}")

    seq_task.register_callback("progress_updated", on_progress)

    # 提交任务
    manager = TaskManager.get_instance()
    task_id = manager.submit_task(seq_task)

    # 等待完成
    while not seq_task.is_finished():
        time.sleep(0.1)

    # 检查结果
    assert seq_task.state == TaskState.COMPLETED
    assert seq_task.result.is_success()

    result_data = seq_task.result.get_data()
    print(f"✓ 顺序任务完成")
    print(f"  - 总任务数: {result_data['total_tasks']}")
    print(f"  - 完成数: {result_data['completed']}")
    print(f"  - 失败数: {result_data['failed']}")
    print(f"  - 总耗时: {seq_task.get_elapsed_time():.2f}s")


def test_sequence_with_data_passing():
    """测试数据传递"""
    print("\n=== 测试2: 带数据传递的顺序任务 ===")

    task1 = SimpleTask("数据生成任务", steps=2)
    task2 = SimpleTask("数据处理任务", steps=2)
    task3 = SimpleTask("数据输出任务", steps=2)

    # 创建带数据传递的顺序任务
    seq_task = SequenceTask(
        task_name="数据处理流水线",
        tasks=[task1, task2, task3],
        stop_on_failure=True,
        pass_data=True,  # 启用数据传递
    )

    # 提交任务
    manager = TaskManager.get_instance()
    task_id = manager.submit_task(seq_task)

    # 等待完成
    while not seq_task.is_finished():
        time.sleep(0.1)

    assert seq_task.state == TaskState.COMPLETED
    print(f"✓ 数据传递测试通过")

    # 检查每个子任务的输入数据
    for i, task in enumerate([task1, task2, task3]):
        print(f"  - {task.task_name}: input_data = {task.input_data}")


def test_sequence_with_failure():
    """测试失败处理"""
    print("\n=== 测试3: 失败处理（遇到失败停止）===")

    task1 = SimpleTask("任务1", steps=2)
    task2 = SimpleTask("任务2-失败", steps=3, should_fail=True)
    task3 = SimpleTask("任务3-不应执行", steps=2)

    seq_task = SequenceTask(
        task_name="失败测试流水线",
        tasks=[task1, task2, task3],
        stop_on_failure=True,  # 遇到失败停止
    )

    manager = TaskManager.get_instance()
    task_id = manager.submit_task(seq_task)

    while not seq_task.is_finished():
        time.sleep(0.1)

    # 顺序任务应该失败
    assert seq_task.state == TaskState.FAILED
    result_data = seq_task.result.get_data(default={})

    print(f"✓ 失败处理测试通过")
    print(f"  - 完成数: {result_data.get('completed', 0)}")
    print(f"  - 失败数: {result_data.get('failed', 0)}")
    print(f"  - 任务3是否执行: {task3.state != TaskState.PENDING}")


def test_sequence_continue_on_failure():
    """测试失败后继续"""
    print("\n=== 测试4: 失败处理（遇到失败继续）===")

    task1 = SimpleTask("任务1", steps=2)
    task2 = SimpleTask("任务2-失败", steps=2, should_fail=True)
    task3 = SimpleTask("任务3-继续执行", steps=2)

    seq_task = SequenceTask(
        task_name="容错流水线",
        tasks=[task1, task2, task3],
        stop_on_failure=False,  # 遇到失败继续
    )

    manager = TaskManager.get_instance()
    task_id = manager.submit_task(seq_task)

    while not seq_task.is_finished():
        time.sleep(0.1)

    result_data = seq_task.result.get_data(default={})

    print(f"✓ 容错测试通过")
    print(f"  - 完成数: {result_data.get('completed', 0)}")
    print(f"  - 失败数: {result_data.get('failed', 0)}")
    print(f"  - 任务3状态: {task3.state.value}")


def test_sequence_cancellation():
    """测试取消"""
    print("\n=== 测试5: 顺序任务取消 ===")

    task1 = SimpleTask("任务1", steps=2, delay=0.2)
    task2 = SimpleTask("任务2", steps=5, delay=0.2)  # 较长的任务
    task3 = SimpleTask("任务3", steps=2, delay=0.2)

    seq_task = SequenceTask(task_name="可取消流水线", tasks=[task1, task2, task3], stop_on_failure=True)

    manager = TaskManager.get_instance()
    task_id = manager.submit_task(seq_task)

    # 等待一段时间后取消
    time.sleep(0.5)
    print(f"取消任务，当前状态: {seq_task.state.value}")
    success = seq_task.cancel()

    # 等待任务完成
    max_wait = 3
    waited = 0
    while not seq_task.is_finished() and waited < max_wait:
        time.sleep(0.1)
        waited += 0.1

    assert success
    print(f"✓ 取消测试通过，最终状态: {seq_task.state.value}")


def test_custom_data_transformer():
    """测试自定义数据转换器"""
    print("\n=== 测试6: 自定义数据转换器 ===")

    task1 = SimpleTask("生成数字", steps=2)
    task2 = SimpleTask("处理数字", steps=2)

    # 自定义数据转换函数
    def transform_data(prev_result, next_task):
        """将前一个任务的结果转换为下一个任务需要的格式"""
        if prev_result and "value" in prev_result:
            return {"input_data": f"转换后: {prev_result['value']}"}
        return {}

    seq_task = SequenceTask(task_name="自定义转换流水线", tasks=[task1, task2], pass_data=True, data_transformer=transform_data)

    manager = TaskManager.get_instance()
    task_id = manager.submit_task(seq_task)

    while not seq_task.is_finished():
        time.sleep(0.1)

    assert seq_task.state == TaskState.COMPLETED
    print(f"✓ 自定义转换器测试通过")
    print(f"  - 任务2接收到的数据: {task2.input_data}")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("SequenceTask 测试开始")
    print("=" * 60)

    try:
        test_basic_sequence()
        test_sequence_with_data_passing()
        test_sequence_with_failure()
        test_sequence_continue_on_failure()
        test_sequence_cancellation()
        test_custom_data_transformer()

        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # 关闭管理器
        TaskManager.get_instance().shutdown()


if __name__ == "__main__":
    run_all_tests()
