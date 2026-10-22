"""Neurologist reports (text / HTML / CSV) and the daily SVG chart."""
import csv
import datetime as dt
import io
import json
from html import escape

import store
from store import PHASES, fmt_dur, minutes

CAT_WORDS = {k: v.lower() for k, v in store.CATEGORIES.items()}
TAGS = {"pain": "Pain", "treatment": "Med", "note": "Note", "event": "Event", "start": "Start", "end": "End"}
KEY_MED_CATEGORIES = ("abortive", "preventive", "emergent")


def fmt_date(d):
    return dt.date.fromisoformat(d[:10]).strftime("%a %d %b %Y")


def hhmm(at):
    return at[11:16]


def fmt_mins(m):
    """Plain duration: '36 min', '1 h 05 min'."""
    if m is None:
        return "n/a"
    h, mm = divmod(max(0, int(round(m))), 60)
    return f"{h} h {mm:02d} min" if h else f"{mm} min"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def weather_text(w, prev=None):
    """'6.7 C, humidity 52%, pressure 75.47 cmHg (100.62 kPa), falling since previous headache'."""
    if not w:
        return ""
    s = f"{w['temp_c']:.1f} C, humidity {w['humidity']:.0f}%, pressure {w['pressure_cmhg']:.2f} cmHg"
    if w.get("pressure_kpa") is not None:
        s += f" ({w['pressure_kpa']:.2f} kPa)"
    if prev and prev.get("pressure_cmhg") is not None:
        d = w["pressure_cmhg"] - prev["pressure_cmhg"]
        trend = "rising" if d > 0.005 else "falling" if d < -0.005 else "steady"
        s += f", {trend} since previous headache ({d:+.2f} cmHg)"
    if w.get("pressure_change_6h_cmhg") is not None:
        s += f", change over the 6 hours before: {w['pressure_change_6h_cmhg']:+.2f} cmHg"
    return s


def prev_weather_map(attacks):
    """attack id -> weather of the previous attack (any cycle) that had one."""
    rows = store.q("SELECT id, weather FROM attacks WHERE weather IS NOT NULL ORDER BY started_at, id")
    last, out = None, {}
    for r in rows:
        out[r["id"]] = last
        last = json.loads(r["weather"])
    return out


# ---------------------------------------------------------------- report data

def build(d_from, d_to, cycle_id=None):
    d_from, d_to = store.day(d_from, "start date"), store.day(d_to, "end date")
    if d_to < d_from:
        store.bad("End date is before start date")
    attacks, entries = store.load(cycle_id, d_from, d_to)
    cycles = {c["id"]: c for c in store.q("SELECT * FROM cycles")}
    cycle = cycles.get(int(cycle_id)) if cycle_id and str(cycle_id).isdigit() else None
    used = {a["cycle_id"] for a in attacks} | {e["cycle_id"] for e in entries}

    def covering(d, cid):
        """Cycle used for week numbering: the item's own, else one whose dates contain the day."""
        if cid in cycles:
            return cycles[cid]
        for c in cycles.values():
            if c["started_on"] <= d and (not c["ended_on"] or d <= c["ended_on"]):
                return c
        return None

    stats_cycle = cycle or (cycles.get(next(iter(used - {None}))) if len(used - {None}) == 1 else None)
    stats = store.compute_stats(attacks, entries, d_from, d_to, stats_cycle)
    prev_w = prev_weather_map(attacks)
    log = store.med_log(attacks, entries)

    items = []
    for a in attacks:
        items.append((a["started_at"], 0, a["id"], "start", a))
        if a["ended_at"]:
            items.append((a["ended_at"], 2, a["id"], "end", a))
    for e in entries:
        items.append((e["at"], 1, e["id"], "entry", e))
    items.sort(key=lambda x: x[:3])

    weeks = []
    for at, _, _, typ, obj in items:
        d = at[:10]
        c = cycles.get(obj["cycle_id"])
        wk, wlabel = store.week_key(covering(d, obj["cycle_id"]), d)
        if not weeks or weeks[-1]["key"] != wk:
            weeks.append({"key": wk, "label": wlabel, "days": []})
        days = weeks[-1]["days"]
        if not days or days[-1]["date"] != d:
            days.append({"date": d, "label": fmt_date(d), "cycle_label": "", "attacks": 0, "lines": []})
        dd = days[-1]
        if c and not dd["cycle_label"]:
            dd["cycle_label"] = f"{c['name']}, day {(dt.date.fromisoformat(d) - dt.date.fromisoformat(c['started_on'])).days + 1}"
        if typ == "start":
            dd["attacks"] += 1
        dd["lines"].append(line(at, typ, obj, prev_w))

    s = store.settings_raw()
    return {
        "start": d_from, "end": d_to,
        "patient": s["patient_name"], "neurologist": s["neurologist_name"],
        "place": s["place"],
        "cycles": [cycles[c] for c in sorted(used, key=lambda x: cycles[x]["started_on"] if x in cycles else "")
                   if c in cycles],
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": stats, "weeks": weeks,
        "meds": [{"name": t["name"], "category": t["category"], "mode": t["mode"], "days": med_days(t["name"], log.get(t["key"], []))}
                 for t in stats["treatments"]],
        "attacks": attacks, "entries": entries, "cycle": stats_cycle,
    }


