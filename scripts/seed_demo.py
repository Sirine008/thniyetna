"""Demo data for THNIYETNA (Bizerte governorate only), created through the real application.

    ml/.venv/Scripts/python.exe scripts/seed_demo.py            # seed (idempotent)
    ml/.venv/Scripts/python.exe scripts/seed_demo.py --reset    # list demo rows, ask, delete them only

Everything goes through the running API (accounts, vehicles, lines snapped by OSRM, assignments,
citizen reports with photos -> M1 worker, validation, status changes, M3 route checks) and the
normal M2 scoring job. The script never writes risk scores, routes or alerts itself; its only direct
database writes are the demo tag on rows it just created through the API, and the --reset deletes.

Demo rows are identifiable:
  app_users            username starts with "demo."
  vehicles, official_routes, route_assignments   metadata.demo = true
  complaints, road_events, notification_outbox    payload.demo = true
  perception_jobs      options.demo = true
  road_observations    metadata.demo = true
  complaint_status_history   belongs to a demo complaint
The API exposes `demo` and the UI shows "DÉMO — données fictives". M2 training ignores demo events
(ml/prediction/condition_model.py, TRAINING_EVENTS_SQL / drop_demo).

Passwords are generated and written to data/demo/demo_accounts.json (gitignored), never printed.
Supervisor logins use BOOTSTRAP_PASSWORD from .env (read only).
Needs: the stack with --profile m1 (perception-worker) and photos in data/m1/pilot/.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_FILE = ROOT / "data" / "demo" / "demo_accounts.json"
PHOTOS = ROOT / "data" / "m1" / "pilot"
DEMO_LABEL = "DÉMO — données fictives"
TAG = {"demo": True, "demo_label": DEMO_LABEL}
GOV_CODE = "TN-23"

# ------------------------------------------------------------------ content
PLACES = {
    "Bizerte centre": (37.2744, 9.8739),
    "Menzel Bourguiba": (37.1537, 9.7856),
    "Mateur": (37.0400, 9.6650),
    "Ras Jebel": (37.2150, 10.1200),
    "Zarzouna": (37.2540, 9.8770),
}
LINES = [  # code, start, end, bus, driver
    ("DEMO-L1", "Bizerte centre", "Menzel Bourguiba", "DEMO-BUS-01", "demo.driver1"),
    ("DEMO-L2", "Bizerte centre", "Mateur", "DEMO-BUS-02", "demo.driver2"),
    ("DEMO-L3", "Bizerte centre", "Ras Jebel", "DEMO-BUS-03", "demo.driver3"),
    ("DEMO-L4", "Bizerte centre", "Zarzouna", "DEMO-BUS-04", "demo.driver4"),
]
BUSES = [f"DEMO-BUS-0{i}" for i in range(1, 7)]
INSPECTION_VEHICLE = "DEMO-INSP-01"
DRIVERS = [f"demo.driver{i}" for i in range(1, 5)]
INSPECTOR = "demo.inspection"
CITIZENS = [f"demo.citizen{i}" for i in range(1, 6)]
DISPLAY = {**{d: f"Chauffeur démo {d[-1]}" for d in DRIVERS}, INSPECTOR: "Véhicule d'inspection démo",
           **{c: f"Citoyen démo {c[-1]}" for c in CITIZENS}}

NOTES = {
    "under_review": "Dossier pris en charge par le district de Bizerte ; vérification sur place programmée.",
    "validated": "Dégradation confirmée sur place par l'équipe d'entretien ; ajoutée au programme.",
    "planned": "Intervention planifiée : purge et réparation à l'enrobé à chaud, signalisation de chantier prévue.",
    "resolved": "Réparation réalisée et contrôlée ; chaussée remise en état.",
    "rejected": "La photo ne montre pas de dégradation de la chaussée ; signalement clos sans intervention.",
}
CHAIN = {"open": [], "under_review": ["under_review"], "validated": ["under_review", "validated"],
         "planned": ["under_review", "validated", "planned"],
         "resolved": ["under_review", "validated", "planned", "resolved"],
         "rejected": ["under_review", "rejected"]}

# key, line, target fraction along the line, photo, citizen, final status, description
COMPLAINTS = [
    ("C01", "DEMO-L1", 0.25, "road2.jpg", "demo.citizen1", "open", "Nid-de-poule rempli d'eau sur la voie de droite"),
    ("C02", "DEMO-L1", 0.40, "road3.jpg", "demo.citizen2", "validated", "Grand nid-de-poule et chaussée faïencée"),
    ("C03", "DEMO-L1", 0.70, "road6.jpg", "demo.citizen3", "planned", "Trous comblés au gravier, chaussée instable"),
    ("C04", "DEMO-L1", 0.85, "road5.jpg", "demo.citizen4", "resolved", "Deux nids-de-poule près de l'accotement"),
    ("C05", "DEMO-L2", 0.20, "road4.jpg", "demo.citizen5", "under_review", "Nid-de-poule profond après la pluie"),
    ("C06", "DEMO-L2", 0.40, "road8.jpg", "demo.citizen1", "validated", "Longue fissure sur la chaussée"),
    ("C07", "DEMO-L2", 0.65, "road7.jpg", "demo.citizen2", "open", "Série de nids-de-poule sur plusieurs mètres"),
    ("C08", "DEMO-L2", 0.80, "road13.jpg", "demo.citizen3", "rejected", "Revêtement abîmé à l'entrée"),
    ("C09", "DEMO-L3", 0.20, "road11.jpg", "demo.citizen4", "under_review", "Nid-de-poule au milieu de la voie"),
    ("C10", "DEMO-L3", 0.45, "road1.jpg", "demo.citizen5", "planned", "Chaussée fissurée en surface"),
    ("C11", "DEMO-L3", 0.70, "road9.jpg", "demo.citizen1", "under_review", "Fissure transversale signalée"),
    ("C12", "DEMO-L3", 0.90, "road12.jpg", "demo.citizen2", "rejected", "Revêtement dégradé"),
    ("C13", "DEMO-L4", 0.30, "road2.jpg", "demo.citizen3", "resolved", "Nid-de-poule avec dalles soulevées"),
    ("C14", "DEMO-L4", 0.55, "road4.jpg", "demo.citizen4", "open", "Nid-de-poule à l'approche du pont"),
    ("C15", "DEMO-L4", 0.80, "road6.jpg", "demo.citizen5", "validated", "Rebouchage provisoire déjà dégradé"),
]
# Inspection-vehicle uploads (M1 image jobs) on lines 1 and 2, so the M3 rule has hazards to avoid.
INSPECTIONS = [  # key, line, fraction, photo
    ("E01", "DEMO-L1", 0.50, "road3.jpg"),
    ("E02", "DEMO-L1", 0.60, "road8.jpg"),
    ("E03", "DEMO-L2", 0.50, "road3.jpg"),
    ("E04", "DEMO-L2", 0.58, "road1.jpg"),
]
# events validated by equipment.supervisor (about half), by the item that produced them
VALIDATE = {"C02", "C06", "E01", "E03"}

PLACEMENT_SPACING_M = 300   # between two demo points of a line
END_MARGIN_M = 400          # keep away from the line ends (town centres)
NON_DEMO_CLEARANCE_M = 150  # never near a real event/report: the worker would merge observations


# ------------------------------------------------------------------ plumbing
def read_env() -> dict:
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = read_env()


def db_url() -> str:
    url = os.getenv("DATABASE_URL") or (
        f"postgresql://{ENV.get('POSTGRES_USER', 'thniyetna')}:{ENV.get('POSTGRES_PASSWORD', 'thniyetna_dev')}"
        f"@localhost:{ENV.get('POSTGRES_PORT', '5432')}/{ENV.get('POSTGRES_DB', 'thniyetna')}")
    return url.replace("postgresql+psycopg://", "postgresql://")


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.tokens: dict[str, str] = {}

    def call(self, method, path, token=None, body=None, raw=None, ctype=None, ok=(200, 201)):
        headers, data = {}, None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        if raw is not None:
            data, headers["Content-Type"] = raw, ctype
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in ok:
                return e.code, detail
            return e.code, detail

    def login(self, username: str, password: str) -> str | None:
        st, res = self.call("POST", "/auth/login", body={"username": username, "password": password})
        if st != 200:
            return None
        self.tokens[username] = res["access_token"]
        return res["access_token"]

    def upload(self, token: str, photo: Path) -> dict:
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{photo.name}\"\r\n"
                f"Content-Type: image/jpeg\r\n\r\n").encode() + photo.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        st, res = self.call("POST", "/media/image", token, raw=body, ctype=f"multipart/form-data; boundary={boundary}")
        if st != 200:
            raise SystemExit(f"upload {photo.name} failed: {st} {res}")
        return res


def tag_sql(table: str, column: str) -> str:
    return f"UPDATE {table} SET {column} = {column} || %s::jsonb WHERE id = ANY(%s::uuid[])"


def say(msg: str):
    print(msg, flush=True)


# ------------------------------------------------------------------ demo row identification
def demo_ids(cx) -> dict[str, list]:
    one = lambda q, *a: [r[0] for r in cx.execute(q, a).fetchall()]
    ids = {
        "app_users": one("SELECT username FROM app_users WHERE username LIKE 'demo.%%'"),
        "vehicles": one("SELECT id::text FROM vehicles WHERE coalesce((metadata->>'demo')::boolean,false)"),
        "official_routes": one("SELECT id::text FROM official_routes WHERE coalesce((metadata->>'demo')::boolean,false)"),
        "complaints": one("""SELECT id::text FROM complaints
                             WHERE coalesce((payload->>'demo')::boolean,false) OR actor_ref LIKE 'demo.%%'"""),
        "perception_jobs": one("""SELECT id::text FROM perception_jobs
                                  WHERE coalesce((options->>'demo')::boolean,false) OR created_by LIKE 'demo.%%'"""),
    }
    ids["route_assignments"] = one("""SELECT id::text FROM route_assignments
        WHERE coalesce((metadata->>'demo')::boolean,false) OR driver_username LIKE 'demo.%%'
           OR route_id = ANY(%s::uuid[]) OR vehicle_id = ANY(%s::uuid[])""", ids["official_routes"], ids["vehicles"])
    ids["road_events"] = one("""SELECT id::text FROM road_events
        WHERE coalesce((payload->>'demo')::boolean,false) OR payload->>'job_id' = ANY(%s)""", ids["perception_jobs"])
    ids["road_observations"] = one("""SELECT id::text FROM road_observations
        WHERE coalesce((metadata->>'demo')::boolean,false) OR metadata->>'job_id' = ANY(%s)""", ids["perception_jobs"])
    ids["complaint_status_history"] = one("SELECT id::text FROM complaint_status_history WHERE complaint_id = ANY(%s::uuid[])",
                                          ids["complaints"])
    ids["inspection_sessions"] = one("SELECT id::text FROM inspection_sessions WHERE vehicle_id = ANY(%s::uuid[])",
                                     ids["vehicles"])
    ids["notification_outbox"] = one("""SELECT id::text FROM notification_outbox o
        WHERE coalesce((o.payload->>'demo')::boolean,false) OR o.recipient_ref LIKE 'demo.%%'
           OR o.payload->>'username' LIKE 'demo.%%' OR o.payload->>'driver_username' LIKE 'demo.%%'
           OR o.payload->>'route_code' LIKE 'DEMO-%%' OR o.payload->>'vehicle_code' LIKE 'DEMO-%%'
           OR o.payload->>'job_id' = ANY(%s) OR o.payload->>'complaint_id' = ANY(%s)
           OR (o.topic = 'complaint.created' AND o.payload->>'id' = ANY(%s))
           OR (o.topic IN ('road.event.created','road.event.validated') AND o.payload->>'id' = ANY(%s))""",
                                     ids["perception_jobs"], ids["complaints"], ids["complaints"], ids["road_events"])
    return ids


def tag_outbox(cx):
    ids = demo_ids(cx)["notification_outbox"]
    cx.execute(tag_sql("notification_outbox", "payload"), (json.dumps(TAG), ids))


# ------------------------------------------------------------------ seed steps
class Seeder:
    def __init__(self, api: Api, cx, args):
        self.api, self.cx, self.args = api, cx, args
        self.changed = False
        self.created: dict[str, int] = {}
        self.accounts = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8")) if ACCOUNTS_FILE.exists() else {}

    def count(self, table, n=1):
        self.created[table] = self.created.get(table, 0) + n
        self.changed = True

    def q(self, sql, *a):
        return self.cx.execute(sql, a).fetchall()

    def q1(self, sql, *a):
        row = self.cx.execute(sql, a).fetchone()
        return row[0] if row else None

    # -- preflight
    def preflight(self):
        st, res = self.api.call("GET", "/health")
        if st != 200:
            raise SystemExit(f"API not reachable at {self.api.base}: {st} {res}")
        missing = sorted({c[3] for c in COMPLAINTS} | {e[3] for e in INSPECTIONS})
        missing = [p for p in missing if not (PHOTOS / p).exists()]
        if missing:
            raise SystemExit(f"Missing pilot photos in {PHOTOS}: {missing}")
        clash = self.q("""SELECT 'vehicle '||vehicle_code FROM vehicles
                          WHERE vehicle_code LIKE 'DEMO-%%' AND NOT coalesce((metadata->>'demo')::boolean,false)
                          UNION ALL SELECT 'route '||route_code FROM official_routes
                          WHERE route_code LIKE 'DEMO-%%' AND NOT coalesce((metadata->>'demo')::boolean,false)""")
        if clash:
            raise SystemExit(f"Non-demo rows use demo codes, refusing to touch them: {clash}")
        boot = ENV.get("BOOTSTRAP_PASSWORD") or os.getenv("BOOTSTRAP_PASSWORD")
        for sup in ("equipment.supervisor", "transport.supervisor"):
            if not boot or not self.api.login(sup, boot):
                raise SystemExit(f"Cannot log in as {sup} with BOOTSTRAP_PASSWORD from .env")

    # -- accounts
    def save_accounts(self):
        ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACCOUNTS_FILE.write_text(json.dumps(self.accounts, indent=2, ensure_ascii=False), encoding="utf-8")

    def ensure_account(self, username, role):
        entry = self.accounts.get(username) or {"password": secrets.token_urlsafe(12), "role": role,
                                                 "display_name": DISPLAY[username]}
        self.accounts[username] = entry
        self.save_accounts()
        exists = self.q1("SELECT 1 FROM app_users WHERE username=%s", username)
        if exists and self.api.login(username, entry["password"]):
            return
        if exists and role == "citizen":
            raise SystemExit(f"{username} exists but its password is not in {ACCOUNTS_FILE}; run --reset first")
        if role == "citizen":
            st, res = self.api.call("POST", "/auth/register", body={
                "username": username, "password": entry["password"], "display_name": entry["display_name"]})
        else:
            sup = "transport.supervisor" if role == "bus_driver" else "equipment.supervisor"
            if exists:  # file lost or edited: reset through the supervisor API
                st, res = self.api.call("POST", f"/auth/staff/{username}/password", self.api.tokens[sup],
                                        body={"password": entry["password"]})
            else:
                st, res = self.api.call("POST", "/auth/staff", self.api.tokens[sup], body={
                    "username": username, "password": entry["password"], "display_name": entry["display_name"],
                    "role": role})
        if st not in (200, 201):
            raise SystemExit(f"account {username}: {st} {res}")
        if not exists:
            self.count("app_users")
        if not self.api.login(username, entry["password"]):
            raise SystemExit(f"cannot log in as {username}")

    def accounts_step(self):
        for d in DRIVERS:
            self.ensure_account(d, "bus_driver")
        self.ensure_account(INSPECTOR, "inspection_vehicle")
        for c in CITIZENS:
            self.ensure_account(c, "citizen")
        say(f"accounts: {len(DRIVERS)} drivers, 1 inspection vehicle, {len(CITIZENS)} citizens "
            f"(passwords in {ACCOUNTS_FILE.relative_to(ROOT)})")

    # -- fleet
    def ensure_vehicle(self, code, vtype, org, label, sup):
        if self.q1("SELECT 1 FROM vehicles WHERE vehicle_code=%s", code):
            return
        st, res = self.api.call("POST", "/platform/vehicles", self.api.tokens[sup], body={
            "vehicle_code": code, "vehicle_type": vtype, "owner_org": org, "label": label})
        if st not in (200, 201):
            raise SystemExit(f"vehicle {code}: {st} {res}")
        self.cx.execute("UPDATE vehicles SET metadata = metadata || %s::jsonb WHERE vehicle_code=%s",
                        (json.dumps(TAG), code))
        self.count("vehicles")

    def fleet_step(self):
        for i, code in enumerate(BUSES, 1):
            self.ensure_vehicle(code, "bus", "SRTB", f"DÉMO — Bus {i:02d}", "transport.supervisor")
        self.ensure_vehicle(INSPECTION_VEHICLE, "inspection", "Ministère de l'Équipement",
                            "DÉMO — Véhicule d'inspection", "equipment.supervisor")
        say(f"fleet: {len(BUSES)} buses + 1 inspection vehicle")

    # -- lines
    def line_geometry(self, start, end):
        a, b = PLACES[start], PLACES[end]
        st, res = self.api.call("POST", "/routing/route", body={
            "current_lat": a[0], "current_lon": a[1], "destination_lat": b[0], "destination_lon": b[1],
            "alternatives": 0})
        if st != 200:
            raise SystemExit(f"routing {start} -> {end}: {st} {res}")
        line = res["fastest_polyline"]  # OSRM fastest, already snapped to the road network
        return line, res["fastest_distance_m"]

    def check_line(self, code, line):
        wkt = "LINESTRING(" + ",".join(f"{lon} {lat}" for lat, lon in line) + ")"
        ends = []
        for lat, lon in (line[0], line[-1]):
            inside = self.q1("""SELECT ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s,%s),4326)) FROM admin_areas
                                WHERE code=%s""", lon, lat, GOV_CODE)
            seg = self.q("""SELECT segment_code, round(ST_Distance(geom::geography,
                                   ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography))
                            FROM road_segments ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s,%s),4326) LIMIT 1""",
                         lon, lat, lon, lat)[0]
            ends.append((inside, seg))
        covered = self.q1("""WITH z AS (SELECT ST_Buffer(ST_SetSRID(ST_GeomFromText(%s),4326)::geography,15)::geometry z)
            SELECT coalesce(sum(ST_Length(ST_Intersection(s.geom,z.z)::geography)),0) FROM road_segments s, z
            WHERE ST_Intersects(s.geom,z.z)""", wkt)
        if not all(e[0] for e in ends):
            raise SystemExit(f"{code}: an endpoint is outside {GOV_CODE}: {ends}")
        if covered < 1000:
            raise SystemExit(f"{code}: follows only {covered:.0f} m of road segments")
        return ends, covered

    def lines_step(self):
        say("lines (OSRM via /routing/route):")
        for code, start, end, _, _ in LINES:
            name = f"DÉMO — {code[-2:]} {start} → {end}"
            existing = self.q1("SELECT ST_Length(geom::geography) FROM official_routes WHERE route_code=%s", code)
            if existing:
                say(f"  {code} exists ({existing / 1000:.1f} km), kept")
                continue
            line, dist = self.line_geometry(start, end)
            ends, covered = self.check_line(code, line)
            say(f"  {code} {start} → {end}: {dist / 1000:.1f} km, {len(line)} points, in {GOV_CODE}, "
                f"ends {ends[0][1][1]:.0f} m / {ends[1][1][1]:.0f} m from segments, segments followed {covered / 1000:.1f} km")
            st, res = self.api.call("POST", "/routing/official-routes", self.api.tokens["transport.supervisor"], body={
                "route_code": code, "name": name, "coordinates": line, "owner_org": "SRTB"})
            if st not in (200, 201):
                raise SystemExit(f"line {code}: {st} {res}")
            self.cx.execute("UPDATE official_routes SET metadata = metadata || %s::jsonb WHERE route_code=%s",
                            (json.dumps({**TAG, "start": start, "end": end}), code))
            self.count("official_routes")

    def assignments_step(self):
        for code, _, _, bus, driver in LINES:
            if self.q1("""SELECT 1 FROM route_assignments ra JOIN official_routes r ON r.id=ra.route_id
                          JOIN vehicles v ON v.id=ra.vehicle_id
                          WHERE r.route_code=%s AND v.vehicle_code=%s AND ra.driver_username=%s AND ra.active""",
                       code, bus, driver):
                continue
            st, res = self.api.call("POST", "/routing/assignments", self.api.tokens["transport.supervisor"], body={
                "route_code": code, "vehicle_code": bus, "driver_username": driver})
            if st not in (200, 201):
                raise SystemExit(f"assignment {code}: {st} {res}")
            self.cx.execute(tag_sql("route_assignments", "metadata"), (json.dumps(TAG), [res["id"]]))
            self.count("route_assignments")
        say("assignments: " + ", ".join(f"{c}→{b}→{d}" for c, _, _, b, d in LINES))

    # -- placement on real segments along a line
    def candidates(self, code):
        rows = self.q("""
          WITH r AS (SELECT ST_LineMerge(geom) g, ST_Length(geom::geography) len FROM official_routes WHERE route_code=%s),
          pts AS (SELECT (ST_DumpPoints(ST_LineInterpolatePoints(r.g, LEAST(1.0, 25.0 / r.len)))).geom p, r.len FROM r)
          SELECT ST_Y(p), ST_X(p), ST_LineLocatePoint((SELECT g FROM r), p) frac, len, s.segment_code, s.d
          FROM pts CROSS JOIN LATERAL (
            SELECT segment_code, ST_Distance(geom::geography, p::geography) d FROM road_segments
            WHERE road_class IN ('motorway','trunk','primary','secondary') ORDER BY geom <-> p LIMIT 1) s
          WHERE s.d <= 12
            AND NOT EXISTS (SELECT 1 FROM road_events e
                            WHERE NOT coalesce((e.payload->>'demo')::boolean,false)
                              AND ST_DWithin(e.geom::geography, p::geography, %s))
            AND NOT EXISTS (SELECT 1 FROM complaints c
                            WHERE NOT coalesce((c.payload->>'demo')::boolean,false) AND c.actor_ref NOT LIKE 'demo.%%'
                              AND ST_DWithin(c.geom::geography, p::geography, %s))
          ORDER BY frac""", code, NON_DEMO_CLEARANCE_M, NON_DEMO_CLEARANCE_M)
        return [r for r in rows if END_MARGIN_M <= r[2] * r[3] <= r[3] - END_MARGIN_M]

    def place(self, items):
        """items: (key, line, fraction). Nearest candidate to the target fraction, spaced along the line."""
        placed, by_line = {}, {}
        for key, line, frac in items:
            cands = by_line.setdefault(line, self.candidates(line))
            used = [p for k, p in placed.items() if p[4] == line]
            ok = [c for c in cands if all(abs(c[2] - u[2]) * c[3] >= PLACEMENT_SPACING_M for u in used)]
            if not ok:
                raise SystemExit(f"no free point on {line} for {key}")
            best = min(ok, key=lambda c: abs(c[2] - frac))
            placed[key] = (best[0], best[1], best[2], best[5], line, best[4])
        return placed

    def existing_points(self):
        """demo_key -> (lat, lon) of items already created (keeps re-runs stable)."""
        out = {}
        for key, lat, lon in self.q("""SELECT payload->>'demo_key', ST_Y(geom), ST_X(geom) FROM complaints
                                       WHERE payload->>'demo_key' IS NOT NULL"""):
            out[key] = (lat, lon)
        for key, lat, lon in self.q("""SELECT options->>'demo_key', (options->>'latitude')::float,
                                              (options->>'longitude')::float FROM perception_jobs
                                       WHERE options->>'demo_key' IS NOT NULL"""):
            out[key] = (lat, lon)
        return out

    # -- reports + M1
    def complaints_step(self, placed):
        jobs = []
        for key, line, _, photo, citizen, _, descr in COMPLAINTS:
            if self.q1("SELECT 1 FROM complaints WHERE payload->>'demo_key'=%s", key):
                continue
            lat, lon = placed[key][:2]
            token = self.api.tokens[citizen]
            media = self.api.upload(token, PHOTOS / photo)
            st, c = self.api.call("POST", "/platform/complaints", token, body={
                "description": descr, "latitude": lat, "longitude": lon, "category": "road_damage",
                "image_url": media["media_uri"], "image_storage_key": media["storage_key"]})
            if st != 200:
                raise SystemExit(f"complaint {key}: {st} {c}")
            self.cx.execute(tag_sql("complaints", "payload"),
                            (json.dumps({**TAG, "demo_key": key, "demo_line": line, "demo_photo": photo}), [c["id"]]))
            job = self.q1("SELECT id::text FROM perception_jobs WHERE options->>'complaint_id'=%s", c["id"])
            if job:
                self.cx.execute(tag_sql("perception_jobs", "options"),
                                (json.dumps({**TAG, "demo_key": key, "demo_line": line}), [job]))
                jobs.append(job)
            self.count("complaints")
            self.count("perception_jobs", 1 if job else 0)
        say(f"citizen reports: {len(COMPLAINTS)} defined, {self.created.get('complaints', 0)} created this run")
        return jobs

    def inspections_step(self, placed):
        token = self.api.tokens[INSPECTOR]
        jobs = []
        for key, line, _, photo in INSPECTIONS:
            if self.q1("SELECT 1 FROM perception_jobs WHERE options->>'demo_key'=%s", key):
                continue
            lat, lon = placed[key][:2]
            media = self.api.upload(token, PHOTOS / photo)
            st, job = self.api.call("POST", "/perception/jobs", token, body={
                "job_type": "image", "storage_key": media["storage_key"], "media_uri": media["media_uri"],
                "latitude": lat, "longitude": lon,
                "options": {**TAG, "demo_key": key, "demo_line": line, "demo_photo": photo}})
            if st != 200:
                raise SystemExit(f"inspection job {key}: {st} {job}")
            jobs.append(job["id"])
            self.count("perception_jobs")
        say(f"inspection uploads: {len(INSPECTIONS)} defined, {len(jobs)} submitted this run")
        return jobs

    def wait_jobs(self, jobs, timeout_s=300):
        if not jobs:
            return
        say(f"waiting for the M1 worker ({len(jobs)} jobs)…")
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            left = self.q1("SELECT count(*) FROM perception_jobs WHERE id = ANY(%s::uuid[]) AND status IN ('queued','running')", jobs)
            if not left:
                break
            time.sleep(2)
        else:
            raise SystemExit("M1 jobs still queued: is perception-worker running (--profile m1)?")
        for jid, key, status, result, error in self.q("""
              SELECT id::text, options->>'demo_key', status, result::text, error FROM perception_jobs
              WHERE id = ANY(%s::uuid[]) ORDER BY options->>'demo_key'""", jobs):
            say(f"  {key}: {status} {result if status == 'completed' else (error or '')[:120]}")

    def tag_m1_outputs(self):
        jobs = self.q("SELECT id::text, options->>'demo_key' FROM perception_jobs WHERE coalesce((options->>'demo')::boolean,false)")
        for jid, key in jobs:
            self.cx.execute("""UPDATE road_events SET payload = payload || %s::jsonb
                               WHERE payload->>'job_id' = %s AND NOT coalesce((payload->>'demo')::boolean,false)""",
                            (json.dumps({**TAG, "demo_key": key}), jid))
            self.cx.execute("""UPDATE road_observations SET metadata = metadata || %s::jsonb
                               WHERE metadata->>'job_id' = %s AND NOT coalesce((metadata->>'demo')::boolean,false)""",
                            (json.dumps({**TAG, "demo_key": key}), jid))

    def statuses_step(self):
        token = self.api.tokens["equipment.supervisor"]
        changes = 0
        for key, *_rest in COMPLAINTS:
            final = _rest[4]
            cid, current = self.q("SELECT id::text, status FROM complaints WHERE payload->>'demo_key'=%s", key)[0]
            chain = CHAIN[final]
            todo = chain[chain.index(current) + 1:] if current in chain else ([] if current == final else chain)
            for status in todo:
                st, res = self.api.call("PATCH", f"/platform/complaints/{cid}/status", token,
                                        body={"status": status, "note": NOTES[status]})
                if st != 200:
                    raise SystemExit(f"status {key} -> {status}: {st} {res}")
                changes += 1
        if changes:
            self.count("complaint_status_history", changes)
        say(f"report statuses: {changes} transitions this run")

    def validate_step(self):
        token = self.api.tokens["equipment.supervisor"]
        done = 0
        for eid, key, status in self.q("""SELECT id::text, payload->>'demo_key', status FROM road_events
                                          WHERE coalesce((payload->>'demo')::boolean,false)"""):
            if key in VALIDATE and status != "validated":
                st, res = self.api.call("PATCH", f"/perception/events/{eid}/validate", token)
                if st != 200:
                    raise SystemExit(f"validate {key}: {st} {res}")
                done += 1
                self.changed = True
        say(f"event validations: {done} this run")

    # -- M2 + M3
    def score(self):
        say("M2 scoring pass (python -m prediction.jobs.score --source db --once)…")
        env = {**os.environ, "DATABASE_URL": db_url().replace("postgresql://", "postgresql+psycopg://")}
        out = subprocess.run([sys.executable, "-m", "prediction.jobs.score", "--source", "db", "--once"],
                             cwd=ROOT / "ml", env=env, capture_output=True, text=True)
        if out.returncode != 0:
            raise SystemExit(f"scoring failed:\n{out.stderr[-2000:]}")
        say("  " + out.stdout.strip().splitlines()[-1])

    def route_checks(self):
        say("M3 route checks (POST /routing/driver/next-best as each driver):")
        for code, start, end, bus, driver in LINES:
            had = self.q1("""SELECT count(*) FROM notification_outbox
                             WHERE topic='driver.reroute.alert' AND recipient_ref=%s""", driver)
            if had and not self.args.recheck:
                say(f"  {code}: {driver} already has {had} alert(s), skipped (--recheck to run again)")
                continue
            a, b = PLACES[start], PLACES[end]
            st, res = self.api.call("POST", "/routing/driver/next-best", self.api.tokens[driver], body={
                "vehicle_id": bus, "current_lat": a[0], "current_lon": a[1],
                "destination_lat": b[0], "destination_lon": b[1], "alternatives": 3})
            if st != 200:
                raise SystemExit(f"route check {code}: {st} {res}")
            say(f"  {code}: {res['status']} (initial risk {res['fastest_risk']:.2f}, best {res['risk']:.2f}) — {res['reason']}")
            if res["reroute_needed"]:
                self.count("notification_outbox (driver.reroute.alert)")

    def run(self):
        self.preflight()
        self.accounts_step()
        self.fleet_step()
        self.lines_step()
        self.assignments_step()
        self.cx.commit()
        known = self.existing_points()
        todo = [(k, line, frac) for k, line, frac, *_ in COMPLAINTS + INSPECTIONS if k not in known]
        placed = self.place(todo) if todo else {}
        jobs = self.complaints_step(placed) + self.inspections_step(placed)
        self.cx.commit()
        self.wait_jobs(jobs)
        self.tag_m1_outputs()
        self.statuses_step()
        self.validate_step()
        self.cx.commit()
        if self.changed or self.args.rescore:
            self.score()
        else:
            say("nothing changed: M2 scoring skipped (--rescore to force)")
        self.route_checks()
        tag_outbox(self.cx)
        self.cx.commit()
        summary(self.cx, self.created)


# ------------------------------------------------------------------ summary + reset
def summary(cx, created: dict | None = None):
    ids = demo_ids(cx)
    say("\n=== Summary (from the database) ===")
    if created is not None:
        say("created this run: " + (", ".join(f"{k} {v}" for k, v in created.items()) or "nothing (already seeded)"))
    say("demo rows now in the database:")
    for table, rows in ids.items():
        say(f"  {table:26s} {len(rows)}")
    latest = """WITH latest AS (SELECT DISTINCT ON (segment_id) * FROM risk_scores
                                WHERE risk_level IS NOT NULL ORDER BY segment_id, created_at DESC)"""
    say("segments per risk level: " + ", ".join(f"{l} {n}" for l, n in cx.execute(
        latest + " SELECT risk_level, count(*) FROM latest GROUP BY 1 ORDER BY 1").fetchall()))
    say("segments per priority:   " + ", ".join(f"{p} {n}" for p, n in cx.execute(
        latest + " SELECT maintenance_priority, count(*) FROM latest GROUP BY 1 ORDER BY 1").fetchall()))
    for seg, lvl, prio, cond, score in cx.execute(latest + """
            SELECT s.segment_code, l.risk_level, l.maintenance_priority, l.predicted_condition, round(l.risk_score::numeric,4)
            FROM latest l JOIN road_segments s ON s.id=l.segment_id
            WHERE l.segment_id IN (SELECT segment_id FROM road_events WHERE coalesce((payload->>'demo')::boolean,false))
            ORDER BY l.risk_score DESC""").fetchall():
        say(f"  segment with demo event {seg}: {lvl} / {prio} / {cond} ({score})")
    alerts = cx.execute("""SELECT r.route_code, o.recipient_ref, o.payload->>'reason', round((o.payload->>'risk')::numeric,2), o.created_at
        FROM notification_outbox o
        LEFT JOIN route_assignments ra ON ra.driver_username=o.recipient_ref AND ra.active
        LEFT JOIN official_routes r ON r.id=ra.route_id
        WHERE o.topic='driver.reroute.alert' AND o.recipient_ref LIKE 'demo.%%' ORDER BY r.route_code""").fetchall()
    say(f"M3 reroute alerts for demo drivers: {len(alerts)}")
    for code, driver, reason, risk, at in alerts:
        say(f"  {code} ({driver}): initial risk {risk} — {reason}")
    say("logins (passwords: data/demo/demo_accounts.json; supervisors: BOOTSTRAP_PASSWORD in .env):")
    say("  citizen: " + ", ".join(CITIZENS))
    say("  bus_driver: " + ", ".join(f"{d} ({c})" for c, _, _, _, d in LINES))
    say(f"  inspection_vehicle: {INSPECTOR}")
    say("  equipment_supervisor: equipment.supervisor · transport_supervisor: transport.supervisor")


def reset(cx, args):
    ids = demo_ids(cx)
    shared = cx.execute("""SELECT count(*) FROM road_observations
        WHERE event_id = ANY(%s::uuid[]) AND NOT (id = ANY(%s::uuid[]))""",
                        (ids["road_events"], ids["road_observations"])).fetchone()[0]
    if shared:
        raise SystemExit(f"{shared} non-demo observation(s) are linked to demo events; refusing to delete "
                         "(they would be modified). Inspect them first.")
    media = sorted({r[0] for r in cx.execute("""
        SELECT storage_key FROM perception_jobs WHERE id = ANY(%s::uuid[])
        UNION SELECT payload->>'image_storage_key' FROM complaints WHERE id = ANY(%s::uuid[])""",
        (ids["perception_jobs"], ids["complaints"])).fetchall() if r[0]})
    say("Demo rows that --reset will delete (nothing else is touched):")
    for table, rows in ids.items():
        sample = ", ".join(map(str, rows[:4])) + (" …" if len(rows) > 4 else "")
        say(f"  {table:26s} {len(rows):4d}  {sample}")
    say(f"  media files                {len(media):4d}  (in the api media volume)")
    say("Then one normal M2 scoring pass, so the latest risk scores no longer include demo events.\n"
        "risk_scores / governorate forecasts / M2 history rows are never deleted.")
    if not any(ids.values()):
        say("No demo rows found.")
        return
    if not args.yes and input("Type 'yes' to delete these demo rows: ").strip().lower() != "yes":
        say("Cancelled, nothing deleted.")
        return
    order = [("notification_outbox", "id", "uuid"), ("complaint_status_history", "id", "uuid"),
             ("road_observations", "id", "uuid"), ("road_events", "id", "uuid"),
             ("perception_jobs", "id", "uuid"), ("complaints", "id", "uuid"),
             ("route_assignments", "id", "uuid"), ("official_routes", "id", "uuid"),
             ("inspection_sessions", "id", "uuid"), ("vehicles", "id", "uuid"), ("app_users", "username", "text")]
    with cx.transaction():  # all or nothing
        for table, col, typ in order:
            n = cx.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s::{typ}[])", (ids[table],)).rowcount
            say(f"  deleted {table}: {n}")
    removed = 0
    for key in media:
        if key.startswith(("images/", "videos/")) and ".." not in key:
            r = subprocess.run(["docker", "exec", "thniyetna-api", "rm", "-f", f"/data/media/{key}"],
                               capture_output=True, text=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
            removed += r.returncode == 0
    say(f"  media files removed: {removed}/{len(media)}")
    if ACCOUNTS_FILE.exists():
        ACCOUNTS_FILE.unlink()
        say(f"  removed {ACCOUNTS_FILE.relative_to(ROOT)}")
    if not args.no_score:
        Seeder(Api(args.api), cx, args).score()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="delete demo rows only (asks for confirmation)")
    ap.add_argument("--yes", action="store_true", help="with --reset: do not ask")
    ap.add_argument("--no-score", action="store_true", help="with --reset: skip the M2 scoring pass")
    ap.add_argument("--rescore", action="store_true", help="run the M2 pass even if nothing changed")
    ap.add_argument("--recheck", action="store_true", help="run the M3 route checks even if alerts exist")
    ap.add_argument("--summary", action="store_true", help="print the database summary only")
    ap.add_argument("--api", default=f"http://localhost:{ENV.get('API_PORT', '8000')}")
    args = ap.parse_args()
    # autocommit: each demo tag is committed at once, so the API never waits on a lock held here
    with psycopg.connect(db_url(), autocommit=True) as cx:
        if args.reset:
            reset(cx, args)
        elif args.summary:
            summary(cx)
        else:
            Seeder(Api(args.api), cx, args).run()


if __name__ == "__main__":
    main()
