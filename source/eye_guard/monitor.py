import time
from dataclasses import replace
from pathlib import Path
from threading import Condition, Thread

from .camera import Camera, Vision
from .config import Config
from .state import State, advance, interrupt


class Monitor:
    def __init__(self, config: Config, model: Path, camera_factory=Camera, vision_factory=Vision):
        self.config = config
        self.model = model
        self.camera_factory = camera_factory
        self.vision_factory = vision_factory
        self.condition = Condition()
        self.revision = 0
        self.active = False
        self.stopping = False
        self.mode = "未启动"
        self.state = State()
        self.notices: list[tuple[str, str]] = []
        self.worker = Thread(target=self._run, name="eye-guard-camera", daemon=True)
        self.worker.start()

    def start(self) -> None:
        with self.condition:
            if not self.active and not self.stopping:
                self.active = True
                self.revision += 1
                self.mode = "正在打开摄像头"
                self.condition.notify_all()

    def pause(self) -> None:
        with self.condition:
            if self.active:
                self.active = False
                self.revision += 1
                self.mode = "已暂停"
                self.state = interrupt(self.state)
                self.notices.clear()
                self.condition.notify_all()

    def calibrate(self) -> None:
        with self.condition:
            if self.active:
                self.state = replace(self.state, calibration=())
            else:
                self.notices.append(("calibration", "请先启动监控，再校准距离。"))

    def reset(self) -> None:
        with self.condition:
            self.state = State(baseline=self.state.baseline)
            self.notices.clear()

    def snapshot(self):
        with self.condition:
            notices, self.notices = self.notices, []
            return self.mode, self.state.reading, notices

    def close(self) -> None:
        with self.condition:
            self.stopping = True
            self.revision += 1
            self.condition.notify_all()
        self.worker.join(timeout=4)

    def _current(self, revision: int) -> bool:
        return self.active and not self.stopping and self.revision == revision

    def _run(self) -> None:
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.active or self.stopping)
                if self.stopping:
                    return
                revision = self.revision
            try:
                self._run_camera(revision)
            except Exception as exc:
                with self.condition:
                    if self._current(revision):
                        self.active = False
                        self.revision += 1
                        self.mode = "相机或模型出错 · 可重试"
                        self.state = interrupt(self.state)
                        self.notices.append(("error", str(exc)[:180]))

    def _run_camera(self, revision: int) -> None:
        camera = vision = None
        try:
            if not self.model.is_file():
                raise RuntimeError("模型文件缺失，请重新安装护眼工具。")
            vision = self.vision_factory(self.model)
            with self.condition:
                if not self._current(revision):
                    return
            camera = self.camera_factory(self.config.camera_index)
            last_frame = time.monotonic()
            timestamp_ms = 0
            while True:
                with self.condition:
                    if not self._current(revision):
                        return
                began = time.monotonic()
                frame = camera.read()
                now = time.monotonic()
                if frame is None:
                    if now - last_frame >= self.config.camera_stall_timeout_s:
                        raise RuntimeError("摄像头持续没有画面，已释放设备。可在托盘菜单中重试。")
                    observation = None
                else:
                    last_frame = now
                    timestamp_ms = max(timestamp_ms + 1, int(now * 1000))
                    observation = vision.detect(frame, timestamp_ms)
                    del frame
                with self.condition:
                    if self._current(revision):
                        self.mode = "检测中" if observation is not None else "未检测到人脸"
                        self.state, notices = advance(self.state, observation, now, self.config)
                        self.notices.extend(notices)
                    interval = max(0.0, self.config.analysis_interval_s - (time.monotonic() - began))
                    self.condition.wait_for(lambda: not self._current(revision), timeout=interval)
        finally:
            try:
                if camera is not None:
                    camera.close()
            finally:
                if vision is not None:
                    vision.close()