def session_text(e):
    """', 00:42 to 01:01 (19 min)' for a duration treatment; '' for a dose."""
    if e.get("mode") != "duration":
        return ""
    if not e.get("ended_at"):
        return ", no stop time recorded"
    return f", {hhmm(e['at'])} to {hhmm(e['ended_at'])} ({fmt_mins(minutes(e['at'], e['ended_at']))})"


def med_days(name, doses):
    """One medication's uses grouped by day: [{'date', 'label', 'uses': ['00:42 (15 L/min, 19 min, headache 3)']}]."""
    out = []
    for d in doses:
        bits = []
        if d["amount"]:  # the dose part of 'Oxygen, 15 L/min' (raw amount if the med was renamed since)
            bits.append(d["title"][len(name) + 2:] if d["title"].startswith(name + ", ") else d["amount"])
        if d["mode"] == "duration":
            bits.append(fmt_mins(d["length"]) if d["length"] is not None else "no stop time")
        if d["attack_number"]:
            bits.append(f"headache {d['attack_number']}")
        use = hhmm(d["at"]) + (f" ({', '.join(bits)})" if bits else "")
        if not out or out[-1]["date"] != d["at"][:10]:
            out.append({"date": d["at"][:10], "label": fmt_date(d["at"]), "uses": []})
        out[-1]["uses"].append(use)
    return out


def line(at, typ, o, prev_w):
    """One log line as plain words: {'time', 'type', 'tag', 'text', 'weather', 'in'}."""
    if typ == "start":
        bits = [f"Headache {o['number']} started."]
        if o["side"]:
            bits.append(f"{o['side']} side.")
        if o["locations"]:
            bits.append(f"Location: {', '.join(o['locations'])}.")
        if o["pain_types"]:
            bits.append(f"Type: {', '.join(o['pain_types'])}.")
        if o["notes"]:
            bits.append(o["notes"].strip())
        return {"time": hhmm(at), "type": "start", "tag": TAGS["start"], "text": " ".join(bits),
                "weather": weather_text(o["weather"], prev_w.get(o["id"])), "in": True}
    if typ == "end":
        text = f"Headache {o['number']} ended. Lasted {fmt_mins(minutes(o['started_at'], o['ended_at']))}."
        if o["peak_kip"] is not None:
            text += f" Peak KIP {o['peak_kip']}."
        return {"time": hhmm(at), "type": "end", "tag": TAGS["end"], "text": text, "weather": "", "in": True}
    e = o
    note = (e["note"] or "").strip()
    if e["kind"] == "pain":
        text = f"Pain KIP {e['kip']}" + (f", {PHASES.get(e['phase'], e['phase'])}" if e["phase"] else "")
    elif e["kind"] == "treatment":
        text = f"Medication: {e['title']}{session_text(e)}"
    elif e["kind"] == "event":
        text = f"Event: {e['title']}"
    else:
        text, note = f"Note: {note}", ""
    if note:
        text += f". {note}"
    return {"time": hhmm(at), "type": e["kind"], "tag": TAGS[e["kind"]], "text": text,
            "weather": "", "in": bool(e["attack_id"])}


