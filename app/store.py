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

# D3 regimen: name, default_amount, uom, target_min, target_max, target_note, course_days, role
SEED_SUPPLEMENTS = [
    ("Vitamin D3", 10000, "IU", 10000, None, "", None, "d3"),
    ("Omega 3 fish oil", 1000, "mg", 1000, 2400, "at least EPA 360 mg and DHA 240 mg a day", None, ""),
    ("Calcium citrate", 220, "mg", 220, 500, "", None, ""),
    ("Magnesium", 400, "mg", 400, 500, "malate, glycinate or citrate", None, ""),
    ("Vitamin K2 (MK-7)", 200, "mcg", 200, None, "MK-7 preferred for its longer half-life", None, ""),
    ("Vitamin K2 (MK-4)", 1000, "mcg", 1000, None, "", None, ""),
    ("Vitamin A", 900, "mcg", 900, None, "900 mcg (3,000 IU) for men, 700 mcg (2,333 IU) for women", None, ""),
    ("Vitamin B-50", 1, "capsule", 1, None, "three months only; a mature multivitamin covers it after that", 90, ""),
    ("Zinc", 10, "mg", 10, None, "", None, ""),
    ("Boron", 1, "mg", 1, None, "", None, ""),
]
D3_SCHEDULES = {
    "maintenance": "Maintenance only",
    "two_week": "Two-week loading",
    "four_week": "Four-week loading",
}
D3_MAINTENANCE = 10000
D3_LOADING_DOSE = 50000            # four-week schedule: one extra dose a week in weeks 1 and 2
D3_LOAD_DAYS = {"two_week": 13, "four_week": 28}   # last loading day; maintenance starts the day after
SOURCES = ("supplement", "food")
COURSE_GAP_DAYS = 30               # a longer break restarts a supplement's course countdown

SETTING_DEFAULTS = {
    "patient_name": "",
    "neurologist_name": "",
    "lat": "",
    "lon": "",
    "place": "",
    "font_scale": "0.9",
    "theme": "normal",   # normal (white on black) / dim (grey on black) / auto (dim 22:00-07:00)
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
    (7, "ALTER TABLE attacks ADD COLUMN start_phase TEXT"),  # "How did it start?", kept even without a first KIP
    # v1.4: D3 regimen tracker. Supplements are separate from treatments so they never reach the chart,
    # headache timelines or treatment stats.
    (8, """CREATE TABLE IF NOT EXISTS supplements (
           id INTEGER PRIMARY KEY,
           name TEXT NOT NULL,
           default_amount REAL,
           uom TEXT NOT NULL DEFAULT '',
           target_min REAL,                       -- daily target; the day counts as met at or above this
           target_max REAL,
           target_note TEXT NOT NULL DEFAULT '',
           course_days INTEGER,                   -- e.g. B-50: 90 days, counted from the first dose
           role TEXT NOT NULL DEFAULT '',         -- 'd3': daily target comes from the cycle's loading schedule
           archived INTEGER NOT NULL DEFAULT 0,
           sort INTEGER NOT NULL DEFAULT 0)"""),
    (9, """CREATE TABLE IF NOT EXISTS supplement_logs (
           id INTEGER PRIMARY KEY,
           at TEXT NOT NULL,
           cycle_id INTEGER REFERENCES cycles(id) ON DELETE SET NULL,
           note TEXT NOT NULL DEFAULT '')"""),
    (10, """CREATE TABLE IF NOT EXISTS supplement_items (
           id INTEGER PRIMARY KEY,
           log_id INTEGER NOT NULL REFERENCES supplement_logs(id) ON DELETE CASCADE,
           supplement_id INTEGER REFERENCES supplements(id) ON DELETE SET NULL,
           name TEXT NOT NULL,
           amount REAL,
           uom TEXT NOT NULL DEFAULT '',
           source TEXT NOT NULL DEFAULT 'supplement',   -- 'supplement' or 'food'
           loading INTEGER NOT NULL DEFAULT 0)"""),    # four-week schedule's weekly 50,000 IU D3 dose
    (11, "ALTER TABLE cycles ADD COLUMN d3_schedule TEXT"),  # two_week / four_week / maintenance (NULL)
    (12, "CREATE INDEX IF NOT EXISTS idx_supplement_logs_at ON supplement_logs(at)"),
    (13, "CREATE INDEX IF NOT EXISTS idx_supplement_items_log ON supplement_items(log_id)"),
    (14, "ALTER TABLE cycles ADD COLUMN d3_started_on TEXT"),  # loading day 1; NULL = first D3 dose in the cycle
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
            if not c.execute("SELECT value FROM settings WHERE key='supplements_seeded'").fetchone():
                if c.execute("SELECT COUNT(*) FROM supplements").fetchone()[0] == 0:
                    for i, t in enumerate(SEED_SUPPLEMENTS):
                        c.execute("INSERT INTO supplements(name, default_amount, uom, target_min, target_max,"
                                  " target_note, course_days, role, sort) VALUES(?,?,?,?,?,?,?,?,?)", (*t, i * 10))
                c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('supplements_seeded','1')")
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


# ---------------------------------------------------------------- D3 regimen

def fmt_amount(v):
    """10000 -> '10,000' · 2.5 -> '2.5' · None -> ''."""
    if v is None:
        return ""
    v = float(v)
    return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}".rstrip("0").rstrip(".")


