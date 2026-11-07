"""Send an inspection video (+ optional GPX) through the running application, labelled DÉMO.

    ml/.venv/Scripts/python.exe -X utf8 scripts/demo_video.py --video data/m1/video_sample/santiago_leg2.webm \
        --gpx data/m1/video_sample/demo_track.gpx [--offset 0] [--vehicle DEMO-INSP-01]

Everything goes through the API as `demo.inspection` (password: data/demo/demo_accounts.json, never printed):
session start, video upload (POST /media/video), video job (POST /perception/jobs, options.gpx / gps_offset_s /
demo), then the session is stopped. The M1 worker processes the job; the script waits and prints the job result.
Its only direct database write is the demo tag on the session it created (as scripts/seed_demo.py does).
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
import urllib.request
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
DEMO = {"demo": True, "demo_label": "DÉMO — données fictives"}


def call(api, path, token=None, body=None, method=None):
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{api}{path}", data=None if body is None else json.dumps(body).encode(), headers=headers,
                                 method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def upload(api, token, path: Path):
    boundary = uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or "video/webm"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode()
    body = head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{api}/media/video", data=body, method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8081/api")
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--gpx", type=Path)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--vehicle", default="DEMO-INSP-01")
    ap.add_argument("--db", default=os.getenv("DATABASE_URL", "postgresql://thniyetna:thniyetna_dev@localhost:5433/thniyetna"))
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args(argv)
    accounts = json.loads((ROOT / "data/demo/demo_accounts.json").read_text(encoding="utf-8"))
    token = call(a.api, "/auth/login", body={"username": "demo.inspection", "password": accounts["demo.inspection"]["password"]})["access_token"]

    session = call(a.api, "/perception/inspections/start", token, {"vehicle_code": a.vehicle, "mode": "video"})
    with psycopg.connect(a.db.replace("postgresql+psycopg://", "postgresql://")) as conn:
        conn.execute("UPDATE inspection_sessions SET metadata=metadata||%s::jsonb WHERE id=%s", (json.dumps(DEMO), session["id"]))
    print("session", session["id"])
    t = time.monotonic()
    media = upload(a.api, token, a.video)
    print(f"uploaded {a.video.stat().st_size / 1e6:.1f} MB in {time.monotonic() - t:.0f} s ->", media["storage_key"])
    options = {"gps_offset_s": a.offset, **DEMO}
    if a.gpx:
        options["gpx"] = a.gpx.read_text(encoding="utf-8")
    job = call(a.api, "/perception/jobs", token, {"job_type": "video", "storage_key": media["storage_key"],
                                                  "media_uri": media["media_uri"], "session_id": session["id"], "options": options})
    print("job", job["id"], job["status"])
    # ids of this run, for the headless UI check of the inspection screen (data/m1/video_sample is gitignored)
    (ROOT / "data/m1/video_sample/last_run.json").write_text(json.dumps({"session_id": session["id"], "job_id": job["id"],
        "video": a.video.name, "gpx": a.gpx.name if a.gpx else None}, indent=1), encoding="utf-8")
    call(a.api, f"/perception/inspections/{session['id']}/stop", token, body={})
    if a.no_wait:
        return
    while job["status"] in ("queued", "running"):
        time.sleep(5)
        job = call(a.api, f"/perception/jobs/{job['id']}", token)
        print(f"  {job['status']} {round((job.get('progress') or 0) * 100)} %", flush=True)
    print(json.dumps({k: job[k] for k in ("status", "error", "result")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
