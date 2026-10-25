"""Phone-size (390x844) browser walkthrough of the main flows, with screenshots.
Fails on any script error or any screen wider than the phone.

    python3 tests/ui_walkthrough.py http://127.0.0.1:8799 /tmp/shots
"""
import os
import sys

from playwright.sync_api import sync_playwright

U = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799") + "/"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "shots"
os.makedirs(SHOTS, exist_ok=True)
errors = []

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                       is_mobile=True, has_touch=True, accept_downloads=True).new_page()
    pg.on("console", lambda m: m.type in ("error", "warning") and errors.append(f"console {m.type}: {m.text}"))
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("dialog", lambda d: d.accept())

    def shot(name, full=False):
        pg.wait_for_timeout(400)
        pg.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)
        w = pg.evaluate("document.documentElement.scrollWidth")
        if w > 390:
            errors.append(f"{name}: page is {w}px wide")

    def add_event(choice):
        pg.click("#bar >> text=+ Add event")
        pg.click(f".sheet >> text={choice}")

    pg.goto(U)
    pg.wait_for_selector(".top")
    shot("01-home")
    pg.click("text=+ New cycle") if pg.locator("text=+ New cycle").count() else pg.click("text=Start a new cycle")
    pg.fill("input[name=name]", "Walkthrough cycle")
    pg.click(".sheet-foot >> text=Create cycle")
    pg.wait_for_timeout(700)
    if pg.locator(".sheet").count():
        pg.click(".sheet-foot >> text=Got it")
    pg.wait_for_selector("#bar >> text=Start headache")
    shot("02-cycle")

    # start a headache with its details
    pg.click("#bar >> text=Start headache")
    pg.wait_for_selector(".sheet")
    shot("03-start")
    pg.click(".sheet .kip-grid label:has-text('4')")
    pg.click(".sheet label.opt:has-text('Right')")
    pg.click(".sheet label.opt:has-text('temple')")
    pg.click(".sheet label.opt:has-text('stabbing')")
    pg.fill(".sheet input[name=custom_type]", "ice pick")
    pg.click(".sheet-foot >> text=Start headache")
    pg.wait_for_selector(".hero >> text=IN PROGRESS")
    shot("04-headache")

    # events: pain, quick med, dosed med, pain, note
    add_event("Pain level")
    pg.click(".sheet .kip-grid button[value='7']")
    pg.wait_for_timeout(500)
    add_event("Medication / treatment")
    pg.wait_for_selector(".sheet button[name=quick]")
    shot("05-med")
    pg.click(".sheet button[name=quick] >> nth=0")
    pg.wait_for_timeout(500)
    add_event("Medication / treatment")
    pg.click(".sheet button[name=quick]:has-text('Zomig')")
    pg.wait_for_timeout(500)
    add_event("Medication / treatment")
    pg.click(".sheet label.opt:has-text('Oxygen')")
    pg.fill(".sheet input[name=amount]", "25")
    pg.click(".sheet-foot >> text=Log it")
    pg.wait_for_timeout(500)
    for k in ("9", "3"):
        add_event("Pain level")
        pg.click(f".sheet .kip-grid button[value='{k}']")
        pg.wait_for_timeout(500)
    add_event("Note")
    pg.fill(".sheet textarea[name=note]", "pacing helps")
    pg.click(".sheet-foot >> text=Add note")
    pg.wait_for_timeout(500)
    shot("06-headache-full", full=True)
    assert "Peak" in pg.inner_text("#app"), "auto-phase should mark a peak once pain drops"

    assert "running" in pg.inner_text("#app"), "oxygen should show as running"
    pg.click("#bar >> text=End headache")
    pg.wait_for_selector(".sheet input[name=stop_ids]")
    assert pg.locator(".sheet input[name=stop_ids]").count() == 2, "both oxygen sessions offered for stopping"
    pg.click(".sheet .check label >> nth=0")
    shot("07-end-sheet")
    pg.click(".sheet-foot >> text=End headache")
    pg.wait_for_selector("text=Headache over")
    shot("07-over")

    pg.click(".back")
    for tab in ("Chart", "Stats", "Journal"):
        pg.click(f".tabs >> text={tab}")
        pg.wait_for_timeout(600)
        shot(f"08-{tab.lower()}")

    # one session is still running after the headache: stop it from the cycle screen
    assert pg.locator("text=Running now").count() == 1
    shot("09a-running")
    pg.click("[data-act=stopEntry]")
    pg.click(".sheet-foot >> text=Stop")
    pg.wait_for_timeout(600)
    assert pg.locator("text=Running now").count() == 0

    # D3 regimen: two dose times in a day add up; already-met supplements start unticked the second time
    pg.click("#bar >> text=Track D3 Regimen")
    pg.wait_for_selector(".sheet .supp")
    assert pg.is_checked(".sheet .supp:has-text('Vitamin D3') input[name=on]")
    shot("09c-d3-sheet")
    pg.uncheck(".sheet .supp:has-text('Zinc') input[name=on]")
    pg.click(".sheet .supp:has-text('Magnesium') label.opt:has-text('Food')")
    pg.click(".sheet-foot >> text=Save doses")
    pg.wait_for_selector(".jrow:has-text('D3 regimen')")
    assert "Magnesium 400 mg (food)" in pg.inner_text(".jrow:has-text('D3 regimen')")
    pg.click("#bar >> text=Track D3 Regimen")
    pg.wait_for_selector(".sheet .supp")
    assert pg.is_checked(".sheet .supp:has-text('Zinc') input[name=on]")
    assert not pg.is_checked(".sheet .supp:has-text('Vitamin D3') input[name=on]")
    assert "today 10,000 of 10,000 IU" in pg.inner_text(".sheet .supp:has-text('Vitamin D3')")
    pg.click(".sheet-foot >> text=Save doses")
    pg.wait_for_timeout(600)
    assert pg.locator(".jrow:has-text('D3 regimen')").count() == 2
    shot("09d-d3-journal")
    pg.click(".jrow:has-text('D3 regimen') >> nth=0")
    pg.wait_for_selector(".sheet-head >> text=Edit D3 regimen")
    pg.click(".sheet-head .x")
    pg.click(".tabs >> text=Stats")
    pg.wait_for_selector("section h2:has-text('D3 regimen')")
    shot("09e-d3-stats", full=True)
    pg.click(".tabs >> text=Journal")
    pg.wait_for_timeout(400)

    # Stats -> tap a treatment -> its history; switch to another med
    pg.click(".tabs >> text=Stats")
    pg.wait_for_selector("a.list-row:has-text('Oxygen')")
    pg.click("a.list-row:has-text('Oxygen')")
    pg.wait_for_selector("text=Every use")
    assert pg.locator(".jrow").count() == 2 and "until" in pg.inner_text("#app")
    shot("09b-med", full=True)
    pg.select_option("#medpick", label="Zomig nasal spray (1)")
    pg.wait_for_selector(".top h1:has-text('Zomig')")
    assert pg.locator(".jrow").count() == 1
    pg.click(".back")
    pg.wait_for_selector(".tabs button.on:has-text('Stats')")

    # report: plain .txt download
    pg.goto(U + "#/export")
    pg.wait_for_selector("#preview")
    pg.wait_for_timeout(600)
    shot("09-report")
    with pg.expect_download() as dl:
        pg.click("text=Download report (.txt)")
    assert dl.value.suggested_filename.endswith(".txt"), dl.value.suggested_filename

    # settings: text size applies immediately
    pg.goto(U + "#/settings")
    pg.wait_for_selector("#settings")
    pg.click("[data-act=fontScale][data-v='0.8']")
    pg.wait_for_timeout(300)
    assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--fs').trim()") == "0.8"
    shot("10-settings-small")
    pg.click("[data-act=fontScale][data-v='0.9']")
    pg.wait_for_timeout(300)

    # dim display: grey text, survives a reload
    fg = "getComputedStyle(document.body).color"
    assert pg.evaluate(fg) == "rgb(255, 255, 255)", (pg.evaluate(fg), pg.evaluate("document.documentElement.dataset.theme"))
    pg.click("[data-act=theme][data-v='dim']")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.documentElement.dataset.theme") == "dim"
    assert pg.evaluate(fg) == "rgb(163, 163, 163)", pg.evaluate(fg)
    shot("10b-settings-dim")
    pg.reload()
    pg.wait_for_selector("#settings")
    assert pg.evaluate("document.documentElement.dataset.theme") == "dim"
    pg.click("[data-act=theme][data-v='normal']")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.documentElement.dataset.theme") is None

    for route in ("#/treatments", "#/learnings", "#/loose", "#/supplements"):
        pg.goto(U + route)
        pg.wait_for_selector(".top")
        shot("11-" + route.strip("#/"))
    pg.click("button.list-row:has-text('Vitamin B-50')")
    pg.wait_for_selector(".sheet input[name=course_days]")
    assert pg.input_value(".sheet input[name=course_days]") == "90"
    shot("12-supplement-edit")
    pg.click(".sheet-head .x")
    pg.goto(U)
    pg.wait_for_selector(".top")
    pg.click("text=+ New cycle")
    pg.wait_for_selector(".sheet label.opt:has-text('Four-week loading')")
    shot("13-new-cycle-d3")
    b.close()

if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"UI walkthrough passed (screenshots in {SHOTS})")
