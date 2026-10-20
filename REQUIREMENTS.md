# ClusterLog — Requirements

These are the requirements as given by the project owner, kept close to the
original wording. Status markers: ✅ done in v1.0 · 🟡 partial · ⏳ not yet (see TODO.md).

## Background

> I suffer from Cluster Headaches. Part of my coping mechanism during headache
> attacks is taking detailed notes. I'd like to have a platform where I can record
> my notes. I have been doing these notes in things like Evernote, Google Docs, and
> Word... Evernote was great, except it keeps locking me out. So I want more control.

## Platform & architecture

- ✅ Runs on a Debian Linux box that already hosts other web services (must not
  collide with existing ports/services).
- ✅ Architected as a modern, mobile-optimized web app.
- ✅ Packaged as a basic installer so it can be migrated to different systems as needed.
- ✅ Self-hosted in a homelab. Potentially an iOS app later (⏳), but for now a web app.
- ✅ Security is not important at this juncture — homelab only, no external access.
- ✅ Data entry happens on a mobile phone: open the website and have it optimized for mobile use.

## Core functionality ("the crux")

1. ✅ Self-hosted web app.
2. ✅ Export a date range to email to the neurologist.
3. ✅ Track cycles in a date/time journal format.

## Cycles

- ✅ At the start of a new cluster headache cycle, create a new cycle and give it a
  name. Think of it as a container.
- ✅ Group events by week **inside a cluster cycle** (not calendar week, since cycles
  can span New Year). E.g. a cycle starting November 1 running to December 22:
  Nov 1–7 is week 1, Nov 8–14 is week 2, etc.
- ✅ **Cluster Cycle Learnings** — at the end of each cycle, write down one note of
  wisdom for future me (because future me never remembers). Just one note per
  cycle, to clarify what is actually important. Learnings are **just for me** —
  never included in the neurologist report.

## Headaches (attacks)

- ✅ Episodic sufferers can have 1–6 headaches per day, so each headache needs a
  start and stop time.
- ✅ Headaches can span midnight ("multi-day" events).
- ✅ Headaches can be as short as 10 minutes or as long as 4 hours; **tracking to the
  minute is the most important requirement**.
- ✅ Pattern: initial indication (aka **Shadows**), onset of pain, pain building to a
  peak (can be multi-step), then pain diminishing.
- ✅ "Start a new headache" records the time of the initial indication with a 1–10
  pain ranking, then the various increases in pain each with a timestamp, then a
  stop time.
- ✅ **Pain side** (left / right) — notable because it can change year to year.
- ✅ **Pain location**, multi-select per headache: neck, jaw, nose, sinuses, eye,
  temple, crown, cheekbone.
- ✅ **Pain type**, multi-select per headache: pounding, piercing, stabbing,
  throbbing, like a knife, pressure, woke me up, [add your own].
- ✅ **Weather** per event, non-editable: temperature (°C), humidity (%), pressure
  (cmHg), with trends showing increasing/decreasing since the last event.
  Clarified: pressure is air/barometric pressure in a standard unit of measure
  (sea-level reduced, as weather reports quote it); location is **Calgary**, since
  the mountains (chinooks) matter and Edmonton doesn't have them.

## Medications & treatments

- ✅ Pre-define types of meds/treatments once and reuse them. Examples: nasal spray,
  cold compress, oxygen, injection, electro-stimulation.
- ✅ Each type has a unit of measure, e.g. "Zomig Nasal Spray, 5mg"; "Cold compress,
  no UOM"; "Oxygen, 15L/min"; "Electro-stimulation, level 3".
- ✅ Track the time each med/treatment occurred, with visibility into **how long it
  has been since I took it** — based on historical feeling this helps estimate how
  much longer the attack will be until it aborts.
- ✅ "T A" in the old logs means Tylenol and Advil (extra strength for both) —
  set up as one combined treatment.
- ✅ Emergent treatments outside an attack (e.g. "Emgality Injection") as an event
  type with notes and date/time, using a calendar/date picker.

