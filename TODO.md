# TODO — for subsequent sessions

Status as of 2026-10-19 (late): v1.1.0. Code is in the private GitHub repo
`jzalmanowitz/clusterlog`. `tests/run.sh` (API + phone-size UI walkthrough) passes.
Not yet battle-tested on a real iPhone during a real headache — expect UX tweaks.
Ideas for later (research + QOL proposals) live in IDEAS.md.

**Deploying needs the owner** (Docker requires sudo on this box): after pulling
changes, `sudo /home/jason/projects/clusterlog/install.sh`. Don't cron it — a
rebuild restarts the app and could interrupt logging mid-headache.

## Next up (from the requirements)

- [ ] **Triggers & symptoms (stub).** Owner doesn't track these, but may when
      sharing the app. Plan: two JSON-array columns on `attacks` (`triggers`,
      `symptoms`) mirroring `pain_types`, editable option lists in settings
      (`LIST_SETTINGS` in `app/store.py`), multi-select chips in the start/edit
      headache sheets (`headacheDetailFields` in `app.js`), and a column in the
      CSV/report. Add the columns via a `MIGRATIONS` entry. Ideally a
      Settings toggle to show/hide them so the UI stays lean. Typical options:
      symptoms — tearing eye, runny/blocked nostril, drooping eyelid, restlessness,
      facial sweating, flushing, nausea; triggers — alcohol, nap, strong smells,
      altitude, heat, missed sleep.
- [ ] **iOS app** (later). Cheapest path: keep the web app, wrap with Capacitor or
      ship as a proper PWA once HTTPS exists (see below). Needs offline support +
      sync before a native app makes sense.

## Real-world use: things to watch / likely tweaks

- [ ] Try the start → add event → end flow mid-headache (one-handed, half-awake,
      at night). Too many taps anywhere? Is the start form too long at 3am —
      should side/location/type collapse under "more details"?
- [ ] Auto-phase rules (`autoPhase` in `app.js`) — check they match how attacks
      really unfold; maybe ask for the phase only when ambiguous.
- [ ] "Pain gone" — consider a one-tap "End headache now" (skip the sheet) with
      an Undo toast, like the other quick actions.
- [ ] Oxygen on/off: currently each dose is a point in time. Consider optional
      *duration* treatments (oxygen started 0042, stopped 0058) so the chart can
      draw a bar and stats can use time-on-oxygen.
- [ ] Import: optionally recognise treatment names in imported lines ("oxygen",
      "zomig", "flonase", "T A" → Tylenol + Advil) and create treatment entries
      alongside the note. Careful: "oxygen off", "no zomig", "stopped oxygen" are
      not doses — needs an opt-in checkbox and a preview the owner confirms line by
      line. Maybe a wizard to turn "woken up … pain gone" runs into headaches.
- [ ] Seed sensible daily limits? Deliberately not done — dosing limits are the
      owner's/neurologist's call. Set them under Meds & treatments (e.g. Zomig).

## Platform / ops

- [ ] **HTTPS on the LAN** (e.g. Caddy with an internal CA, or behind the existing
      reverse proxy on :443). Unlocks: service worker/offline mode, "install"
      prompt, Web Share (share the PDF straight to Mail), clipboard API, Wake Lock
      (keep screen on during an attack).
- [ ] **Offline mode**: queue entries in IndexedDB when the server is unreachable
      and sync later (matters if the homelab is down at 2am).
- [ ] Optional auth (single passcode or reverse-proxy auth) before any exposure
      outside the LAN, or before sharing the app with others.
- [ ] Multi-user support if shared out (would need a `users` table and auth).
- [ ] Server-side PDF of the report (currently printable HTML → browser PDF).
- [ ] Off-box backups (e.g. copy `data/backups/` to a NAS on a cron).
## Done

- 2026-10-21 — v1.2: treatments are a *dose* or a *duration* (`treatments.mode`,
  `entries.ended_at`); running sessions with Stop on home/cycle/headache screens,
  optional stop when a headache ends. Existing oxygen / cold compress / e-stim
  entries were back-filled with stop = end of their headache.
- 2026-10-21 — v1.2: Stats → tap a treatment for its full history (one med at a
  time); per-med "Medication log" section in the text/HTML report, CSV gains
  `stopped` / `duration_min`.

- 2026-10-19 — v1.1: plain `.txt` report is the main export; in-app email and
  SMTP settings removed (stored SMTP credentials are deleted on startup).
  "Headache" wording everywhere, report text has no symbols or markup.
- 2026-10-19 — v1.1: text size setting (Small/Medium/Large/Extra large), smaller
  default.
- 2026-10-19 — v1.1: daily dose limits per treatment (`max_per_day`), shown under
  "Since last dose"; logging past the limit asks for confirmation.
- 2026-10-19 — v1.1: pressure change over the 6 hours before each headache.
- 2026-10-19 — v1.1: schema migrations (`MIGRATIONS` in `store.py`), tests in
  `tests/`, project in git + private GitHub repo.
- 2026-10-19 — v1.0.2: start headache → add event (pain / medication / note) →
  end headache flow.

## Decisions log

- 2026-10-19 — Pressure = sea-level barometric (standard reported figure), cmHg +
  kPa. Weather location = Calgary (mountains/chinooks matter; Edmonton doesn't).
- 2026-10-19 — "T A" in old logs = Tylenol + Advil, extra strength → one combined
  quick treatment. (Importer still brings "T A" lines in as notes.)
- 2026-10-19 — Cycle learnings are private; never in reports.
- 2026-10-19 — No email from the app: download a plain .txt and attach it by hand.
  Copy text, CSV and the printable page (with chart) kept as secondary options —
  owner can say if any should go.

## Open questions for the owner

- Seeded treatment list came from the example log (Oxygen, Zomig, Flonase, ice,
  electro-stim, energy drink, Tylenol + Advil, verapamil, psilocybin, Emgality,
  nerve block, vitamin D, B12, magnesium, melatonin). Prune/rename as needed.
- Keep the CSV and printable-page options on the Report screen, or only .txt?
