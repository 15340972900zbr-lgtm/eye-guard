"""配置测试：未确认的提醒阈值默认禁用、TOML 加载与校验。"""

import pytest

from eye_guard.config import EyeGuardConfig, load_config


def test_reminder_thresholds_disabled_by_default() -> None:
    cfg = EyeGuardConfig()
    assert cfg.continuous_remind_minutes is None
    assert cfg.proximity_too_close is None
    assert cfg.proximity_too_far is None
    assert cfg.blink_rate_remind_per_min is None


def test_load_missing_auto_path_returns_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config() == EyeGuardConfig()


def test_load_explicit_missing_file_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")


def test_toml_overrides_values(tmp_path) -> None:
    p = tmp_path / "config.toml"
    p.write_text(
        "continuous_remind_minutes = 20\near_close_threshold = 0.18\n"
        "blink_rate_remind_per_min = 15\nblink_window_s = 90\n"
        "camera_stall_timeout_s = 5\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.continuous_remind_minutes == 20.0
    assert cfg.ear_close_threshold == 0.18
    assert cfg.blink_rate_remind_per_min == 15.0
    assert cfg.blink_window_s == 90.0
    assert cfg.camera_stall_timeout_s == 5.0
    assert cfg.proximity_too_close is None  # 未填写的阈值保持禁用


def test_unknown_key_rejected(tmp_path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("foo = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="foo"):
        load_config(p)


def test_non_numeric_threshold_rejected(tmp_path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('continuous_remind_minutes = "abc"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_non_positive_threshold_rejected(tmp_path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("proximity_too_close = 0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)
