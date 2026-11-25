"""连续用眼计时状态机测试（纯函数，注入时间戳）。"""

import pytest

from eye_guard.session import MAX_STEP_S, SessionEvent, SessionState, update_session

DEFAULTS = dict(remind_limit_s=None, absence_grace_s=30.0, gap_reset_s=60.0)


def upd(state: SessionState, now: float, present: bool, **overrides):
    return update_session(state, now, present, **{**DEFAULTS, **overrides})


def accumulate(seconds: float, dt: float = 1.0) -> tuple[SessionState, float]:
    state, _ = upd(SessionState(), 0.0, True)
    t = 0.0
    while t < seconds:
        t += dt
        state, _ = upd(state, t, True)
    return state, t


def test_first_call_initializes_without_accumulating() -> None:
    state, events = upd(SessionState(), 100.0, True)
    assert state.last_now == 100.0
    assert state.total_s == 0.0
    assert events == []


def test_accumulates_while_present() -> None:
    state, _ = accumulate(60.0, dt=0.1)
    assert state.total_s == pytest.approx(60.0)
    assert state.continuous_s == pytest.approx(60.0)


def test_absence_shorter_than_grace_preserves_segment() -> None:
    state, t = accumulate(60.0)
    absent, _ = upd(state, t + 10.0, False)
    assert absent.continuous_s == pytest.approx(60.0)
    # 恢复检测的第一帧不累计（重建基线），后续帧正常累计
    resumed, _ = upd(absent, t + 10.5, True)
    assert resumed.continuous_s == pytest.approx(60.0)
    resumed2, _ = upd(resumed, t + 11.0, True)
    assert resumed2.continuous_s == pytest.approx(60.5)


def test_detection_gap_not_counted_as_usage() -> None:
    # 模拟「闭眼 → 丢失人脸 → 恢复检测」：断档期间的时间不得计入用眼时长
    state, _ = upd(SessionState(), 0.0, True)
    state, _ = upd(state, 0.5, False)
    state, _ = upd(state, 1.0, True)
    assert state.total_s == 0.0
    state, _ = upd(state, 1.5, True)
    assert state.total_s == pytest.approx(0.5)


def test_absence_beyond_grace_resets_segment_but_keeps_total() -> None:
    state, t = accumulate(60.0)
    reset, _ = upd(state, t + 31.0, False)
    assert reset.continuous_s == 0.0
    assert reset.reminded is False
    assert reset.total_s == pytest.approx(60.0)


def test_gap_larger_than_reset_discards_segment() -> None:
    state, t = accumulate(60.0)
    after, _ = upd(state, t + 61.0, True)
    assert after.continuous_s == 0.0
    assert after.total_s == pytest.approx(60.0)


def test_step_gap_not_counted_as_usage() -> None:
    # 帧间隔异常增大（线程卡顿/暂停后恢复）：未知状态的时间不计入
    state, _ = upd(SessionState(), 0.0, True)
    after, _ = upd(state, 30.0, True)  # 30s < 60s 不算断档，但超过单步上限
    assert after.total_s == 0.0
    assert after.last_now == 30.0
    next_state, _ = upd(after, 30.5, True)
    assert next_state.total_s == pytest.approx(0.5)


def test_max_step_boundary() -> None:
    # 恰好等于单步上限的间隔正常累计，超过则该步不累计
    state, _ = upd(SessionState(), 0.0, True)
    at_limit, _ = upd(state, MAX_STEP_S, True)
    assert at_limit.total_s == pytest.approx(MAX_STEP_S)
    beyond, _ = upd(at_limit, at_limit.last_now + MAX_STEP_S + 0.1, True)
    assert beyond.total_s == pytest.approx(MAX_STEP_S)


def test_reminder_fires_exactly_once_at_limit() -> None:
    state, _ = upd(SessionState(), 0.0, True, remind_limit_s=60.0)
    events = []
    t = 0.0
    for _ in range(120):
        t += 0.5
        state, ev = upd(state, t, True, remind_limit_s=60.0)
        events += ev
    assert events == [SessionEvent.CONTINUOUS_LIMIT]
    assert state.continuous_s >= 60.0


def test_no_reminder_when_threshold_disabled() -> None:
    state, _ = upd(SessionState(), 0.0, True)
    t = 0.0
    for _ in range(100):
        t += 1.0
        state, ev = upd(state, t, True)
        assert ev == []


def test_reminder_rearms_after_segment_reset() -> None:
    state, _ = upd(SessionState(), 0.0, True, remind_limit_s=10.0)
    t, events = 0.0, []
    for _ in range(30):
        t += 1.0
        state, ev = upd(state, t, True, remind_limit_s=10.0)
        events += ev
    assert events == [SessionEvent.CONTINUOUS_LIMIT]
    state, _ = upd(state, t + 45.0, False)  # 离开超过宽限期，段重置
    events2 = []
    for i in range(15):
        state, ev = upd(state, t + 45.0 + i + 1.0, True, remind_limit_s=10.0)
        events2 += ev
    assert events2 == [SessionEvent.CONTINUOUS_LIMIT]
