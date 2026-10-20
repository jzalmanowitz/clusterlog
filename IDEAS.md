# IDEAS — for review

A parking lot of possible features. Nothing here is committed to; move anything
worth doing into TODO.md. Sizes: **S** = an evening, **M** = a session, **L** = several.

> **Cluster headache is not migraine.** It's a separate primary headache disorder
> (a *trigeminal autonomic cephalalgia*). Attacks are strictly one-sided, around
> the eye/temple, last roughly 15–180 minutes untreated, can come up to 8 times a
> day, often at the same clock time, and bring same-side autonomic signs (tearing,
> red eye, runny or blocked nostril, drooping eyelid, sweating) plus *restlessness
> and pacing* — where migraine sufferers usually lie still in a dark room and
> attacks last 4–72 hours. Patients rate it among the worst pains known (9.7/10 in
> a 2020 survey, ahead of childbirth and kidney stones). Treatments differ too:
> high-flow oxygen works for cluster headache, not migraine. Anything borrowed from
> migraine apps (or migraine-shaped clinic diaries) needs checking against this.

*Note on sources:* Reddit (r/clusterheads) couldn't be read from here — Reddit
blocks automated access and I won't spoof my way past that. If you want it
included: create a free Reddit "script" app (reddit.com/prefs/apps) for proper API
access, or paste posts you like into a file. Everything below comes from patient
organisations, existing cluster apps and clinical literature.

---

## Part 1 — Ideas from the cluster headache community and research

### Logging what neurologists actually use

1. **Autonomic signs, one tap each** (S) — tearing, red eye, runny/blocked
   nostril, drooping eyelid, facial sweating, ear fullness, *restless/pacing*.
   These are the ICHD-3 diagnostic features and the clearest "this is not
   migraine" evidence in a report. Could be the "symptoms" half of the
   triggers/symptoms stub, with triggers left off. *(ICHD-3 summaries; Clusterbusters.)*
2. **"Woke me up" as a first-class flag + night/day split in the report** (S) —
   nocturnal attacks are a hallmark; clinicians and Gammacore's diary guide ask
   for day vs night and whether attacks wake you. Already a pain type; promote it
   to its own field so stats can count it.
3. **Kip scale built in** (S) — the 0–10 KIP scale was devised by patient Bob
   Kipple; OUCH publishes level descriptions (1 = shadows come and go, 4 = starting
   to get bad, 8 = time to scream/rock/pace, 10 = ER trip). Show the description
   under each KIP button (or on long-press) to calibrate at 3am, and print the
   legend at the end of the .txt report so a neurologist unfamiliar with KIP can
   read it. Note in the report that KIP isn't clinically validated.
4. **Triptan days per month** (S) — neurologists track triptan *days* (overuse and
   daily limits). Add "days with a triptan" per week/month to stats and the report.
5. **Shadow-only episodes** (S) — shadows that never become an attack matter for
   judging preventives (D3 regimen, busting, verapamil). Let "End headache" with
   no pain above KIP 2 be marked *shadow only*, counted separately in stats.

### Patterns: the clock and the calendar

6. **24-hour "clock face" chart** (M) — a 2023 meta-analysis of 16 studies found a
   circadian pattern in ~70% of patients, peaking 21:00–03:00, often precise to
   within minutes day to day. A radial clock of start times per cycle makes "my
   attacks come at 23:30 and 04:45" obvious. *(Benkli et al., Neurology 2023.)*
7. **"Next likely window" heads-up** (M) — from the last 5–7 days' start times,
   show "most of your recent headaches started 23:00–00:30" on the cycle screen,
   so oxygen is at the bed and the energy drink is in the fridge. Descriptive only,
   never a prediction promise.
8. **Seasonal / cycle history** (M) — the same meta-analysis found seasonal peaks
   in spring and autumn. A multi-year timeline of cycles (start date, length,
   headaches/day) answers "when does my next cycle usually start?" and pairs with
   Cycle Learnings ("last time: start D3 two weeks before late October").
9. **Chinook / pressure view** (M) — Calgary-specific: flag headaches where the 6-h
   pressure change or temperature jump was large, and show headaches-per-day next
   to pressure on the daily chart. The University of Padua thesis looked at
   pressure and moon phase; evidence is thin, which is exactly why a personal
   record is interesting.

### Treatment details

