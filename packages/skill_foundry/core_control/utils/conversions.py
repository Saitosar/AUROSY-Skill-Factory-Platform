import math


def deg2rad(degrees: float) -> float:
    """Перевод градусов в радианы."""
    return degrees * (math.pi / 180.0)


def rad2deg(radians: float) -> float:
    """Перевод радиан в градусы."""
    return radians * (180.0 / math.pi)

