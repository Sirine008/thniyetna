"""M4 backend aggregation for citizen, driver and ministry dashboards."""
from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from .schemas import ComplaintIn,ComplaintOut,ComplaintStatusUpdate,AlertAck,VehicleCreate
from shared.auth import require_role,get_current_user
from shared.db import get_db
from shared.realtime import publish

router=APIRouter()

@router.post("/complaints",response_model=ComplaintOut)
def submit_complaint(c:ComplaintIn,db:Session=Depends(get_db),user=Depends(require_role("citizen"))):
    actor=c.citizen_id or user["sub"]
    row=db.execute(text("""INSERT INTO complaints(actor_ref,description,geom,payload) VALUES(:a,:d,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),jsonb_build_object('category',CAST(:cat AS text),'image_url',CAST(:img AS text),'image_storage_key',CAST(:storage_key AS text))) RETURNING id::text,status,description,ST_Y(geom) latitude,ST_X(geom) longitude,created_at,payload->>'category' category,payload->>'image_url' image_url"""),{"a":actor,"d":c.description,"lon":c.longitude,"lat":c.latitude,"cat":c.category,"img":c.image_url,"storage_key":c.image_storage_key}).mappings().one()
    if c.category == "road_damage" and c.image_storage_key:
        db.execute(text("""INSERT INTO perception_jobs(job_type,source,storage_key,media_uri,options,created_by) VALUES('image','citizen',:storage_key,:media,CAST(:options AS jsonb),:created_by)"""),{
            "storage_key":c.image_storage_key,
            "media":c.image_url,
            "options":json.dumps({"latitude":c.latitude,"longitude":c.longitude,"captured_at":datetime.now(timezone.utc).isoformat(),"complaint_id":row["id"]}),
            "created_by":user["sub"],
        })
    publish(db,"complaint.created",dict(row),"equipment_supervisor"); db.commit(); return row

@router.get("/complaints/mine",response_model=List[ComplaintOut])
def my_complaints(db:Session=Depends(get_db),user=Depends(require_role("citizen"))):
    return list(db.execute(text("SELECT id::text,status,description,ST_Y(geom) latitude,ST_X(geom) longitude,created_at,payload->>'category' category,payload->>'image_url' image_url FROM complaints WHERE actor_ref=:u ORDER BY created_at DESC"),{"u":user["sub"]}).mappings())

@router.get("/complaints",response_model=List[ComplaintOut])
def list_complaints(status:str|None=None,db:Session=Depends(get_db),user=Depends(require_role("equipment_supervisor"))):
    return list(db.execute(text("""SELECT id::text,status,description,ST_Y(geom) latitude,ST_X(geom) longitude,created_at,payload->>'category' category,payload->>'image_url' image_url FROM complaints WHERE (CAST(:s AS text) IS NULL OR status=CAST(:s AS text)) ORDER BY created_at DESC"""),{"s":status}).mappings())

@router.patch("/complaints/{complaint_id}/status")
def update_complaint(complaint_id:str,req:ComplaintStatusUpdate,db:Session=Depends(get_db),user=Depends(require_role("equipment_supervisor"))):
    if req.status not in {"open","under_review","validated","planned","resolved","rejected"}: raise HTTPException(422,"Unsupported status")
    old=db.execute(text("SELECT status,actor_ref FROM complaints WHERE id=:id"),{"id":complaint_id}).mappings().first()
    if not old: raise HTTPException(404,"Complaint not found")
    db.execute(text("UPDATE complaints SET status=:s,payload=payload||jsonb_build_object('last_note',CAST(:n AS text),'updated_by',CAST(:u AS text)) WHERE id=:id"),{"s":req.status,"n":req.note,"u":user["sub"],"id":complaint_id})
    db.execute(text("INSERT INTO complaint_status_history(complaint_id,old_status,new_status,changed_by,note) VALUES(:id,:o,:n,:u,:note)"),{"id":complaint_id,"o":old["status"],"n":req.status,"u":user["sub"],"note":req.note})
    publish(db,"complaint.status",{"complaint_id":complaint_id,"old_status":old["status"],"new_status":req.status,"note":req.note},old["actor_ref"]); db.commit(); return {"id":complaint_id,"status":req.status}

