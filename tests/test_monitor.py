"""process_frame 纯步骤测试：合成关键点端到端推进状态机，无硬件依赖。"""

from dataclasses import replace

import pytest

from _synthetic import synthetic_landmarks
from eye_guard.blink import EyePhase
from eye_guard.config import EyeGuardConfig
from eye_guard.monitor import (
    MonitorState,
    ReminderKind,
    interrupt_detection,
    process_frame,
    start_calibration,
)
from eye_guard.session import SessionState

DEFAULT_BOX = (0.30, 0.20, 0.70, 0.60)  # 人脸框占比 0.16


def cfg(**overrides) -> EyeGuardConfig:
    return EyeGuardConfig(**overrides)


def feed(state, frames, config, aspect: float = 1.0):
    state_out, reminders, snapshots = state, [], []
    for now, lms in frames:
        state_out, rems, snap = process_frame(state_out, lms, now, config, aspect)
        reminders += rems
        snapshots.append(snap)
    return state_out, reminders, snapshots


def frames_open(n: int, ear: float = 0.35, dt: float = 0.1, box=DEFAULT_BOX):
    return [(i * dt, synthetic_landmarks(ear=ear, box=box)) for i in range(n)]


def test_no_face_frame_is_recorded_as_absent() -> None:
    _, _, snaps = feed(MonitorState(), [(0.0, synthetic_landmarks()), (10.0, None)], cfg())
    assert snaps[-1].face_present is False
    assert snaps[-1].proximity is None


def test_blink_counted_end_to_end() -> None:
    frames = [
        (0.0, synthetic_landmarks(ear=0.35)),
        (0.1, synthetic_landmarks(ear=0.35)),
        (0.2, synthetic_landmarks(ear=0.10)),
        (0.3, synthetic_landmarks(ear=0.35)),
    ]
    state, _, snaps = feed(MonitorState(), frames, cfg())
    assert state.blink.total == 1
    assert snaps[-1].blink_total == 1


def test_calibration_sets_baseline_and_notifies() -> None:
    config = cfg(calibration_frames=3)
    state, reminders, _ = feed(start_calibration(MonitorState(), config), frames_open(3), config)
    assert state.baseline_ratio == pytest.approx(0.16)
    assert [r.kind for r in reminders] == [ReminderKind.CALIBRATED]


def test_proximity_reported_after_calibration() -> None:
    config = cfg(calibration_frames=1)
    state = start_calibration(MonitorState(), config)
    state, _, _ = feed(state, [(0.0, synthetic_landmarks(box=DEFAULT_BOX))], config)
    far_box = (0.36, 0.24, 0.64, 0.56)  # 占比 0.28*0.32 = 0.0896
    _, _, snaps = feed(state, [(0.1, synthetic_landmarks(box=far_box))], config)
    assert snaps[0].proximity == pytest.approx(0.0896 / 0.16)


def test_too_close_reminder_respects_cooldown() -> None:
    config = cfg(proximity_too_close=1.2, reminder_cooldown_s=300.0)
    state = MonitorState(baseline_ratio=0.16)
    near_box = (0.20, 0.10, 0.80, 0.70)  # 占比 0.36，proximity 2.25
    state, reminders, _ = feed(
        state, [(0.0, synthetic_landmarks()), (0.1, synthetic_landmarks(box=near_box))], config
    )
    assert [r.kind for r in reminders] == [ReminderKind.TOO_CLOSE]
    _, reminders2, _ = feed(state, [(0.2, synthetic_landmarks(box=near_box))], config)
    assert reminders2 == []


def test_too_far_reminder_fires() -> None:
    config = cfg(proximity_too_far=0.8)
    state = MonitorState(baseline_ratio=0.16)
    far_box = (0.36, 0.26, 0.64, 0.54)  # 占比 0.0784，proximity 0.49
    _, reminders, _ = feed(state, [(0.0, synthetic_landmarks(box=far_box))], config)
    assert [r.kind for r in reminders] == [ReminderKind.TOO_FAR]


def test_no_distance_reminder_when_thresholds_disabled() -> None:
    state = MonitorState(baseline_ratio=0.16)
    near_box = (0.20, 0.10, 0.80, 0.70)
    _, reminders, _ = feed(state, [(0.0, synthetic_landmarks(box=near_box))], cfg())
    assert reminders == []


def test_continuous_reminder_through_process_frame() -> None:
    config = cfg(continuous_remind_minutes=0.01)  # 0.6 秒，便于测试
    state, reminders, _ = feed(MonitorState(), frames_open(9), config)
    assert [r.kind for r in reminders] == [ReminderKind.CONTINUOUS_LIMIT]


