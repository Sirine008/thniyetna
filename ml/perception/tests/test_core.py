from datetime import datetime, timedelta, timezone

from perception.gps import GpsSample, interpolate
from perception.severity import severity_proxy


def test_gps_interpolation_midpoint():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        GpsSample(t0, 37.0, 9.0),
        GpsSample(t0 + timedelta(seconds=10), 38.0, 10.0),
    ]
    lat, lon = interpolate(samples, t0 + timedelta(seconds=5))
    assert round(lat, 6) == 37.5
    assert round(lon, 6) == 9.5


def test_severity_proxy_is_bounded_and_size_sensitive():
    small = severity_proxy("pothole", 0.005, 0.9)
    large = severity_proxy("pothole", 0.15, 0.9)
    assert 0 <= small <= 1
    assert 0 <= large <= 1
    assert large > small
