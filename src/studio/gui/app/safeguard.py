from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable

log = logging.getLogger(__name__)

# Names of pop functions that require count=1 during recovery
_POP_WITH_COUNT = frozenset({"pop_style_color", "pop_style_var"})


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class PairType(Enum):
    UNCONDITIONAL_BEGIN_END = auto()  # end is always called
    CONDITIONAL_BEGIN_END = auto()  # end called only when begin returns True
    PUSH_POP = auto()  # pop is always called


@dataclass
class StackEntry:
    end_func_name: str
    should_call: bool = True
    pop_kwargs: dict = field(default_factory=dict)


@dataclass
class PairConfig:
    begin_name: str
    end_name: str
    pair_type: PairType


# ---------------------------------------------------------------------------
# Pair registry – every begin/push ↔ end/pop pair known to slimgui
# ---------------------------------------------------------------------------

PAIR_REGISTRY: list[PairConfig] = [
    # Unconditional begin/end (end always called)
    PairConfig("begin", "end", PairType.UNCONDITIONAL_BEGIN_END),
    PairConfig("begin_child", "end_child", PairType.UNCONDITIONAL_BEGIN_END),
    # Conditional begin/end (end called only when begin returns True)
    PairConfig("begin_combo", "end_combo", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_list_box", "end_list_box", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_menu_bar", "end_menu_bar", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_main_menu_bar", "end_main_menu_bar", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_menu", "end_menu", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_tooltip", "end_tooltip", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_item_tooltip", "end_tooltip", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_popup", "end_popup", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_popup_modal", "end_popup", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_tab_bar", "end_tab_bar", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_tab_item", "end_tab_item", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_table", "end_table", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_drag_drop_source", "end_drag_drop_source", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_drag_drop_target", "end_drag_drop_target", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_group", "end_group", PairType.UNCONDITIONAL_BEGIN_END),
    PairConfig("begin_disabled", "end_disabled", PairType.UNCONDITIONAL_BEGIN_END),
    PairConfig("tree_node", "tree_pop", PairType.CONDITIONAL_BEGIN_END),
    # Conditional popup context (end_popup called only when begin returns True)
    PairConfig("begin_popup_context_item", "end_popup", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_popup_context_window", "end_popup", PairType.CONDITIONAL_BEGIN_END),
    PairConfig("begin_popup_context_void", "end_popup", PairType.CONDITIONAL_BEGIN_END),
    # Push/pop operations
    PairConfig("push_id", "pop_id", PairType.PUSH_POP),
    PairConfig("push_style_color", "pop_style_color", PairType.PUSH_POP),
    PairConfig("push_style_var", "pop_style_var", PairType.PUSH_POP),
    PairConfig("push_style_var_x", "pop_style_var", PairType.PUSH_POP),
    PairConfig("push_style_var_y", "pop_style_var", PairType.PUSH_POP),
    PairConfig("push_font", "pop_font", PairType.PUSH_POP),
    PairConfig("push_clip_rect", "pop_clip_rect", PairType.PUSH_POP),
    PairConfig("push_item_width", "pop_item_width", PairType.PUSH_POP),
    PairConfig("push_text_wrap_pos", "pop_text_wrap_pos", PairType.PUSH_POP),
    PairConfig("tree_push", "tree_pop", PairType.PUSH_POP),
]


# ---------------------------------------------------------------------------
# ImguiSafeGuard
# ---------------------------------------------------------------------------


class ImguiSafeGuard:
    """Monkey-patch guard that tracks imgui begin/push calls and can recover
    the imgui state when a user callback raises an exception."""

    def __init__(self, imgui_module):
        self._imgui_module = imgui_module
        self._call_stack: list[StackEntry] = []
        self._originals: dict[str, object] = {}
        self._installed: bool = False
        self._pair_registry: list[PairConfig] = PAIR_REGISTRY

    # ------------------------------------------------------------------
    # Wrapper factory methods
    # ------------------------------------------------------------------

    def _make_begin_wrapper(self, original: Callable, end_name: str, conditional: bool) -> Callable:
        """Create a wrapper for a begin function.

        Args:
            original: The original imgui begin function.
            end_name: Name of the corresponding end function.
            conditional: If False, should_call is always True (unconditional).
                         If True, should_call is derived from the return value.
        """
        call_stack = self._call_stack

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)

            if conditional:
                # Return may be a plain bool or a tuple whose first element is bool
                should_call = result[0] if isinstance(result, tuple) else bool(result)
            else:
                should_call = True

            call_stack.append(StackEntry(end_func_name=end_name, should_call=should_call))
            return result

        return wrapper

    def _make_end_wrapper(self, original: Callable, end_name: str) -> Callable:
        """Create a wrapper for an end function.

        Pops the most recent matching entry from the call stack.
        """
        call_stack = self._call_stack

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)

            # Pop the last matching entry (search from the top)
            for i in range(len(call_stack) - 1, -1, -1):
                if call_stack[i].end_func_name == end_name:
                    call_stack.pop(i)
                    break

            return result

        return wrapper

    def _make_push_wrapper(self, original: Callable, pop_name: str) -> Callable:
        """Create a wrapper for a push function.

        Pushes a StackEntry with appropriate pop_kwargs (e.g. count=1 for
        pop_style_color / pop_style_var).
        """
        call_stack = self._call_stack
        pop_kwargs: dict = {"count": 1} if pop_name in _POP_WITH_COUNT else {}

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)
            call_stack.append(
                StackEntry(
                    end_func_name=pop_name,
                    should_call=True,
                    pop_kwargs=pop_kwargs,
                )
            )
            return result

        return wrapper

    def _make_pop_wrapper(self, original: Callable, pop_name: str) -> Callable:
        """Create a wrapper for a pop function.

        Pops the most recent matching entry from the call stack.
        Respects the ``count`` parameter for pop_style_color / pop_style_var.
        """
        call_stack = self._call_stack
        has_count = pop_name in _POP_WITH_COUNT

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)

            # Determine how many stack entries to remove
            if has_count:
                count = kwargs.get("count", args[0] if args else 1)
            else:
                count = 1

            removed = 0
            for _ in range(count):
                for i in range(len(call_stack) - 1, -1, -1):
                    if call_stack[i].end_func_name == pop_name:
                        call_stack.pop(i)
                        removed += 1
                        break

            return result

        return wrapper

    # ------------------------------------------------------------------
    # Lifecycle methods (to be implemented in subsequent tasks)
    # ------------------------------------------------------------------

    def install(self) -> None:
        """Install monkey-patch wrappers onto the imgui module."""
        if self._installed:
            return

        mod = self._imgui_module

        for pair in self._pair_registry:
            begin_name = pair.begin_name
            end_name = pair.end_name

            # --- begin / push side ---
            orig_begin = getattr(mod, begin_name, None)
            if orig_begin is None:
                log.warning("imgui module has no attribute %r – skipping pair", begin_name)
                continue

            # --- end / pop side ---
            orig_end = getattr(mod, end_name, None)
            if orig_end is None:
                log.warning("imgui module has no attribute %r – skipping pair", end_name)
                continue

            # Store originals (only first encounter wins – some end names are shared)
            if begin_name not in self._originals:
                self._originals[begin_name] = orig_begin
            if end_name not in self._originals:
                self._originals[end_name] = orig_end

            # Create and install wrappers for the begin/push side
            if pair.pair_type == PairType.UNCONDITIONAL_BEGIN_END:
                setattr(mod, begin_name, self._make_begin_wrapper(self._originals[begin_name], end_name, conditional=False))
            elif pair.pair_type == PairType.CONDITIONAL_BEGIN_END:
                setattr(mod, begin_name, self._make_begin_wrapper(self._originals[begin_name], end_name, conditional=True))
            elif pair.pair_type == PairType.PUSH_POP:
                setattr(mod, begin_name, self._make_push_wrapper(self._originals[begin_name], end_name))

            # Create and install wrappers for the end/pop side
            if pair.pair_type == PairType.PUSH_POP:
                setattr(mod, end_name, self._make_pop_wrapper(self._originals[end_name], end_name))
            else:
                setattr(mod, end_name, self._make_end_wrapper(self._originals[end_name], end_name))

        self._installed = True

    def uninstall(self) -> None:
        """Restore original functions and clear the call stack."""
        if not self._installed:
            return

        mod = self._imgui_module

        for name, original in self._originals.items():
            try:
                setattr(mod, name, original)
            except Exception:
                log.warning("Failed to restore %r on imgui module", name, exc_info=True)

        self._originals.clear()
        self._call_stack.clear()
        self._installed = False

    def recover(self) -> None:
        """Walk the call stack in reverse, calling end/pop to restore imgui state."""
        while self._call_stack:
            entry = self._call_stack.pop()

            if not entry.should_call:
                continue

            end_func = self._originals.get(entry.end_func_name)
            if end_func is None:
                end_func = getattr(self._imgui_module, entry.end_func_name, None)

            if end_func is None:
                log.warning("Cannot find end/pop function %r for recovery", entry.end_func_name)
                continue

            try:
                end_func(**entry.pop_kwargs)
            except Exception:
                log.warning(
                    "Exception during recovery call to %r – continuing",
                    entry.end_func_name,
                    exc_info=True,
                )