# ---------------------------------------------------------------- renderers

def _summary_lines(r):
    s = r["stats"]
    du, pk = s["duration"], s["peak"]
    out = [("Headaches", f"{s['attacks']} ({s['per_day_avg']} per day). Days with headaches: {s['attack_days']}. "
                         f"Headache-free days: {s['free_days']} of {s['days']}.")]
    if du["n"]:
        iqr = f" Middle half: {fmt_mins(du['p25'])} to {fmt_mins(du['p75'])}." if du["p25"] is not None else ""
        out.append(("Duration", f"median {fmt_mins(du['median'])}, mean {fmt_mins(du['mean'])}, shortest "
                                f"{fmt_mins(du['min'])}, longest {fmt_mins(du['max'])} "
                                f"({plural(du['n'], 'finished headache')}).{iqr}"))
    if pk["max"] is not None:
        out.append(("Peak pain", f"average KIP {pk['mean']}, highest KIP {pk['max']}."))
    return out


def _hour_buckets(by_hour):
    return [(f"{i:02d}:00-{i + 3:02d}:00", sum(by_hour[i:i + 3])) for i in range(0, 24, 3)]


def _treat_line(t):
    s = f"used {plural(t['uses'], 'time')}"
    if t["mode"] == "duration" and t["session"]["n"]:
        s += (f" (median session {fmt_mins(t['session']['median'])}, "
              f"total {fmt_mins(t['total_min'])})")
    if t["in_attacks"]:
        s += f", {t['in_attacks']} during headaches"
    te = t["to_end"]
    if te["n"]:
        s += (f"; headache ended a median {fmt_mins(te['median'])} after the first dose "
              f"({plural(te['n'], 'headache')})")
    return s + "."


def text(r):
    """The plain-text report: no markup or symbols, just the facts, ready to attach to an email."""
    s = r["stats"]
    L = ["Cluster headache log", ""]
    if r["patient"]:
        L.append(f"Patient: {r['patient']}")
    if r["neurologist"]:
        L.append(f"Prepared for: {r['neurologist']}")
    L.append(f"Period: {fmt_date(r['start'])} to {fmt_date(r['end'])} ({s['days']} days)")
    for c in r["cycles"]:
        L.append(f"Cycle: {c['name']}, began {fmt_date(c['started_on'])}, "
                 + (f"ended {fmt_date(c['ended_on'])}" if c["ended_on"] else "ongoing"))
    L.append(f"Prepared: {r['generated']}")
    L.append("Pain is on the KIP scale from 0 to 10. Times are local, 24-hour clock.")
    if r["place"]:
        L.append(f"Weather is recorded for {r['place']} at the hour each headache started; "
                 "pressure is barometric, reduced to sea level.")
    L += ["", "Summary", ""]
    for k, v in _summary_lines(r):
        L.append(f"{k}: {v}")
    if s["attacks"]:
        busy = [f"{label} {c}" for label, c in _hour_buckets(s["by_hour"]) if c]
        L.append("Start times: " + "; ".join(busy) + ".")
    if s["weeks"]:
        L += ["", "By week:"]
        for w in s["weeks"]:
            extra = f", median length {fmt_mins(w['median_duration'])}" if w["median_duration"] is not None else ""
            extra += f", highest KIP {w['max_kip']}" if w["max_kip"] is not None else ""
            L.append(f"{w['label']}: {plural(w['attacks'], 'headache')}, {plural(w['meds'], 'dose')}{extra}.")
    if s["treatments"]:
        L += ["", "Treatments:"]
        for t in s["treatments"]:
            L.append(f"{t['name']}: {_treat_line(t)}")
    if r["meds"]:
        L += ["", "Medication log", "",
              "Each time a medication or treatment was used, grouped by medication. "
              "Session lengths are shown for treatments with a start and stop time."]
        for m in r["meds"]:
            L += ["", f"{m['name']} ({CAT_WORDS.get(m['category'], m['category'])})"]
            for d in m["days"]:
                L.append(f"{d['label']}: {'; '.join(d['uses'])}")
    L += ["", "Daily log"]
    if not r["weeks"]:
        L += ["", "Nothing was logged in this period."]
    for w in r["weeks"]:
        L += ["", w["label"]]
        for d in w["days"]:
            head = d["label"]
            if d["cycle_label"]:
                head += f", {d['cycle_label']}"
            if d["attacks"]:
                head += f", {plural(d['attacks'], 'headache')}"
            L += ["", head]
            for l in d["lines"]:
                L.append(f"{l['time']} {l['text']}")
                if l["weather"]:
                    L.append(f"{l['time']} Weather: {l['weather']}.")
    L += ["", "End of log."]
    return "\n".join(L) + "\n"


