"""MediaPipe 人脸与坐姿推理，图像帧仅在内存中处理。

模型文件为本地 .task 文件，运行期不发起任何网络请求、不落盘任何帧。
"""

from pathlib import Path

import cv2
import numpy as np

from eye_guard.posture import head_forward_score

POSTURE_MODEL_PATH = Path("assets/pose_landmarker_lite.task")
_POSTURE_POINTS = (7, 8, 11, 12)  # 左/右耳、左/右肩
_MIN_VISIBILITY = 0.5


class FaceLandmarkerEngine:
    """Face Landmarker（VIDEO 模式）封装：BGR 帧 -> 归一化关键点 (N, 2)。"""

    def __init__(self, model_path: str | Path = "assets/face_landmarker.task") -> None:
        import mediapipe as mp  # 延迟导入：重量级，避免拖慢纯逻辑测试
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        model_file = Path(model_path)
        if not model_file.is_file():
            raise FileNotFoundError(
                f"未找到人脸关键点模型 {model_file}。"
                "请先运行: uv run python scripts/download_model.py（详见 README）"
            )

        base_options = mp_python.BaseOptions(model_asset_path=str(model_file))
        options = mp_vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
        )
        self._mp = mp
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> np.ndarray | None:
        """对单帧推理，返回 (478, 2) 归一化关键点；未检出人脸返回 None。

        timestamp_ms 必须单调递增（VIDEO 模式要求），由调用方保证。
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.face_landmarks:
            return None
        return np.array([[p.x, p.y] for p in result.face_landmarks[0]], dtype=np.float32)


class PostureLandmarkerEngine:
    """使用 Lite 模型，从和人脸检测共用的帧估计头部前伸。"""

    def __init__(self) -> None:
        if not POSTURE_MODEL_PATH.is_file():
            raise FileNotFoundError(
                "缺少坐姿模型。请运行 uv run python scripts/download_model.py。"
            )

        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(POSTURE_MODEL_PATH)),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
        )
        self._mp = mp
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> float | None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.pose_landmarks or not result.pose_world_landmarks:
            return None

        points = []
        for index in _POSTURE_POINTS:
            view = result.pose_landmarks[0][index]
            if view.visibility is None or not _MIN_VISIBILITY <= view.visibility <= 1:
                return None
            if view.x is None or view.y is None or not (0 <= view.x <= 1 and 0 <= view.y <= 1):
                return None
            point = result.pose_world_landmarks[0][index]
            if point.x is None or point.y is None or point.z is None:
                return None
            points.append((point.x, point.y, point.z))

        left_ear, right_ear, left_shoulder, right_shoulder = points
        return head_forward_score((left_ear, right_ear), (left_shoulder, right_shoulder))

    def close(self) -> None:
        self._landmarker.close()
