"""测试用合成关键点：构造已知 EAR / 人脸框占比的归一化关键点，不依赖摄像头与模型。"""

import numpy as np

_LEFT_EYE = (362, 385, 387, 263, 373, 380)
_RIGHT_EYE = (33, 160, 158, 133, 153, 144)
_EYE_WIDTH = 0.06
_EYE_Y = 0.40


def synthetic_landmarks(
    ear: float = 0.35,
    box: tuple[float, float, float, float] = (0.30, 0.20, 0.70, 0.60),
) -> np.ndarray:
    """返回 478 个归一化关键点 (N, 3)。

    眼部 6 点构成指定 EAR（水平跨距 _EYE_WIDTH，竖直半距 = ear * width / 2），
    其余点均匀铺满 box，因此人脸框占比 == box 的宽 × 高。
    """
    pts = np.zeros((478, 3), dtype=np.float64)
    pts[:, 0] = np.linspace(box[0], box[2], 478)
    pts[:, 1] = np.linspace(box[1], box[3], 478)
    half = ear * _EYE_WIDTH / 2

    def place(indices: tuple[int, ...], x_left: float) -> None:
        offsets = {
            1: (0.0, 0.0),
            4: (_EYE_WIDTH, 0.0),
            2: (0.02, -half),
            6: (0.02, half),
            3: (0.04, -half),
            5: (0.04, half),
        }
        for slot, idx in enumerate(indices, start=1):
            dx, dy = offsets[slot]
            pts[idx] = (x_left + dx, _EYE_Y + dy, 0.0)

    place(_LEFT_EYE, 0.40)
    place(_RIGHT_EYE, 0.52)
    return pts