HTML_CSS = """
body{font-family:Consolas,"SF Mono",Menlo,"DejaVu Sans Mono",monospace;color:#000;background:#fff;
 max-width:860px;margin:24px auto;padding:0 16px;font-size:13px;line-height:1.45}
h1{font-size:20px;margin:0 0 8px}h2{font-size:15px;border-bottom:2px solid #000;margin:28px 0 8px;padding-bottom:2px}
h3{font-size:14px;margin:22px 0 4px}h4{font-size:13px;margin:14px 0 2px;background:#eee;padding:4px 6px}
table{border-collapse:collapse;width:100%}td,th{padding:2px 6px;vertical-align:top;text-align:left}
.meta td:first-child{font-weight:bold;width:110px}.log td.t{width:44px;white-space:nowrap}
.log td.g{width:52px;color:#444;font-size:11px;padding-top:4px}.log tr.in td.t{border-left:3px solid #000}
.log tr.start td,.log tr.end td{font-weight:bold}.w{color:#333;font-weight:normal;font-size:11px}
.bar{display:inline-block;height:9px;background:#000;vertical-align:middle}.muted{color:#555}
.chart{overflow-x:auto;margin:8px 0}.chart svg{max-width:none}
.stats td{border-bottom:1px solid #ddd}
@media print{body{margin:0;max-width:none}h4{break-after:avoid}.chart{overflow:visible}}
"""


