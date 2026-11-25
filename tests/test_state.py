from dataclasses import replace

import pytest
from eye_guard.config import Config, load_config
from eye_guard.metrics import LEFT_EYE, RIGHT_EYE, Observation, measure
from eye_guard.state import State, advance, interrupt

OPEN = Observation(0.35, 0.16)
CLOSED = Observation(0.15, 0.16)


def feed(frames, config=None, state=None):
    config = config if config is not None else Config()
    state = state if state is not None else State()
    notices = []
    for timestamp, observation in frames:
        state, updates = advance(state, observation, timestamp, config)
        notices.extend(updates)
    return state, notices


def test_widescreen_geometry():
    def points(aspect):
        data = [(0.5, 0.5)] * 478
        for eye, center in ((LEFT_EYE, 0.65), (RIGHT_EYE, 0.35)):
            for index, (x, y) in zip(
                eye,
                [(-0.04, 0), (-0.02, 0.006), (0.02, 0.006), (0.04, 0), (0.02, -0.006), (-0.02, -0.006)],
                strict=True,
            ):
                data[index] = (center + x / aspect, 0.5 + y)
        return data

    for aspect in (1, 16 / 9):
        assert measure(points(aspect), aspect).ear == pytest.approx(0.15)


def test_a_complete_blink_counts_once():
    state, _ = feed([(0.0, OPEN), (0.1, CLOSED), (0.2, CLOSED), (0.3, OPEN), (0.4, OPEN)])
    assert state.reading.blink_total == 1
    assert state.reading.total_seconds == pytest.approx(0.4)


def test_tracking_loss_discards_partial_blink_and_interval():
    state, _ = feed([(0.0, OPEN), (0.1, CLOSED), (0.2, None), (0.4, OPEN)])
    assert state.reading.blink_total == 0
    assert state.reading.total_seconds == pytest.approx(0.1)


def test_pause_preserves_totals_but_discards_incomplete_blink():
    first, _ = feed([(0.0, OPEN), (0.1, CLOSED), (0.2, OPEN), (0.3, CLOSED)])
    state, _ = feed([(0.4, OPEN)], state=interrupt(first))
    assert state.reading.blink_total == 1
    assert state.reading.total_seconds == pytest.approx(0.3)
    assert state.reading.active_seconds == 0


def test_low_rate_requires_a_complete_fresh_window_after_absence():
    config = replace(Config(), blink_window_s=2, blink_rate_remind_per_min=10, reminder_cooldown_s=1)
    first, _ = feed([(0.0, OPEN), (0.5, CLOSED), (1.0, OPEN), (1.5, CLOSED), (2.0, OPEN)], config)
    assert first.reading.blink_rate == 60
    state, notices = feed([(2.5, None), (3.5, OPEN)], config, first)
    assert state.reading.blink_rate is None
    assert notices == []
    state, notices = feed([(4.0, OPEN), (4.5, OPEN), (5.0, OPEN), (5.5, OPEN)], config, state)
    assert state.reading.blink_rate == 0
    assert [kind for kind, _ in notices] == ["blink"]


def test_calibration_sets_baseline_and_distance_warns_only_when_set():
    config = replace(Config(), calibration_frames=2, proximity_too_close=1.2)
    state, notices = feed([(0.0, OPEN), (0.1, OPEN)], config, State(calibration=()))
    assert state.reading.face_scale == 1
    assert [kind for kind, _ in notices] == ["calibrated"]
    state, notices = feed(
        [(0.2, Observation(0.35, 0.24)), (0.3, Observation(0.35, 0.24))], config, state
    )
    assert state.reading.face_scale == pytest.approx(1.5)
    assert [kind for kind, _ in notices] == ["close"]


def test_no_health_thresholds_are_enabled_by_default(tmp_path):
    config = load_config(tmp_path / "config.toml")
    assert config.blink_rate_remind_per_min is None
    assert config.continuous_remind_minutes is None
    assert config.proximity_too_close is None
    assert config.proximity_too_far is None


def test_config_rejects_inverse_ear_thresholds(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("ear_open_threshold = 0.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="睁眼阈值"):
        load_config(path)