## Notes & editing

- ✅ General notes with a timestamp, as a running log of events (a form of control).
- ✅ Go back and edit entries — "in the throes of pain I won't be coherent but I will
  be able to update in the cold light of morning".

## Charts

- ✅ Daily graphs: quantity of headache events per day, plus marks for
  injection/medication doses — a dot for a headache and a diamond for a
  medication event.

## Navigation

- ✅ Open the page → click into a cycle (or create a new one) → create a new event,
  defaulting to today's date/time.

## Look & feel

- ✅ Dark mode with decent colour contrast. Colours aren't important: black
  background, white text, bold for headings, otherwise a monospace font like Consolas.

## Explicitly deferred

- ⏳ **Triggers and symptoms** — "some people like to track triggers and symptoms; I
  don't. But I might loop back on this if I end up sharing it out." A stub exists
  (see TODO.md and the comment on the `attacks` table in `app/store.py`).
- ⏳ iOS app.

## Reference: example of a historical log

The format the app's journal and report mirror, and that the text importer reads:

```
Feb 7
0035 - woken up
0042 - start oxygen, journey between kip 6 to kip 8, no zomig
0058 - pain starting to down
0059 - still stabbing pain in the left temple, going to wander back to bed
0227 - woken up, kip 5. Went to get the flonase
0234 - starting the oxygen, kip 6
0250 - oxygen off, started to get quesy
0255 - restarted the oxygen
0258 - oxygen off , pain gone
0445 - woken up
0450 - oxygen on, kip 6
0500 - oxygen off
0505 - took .5g mushrooms
0635 - time to wake up for work. Little bit of residual pain in the temple

0955 - shadows
1000 - .25g mushrooms
1010 - 12000 IU vitamin D, 1000 mcg B12 sublingual
1100 - feeling fantastic
1300 - some shadows
1350 - 10000 IU vitamin D, magnesium, T A
1530 - shadows, pain in the ear
1645 - kip 7... Going in search of redbull
1700 - redbull 473
1713 - flonase
1715 - oxygen
1719 - tank swap
1724 - oxygen off
2030 - shadows
2100 - .125 mushrooms, robax
2108 - oxygen kip 6
2125 - oxygen off still kip 6, flonase
2130 - melatonin 2mg
2134 - pain starting to subside
2145 - fall asleep
2326 - woken up, kip 6
2330 - caved and took zomig
2331 - oxygen, journey between kip 6 and 8
2346 - oxygen off, still pain
2355 - pain starting to subside

Feb 8 - day 10
0645 - 15000 IU vitamin D
1400 - some shadows, slammed a Monster energy and shadows left
1745 - some shadows
1800 - oxygen, kip 6 to kip 7
1813 - pain started to dissipate, oxygen off
1825 - pain gone
2300  - fall asleep

Feb 9
0041 - woken up kip 6
0047 - zomig flonase oxygen
0052 - tank swap
0104 - pain subsiding
0106 - oxygen off
0108 - back to bed
0645 - 15000 IU vitamin D
1530 - shadows, slammed a Monster
1600 - shadows gone
1650 - nerve block injection
2145 - shadows
2210 - T A flonase
2215 - starting oxygen kip 5/6 tender temple
2233 - stopped oxygen no effect, zomig
2236 - restarted oxygen
2241 - kip 8
2250 - pain starting to subside

Feb 10
0645 - 80 mg verapimil, docusate
2230 - 80 mg verapimil, docusate
2330 - woken up pain
2341 - zomig kip 6, ice wrap
2359 - pain started to dissipate

Feb 11
0006 - pain mostly gone, going back to bed
0830 - emgality 300
1730 - verapimil 160
1815 - shadows
1836 - zomig, kip 6, starting oxygen
1841 - oxygen up to 25lpm, kip 8
1844 - flonase
1846 - oxygen off
1855 - pain subsiding
2200 - 80 mg verapimil
```