def supplement_target(s):
    """'1,000 to 2,400 mg' · '10 mg' · ''."""
    lo, hi, uom = s.get("target_min"), s.get("target_max"), s.get("uom") or ""
    if lo is None and hi is None:
        return ""
    if lo is not None and hi is not None and hi != lo:
        return f"{fmt_amount(lo)} to {fmt_amount(hi)} {uom}".strip()
    return f"{fmt_amount(lo if lo is not None else hi)} {uom}".strip()


def d3_plan(schedule, n):
    """D3 target for day n of a cycle's regimen (day 1 = first D3 dose in the cycle; None = not started yet)."""
    schedule = schedule if schedule in D3_SCHEDULES else "maintenance"
    k = n or 1
    out = {"schedule": schedule, "schedule_label": D3_SCHEDULES[schedule], "day": n, "target": D3_MAINTENANCE,
           "phase": "Maintenance", "weekly_loading": False, "loading_week": None, "until_maintenance": 0}
    load = D3_LOAD_DAYS.get(schedule)
    if not load or k > load:
        return out
    week = (k - 1) // 7 + 1
    out.update(phase=f"Loading week {week}", until_maintenance=load + 1 - k)
    if schedule == "two_week":
        out["target"] = 50000 if week == 1 else 40000
    else:
        out["target"] = 20000 if week <= 2 else 15000
        out.update(weekly_loading=week <= 2, loading_week=week)
    return out


def regimen_starts():
    """cycle id -> day 1 of its loading schedule: the cycle's 'loading started on' date if set,
    else the date of the first D3 dose logged in that cycle."""
    out = {r["cycle_id"]: r["first"] for r in q(
        """SELECT l.cycle_id, MIN(substr(l.at, 1, 10)) AS first FROM supplement_logs l
           JOIN supplement_items i ON i.log_id = l.id JOIN supplements s ON s.id = i.supplement_id
           WHERE s.role = 'd3' AND l.cycle_id IS NOT NULL GROUP BY l.cycle_id""")}
    out.update({r["id"]: r["d3_started_on"] for r in q("SELECT id, d3_started_on FROM cycles WHERE d3_started_on IS NOT NULL")})
    return out


def plan_for(schedule, start, date):
    """d3_plan for a date; days before the loading start (e.g. maintenance doses already taken) count as maintenance."""
    if start and date < start:
        return dict(d3_plan("maintenance", None), phase="Before loading")
    return d3_plan(schedule, regimen_day_n(start, date))


def regimen_day_n(start, date):
    return (dt.date.fromisoformat(date) - dt.date.fromisoformat(start)).days + 1 if start and start <= date else None


def course_windows(course_days):
    """supplement id -> [(start, end)] courses of a limited-time supplement (e.g. B-50 for 90 days).
    Each course starts at the first dose after a break of more than COURSE_GAP_DAYS."""
    out = {}
    rows = q("""SELECT DISTINCT i.supplement_id AS sid, substr(l.at, 1, 10) AS d FROM supplement_items i
                JOIN supplement_logs l ON l.id = i.log_id WHERE i.supplement_id IN (%s) ORDER BY sid, d"""
             % ",".join("?" * len(course_days)), tuple(course_days)) if course_days else []
    last = {}
    for r in rows:
        sid, d = r["sid"], dt.date.fromisoformat(r["d"])
        if sid not in last or (d - last[sid]).days > COURSE_GAP_DAYS:
            out.setdefault(sid, []).append((d, d + dt.timedelta(days=course_days[sid] - 1)))
        last[sid] = d
    return out


def course_state(windows, date):
    """{'start', 'end', 'days_left'} of the course covering `date` (or the last one before it); None if never started."""
    d = dt.date.fromisoformat(date)
    past = [w for w in windows or [] if w[0] <= d]
    if not past:
        return None
    start, end = past[-1]
    return {"start": start.isoformat(), "end": end.isoformat(), "days_left": max(0, (end - d).days + 1)}


def list_supplements(include_archived=True):
    w = "" if include_archived else " WHERE archived = 0"
    return q(f"SELECT * FROM supplements{w} ORDER BY archived, sort, name")


