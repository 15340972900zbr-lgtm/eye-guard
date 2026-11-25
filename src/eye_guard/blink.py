"""眨眼检测状态机（纯函数）：输入 EAR 序列，输出更新后的状态。

使用双阈值迟滞（close/open）抑制噪声，闭眼→睁眼转换计一次眨眼。
"""

import enum
from dataclasses import dataclass


class EyePhase(enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True)
class BlinkState:
    phase: EyePhase = EyePhase.OPEN
    closed_frames: int = 0
    total: int = 0


def update_blink(
    state: BlinkState,
    ear: float,
    *,
    close_threshold: float,
    open_threshold: float,
    min_closed_frames: int = 1,
) -> BlinkState:
    """推进一帧眨眼状态，返回新状态（不修改入参）。"""
    if state.phase is EyePhase.OPEN:
        if ear < close_threshold:
            return BlinkState(EyePhase.CLOSED, 1, state.total)
        return state

    # CLOSED
    if ear < close_threshold:
        return BlinkState(EyePhase.CLOSED, state.closed_frames + 1, state.total)
    if ear > open_threshold:
        counted = state.closed_frames >= min_closed_frames
        return BlinkState(EyePhase.OPEN, 0, state.total + (1 if counted else 0))
    return state  # 迟滞区间内，维持闭眼
