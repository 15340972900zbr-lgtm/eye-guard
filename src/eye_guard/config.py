"""配置：机制参数带工程默认值；提醒阈值未经用户确认，默认一律禁用（None）。

在 config.toml 中填写阈值即视为用户确认该数值（参见 ITERATION_TASK_SPEC.md 的
反幻觉红线：AI 不得代填医学/工程参数）。
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path

AUTO_CONFIG_NAME = "config.toml"


@dataclass(frozen=True)
class EyeGuardConfig:
    # —— 机制参数（工程默认值，可调）——
    model_path: str = "assets/face_landmarker.task"
    analysis_interval_s: float = 0.1  # 分析频率（秒），10 Hz 以内兼顾低功耗
    ear_close_threshold: float = 0.20  # EAR 低于此值判定闭眼
    ear_open_threshold: float = 0.25  # EAR 高于此值判定睁眼（迟滞区间）
    min_closed_frames: int = 1  # 构成一次眨眼的最少闭眼帧数
    absence_grace_s: float = 30.0  # 离开宽限期，超过则连续段重置
    session_gap_reset_s: float = 60.0  # 断档超过该秒数则连续段重置
    calibration_frames: int = 30  # 距离校准采样帧数
    reminder_cooldown_s: float = 300.0  # 距离/频率类提醒冷却（秒）
    blink_window_s: float = 60.0  # 眨眼频率统计窗口（秒）
    camera_stall_timeout_s: float = 3.0  # 句柄开但无帧超过该秒数视为故障

    # —— 提醒阈值（未确认，默认禁用；在 config.toml 中确认后启用）——
    continuous_remind_minutes: float | None = None  # 连续用眼提醒（分钟）
    proximity_too_close: float | None = None  # 相对距离高于此值提醒过近
    proximity_too_far: float | None = None  # 相对距离低于此值提醒过远
    blink_rate_remind_per_min: float | None = None  # 眨眼频率低于此值提醒（次/分）


_FLOAT_FIELDS = frozenset(
    {
        "analysis_interval_s",
        "ear_close_threshold",
        "ear_open_threshold",
        "absence_grace_s",
        "session_gap_reset_s",
        "reminder_cooldown_s",
        "blink_window_s",
        "camera_stall_timeout_s",
        "continuous_remind_minutes",
        "proximity_too_close",
        "proximity_too_far",
        "blink_rate_remind_per_min",
    }
)
_INT_FIELDS = frozenset({"min_closed_frames", "calibration_frames"})
_STR_FIELDS = frozenset({"model_path"})
_NULLABLE = frozenset(
    {
        "continuous_remind_minutes",
        "proximity_too_close",
        "proximity_too_far",
        "blink_rate_remind_per_min",
    }
)


def config_from_dict(data: Mapping[str, object]) -> EyeGuardConfig:
    """从字典构造配置；未知键、类型错误、非正数值直接报错。"""
    valid = {f.name for f in fields(EyeGuardConfig)}
    unknown = set(data) - valid
    if unknown:
        raise ValueError(f"未知配置项: {', '.join(sorted(unknown))}")

    overrides: dict[str, object] = {}
    for name, value in data.items():
        if name in _FLOAT_FIELDS:
            if value is None and name in _NULLABLE:
                overrides[name] = None
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"配置项 {name} 需为正数: {value!r}")
            else:
                overrides[name] = float(value)
        elif name in _INT_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"配置项 {name} 需为正整数: {value!r}")
            else:
                overrides[name] = value
        else:  # _STR_FIELDS
            if not isinstance(value, str) or not value:
                raise ValueError(f"配置项 {name} 需为非空字符串")
            overrides[name] = value
    return replace(EyeGuardConfig(), **overrides)


def load_config(path: str | Path | None = None) -> EyeGuardConfig:
    """加载配置。path 为 None 时自动查找当前目录 config.toml，不存在则用默认值。"""
    if path is None:
        auto = Path(AUTO_CONFIG_NAME)
        if not auto.is_file():
            return EyeGuardConfig()
        path = auto

    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    return config_from_dict(tomllib.loads(config_path.read_text(encoding="utf-8")))
