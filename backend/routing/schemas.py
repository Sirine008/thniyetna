from typing import List, Optional

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    vehicle_id: str = "citizen"
    current_lat: float = Field(ge=-90, le=90)
    current_lon: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lon: float = Field(ge=-180, le=180)
    alternatives: int = Field(default=3, ge=0, le=3)


class RouteCandidate(BaseModel):
    distance_m: float
    duration_s: float
    risk: float
    score: float
    polyline: List[List[float]]
    hazard_risk: float = 0        # exposure to M1 events / citizen complaints
    segment_risk: float = 0       # M2 RiskScore of the segments followed
    scored_segments: int = 0


class RouteResponse(BaseModel):
    route_id: str
    status: str
    risk: float = 0
    polyline: List[List[float]]
    score: float
    reason: Optional[str] = None
    distance_m: float
    duration_s: float
    alternatives: List[RouteCandidate] = []
    fastest_polyline: List[List[float]] = []
    fastest_risk: float = 0
    fastest_distance_m: float = 0
    fastest_duration_s: float = 0
    reroute_needed: bool = False
    hazards_on_initial: int = 0
    hazards_on_best: int = 0
    fastest_segment_risk: float = 0
    best_segment_risk: float = 0


class RouteCreate(BaseModel):
    route_code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    coordinates: List[List[float]]
    owner_org: str = "SRTB"
    active: bool = True


class AssignmentCreate(BaseModel):
    route_code: str
    vehicle_code: str
    driver_username: str
