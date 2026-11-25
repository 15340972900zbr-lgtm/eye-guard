"""Monitor 后台线程生命周期测试：假摄像头/假引擎，验证摄像头占用与错误恢复。

不依赖真实硬件，但使用真实线程与休眠，属于低速集成测试。
"""

import time

import numpy as np

from _synthetic import synthetic_landmarks
from eye_guard.config import EyeGuardConfig
from eye_guard.monitor import Monitor, ReminderKind


class FakeCamera:
    def __init__(self, fail_first_open: int = 0) -> None:
        self._fail_remaining = fail_first_open
        self._opened = False
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> bool:
        self.open_calls += 1
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            return False
        self._opened = True
        return True

    def is_open(self) -> bool:
        return self._opened

    def close(self) -> None:
        self.close_calls += 1
        self._opened = False

    def read_frame(self) -> np.ndarray | None:
        if not self._opened:
            return None
        return np.zeros((480, 640, 3), dtype=np.uint8)


class FakeEngine:
    def __init__(self, fail_after: int | None = None) -> None:
        self._fail_after = fail_after
        self.calls = 0

    def detect(self, _frame, _timestamp_ms):
        self.calls += 1
        if self._fail_after is not None and self.calls > self._fail_after:
            raise RuntimeError("engine boom")
        return synthetic_landmarks()


class SwitchingEngine:
    """先持续输出闭眼，release() 之后输出睁眼。"""

    def __init__(self) -> None:
        self.calls = 0
        self._open = False

    def release(self) -> None:
        self._open = True

    def detect(self, _frame, _timestamp_ms):
        self.calls += 1
        return synthetic_landmarks(ear=0.35 if self._open else 0.10)


class StallingCamera(FakeCamera):
    """句柄保持打开，但永远读不出帧。"""

    def read_frame(self):  # noqa: PLR6301 - 测试替身无需 self
        return None


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def make_monitor(camera, engine) -> Monitor:
    config = EyeGuardConfig(analysis_interval_s=0.005)
    return Monitor(camera, engine, config)


def drain_into(monitor, kinds) -> bool:
    kinds.extend(r.kind for r in monitor.drain_reminders())
    return ReminderKind.CAMERA_ERROR in kinds


def test_pause_releases_camera_and_resume_reopens() -> None:
    camera, engine = FakeCamera(), FakeEngine()
    monitor = make_monitor(camera, engine)
    monitor.start()
    try:
        assert wait_until(lambda: monitor.snapshot().face_present)
        monitor.pause()
        assert wait_until(lambda: camera.close_calls >= 1), "暂停后摄像头应被释放"
        monitor.resume()
        assert wait_until(lambda: camera.open_calls >= 2 and monitor.snapshot().face_present)
    finally:
        monitor.stop()
    assert not camera.is_open()


def test_engine_exception_auto_pauses_and_releases_camera() -> None:
    camera, engine = FakeCamera(), FakeEngine(fail_after=3)
    monitor = make_monitor(camera, engine)
    monitor.start()
    kinds: list = []
    try:
        assert wait_until(lambda: drain_into(monitor, kinds)), "推理异常应产生 CAMERA_ERROR 提醒"
        assert monitor.is_paused()
        assert wait_until(lambda: camera.close_calls >= 1), "异常自动暂停后摄像头应被释放"
    finally:
        monitor.stop()


def test_camera_open_failure_can_retry_after_resume() -> None:
    camera, engine = FakeCamera(fail_first_open=1), FakeEngine()
    monitor = make_monitor(camera, engine)
    monitor.start()
    kinds: list = []
    try:
        assert wait_until(lambda: drain_into(monitor, kinds)), "首次打开失败应产生 CAMERA_ERROR"
        assert monitor.is_paused()
        monitor.resume()  # 用户再次点击「恢复监控」应重试打开
        assert wait_until(lambda: monitor.snapshot().face_present)
        assert camera.open_calls >= 2
    finally:
        monitor.stop()


