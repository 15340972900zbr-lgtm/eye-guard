"""头部相对双肩前伸的估计和校准，独立于相机与提醒界面。"""

from dataclasses import dataclass, replace
from enum import Enum
from math import copysign, hypot, isfinite
from statistics import median

Point = tuple[float, float, float]


def head_forward_score(ears: tuple[Point, Point], shoulders: tuple[Point, Point]) -> float | None:
    """将双耳中心相对双肩的偏移投影到肩线的正前方，以肩宽归一化。"""
    left, right = shoulders
    dx, dz = right[0] - left[0], right[2] - left[2]
    width = hypot(dx, dz)
    if width <= 0 or not all(isfinite(v) for point in (*ears, *shoulders) for v in point):
        return None

    # camera-space z 正方向远离相机，因此选择朝向相机的肩线法向量。
    forward_x, forward_z = dz * copysign(1, dx) / width, -abs(dx) / width
    x = (ears[0][0] + ears[1][0] - left[0] - right[0]) / 2
    z = (ears[0][2] + ears[1][2] - left[2] - right[2]) / 2
    return (x * forward_x + z * forward_z) / width


class PostureCalibration(Enum):
    UPRIGHT = "upright"
    LIMIT = "limit"


@dataclass(frozen=True)
class PostureState:
    upright_max: float | None = None
    limit: float | None = None
    calibration: PostureCalibration | None = None
    samples: tuple[float, ...] = ()
    since: float | None = None  # 本轮稳定采样或持续前伸的起点
    last_sample_at: float | None = None
    leaning: bool | None = None  # None 表示暂无可信测量
    last_reminder: float | None = None

    @property
    def sampling(self) -> bool:
        return self.calibration is not None or self.limit is not None


def start_posture_calibration(state: PostureState, phase: PostureCalibration) -> PostureState:
    if phase is PostureCalibration.UPRIGHT:
        return PostureState(calibration=phase)
    if state.upright_max is None:
        raise ValueError("请先完成「校准坐直姿势」。")
    return PostureState(upright_max=state.upright_max, calibration=phase)


def interrupt_posture(state: PostureState) -> PostureState:
    return replace(state, samples=(), since=None, last_sample_at=None, leaning=None)


def update_posture(
    state: PostureState,
    score: float | None,
    now: float,
    *,
    hold_s: float,
    max_gap_s: float,
    cooldown_s: float,
) -> tuple[PostureState, str | None]:
    if not state.sampling:
        return state, None
    if score is None or not isfinite(score):
        return interrupt_posture(state), None
    if state.last_sample_at is not None and now - state.last_sample_at > max_gap_s:
        state = interrupt_posture(state)
    since = state.since if state.since is not None else now
    state = replace(state, last_sample_at=now)

    if state.calibration is not None:
        samples = (*state.samples, score)
        if now - since < hold_s:
            return replace(state, samples=samples, since=since), None
        if state.calibration is PostureCalibration.UPRIGHT:
            return PostureState(upright_max=max(samples)), "坐直姿势已记录。接着校准前倾提醒界线。"
        limit = median(samples)
        if state.upright_max is None or limit <= state.upright_max:
            return PostureState(upright_max=state.upright_max), "两种姿势差别不够。请重试前倾界线。"
        return PostureState(upright_max=state.upright_max, limit=limit), "头前倾提醒已开启。"

    if state.limit is None or score < state.limit:
        return replace(state, since=None, leaning=False), None

    state = replace(state, since=since, leaning=True)
    if now - since < hold_s:
        return state, None
    if state.last_reminder is not None and now - state.last_reminder < cooldown_s:
        return state, None
    return replace(state, last_reminder=now), "头有点往前伸。试着坐直一点，让肩膀放松。"
