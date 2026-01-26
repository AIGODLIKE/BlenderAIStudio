from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseProvider(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Any:
        raise NotImplementedError
