"""连续用眼计时状态机（纯函数）：注入时间戳，输出新状态与事件。

规则：
- 只累计「连续两帧都检测到人脸」之间的时间；检测中断后恢复的第一帧
  只重建时间基线，断档期间（丢脸/暂停/线程卡顿）的未知时间一律不计入。
- 单帧间隔超过 MAX_STEP_S 同样视为断档，不做钳制累计。
- 短暂离开（< absence_grace_s）保留连续段；超过宽限期或出现长时间断档
  （> gap_reset_s）则重置连续段、保留累计总时长。
- remind_limit_s 为 None 时不产生提醒（未确认阈值默认禁用）。
"""

import enum
from dataclasses import dataclass, replace

MAX_STEP_S = 1.0


class SessionEvent(enum.Enum):
    CONTINUOUS_LIMIT = "continuous_limit"


@dataclass(frozen=True)
class SessionState:
    total_s: float = 0.0
    continuous_s: float = 0.0
    absence_s: float = 0.0
    last_now: float | None = None
    was_present: bool = False
    reminded: bool = False


def update_session(
    state: SessionState,
    now: float,
    face_present: bool,
    *,
    remind_limit_s: float | None,
    absence_grace_s: float,
    gap_reset_s: float,
) -> tuple[SessionState, list[SessionEvent]]:
    """推进一帧用眼计时，返回 (新状态, 事件列表)。"""
    if state.last_now is None:
        return replace(state, absence_s=0.0, last_now=now, was_present=face_present), []

    dt = max(0.0, now - state.last_now)
    if dt > gap_reset_s:
        # 长断档（暂停很久/离开很久）：重置连续段，保留累计
        return SessionState(state.total_s, 0.0, dt, now, False, False), []

    if not face_present:
        absence = state.absence_s + dt
        if absence >= absence_grace_s:
            return SessionState(state.total_s, 0.0, absence, now, False, False), []
        return (
            SessionState(state.total_s, state.continuous_s, absence, now, False, state.reminded),
            [],
        )

    if not state.was_present or dt > MAX_STEP_S:
        # 检测中断后恢复（丢脸/暂停/卡顿）：本帧不累计，重建时间基线
        return SessionState(state.total_s, state.continuous_s, 0.0, now, True, state.reminded), []

    continuous = state.continuous_s + dt
    events: list[SessionEvent] = []
    reminded = state.reminded
    if remind_limit_s is not None and not reminded and continuous >= remind_limit_s:
        events.append(SessionEvent.CONTINUOUS_LIMIT)
        reminded = True
    return (
        SessionState(state.total_s + dt, continuous, 0.0, now, True, reminded),
        events,
    )
