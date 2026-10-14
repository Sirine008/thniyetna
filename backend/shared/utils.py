from math import radians, sin, cos, sqrt, atan2


def haversine_m(a_lat, a_lon, b_lat, b_lon):
    r = 6371000.0
    p1, p2 = radians(a_lat), radians(b_lat)
    dp, dl = radians(b_lat-a_lat), radians(b_lon-a_lon)
    x = sin(dp/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    return 2*r*atan2(sqrt(x), sqrt(1-x))


def category(score: float) -> str:
    return "high" if score >= 0.70 else "medium" if score >= 0.40 else "low"
