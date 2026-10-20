# ClusterLog

A self-hosted, phone-first journal for cluster headaches. Log a headache one tap
at a time while it's happening, fix the details "in the cold light of morning",
and email a clean date-range report to your neurologist.

Black background, white monospace text, big tap targets. Runs in Docker on a
homelab box; all data is one SQLite file you own.

- Full requirements: [REQUIREMENTS.md](REQUIREMENTS.md)
- What's next: [TODO.md](TODO.md)

---

## Install

Needs Docker with the Compose plugin (Debian:
<https://docs.docker.com/engine/install/debian/>).

```bash
cd clusterlog
./install.sh
```

The installer:

1. creates `.env` on first run — picks a free port (default **8765**, skipping
   ports already in use), your timezone, and your user/group id;
2. builds the image and starts the container (`restart: unless-stopped`);
3. waits for the health check and prints the URLs to open.

Re-running `./install.sh` is how you **update** after changing code: it rebuilds
and restarts, and never touches `./data`. If you aren't in the `docker` group the
scripts use `sudo docker` (or run `sudo usermod -aG docker $USER` and log in again).

**On the phone:** open `http://<server-ip>:8765` in Safari → Share → *Add to Home
Screen*. It then opens full-screen like an app.

### First-time setup (Settings screen)

- **Weather location** — search your city (currently **Calgary**); every headache
  then gets a weather snapshot automatically.
- **Your name / neurologist's name and email** — used on reports.
- **Email (SMTP)** — needed for the "Email report" button. For Gmail: host
  `smtp.gmail.com`, port `587`, STARTTLS, your address as username and a Google
  *App Password*. Use "Send test email" to check.
- **Meds & treatments** — a starter list is pre-loaded from the example log; edit,
  archive or add your own (name, category, default amount, unit).

---

## Using it

```
Home ─┬─ Cycle (container: "Fall 2026") ─┬─ Start headache → live Attack screen
      │                                   ├─ + Med / + Note (bottom bar)
      │                                   └─ Journal · Chart · Stats tabs
      ├─ Outside a cycle (injections, appointments between cycles)
      ├─ Cycle learnings
      ├─ Report for neurologist
      └─ Meds & treatments · Settings
```

- **Cycle** — create one when a cycle begins. Days and **weeks are counted from
  the cycle's start** (days 1–7 = week 1), so a cycle running over New Year
  stays in one sequence. Ending a cycle asks for its **learnings**; starting a new
  cycle shows you all past learnings.
The headache flow is three steps:

1. **Start headache** — one form with everything about how it began: time
   (defaults to now), Shadows or Pain onset, KIP (optional), side, location and
   pain type (multi-select, or type your own), note. *Logging a past headache?*
   reveals an end time.
2. **+ Add event** (as many times as needed) → choose:
   - **Pain level** — pick a phase or leave it on *Auto*, then tap the KIP number
     and it's logged. Auto labels shadows → onset → building → subsiding, and
     marks the highest point as *peak* once pain drops.
   - **Medication / treatment** — *Quick* treatments are listed first: one tap
     logs the default dose. Below, pick any treatment and set the dose, or a
     custom event.
   - **Note** — free text, timestamped.
   Each log shows an **Undo / Edit** toast.
3. **End headache** — time (defaults to now) and an optional note; a short
   summary card follows.

The **headache screen** in between shows the live timer, KIP now/peak, how long
your headaches usually last, side/location/type (tap to edit), time since each
dose in the past 24h (with how long after it headaches typically ended), the pain
curve, weather at start (↑/↓ vs. previous headache) and the timeline.
- **Edit anything** — tap any journal row. Times are editable to the minute.
- **Events outside a headache** — *+ Add event* on the cycle (or "Outside a
  cycle") screen → *Medication / treatment* → a treatment (e.g. Emgality 300 mg) or
  *Other / custom event* with your own title, any date/time.
- **Chart tab** — days across, time of day down: ● attack (size = peak KIP) with
  a bar for its duration, ◇ abortive dose, ◆ preventive/emergent dose, plus an
  attacks-per-day strip. Week lines follow cycle weeks.
- **Stats tab** — attacks/day, median/longest length, peak KIP, attack-free days,
  start-time histogram, per-week table, per-treatment "time to attack end".
- **Report** — pick a date range (presets: this cycle, 7/30/90 days) →
  *Email report* (text body + printable HTML + CSV attached), *Open printable
  report* (includes the chart; Share → Print → save as PDF on iPhone), CSV,
  text file, copy, or open in your mail app.
- **Import an old text log** (Settings) — paste Evernote/Docs logs in the
  `Feb 7` / `0042 - start oxygen, kip 6` format. Lines become notes; "kip N"
  lines become pain points. Then create past attacks with start/end times and the
  imported lines inside each window are grouped into them automatically.

---

## Backups & moving to another machine

| What | How |
|---|---|
| Automatic | A daily SQLite snapshot in `data/backups/` (last 30 kept). |
| Manual, on the server | `scripts/backup.sh` → `backups/clusterlog-backup-<stamp>.tar.gz` |
| From the phone | Settings → *Download full backup (JSON)* (everything except the SMTP password) |
| Restore | `scripts/restore.sh <file.tar.gz or .db>`, or Settings → *Restore from a JSON backup* (a safety snapshot is taken first) |
| Move to a new server | `scripts/package.sh --with-data` → copy `dist/clusterlog-*.tar.gz` → `tar xzf … && cd clusterlog && ./install.sh` |
| Remove | `scripts/uninstall.sh` (stops the container, keeps `./data`) |

Everything that matters is `./data/clusterlog.db`. Copying the whole project
folder (with `data/`) to another Docker host and running `./install.sh` also works.

---

## Project spec

### Architecture

```
phone (Safari) ──HTTP──▶ Docker container "clusterlog" (port 8765 → 8000)
                         ├─ uvicorn + FastAPI   app/main.py   JSON API under /api
                         ├─ static SPA          app/static/   index.html, app.js, app.css
                         └─ SQLite (WAL)        /data/clusterlog.db  ← ./data on the host
                              background thread: daily backup + weather back-fill (hourly)
                         ──HTTPS──▶ open-meteo.com (weather + city lookup, no API key)
                         ──SMTP───▶ your mail provider (optional)
```

- **No build step, no Node.** Plain JS front end; Python standard library plus
  FastAPI/uvicorn on the back end. One small image, two Python dependencies.
- **Time model:** every timestamp is a local wall-clock string
  `YYYY-MM-DDTHH:MM` (minute precision), exactly what the phone's picker
  produces. Sorting and range queries are plain string comparisons. Durations
  are computed in Python/JS. (Consequence: a DST change mid-attack can skew that
  one duration by an hour.)
- **No authentication** (by design for a LAN-only homelab). Don't expose it to the
  internet without putting auth in front (see TODO).

### Files

| Path | Purpose |
|---|---|
| `install.sh` | Install / update |
| `scripts/` | `backup.sh`, `restore.sh`, `package.sh`, `uninstall.sh`, shared `lib.sh` |
| `Dockerfile`, `docker-compose.yml`, `.env` | Container build and runtime config |
| `app/main.py` | API routes, email, backup/restore, text-log import, maintenance thread |
| `app/store.py` | Schema, DB helpers, validation, statistics, week grouping |
| `app/reports.py` | Report builder (text / HTML / CSV) and the daily SVG chart |
| `app/weather.py` | Open-Meteo fetch + geocoding |
| `app/static/app.js` | The whole SPA: router, views, bottom sheets, actions |
| `app/static/app.css` | Design tokens and layout (4 type sizes, 8px grid, 48px targets) |

### Data model (SQLite)

| Table | Key columns |
|---|---|
| `cycles` | `name`, `started_on`, `ended_on` (null = active), `notes`, `learnings` |
| `treatments` | `name`, `category` (abortive · preventive · emergent · supplement · other), `default_amount`, `uom`, `uom_prefix` ("level 3"), `quick`, `archived`, `sort` |
| `attacks` | `cycle_id`, `started_at`, `ended_at` (null = in progress), `side`, `locations` (JSON), `pain_types` (JSON), `notes`, `weather` (JSON, read-only) |
| `entries` | `kind` (pain · treatment · note · event), `at`, `cycle_id`, `attack_id`, `kip`, `phase`, `treatment_id`, `amount`, `title` (dose label snapshot, e.g. "Oxygen, 15 L/min"), `note` |
| `settings` | key/value (SMTP, location, patient/neurologist, pain option lists) |
| view `attacks_v` | attacks + `number` (per cycle), `peak_kip`, `last_kip` |

Rules worth knowing:

- An entry logged without an attack but whose time falls inside an attack in the
  same cycle is attached to it automatically. Open attacks only claim 24h.
- Creating or editing an attack pulls in loose entries inside its time window.
- A pain point earlier than its attack's start moves the start back.
- Deleting a treatment that's been used archives it instead. Deleting a cycle
  keeps its attacks/entries (they move to "outside a cycle"). Deleting an attack
  deletes its entries.
- Weather is taken for the hour the attack started; recent dates use Open-Meteo's
  forecast API, older dates its archive API. Missing snapshots are retried hourly.
  Pressure is **barometric pressure reduced to sea level** — the standard figure
  weather reports quote — stored in cmHg (shown everywhere) and kPa (shown on the
  attack screen and in the CSV; Environment Canada's unit). Snapshots carry
  `"basis": "sea-level"`; any without it are cleared at startup and re-fetched.
- Cycle learnings are private: they never appear in reports, CSV or email.

### API (all JSON unless noted)

```
GET  /api/health
GET  /api/cycles?today=  POST /api/cycles   GET|PUT|DELETE /api/cycles/{id}   GET /api/learnings
GET  /api/treatments?include_archived=      POST /api/treatments              PUT|DELETE /api/treatments/{id}
POST /api/attacks   GET /api/attacks/active   GET /api/attacks/last-details
GET|PATCH|DELETE /api/attacks/{id}          POST /api/attacks/{id}/end
POST /api/entries   PUT|DELETE /api/entries/{id}
GET  /api/journal?cycle_id=(id|none)&start=&end=
GET  /api/recent?since=                     GET /api/stats?cycle_id=&start=&end=&today=
GET  /api/chart/daily.svg?cycle_id=&start=&end=&theme=(dark|light)&meds=(key|all|none)
GET  /api/report?start=&end=&cycle_id=&format=(text|html|csv)&download=true
POST /api/report/email
GET|PUT /api/settings   POST /api/settings/test-email   GET /api/geocode?name=
GET  /api/backup (JSON download)   POST /api/restore   GET|POST /api/backups
POST /api/import/text   {text, year, cycle_id, dry_run}
```

### Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r app/requirements.txt
cd app && CLUSTERLOG_DATA=../data-dev ../.venv/bin/uvicorn main:app --reload --port 8799
```

Static files are served from disk, so front-end edits show up on reload. The
Docker image copies the code in at build time, so run `./install.sh` again to
deploy changes.
