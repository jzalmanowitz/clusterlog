"""Neurologist reports (text / HTML / CSV) and the daily SVG chart."""
import csv
import datetime as dt
import io
import json
import math
from html import escape

import store
from store import PHASES, fmt_dur, minutes

TAGS = {"pain": "PAIN", "treatment": "MED", "note": "NOTE", "event": "EVENT"}
KEY_MED_CATEGORIES = ("abortive", "preventive", "emergent")


def fmt_date(d):
    return dt.date.fromisoformat(d[:10]).strftime("%a %d %b %Y")


def hhmm(at):
    return at[11:13] + at[14:16]


def weather_text(w, prev=None):
    if not w:
        return ""
    parts = []
    for key, unit, fmt in (("temp_c", "°C", "{:.1f}"), ("humidity", "%", "{:.0f}"), ("pressure_cmhg", " cmHg", "{:.2f}")):
        s = fmt.format(w[key]) + unit
        if prev and prev.get(key) is not None:
            delta = w[key] - prev[key]
            s += " ↑" if delta > 0.005 else (" ↓" if delta < -0.005 else " →")
        parts.append(s)
    return " · ".join(parts)


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
        "attacks": attacks, "entries": entries, "cycle": stats_cycle,
    }


def line(at, typ, o, prev_w):
    if typ == "start":
        bits = [f"ATTACK #{o['number']} START"]
        detail = [x for x in (f"{o['side']} side" if o["side"] else "",
                              ", ".join(o["locations"]), ", ".join(o["pain_types"])) if x]
        if detail:
            bits.append("(" + "; ".join(detail) + ")")
        if o["notes"]:
            bits.append("— " + o["notes"].strip())
        w = weather_text(o["weather"], prev_w.get(o["id"]))
        return {"time": hhmm(at), "type": "start", "tag": "▶", "text": " ".join(bits),
                "weather": w, "in": True}
    if typ == "end":
        d = minutes(o["started_at"], o["ended_at"])
        text = f"ATTACK #{o['number']} END — lasted {fmt_dur(d)}"
        if o["peak_kip"] is not None:
            text += f", peak KIP {o['peak_kip']}"
        return {"time": hhmm(at), "type": "end", "tag": "■", "text": text, "weather": "", "in": True}
    e = o
    note = (e["note"] or "").strip()
    if e["kind"] == "pain":
        text = f"KIP {e['kip']}" + (f" ({PHASES.get(e['phase'], e['phase'])})" if e["phase"] else "")
        if note:
            text += " — " + note
    elif e["kind"] in ("treatment", "event"):
        text = e["title"] + (" — " + note if note else "")
    else:
        text = note
    return {"time": hhmm(at), "type": e["kind"], "tag": TAGS[e["kind"]], "text": text,
            "weather": "", "in": bool(e["attack_id"])}


# ---------------------------------------------------------------- renderers

def _summary_lines(r):
    s = r["stats"]
    du, pk = s["duration"], s["peak"]
    out = [("Attacks", f"{s['attacks']}  ({s['per_day_avg']}/day avg · {s['attack_days']} days with attacks · "
                       f"{s['free_days']} attack-free of {s['days']})")]
    if du["n"]:
        rng = f"{fmt_dur(du['min'])}–{fmt_dur(du['max'])}"
        iqr = f", middle half {fmt_dur(du['p25'])}–{fmt_dur(du['p75'])}" if du["p25"] is not None else ""
        out.append(("Duration", f"median {fmt_dur(du['median'])} · mean {fmt_dur(du['mean'])} · range {rng}{iqr} (n={du['n']})"))
    if pk["max"] is not None:
        out.append(("Peak pain", f"mean KIP {pk['mean']} · max KIP {pk['max']}"))
    return out


def _hour_buckets(by_hour):
    return [(f"{i:02d}–{i + 3:02d}h", sum(by_hour[i:i + 3])) for i in range(0, 24, 3)]


def _treat_line(t):
    s = f"{t['uses']} use{'s' if t['uses'] != 1 else ''}"
    if t["in_attacks"]:
        s += f", {t['in_attacks']} during attacks"
    te = t["to_end"]
    if te["n"]:
        s += f" · attack ended a median {fmt_dur(te['median'])} after first dose (n={te['n']})"
    return s


