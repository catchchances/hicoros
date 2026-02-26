import pytest

from hicoros import _vincenty as vincenty_ext
from tests.gcj_helpers import gcj02_to_wgs84_caijun
from tests.gcj_helpers import gcj02_to_wgs84_naive


DEMO_CASES = [
    ((39.9042, 116.4074), (39.90279666, 116.40115775), (39.90279625, 116.40115683)),
    ((31.2304, 121.4737), (31.23234226, 121.46917694), (31.23232924, 121.46916226)),
    ((23.1291, 113.2644), (23.13177666, 113.25907041), (23.13177798, 113.25907324)),
    ((22.5431, 114.0579), (22.54581719, 114.05278600), (22.54582650, 114.05279233)),
    ((30.5728, 104.0668), (30.57525386, 104.06429452), (30.57525661, 104.06429912)),
    ((30.2741, 120.1551), (30.27642878, 120.15040552), (30.27642035, 120.15039193)),
    ((32.0603, 118.7969), (32.06237570, 118.79171644), (32.06236859, 118.79170770)),
    ((34.3416, 108.9398), (34.34315550, 108.93514437), (34.34316208, 108.93515602)),
    ((29.5630, 106.5516), (29.56584873, 106.54788235), (29.56584011, 106.54787535)),
    ((36.0671, 120.3826), (36.06682377, 120.37746692), (36.06682851, 120.37746949)),
]


def validate_against_demo() -> dict:
    rough_ok = 0
    precise_ok = 0
    details = []

    for inp, expected_rough, expected_precise in DEMO_CASES:
        rough = gcj02_to_wgs84_naive(*inp)
        precise = vincenty_ext.gcj02_to_wgs84_batch([inp])[0]

        rough_match = (round(rough[0], 8), round(rough[1], 8)) == (
            round(expected_rough[0], 8),
            round(expected_rough[1], 8),
        )
        precise_match = abs(precise[0] - expected_precise[0]) <= 2e-8 and abs(precise[1] - expected_precise[1]) <= 2e-8
        rough_ok += int(rough_match)
        precise_ok += int(precise_match)
        details.append(
            {
                "input": inp,
                "rough_match_8dp": rough_match,
                "precise_match_8dp": precise_match,
            }
        )

    return {
        "cases": len(DEMO_CASES),
        "rough_passed": rough_ok,
        "precise_passed": precise_ok,
        "all_passed": rough_ok == len(DEMO_CASES) and precise_ok == len(DEMO_CASES),
        "details": details,
    }


@pytest.mark.parametrize("inp, expected_rough, _", DEMO_CASES)
def test_naive_matches_demo_rough_8dp(inp, expected_rough, _):
    got_lat, got_lon = gcj02_to_wgs84_naive(*inp)
    assert round(got_lat, 8) == round(expected_rough[0], 8)
    assert round(got_lon, 8) == round(expected_rough[1], 8)


@pytest.mark.parametrize("inp, _, expected_precise", DEMO_CASES)
def test_batch_single_point_matches_demo_precise_8dp(inp, _, expected_precise):
    got_lat, got_lon = vincenty_ext.gcj02_to_wgs84_batch([inp])[0]
    exp_lat, exp_lon = expected_precise
    assert got_lat == pytest.approx(exp_lat, abs=2e-8)
    assert got_lon == pytest.approx(exp_lon, abs=2e-8)


@pytest.mark.parametrize("inp, expected_rough, expected_precise", DEMO_CASES)
def test_batch_single_point_matches_caijun(inp, expected_rough, expected_precise):
    got_lat, got_lon = vincenty_ext.gcj02_to_wgs84_batch([inp])[0]
    precise_lat, precise_lon = gcj02_to_wgs84_caijun(*inp)
    assert got_lat == pytest.approx(precise_lat, abs=2e-8)
    assert got_lon == pytest.approx(precise_lon, abs=2e-8)


@pytest.mark.parametrize("inp, expected_rough, expected_precise", DEMO_CASES)
def test_naive_is_baseline_close_to_demo_rough(inp, expected_rough, expected_precise):
    naive_lat, naive_lon = gcj02_to_wgs84_naive(*inp)
    assert naive_lat == pytest.approx(expected_rough[0], abs=2e-5)
    assert naive_lon == pytest.approx(expected_rough[1], abs=2e-5)


def test_naive_outside_china_returns_input():
    inp = (35.6895, 139.6917)
    got = gcj02_to_wgs84_naive(*inp)
    assert got == inp


@pytest.mark.parametrize("inp, expected_rough, expected_precise", DEMO_CASES)
def test_caijun_matches_demo_precise(inp, expected_rough, expected_precise):
    got_lat, got_lon = gcj02_to_wgs84_caijun(*inp)
    assert got_lat == pytest.approx(expected_precise[0], abs=2e-8)
    assert got_lon == pytest.approx(expected_precise[1], abs=2e-8)


@pytest.mark.parametrize("inp, expected_rough, expected_precise", DEMO_CASES)
def test_caijun_is_closer_than_naive_to_precise(inp, expected_rough, expected_precise):
    caijun_lat, caijun_lon = gcj02_to_wgs84_caijun(*inp)
    naive_lat, naive_lon = gcj02_to_wgs84_naive(*inp)
    pr_lat, pr_lon = expected_precise

    caijun_err = abs(caijun_lat - pr_lat) + abs(caijun_lon - pr_lon)
    naive_err = abs(naive_lat - pr_lat) + abs(naive_lon - pr_lon)
    assert caijun_err <= naive_err


def test_validate_against_demo_all_passed():
    result = validate_against_demo()
    assert result["cases"] == len(DEMO_CASES)
    assert result["rough_passed"] == len(DEMO_CASES)
    assert result["precise_passed"] == len(DEMO_CASES)
    assert result["all_passed"] is True


def test_batch_multi_point_matches_demo_precise_8dp():
    points = [inp for inp, _, _ in DEMO_CASES]
    expected_precise = [exp for _, _, exp in DEMO_CASES]

    got_batch = vincenty_ext.gcj02_to_wgs84_batch(points)

    assert len(got_batch) == len(expected_precise)
    for got, exp in zip(got_batch, expected_precise):
        assert got[0] == pytest.approx(exp[0], abs=2e-8)
        assert got[1] == pytest.approx(exp[1], abs=2e-8)


def test_batch_multi_point_outside_china_returns_input():
    points = [(35.6895, 139.6917), (1.3521, 103.8198)]
    got_batch = vincenty_ext.gcj02_to_wgs84_batch(points)

    assert got_batch[0] == pytest.approx(points[0], abs=0.0)
    assert got_batch[1] != pytest.approx(points[1], abs=0.0)
