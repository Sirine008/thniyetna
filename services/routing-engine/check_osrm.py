"""Small OSRM connectivity check for the Bizerte graph."""
import json
import urllib.request

url = "http://localhost:5002/route/v1/driving/9.8739,37.2746;9.9140,37.2366?overview=false"
with urllib.request.urlopen(url, timeout=5) as response:
    payload = json.load(response)
if payload.get("code") != "Ok":
    raise SystemExit(payload)
print("OSRM OK", payload["routes"][0]["distance"], "m")
