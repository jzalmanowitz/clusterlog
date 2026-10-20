"""ClusterLog — a self-hosted cluster headache journal.

FastAPI JSON API under /api, plus the static single-page app at /.
"""
import datetime as dt
import json
import re
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, closing
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import reports
import store
import weather
from store import bad, day, q, q1, ts, tx

APP_VERSION = "1.1.0"
STATIC_DIR = store.Path(__file__).parent / "static"


# ---------------------------------------------------------------- lifecycle

def make_backup(tag="auto"):
    store.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = store.BACKUP_DIR / f"clusterlog-{dt.datetime.now():%Y%m%d-%H%M%S}-{tag}.db"
    with closing(store.connect()) as src, closing(sqlite3.connect(path)) as dst:
        src.backup(dst)
    autos = sorted(store.BACKUP_DIR.glob("clusterlog-*-auto.db"))
    for old in autos[:-30]:  # keep the 30 most recent daily backups
        old.unlink(missing_ok=True)
    return path


def maintenance_loop():
    """Hourly: one automatic backup per day, and fill in any missing weather."""
    time.sleep(20)
    while True:
        try:
            if not list(store.BACKUP_DIR.glob(f"clusterlog-{dt.date.today():%Y%m%d}-*-auto.db")):
                make_backup("auto")
        except Exception as e:
            print(f"backup failed: {e}", flush=True)
        try:
            weather.fill_missing()
        except Exception as e:
            print(f"weather fill failed: {e}", flush=True)
        time.sleep(3600)


@asynccontextmanager
async def lifespan(_app):
    store.init_db()
    threading.Thread(target=maintenance_loop, daemon=True).start()
    yield


