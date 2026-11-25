"""监控编排：纯函数步骤 process_frame + 后台工作线程。

process_frame 输入关键点（或 None）、帧宽高比与时间戳，输出新状态、提醒
事件与快照，完全不依赖摄像头硬件（单元测试使用合成关键点）。
Monitor 线程负责摄像头生命周期：暂停即释放设备，恢复时重新打开；任何
异常自动暂停并透出 CAMERA_ERROR，线程保活等待用户恢复。
"""

import enum
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field, replace

import numpy as np

from eye_guard import metrics
from eye_guard.blink import BlinkState, EyePhase, update_blink
from eye_guard.camera import OpenCVCamera
from eye_guard.config import EyeGuardConfig
from eye_guard.posture import (
    PostureCalibration,
    PostureState,
    interrupt_posture,
    start_posture_calibration,
    update_posture,
)
from eye_guard.session import SessionEvent, SessionState, update_session
from eye_guard.vision import FaceLandmarkerEngine, PostureLandmarkerEngine


class ReminderKind(enum.Enum):
    CONTINUOUS_LIMIT = "continuous_limit"
    TOO_CLOSE = "too_close"
    TOO_FAR = "too_far"
    BLINK_RATE_LOW = "blink_rate_low"
    CALIBRATED = "calibrated"
    CAMERA_ERROR = "camera_error"
    POSTURE = "posture"


@dataclass(frozen=True)
class Reminder:
    kind: ReminderKind
    value: float = 0.0
    message: str = ""  # CAMERA_ERROR 等运行时错误的原文


@dataclass(frozen=True)
class MonitorState:
    blink: BlinkState = field(default_factory=BlinkState)
    session: SessionState = field(default_factory=SessionState)
    baseline_ratio: float | None = None
    calibration_remaining: int = 0
    calibration_samples: tuple[float, ...] = ()
    blink_times: tuple[float, ...] = ()  # 窗口内每次眨眼的时刻
    last_close_reminder: float | None = None
    last_far_reminder: float | None = None
    last_rate_reminder: float | None = None


@dataclass(frozen=True)
class MonitorSnapshot:
    """供 UI 轮询的只读快照。"""

    face_present: bool = False
    ear: float | None = None
    blink_total: int = 0
    blink_rate_per_min: float = 0.0
    continuous_s: float = 0.0
    total_s: float = 0.0
    proximity: float | None = None
    calibrating: bool = False


def start_calibration(state: MonitorState, config: EyeGuardConfig) -> MonitorState:
    return replace(state, calibration_remaining=config.calibration_frames, calibration_samples=())


def interrupt_detection(state: MonitorState) -> MonitorState:
    """标记检测流中断（暂停/出错自动暂停）。

    重置眨眼相位与频率窗口、清零连续段，确保恢复后不会把中断期间的未知
    状态误计为眨眼或用眼时间；眨眼总数、累计用眼时长与距离校准基准保留。
    """
    return MonitorState(
        blink=BlinkState(EyePhase.OPEN, 0, state.blink.total),
        session=SessionState(
            total_s=state.session.total_s,
            last_now=state.session.last_now,
            was_present=False,
        ),
        baseline_ratio=state.baseline_ratio,
        calibration_remaining=state.calibration_remaining,
        calibration_samples=state.calibration_samples,
        blink_times=(),
        last_close_reminder=state.last_close_reminder,
        last_far_reminder=state.last_far_reminder,
        last_rate_reminder=state.last_rate_reminder,
    )


def _cooldown_ok(last: float | None, now: float, cooldown_s: float) -> bool:
    return last is None or now - last >= cooldown_s


