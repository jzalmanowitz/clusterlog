"""Database access, validation helpers and statistics for ClusterLog.

All timestamps are stored as local wall-clock strings, "YYYY-MM-DDTHH:MM"
(minute precision). That is exactly what the phone's date/time picker
produces, sorts correctly as text, and avoids any timezone surprises.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import statistics
from contextlib import closing, contextmanager
from pathlib import Path

from fastapi import HTTPException

DATA_DIR = Path(os.environ.get("CLUSTERLOG_DATA", "/data"))
DB_PATH = DATA_DIR / "clusterlog.db"
BACKUP_DIR = DATA_DIR / "backups"

PHASES = {
    "shadow": "shadows",
    "onset": "onset",
    "build": "building",
    "peak": "peak",
    "subside": "subsiding",
}
CATEGORIES = {
    "abortive": "Abortive",
    "preventive": "Preventive",
    "emergent": "Emergent / transitional",
    "supplement": "Supplement",
    "other": "Other",
}
KINDS = ("pain", "treatment", "note", "event")
MODES = ("dose", "duration")  # one moment, or started and later stopped (oxygen, cold compress)
SIDES = ("", "Left", "Right", "Both", "Alternating")

DEFAULT_LOCATIONS = ["neck", "jaw", "nose", "sinuses", "eye", "temple", "crown", "cheekbone"]
DEFAULT_PAIN_TYPES = ["pounding", "piercing", "stabbing", "throbbing", "like a knife", "pressure", "woke me up"]

# name, category, default_amount, uom, uom_prefix, quick, mode
SEED_TREATMENTS = [
    ("Oxygen", "abortive", "15", "L/min", 0, 1, "duration"),
    ("Zomig nasal spray", "abortive", "5", "mg", 0, 1, "dose"),
    ("Flonase", "abortive", "", "", 0, 1, "dose"),
    ("Cold compress / ice wrap", "abortive", "", "", 0, 1, "duration"),
    ("Electro-stimulation", "abortive", "3", "level", 1, 1, "duration"),
    ("Energy drink (caffeine)", "abortive", "473", "ml", 0, 1, "dose"),
    ("Tylenol + Advil (extra strength)", "other", "", "", 0, 1, "dose"),
    ("Verapamil", "preventive", "80", "mg", 0, 0, "dose"),
    ("Psilocybin", "preventive", "0.25", "g", 0, 0, "dose"),
    ("Emgality injection", "emergent", "300", "mg", 0, 0, "dose"),
    ("Occipital nerve block", "emergent", "", "", 0, 0, "dose"),
    ("Vitamin D3", "supplement", "10000", "IU", 0, 0, "dose"),
    ("Vitamin B12 (sublingual)", "supplement", "1000", "mcg", 0, 0, "dose"),
    ("Magnesium", "supplement", "", "", 0, 0, "dose"),
    ("Melatonin", "supplement", "2", "mg", 0, 0, "dose"),
]
DURATION_SEEDS = tuple(t[0] for t in SEED_TREATMENTS if t[6] == "duration")

SETTING_DEFAULTS = {
    "patient_name": "",
    "neurologist_name": "",
    "lat": "",
    "lon": "",
    "place": "",
    "font_scale": "0.9",
    "pain_locations": json.dumps(DEFAULT_LOCATIONS),
    "pain_types": json.dumps(DEFAULT_PAIN_TYPES),
}
LIST_SETTINGS = ("pain_locations", "pain_types")
WEATHER_VERSION = 2  # bump to make stored weather snapshots re-fetch (see weather.fetch)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  started_on TEXT NOT NULL,
  ended_on TEXT,
  notes TEXT NOT NULL DEFAULT '',
  learnings TEXT NOT NULL DEFAULT '',   -- "Cluster Cycle Learnings": one note for future me
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS treatments (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'abortive',
  default_amount TEXT NOT NULL DEFAULT '',
  uom TEXT NOT NULL DEFAULT '',
  uom_prefix INTEGER NOT NULL DEFAULT 0,
  quick INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attacks (
  id INTEGER PRIMARY KEY,
  cycle_id INTEGER REFERENCES cycles(id) ON DELETE SET NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  side TEXT NOT NULL DEFAULT '',
  locations TEXT NOT NULL DEFAULT '[]',
  pain_types TEXT NOT NULL DEFAULT '[]',
  -- FUTURE (see TODO.md): triggers / symptoms would be two more
  -- JSON-array columns exactly like pain_types, each with an editable
  -- option list in settings.
  notes TEXT NOT NULL DEFAULT '',
  weather TEXT
);
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('pain','treatment','note','event')),
  at TEXT NOT NULL,
  cycle_id INTEGER REFERENCES cycles(id) ON DELETE SET NULL,
  attack_id INTEGER REFERENCES attacks(id) ON DELETE CASCADE,
  kip INTEGER,
  phase TEXT,
  treatment_id INTEGER REFERENCES treatments(id) ON DELETE SET NULL,
  amount TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_entries_at ON entries(at);
CREATE INDEX IF NOT EXISTS idx_entries_attack ON entries(attack_id);
CREATE INDEX IF NOT EXISTS idx_attacks_start ON attacks(started_at);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

# Ordered schema changes for databases created by an earlier version. SCHEMA
# above is the version-1 baseline; never edit it — add a migration instead.
MIGRATIONS = [
    (2, "ALTER TABLE treatments ADD COLUMN max_per_day INTEGER"),  # daily dose limit, e.g. triptans 2/24h
    (3, "ALTER TABLE treatments ADD COLUMN mode TEXT NOT NULL DEFAULT 'dose'"),
    (4, f"UPDATE treatments SET mode = 'duration' WHERE name IN ({', '.join(repr(n) for n in DURATION_SEEDS)})"),
    (5, "ALTER TABLE entries ADD COLUMN ended_at TEXT"),  # stop time of a duration treatment; NULL = running / unknown
    # sessions logged before 1.2 had no stop time: assume they ran until their headache ended
    (6, """UPDATE entries SET ended_at = (SELECT a.ended_at FROM attacks a WHERE a.id = entries.attack_id)
           WHERE kind = 'treatment' AND ended_at IS NULL
             AND treatment_id IN (SELECT id FROM treatments WHERE mode = 'duration')
             AND (SELECT a.ended_at FROM attacks a WHERE a.id = entries.attack_id) >= at"""),
]

VIEWS = """
DROP VIEW IF EXISTS attacks_v;
CREATE VIEW attacks_v AS
  SELECT a.*,
    ROW_NUMBER() OVER (PARTITION BY a.cycle_id ORDER BY a.started_at, a.id) AS number,
    (SELECT MAX(kip) FROM entries e WHERE e.attack_id = a.id AND e.kind = 'pain') AS peak_kip,
    (SELECT kip FROM entries e WHERE e.attack_id = a.id AND e.kind = 'pain'
       ORDER BY e.at DESC, e.id DESC LIMIT 1) AS last_kip
  FROM attacks a;
