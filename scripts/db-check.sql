SELECT postgis_version();
SELECT segment_code,ST_Length(geom::geography)::int AS length_m FROM road_segments ORDER BY segment_code;
SELECT route_code,name FROM official_routes;