@router.get("/map")
def map_snapshot(db:Session=Depends(get_db)):
    events=list(db.execute(text("SELECT id::text,event_type,severity,confidence,status,source,ST_Y(geom) latitude,ST_X(geom) longitude,observed_at,segment_id::text FROM road_events ORDER BY observed_at DESC LIMIT 250")).mappings())
    complaints=list(db.execute(text("SELECT id::text,description,status,ST_Y(geom) latitude,ST_X(geom) longitude,created_at,payload->>'category' category FROM complaints ORDER BY created_at DESC LIMIT 250")).mappings())
    # Latest valid score per segment; an M2 model score (risk_level set) wins over a contextual-v1 fallback row.
    segments=list(db.execute(text("""SELECT s.id::text,s.segment_code,s.name,s.road_class,ST_AsGeoJSON(s.geom)::json geometry,rs.risk_score,rs.risk_category,coalesce(rs.risk_level,rs.risk_category) risk_level,rs.maintenance_priority,rs.predicted_condition,rs.top_factors,rs.model_version FROM road_segments s LEFT JOIN LATERAL(SELECT risk_score,risk_category,risk_level,maintenance_priority,predicted_condition,top_factors,model_version FROM risk_scores r WHERE r.segment_id=s.id AND (r.valid_until IS NULL OR r.valid_until>now()) ORDER BY (r.risk_level IS NOT NULL) DESC, created_at DESC LIMIT 1) rs ON true ORDER BY s.segment_code""")).mappings())
    routes=list(db.execute(text("SELECT route_code,name,owner_org,active,ST_AsGeoJSON(geom)::json geometry,metadata FROM official_routes WHERE active ORDER BY route_code")).mappings())
    return {"generated_at":datetime.now(timezone.utc),"events":events,"complaints":complaints,"segments":segments,"routes":routes}

@router.get("/dashboard/equipment")
def equipment_dashboard(db:Session=Depends(get_db),user=Depends(require_role("equipment_supervisor"))):
    return db.execute(text("""SELECT (SELECT count(*) FROM complaints WHERE status NOT IN ('resolved','rejected')) open_complaints,(SELECT count(*) FROM road_events WHERE status='observed') unvalidated_events,(SELECT count(*) FROM road_events WHERE observed_at>now()-interval '24 hours') events_24h,(SELECT count(*) FROM inspection_sessions WHERE status='active') active_inspections""")).mappings().one()

@router.get("/dashboard/transport")
def transport_dashboard(db:Session=Depends(get_db),user=Depends(require_role("transport_supervisor"))):
    return db.execute(text("""SELECT (SELECT count(*) FROM official_routes WHERE active) active_routes,(SELECT count(*) FROM vehicles WHERE vehicle_type='bus' AND active) active_buses,(SELECT count(*) FROM route_assignments WHERE active) assignments,(SELECT count(*) FROM risk_scores WHERE coalesce(risk_level,risk_category) IN ('high','critical') AND created_at>now()-interval '24 hours') high_risk_updates""")).mappings().one()

@router.get("/alerts")
def alerts(db:Session=Depends(get_db),user=Depends(get_current_user)):
    return list(db.execute(text("SELECT id::text,topic,payload,status,created_at FROM notification_outbox WHERE recipient_ref IS NULL OR recipient_ref=:u OR recipient_ref=:r ORDER BY created_at DESC LIMIT 100"),{"u":user["sub"],"r":user["role"]}).mappings())

@router.post("/alerts/{notification_id}/ack")
def ack(notification_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    db.execute(text("UPDATE notification_outbox SET status='delivered',delivered_at=now() WHERE id=:id"),{"id":notification_id}); db.commit(); return {"status":"acknowledged"}


@router.post("/vehicles", status_code=201)
def create_vehicle(req:VehicleCreate,db:Session=Depends(get_db),user=Depends(require_role("transport_supervisor","equipment_supervisor"))):
    row=db.execute(text("""
        INSERT INTO vehicles(vehicle_code,vehicle_type,owner_org,label,metadata)
        VALUES(:code,:type,:org,:label,jsonb_build_object('created_by',CAST(:user AS text)))
        ON CONFLICT(vehicle_code) DO UPDATE SET
          vehicle_type=excluded.vehicle_type,owner_org=excluded.owner_org,label=excluded.label,active=true
        RETURNING vehicle_code,vehicle_type,owner_org,label,metadata,active
    """),{"code":req.vehicle_code,"type":req.vehicle_type,"org":req.owner_org,"label":req.label,"user":user["sub"]}).mappings().one()
    db.commit(); return dict(row)

@router.get("/vehicles")
def list_vehicles(db:Session=Depends(get_db),user=Depends(require_role("transport_supervisor","equipment_supervisor"))):
    return list(db.execute(text("SELECT vehicle_code,vehicle_type,owner_org,label,metadata,active FROM vehicles ORDER BY vehicle_code")).mappings())

@router.get("/complaints/{complaint_id}/history")
def complaint_history(complaint_id:str,db:Session=Depends(get_db),user=Depends(require_role("equipment_supervisor"))):
    return list(db.execute(text("SELECT old_status,new_status,changed_by,note,changed_at FROM complaint_status_history WHERE complaint_id=:id ORDER BY changed_at"),{"id":complaint_id}).mappings())