def load_supplement_logs(cycle_id=None, d_from=None, d_to=None, date=None):
    """Supplement logs (each with its items), oldest first. `date` = every log on that day, any cycle."""
    if date:
        w, a = " WHERE substr(at, 1, 10) = ?", [date]
    else:
        w, a = scope(cycle_id, d_from, d_to, "at")
    logs = q(f"SELECT * FROM supplement_logs{w} ORDER BY at, id", a)
    by_id = {l["id"]: dict(l, items=[]) for l in logs}
    if by_id:
        for it in q(f"""SELECT i.*, s.role FROM supplement_items i LEFT JOIN supplements s ON s.id = i.supplement_id
                        WHERE i.log_id IN ({",".join("?" * len(by_id))}) ORDER BY i.id""", tuple(by_id)):
            by_id[it["log_id"]]["items"].append(it)
    return list(by_id.values())


def item_key(it):
    return str(it["supplement_id"]) if it["supplement_id"] else "n:" + it["name"]


def day_totals(logs):
    """date -> item key -> {'name', 'uom', 'total', 'food', 'loading'}."""
    out = {}
    for l in logs:
        for it in l["items"]:
            r = out.setdefault(l["at"][:10], {}).setdefault(item_key(it), {
                "name": it["name"], "uom": it["uom"], "total": 0.0, "food": 0.0, "loading": 0.0})
            amt = it["amount"] or 0
            r["total"] += amt
            if it["source"] == "food":
                r["food"] += amt
            if it["loading"]:
                r["loading"] += amt
    return out


def regimen_today(cycle_id, date, exclude_log=None):
    """What the Track D3 Regimen sheet shows: today's schedule position and running totals against each target."""
    cycle = get_cycle(cycle_id) if cycle_id else None
    start = regimen_starts().get(cycle["id"]) if cycle else None
    plan = plan_for(cycle["d3_schedule"] if cycle else "maintenance", start, date)
    if cycle and not start and plan["schedule"] != "maintenance":
        plan["until_maintenance"] = D3_LOAD_DAYS[plan["schedule"]]
    logs = [l for l in load_supplement_logs(date=date) if l["id"] != exclude_log]
    totals = day_totals(logs).get(date, {})
    if plan["weekly_loading"]:
        ws = (dt.date.fromisoformat(start or date) + dt.timedelta(days=(plan["loading_week"] - 1) * 7)).isoformat()
        we = (dt.date.fromisoformat(ws) + dt.timedelta(days=6)).isoformat()
        plan["loading_taken"] = bool(q1(
            """SELECT 1 FROM supplement_items i JOIN supplement_logs l ON l.id = i.log_id
               WHERE i.loading = 1 AND l.cycle_id IS ? AND substr(l.at, 1, 10) BETWEEN ? AND ? AND l.id IS NOT ?""",
            (cycle_id, ws, we, exclude_log)))
    sups = list_supplements()
    windows = course_windows({s["id"]: s["course_days"] for s in sups if s["course_days"]})
    out = []
    for s in sups:
        t = totals.get(str(s["id"]), {})
        if s["role"] == "d3":
            s = dict(s, target_min=plan["target"], target_max=None)
        taken = t.get("total", 0.0) - (t.get("loading", 0.0) if s["role"] == "d3" else 0)
        course = course_state(windows.get(s["id"]), date) if s["course_days"] else None
        if s["archived"] and not t:
            continue
        out.append({**s, "target": supplement_target(s), "taken": t.get("total", 0.0), "food": t.get("food", 0.0),
                    "met": s["target_min"] is not None and taken >= s["target_min"] - 1e-9,
                    "remaining": max(0.0, (s["target_min"] or 0) - taken), "course": course})
    return {"date": date, "cycle_id": cycle_id, "d3": plan, "supplements": out, "logs": len(logs)}


