from dataclasses import dataclass, replace

from .config import Config
from .metrics import Observation


@dataclass(frozen=True)
class Reading:
    present: bool = False
    blink_total: int = 0
    blink_rate: float | None = None
    sample_seconds: float = 0.0
    active_seconds: float = 0.0
    total_seconds: float = 0.0
    face_scale: float | None = None
    calibrating: bool = False


@dataclass(frozen=True)
class State:
    reading: Reading = Reading()
    last_at: float | None = None
    absent_since: float | None = None
    first_valid: float | None = None
    eye_open: bool | None = None
    blink_times: tuple[float, ...] = ()
    baseline: float | None = None
    calibration: tuple[float, ...] | None = None
    rest_notified: bool = False
    last_notices: tuple[tuple[str, float], ...] = ()


def interrupt(state: State) -> State:
    return State(
        reading=Reading(
            blink_total=state.reading.blink_total, total_seconds=state.reading.total_seconds
        ),
        baseline=state.baseline,
        last_notices=state.last_notices,
    )


def advance(
    state: State, observation: Observation | None, now: float, config: Config
) -> tuple[State, tuple[tuple[str, str], ...]]:
    old = state.reading
    elapsed = 0.0 if state.last_at is None else max(0.0, now - state.last_at)
    gap = elapsed > max(1.0, config.analysis_interval_s * 3)
    if observation is None:
        since = state.absent_since
        if since is None:
            since = state.last_at if state.last_at is not None else now
        rested = now - since >= config.absence_grace_s
        reading = Reading(
            blink_total=old.blink_total,
            active_seconds=0.0 if rested else old.active_seconds,
            total_seconds=old.total_seconds,
            calibrating=state.calibration is not None,
        )
        return replace(
            state,
            reading=reading,
            last_at=now,
            absent_since=since,
            first_valid=None,
            eye_open=None,
            blink_times=(),
            rest_notified=state.rest_notified and not rested,
            calibration=() if state.calibration is not None else None,
        ), ()

    intact = old.present and not gap
    rested = (
        state.absent_since is not None and now - state.absent_since >= config.absence_grace_s
    ) or elapsed >= config.absence_grace_s
    first = state.first_valid if intact and state.first_valid is not None else now
    interval = elapsed if intact else 0.0
    phase = state.eye_open if intact else None
    count = old.blink_total
    timestamps = tuple(t for t in state.blink_times if now - t < config.blink_window_s) if intact else ()
    if observation.ear >= config.ear_open_threshold:
        if phase is False:
            count += 1
            timestamps = (*timestamps, now)
        phase = True
    elif observation.ear <= config.ear_close_threshold and phase is not None:
        phase = False
    sample = min(config.blink_window_s, now - first)
    rate = len(timestamps) * 60 / config.blink_window_s if sample >= config.blink_window_s else None
    active = (0.0 if rested else old.active_seconds) + interval
    baseline, calibration = state.baseline, state.calibration
    notices: list[tuple[str, str]] = []
    if calibration is not None:
        calibration = (*(calibration if intact else ()), observation.face_ratio)
        if len(calibration) >= config.calibration_frames:
            baseline = sum(calibration) / len(calibration)
            calibration = None
            notices.append(("calibrated", "距离校准完成"))
    scale = observation.face_ratio / baseline if baseline and calibration is None else None
    last_notices = dict(state.last_notices)

    def warn(kind: str, message: str) -> None:
        last = last_notices.get(kind)
        if last is None or now - last >= config.reminder_cooldown_s:
            notices.append((kind, message))
            last_notices[kind] = now

    reminded = state.rest_notified and not rested
    if config.continuous_remind_minutes is not None and not reminded:
        if active >= config.continuous_remind_minutes * 60:
            notices.append(("rest", f"已连续用眼 {active / 60:g} 分钟，可以休息一下。"))
            reminded = True
    if rate is not None and config.blink_rate_remind_per_min is not None:
        if rate < config.blink_rate_remind_per_min:
            warn("blink", f"这段时间眨眼约 {rate:.0f} 次/分，低于你的提醒设置。")
    if scale is not None and config.proximity_too_close is not None:
        if scale > config.proximity_too_close:
            warn("close", "你比校准时更靠近屏幕。")
    if scale is not None and config.proximity_too_far is not None:
        if scale < config.proximity_too_far:
            warn("far", "你比校准时离屏幕更远。")

    reading = Reading(
        present=True,
        blink_total=count,
        blink_rate=rate,
        sample_seconds=sample,
        active_seconds=active,
        total_seconds=old.total_seconds + interval,
        face_scale=scale,
        calibrating=calibration is not None,
    )
    return State(
        reading,
        now,
        None,
        first,
        phase,
        timestamps,
        baseline,
        calibration,
        reminded,
        tuple(last_notices.items()),
    ), tuple(notices)