def test_absence_resets_continuous_segment() -> None:
    state, _, _ = feed(MonitorState(), frames_open(10), cfg())
    # 离开超过宽限期（默认 30s）后回来
    state, _, _ = feed(state, [(2.0, None), (60.0, None)], cfg())
    # 恢复的第一帧只重建基线，第二帧开始正常累计
    state, _, snaps = feed(state, [(60.1, synthetic_landmarks())], cfg())
    assert state.session.continuous_s == 0.0
    assert snaps[0].face_present is True
    state, _, _ = feed(state, [(60.2, synthetic_landmarks())], cfg())
    assert state.session.continuous_s == pytest.approx(0.1)


def test_face_loss_recovery_does_not_phantom_count() -> None:
    # 「闭眼 → 丢失人脸 → 重新检测到睁眼」：不得误计眨眼，也不得计入断档时间
    frames = [
        (0.0, synthetic_landmarks(ear=0.10)),
        (0.5, None),
        (1.0, synthetic_landmarks(ear=0.35)),
    ]
    state, reminders, _ = feed(MonitorState(), frames, cfg())
    assert state.blink.total == 0
    assert state.session.total_s == 0.0
    assert reminders == []


def test_near_closed_eye_on_widescreen_still_detected() -> None:
    wide = 16 / 9
    # 几何 EAR 0.15（闭眼）：不做宽高比校正会被算成 0.2667（睁眼）导致漏检
    frames = [
        (0.0, synthetic_landmarks(ear=0.35 * wide)),
        (0.1, synthetic_landmarks(ear=0.35 * wide)),
        (0.2, synthetic_landmarks(ear=0.15 * wide)),
        (0.3, synthetic_landmarks(ear=0.35 * wide)),
    ]
    state, _, _ = feed(MonitorState(), frames, cfg(), aspect=wide)
    assert state.blink.total == 1


def test_blink_rate_reported_in_snapshot() -> None:
    frames = []
    t = 0.0
    for _ in range(3):
        frames.append((t, synthetic_landmarks(ear=0.35)))
        t += 0.1
        frames.append((t, synthetic_landmarks(ear=0.10)))
        t += 0.1
        frames.append((t, synthetic_landmarks(ear=0.35)))
        t += 0.1
    _, _, snaps = feed(MonitorState(), frames, cfg())
    assert snaps[-1].blink_rate_per_min == 3.0  # 60s 窗口内 3 次眨眼


def test_low_blink_rate_reminder_after_warmup() -> None:
    # 阈值确认后才启用；需累计满一个窗口（60s 检测时长）才判定，避免冷启动误报
    config = cfg(blink_rate_remind_per_min=10)
    frames = [(i * 1.0, synthetic_landmarks()) for i in range(62)]
    _, reminders, snaps = feed(MonitorState(), frames, config)
    kinds = [r.kind for r in reminders]
    assert kinds.count(ReminderKind.BLINK_RATE_LOW) == 1  # 冷却期内不重复
    assert snaps[-1].blink_rate_per_min == 0.0


def test_blink_rate_reminder_disabled_by_default() -> None:
    frames = [(i * 1.0, synthetic_landmarks()) for i in range(62)]
    _, reminders, _ = feed(MonitorState(), frames, cfg())
    assert reminders == []


def test_interrupt_detection_resets_transient_state() -> None:
    # 暂停/出错中断：眨眼相位、频率窗口、连续段清零；总数与累计保留
    closed = synthetic_landmarks(ear=0.10)
    state, _, _ = feed(MonitorState(), [(0.0, closed), (0.1, closed)], cfg())
    assert state.blink.phase is EyePhase.CLOSED
    state = replace(
        state,
        blink_times=(0.05,),
        session=SessionState(total_s=10.0, continuous_s=10.0, last_now=0.1, was_present=True),
    )
    interrupted = interrupt_detection(state)
    assert interrupted.blink.phase is EyePhase.OPEN
    assert interrupted.blink.total == state.blink.total
    assert interrupted.blink_times == ()
    assert interrupted.session.continuous_s == 0.0
    assert interrupted.session.was_present is False
    assert interrupted.session.total_s == 10.0


def test_blink_rate_reminder_requires_fresh_window_after_break() -> None:
    # 先满窗口正常眨眼（30 次/分），离开 80 秒后回来：新一段有效检测为 0，
    # 不得用历史累计时长判定窗口已采满而立刻弹低频提醒
    config = cfg(blink_rate_remind_per_min=10)
    frames = []
    t = 0.0
    pattern = [0.35, 0.35, 0.10, 0.35]  # 每 2 秒一次眨眼
    i = 0
    while t < 62.0:
        frames.append((t, synthetic_landmarks(ear=pattern[i % 4])))
        i += 1
        t += 0.5
    while t < 142.0:  # 离开 80 秒：连续段重置、窗口内眨眼全部过期
        frames.append((t, None))
        t += 1.0
    frames.append((t + 0.5, synthetic_landmarks(ear=0.35)))  # 回来第一帧
    _, reminders, _ = feed(MonitorState(), frames, config)
    assert ReminderKind.BLINK_RATE_LOW not in [r.kind for r in reminders]
