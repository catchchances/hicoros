import math

import pytest

from hicoros import _vincenty as vincenty_ext
from tests.gcj_helpers import gcj02_to_wgs84_caijun


def _vincenty_reference_python(point1: tuple, point2: tuple) -> float:
    """
    Reference implementation of the Vincenty formula in Python.
    Source: https://github.com/maurycyp/vincenty/blob/48ba4d98/vincenty/__init__.py
    """
    a = 6378137
    f = 1 / 298.257223563
    b = 6356752.314245
    max_iterations = 200
    convergence_threshold = 1e-12

    if point1[0] == point2[0] and point1[1] == point2[1]:
        return 0.0

    u1 = math.atan((1 - f) * math.tan(math.radians(point1[0])))
    u2 = math.atan((1 - f) * math.tan(math.radians(point2[0])))
    l_val = math.radians(point2[1] - point1[1])
    lambda_val = l_val
    sin_u1 = math.sin(u1)
    cos_u1 = math.cos(u1)
    sin_u2 = math.sin(u2)
    cos_u2 = math.cos(u2)

    for _ in range(max_iterations):
        sin_lambda = math.sin(lambda_val)
        cos_lambda = math.cos(lambda_val)
        sin_sigma = math.sqrt((cos_u2 * sin_lambda) ** 2 + (cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lambda) ** 2)
        if sin_sigma == 0:
            return 0.0
        cos_sigma = sin_u1 * sin_u2 + cos_u1 * cos_u2 * cos_lambda
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_u1 * cos_u2 * sin_lambda / sin_sigma
        cos_sq_alpha = 1 - sin_alpha**2
        try:
            cos2_sigma_m = cos_sigma - 2 * sin_u1 * sin_u2 / cos_sq_alpha
        except ZeroDivisionError:
            cos2_sigma_m = 0
        c_val = f / 16 * cos_sq_alpha * (4 + f * (4 - 3 * cos_sq_alpha))
        lambda_prev = lambda_val
        lambda_val = l_val + (1 - c_val) * f * sin_alpha * (
            sigma + c_val * sin_sigma * (cos2_sigma_m + c_val * cos_sigma * (-1 + 2 * cos2_sigma_m**2))
        )
        if abs(lambda_val - lambda_prev) < convergence_threshold:
            break
    else:
        raise Exception(f"Failed to calculate distance between {point1} and {point2}")

    u_sq = cos_sq_alpha * (a**2 - b**2) / (b**2)
    a_val = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
    b_val = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
    delta_sigma = (
        b_val
        * sin_sigma
        * (
            cos2_sigma_m
            + b_val
            / 4
            * (
                cos_sigma * (-1 + 2 * cos2_sigma_m**2)
                - b_val / 6 * cos2_sigma_m * (-3 + 4 * sin_sigma**2) * (-3 + 4 * cos2_sigma_m**2)
            )
        )
    )
    s_val = b * a_val * (sigma - delta_sigma)
    return round(s_val, 6)


@pytest.mark.parametrize(
    ("point1", "point2"),
    [
        ((39.9042, 116.4074), (31.2304, 121.4737)),
        ((22.3193, 114.1694), (22.5431, 114.0579)),
        ((48.8566, 2.3522), (51.5074, -0.1278)),
        ((40.7128, -74.0060), (34.0522, -118.2437)),
        ((-33.8688, 151.2093), (-37.8136, 144.9631)),
        ((64.1466, -21.9426), (59.9139, 10.7522)),
        ((0.0, 179.9), (0.0, -179.9)),
        ((89.0, 0.0), (89.0, 90.0)),
        ((10.0, 20.0), (-10.0, -150.0)),
        ((35.6895, 139.6917), (37.7749, -122.4194)),
        ((-23.5505, -46.6333), (19.4326, -99.1332)),
        ((55.7558, 37.6173), (59.9343, 30.3351)),
        ((-34.6037, -58.3816), (-33.4489, -70.6693)),
        ((1.3521, 103.8198), (13.7563, 100.5018)),
        ((30.5728, 104.0668), (29.5630, 106.5516)),
    ],
)
def test_vincenty_cpp_matches_reference_python_for_known_points(point1, point2):
    cpp_distance = vincenty_ext.vincenty_distance_m(*point1, *point2)
    python_distance = _vincenty_reference_python(point1, point2)

    assert cpp_distance == python_distance
    assert cpp_distance == vincenty_ext.vincenty_distance_m(*point2, *point1)


@pytest.mark.parametrize(
    "point",
    [
        (30.0, 120.0),
        (0.0, 0.0),
        (51.5074, -0.1278),
        (-33.8688, 151.2093),
        (89.999, 45.0),
    ],
)
def test_vincenty_cpp_matches_reference_python_for_same_point(point):
    cpp_distance = vincenty_ext.vincenty_distance_m(*point, *point)
    python_distance = _vincenty_reference_python(point, point)

    assert cpp_distance == python_distance


@pytest.mark.parametrize(
    ("point1", "point2"),
    [
        ((10.0, 20.0), (-10.0, -160.0)),
        ((25.0, 30.0), (-25.0, -150.0)),
        ((1.0, 1.0), (-1.0, 181.0)),
    ],
)
def test_vincenty_cpp_raises_for_antipodal_non_convergence(point1, point2):
    with pytest.raises(RuntimeError, match="Failed to calculate distance"):
        vincenty_ext.vincenty_distance_m(*point1, *point2)


@pytest.mark.parametrize(
    ("point1", "point2"),
    [
        ((42.3541165, -71.0693514), (40.7791472, -73.9680804)),
        ((40.7791472, -73.9680804), (42.3541165, -71.0693514)),
    ],
)
def test_vincenty_cpp_matches_public_boston_newyork_example_values(point1, point2):
    distance_m = vincenty_ext.vincenty_distance_m(*point1, *point2)
    distance_km = distance_m / 1000

    assert distance_km == pytest.approx(298.396057, abs=1e-6)


def test_vincenty_cpp_batch_matches_scalar_results():
    pairs = [
        (39.9042, 116.4074, 31.2304, 121.4737),
        (22.3193, 114.1694, 22.5431, 114.0579),
        (48.8566, 2.3522, 51.5074, -0.1278),
        (0.0, 179.9, 0.0, -179.9),
    ]

    batched = vincenty_ext.vincenty_distance_batch_m(pairs)
    scalar = [vincenty_ext.vincenty_distance_m(*pair) for pair in pairs]

    assert len(batched) == len(scalar)
    assert batched == scalar


def test_gcj02_to_wgs84_cpp_batch_matches_caijun():
    points = [
        (39.9042, 116.4074),
        (31.2304, 121.4737),
        (30.5728, 104.0668),
        (22.5431, 114.0579),
        (35.6895, 139.6917),
    ]

    batched = vincenty_ext.gcj02_to_wgs84_batch(points)
    expected = [gcj02_to_wgs84_caijun(lat, lon) for lat, lon in points]

    assert len(batched) == len(expected)
    for got, exp in zip(batched, expected):
        assert got[0] == pytest.approx(exp[0], abs=2e-8)
        assert got[1] == pytest.approx(exp[1], abs=2e-8)
