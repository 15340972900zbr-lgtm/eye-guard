from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot, isfinite

LEFT_EYE = (362, 385, 387, 263, 373, 380)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)


@dataclass(frozen=True)
class Observation:
    ear: float
    face_ratio: float


def _distance(a, b, aspect: float) -> float:
    return hypot((a[0] - b[0]) * aspect, a[1] - b[1])


def _ear(points, indices, aspect: float) -> float | None:
    a, b, c, d, e, f = (points[index] for index in indices)
    span = _distance(a, d, aspect)
    if span <= 0:
        return None
    return (_distance(b, f, aspect) + _distance(c, e, aspect)) / (2 * span)


def measure(points: Sequence[tuple[float, float]], aspect: float) -> Observation | None:
    if len(points) <= max(LEFT_EYE) or not isfinite(aspect) or aspect <= 0:
        return None
    left, right = (_ear(points, eye, aspect) for eye in (LEFT_EYE, RIGHT_EYE))
    if left is None or right is None:
        return None
    xs, ys = zip(*points, strict=True)
    area = (min(1.0, max(xs)) - max(0.0, min(xs))) * (min(1.0, max(ys)) - max(0.0, min(ys)))
    if not (0 < area <= 1 and isfinite(left) and isfinite(right)):
        return None
    return Observation((left + right) / 2, area)