10. **Oxygen sessions, not just doses** (M) — community guidance stresses flow rate
    (12–15+ L/min, some up to 25 with demand valves), a non-rebreather mask, and
    starting at the first sign rather than at peak. Track an O2 *session*:
    on/off times, flow changes ("up to 25 lpm"), tank swaps — your old log does
    exactly this by hand. Stats: time-on-O2 to relief, and does starting at
    shadows vs at KIP 6+ change outcome? *(Clusterbusters oxygen guide.)*
11. **Tank inventory** (S) — count full/empty tanks, decrement on "tank swap",
    warn when two are left so you reorder before a bad week.
12. **"Did it work?" after each abortive** (S) — one tap when ending a headache:
    for each abortive used, *aborted / helped / no effect*. ClusterUck records
    effectiveness this way; it makes the "time to headache end" stats far more
    meaningful.
13. **Energy-drink protocol** (S) — many report faster aborts with a
    caffeine + taurine drink at first sign, then oxygen. Already loggable; a
    "first-sign kit" quick action could log drink + O2 start in one tap.
    *(Clusterbusters; anecdotal.)*
14. **Preventive / regimen checklist** (M) — a daily "taken today?" list for
    preventives (verapamil doses, the Clusterbusters D3 regimen pieces, Emgality
    monthly). Shows misses alongside headache counts. The D3 regimen has a
    kidney-stone caution in community threads — a reminder to get bloodwork is a
    reasonable add.

### Getting care

15. **ER / "not a migraine" card** (S) — a one-page printable (and offline)
    sheet: diagnosis, what works (100% O2 12–15 L/min via non-rebreather, which
    triptan), current meds and doses, neurologist contact. ER staff treating
    cluster headache as migraine is a recurring frustration in patient forums.
16. **Oxygen travel letter** (S) — MyClusters ships a travel guide incl. oxygen
    abroad; a generated letter + checklist (prescription, supplier contacts,
    airline rules) is cheap to add.
17. **"Since my last appointment" report preset** (S) — store appointment dates;
    one tap makes the .txt cover exactly that period.
18. **Questions for my neurologist** (S) — a running list you add to whenever
    something comes up mid-cycle, printed at the end of the report.

### Ideas seen in other cluster apps

| App | Feature worth considering |
|---|---|
| MyClusters (iOS/Android) | Lock-screen live logging; "repeat last attack" quick log; timestamped trace logs reconstructed afterwards; day rating; import from notes; offline article library |
| ClusterUck (iOS) | Effectiveness per medication; default pain location; head diagram for location; copy an episode; Apple Watch logging; CSV import |
| A Clusterbusters member's open-source web tracker | Oxygen on/off status as part of the attack |

---

## Part 2 — Quality-of-life proposals for ClusterLog

### Fewer taps at 3am

19. **Home-screen shortcut straight to "Start headache"** (S) — `#/start` opens
    the start form for the active cycle; add it to the home screen as a second icon.
20. **Note templates** (S) — one-tap notes from your own vocabulary: *woken up,
    back to bed, fell asleep, tank swap, shadows gone, oxygen off, pain gone*.
21. **Log several meds at once** (S) — your log often has "zomig, flonase,
    oxygen" in the same minute; let the Medication sheet multi-select quick meds.
22. **Repeat last dose** (S) — a "same again" button on the most recent dose.
23. **"Forgot to end it?" nudge** (S) — if a headache has been open longer than
    your longest ever (or 4 h), show a banner offering to end it at the last
    logged time.
24. **Dim mode for night** (S) — still black/white, but greys instead of pure
    white for big buttons so the screen doesn't glare at 3am; auto after 22:00.
25. **Countdown timers** (M) — "oxygen 15 min" session timer and "earliest next
    Zomig in 1 h 45 m" (from a per-med minimum interval), shown on the headache
    screen.

### Morning-after review

26. **Edit history** (M) — keep previous versions of edited entries so
    "cold light of morning" corrections are visible and reversible.
27. **Search the journal** (S) — find "nerve block", "redbull", "ER".
28. **Compare cycles side by side** (M) — length, headaches/day, median length,
    peak KIP, what you were taking — next to that cycle's Learnings.
29. **Year heatmap** (M) — a calendar grid (GitHub-style) of headaches per day
    across all cycles: cycles and remission periods at a glance.

### Reports

30. **KIP legend + "how to read this" footer in the .txt** (S) — see #3.
31. **Optional sections** (S) — tick boxes for summary / weekly table / daily log /
    weather, so a short report for a quick appointment is one tap.