def html(r, include_chart=True):
    e = escape
    s = r["stats"]
    o = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Cluster headache log {r['start']} to {r['end']}</title><style>{HTML_CSS}</style></head><body>"]
    o.append("<h1>Cluster headache log</h1><table class='meta'>")
    if r["patient"]:
        o.append(f"<tr><td>Patient</td><td>{e(r['patient'])}</td></tr>")
    if r["neurologist"]:
        o.append(f"<tr><td>Prepared for</td><td>{e(r['neurologist'])}</td></tr>")
    o.append(f"<tr><td>Period</td><td>{fmt_date(r['start'])} to {fmt_date(r['end'])} ({s['days']} days)</td></tr>")
    for c in r["cycles"]:
        o.append(f"<tr><td>Cycle</td><td>{e(c['name'])}, began {fmt_date(c['started_on'])}, "
                 + (f"ended {fmt_date(c['ended_on'])}" if c["ended_on"] else "ongoing") + "</td></tr>")
    o.append(f"<tr><td>Prepared</td><td>{r['generated']}</td></tr>"
             "<tr><td>Notes</td><td>Pain on the KIP 0–10 scale. Times local, 24-hour. Pressure is barometric, "
             "reduced to sea level.</td></tr></table>")
    o.append("<h2>Summary</h2><table class='stats'>")
    for k, v in _summary_lines(r):
        o.append(f"<tr><td><b>{k}</b></td><td>{e(v)}</td></tr>")
    o.append("</table>")
    if include_chart and (r["attacks"] or r["entries"]):
        o.append("<h3>Daily chart</h3><div class='chart'>"
                 + daily_svg(r["attacks"], r["entries"], r["start"], r["end"], r["cycle"], theme="light")
                 + "</div>")
    if s["attacks"]:
        mx = max(c for _, c in _hour_buckets(s["by_hour"])) or 1
        o.append("<h3>Headache start times</h3><table>")
        for label, c in _hour_buckets(s["by_hour"]):
            o.append(f"<tr><td style='width:80px'>{label}</td><td><span class='bar' style='width:{c / mx * 300:.0f}px'></span> {c}</td></tr>")
        o.append("</table>")
    if s["weeks"]:
        o.append("<h3>By week</h3><table class='stats'><tr><th>Week</th><th>Headaches</th><th>Doses</th><th>Median length</th><th>Highest KIP</th></tr>")
        for w in s["weeks"]:
            o.append(f"<tr><td>{e(w['label'])}</td><td>{w['attacks']}</td><td>{w['meds']}</td>"
                     f"<td>{fmt_mins(w['median_duration']) if w['median_duration'] is not None else '–'}</td>"
                     f"<td>{w['max_kip'] if w['max_kip'] is not None else '–'}</td></tr>")
        o.append("</table>")
    if s["treatments"]:
        o.append("<h3>Treatments</h3><table class='stats'>")
        for t in s["treatments"]:
            o.append(f"<tr><td><b>{e(t['name'])}</b></td><td>{e(_treat_line(t))}</td></tr>")
        o.append("</table>")
    if r["meds"]:
        o.append("<h2>Medication log</h2><p class='muted'>Each time a medication or treatment was used, grouped by "
                 "medication. Session lengths are shown for treatments with a start and stop time.</p>")
        for m in r["meds"]:
            o.append(f"<h4>{e(m['name'])} <span class='muted'>· {e(CAT_WORDS.get(m['category'], m['category']))}</span>"
                     "</h4><table class='stats'>")
            for d in m["days"]:
                o.append(f"<tr><td style='width:150px;white-space:nowrap'>{d['label']}</td>"
                         f"<td>{e('; '.join(d['uses']))}</td></tr>")
            o.append("</table>")
    o.append("<h2>Daily log</h2>")
    if not r["weeks"]:
        o.append("<p class='muted'>Nothing logged in this period.</p>")
    for w in r["weeks"]:
        o.append(f"<h3>{e(w['label'])}</h3>")
        for d in w["days"]:
            head = e(d["label"])
            if d["cycle_label"]:
                head += f" <span class='muted'>· {e(d['cycle_label'])}</span>"
            if d["attacks"]:
                head += f" <span class='muted'>· {plural(d['attacks'], 'headache')}</span>"
            o.append(f"<h4>{head}</h4><table class='log'>")
            for l in d["lines"]:
                cls = " ".join(x for x in ("in" if l["in"] else "", l["type"]) if x)
                wx = f"<br><span class='w'>Weather: {e(l['weather'])}</span>" if l["weather"] else ""
                o.append(f"<tr class='{cls}'><td class='t'>{l['time']}</td><td class='g'>{l['tag']}</td>"
                         f"<td>{e(l['text'])}{wx}</td></tr>")
            o.append("</table>")
    o.append("<p class='muted'>Generated by ClusterLog.</p></body></html>")
    return "".join(o)


def csv_text(r):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "time", "cycle", "headache", "kind", "kip", "phase", "treatment", "amount",
                "title", "note", "side", "locations", "pain_types", "temp_c", "humidity_pct", "pressure_cmhg",
                "pressure_kpa", "stopped", "duration_min"])
    cycles = {c["id"]: c["name"] for c in store.q("SELECT id, name FROM cycles")}
    tnames = {t["id"]: t["name"] for t in store.q("SELECT id, name FROM treatments")}
    num = {a["id"]: a["number"] for a in r["attacks"]}
    rows = []
    for a in r["attacks"]:
        wx = a["weather"] or {}
        base = [cycles.get(a["cycle_id"], ""), a["number"]]
        rows.append((a["started_at"], [*base, "headache_start", "", "", "", "", "", a["notes"], a["side"],
                                       "; ".join(a["locations"]), "; ".join(a["pain_types"]),
                                       wx.get("temp_c", ""), wx.get("humidity", ""), wx.get("pressure_cmhg", ""),
                                       wx.get("pressure_kpa", ""), "", ""]))
        if a["ended_at"]:
            rows.append((a["ended_at"], [*base, "headache_end", a["peak_kip"] if a["peak_kip"] is not None else "",
                                         "", "", "", f"lasted {minutes(a['started_at'], a['ended_at'])} min",
                                         "", "", "", "", "", "", "", "", "", ""]))
    for e in r["entries"]:
        rows.append((e["at"], [cycles.get(e["cycle_id"], ""), num.get(e["attack_id"], ""), e["kind"],
                               e["kip"] if e["kip"] is not None else "", PHASES.get(e["phase"] or "", ""),
                               tnames.get(e["treatment_id"], ""), e["amount"], e["title"], e["note"],
                               "", "", "", "", "", "", "",
                               e["ended_at"].replace("T", " ") if e.get("ended_at") else "",
                               minutes(e["at"], e["ended_at"]) if e.get("ended_at") else ""]))
    rows.sort(key=lambda x: x[0])
    for at, vals in rows:
        w.writerow([at[:10], at[11:16], *vals])
    return buf.getvalue()


