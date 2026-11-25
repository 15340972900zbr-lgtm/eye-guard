from pathlib import Path

from .metrics import measure


class Camera:
    def __init__(self, index: int) -> None:
        import cv2

        self.cv2 = cv2
        self.handle = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.handle.isOpened():
            self.handle.release()
            self.handle = cv2.VideoCapture(index, cv2.CAP_MSMF)
        if not self.handle.isOpened():
            self.handle.release()
            raise RuntimeError("无法打开摄像头。请检查 Windows 相机权限，或关闭正在使用相机的其他软件。")
        self.handle.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.handle.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    def read(self):
        ok, frame = self.handle.read()
        return frame if ok else None

    def close(self) -> None:
        self.handle.release()


class Vision:
    def __init__(self, model: Path) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        self.mp = mp
        self.cv2 = __import__("cv2")
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_buffer=model.read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)

    def detect(self, frame, timestamp_ms):
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.detector.detect_for_video(image, timestamp_ms)
        if not result.face_landmarks:
            return None
        points = [(point.x, point.y) for point in result.face_landmarks[0]]
        return measure(points, frame.shape[1] / frame.shape[0])

    def close(self) -> None:
        self.detector.close()
