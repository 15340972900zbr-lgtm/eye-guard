"""metrics 纯函数测试：EAR、人脸框占比、相对距离。"""

import math

import pytest

from _synthetic import synthetic_landmarks
from eye_guard import metrics


def six_point_eye(ear: float, width: float = 1.0) -> list[tuple[float, float]]:
    """构造已知 EAR 的单眼六关键点，顺序 p1..p6。"""
    half = ear * width / 2
    return [
        (0.0, 0.0),  # p1 眼角
        (0.3 * width, -half),  # p2 上睑
        (0.7 * width, -half),  # p3 上睑
        (width, 0.0),  # p4 眼角
        (0.7 * width, half),  # p5 下睑
        (0.3 * width, half),  # p6 下睑
    ]


@pytest.mark.parametrize("ear", [0.05, 0.2, 0.35])
def test_ear_returns_designed_ratio(ear: float) -> None:
    pts = six_point_eye(ear)
    assert math.isclose(metrics.eye_aspect_ratio(pts, range(6)), ear, rel_tol=1e-9)


def test_ear_is_scale_invariant() -> None:
    assert math.isclose(
        metrics.eye_aspect_ratio(six_point_eye(0.3, width=1.0), range(6)),
        metrics.eye_aspect_ratio(six_point_eye(0.3, width=10.0), range(6)),
    )


def test_closed_eye_has_zero_ear() -> None:
    assert metrics.eye_aspect_ratio(six_point_eye(0.0), range(6)) == 0.0


def test_ear_corrected_for_frame_aspect() -> None:
    # 同一只眼（几何 EAR 0.15）在 16:9 帧上的归一化坐标：
    # 未校正会算成 0.15 * 16/9 = 0.2667，跨过闭眼/睁眼阈值
    pts = six_point_eye(0.15 * 16 / 9)
    assert math.isclose(metrics.eye_aspect_ratio(pts, range(6), aspect=16 / 9), 0.15, rel_tol=1e-9)
    uncorrected = metrics.eye_aspect_ratio(pts, range(6))
    assert math.isclose(uncorrected, 0.15 * 16 / 9, rel_tol=1e-9)


def test_average_ear_uses_both_eyes() -> None:
    lms = synthetic_landmarks(ear=0.4)
    assert math.isclose(metrics.average_ear(lms), 0.4, rel_tol=1e-6)
    assert math.isclose(metrics.average_ear(lms, aspect=2.0), 0.2, rel_tol=1e-6)


def test_face_box_ratio_matches_bbox_area() -> None:
    lms = synthetic_landmarks(box=(0.3, 0.2, 0.7, 0.6))
    assert math.isclose(metrics.face_box_ratio(lms), 0.4 * 0.4)


def test_closer_face_has_larger_box_ratio() -> None:
    near = metrics.face_box_ratio(synthetic_landmarks(box=(0.2, 0.1, 0.8, 0.7)))
    far = metrics.face_box_ratio(synthetic_landmarks(box=(0.35, 0.25, 0.65, 0.55)))
    assert near > far


def test_proximity_is_current_over_baseline() -> None:
    assert math.isclose(metrics.proximity(0.24, 0.12), 2.0)


def test_proximity_rejects_nonpositive_baseline() -> None:
    with pytest.raises(ValueError):
        metrics.proximity(0.2, 0.0)