# ---------------------------------------------------------------- daily chart

def daily_svg(attacks, entries, d_from, d_to, cycle=None, theme="dark", meds="key"):
    """Days across, time of day down. ● attack start (bigger = higher peak
    KIP) with a bar for its duration; ◇ abortive dose, ◆ preventive /
    emergent dose; bottom strip = attacks per day."""
    fg, bg, grid, mute = ("#fff", "#000", "#3a3a3a", "#bbb") if theme == "dark" else ("#000", "#fff", "#ccc", "#444")
    d0, d1 = dt.date.fromisoformat(d_from), dt.date.fromisoformat(d_to)
    n = max(1, (d1 - d0).days + 1)
    dw = max(10, min(28, 640 // n))
    ml, mr, mt, ph, gap, bh = 30, 8, 24, 264, 28, 56
    W = ml + n * dw + mr
    H = mt + ph + gap + bh + 52
    by = mt + ph + gap  # top of count strip

    def y(h):
        return mt + h / 24 * ph

    def xi(dstr):
        return (dt.date.fromisoformat(dstr) - d0).days

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Consolas, SF Mono, Menlo, monospace" font-size="10" role="img" '
         f'aria-label="Daily chart of headaches and medication doses">',
         f'<rect width="{W}" height="{H}" fill="{bg}"/>']
    for h in (0, 6, 12, 18, 24):
        o.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y(h):.1f}" y2="{y(h):.1f}" stroke="{grid}" stroke-width="1"/>'
                 f'<text x="{ml - 4}" y="{y(h) + 3:.1f}" fill="{mute}" text-anchor="end">{h:02d}</text>')
    # week separators + labels
    for i in range(n):
        d = d0 + dt.timedelta(days=i)
        if cycle:
            off = (d - dt.date.fromisoformat(cycle["started_on"])).days
            is_start, label = off >= 0 and off % 7 == 0, f"W{off // 7 + 1}"
        else:
            is_start, label = d.weekday() == 0, d.strftime("%d %b")
        if is_start or i == 0:
            x = ml + i * dw
            o.append(f'<line x1="{x}" x2="{x}" y1="{mt - 8}" y2="{by + bh}" stroke="{grid}" stroke-width="1"/>')
            if is_start:
                o.append(f'<text x="{x + 2}" y="{mt - 10}" fill="{fg}" font-weight="bold">{label}</text>')
                o.append(f'<text x="{x + 2}" y="{by + bh + 14}" fill="{mute}">{d:%d %b}</text>')
    # attacks: duration bars (split over midnight) + start dots
    counts = [0] * n
    for a in attacks:
        start = store.parse_ts(a["started_at"])
        end = store.parse_ts(a["ended_at"]) if a["ended_at"] else start + dt.timedelta(minutes=10)
        cur = start
        while cur < end:
            midnight = dt.datetime.combine(cur.date() + dt.timedelta(days=1), dt.time())
            seg_end = min(end, midnight)
            i = (cur.date() - d0).days
            if 0 <= i < n:
                h0 = cur.hour + cur.minute / 60
                h1 = 24 if seg_end == midnight else seg_end.hour + seg_end.minute / 60
                o.append(f'<rect x="{ml + i * dw + dw * 0.22:.1f}" y="{y(h0):.1f}" width="{max(2, dw * 0.16):.1f}" '
                         f'height="{max(1.5, y(h1) - y(h0)):.1f}" fill="{fg}" opacity="0.45"/>')
            cur = seg_end
        i = xi(a["started_at"][:10])
        if 0 <= i < n:
            counts[i] += 1
            r = min(dw * 0.3, 2.5 + (a["peak_kip"] or 0) * 0.3)
            dur = fmt_dur(minutes(a["started_at"], a["ended_at"])) if a["ended_at"] else "open"
            o.append(f'<circle cx="{ml + i * dw + dw * 0.3:.1f}" cy="{y(start.hour + start.minute / 60):.1f}" r="{r:.1f}" '
                     f'fill="{fg}"><title>Headache {a["number"]} {a["started_at"][5:]} · {dur}'
                     f'{" · KIP " + str(a["peak_kip"]) if a["peak_kip"] is not None else ""}</title></circle>')
    # medication diamonds
    if meds != "none":
        for e in entries:
            if e["kind"] not in ("treatment", "event"):
                continue
            cat = e.get("category") or ("emergent" if e["kind"] == "event" else "other")
            if meds == "key" and cat not in KEY_MED_CATEGORIES:
                continue
            i = xi(e["at"][:10])
            if not 0 <= i < n:
                continue
            cx, cy, s = ml + i * dw + dw * 0.72, y(int(e["at"][11:13]) + int(e["at"][14:16]) / 60), min(4.5, dw * 0.24)
            fill = bg if cat == "abortive" else fg
            o.append(f'<path d="M{cx:.1f} {cy - s:.1f}L{cx + s:.1f} {cy:.1f}L{cx:.1f} {cy + s:.1f}L{cx - s:.1f} {cy:.1f}Z" '
                     f'fill="{fill}" stroke="{fg}" stroke-width="1.2"><title>{escape(e["title"])} {e["at"][5:]}</title></path>')
    # attacks-per-day strip
    mx = max(counts + [1])
    o.append(f'<text x="{ml - 4}" y="{by + 4}" fill="{mute}" text-anchor="end">{mx}</text>'
             f'<text x="{ml - 4}" y="{by + bh}" fill="{mute}" text-anchor="end">0</text>'
             f'<line x1="{ml}" x2="{W - mr}" y1="{by + bh}" y2="{by + bh}" stroke="{grid}"/>')
    for i, c in enumerate(counts):
        if c:
            hgt = c / mx * bh
            o.append(f'<rect x="{ml + i * dw + 1.5:.1f}" y="{by + bh - hgt:.1f}" width="{max(2, dw - 3):.1f}" '
                     f'height="{hgt:.1f}" fill="{fg}"/>')
            if dw >= 14:
                o.append(f'<text x="{ml + i * dw + dw / 2:.1f}" y="{by + bh - hgt - 3:.1f}" fill="{fg}" '
                         f'text-anchor="middle">{c}</text>')
    ly = H - 12
    o.append(f'<circle cx="{ml + 4}" cy="{ly - 3}" r="4" fill="{fg}"/>'
             f'<text x="{ml + 12}" y="{ly}" fill="{fg}">headache (size = peak KIP)</text>'
             f'<path d="M{ml + 186} {ly - 7.5}L{ml + 190.5} {ly - 3}L{ml + 186} {ly + 1.5}L{ml + 181.5} {ly - 3}Z" fill="{bg}" stroke="{fg}"/>'
             f'<text x="{ml + 195}" y="{ly}" fill="{fg}">abortive</text>'
             f'<path d="M{ml + 262} {ly - 7.5}L{ml + 266.5} {ly - 3}L{ml + 262} {ly + 1.5}L{ml + 257.5} {ly - 3}Z" fill="{fg}" stroke="{fg}"/>'
             f'<text x="{ml + 271}" y="{ly}" fill="{fg}">preventive/emergent</text>'
             f'<text x="{ml}" y="{by - 8}" fill="{mute}">headaches per day</text>')
    o.append("</svg>")
    return "".join(o)
