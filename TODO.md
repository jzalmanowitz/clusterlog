# TODO — for subsequent sessions

Status as of 2026-10-19: v1.0.0 built and tested end-to-end (API script + headless
phone-size browser walkthrough of every screen). Not yet battle-tested on a real
iPhone across a real attack — expect UX tweaks from that.

## Next up (from the requirements)

- [ ] **Report = downloadable plain .txt, no in-app email.** Owner clarified
      (2026-10-19): don't send email from the app. The Report screen should
      produce a plain-text `.txt` file to download and then attach to an email by
      hand — "no markdown or html formatting… just the facts". To do:
      - make *Download .txt* the primary action on the Report screen;
      - remove *Email report* and the SMTP settings (UI, `/api/report/email`,
        `/api/settings/test-email`, `send_mail`, smtp_* settings keys); keep or
        drop *Open in mail app* / *Copy text* per owner;
      - strip decoration from `reports.text()`: no `====`/`----` underlines, no
        `#` bar chart, no `▶ ■ |` symbols, no ↑↓ arrows — plain words, e.g.
        "23:26 Headache 1 started (left side; temple, eye)", "Pressure rising";
      - use "headache" wording to match the app;
      - decide whether the printable HTML/CSV options stay (ask owner);
      - update README (Report section, SMTP setup) and REQUIREMENTS ("export a
        date range to email" → "download a .txt to email").

- [ ] **Triggers & symptoms (stub).** Owner doesn't track these, but may when
      sharing the app. Plan: two JSON-array columns on `attacks` (`triggers`,
      `symptoms`) mirroring `pain_types`, editable option lists in settings
      (`LIST_SETTINGS` in `app/store.py`), chips on the attack screen
      (`detailsHTML` in `app.js`), and a column in the CSV/report. Ideally a
      Settings toggle to show/hide them so the UI stays lean. Typical options:
      symptoms — tearing eye, runny/blocked nostril, drooping eyelid, restlessness,
      facial sweating, flushing, nausea; triggers — alcohol, nap, strong smells,
      altitude, heat, missed sleep.
- [ ] **iOS app** (later). Cheapest path: keep the web app, wrap with Capacitor or
      ship as a proper PWA once HTTPS exists (see below). Needs offline support +
      sync before a native app makes sense.

## Real-world use: things to watch / likely tweaks

- [ ] Try the attack screen mid-attack (one-handed, half-awake, at night). Is the
      KIP grid the right size? Should quick-treat buttons sit above the KIP grid?
- [ ] Auto-phase rules (`autoPhase` in `app.js`) — check they match how attacks
      really unfold; maybe ask for the phase only when ambiguous.
- [ ] "Pain gone" — consider a one-tap "End attack now" (skip the sheet) with an
      Undo toast, like the other quick actions.
- [ ] Oxygen on/off: currently each dose is a point in time. Consider optional
      *duration* treatments (oxygen started 0042, stopped 0058) so the chart can
      draw a bar and stats can use time-on-oxygen.
- [ ] Daily limits: warn when a med passes a per-day maximum (e.g. triptans
      2/day) — add `max_per_day` to treatments, show on "Since last dose".
- [ ] Import: optionally recognise treatment names in imported lines ("oxygen",
      "zomig", "flonase") and create treatment entries instead of notes; maybe a
      wizard to turn "woken up … pain gone" runs into attacks automatically.

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
- [ ] Chart image in the email body (Gmail strips inline SVG; would need PNG
      rendering, e.g. cairosvg).
- [ ] Schema migrations: `PRAGMA user_version` is set to 1; add an ordered
      migration list in `store.init_db()` when the schema next changes
      (`CREATE TABLE IF NOT EXISTS` won't add new columns to an existing DB).
- [ ] Off-box backups (e.g. copy `data/backups/` to a NAS on a cron).
- [ ] Automated tests in the repo (the session used throwaway scripts: an API
      walkthrough and a Playwright phone-size UI walkthrough — worth committing
      as `tests/`).
- [ ] Put the project under git (`git init`; `.gitignore` already excludes data).

## Decisions log

- 2026-10-19 — Pressure = sea-level barometric (standard reported figure), cmHg +
  kPa. Weather location = Calgary (mountains/chinooks matter; Edmonton doesn't).
- 2026-10-19 — "T A" in old logs = Tylenol + Advil, extra strength → one combined
  quick treatment. (Importer still brings "T A" lines in as notes.)
- 2026-10-19 — Cycle learnings are private; never in reports.

## Open questions for the owner

- Seeded treatment list came from the example log (Oxygen, Zomig, Flonase, ice,
  electro-stim, energy drink, Tylenol + Advil, verapamil, psilocybin, Emgality,
  nerve block, vitamin D, B12, magnesium, melatonin). Prune/rename as needed.
- Pressure trend arrows compare with the previous *attack*. With chinooks, a
  "change over the last 3/6/12 h before the attack" figure may be more telling —
  Open-Meteo hourly data makes this cheap to add.