def text(r):
    s = r["stats"]
    L = ["CLUSTER HEADACHE LOG", "===================="]
    if r["patient"]:
        L.append(f"Patient:    {r['patient']}")
    L.append(f"Period:     {fmt_date(r['start'])} to {fmt_date(r['end'])} ({s['days']} days)")
    for c in r["cycles"]:
        L.append(f"Cycle:      {c['name']} — began {fmt_date(c['started_on'])}"
                 + (f", ended {fmt_date(c['ended_on'])}" if c["ended_on"] else " (ongoing)"))
    L.append(f"Generated:  {r['generated']}")
    L.append("Pain scale: KIP 0–10. Times are local, 24-hour (HHMM).")
    L += ["", "SUMMARY", "-------"]
    for k, v in _summary_lines(r):
        L.append(f"  {k + ':':<11} {v}")
    if s["attacks"]:
        L.append("  Attack start times:")
        mx = max(c for _, c in _hour_buckets(s["by_hour"])) or 1
        for label, c in _hour_buckets(s["by_hour"]):
            L.append(f"    {label}  {'#' * math.ceil(c / mx * 30) if c else '':<30} {c}")
    if s["weeks"]:
        L.append("  By week:")
        for w in s["weeks"]:
            extra = f", median {fmt_dur(w['median_duration'])}" if w["median_duration"] is not None else ""
            extra += f", max KIP {w['max_kip']}" if w["max_kip"] is not None else ""
            L.append(f"    {w['label']}: {w['attacks']} attacks, {w['meds']} med doses{extra}")
    if s["treatments"]:
        L.append("  Treatments:")
        for t in s["treatments"]:
            L.append(f"    {t['name']}: {_treat_line(t)}")
    L += ["", "DAILY LOG", "---------"]
    if not r["weeks"]:
        L.append("  (nothing logged in this period)")
    for w in r["weeks"]:
        L += ["", f"== {w['label']} =="]
        for d in w["days"]:
            head = d["label"]
            if d["cycle_label"]:
                head += f"  ·  {d['cycle_label']}"
            if d["attacks"]:
                head += f"  ·  {d['attacks']} attack{'s' if d['attacks'] != 1 else ''}"
            L += ["", head]
            for l in d["lines"]:
                L.append(f"  {l['time']} {'|' if l['in'] else ' '} {l['tag']:<5} {l['text']}")
                if l["weather"]:
                    L.append(f"  {'':4} | {'':5} weather: {l['weather']}")
    L += ["", "'|' marks entries during an attack. Generated by ClusterLog."]
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


def html(r, message="", include_chart=True):
    e = escape
    s = r["stats"]
    o = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Cluster headache log {r['start']} to {r['end']}</title><style>{HTML_CSS}</style></head><body>"]
    if message:
        o.append(f"<p>{e(message).replace(chr(10), '<br>')}</p><hr>")
    o.append("<h1>Cluster headache log</h1><table class='meta'>")
    if r["patient"]:
        o.append(f"<tr><td>Patient</td><td>{e(r['patient'])}</td></tr>")
    o.append(f"<tr><td>Period</td><td>{fmt_date(r['start'])} to {fmt_date(r['end'])} ({s['days']} days)</td></tr>")
    for c in r["cycles"]:
        o.append(f"<tr><td>Cycle</td><td>{e(c['name'])} — began {fmt_date(c['started_on'])}"
                 + (f", ended {fmt_date(c['ended_on'])}" if c["ended_on"] else " (ongoing)") + "</td></tr>")
    o.append(f"<tr><td>Generated</td><td>{r['generated']}</td></tr>"
             "<tr><td>Notes</td><td>Pain on the KIP 0–10 scale. Times local, 24-hour.</td></tr></table>")
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
        o.append("<h3>Attack start times</h3><table>")
        for label, c in _hour_buckets(s["by_hour"]):
            o.append(f"<tr><td style='width:80px'>{label}</td><td><span class='bar' style='width:{c / mx * 300:.0f}px'></span> {c}</td></tr>")
        o.append("</table>")
    if s["weeks"]:
        o.append("<h3>By week</h3><table class='stats'><tr><th>Week</th><th>Attacks</th><th>Med doses</th><th>Median length</th><th>Max KIP</th></tr>")
        for w in s["weeks"]:
            o.append(f"<tr><td>{e(w['label'])}</td><td>{w['attacks']}</td><td>{w['meds']}</td>"
                     f"<td>{fmt_dur(w['median_duration']) if w['median_duration'] is not None else '–'}</td>"
                     f"<td>{w['max_kip'] if w['max_kip'] is not None else '–'}</td></tr>")
        o.append("</table>")
    if s["treatments"]:
        o.append("<h3>Treatments</h3><table class='stats'>")
        for t in s["treatments"]:
            o.append(f"<tr><td><b>{e(t['name'])}</b></td><td>{e(_treat_line(t))}</td></tr>")
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
                head += f" <span class='muted'>· {d['attacks']} attack{'s' if d['attacks'] != 1 else ''}</span>"
            o.append(f"<h4>{head}</h4><table class='log'>")
            for l in d["lines"]:
                cls = " ".join(x for x in ("in" if l["in"] else "", l["type"]) if x)
                wx = f"<br><span class='w'>weather: {e(l['weather'])}</span>" if l["weather"] else ""
                o.append(f"<tr class='{cls}'><td class='t'>{l['time']}</td><td class='g'>{l['tag']}</td>"
                         f"<td>{e(l['text'])}{wx}</td></tr>")
            o.append("</table>")
    o.append("<p class='muted'>Generated by ClusterLog.</p></body></html>")
    return "".join(o)