def process_frame(
    state: MonitorState,
    landmarks: np.ndarray | None,
    now: float,
    config: EyeGuardConfig,
    aspect: float = 1.0,
) -> tuple[MonitorState, list[Reminder], MonitorSnapshot]:
    """推进一帧监控状态（纯函数）。aspect 为帧宽/帧高，用于校正 EAR。"""
    reminders: list[Reminder] = []
    ear = ratio = None
    if landmarks is not None:
        ear = metrics.average_ear(landmarks, aspect)
        ratio = metrics.face_box_ratio(landmarks)

    # 眨眼：丢脸时重置相位，避免恢复时把未知闭合误计为眨眼
    if landmarks is None:
        blink = BlinkState(EyePhase.OPEN, 0, state.blink.total)
    else:
        blink = update_blink(
            state.blink,
            ear,
            close_threshold=config.ear_close_threshold,
            open_threshold=config.ear_open_threshold,
            min_closed_frames=config.min_closed_frames,
        )
    blink_times = state.blink_times
    if blink.total > state.blink.total:
        blink_times = (*blink_times, now)
    window_s = config.blink_window_s
    blink_times = tuple(t for t in blink_times if now - t <= window_s)
    blink_rate = len(blink_times) * 60.0 / window_s

    remind_limit_s = (
        config.continuous_remind_minutes * 60.0
        if config.continuous_remind_minutes is not None
        else None
    )
    session, events = update_session(
        state.session,
        now,
        landmarks is not None,
        remind_limit_s=remind_limit_s,
        absence_grace_s=config.absence_grace_s,
        gap_reset_s=config.session_gap_reset_s,
    )
    if SessionEvent.CONTINUOUS_LIMIT in events:
        reminders.append(Reminder(ReminderKind.CONTINUOUS_LIMIT, session.continuous_s / 60.0))

    # 距离校准：采样人脸框占比，取平均作为基准
    baseline = state.baseline_ratio
    samples = state.calibration_samples
    remaining = state.calibration_remaining
    was_calibrating = remaining > 0
    if ratio is not None and was_calibrating:
        samples = (*samples, ratio)
        remaining -= 1
        if remaining == 0:
            baseline = sum(samples) / len(samples)
            reminders.append(Reminder(ReminderKind.CALIBRATED, baseline))
            samples = ()

    # 相对距离与距离类提醒（校准期间不判定）
    proximity_value = None
    last_close = state.last_close_reminder
    last_far = state.last_far_reminder
    if ratio is not None and baseline is not None and not was_calibrating:
        proximity_value = metrics.proximity(ratio, baseline)
        if (
            config.proximity_too_close is not None
            and proximity_value > config.proximity_too_close
            and _cooldown_ok(last_close, now, config.reminder_cooldown_s)
        ):
            reminders.append(Reminder(ReminderKind.TOO_CLOSE, proximity_value))
            last_close = now
        if (
            config.proximity_too_far is not None
            and proximity_value < config.proximity_too_far
            and _cooldown_ok(last_far, now, config.reminder_cooldown_s)
        ):
            reminders.append(Reminder(ReminderKind.TOO_FAR, proximity_value))
            last_far = now

    # 眨眼频率过低提醒：以「当前连续段」覆盖满一个窗口为预热条件，
    # 离开/暂停后回来需重新采满窗口，不用历史累计时长判定
    last_rate = state.last_rate_reminder
    if (
        config.blink_rate_remind_per_min is not None
        and landmarks is not None
        and session.continuous_s >= window_s
        and blink_rate < config.blink_rate_remind_per_min
        and _cooldown_ok(last_rate, now, config.reminder_cooldown_s)
    ):
        reminders.append(Reminder(ReminderKind.BLINK_RATE_LOW, blink_rate))
        last_rate = now

    new_state = MonitorState(
        blink=blink,
        session=session,
        baseline_ratio=baseline,
        calibration_remaining=remaining,
        calibration_samples=samples,
        blink_times=blink_times,
        last_close_reminder=last_close,
        last_far_reminder=last_far,
        last_rate_reminder=last_rate,
    )
    snapshot = MonitorSnapshot(
        face_present=landmarks is not None,
        ear=ear,
        blink_total=blink.total,
        blink_rate_per_min=blink_rate,
        continuous_s=session.continuous_s,
        total_s=session.total_s,
        proximity=proximity_value,
        calibrating=remaining > 0,
    )
    return new_state, reminders, snapshot


