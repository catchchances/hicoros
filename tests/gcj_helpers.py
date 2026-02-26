import math


GCJ_A = 6378245.0
GCJ_EE = 0.00669342162296594323


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def _out_of_china(lat: float, lon: float) -> bool:
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _delta(lat: float, lon: float) -> tuple[float, float]:
    d_lat = _transform_lat(lon - 105.0, lat - 35.0)
    d_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - GCJ_EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((GCJ_A * (1 - GCJ_EE)) / (magic * sqrt_magic) * math.pi)
    d_lon = (d_lon * 180.0) / (GCJ_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return d_lat, d_lon


def gcj02_to_wgs84_naive(lat: float, lon: float) -> tuple[float, float]:
    if _out_of_china(lat, lon):
        return lat, lon
    d_lat, d_lon = _delta(lat, lon)
    return lat - d_lat, lon - d_lon


def _wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    if _out_of_china(lat, lon):
        return lat, lon
    d_lat, d_lon = _delta(lat, lon)
    return lat + d_lat, lon + d_lon


def gcj02_to_wgs84_caijun(lat: float, lon: float, max_iter: int = 10, eps: float = 1e-12) -> tuple[float, float]:
    if _out_of_china(lat, lon):
        return lat, lon

    wgs_lat, wgs_lon = gcj02_to_wgs84_naive(lat, lon)
    for _ in range(max_iter):
        gcj_lat, gcj_lon = _wgs84_to_gcj02(wgs_lat, wgs_lon)
        diff_lat = gcj_lat - lat
        diff_lon = gcj_lon - lon
        wgs_lat -= diff_lat
        wgs_lon -= diff_lon
        if abs(diff_lat) <= eps and abs(diff_lon) <= eps:
            break

    return wgs_lat, wgs_lon
