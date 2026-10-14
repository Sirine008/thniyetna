# Routing Engine (M3)

Wraps OSRM/GraphHopper for map matching and path finding, and implements the
multi-objective cost function that balances safety (M2 risk), time, and
distance so routing doesn't just pick the shortest path through a hazard.

- `osrm_client.py` — thin client for the OSRM/GraphHopper HTTP API
- `map_matching.py` — snap noisy GPS points to the road graph
- `cost_function.py` — multi-objective scoring for candidate routes
