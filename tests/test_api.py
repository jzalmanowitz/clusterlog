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

    # plain-text report: no markup or decoration symbols
    t = call("GET", "/report?start=2026-02-07&end=2026-02-11&format=text", raw=True)
    assert "Headache 1 started. Left side. Location: temple, eye. Type: stabbing." in t, t
    assert "Headache 1 ended. Lasted 46 min. Peak KIP 8." in t
    assert "23:30 Medication: Zomig nasal spray, 5 mg" in t
    assert "Event: Emgality injection 300mg" in t
    for bad in ("▶", "■", "|", "===", "---", "#", "<", "↑", "↓", "·", "**"):
        assert bad not in t, f"plain report contains {bad!r}"
    assert "<svg" in call("GET", "/report?start=2026-02-07&end=2026-02-11&format=html", raw=True)
    assert call("GET", "/report?start=2026-02-07&end=2026-02-11&format=csv", raw=True).startswith("date,time,cycle,headache")
    assert status("POST", "/report/email", {}) in (404, 405), "in-app email should be gone"

    # learnings, settings, text size
    call("PUT", f"/cycles/{c['id']}", {**c, "ended_on": "2026-03-20", "learnings": "Start verapamil week 1."})
    assert call("GET", "/learnings")[0]["learnings"] == "Start verapamil week 1."
    assert call("PUT", "/settings", {"font_scale": "1.15"})["font_scale"] == "1.15"
    assert status("PUT", "/settings", {"font_scale": "9"}) == 400
    assert "smtp_host" not in call("GET", "/settings")

    # text-log import incl. New Year rollover, then backup/restore round trip
    log = "Feb 12\n0035 - woken up\n0042 - oxygen, kip 6 to kip 8\nDec 31\n2300 - sleep\nJan 1\n0010 - new year"
    p = call("POST", "/import/text", {"text": log, "year": 2026, "cycle_id": c["id"], "dry_run": True})
    assert [r["at"] for r in p["rows"]] == ["2026-02-12T00:35", "2026-02-12T00:42", "2026-12-31T23:00", "2027-01-01T00:10"]
    assert p["rows"][1]["kind"] == "pain" and p["rows"][1]["kip"] == 8
    data = json.loads(call("GET", "/backup", raw=True))
    counts = call("POST", "/restore", data)["counts"]
    assert counts["attacks"] == 2 and call("GET", "/settings")["pain_types"], "restore must keep option lists"
    print("API tests passed")


if __name__ == "__main__":
    main()
