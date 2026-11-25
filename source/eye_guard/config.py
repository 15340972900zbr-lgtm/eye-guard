import tomllib
from dataclasses import dataclass, fields
from math import isfinite
from pathlib import Path


@dataclass(frozen=True)
class Config:
    camera_index: int = 0
    analysis_interval_s: float = 0.1
    camera_stall_timeout_s: float = 3.0
    ear_close_threshold: float = 0.20
    ear_open_threshold: float = 0.25
    blink_window_s: float = 60.0
    absence_grace_s: float = 30.0
    calibration_frames: int = 30
    reminder_cooldown_s: float = 300.0
    continuous_remind_minutes: float | None = None
    blink_rate_remind_per_min: float | None = None
    proximity_too_close: float | None = None
    proximity_too_far: float | None = None


def load_config(path: Path) -> Config:
    if not path.is_file():
        return Config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    defaults = Config()
    allowed = {field.name for field in fields(defaults)}
    if unknown := data.keys() - allowed:
        raise ValueError(f"未知设置：{', '.join(sorted(unknown))}")
    for key, value in data.items():
        if key in {"camera_index", "calibration_frames"}:
            minimum = 0 if key == "camera_index" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{key} 需要不小于 {minimum} 的整数")
        elif type(value) not in (int, float) or not isfinite(value) or value <= 0:
            raise ValueError(f"{key} 需要有限正数")
    config = Config(**data)
    if config.ear_open_threshold <= config.ear_close_threshold:
        raise ValueError("睁眼阈值需要大于闭眼阈值")
    if config.proximity_too_close is not None and config.proximity_too_close <= 1:
        raise ValueError("过近阈值需要大于 1")
    if config.proximity_too_far is not None and config.proximity_too_far >= 1:
        raise ValueError("过远阈值需要小于 1")
    return config
