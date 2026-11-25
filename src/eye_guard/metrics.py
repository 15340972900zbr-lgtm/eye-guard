"""生理指标纯函数：EAR、人脸框占比、相对距离。

输入为归一化关键点坐标（MediaPipe Face Landmarker 输出，x/y ∈ [0, 1]），
输出为数值指标。不依赖摄像头硬件，便于单元测试。
"""

import math
from collections.abc import Iterable, Sequence

Point = Sequence[float]

# MediaPipe Face Mesh 眼部六关键点（p1..p6：眼角/上睑/上睑/眼角/下睑/下睑）
LEFT_EYE_INDICES = (362, 385, 387, 263, 373, 380)
RIGHT_EYE_INDICES = (33, 160, 158, 133, 153, 144)


def _dist(p: Point, q: Point, aspect: float = 1.0) -> float:
    # 关键点为归一化坐标（x 除以帧宽、y 除以帧高），aspect = 帧宽/帧高
    # 用于把 x 统一到与 y 相同的单位（帧高），否则 EAR 会随画面宽高比漂移
    return math.hypot((p[0] - q[0]) * aspect, p[1] - q[1])


def eye_aspect_ratio(
    landmarks: Sequence[Point], indices: Iterable[int], aspect: float = 1.0
) -> float:
    """EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)。闭眼时趋于 0。"""
    p = [landmarks[i] for i in indices]
    horizontal = _dist(p[0], p[3], aspect)
    if horizontal == 0.0:
        return 0.0
    vertical = _dist(p[1], p[5]) + _dist(p[2], p[4])
    return vertical / (2.0 * horizontal)


def average_ear(landmarks: Sequence[Point], aspect: float = 1.0) -> float:
    """双眼 EAR 的平均值。"""
    return (
        eye_aspect_ratio(landmarks, LEFT_EYE_INDICES, aspect)
        + eye_aspect_ratio(landmarks, RIGHT_EYE_INDICES, aspect)
    ) / 2.0


def face_box_ratio(landmarks: Sequence[Point]) -> float:
    """人脸框占比：全部关键点包围盒面积（归一化坐标系，即相对帧面积）。"""
    xs = [pt[0] for pt in landmarks]
    ys = [pt[1] for pt in landmarks]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def proximity(current_ratio: float, baseline_ratio: float) -> float:
    """相对距离 = 当前人脸框占比 / 校准基准。>1 比校准时更近，<1 更远。"""
    if baseline_ratio <= 0:
        raise ValueError("baseline_ratio must be positive")
    return current_ratio / baseline_ratio