"""

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------- db helpers

def connect():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


@contextmanager
def tx():
    c = connect()
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def q(sql, args=()):
    with closing(connect()) as c:
        return [dict(r) for r in c.execute(sql, args)]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        version = c.execute("PRAGMA user_version").fetchone()[0] or 1
        for v, sql in MIGRATIONS:
            if version < v:
                with c:
                    c.execute(sql)
                    c.execute(f"PRAGMA user_version={v}")
                version = v
        c.executescript(VIEWS)
        with c:
            seeded = c.execute("SELECT value FROM settings WHERE key='seeded'").fetchone()
            if not seeded:
                if c.execute("SELECT COUNT(*) FROM treatments").fetchone()[0] == 0:
                    for i, t in enumerate(SEED_TREATMENTS):
                        c.execute(
                            "INSERT INTO treatments(name,category,default_amount,uom,uom_prefix,quick,mode,sort)"
                            " VALUES(?,?,?,?,?,?,?,?)", (*t, i * 10))
                c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('seeded','1')")
            # v1.1: in-app email removed — drop stored SMTP credentials
            c.execute("DELETE FROM settings WHERE key LIKE 'smtp_%' OR key = 'recipient'")
            # re-fetch weather snapshots from older formats (v1.0.1 sea-level pressure, v1.1 6-hour trend)
            c.execute("UPDATE attacks SET weather = NULL WHERE weather IS NOT NULL"
                      " AND IFNULL(json_extract(weather, '$.v'), 1) < ?", (WEATHER_VERSION,))


# ---------------------------------------------------------------- validation

def bad(msg, code=400):
    raise HTTPException(code, msg)


def ts(v, field="time", required=True):
    """Normalise a local timestamp to 'YYYY-MM-DDTHH:MM'."""
    if v in (None, ""):
        if required:
            bad(f"{field} is required")
        return None
    v = str(v).strip().replace(" ", "T")
    if not TS_RE.match(v):
        bad(f"Invalid {field}: {v}")
    try:
        dt.datetime.strptime(v[:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        bad(f"Invalid {field}: {v}")
    return v[:16]


def day(v, field="date", required=True):
    if v in (None, ""):
        if required:
            bad(f"{field} is required")
        return None
    v = str(v).strip()[:10]
    try:
        dt.date.fromisoformat(v)
    except ValueError:
        bad(f"Invalid {field}: {v}")
    return v


def parse_ts(s):
    return dt.datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")


def minutes(a, b):
    return int((parse_ts(b) - parse_ts(a)).total_seconds() // 60)


def fmt_dur(m):
    if m is None:
        return "–"
    h, mm = divmod(max(0, int(round(m))), 60)
    return f"{h}h{mm:02d}m" if h else f"{mm}m"


def str_list(v):
    """Clean a list of free-text tags: trimmed, de-duplicated, order kept."""
    out, seen = [], set()
    for x in v or []:
        x = str(x).strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x[:60])
    return out


# ---------------------------------------------------------------- settings

def settings_raw():
    s = dict(SETTING_DEFAULTS)
    for r in q("SELECT key, value FROM settings"):
        s[r["key"]] = r["value"]
    return s


def settings_public():
    s = settings_raw()
    out = {k: s[k] for k in SETTING_DEFAULTS}
    for k in LIST_SETTINGS:
        try:
            out[k] = json.loads(s[k])
        except (TypeError, ValueError):
            out[k] = json.loads(SETTING_DEFAULTS[k])
    return out


def set_settings(values: dict):
    with tx() as c:
        for k, v in values.items():
            if k not in SETTING_DEFAULTS:
                continue
            if k in LIST_SETTINGS:
                if isinstance(v, str):  # backups store these as JSON text
                    try:
                        v = json.loads(v)
                    except ValueError:
                        v = v.splitlines()
                v = json.dumps(str_list(v if isinstance(v, list) else []))
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v if v is not None else "")))


# ---------------------------------------------------------------- formatting

def dose_label(t, amount):
    """'Oxygen, 15 L/min' · 'Electro-stimulation, level 3' · 'Cold compress'."""
    amount = (amount or "").strip()
    uom = (t["uom"] or "").strip()
    if not amount:
        return t["name"]
    if not uom:
        return f"{t['name']}, {amount}"
    return f"{t['name']}, {uom} {amount}" if t["uom_prefix"] else f"{t['name']}, {amount} {uom}"


def attack_out(r):
    if r is None:
        return None
    for k in ("locations", "pain_types"):
        try:
            r[k] = json.loads(r.get(k) or "[]")
        except ValueError:
            r[k] = []
    try:
        r["weather"] = json.loads(r["weather"]) if r.get("weather") else None
    except ValueError:
        r["weather"] = None
    return r


# ---------------------------------------------------------------- loading

def scope(cycle_id, d_from, d_to, col):
    where, args = [], []
    if cycle_id == "none":
        where.append("cycle_id IS NULL")
    elif cycle_id not in (None, "", "all"):
        try:
            args.append(int(cycle_id))
        except ValueError:
            bad("Invalid cycle")
        where.append("cycle_id = ?")
    if d_from:
        where.append(f"{col} >= ?")
        args.append(d_from + "T00:00")
    if d_to:
        where.append(f"{col} <= ?")
        args.append(d_to + "T23:59")
    return (" WHERE " + " AND ".join(where)) if where else "", args


def load(cycle_id=None, d_from=None, d_to=None):
    w, a = scope(cycle_id, d_from, d_to, "started_at")
    attacks = [attack_out(r) for r in q(f"SELECT * FROM attacks_v{w} ORDER BY started_at, id", a)]
    w, a = scope(cycle_id, d_from, d_to, "at")
    entries = q(f"SELECT e.*, t.category AS category, t.mode AS mode FROM entries e "
                f"LEFT JOIN treatments t ON t.id = e.treatment_id"
                f"{w.replace('cycle_id', 'e.cycle_id')} ORDER BY at, e.id", a)
    return attacks, entries


def get_cycle(cid):
    return q1("SELECT * FROM cycles WHERE id=?", (cid,))


def cycle_week(cycle_started_on, date):
    """Week number within a cycle: days 1-7 are week 1, 8-14 week 2, ..."""
    d = (dt.date.fromisoformat(date) - dt.date.fromisoformat(cycle_started_on)).days
    return d // 7 + 1


def week_key(cycle, date):
    """(sort_key, label) for grouping a date into a cycle week or, outside a
    cycle, a Monday-based calendar week."""
    d = dt.date.fromisoformat(date)
    if cycle:
        start = dt.date.fromisoformat(cycle["started_on"])
        n = (d - start).days // 7 + 1
        if n >= 1:
            ws = start + dt.timedelta(days=(n - 1) * 7)
            we = ws + dt.timedelta(days=6)
            return (f"c{cycle['id']}-{n:04d}", f"Week {n} ({ws:%d %b} to {we:%d %b %Y})")
    ws = d - dt.timedelta(days=d.weekday())
    we = ws + dt.timedelta(days=6)
    return (f"w{ws.isoformat()}", f"Calendar week {ws:%d %b} to {we:%d %b %Y}")


# ---------------------------------------------------------------- statistics

def summarize(v):
    v = [x for x in v if x is not None]
    if not v:
        return {"n": 0, "median": None, "mean": None, "min": None, "max": None, "p25": None, "p75": None}
    out = {"n": len(v), "median": round(statistics.median(v)), "mean": round(statistics.mean(v)),
           "min": min(v), "max": max(v), "p25": None, "p75": None}
    if len(v) >= 4:
        qs = statistics.quantiles(v, n=4)
        out["p25"], out["p75"] = round(qs[0]), round(qs[2])
    return out


def compute_stats(attacks, entries, d_from=None, d_to=None, cycle=None, today=None):
    today = today or dt.date.today().isoformat()
    dates = [a["started_at"][:10] for a in attacks] + [e["at"][:10] for e in entries]
    if d_from:
        first = d_from
    elif cycle:
        first = cycle["started_on"]
    else:
        first = min(dates) if dates else today
    if d_to:
        last = d_to
    elif cycle:
        last = cycle["ended_on"] or max([today] + dates)
    else:
        last = max(dates) if dates else today
    if last < first:
        last = first
    d0, d1 = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    ndays = (d1 - d0).days + 1

    counts = {}
    for a in attacks:
        counts[a["started_at"][:10]] = counts.get(a["started_at"][:10], 0) + 1
    attack_days = len([d for d in counts if first <= d <= last])

    ended = [a for a in attacks if a["ended_at"]]
    durs = [minutes(a["started_at"], a["ended_at"]) for a in ended]
    peaks = [a["peak_kip"] for a in attacks if a["peak_kip"] is not None]
    by_hour = [0] * 24
    for a in attacks:
        by_hour[int(a["started_at"][11:13])] += 1

    tinfo = {t["id"]: t for t in q("SELECT id, name, category, mode FROM treatments")}
    by_id = {a["id"]: a for a in attacks}
    tre, seen = {}, set()
    for e in entries:
        if e["kind"] != "treatment":
            continue
        key = e["treatment_id"] or ("t:" + e["title"])
        t = tinfo.get(e["treatment_id"])
        r = tre.setdefault(key, {"key": str(key), "treatment_id": e["treatment_id"],
                                 "name": t["name"] if t else e["title"],
                                 "category": t["category"] if t else "other",
                                 "mode": t["mode"] if t else "dose",
                                 "uses": 0, "in_attacks": 0, "to_end": [], "sessions": []})
        r["uses"] += 1
        if e.get("ended_at"):
            r["sessions"].append(max(0, minutes(e["at"], e["ended_at"])))
        a = by_id.get(e["attack_id"])
        if a:
            r["in_attacks"] += 1
            if a["ended_at"] and (a["id"], key) not in seen:  # entries are time-ordered: first dose
                seen.add((a["id"], key))
                r["to_end"].append(max(0, minutes(e["at"], a["ended_at"])))
    treatments = sorted(
        ({**r, "to_end": summarize(r["to_end"]), "session": summarize(r["sessions"]),
          "total_min": sum(r.pop("sessions"))} for r in tre.values()),
        key=lambda r: (-r["uses"], r["name"]))

    # weekly table (cycle weeks when scoped to a cycle, else calendar weeks)
    weeks = {}

    def week(date):
        k, label = week_key(cycle, date)
        return weeks.setdefault(k, {"label": label, "attacks": 0, "meds": 0, "durations": [], "peaks": []})

    for i in range(0, ndays if ndays <= 1000 else 0):
        week((d0 + dt.timedelta(days=i)).isoformat())  # include empty weeks
    for a in attacks:
        w = week(a["started_at"][:10])
        w["attacks"] += 1
        if a["ended_at"]:
            w["durations"].append(minutes(a["started_at"], a["ended_at"]))
        if a["peak_kip"] is not None:
            w["peaks"].append(a["peak_kip"])
    for e in entries:
        if e["kind"] == "treatment":
            week(e["at"][:10])["meds"] += 1
    week_list = []
    for k in sorted(weeks):
        w = weeks[k]
        week_list.append({"label": w["label"], "attacks": w["attacks"], "meds": w["meds"],
                          "median_duration": summarize(w["durations"])["median"],
                          "max_kip": max(w["peaks"]) if w["peaks"] else None})

    return {
        "start": first, "end": last, "days": ndays,
        "attacks": len(attacks), "ended": len(ended),
        "per_day_avg": round(len(attacks) / ndays, 2) if ndays else 0,
        "attack_days": attack_days, "free_days": max(0, ndays - attack_days),
        "duration": summarize(durs),
        "peak": {"mean": round(statistics.mean(peaks), 1) if peaks else None,
                 "max": max(peaks) if peaks else None},
        "by_hour": by_hour,
        "per_day": [{"date": (d0 + dt.timedelta(days=i)).isoformat(),
                     "count": counts.get((d0 + dt.timedelta(days=i)).isoformat(), 0)}
                    for i in range(ndays)] if ndays <= 400 else [],
        "weeks": week_list,
        "treatments": treatments,
    }


def med_log(attacks, entries):
    """Every use of each treatment, oldest first, keyed like compute_stats rows
    (str(treatment_id), or 't:<title>' for a treatment that no longer exists)."""
    by_id = {a["id"]: a for a in attacks}
    out = {}
    for e in entries:
        if e["kind"] != "treatment":
            continue
        a = by_id.get(e["attack_id"])
        out.setdefault(str(e["treatment_id"] or "t:" + e["title"]), []).append({
            "id": e["id"], "kind": "treatment", "treatment_id": e["treatment_id"], "cycle_id": e["cycle_id"],
            "at": e["at"], "ended_at": e.get("ended_at"), "mode": e.get("mode") or "dose",
            "amount": e["amount"], "title": e["title"], "note": e["note"],
            "attack_id": e["attack_id"], "attack_number": a["number"] if a else None,
            "length": max(0, minutes(e["at"], e["ended_at"])) if e.get("ended_at") else None,
            "to_end": max(0, minutes(e["at"], a["ended_at"])) if a and a["ended_at"] else None})
    return out


def history_hints(exclude=None):
    """Historical medians used on the live attack screen: how long attacks
    usually last, and how long after each treatment they usually end."""
    done = q("SELECT started_at, ended_at FROM attacks WHERE ended_at IS NOT NULL AND id IS NOT ?", (exclude,))
    rows = q("""SELECT e.attack_id, e.treatment_id, MIN(e.at) AS first_at, a.ended_at
                FROM entries e JOIN attacks a ON a.id = e.attack_id
                WHERE e.kind='treatment' AND e.treatment_id IS NOT NULL
                  AND a.ended_at IS NOT NULL AND a.id IS NOT ?
                GROUP BY e.attack_id, e.treatment_id""", (exclude,))
    per = {}
    for r in rows:
        per.setdefault(r["treatment_id"], []).append(max(0, minutes(r["first_at"], r["ended_at"])))
    return {
        "duration": summarize([minutes(a["started_at"], a["ended_at"]) for a in done]),
        "treatments": {str(k): summarize(v) for k, v in per.items()},
    }
