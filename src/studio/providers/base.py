from abc import ABC, abstractmethod
from typing import Tuple


class BaseProvider(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def generate_image(self, prompt, **kwargs) -> Tuple[bytes, str]:
        raise NotImplementedError
