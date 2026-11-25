import time
from threading import Event

from eye_guard.config import Config
from eye_guard.metrics import Observation
from eye_guard.monitor import Monitor


def wait_for(predicate):
    end = time.monotonic() + 2
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


class FakeCamera:
    def __init__(self, frame=True):
        self.frame = frame
        self.closed = False

    def read(self):
        return object() if self.frame else None

    def close(self):
        self.closed = True


class FakeVision:
    def __init__(self, _model):
        pass

    def detect(self, _frame, _time):
        return Observation(0.35, 0.16)

    def close(self):
        pass


def test_rapid_pause_resume_reopens_and_ignores_old_frame(tmp_path):
    first_frame = Event()
    finish_frame = Event()
    cameras = []

    def open_camera(_index):
        camera = FakeCamera()
        cameras.append(camera)
        return camera

    class Vision(FakeVision):
        def detect(self, frame, timestamp):
            if len(cameras) == 1:
                first_frame.set()
                if not finish_frame.wait(2):
                    raise RuntimeError("test never released frame")
                return Observation(0.10, 0.16)
            return super().detect(frame, timestamp)

    model = tmp_path / "unused-model"
    model.touch()
    monitor = Monitor(Config(analysis_interval_s=0.005), model, open_camera, Vision)
    try:
        monitor.start()
        assert first_frame.wait(2)
        monitor.pause()
        monitor.start()
        finish_frame.set()
        wait_for(lambda: len(cameras) == 2 and monitor.snapshot()[1].present)
        assert cameras[0].closed
        assert monitor.snapshot()[1].blink_total == 0
    finally:
        finish_frame.set()
        monitor.close()
    assert all(camera.closed for camera in cameras)


def test_stalled_camera_closes_and_can_restart(tmp_path):
    first, second = FakeCamera(frame=False), FakeCamera()
    cameras = iter([first, second])
    model = tmp_path / "unused-model"
    model.touch()
    monitor = Monitor(
        Config(analysis_interval_s=0.005, camera_stall_timeout_s=0.04),
        model,
        lambda _index: next(cameras),
        FakeVision,
    )
    try:
        monitor.start()
        wait_for(lambda: first.closed and monitor.snapshot()[0].startswith("相机或模型出错"))
        monitor.start()
        wait_for(lambda: monitor.snapshot()[1].present)
    finally:
        monitor.close()
    assert second.closed
