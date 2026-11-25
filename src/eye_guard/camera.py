"""摄像头采集模块：帧仅存在于内存中，严禁写盘或联网。

cv2 由 mediapipe 的依赖链提供（opencv-contrib-python）。
"""

import cv2
import numpy as np


class OpenCVCamera:
    """macOS 摄像头采集的薄封装，线程所有权归属 Monitor 工作线程。"""

    def __init__(self, camera_index: int = 0) -> None:
        self._camera_index = camera_index
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        """打开摄像头；失败时释放句柄，下次调用重新尝试（授权后可恢复）。"""
        if self._cap is not None:
            if self._cap.isOpened():
                return True
            self._cap.release()
            self._cap = None
        self._cap = cv2.VideoCapture(self._camera_index)
        return self._cap.isOpened()

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def read_frame(self) -> np.ndarray | None:
        """读取一帧 BGR 图像（仅内存），失败返回 None。"""
        if not self.is_open():
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