app = FastAPI(title="ClusterLog", version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def no_cache(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return resp


def weather_async(attack_id):
    threading.Thread(target=weather.fill, args=(attack_id,), daemon=True).start()


@app.get("/api/health")
def health():
    return {"ok": True, "version": APP_VERSION}


# ---------------------------------------------------------------- cycles

class CycleIn(BaseModel):
    name: str
    started_on: str
    ended_on: Optional[str] = None
    notes: Optional[str] = ""
    learnings: Optional[str] = ""


def cycle_values(b: CycleIn):
    name = (b.name or "").strip()
    if not name:
        bad("Give the cycle a name")
    start, end = day(b.started_on, "start date"), day(b.ended_on, "end date", False)
    if end and end < start:
        bad("End date is before start date")
    return name, start, end, (b.notes or "").strip(), (b.learnings or "").strip()


@app.get("/api/learnings")
def learnings():
    """Every cycle's 'learnings' note, newest first — shown when a new cycle starts."""
    return q("SELECT id, name, started_on, ended_on, learnings FROM cycles WHERE learnings != ''"
             " ORDER BY started_on DESC, id DESC")


@app.get("/api/cycles")
def list_cycles(today: Optional[str] = None):
    today = today if today and store.DATE_RE.match(today) else dt.date.today().isoformat()
    return q("""SELECT c.*,
        (SELECT COUNT(*) FROM attacks a WHERE a.cycle_id = c.id) AS attack_count,
        (SELECT COUNT(*) FROM attacks a WHERE a.cycle_id = c.id AND substr(a.started_at, 1, 10) = ?) AS today_count,
        (SELECT MAX(started_at) FROM attacks a WHERE a.cycle_id = c.id) AS last_attack_at
      FROM cycles c ORDER BY (c.ended_on IS NULL) DESC, c.started_on DESC, c.id DESC""", (today,))


@app.post("/api/cycles")
def create_cycle(b: CycleIn):
    with tx() as c:
        cid = c.execute("INSERT INTO cycles(name, started_on, ended_on, notes, learnings) VALUES(?,?,?,?,?)",
                        cycle_values(b)).lastrowid
    return store.get_cycle(cid)


@app.get("/api/cycles/{cid}")
def get_cycle(cid: int):
    return store.get_cycle(cid) or bad("Cycle not found", 404)


@app.put("/api/cycles/{cid}")
def update_cycle(cid: int, b: CycleIn):
    get_cycle(cid)
    with tx() as c:
        c.execute("UPDATE cycles SET name=?, started_on=?, ended_on=?, notes=?, learnings=? WHERE id=?",
                  (*cycle_values(b), cid))
    return store.get_cycle(cid)


@app.delete("/api/cycles/{cid}")
def delete_cycle(cid: int):
    """Removes the container only; its attacks and entries move to 'outside a cycle'."""
    with tx() as c:
        c.execute("DELETE FROM cycles WHERE id=?", (cid,))
    return {"ok": True}


# ---------------------------------------------------------------- treatments

class TreatmentIn(BaseModel):
    name: str
    category: str = "abortive"
    default_amount: Optional[str] = ""
    uom: Optional[str] = ""
    uom_prefix: bool = False
    quick: bool = False
    archived: bool = False
    sort: int = 0
    max_per_day: Optional[int] = None   # daily dose limit (rolling 24h); None = no limit


def treatment_values(b: TreatmentIn):
    name = (b.name or "").strip()
    if not name:
        bad("Name is required")
    if b.category not in store.CATEGORIES:
        bad("Unknown category")
    if b.max_per_day is not None and b.max_per_day < 1:
        bad("Daily limit must be 1 or more (or blank for none)")
    return (name, b.category, (b.default_amount or "").strip(), (b.uom or "").strip(),
            int(b.uom_prefix), int(b.quick), int(b.archived), b.sort, b.max_per_day)


@app.get("/api/treatments")
def list_treatments(include_archived: bool = False):
    w = "" if include_archived else " WHERE archived = 0"
    return q(f"SELECT * FROM treatments{w} ORDER BY archived, sort, name")


@app.post("/api/treatments")
def create_treatment(b: TreatmentIn):
    with tx() as c:
        tid = c.execute("INSERT INTO treatments(name, category, default_amount, uom, uom_prefix, quick, archived, sort,"
                        " max_per_day) VALUES(?,?,?,?,?,?,?,?,?)", treatment_values(b)).lastrowid
    return q1("SELECT * FROM treatments WHERE id=?", (tid,))


@app.put("/api/treatments/{tid}")
def update_treatment(tid: int, b: TreatmentIn):
    with tx() as c:
        n = c.execute("UPDATE treatments SET name=?, category=?, default_amount=?, uom=?, uom_prefix=?, quick=?,"
                      " archived=?, sort=?, max_per_day=? WHERE id=?", (*treatment_values(b), tid)).rowcount
    if not n:
        bad("Treatment not found", 404)
    return q1("SELECT * FROM treatments WHERE id=?", (tid,))


@app.delete("/api/treatments/{tid}")
def delete_treatment(tid: int):
    """Treatments already used in the log are archived instead, so history and stats keep working."""
    with tx() as c:
        if c.execute("SELECT 1 FROM entries WHERE treatment_id=? LIMIT 1", (tid,)).fetchone():
            c.execute("UPDATE treatments SET archived=1 WHERE id=?", (tid,))
            return {"ok": True, "archived": True}
        c.execute("DELETE FROM treatments WHERE id=?", (tid,))
    return {"ok": True, "archived": False}


# ---------------------------------------------------------------- attacks

class AttackIn(BaseModel):
    cycle_id: Optional[int] = None
    started_at: str
    ended_at: Optional[str] = None
    side: Optional[str] = ""
    locations: list[str] = []
    pain_types: list[str] = []
    notes: Optional[str] = ""
    kip: Optional[int] = None       # optional first pain point
    phase: Optional[str] = None
    note: Optional[str] = ""        # note on that first pain point


class AttackPatch(BaseModel):
    cycle_id: Optional[int] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    side: Optional[str] = None
    locations: Optional[list[str]] = None
    pain_types: Optional[list[str]] = None
    notes: Optional[str] = None


class AttackEnd(BaseModel):
    ended_at: str
    note: Optional[str] = ""


def absorb(c, attack_id):
    """Attach loose entries that fall inside an attack's time window (e.g.
    meds logged from the cycle screen, or an imported text log)."""
    a = c.execute("SELECT * FROM attacks WHERE id=?", (attack_id,)).fetchone()
    end = a["ended_at"] or (store.parse_ts(a["started_at"]) + dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
    c.execute("""UPDATE entries SET attack_id=?, cycle_id=?
                 WHERE attack_id IS NULL AND kind != 'event' AND at >= ? AND at <= ?
                   AND (cycle_id IS ? OR cycle_id IS NULL)""",
              (attack_id, a["cycle_id"], a["started_at"], end, a["cycle_id"]))


def check_cycle(c, cycle_id):
    if cycle_id is not None and not c.execute("SELECT 1 FROM cycles WHERE id=?", (cycle_id,)).fetchone():
        bad("Cycle not found")


def check_side(side):
    side = (side or "").strip()
    if side not in store.SIDES:
        bad("Side must be Left, Right, Both or Alternating")
    return side


@app.get("/api/attacks/active")
def active_attack():
    return store.attack_out(q1("""SELECT a.*, c.name AS cycle_name FROM attacks_v a
        LEFT JOIN cycles c ON c.id = a.cycle_id WHERE a.ended_at IS NULL ORDER BY a.started_at DESC LIMIT 1"""))


@app.get("/api/attacks/last-details")
def last_details():
    """Side/locations/types of the most recent attack, used as defaults for a new one."""
    return store.attack_out(q1("SELECT side, locations, pain_types FROM attacks ORDER BY started_at DESC LIMIT 1")) or {}


@app.post("/api/attacks")
def create_attack(b: AttackIn):
    start, end = ts(b.started_at, "start time"), ts(b.ended_at, "end time", False)
    if end and end < start:
        bad("End time is before start time")
    if b.kip is not None and not 0 <= b.kip <= 10:
        bad("KIP must be 0–10")
    if b.phase and b.phase not in store.PHASES:
        bad("Unknown phase")
    with tx() as c:
        check_cycle(c, b.cycle_id)
        aid = c.execute("INSERT INTO attacks(cycle_id, started_at, ended_at, side, locations, pain_types, notes)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (b.cycle_id, start, end, check_side(b.side), json.dumps(store.str_list(b.locations)),
                         json.dumps(store.str_list(b.pain_types)), (b.notes or "").strip())).lastrowid
        if b.kip is not None:
            c.execute("INSERT INTO entries(kind, at, cycle_id, attack_id, kip, phase, note)"
                      " VALUES('pain',?,?,?,?,?,?)", (start, b.cycle_id, aid, b.kip, b.phase or "shadow",
                                                      (b.note or "").strip()))
        absorb(c, aid)
    weather_async(aid)
    return get_attack(aid)


@app.get("/api/attacks/{aid}")
def get_attack(aid: int):
    a = store.attack_out(q1("""SELECT a.*, c.name AS cycle_name, c.started_on AS cycle_started_on
        FROM attacks_v a LEFT JOIN cycles c ON c.id = a.cycle_id WHERE a.id=?""", (aid,)))
    if not a:
        bad("Attack not found", 404)
    a["entries"] = q("""SELECT e.*, t.category AS category FROM entries e
        LEFT JOIN treatments t ON t.id = e.treatment_id WHERE e.attack_id=? ORDER BY e.at, e.id""", (aid,))
    prev = q1("SELECT weather FROM attacks WHERE weather IS NOT NULL AND (started_at < ? OR (started_at = ? AND id < ?))"
              " ORDER BY started_at DESC, id DESC LIMIT 1", (a["started_at"], a["started_at"], aid))
    a["prev_weather"] = json.loads(prev["weather"]) if prev else None
    a["hints"] = store.history_hints(exclude=aid)
    return a


@app.patch("/api/attacks/{aid}")
def update_attack(aid: int, b: AttackPatch):
    fields = b.model_dump(exclude_unset=True)
    with tx() as c:
        cur = c.execute("SELECT * FROM attacks WHERE id=?", (aid,)).fetchone()
        if not cur:
            bad("Attack not found", 404)
        sets = {}
        if "started_at" in fields:
            sets["started_at"] = ts(fields["started_at"], "start time")
        if "ended_at" in fields:
            sets["ended_at"] = ts(fields["ended_at"], "end time", False)
        start = sets.get("started_at", cur["started_at"])
        end = sets.get("ended_at", cur["ended_at"])
        if end and end < start:
            bad("End time is before start time")
        if "cycle_id" in fields:
            check_cycle(c, fields["cycle_id"])
            sets["cycle_id"] = fields["cycle_id"]
        if "side" in fields:
            sets["side"] = check_side(fields["side"])
        for k in ("locations", "pain_types"):
            if k in fields:
                sets[k] = json.dumps(store.str_list(fields[k]))
        if "notes" in fields:
            sets["notes"] = (fields["notes"] or "").strip()
        if sets.get("started_at", cur["started_at"])[:13] != cur["started_at"][:13]:
            sets["weather"] = None  # different hour -> fetch a fresh snapshot
        if sets:
            c.execute(f"UPDATE attacks SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), aid))
        if "cycle_id" in sets:
            c.execute("UPDATE entries SET cycle_id=? WHERE attack_id=?", (sets["cycle_id"], aid))
        absorb(c, aid)
    if "weather" in sets:
        weather_async(aid)
    return get_attack(aid)


@app.post("/api/attacks/{aid}/end")
def end_attack(aid: int, b: AttackEnd):
    end = ts(b.ended_at, "end time")
    with tx() as c:
        a = c.execute("SELECT * FROM attacks WHERE id=?", (aid,)).fetchone()
        if not a:
            bad("Attack not found", 404)
        if end < a["started_at"]:
            bad("End time is before start time")
        c.execute("UPDATE attacks SET ended_at=? WHERE id=?", (end, aid))
        if (b.note or "").strip():
            c.execute("INSERT INTO entries(kind, at, cycle_id, attack_id, note) VALUES('note',?,?,?,?)",
                      (end, a["cycle_id"], aid, b.note.strip()))
    return get_attack(aid)


@app.delete("/api/attacks/{aid}")
def delete_attack(aid: int):
    with tx() as c:
        c.execute("DELETE FROM attacks WHERE id=?", (aid,))  # entries cascade
    return {"ok": True}


# ---------------------------------------------------------------- entries

class EntryIn(BaseModel):
    kind: str
    at: str
    cycle_id: Optional[int] = None
    attack_id: Optional[int] = None
    kip: Optional[int] = None
    phase: Optional[str] = None
    treatment_id: Optional[int] = None
    amount: Optional[str] = ""
    title: Optional[str] = ""
    note: Optional[str] = ""


def find_attack(c, cycle_id, at):
    """The attack (in the same cycle) whose time window contains `at`.
    Open attacks only count for 24h so a forgotten one doesn't swallow days."""
    day_before = (store.parse_ts(at) - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
    return c.execute("""SELECT id FROM attacks WHERE cycle_id IS ? AND started_at <= ?
        AND (ended_at >= ? OR (ended_at IS NULL AND started_at >= ?))
        ORDER BY started_at DESC LIMIT 1""", (cycle_id, at, at, day_before)).fetchone()


def entry_values(c, b: EntryIn):
    if b.kind not in store.KINDS:
        bad("Unknown entry kind")
    at = ts(b.at)
    cycle_id, attack_id = b.cycle_id, b.attack_id
    if attack_id:
        a = c.execute("SELECT cycle_id FROM attacks WHERE id=?", (attack_id,)).fetchone()
        if not a:
            bad("Attack not found")
        cycle_id = a["cycle_id"]
    else:
        check_cycle(c, cycle_id)
        if b.kind != "event":
            a = find_attack(c, cycle_id, at)
            attack_id = a["id"] if a else None
    v = {"kind": b.kind, "at": at, "cycle_id": cycle_id, "attack_id": attack_id, "kip": None, "phase": None,
         "treatment_id": None, "amount": "", "title": "", "note": (b.note or "").strip()}
    if b.kind == "pain":
        if b.kip is None or not 0 <= b.kip <= 10:
            bad("Pick a KIP level 0–10")
        if b.phase and b.phase not in store.PHASES:
            bad("Unknown phase")
        v.update(kip=b.kip, phase=b.phase or None)
    elif b.kind == "treatment":
        t = c.execute("SELECT * FROM treatments WHERE id=?", (b.treatment_id,)).fetchone()
        if not t:
            bad("Pick a treatment")
        amount = (b.amount or "").strip()
        v.update(treatment_id=t["id"], amount=amount, title=store.dose_label(t, amount))
    elif b.kind == "event":
        title = (b.title or "").strip()
        if not title:
            bad("Give the event a name")
        v["title"] = title
    elif not v["note"]:
        bad("The note is empty")
    return v


def get_entry(eid):
    return q1("""SELECT e.*, t.category AS category FROM entries e
                 LEFT JOIN treatments t ON t.id = e.treatment_id WHERE e.id=?""", (eid,)) or bad("Entry not found", 404)


@app.post("/api/entries")
def create_entry(b: EntryIn):
    with tx() as c:
        v = entry_values(c, b)
        eid = c.execute(f"INSERT INTO entries({', '.join(v)}) VALUES({', '.join('?' * len(v))})",
                        tuple(v.values())).lastrowid
        if v["attack_id"]:  # an earlier pain point moves the attack start back
            c.execute("UPDATE attacks SET started_at=? WHERE id=? AND started_at > ?", (v["at"], v["attack_id"], v["at"]))
    return get_entry(eid)


@app.put("/api/entries/{eid}")
def update_entry(eid: int, b: EntryIn):
    get_entry(eid)
    with tx() as c:
        v = entry_values(c, b)
        c.execute(f"UPDATE entries SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), eid))
        if v["attack_id"]:
            c.execute("UPDATE attacks SET started_at=? WHERE id=? AND started_at > ?", (v["at"], v["attack_id"], v["at"]))
    return get_entry(eid)


@app.delete("/api/entries/{eid}")
def delete_entry(eid: int):
    with tx() as c:
        c.execute("DELETE FROM entries WHERE id=?", (eid,))
    return {"ok": True}


# ---------------------------------------------------------------- journal & stats

@app.get("/api/journal")
def journal(cycle_id: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None):
    attacks, entries = store.load(cycle_id, day(start, required=False), day(end, required=False))
    return {"attacks": attacks, "entries": entries}


@app.get("/api/recent")
def recent(since: str):
    """Last dose of each treatment since `since`, newest first, with counts."""
    rows = q("""SELECT e.treatment_id, e.title, e.at, t.name, t.category, t.max_per_day FROM entries e
                LEFT JOIN treatments t ON t.id = e.treatment_id
                WHERE e.kind='treatment' AND e.at >= ? ORDER BY e.at DESC, e.id DESC""", (ts(since),))
    out = {}
    for r in rows:
        k = r["treatment_id"] or "t:" + r["title"]
        if k not in out:
            out[k] = {"treatment_id": r["treatment_id"], "title": r["title"], "name": r["name"] or r["title"],
                      "category": r["category"], "max_per_day": r["max_per_day"], "last_at": r["at"], "count": 0}
        out[k]["count"] += 1
    return list(out.values())


@app.get("/api/stats")
def stats(cycle_id: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
          today: Optional[str] = None):
    d_from, d_to = day(start, required=False), day(end, required=False)
    attacks, entries = store.load(cycle_id, d_from, d_to)
    cycle = store.get_cycle(int(cycle_id)) if cycle_id and cycle_id.isdigit() else None
    return store.compute_stats(attacks, entries, d_from, d_to, cycle, day(today, required=False))


@app.get("/api/chart/daily.svg")
def chart(cycle_id: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
          theme: str = "dark", meds: str = "key", today: Optional[str] = None):
    d_from, d_to = day(start, required=False), day(end, required=False)
    attacks, entries = store.load(cycle_id, d_from, d_to)
    cycle = store.get_cycle(int(cycle_id)) if cycle_id and cycle_id.isdigit() else None
    s = store.compute_stats(attacks, entries, d_from, d_to, cycle, day(today, required=False))
    svg = reports.daily_svg(attacks, entries, s["start"], s["end"], cycle, theme, meds)
    return Response(svg, media_type="image/svg+xml")


# ---------------------------------------------------------------- reports

@app.get("/api/report")
def report(start: str, end: str, cycle_id: Optional[str] = None,
           fmt: str = Query("text", alias="format"), download: bool = False):
    r = reports.build(start, end, cycle_id)
    name = f"cluster-headache-log_{r['start']}_to_{r['end']}"
    if fmt == "html":
        body, mt, ext = reports.html(r), "text/html; charset=utf-8", "html"
    elif fmt == "csv":
        body, mt, ext = reports.csv_text(r), "text/csv; charset=utf-8", "csv"
    else:
        body, mt, ext = reports.text(r), "text/plain; charset=utf-8", "txt"
    headers = {"Content-Disposition": f'attachment; filename="{name}.{ext}"'} if download else {}
    return Response(body, media_type=mt, headers=headers)


# ---------------------------------------------------------------- settings

FONT_SCALES = ("0.8", "0.9", "1", "1.15")


@app.get("/api/settings")
def get_settings():
    return store.settings_public()


@app.put("/api/settings")
def put_settings(values: dict):
    values = dict(values)
    if "font_scale" in values and str(values["font_scale"]) not in FONT_SCALES:
        bad("Unknown text size")
    for k in ("lat", "lon"):
        if values.get(k) not in (None, ""):
            try:
                float(values[k])
            except (TypeError, ValueError):
                bad(f"Invalid {k}")
    store.set_settings(values)
    if values.get("lat") and values.get("lon"):
        threading.Thread(target=weather.fill_missing, daemon=True).start()
    return store.settings_public()


@app.get("/api/geocode")
def geocode(name: str):
    try:
        return weather.geocode(name)
    except Exception as e:
        raise HTTPException(502, f"Location lookup failed (is the server online?): {e}")


# ---------------------------------------------------------------- backup / restore / import

TABLES = {
    "cycles": ["id", "name", "started_on", "ended_on", "notes", "learnings", "created_at"],
    "treatments": ["id", "name", "category", "default_amount", "uom", "uom_prefix", "quick", "archived", "sort",
                   "max_per_day"],
    "attacks": ["id", "cycle_id", "started_at", "ended_at", "side", "locations", "pain_types", "notes", "weather"],
    "entries": ["id", "kind", "at", "cycle_id", "attack_id", "kip", "phase", "treatment_id", "amount", "title", "note"],
}


@app.get("/api/backup")
def backup_json():
    data = {"app": "clusterlog", "version": APP_VERSION, "exported_at": dt.datetime.now().isoformat(timespec="seconds")}
    for t, cols in TABLES.items():
        data[t] = q(f"SELECT {', '.join(cols)} FROM {t} ORDER BY id")
    data["settings"] = store.settings_raw()
    return Response(json.dumps(data, indent=1, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="clusterlog-backup-{dt.date.today()}.json"'})


@app.post("/api/restore")
async def restore(request: Request):
    try:
        data = await request.json()
    except ValueError:
        bad("That file isn't valid JSON")
    if not isinstance(data, dict) or data.get("app") != "clusterlog":
        bad("That doesn't look like a ClusterLog backup")
    safety = make_backup("pre-restore")
    with tx() as c:
        for t in ("entries", "attacks", "treatments", "cycles"):
            c.execute(f"DELETE FROM {t}")
        for t, cols in TABLES.items():
            for row in data.get(t) or []:
                keys = [k for k in cols if k in row]
                c.execute(f"INSERT INTO {t}({', '.join(keys)}) VALUES({', '.join('?' * len(keys))})",
                          [row[k] for k in keys])
    store.set_settings(data.get("settings") or {})
    return {"ok": True, "safety_backup": safety.name,
            "counts": {t: len(data.get(t) or []) for t in TABLES}}


@app.get("/api/backups")
def list_backups():
    files = sorted(store.BACKUP_DIR.glob("clusterlog-*.db"), reverse=True) if store.BACKUP_DIR.exists() else []
    return [{"name": f.name, "size": f.stat().st_size} for f in files]


@app.post("/api/backups")
def backup_now():
    return {"name": make_backup("manual").name}


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DAY_LINE = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b")
TIME_LINE = re.compile(r"^(\d{1,2}):?(\d{2})\b\s*[-–—:]*\s*(.*)$")
KIP_RE = re.compile(r"\bkip\s*(\d{1,2})", re.I)


def parse_log(text, year):
    """Parse an old free-text log ('Feb 7' day headers, '0035 - woken up'
    lines) into entries. Lines mentioning 'kip N' become pain points."""
    out, errors, cur, prev_month = [], [], None, None
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = TIME_LINE.match(s)
        if m and cur:
            hh, mm, body = int(m.group(1)), int(m.group(2)), m.group(3).strip()
            if hh < 24 and mm < 60:
                kips = [int(k) for k in KIP_RE.findall(body) if int(k) <= 10]
                out.append({"at": f"{cur}T{hh:02d}:{mm:02d}", "kind": "pain" if kips else "note",
                            "kip": max(kips) if kips else None,
                            "phase": "shadow" if "shadow" in body.lower() and not kips else None,
                            "note": body})
                continue
        m = DAY_LINE.match(s)
        if m and m.group(1)[:3].lower() in MONTHS:
            month = MONTHS[m.group(1)[:3].lower()]
            if prev_month and month < prev_month:
                year += 1  # log ran over New Year
            prev_month = month
            try:
                cur = dt.date(year, month, int(m.group(2))).isoformat()
            except ValueError:
                errors.append(s)
            continue
        if out:
            out[-1]["note"] += " " + s  # continuation line
        else:
            errors.append(s)
    for e in out:
        if e["kind"] == "note" and not e["note"]:
            e["note"] = "(no text)"
    return out, errors


class ImportIn(BaseModel):
    text: str
    year: int
    cycle_id: Optional[int] = None
    dry_run: bool = True


@app.post("/api/import/text")
def import_text(b: ImportIn):
    rows, errors = parse_log(b.text, b.year)
    if b.dry_run:
        return {"count": len(rows), "rows": rows[:400], "errors": errors}
    with tx() as c:
        check_cycle(c, b.cycle_id)
        for r in rows:
            a = find_attack(c, b.cycle_id, r["at"])
            c.execute("INSERT INTO entries(kind, at, cycle_id, attack_id, kip, phase, note) VALUES(?,?,?,?,?,?,?)",
                      (r["kind"], r["at"], b.cycle_id, a["id"] if a else None, r["kip"], r["phase"], r["note"]))
    return {"count": len(rows), "errors": errors}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
