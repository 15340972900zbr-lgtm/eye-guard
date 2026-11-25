"""摄像头采集模块测试：打开失败后必须重试，句柄状态必须可查询。"""

import eye_guard.camera as camera_module
from eye_guard.camera import OpenCVCamera


class FakeVideoCapture:
    def __init__(self, opened: bool) -> None:
        self._opened = opened

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self._opened = False


def test_open_failure_retries_on_next_call(monkeypatch) -> None:
    calls = {"n": 0}

    def factory(_index: int) -> FakeVideoCapture:
        calls["n"] += 1
        return FakeVideoCapture(opened=calls["n"] > 1)

    monkeypatch.setattr(camera_module.cv2, "VideoCapture", factory)
    camera = OpenCVCamera()
    assert camera.open() is False
    # 首次失败后必须释放失败句柄、重新尝试，而不是永远返回缓存结果
    assert camera.open() is True
    assert calls["n"] == 2


def test_is_open_reflects_lifecycle(monkeypatch) -> None:
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda _i: FakeVideoCapture(opened=True))
    camera = OpenCVCamera()
    assert camera.is_open() is False
    assert camera.open() is True
    assert camera.is_open() is True
    camera.close()
    assert camera.is_open() is False