def csv_text(r):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "time", "cycle", "attack", "kind", "kip", "phase", "treatment", "amount",
                "title", "note", "side", "locations", "pain_types", "temp_c", "humidity_pct", "pressure_cmhg",
                "pressure_kpa"])
    cycles = {c["id"]: c["name"] for c in store.q("SELECT id, name FROM cycles")}
    tnames = {t["id"]: t["name"] for t in store.q("SELECT id, name FROM treatments")}
    num = {a["id"]: a["number"] for a in r["attacks"]}
    rows = []
    for a in r["attacks"]:
        wx = a["weather"] or {}
        base = [cycles.get(a["cycle_id"], ""), a["number"]]
        rows.append((a["started_at"], [*base, "attack_start", "", "", "", "", "", a["notes"], a["side"],
                                       "; ".join(a["locations"]), "; ".join(a["pain_types"]),
                                       wx.get("temp_c", ""), wx.get("humidity", ""), wx.get("pressure_cmhg", ""),
                                       wx.get("pressure_kpa", "")]))
        if a["ended_at"]:
            rows.append((a["ended_at"], [*base, "attack_end", a["peak_kip"] if a["peak_kip"] is not None else "",
                                         "", "", "", f"lasted {minutes(a['started_at'], a['ended_at'])} min",
                                         "", "", "", "", "", "", "", ""]))
    for e in r["entries"]:
        rows.append((e["at"], [cycles.get(e["cycle_id"], ""), num.get(e["attack_id"], ""), e["kind"],
                               e["kip"] if e["kip"] is not None else "", PHASES.get(e["phase"] or "", ""),
                               tnames.get(e["treatment_id"], ""), e["amount"], e["title"], e["note"],
                               "", "", "", "", "", "", ""]))
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
         f'aria-label="Daily chart of attacks and medication doses">',
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
                     f'fill="{fg}"><title>Attack #{a["number"]} {a["started_at"][5:]} · {dur}'
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
             f'<text x="{ml + 12}" y="{ly}" fill="{fg}">attack (size = peak KIP)</text>'
             f'<path d="M{ml + 186} {ly - 7.5}L{ml + 190.5} {ly - 3}L{ml + 186} {ly + 1.5}L{ml + 181.5} {ly - 3}Z" fill="{bg}" stroke="{fg}"/>'
             f'<text x="{ml + 195}" y="{ly}" fill="{fg}">abortive</text>'
             f'<path d="M{ml + 262} {ly - 7.5}L{ml + 266.5} {ly - 3}L{ml + 262} {ly + 1.5}L{ml + 257.5} {ly - 3}Z" fill="{fg}" stroke="{fg}"/>'
             f'<text x="{ml + 271}" y="{ly}" fill="{fg}">preventive/emergent</text>'
             f'<text x="{ml}" y="{by - 8}" fill="{mute}">attacks per day</text>')
    o.append("</svg>")
    return "".join(o)
