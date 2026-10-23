"""M3 routing: OSRM candidates + risk-aware next-best selection."""
import os, json, math, urllib.parse, urllib.request
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from .schemas import RouteRequest, RouteResponse, RouteCandidate
from .schemas import RouteCreate, AssignmentCreate
from shared.db import get_db
from shared.auth import require_role
from shared.realtime import publish
from shared.utils import haversine_m

router=APIRouter(); OSRM_URL=os.getenv("OSRM_URL","http://osrm:5000").rstrip("/")

def _fetch_osrm(coords, alternatives=0):
    coord_string=";".join(f"{lon},{lat}" for lat,lon in coords)
    q=urllib.parse.urlencode({"overview":"full","geometries":"geojson","alternatives":str(max(0,min(alternatives,3))) if alternatives else "false","steps":"false"})
    try:
        with urllib.request.urlopen(f"{OSRM_URL}/route/v1/driving/{coord_string}?{q}",timeout=8) as r: body=json.load(r)
    except Exception as e: raise HTTPException(503,f"OSRM unavailable: {e}")
    if body.get("code")!="Ok": raise HTTPException(502,f"OSRM error: {body.get('message',body.get('code'))}")
    return body.get("routes",[])

def _osrm(req:RouteRequest):
    return _fetch_osrm([(req.current_lat,req.current_lon),(req.destination_lat,req.destination_lon)], req.alternatives)

def _risk_points(db):
    return db.execute(text("""
      SELECT lat,lon,risk,event_type FROM (
        SELECT ST_Y(e.geom) lat,ST_X(e.geom) lon,GREATEST(coalesce(rs.risk_score,0),coalesce(e.severity,0.3)) risk,e.event_type,e.observed_at ts
        FROM road_events e LEFT JOIN LATERAL (SELECT risk_score FROM risk_scores r WHERE r.segment_id=e.segment_id AND (r.valid_until IS NULL OR r.valid_until>now()) ORDER BY (r.risk_level IS NOT NULL) DESC, created_at DESC LIMIT 1) rs ON true
        WHERE e.status<>'closed'
        UNION ALL
        SELECT ST_Y(c.geom),ST_X(c.geom),CASE WHEN c.status IN ('validated','planned') THEN 0.72 ELSE 0.55 END,'citizen_report',c.created_at
        FROM complaints c WHERE c.status NOT IN ('resolved','rejected') AND coalesce(c.payload->>'category','road_damage')='road_damage'
      ) h ORDER BY ts DESC LIMIT 200
    """)).mappings().all()

def _line(route): return [[lat,lon] for lon,lat in route["geometry"]["coordinates"]]

# M2 segment risk along a candidate geometry.
# Point hazards above only cover places with an M1 event or a citizen complaint.
# M2 also scores segments with no event at all (accident history x road class x
# exposure), so every candidate is matched against the latest valid M2 score of
# the road segments it actually follows.
SEGMENT_BUFFER_M=15      # route geometry vs segment geometry tolerance
SEGMENT_MIN_OVERLAP_M=60 # a crossing street only touches ~2x buffer, so it is ignored
_SEGMENT_RISK_SQL=text("""
  WITH route AS (SELECT ST_SetSRID(ST_GeomFromText(:wkt),4326) g),
  zone AS (SELECT g, ST_Buffer(g::geography,:buf)::geometry z FROM route),
  near AS (
    SELECT s.id, ST_Length(s.geom::geography) seg_m,
           ST_Length(ST_Intersection(s.geom,zone.z)::geography) overlap_m
    FROM road_segments s, zone
    WHERE s.geom && zone.z AND ST_Intersects(s.geom,zone.z)
  )
  SELECT n.overlap_m, rs.risk_score
  FROM near n
  JOIN LATERAL (
    SELECT risk_score FROM risk_scores r
    WHERE r.segment_id=n.id AND (r.valid_until IS NULL OR r.valid_until>now())
    -- prefer an M2 model score (risk_level set) over a contextual-v1 fallback row
    ORDER BY (r.risk_level IS NOT NULL) DESC, r.created_at DESC LIMIT 1
  ) rs ON true
  WHERE n.overlap_m >= LEAST(:min_overlap, 0.5*n.seg_m) AND n.overlap_m > 0
""")