def test_short_pause_does_not_phantom_count() -> None:
    # 「闭眼 → 暂停 0.3s → 恢复时睁眼」：不得误计眨眼，暂停时间不得计入用眼
    camera, engine = FakeCamera(), SwitchingEngine()
    monitor = make_monitor(camera, engine)
    monitor.start()
    try:
        assert wait_until(lambda: engine.calls >= 2)  # 闭眼帧已被处理
        monitor.pause()
        engine.release()  # 暂停期间目标变为睁眼
        time.sleep(0.3)
        monitor.resume()
        assert wait_until(lambda: monitor.snapshot().face_present)
        time.sleep(0.15)
        snap = monitor.snapshot()
        assert snap.blink_total == 0, "暂停后恢复不得把中断前的闭眼误计为眨眼"
        assert snap.total_s < 0.25, "暂停期间的时间不得计入用眼时长"
        assert snap.continuous_s < 0.25, "连续段应在暂停时清零重新累计"
    finally:
        monitor.stop()


def test_stalled_camera_auto_pauses_with_error() -> None:
    # 句柄打开但持续读不到帧：应报错、自动暂停并释放摄像头，而不是静默监控
    camera, engine = StallingCamera(), FakeEngine()
    config = EyeGuardConfig(analysis_interval_s=0.005, camera_stall_timeout_s=0.3)
    monitor = Monitor(camera, engine, config)
    kinds: list = []
    monitor.start()
    try:
        assert wait_until(lambda: drain_into(monitor, kinds)), "持续无帧应产生 CAMERA_ERROR"
        assert monitor.is_paused()
        assert wait_until(lambda: camera.close_calls >= 1), "应释放卡死的摄像头句柄"
    finally:
        monitor.stop()


def test_posture_confirmation_and_reminder_use_the_shared_camera(monkeypatch):
    from eye_guard import monitor as monitor_module
    from eye_guard.posture import PostureCalibration

    class FakePose:
        score = 0.1
        calls = 0
        closed = False

        def detect(self, _frame, _timestamp_ms):
            self.calls += 1
            return self.score

        def close(self):
            self.closed = True

    camera, pose = FakeCamera(), FakePose()
    monkeypatch.setattr(monitor_module, "PostureLandmarkerEngine", lambda: pose)
    monitor = Monitor(camera, FakeEngine(), EyeGuardConfig(analysis_interval_s=0.005))
    monitor.start()
    try:
        assert wait_until(lambda: monitor.snapshot().face_present)
        assert pose.calls == 0
        monitor.calibrate_posture(PostureCalibration.UPRIGHT)
        assert wait_until(lambda: monitor.posture_snapshot().upright_max == 0.1)
        pose.score = 0.3
        monitor.calibrate_posture(PostureCalibration.LIMIT)
        assert wait_until(lambda: monitor.posture_snapshot().limit == 0.3)
        pose.score = 0.4
        assert wait_until(lambda: monitor.posture_snapshot().last_reminder is not None)
        assert any("坐直" in notice.message for notice in monitor.drain_reminders())
        assert camera.open_calls == 1
        monitor.disable_posture()
        assert not monitor.posture_snapshot().sampling
    finally:
        monitor.stop()
    assert pose.closed


def test_missing_posture_model_does_not_pause_face_monitoring(monkeypatch):
    from eye_guard import monitor as monitor_module
    from eye_guard.posture import PostureCalibration

    def no_model():
        raise FileNotFoundError("姿势模型未安装")

    monkeypatch.setattr(monitor_module, "PostureLandmarkerEngine", no_model)
    monitor = make_monitor(FakeCamera(), FakeEngine())
    monitor.start()
    messages = []
    try:
        monitor.calibrate_posture(PostureCalibration.UPRIGHT)

        def model_error_reported():
            messages.extend(monitor.drain_reminders())
            return any("姿势模型未安装" in item.message for item in messages)

        assert wait_until(model_error_reported)
        assert monitor.snapshot().face_present
        assert not monitor.is_paused()
    finally:
        monitor.stop()
