"""Weather snapshots for attacks, from Open-Meteo (free, no API key).

A snapshot is recorded for the hour an attack started and is never edited by
hand. Recent dates use the forecast API (which keeps ~3 months of history);
older dates (e.g. imported logs) use the historical archive API.

Pressure is barometric pressure reduced to sea level (what weather reports
quote), stored in cmHg and kPa.
"""
import datetime as dt
import json
import urllib.parse
import urllib.request

import store

HPA_TO_CMHG = 0.0750062
PRESSURE_BASIS = "sea-level"  # snapshots without this marker are re-fetched (see store.init_db)
UA = {"User-Agent": "ClusterLog/1.0 (self-hosted)"}


def _get(url, params):
    with urllib.request.urlopen(urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=UA),
                                timeout=15) as r:
        return json.load(r)


def geocode(name):
    j = _get("https://geocoding-api.open-meteo.com/v1/search", {"name": name, "count": 6, "format": "json"})
    out = []
    for r in j.get("results") or []:
        label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
        out.append({"label": label, "lat": r["latitude"], "lon": r["longitude"]})
    return out


def fetch(at, lat, lon):
    """Weather at local time `at` ('YYYY-MM-DDTHH:MM'), or None."""
    date = at[:10]
    age = (dt.date.today() - dt.date.fromisoformat(date)).days
    base = ("https://api.open-meteo.com/v1/forecast" if age <= 80
            else "https://archive-api.open-meteo.com/v1/archive")
    j = _get(base, {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "hourly": "temperature_2m,relative_humidity_2m,pressure_msl",
        "start_date": date, "end_date": date,
    })
    h = j.get("hourly") or {}
    times = h.get("time") or []
    target = at[:13] + ":00"
    if target not in times:
        return None
    i = times.index(target)
    t, rh, p = (h["temperature_2m"][i], h["relative_humidity_2m"][i], h["pressure_msl"][i])
    if t is None or rh is None or p is None:
        return None  # archive data lags a few days; retried later
    return {
        "temp_c": round(t, 1),
        "humidity": round(rh),
        "pressure_cmhg": round(p * HPA_TO_CMHG, 2),
        "pressure_kpa": round(p / 10, 2),
        "basis": PRESSURE_BASIS,
        "hour": target,
        "source": "open-meteo.com",
    }


def fill(attack_id):
    """Fetch and store the snapshot for one attack. Silent on failure."""
    s = store.settings_raw()
    if not (s["lat"] and s["lon"]):
        return False
    a = store.q1("SELECT started_at FROM attacks WHERE id=? AND weather IS NULL", (attack_id,))
    if not a:
        return False
    try:
        w = fetch(a["started_at"], s["lat"], s["lon"])
    except Exception as e:  # offline, rate-limited, etc.
        print(f"weather: attack {attack_id}: {e}", flush=True)
        return False
    if not w:
        return False
    w["place"] = s["place"]
    with store.tx() as c:
        c.execute("UPDATE attacks SET weather=? WHERE id=? AND weather IS NULL", (json.dumps(w), attack_id))
    return True


def fill_missing(limit=20):
    for r in store.q("SELECT id FROM attacks WHERE weather IS NULL ORDER BY started_at DESC LIMIT ?", (limit,)):
        fill(r["id"])
