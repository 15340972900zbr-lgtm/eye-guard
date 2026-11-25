"""坐姿几何、校准和提醒回归测试，不需要真实摄像头。"""

import math

import pytest

from eye_guard.posture import (
    PostureCalibration,
    PostureState,
    head_forward_score,
    interrupt_posture,
    start_posture_calibration,
    update_posture,
)

SHOULDERS = ((-0.2, 0.0, 0.0), (0.2, 0.0, 0.0))
EARS = ((-0.1, -0.2, -0.12), (0.1, -0.2, -0.12))


def sample(state, score, now):
    return update_posture(state, score, now, hold_s=2.0, max_gap_s=1.1, cooldown_s=10.0)


def calibrate(state, values):
    for now, score in enumerate(values):
        state, message = sample(state, score, float(now))
    return state, message


def test_head_protrusion_is_relative_to_shoulders() -> None:
    def rotate_and_translate(points):
        angle = math.radians(25)
        return tuple(
            (
                0.2 + x * math.cos(angle) + z * math.sin(angle),
                y + 0.1,
                -0.4 - x * math.sin(angle) + z * math.cos(angle),
            )
            for x, y, z in points
        )

    assert head_forward_score(EARS, SHOULDERS) == pytest.approx(0.3)
    assert head_forward_score(
        rotate_and_translate(EARS), rotate_and_translate(SHOULDERS)
    ) == pytest.approx(0.3)
    assert head_forward_score(EARS, (SHOULDERS[0],) * 2) is None


def test_needs_two_distinct_user_calibration_poses():
    with pytest.raises(ValueError, match="先完成"):
        start_posture_calibration(PostureState(), PostureCalibration.LIMIT)
    upright, notice = calibrate(
        start_posture_calibration(PostureState(), PostureCalibration.UPRIGHT),
        [0.12, 0.13, 0.14],
    )
    assert upright.upright_max == 0.14
    assert not upright.sampling
    assert "已记录" in notice

    pending = start_posture_calibration(upright, PostureCalibration.LIMIT)
    rejected, notice = calibrate(pending, [0.12, 0.13, 0.14])
    assert rejected.limit is None
    assert "差别不够" in notice
    enabled, notice = calibrate(pending, [0.28, 0.29, 0.3])
    assert enabled.limit == 0.29
    assert "已开启" in notice


def test_prompt_requires_sustained_forward_posture_and_respects_cooldown():
    state = PostureState(upright_max=0.12, limit=0.3)
    for now, score in [(0, 0.4), (1, 0.2), (2, 0.4), (3, 0.4)]:
        state, notice = sample(state, score, now)
        assert notice is None
    state, notice = sample(state, 0.4, 4)
    assert state.leaning is True
    assert "放松" in notice
    state, notice = sample(state, 0.4, 5)
    assert notice is None
    assert state.last_reminder == 4


def test_lost_tracking_or_pause_clears_only_the_current_hold():
    state, _ = sample(PostureState(upright_max=0.12, limit=0.3), 0.4, 0)
    state, _ = sample(state, 0.4, 1)
    state, notice = sample(state, None, 2)
    assert state.leaning is None
    assert notice is None
    state, notice = sample(state, 0.4, 3)
    assert notice is None and state.since == 3
    state, notice = sample(state, 0.4, 5)  # long gap between samples
    assert notice is None and state.since == 5
    state = interrupt_posture(state)
    assert state.limit == 0.3
    assert state.since is None
