import time
from typing import Any, Callable, List, Optional, Protocol, TypeVar, Self

T = TypeVar("T", bound="Tween")
G = TypeVar("G", bound="AnimationGroup")
A = TypeVar("A", bound="Animatable")


class Easing:
    """常用缓动函数集合"""

    @staticmethod
    def linear(t: float) -> float:
        return t

    @staticmethod
    def ease_in_quad(t: float) -> float:
        return t * t

    @staticmethod
    def ease_out_quad(t: float) -> float:
        return t * (2 - t)

    @staticmethod
    def ease_in_out_quad(t: float) -> float:
        return 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t

    @staticmethod
    def ease_out_back(t: float) -> float:
        s = 1.70158
        t -= 1
        return t * t * ((s + 1) * t + s) + 1

    @staticmethod
    def bounce_out(t: float) -> float:
        if t < 1 / 2.75:
            return 7.5625 * t * t
        elif t < 2 / 2.75:
            t -= 1.5 / 2.75
            return 7.5625 * t * t + 0.75
        elif t < 2.5 / 2.75:
            t -= 2.25 / 2.75
            return 7.5625 * t * t + 0.9375
        else:
            t -= 2.625 / 2.75
            return 7.5625 * t * t + 0.984375


class Animatable(Protocol):
    """动画更新协议"""

    def update(self) -> bool: ...
    def stop(self) -> None: ...


class Tween(Animatable):
    """
    基础补间动画类
    负责将数值从 start_value 插值到 end_value
    """

    def __init__(
        self,
        start_value: Any,
        end_value: Any,
        duration: float = 1.0,
        easing: Callable[[float], float] = Easing.linear,
        on_update: Optional[Callable[[Any], None]] = None,
        delay: float = 0.0,
        repeat: int = 0,  # 0 为播放一次，-1 为无限循环
    ) -> None:
        self.start_val = start_value
        self.end_val = end_value
        self.duration = duration
        self.easing = easing
        self.on_update = on_update
        self.delay = delay
        self.repeat = repeat

        self._start_time: Optional[float] = None  # 延迟初始化以支持 Sequence
        self._completed_repeats = 0
        self.is_finished = False
        self.on_complete_callback: Optional[Callable[[], None]] = None

    def on_complete(self: T, callback: Callable[[], None]) -> T:
        """设置完成回调，支持链式调用"""
        self.on_complete_callback = callback
        return self

    def stop(self) -> None:
        """立即停止动画"""
        self.is_finished = True

    def update(self) -> bool:
        if self.is_finished:
            return False

        # 只有在真正开始 update 时才记录开始时间
        if self._start_time is None:
            self._start_time = time.time()

        elapsed = time.time() - self._start_time

        if elapsed < self.delay:
            return True

        # 计算标准化进度 (0.0 -> 1.0)
        t = min(1.0, (elapsed - self.delay) / self.duration)
        eased_t = self.easing(t)

        # 数值插值
        current_val = self._interpolate(self.start_val, self.end_val, eased_t)

        if self.on_update:
            self.on_update(current_val)

        if t >= 1.0:
            if self.repeat == -1 or self._completed_repeats < self.repeat:
                self._completed_repeats += 1
                self._start_time = time.time()  # 重置时间实现循环
                return True
            else:
                self.is_finished = True
                if self.on_complete_callback:
                    self.on_complete_callback()
                return False

        return True

    def _interpolate(self, a: Any, b: Any, t: float) -> Any:
        if isinstance(a, (int, float)):
            return a + (b - a) * t
        if isinstance(a, (list, tuple)):
            return type(a)(a_i + (b_i - a_i) * t for a_i, b_i in zip(a, b))
        return b if t < 1.0 else a


class AnimationGroup:
    """动画组基类 (组合模式)"""

    def __init__(self, animations: List[Animatable]) -> None:
        self.animations = animations
        self.is_finished = False
        self.on_complete_callback: Optional[Callable[[], None]] = None

    def on_complete(self: Self, callback: Callable[[], None]) -> Self:
        self.on_complete_callback = callback
        return self

    def stop(self) -> None:
        """停止组内所有动画"""
        for anim in self.animations:
            anim.stop()
        self.is_finished = True


class Parallel(AnimationGroup):
    """并行播放的一组动画"""

    def update(self) -> bool:
        if self.is_finished or not self.animations:
            return False

        # 更新所有子动画，并移除已结束的
        self.animations = [a for a in self.animations if a.update()]

        if not self.animations:
            self.is_finished = True
            if self.on_complete_callback:
                self.on_complete_callback()
            return False
        return True


class Sequence(AnimationGroup):
    """顺序播放的一组动画"""

    def update(self) -> bool:
        if self.is_finished or not self.animations:
            return False

        # 仅更新当前的动画，当前一个结束（返回 False）时，pop 并进入下一个
        if not self.animations[0].update():
            self.animations.pop(0)
            if not self.animations:
                self.is_finished = True
                if self.on_complete_callback:
                    self.on_complete_callback()
                return False

        return True


class AnimationSystem:
    """全局动画管理器，负责统一生命周期管理"""

    _INSTANCE = None

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    @classmethod
    def get_instance(cls) -> Self:
        if cls._INSTANCE is None:
            cls._INSTANCE = cls()
        return cls._INSTANCE

    def __init__(self) -> None:
        self.active_anims: List[Animatable] = []

    def add(self, anim: A) -> A:
        """注册一个动画到系统"""
        self.active_anims.append(anim)
        return anim

    def update(self) -> None:
        """主循环更新"""
        self.active_anims = [a for a in self.active_anims if a.update()]
