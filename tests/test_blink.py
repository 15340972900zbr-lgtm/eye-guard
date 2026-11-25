"""眨眼状态机测试（纯函数，无硬件依赖）。"""

from eye_guard.blink import BlinkState, EyePhase, update_blink

OPEN_EAR = 0.35
CLOSED_EAR = 0.10
BAND_EAR = 0.22  # 介于闭眼/睁眼阈值之间的迟滞区间


def step(state: BlinkState, ear: float, min_closed_frames: int = 1) -> BlinkState:
    return update_blink(
        state,
        ear,
        close_threshold=0.20,
        open_threshold=0.25,
        min_closed_frames=min_closed_frames,
    )


def drive(ears: list[float], min_closed_frames: int = 1) -> BlinkState:
    state = BlinkState()
    for ear in ears:
        state = step(state, ear, min_closed_frames)
    return state


def test_stays_open_without_closure() -> None:
    state = drive([OPEN_EAR] * 50)
    assert state.total == 0
    assert state.phase is EyePhase.OPEN


def test_single_closed_frame_counts_one_blink() -> None:
    assert drive([OPEN_EAR, CLOSED_EAR, OPEN_EAR]).total == 1


def test_long_closure_counts_exactly_one_blink() -> None:
    state = drive([OPEN_EAR] + [CLOSED_EAR] * 8 + [OPEN_EAR] * 3)
    assert state.total == 1


def test_spike_below_min_closed_frames_is_ignored() -> None:
    assert drive([OPEN_EAR, CLOSED_EAR, OPEN_EAR], min_closed_frames=2).total == 0
    assert drive([OPEN_EAR, CLOSED_EAR, CLOSED_EAR, OPEN_EAR], min_closed_frames=2).total == 1


def test_hysteresis_band_keeps_eye_closed() -> None:
    # BAND_EAR 落在迟滞区间：不应判定睁眼，也不应多计一次眨眼
    state = drive([OPEN_EAR, CLOSED_EAR, BAND_EAR, CLOSED_EAR, OPEN_EAR])
    assert state.total == 1


def test_update_does_not_mutate_previous_state() -> None:
    original = BlinkState()
    updated = step(original, CLOSED_EAR)
    assert original.phase is EyePhase.OPEN
    assert original.total == 0
    assert updated.phase is EyePhase.CLOSED
