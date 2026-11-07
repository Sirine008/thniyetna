"""Synthetic GPX track along a real Bizerte road (DÉMO), to test the M1 inspection-video pipeline.

    ml/.venv/Scripts/python.exe -X utf8 scripts/make_demo_gpx.py --seconds 345 --out data/m1/video_sample/demo_track.gpx

The road geometry is the OSRM route between two points (POST /routing/route on the running API, no write);
points are placed every second at a constant speed from --start (UTC). The track is synthetic: it does not
come from a vehicle and is labelled « DÉMO — données fictives » in the file.
"""
from __future__ import annotations

import argparse
import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEMO_LABEL = "DÉMO — données fictives"


def haversine_m(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    return 2 * r * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def resample(line, step_m):
    """Points every step_m metres along the polyline [[lat, lon], ...]."""
    out, carry = [line[0]], 0.0
    for a, b in zip(line, line[1:]):
        seg = haversine_m(a, b)
        pos = step_m - carry
        while pos <= seg:
            t = pos / seg
            out.append([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
            pos += step_m
        carry = (carry + seg) % step_m
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--api', default='http://localhost:8081/api')
    ap.add_argument('--from', dest='src', default='37.2744,9.8739', help='lat,lon (default: Bizerte centre)')
    ap.add_argument('--to', dest='dst', default='37.2150,10.1200', help='lat,lon (default: Ras Jebel)')
    ap.add_argument('--speed-kmh', type=float, default=40.0)
    ap.add_argument('--seconds', type=int, required=True, help='track duration (>= video duration)')
    ap.add_argument('--start', default='2026-10-24T09:00:00Z')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(argv)
    (la, lo), (lb, lob) = (map(float, a.src.split(',')), map(float, a.dst.split(',')))
    body = json.dumps({'current_lat': la, 'current_lon': lo, 'destination_lat': lb, 'destination_lon': lob, 'alternatives': 0}).encode()
    req = urllib.request.Request(f'{a.api}/routing/route', data=body, headers={'Content-Type': 'application/json'})
    route = json.load(urllib.request.urlopen(req, timeout=60))
    line = route['fastest_polyline'] or route['polyline']
    points = resample(line, a.speed_kmh / 3.6)[: a.seconds + 1]
    if len(points) <= a.seconds:
        raise SystemExit(f'route too short for {a.seconds} s at {a.speed_kmh} km/h')
    t0 = datetime.fromisoformat(a.start.replace('Z', '+00:00')).astimezone(timezone.utc)
    rows = '\n'.join(f'      <trkpt lat="{p[0]:.7f}" lon="{p[1]:.7f}"><time>{(t0 + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>'
                     for i, p in enumerate(points))
    gpx = f'''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="THNIYETNA make_demo_gpx.py" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>{DEMO_LABEL} — trace synthétique ({a.speed_kmh:g} km/h, route OSRM {a.src} → {a.dst})</name></metadata>
  <trk><name>{DEMO_LABEL}</name><trkseg>
{rows}
  </trkseg></trk>
</gpx>
'''
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(gpx, encoding='utf-8')
    dist = sum(haversine_m(p, q) for p, q in zip(points, points[1:]))
    print(f'{a.out}: {len(points)} points, {dist / 1000:.2f} km, {t0.isoformat()} → {(t0 + timedelta(seconds=len(points) - 1)).isoformat()}')


if __name__ == '__main__':
    main()