class Monitor:
    """后台线程：采集 -> 推理 -> process_frame。UI 轮询 snapshot/drain_reminders。"""

    def __init__(
        self,
        camera: OpenCVCamera,
        engine: FaceLandmarkerEngine | None,
        config: EyeGuardConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._camera = camera
        self._engine = engine
        self._config = config
        self._clock = clock
        self._lock = threading.Lock()
        self._state = MonitorState()
        self._snapshot = MonitorSnapshot()
        self._pending: list[Reminder] = []
        self._thread: threading.Thread | None = None
        self._active = threading.Event()  # clear = 暂停分析并释放摄像头
        self._stop_flag = threading.Event()
        self._last_frame_at: float | None = None
        self._posture = PostureState()
        self._posture_engine: PostureLandmarkerEngine | None = None
        self._posture_revision = 0
        self._posture_due = 0.0
        self._posture_interval = 4 * config.analysis_interval_s

    def is_started(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_paused(self) -> bool:
        return self.is_started() and not self._active.is_set()

    def start(self) -> None:
        if self.is_started():
            return
        if self._engine is None:
            raise RuntimeError("模型未就绪，请先运行: uv run python scripts/download_model.py")
        self._stop_flag.clear()
        self._active.set()
        self._thread = threading.Thread(target=self._run, name="eye-guard-monitor", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        # 先关闸再标记中断：与工作线程的加锁处理互斥，保证中断标记
        # 不会被暂停后才处理完的最后一帧覆盖
        self._active.clear()
        self._interrupt()

    def _interrupt(self) -> None:
        with self._lock:
            self._state = interrupt_detection(self._state)
            self._posture = interrupt_posture(self._posture)
            self._posture_revision += 1
            self._posture_due = 0.0

    def resume(self) -> None:
        self._active.set()

    def stop(self) -> None:
        self._stop_flag.set()
        self._active.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._camera.close()

    def calibrate(self) -> None:
        with self._lock:
            self._state = start_calibration(self._state, self._config)

    def calibrate_posture(self, phase: PostureCalibration) -> None:
        with self._lock:
            if not self._active.is_set() or self._stop_flag.is_set():
                raise ValueError("请先启动监控，再校准坐姿。")
            self._posture = start_posture_calibration(self._posture, phase)
            self._posture_revision += 1
            self._posture_due = 0.0
            self._pending = [r for r in self._pending if r.kind is not ReminderKind.POSTURE]

    def disable_posture(self) -> None:
        with self._lock:
            self._posture = PostureState()
            self._posture_revision += 1
            self._pending = [r for r in self._pending if r.kind is not ReminderKind.POSTURE]

    def posture_snapshot(self) -> PostureState:
        with self._lock:
            return self._posture

    def reset_stats(self) -> None:
        """清零计数与连续段，保留距离校准基准。"""
        with self._lock:
            self._state = MonitorState(baseline_ratio=self._state.baseline_ratio)

    def snapshot(self) -> MonitorSnapshot:
        with self._lock:
            return self._snapshot

    def drain_reminders(self) -> list[Reminder]:
        with self._lock:
            pending = self._pending
            self._pending = []
        return pending

    def _emit_error(self, message: str) -> None:
        with self._lock:
            self._pending.append(Reminder(ReminderKind.CAMERA_ERROR, message=message))

    def _sample_posture(
        self, frame: np.ndarray | None, timestamp_ms: int, now: float, revision: int
    ) -> None:
        with self._lock:
            if revision != self._posture_revision or not self._posture.sampling:
                return
            if frame is None:
                if self._posture.last_sample_at is not None:
                    self._posture = interrupt_posture(self._posture)
                return
            if now < self._posture_due:
                return
            self._posture_due = now + self._posture_interval

        error = None
        try:
            if self._posture_engine is None:
                self._posture_engine = PostureLandmarkerEngine()
            score = self._posture_engine.detect(frame, timestamp_ms)
        except Exception as exc:
            if self._posture_engine is not None:
                with suppress(Exception):
                    self._posture_engine.close()
                self._posture_engine = None
            error = f"坐姿检测已关闭：{exc}"
            score = None

        with self._lock:
            if (
                revision != self._posture_revision
                or not self._active.is_set()
                or self._stop_flag.is_set()
            ):
                return
            if error is None:
                self._posture, message = update_posture(
                    self._posture,
                    score,
                    now,
                    hold_s=self._config.calibration_frames * self._config.analysis_interval_s,
                    max_gap_s=2 * self._posture_interval,
                    cooldown_s=self._config.reminder_cooldown_s,
                )
            else:
                self._posture, message = PostureState(), error
            if message is not None:
                self._pending.append(Reminder(ReminderKind.POSTURE, message=message))

    def _run(self) -> None:
        ts_ms = 0
        try:
            while not self._stop_flag.is_set():
                if not self._active.is_set():
                    if self._camera.is_open():
                        self._camera.close()  # 暂停即释放摄像头，供其他应用使用
                    self._active.wait(timeout=0.2)
                    continue
                try:
                    now = self._clock()
                    if not self._camera.is_open():
                        if not self._camera.open():
                            raise RuntimeError(
                                "无法打开摄像头，请检查系统设置 > 隐私与安全性 > 相机权限。"
                            )
                        self._last_frame_at = now
                    with self._lock:
                        posture_revision = self._posture_revision
                    frame = self._camera.read_frame()
                    landmarks = None
                    aspect = 1.0
                    if frame is not None:
                        self._last_frame_at = now
                        aspect = frame.shape[1] / frame.shape[0]
                        ts_ms = max(ts_ms + 1, int(self._clock() * 1000))
                        landmarks = self._engine.detect(frame, ts_ms)
                    elif (
                        self._last_frame_at is not None
                        and now - self._last_frame_at > self._config.camera_stall_timeout_s
                    ):
                        # 句柄还开着但持续读不出画面：视为摄像头故障
                        raise RuntimeError(
                            "摄像头已打开但持续读不到画面，已自动暂停并释放；"
                            "可点击「恢复监控」重试。"
                        )
                    self._sample_posture(
                        frame if landmarks is not None else None,
                        ts_ms,
                        self._clock(),
                        posture_revision,
                    )
                    frame = None  # 帧数据仅存于内存，用完即弃
                    now = self._clock()
                    with self._lock:
                        if self._active.is_set():  # 暂停可能在采帧期间到达
                            self._state, reminders, self._snapshot = process_frame(
                                self._state, landmarks, now, self._config, aspect
                            )
                            self._pending.extend(reminders)
                except Exception as exc:  # 后台线程兜底：任何异常不得让线程带死
                    self._active.clear()
                    self._interrupt()
                    self._emit_error(f"监控出错，已自动暂停：{exc}")
                    continue
                time.sleep(self._config.analysis_interval_s)
        finally:
            try:
                self._camera.close()  # 线程退出（stop 或未捕获异常）必释放摄像头
            finally:
                if self._posture_engine is not None:
                    self._posture_engine.close()
                    self._posture_engine = None