32. **Time format option** (S) — HH:MM (current) or your own HHMM style.

### Reliability & ops

33. **HTTPS + installable app** (M) — unlocks keep-screen-awake during a headache,
    real offline mode, web push reminders (iOS 16.4+ supports push for home-screen
    web apps), and the share sheet for the .txt.
34. **Offline queue** (M) — if the homelab is down mid-attack, entries are kept on
    the phone and sync when it's back.
35. **Off-box backups** (S) — nightly copy of `data/backups/` to a NAS or cloud
    drive; a "last backup" line on the Settings screen.
36. **Import from MyClusters / ClusterUck CSV** (M) — useful if you (or someone
    you share this with) have history in those apps.
37. **Health dashboard line** (S) — Settings shows app version, DB size, last
    backup, last weather fetch, so problems are visible before they matter.

---

## Sources

- ICHD-3 criteria summary and history: [Practical Neurology — Cluster Headache: History, Mechanisms, Treatment](https://practicalneurology.com/articles/2017-may/cluster-headache-history-mechanisms-and-most-importantly-treatment-options); [EBSCO — Could it be cluster headache?](https://about.ebsco.com/blogs/health-notes/severe-headache-pain-could-it-be-cluster-headache); [Cluster headache and migraine: two distinct primary headaches? (PMC9706960)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9706960); [How do cluster headaches differ from migraines?](https://progress.im/en/node/3061)
- Pain rating vs other pain: [Burish et al. 2020, *Headache* (PMC7898696)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7898696/); [Patient Care — Cluster headache pain and symptomatology](https://www.patientcareonline.com/view/cluster-headache-pain-and-symptomatology)
- KIP scale: [DocCheck Flexikon — KIP-Skala](https://flexikon.doccheck.com/de/KIP-Skala); [OUCH UK downloads](https://mail.ouchuk.org/downloads); [Clusterbusters thread on shadows and the KIP scale](https://clusterbusters.org/forums/topic/2721-rant-morphed-to-shadows-and-kip-scale/page/3/)
- Circadian and seasonal patterns: [UTHealth — Cluster headache, migraine strongly associated with circadian system](https://ww2.uth.edu/news/story/cluster-headache-migraine-strongly-associated-with-circadian-system-according-to-published-research); [MDedge summary](https://mdedge.com/content/cluster-migraine-headache-strongly-linked-circadian-rhythm); [Healthline — why attacks happen at the same time of day](https://www.healthline.com/health-news/why-your-migraine-or-cluster-headaches-happen-at-the-same-time-of-day); [University of Padua thesis (seasonality, pressure, moon phase)](https://thesis.unipd.it/handle/20.500.12608/30892)
- Oxygen and energy drinks: [Clusterbusters — High-Flow Oxygen Therapy](https://clusterbusters.org/resource/oxygen-therapy-for-cluster-headaches/); [Wikipedia — Demand valve oxygen therapy](https://en.wikipedia.org/wiki/Demand_valve_oxygen_therapy); [Oxygen therapy review (PMC7802413)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7802413/); [migraine.com — 5 things to know to abort cluster headaches with oxygen](https://migraine.com/living-migraine/abort-cluster-headaches-oxygen); [Clusterbusters forum — insurance doesn't cover oxygen](https://clusterbusters.org/forums/topic/7256-my-insurance-doesnt-cover-oxygen-any-tips/)
- D3 regimen discussion (anecdotal): [Clusterbusters forum — episodic sufferer, worst cycle yet](https://clusterbusters.org/forums/topic/8444-episodic-suffer-worst-cycle-yet/)
- What to record: [Gammacore — Keeping a cluster headache journal](https://www.gammacore.com/keeping-a-cluster-headache-journal-what-to-track-and-why/); [OUCH UK forum — diary for cluster headache](https://ouchuk.org/node/818); [OUCH UK leaflet](https://ouchuk.org/sites/default/files/downloads/trifold-leaflet-2023-v5.pdf)
- Other apps: [MyClusters (App Store)](https://apps.apple.com/app/id6745556184); [ClusterUck (App Store)](https://apps.apple.com/app/id1072769448); [Clusterbusters — headache tracking & pain logging thread](https://clusterbusters.org/forums/topic/15109-headache-tracking-pain-logging); [OUCH UK on MyClusters](https://ouchuk.org/node/1703)

*None of this is medical advice — ideas for what to track, to discuss with your
neurologist.*
