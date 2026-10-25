"""End-to-end API checks. Run via tests/run.sh (starts a throwaway server).

    python3 tests/test_api.py http://127.0.0.1:8799
"""
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799") + "/api"


def call(method, path, body=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode()
        return t if raw else json.loads(t)


def status(method, path, body=None):
    try:
        call(method, path, body)
        return 200
    except urllib.error.HTTPError as e:
        return e.code


def main():
    assert call("GET", "/health")["ok"]
    tr = {t["name"]: t for t in call("GET", "/treatments")}
    ox, zo, es = tr["Oxygen"], tr["Zomig nasal spray"], tr["Electro-stimulation"]
    assert "Tylenol + Advil (extra strength)" in tr

    c = call("POST", "/cycles", {"name": "Test cycle", "started_on": "2026-01-30"})

    # a headache over midnight, built with the start form + events
    a = call("POST", "/attacks", {"cycle_id": c["id"], "started_at": "2026-02-07T23:26", "kip": 6, "phase": "shadow",
                                  "side": "Left", "locations": ["temple", "eye"], "pain_types": ["stabbing"],
                                  "note": "woken up"})
    assert a["number"] == 1 and a["side"] == "Left" and a["locations"] == ["temple", "eye"]
    assert a["start_phase"] == "shadow"
    call("POST", "/entries", {"kind": "treatment", "at": "2026-02-07T23:30", "attack_id": a["id"],
                              "treatment_id": zo["id"], "amount": "5"})
    call("POST", "/entries", {"kind": "pain", "at": "2026-02-07T23:40", "attack_id": a["id"], "kip": 8, "phase": "build"})
    # logged from the cycle screen, inside the headache's window -> attached automatically
    e = call("POST", "/entries", {"kind": "treatment", "at": "2026-02-08T00:01", "cycle_id": c["id"],
                                  "treatment_id": es["id"], "amount": "3"})
    assert e["attack_id"] == a["id"] and e["title"] == "Electro-stimulation, level 3", e
    done = call("POST", f"/attacks/{a['id']}/end", {"ended_at": "2026-02-08T00:12", "note": "pain gone"})
    assert done["peak_kip"] == 8 and done["ended_at"] == "2026-02-08T00:12"

    # retro headache absorbs a med logged earlier
    call("POST", "/entries", {"kind": "treatment", "at": "2026-02-08T18:02", "cycle_id": c["id"],
                              "treatment_id": ox["id"], "amount": "25"})
    a2 = call("POST", "/attacks", {"cycle_id": c["id"], "started_at": "2026-02-08T18:00", "ended_at": "2026-02-08T18:25", "kip": 7})
    assert any(x["kind"] == "treatment" for x in a2["entries"]), "retro headache should absorb the oxygen dose"

    # event outside a headache, note
    call("POST", "/entries", {"kind": "event", "at": "2026-02-11T08:30", "title": "Emgality injection 300mg"})
    assert status("POST", "/entries", {"kind": "note", "at": "2026-02-09T06:45", "note": ""}) == 400
    assert status("POST", "/entries", {"kind": "pain", "at": "2026-02-09T06:45", "kip": 11, "attack_id": a["id"]}) == 400
    assert status("POST", "/attacks", {"started_at": "2026-02-09T10:00", "ended_at": "2026-02-09T09:00"}) == 400

    # stats, weeks counted from the cycle start
    s = call("GET", f"/stats?cycle_id={c['id']}&start=2026-01-30&end=2026-02-14")
    assert s["attacks"] == 2 and s["duration"]["median"] == 36, s["duration"]
    assert s["weeks"][1]["label"].startswith("Week 2 (06 Feb") and s["weeks"][1]["attacks"] == 2, s["weeks"]

    # daily limit
    call("PUT", f"/treatments/{zo['id']}", {**zo, "max_per_day": 2})
    rec = call("GET", "/recent?since=2026-02-07T00:00")
    assert next(r for r in rec if r["treatment_id"] == zo["id"])["max_per_day"] == 2

    # duration treatments: start, see it running, stop it (also when the headache ends)
    assert ox["mode"] == "duration" and es["mode"] == "duration" and zo["mode"] == "dose"
    a3 = call("POST", "/attacks", {"cycle_id": c["id"], "started_at": "2026-02-09T03:00", "kip": 5})
    o1 = call("POST", "/entries", {"kind": "treatment", "at": "2026-02-09T03:02", "attack_id": a3["id"],
                                   "treatment_id": ox["id"], "amount": "15"})
    e1 = call("POST", "/entries", {"kind": "treatment", "at": "2026-02-09T03:05", "attack_id": a3["id"],
                                   "treatment_id": es["id"], "amount": "3"})
    assert o1["mode"] == "duration" and o1["ended_at"] is None
    running = lambda: {r["id"] for r in call("GET", "/running?since=2026-02-08T04:00")}
    assert {o1["id"], e1["id"]} <= running()
    assert status("POST", "/entries", {"kind": "treatment", "at": "2026-02-09T03:10", "attack_id": a3["id"],
                                       "treatment_id": zo["id"], "ended_at": "2026-02-09T03:30"}) == 400, "doses can't stop"
    assert status("POST", "/entries", {"kind": "treatment", "at": "2026-02-09T03:10", "attack_id": a3["id"],
                                       "treatment_id": ox["id"], "ended_at": "2026-02-09T03:00"}) == 400
    assert status("POST", f"/entries/{o1['id']}/stop", {"ended_at": "2026-02-09T02:00"}) == 400
    call("POST", f"/attacks/{a3['id']}/end", {"ended_at": "2026-02-09T03:40", "stop_ids": [o1["id"]]})
    assert o1["id"] not in running() and e1["id"] in running(), "only the ticked session stops with the headache"
    assert call("POST", f"/entries/{e1['id']}/stop", {"ended_at": "2026-02-09T03:50"})["ended_at"] == "2026-02-09T03:50"
    assert e1["id"] not in running()
    call("POST", "/entries", {"kind": "treatment", "at": "2026-02-10T05:00", "ended_at": "2026-02-10T05:20",
                              "cycle_id": c["id"], "treatment_id": ox["id"], "amount": "15"})  # logged after the fact
    row = next(t for t in call("GET", f"/stats?cycle_id={c['id']}")["treatments"] if t["name"] == "Oxygen")
    assert row["treatment_id"] == ox["id"] and row["session"]["n"] == 2 and row["total_min"] == 58, row
    log = call("GET", f"/treatments/{ox['id']}/log?cycle_id={c['id']}")
    assert [(d["at"], d["attack_number"], d["length"]) for d in log["doses"]] == [
        ("2026-02-08T18:02", 2, None), ("2026-02-09T03:02", 3, 38), ("2026-02-10T05:00", None, 20)], log["doses"]
    assert log["summary"]["uses"] == 3 and any(o["name"] == "Zomig nasal spray" for o in log["others"])

    # plain-text report: no markup or decoration symbols
    t = call("GET", "/report?start=2026-02-07&end=2026-02-11&format=text", raw=True)
    assert "Headache 1 started. Left side. Location: temple, eye. Type: stabbing." in t, t
    assert "Headache 1 ended. Lasted 46 min. Peak KIP 8." in t
    assert "23:30 Medication: Zomig nasal spray, 5 mg" in t
    assert "Event: Emgality injection 300mg" in t
    assert "03:02 Medication: Oxygen, 15 L/min, 03:02 to 03:40 (38 min)" in t, t
    assert "18:02 Medication: Oxygen, 25 L/min, no stop time recorded" in t
    assert "Oxygen: used 3 times (median session 29 min, total 58 min)" in t
    m = t[t.index("Medication log"):t.index("Daily log")]
    assert "Oxygen (abortive)\nSun 08 Feb 2026: 18:02 (25 L/min, no stop time, headache 2)\n" \
           "Mon 09 Feb 2026: 03:02 (15 L/min, 38 min, headache 3)\nTue 10 Feb 2026: 05:00 (15 L/min, 20 min)" in m, m
    assert "Zomig nasal spray (abortive)\nSat 07 Feb 2026: 23:30 (5 mg, headache 1)" in m, m
    for bad in ("▶", "■", "|", "===", "---", "#", "<", "↑", "↓", "·", "**"):
        assert bad not in t, f"plain report contains {bad!r}"
    assert "<svg" in call("GET", "/report?start=2026-02-07&end=2026-02-11&format=html", raw=True)
    assert "<h2>Medication log</h2>" in call("GET", "/report?start=2026-02-07&end=2026-02-11&format=html", raw=True)
    csv_t = call("GET", "/report?start=2026-02-07&end=2026-02-11&format=csv", raw=True)
    assert csv_t.startswith("date,time,cycle,headache") and "2026-02-09 03:40,38" in csv_t, csv_t
    assert status("POST", "/report/email", {}) in (404, 405), "in-app email should be gone"

    regimen_checks()

    # learnings, settings, text size
    call("PUT", f"/cycles/{c['id']}", {**c, "ended_on": "2026-03-20", "learnings": "Start verapamil week 1."})
    assert call("GET", "/learnings")[0]["learnings"] == "Start verapamil week 1."
    assert call("PUT", "/settings", {"font_scale": "1.15"})["font_scale"] == "1.15"
    assert status("PUT", "/settings", {"font_scale": "9"}) == 400
    assert call("GET", "/settings")["theme"] == "normal"
    assert call("PUT", "/settings", {"theme": "dim"})["theme"] == "dim"
    assert status("PUT", "/settings", {"theme": "purple"}) == 400
    assert "#a3a3a3" in call("GET", f"/chart/daily.svg?cycle_id={c['id']}&theme=dim", raw=True)
    call("PUT", "/settings", {"theme": "normal"})
    assert "smtp_host" not in call("GET", "/settings")

    # text-log import incl. New Year rollover, then backup/restore round trip
    log = "Feb 12\n0035 - woken up\n0042 - oxygen, kip 6 to kip 8\nDec 31\n2300 - sleep\nJan 1\n0010 - new year"
    p = call("POST", "/import/text", {"text": log, "year": 2026, "cycle_id": c["id"], "dry_run": True})
    assert [r["at"] for r in p["rows"]] == ["2026-02-12T00:35", "2026-02-12T00:42", "2026-12-31T23:00", "2027-01-01T00:10"]
    assert p["rows"][1]["kind"] == "pain" and p["rows"][1]["kip"] == 8
    data = json.loads(call("GET", "/backup", raw=True))
    assert any(e["ended_at"] == "2026-02-09T03:40" for e in data["entries"])
    assert next(t for t in data["treatments"] if t["name"] == "Oxygen")["mode"] == "duration"
    counts = call("POST", "/restore", data)["counts"]
    assert counts["attacks"] == 3 and call("GET", "/settings")["pain_types"], "restore must keep option lists"
    assert counts["supplement_logs"] == 4 and counts["supplement_items"] == 9, counts
    assert len(call("GET", "/supplements?include_archived=true")) == 10
    print("API tests passed")


def regimen_checks():
    """D3 regimen: loading schedules per cycle, additive daily totals, food, B-50 course, report, no chart."""
    sup = {s["name"]: s for s in call("GET", "/supplements")}
    d3, om, mg, b50, zn = (sup[n] for n in ("Vitamin D3", "Omega 3 fish oil", "Magnesium", "Vitamin B-50", "Zinc"))
    assert len(sup) == 10 and d3["role"] == "d3" and b50["course_days"] == 90 and om["target_max"] == 2400

    c2 = call("POST", "/cycles", {"name": "Spring", "started_on": "2026-04-01", "ended_on": "2026-04-03",
                                  "d3_schedule": "two_week"})
    assert c2["d3_schedule"] == "two_week"
    assert status("POST", "/cycles", {"name": "x", "started_on": "2026-04-01", "d3_schedule": "weekly"}) == 400
    r = call("GET", f"/regimen?date=2026-04-02&cycle_id={c2['id']}")
    assert r["d3"]["target"] == 50000 and r["d3"]["until_maintenance"] == 13 and r["d3"]["day"] is None, r["d3"]

    item = lambda s, amt, **k: {"supplement_id": s["id"], "amount": amt, **k}
    call("POST", "/supplement-logs", {"at": "2026-04-02T08:00", "cycle_id": c2["id"], "items": [
        item(d3, 30000), item(om, 1000), item(mg, 200, source="food"), item(b50, 1)]})
    r = call("GET", f"/regimen?date=2026-04-02&cycle_id={c2['id']}")
    row = {s["name"]: s for s in r["supplements"]}
    assert r["d3"]["day"] == 1 and row["Vitamin D3"]["remaining"] == 20000 and not row["Vitamin D3"]["met"]
    assert row["Vitamin B-50"]["course"]["days_left"] == 90
    second = call("POST", "/supplement-logs", {"at": "2026-04-02T20:00", "cycle_id": c2["id"], "note": "with dinner",
                                               "items": [item(d3, 20000), item(mg, 200)]})
    row = {s["name"]: s for s in call("GET", f"/regimen?date=2026-04-02&cycle_id={c2['id']}")["supplements"]}
    assert row["Vitamin D3"]["met"] and row["Magnesium"]["taken"] == 400 and row["Magnesium"]["food"] == 200
    assert row["Magnesium"]["met"] and not row["Zinc"]["met"]
    # editing a log: the sheet's totals leave out the log being edited
    r = call("GET", f"/regimen?date=2026-04-02&cycle_id={c2['id']}&exclude_log={second['id']}")
    assert next(s for s in r["supplements"] if s["name"] == "Vitamin D3")["taken"] == 30000
    assert call("PUT", f"/supplement-logs/{second['id']}", {"at": "2026-04-02T21:00", "cycle_id": c2["id"], "note": "with dinner",
                "items": [item(d3, 20000), item(mg, 200)]})["at"] == "2026-04-02T21:00"
    d = call("GET", f"/regimen?date=2026-04-09&cycle_id={c2['id']}")["d3"]
    assert (d["day"], d["target"], d["phase"], d["until_maintenance"]) == (8, 40000, "Loading week 2", 6), d
    d = call("GET", f"/regimen?date=2026-04-15&cycle_id={c2['id']}")["d3"]
    assert (d["target"], d["phase"]) == (10000, "Maintenance"), d
    assert call("GET", "/regimen?date=2026-04-02")["d3"]["target"] == 10000, "outside a cycle = maintenance"
    row = {s["name"]: s for s in call("GET", "/regimen?date=2026-05-01")["supplements"]}
    assert row["Vitamin B-50"]["course"]["days_left"] == 61

    assert status("POST", "/supplement-logs", {"at": "2026-04-02T09:00", "items": []}) == 400
    assert status("POST", "/supplement-logs", {"at": "2026-04-02T09:00", "items": [item(zn, 10, loading=True)]}) == 400
    assert status("POST", "/supplement-logs", {"at": "2026-04-02T09:00", "items": [item(zn, 10, source="pill")]}) == 400

    # loading started later than the first D3 dose: earlier days count as maintenance
    late = call("POST", "/cycles", {"name": "Late", "started_on": "2026-08-01", "ended_on": "2026-08-12",
                                    "d3_schedule": "two_week"})
    call("POST", "/supplement-logs", {"at": "2026-08-01T07:15", "cycle_id": late["id"], "items": [item(d3, 11000)]})
    call("PUT", f"/cycles/{late['id']}", {**late, "d3_started_on": "2026-08-10"})
    d = call("GET", f"/regimen?date=2026-08-01&cycle_id={late['id']}")["d3"]
    assert (d["target"], d["phase"]) == (10000, "Before loading"), d
    d = call("GET", f"/regimen?date=2026-08-11&cycle_id={late['id']}")["d3"]
    assert (d["day"], d["target"], d["until_maintenance"]) == (2, 50000, 12), d
    assert call("GET", f"/stats?cycle_id={late['id']}")["regimen"]["status"]["day"] == 3
    call("DELETE", f"/cycles/{late['id']}")

    # four-week schedule: 20,000 IU a day plus one 50,000 IU loading dose a week
    c3 = call("POST", "/cycles", {"name": "Summer", "started_on": "2026-06-01", "ended_on": "2026-06-08",
                                  "d3_schedule": "four_week"})
    call("POST", "/supplement-logs", {"at": "2026-06-01T08:00", "cycle_id": c3["id"],
                                      "items": [item(d3, 20000), item(d3, 50000, loading=True)]})
    r = call("GET", f"/regimen?date=2026-06-01&cycle_id={c3['id']}")
    assert r["d3"]["weekly_loading"] and r["d3"]["loading_taken"] and r["d3"]["until_maintenance"] == 28
    assert next(s for s in r["supplements"] if s["role"] == "d3")["met"]
    r = call("GET", f"/regimen?date=2026-06-08&cycle_id={c3['id']}")
    assert r["d3"]["loading_week"] == 2 and not r["d3"]["loading_taken"]
    g = call("GET", f"/stats?cycle_id={c3['id']}")["regimen"]
    assert g["loading_doses"] == {"taken": 1, "expected": 2} and g["days"] == 8, g

    # stats, journal, chart, report
    g = call("GET", f"/stats?cycle_id={c2['id']}")["regimen"]
    assert g["days"] == 2 and g["complete_days"] == 0 and g["schedule_label"] == "Two-week loading", g
    dd = next(p for p in g["supplements"] if p["name"] == "Vitamin D3")
    assert (dd["days_met"], dd["days_expected"], dd["total"]) == (1, 2, 50000), dd
    j = call("GET", f"/journal?cycle_id={c2['id']}")
    assert len(j["supplement_logs"]) == 2 and j["supplement_logs"][1]["note"] == "with dinner"
    assert "Vitamin" not in call("GET", f"/chart/daily.svg?cycle_id={c2['id']}&meds=all", raw=True)
    t = call("GET", f"/report?start=2026-04-01&end=2026-04-03&cycle_id={c2['id']}&format=text", raw=True)
    assert "\nD3 regimen\n" in t and "Schedule: Spring: Two-week loading, loading started Thu 02 Apr 2026, " \
           "maintenance (10,000 IU a day) from Wed 15 Apr 2026." in t, t
    assert "Thu 02 Apr 2026, loading week 1, D3 target 50,000 IU: Vitamin D3 50,000 IU; " in t, t
    assert "Magnesium 400 mg (200 from food)" in t and "Missed: Calcium citrate" in t, t
    assert "Fri 03 Apr 2026, loading week 1, D3 target 50,000 IU: nothing recorded. Missed: Vitamin D3, " in t, t
    for bad in ("|", "#", "<", "·"):
        assert bad not in t, f"plain report contains {bad!r}"
    assert "<h2>D3 regimen</h2>" in call("GET", f"/report?start=2026-04-01&end=2026-04-03&format=html", raw=True)
    assert ",supplement,,,Vitamin D3,30000 IU," in call("GET", "/report?start=2026-04-01&end=2026-04-03&format=csv", raw=True)

    # add / remove supplements: logged ones (and D3) are archived, unused ones deleted
    new = call("POST", "/supplements", {"name": "Vitamin C", "default_amount": 500, "uom": "mg", "target_min": 500})
    assert call("DELETE", f"/supplements/{new['id']}")["archived"] is False
    assert call("DELETE", f"/supplements/{zn['id']}")["archived"] is False
    assert call("DELETE", f"/supplements/{mg['id']}")["archived"] is True
    assert call("DELETE", f"/supplements/{d3['id']}")["archived"] is True
    call("PUT", f"/supplements/{d3['id']}", {**d3, "archived": False})
    call("PUT", f"/supplements/{mg['id']}", {**mg, "archived": False})
    assert status("POST", "/supplements", {"name": "x", "target_min": 5, "target_max": 1}) == 400
    call("POST", "/supplements", {"name": "Zinc", "default_amount": 10, "uom": "mg", "target_min": 10})


if __name__ == "__main__":
    main()
