from .task import (
    Task,
    TaskManager,
    TaskProgress,
    TaskResult,
    TaskState,
)

from .sequence_task import SequenceTask
from .universal_task import UniversalModelTask
from .remove_background_task import RemoveBackgroundTask
from .ocr_task import OCRTask


__all__ = [
    "Task",
    "TaskManager",
    "TaskProgress",
    "TaskResult",
    "TaskState",
    "SequenceTask",
    "UniversalModelTask",
    "RemoveBackgroundTask",
    "OCRTask",
]