def _segment_risk(db,line):
    """Return (risk, scored_segment_count) for the M2 segments a candidate follows.

    risk blends the worst segment (a single dangerous stretch matters) with the
    overlap-length-weighted mean (long exposure matters), like the hazard blend.
    """
    if db is None or len(line)<2:return 0.0,0
    sample=line[::max(1,len(line)//300)]
    if sample[-1]!=line[-1]:sample.append(line[-1])
    wkt="LINESTRING("+",".join(f"{lon} {lat}" for lat,lon in sample)+")"
    try:
        rows=db.execute(_SEGMENT_RISK_SQL,{"wkt":wkt,"buf":SEGMENT_BUFFER_M,"min_overlap":SEGMENT_MIN_OVERLAP_M}).mappings().all()
    except Exception:
        # Routing must keep working without segments / scores (fresh DB, M2 not run).
        db.rollback(); return 0.0,0
    if not rows:return 0.0,0
    total=sum(float(r["overlap_m"]) for r in rows) or 1.0
    peak=max(float(r["risk_score"]) for r in rows)
    mean=sum(float(r["risk_score"])*float(r["overlap_m"]) for r in rows)/total
    return round(min(1.0,.72*peak+.28*mean),3),len(rows)

HAZARD_RADIUS_M=105
# True distance (geography, metres) from each hazard to the whole route LineString. Measuring to route
# vertices missed hazards lying between two far-apart vertices (OSRM puts few on straight roads).
_HAZARD_DISTANCE_SQL=text("""
  WITH r AS (SELECT ST_SetSRID(ST_GeomFromText(:wkt),4326)::geography g),
  h AS (SELECT t.i, ST_SetSRID(ST_MakePoint(t.lon,t.lat),4326)::geography p
        FROM unnest(CAST(:lats AS float8[]),CAST(:lons AS float8[])) WITH ORDINALITY AS t(lat,lon,i))
  SELECT h.i-1 AS idx, ST_Distance(r.g,h.p) AS d FROM r,h WHERE ST_DWithin(r.g,h.p,:radius)
""")

def _wkt(line):return "LINESTRING("+",".join(f"{lon} {lat}" for lat,lon in line)+")"

def _point_segment_m(lat,lon,a,b):
    """Distance from a point to segment a-b, local equirectangular metres (fallback without PostGIS)."""
    k=111320.0*math.cos(math.radians(lat))
    ax,ay=(a[1]-lon)*k,(a[0]-lat)*110540.0; bx,by=(b[1]-lon)*k,(b[0]-lat)*110540.0
    dx,dy=bx-ax,by-ay; n=dx*dx+dy*dy
    t=0.0 if n==0 else max(0.0,min(1.0,-(ax*dx+ay*dy)/n))
    return math.hypot(ax+t*dx,ay+t*dy)

def _hazard_distances(line,hazards,db=None,radius_m=HAZARD_RADIUS_M):
    """{hazard index: true distance in m to the route} for the hazards within radius_m of the route."""
    if not hazards or len(line)<2:return {}
    if db is not None and hasattr(db,"execute"):
        try:
            rows=db.execute(_HAZARD_DISTANCE_SQL,{"wkt":_wkt(line),"radius":radius_m,
                "lats":[float(h["lat"]) for h in hazards],"lons":[float(h["lon"]) for h in hazards]}).mappings().all()
            return {int(r["idx"]):float(r["d"]) for r in rows}
        except Exception:
            db.rollback()  # no PostGIS (tests, fresh DB): exact geometry in Python below
    out={}
    for i,h in enumerate(hazards):
        lat,lon=float(h["lat"]),float(h["lon"])
        d=min(_point_segment_m(lat,lon,line[j],line[j+1]) for j in range(len(line)-1))
        if d<radius_m:out[i]=d
    return out

def _route_exposure(line,hazards,db=None,radius_m=HAZARD_RADIUS_M):
    """Risk is based on actual distance between a candidate geometry and hazards."""
    if not hazards or not line:return 0.0,0
    exposure=[]
    for i,d in _hazard_distances(line,hazards,db,radius_m).items():
        h=hazards[i]
        if d<radius_m:
            # Stronger penalty near the pothole, fading to zero at radius_m.
            exposure.append(float(h.get("risk") or .5)*(1-d/radius_m))
    if not exposure:return 0.0,0
    # Blend peak danger and cumulative exposure; clamp to [0,1].
    risk=min(1.0,.72*max(exposure)+.28*min(1.0,sum(exposure)/2.0))
    return round(risk,3),len(exposure)

def _candidate(route,hazards,db=None):
    line=_line(route)
    hazard_risk,count=_route_exposure(line,hazards,db)
    segment_risk,segments=_segment_risk(db,line)
    # max() rather than a probabilistic sum: a segment holding an M1 event already
    # carries that event in its M2 score, so adding both would count it twice.
    risk=max(hazard_risk,segment_risk)
    distance=float(route["distance"]); duration=float(route["duration"])
    score=round(duration/60 + distance/1000*.32 + risk*22,3)
    return RouteCandidate(distance_m=distance,duration_s=duration,risk=risk,score=score,polyline=line,
                          hazard_risk=hazard_risk,segment_risk=segment_risk,scored_segments=segments),count

def _detour_routes(req):
    """Ask OSRM for road-following corridors on both sides of the direct route.
    The waypoint is only a search hint; returned geometry still follows real roads.
    """
    a=(req.current_lat,req.current_lon); b=(req.destination_lat,req.destination_lon)
    mid_lat=(a[0]+b[0])/2; mid_lon=(a[1]+b[1])/2
    # Perpendicular unit vector in local lat/lon coordinates.
    dx=(b[1]-a[1])*math.cos(math.radians(mid_lat)); dy=b[0]-a[0]
    norm=math.hypot(dx,dy) or 1.0; px=-dy/norm; py=dx/norm
    routes=[]
    # 0.9-2.7 km lateral search gives visibly distinct but still practical corridors.
    for km in (0.9,1.4,2.0,2.7):
        for side in (-1,1):
            lat=mid_lat + side*py*(km/111.0)
            lon=mid_lon + side*px*(km/(111.0*max(.2,math.cos(math.radians(mid_lat)))))
            try:
                found=_fetch_osrm([a,(lat,lon),b],0)
                if found: routes.append(found[0])
            except HTTPException:
                continue
    return routes

def _different_enough(a,b):
    """Reject an 'alternative' that visually sits on top of the initial route."""
    if not a or not b:return False
    bs=b[::max(1,len(b)//120)]; aa=a[::max(1,len(a)//120)]
    near=sum(1 for p in aa if min(haversine_m(p[0],p[1],q[0],q[1]) for q in bs)<45)
    return near/max(1,len(aa)) < .78

@router.post("/route",response_model=RouteResponse)
def get_route(req:RouteRequest,db:Session=Depends(get_db)):
    routes=_osrm(req)
    if not routes:
        raise HTTPException(404,"No route found")

    hazards=_risk_points(db)
    fastest_route=min(routes,key=lambda r:r["duration"])
    fastest,fast_count=_candidate(fastest_route,hazards,db)

    pool=[]
    for route in routes:
        candidate,count=_candidate(route,hazards,db)
        pool.append((candidate,count))

    # If the fastest route is exposed to a meaningful road risk, search additional
    # road-following corridors. This preserves the next-best-route behaviour while
    # using only real RoadEvents / validated citizen reports from PostgreSQL.
    # (M2 segment risk can trigger this too, even with no point hazard nearby.)
    if fastest.risk >= .42:
        for route in _detour_routes(req):
            candidate,count=_candidate(route,hazards,db)
            if _different_enough(fastest.polyline,candidate.polyline):
                pool.append((candidate,count))

    # Deduplicate geometrically equivalent candidates, then rank by the composite
    # time + distance + risk cost.
    unique=[]
    for candidate,count in sorted(pool,key=lambda x:x[0].score):
        if not any(not _different_enough(candidate.polyline,existing.polyline) for existing,_ in unique):
            unique.append((candidate,count))

    safer_pair=next((
        (candidate,count) for candidate,count in unique
        if candidate.polyline != fastest.polyline
        and _different_enough(fastest.polyline,candidate.polyline)
        and candidate.risk + .12 < fastest.risk
    ),None)

    reroute=safer_pair is not None and fastest.risk >= .42
    best,best_count=safer_pair if reroute else (fastest,fast_count)
    if reroute and fastest.segment_risk > fastest.hazard_risk:
        reason=(
            f"Le trajet initial emprunte des segments à risque M2 élevé ({fastest.segment_risk:.0%}) ; "
            f"l'alternative ramène le risque à {best.risk:.0%}."
        )
    elif reroute:
        reason=(
            f"{fast_count} danger(s) routier(s) affectent le trajet initial ; "
            f"l'alternative réduit l'exposition à {best_count}."
        )
    else:
        reason="Itinéraire normal conservé : aucune alternative ne réduit suffisamment le risque."
    alternatives=[candidate for candidate,_ in unique if candidate.polyline != best.polyline][:4]

    return RouteResponse(
        route_id=str(uuid4()),
        status="rerouted" if reroute else "normal_route",
        risk=best.risk,
        polyline=best.polyline,
        score=best.score,
        reason=reason,
        distance_m=best.distance_m,
        duration_s=best.duration_s,
        alternatives=alternatives,
        fastest_polyline=fastest.polyline,
        fastest_risk=fastest.risk,
        fastest_distance_m=fastest.distance_m,
        fastest_duration_s=fastest.duration_s,
        reroute_needed=reroute,
        hazards_on_initial=fast_count,
        hazards_on_best=best_count,
        fastest_segment_risk=fastest.segment_risk,
        best_segment_risk=best.segment_risk,
    )

@router.get("/geocode")
def geocode(q:str=Query(min_length=2,max_length=120)):
    params=urllib.parse.urlencode({"q":f"{q}, Bizerte, Tunisia","format":"jsonv2","limit":5,"countrycodes":"tn"})
    request=urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{params}",headers={"User-Agent":"THNIYETNA/2.0"})
    try:
        with urllib.request.urlopen(request,timeout=5) as r: rows=json.load(r)
        return [{"label":x.get("display_name",q),"lat":float(x["lat"]),"lon":float(x["lon"])} for x in rows]
    except Exception:return []

@router.get("/official-routes")
def list_routes(db:Session=Depends(get_db)):
    return list(db.execute(text("SELECT route_code,name,owner_org,active,metadata,ST_AsGeoJSON(geom)::json geometry FROM official_routes ORDER BY route_code")).mappings())

@router.post("/official-routes")
def create_route(req:RouteCreate,db:Session=Depends(get_db),user=Depends(require_role("transport_supervisor"))):
    if len(req.coordinates)<2: raise HTTPException(422,"At least two coordinates required")
    wkt="LINESTRING("+",".join(f"{lon} {lat}" for lat,lon in req.coordinates)+")"
    row=db.execute(text("""INSERT INTO official_routes(route_code,name,owner_org,geom,active,metadata) VALUES(:c,:n,:o,ST_Multi(ST_GeomFromText(:w,4326)),:a,jsonb_build_object('created_by',CAST(:u AS text))) ON CONFLICT(route_code) DO UPDATE SET name=excluded.name,geom=excluded.geom,active=excluded.active,updated_at=now() RETURNING id::text,route_code,name"""),{"c":req.route_code,"n":req.name,"o":req.owner_org,"w":wkt,"a":req.active,"u":user["sub"]}).mappings().one()
    publish(db,"route.updated",dict(row)); db.commit(); return row

@router.post("/assignments")
def assign_route(req:AssignmentCreate,db:Session=Depends(get_db),user=Depends(require_role("transport_supervisor"))):
    row=db.execute(text("""INSERT INTO route_assignments(route_id,vehicle_id,driver_username,metadata) SELECT r.id,v.id,:d,jsonb_build_object('assigned_by',CAST(:u AS text)) FROM official_routes r,vehicles v WHERE r.route_code=:r AND v.vehicle_code=:v RETURNING id::text"""),{"d":req.driver_username,"u":user["sub"],"r":req.route_code,"v":req.vehicle_code}).mappings().first()
    if not row: raise HTTPException(404,"Route or vehicle not found")
    publish(db,"route.assignment",{"assignment_id":row["id"],**req.model_dump()},req.driver_username); db.commit(); return {"status":"assigned",**row}

@router.get("/assignments")
def list_assignments(db:Session=Depends(get_db),user=Depends(require_role("transport_supervisor"))):
    return list(db.execute(text("""SELECT ra.id::text assignment_id,ra.driver_username,ra.valid_from,ra.valid_to,r.route_code,r.name route_name,v.vehicle_code,v.label vehicle_label FROM route_assignments ra JOIN official_routes r ON r.id=ra.route_id JOIN vehicles v ON v.id=ra.vehicle_id WHERE ra.active ORDER BY ra.created_at DESC""")).mappings())

@router.get("/driver/me")
def driver_route(db:Session=Depends(get_db),user=Depends(require_role("bus_driver"))):
    rows=db.execute(text("""SELECT ra.id::text assignment_id,r.route_code,r.name,v.vehicle_code,v.label,ST_AsGeoJSON(r.geom)::json geometry,r.metadata FROM route_assignments ra JOIN official_routes r ON r.id=ra.route_id JOIN vehicles v ON v.id=ra.vehicle_id WHERE ra.driver_username=:u AND ra.active ORDER BY ra.created_at DESC"""),{"u":user["sub"]}).mappings().all(); return list(rows)

@router.post("/driver/next-best",response_model=RouteResponse)
def driver_next_best(req:RouteRequest,db:Session=Depends(get_db),user=Depends(require_role("bus_driver"))):
    response=get_route(req,db)
    if response.reroute_needed:
        publish(db,"driver.reroute.alert",{"vehicle_id":req.vehicle_id,"risk":response.fastest_risk,"reason":response.reason,"route_id":response.route_id},user["sub"]); db.commit()
    return response