def regimen_stats(cycle_id, d_from, d_to, today=None, daily=False):
    """Adherence for Stats and the report: per-supplement days at target, and optionally a per-day summary.
    The range runs from the first logged dose in scope (or d_from, if later) to d_to, capped at today."""
    today = today or dt.date.today().isoformat()
    logs = load_supplement_logs(cycle_id, d_from, d_to)
    cycles = {c["id"]: c for c in q("SELECT * FROM cycles")}
    cycle = cycles.get(int(cycle_id)) if cycle_id and str(cycle_id).isdigit() else None
    starts = regimen_starts()
    out = {"schedule": (cycle["d3_schedule"] or "maintenance") if cycle else None, "days": 0, "complete_days": 0,
           "supplements": [], "daily": [], "status": None, "loading_doses": None, "scope": cycle_id,
           "cycle_ids": sorted({l["cycle_id"] for l in logs if l["cycle_id"]})}
    if out["schedule"]:
        out["schedule_label"] = D3_SCHEDULES[out["schedule"]]
        out["started_on"] = starts.get(cycle["id"])
        out["status"] = plan_for(out["schedule"], out["started_on"], min(today, cycle["ended_on"] or today))
    if not logs:
        return out
    first = max(logs[0]["at"][:10], d_from or "")
    last = min(d_to or (cycle and cycle["ended_on"]) or today, today)
    if last < first:
        last = logs[-1]["at"][:10]
    totals = day_totals(logs)
    day_cycle = {}
    for l in logs:
        day_cycle.setdefault(l["at"][:10], l["cycle_id"])
    sups = list_supplements()
    logged = {item_key(it) for l in logs for it in l["items"]}
    rows = [s for s in sups if not s["archived"] or str(s["id"]) in logged]
    known = {str(s["id"]) for s in rows}
    for k in sorted(logged - known):  # supplement deleted since: totals only
        it = next(it for l in logs for it in l["items"] if item_key(it) == k)
        rows.append({"id": None, "name": it["name"], "uom": it["uom"], "target_min": None, "target_max": None,
                     "role": "", "archived": 1, "course_days": None, "key": k})
    windows = course_windows({s["id"]: s["course_days"] for s in rows if s["id"] and s["course_days"]})
    per = {r.get("key") or str(r["id"]): {"name": r["name"], "uom": r["uom"], "role": r["role"], "target": "",
                                          "days_met": 0, "days_taken": 0, "days_expected": 0, "total": 0.0,
                                          "food": 0.0} for r in rows}
    loading = {}
    d0, d1 = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    for i in range((d1 - d0).days + 1 if (d1 - d0).days < 1000 else 0):
        date = (d0 + dt.timedelta(days=i)).isoformat()
        cid = day_cycle.get(date)
        if cid is None and cycle:
            cid = cycle["id"]
        elif cid is None and cycle_id != "none":  # a day with nothing logged: the cycle whose dates cover it
            cid = next((c["id"] for c in cycles.values() if c["started_on"] <= date
                        and (not c["ended_on"] or date <= c["ended_on"])), None)
        c = cycles.get(cid)
        plan = plan_for(c["d3_schedule"] if c else "maintenance", starts.get(cid), date)
        if plan["weekly_loading"] and plan["day"]:
            loading.setdefault((cid, plan["loading_week"]), False)
        day = totals.get(date, {})
        lines, missed = [], []
        for r in rows:
            k = r.get("key") or str(r["id"])
            t = day.get(k)
            p = per[k]
            target = plan["target"] if r["role"] == "d3" else r["target_min"]
            if r["role"] == "d3":
                p["target"] = "per schedule"
            elif target is not None:
                p["target"] = supplement_target(r)
            expected = not r["archived"] and target is not None
            if expected and r["course_days"]:
                cs = course_state(windows.get(r["id"]), date)
                expected = not cs or date <= cs["end"]
            taken = (t["total"] - (t["loading"] if r["role"] == "d3" else 0)) if t else 0
            met = target is not None and taken >= target - 1e-9
            if t:
                p["days_taken"] += 1
                p["total"] += t["total"]
                p["food"] += t["food"]
                if r["role"] == "d3" and t["loading"] and plan["weekly_loading"]:
                    loading[(cid, plan["loading_week"])] = True
            if expected:
                p["days_expected"] += 1
                p["days_met"] += met
                if not met:
                    missed.append(r["name"] if not t else
                                  f"{r['name']} below target ({fmt_amount(taken)} of {fmt_amount(target)} {r['uom']})".strip())
            if t:
                bits = [f"{fmt_amount(t['total'])} {t['uom']}".strip()]
                if t["food"]:
                    bits.append(f"{fmt_amount(t['food'])} from food" if t["food"] < t["total"] else "from food")
                if r["role"] == "d3" and t["loading"]:
                    bits.append("includes weekly loading dose")
                lines.append({"name": r["name"], "text": bits[0] + (f" ({', '.join(bits[1:])})" if bits[1:] else ""),
                              "met": met})
        out["days"] += 1
        out["complete_days"] += not missed
        if daily:
            out["daily"].append({"date": date, "phase": plan["phase"], "d3_target": plan["target"],
                                 "weekly_loading": plan["weekly_loading"], "lines": lines, "missed": missed})
    out["start"], out["end"] = first, last
    out["supplements"] = [dict(v, total=round(v["total"], 2), food=round(v["food"], 2)) for v in per.values()
                          if v["days_taken"] or v["days_expected"]]
    if loading:
        out["loading_doses"] = {"taken": sum(loading.values()), "expected": len(loading)}
    return out
