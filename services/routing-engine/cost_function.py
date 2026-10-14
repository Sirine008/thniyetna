"""Simple explainable route score. Lower is better."""
def score_route(distance_km: float, duration_min: float, max_segment_risk: float) -> float:
    risk=max(0.0,min(1.0,float(max_segment_risk)))
    return round(duration_min + 0.35*distance_km + 18.0*risk,3)
