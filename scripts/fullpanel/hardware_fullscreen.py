# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Hardware acceptance run on a MacBook with a camera housing.

Takes over the Mac for a few minutes: enters and leaves native fullscreen,
moves between Spaces, opens Mission Control, clicks the Dock and presses
Command-Tab. Do not use the Mac while it runs. Needs Accessibility and Screen
Recording for the terminal, and FullPanelKit's spacesctl
(Tools/SpacesHarness; build with `swift build --product spacesctl`).

  ZEN_HARDWARE=1 SPACESCTL=/path/to/spacesctl ZEN_APP=/path/Zen\\ FullPanel.app \\
    python3 scripts/fullpanel/hardware_fullscreen.py [step ...]

Steps (default: all, in this order): standard fullpanel band reveal cycles
switch missioncontrol spaces dock cmdtab display restore. Results, logs and
top-of-display captures go to ~/Projects/Zen-FullPanelKit/test-runs/<time>/.
Each step prints PASS, FAIL or INFO with what it measured.
"""

import datetime
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pngread import read_png  # noqa: E402
from zentest import ZenApp  # noqa: E402

SPACESCTL = os.environ.get("SPACESCTL", "")
OUT = os.path.join(
    os.path.dirname(os.path.dirname(HERE)), "..", "test-runs",
    datetime.datetime.now().strftime("%Y%m%d-%H%M%S"),
)
OUT = os.path.normpath(OUT)
TOP = (200, 30, 30)

PAGE = """<!doctype html><meta charset=utf-8><title>FullPanel band</title>
<style>html,body{margin:0}body{background:#fff;font:15px -apple-system}
#top{height:300px;background:rgb(200,30,30);color:#fff;display:grid;place-items:center}
.row{height:120px;display:flex;align-items:center;justify-content:space-between;padding:0 24px;color:#fff}
.row:nth-child(4n+1){background:rgb(30,160,60)}.row:nth-child(4n+2){background:rgb(30,60,200)}
.row:nth-child(4n+3){background:rgb(200,150,20)}.row:nth-child(4n+4){background:rgb(120,40,160)}
#nav{position:fixed;top:0;left:0;right:0;height:44px;background:rgba(20,20,20,.9);color:#fff;
display:flex;align-items:center;justify-content:center;z-index:2}</style>
<div id=nav>fixed header <input id=q placeholder=search style="margin-left:12px"></div>
<div id=top>top section</div><div id=rows></div>
<script>for(let i=0;i<60;i++){const d=document.createElement('div');d.className='row';
d.textContent='row '+i;rows.appendChild(d)}
addEventListener('click',e=>{document.documentElement.dataset.click=e.clientX+','+e.clientY+','+(e.target.id||e.target.className)},true)</script>
"""

results = []


def record(step, status, detail):
    line = {"step": step, "status": status, "detail": detail}
    results.append(line)
    print(f"{status:4} {step}: {json.dumps(detail)}", flush=True)
    with open(os.path.join(OUT, "results.jsonl"), "a") as f:
        f.write(json.dumps(line) + "\n")


def ctl(*args, timeout=60):
    r = subprocess.run([SPACESCTL, *map(str, args)], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def near(a, b, tol=8):
    return all(abs(a[i] - b[i]) <= tol for i in range(3))


class Site:
    def __init__(self):
        self.dir = os.path.join(OUT, "site")
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, "band.html"), "w") as f:
            f.write(PAGE)
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(  # noqa: E731
            *a, directory=self.dir, **k)
        http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/band.html"


class Run:
    def __init__(self, site, profile=None, prefs=None):
        self.zen = ZenApp(prefs=dict({"browser.startup.page": 3}, **(prefs or {})),
                          profile=profile, keep=True)
        self.m = self.zen.start()
        self.pid = self.zen.proc.pid
        self.site = site

    # --- browser side -----------------------------------------------------
    def chrome(self, script, args=None):
        return self.m.chrome(script, args)

    def state(self):
        return json.loads(self.chrome("return Services.zen.fullPanelState(window)") or "{}")

    def set_pref(self, name, value):
        kind = {bool: "Bool", str: "String", int: "Int"}[type(value)]
        self.chrome(f"Services.prefs.set{kind}Pref(arguments[0], arguments[1])", [name, value])

    def activate(self):
        self.chrome("Cc['@mozilla.org/widget/macdocksupport;1']"
                    ".getService(Ci.nsIMacDockSupport).activateApplication(true)")
        time.sleep(0.8)

    def load(self):
        self.m.navigate(self.site.url)
        self.m.js("window.scrollTo(0, 0)")
        time.sleep(0.5)

    def fullscreen(self, on, timeout=10):
        self.activate()
        self.chrome("window.fullScreen = arguments[0]", [on])
        deadline = time.time() + timeout
        while time.time() < deadline:
            s = self.state()
            if bool(s.get("fullscreen")) == on and self.chrome("return window.fullScreen") == on:
                break
            time.sleep(0.25)
        time.sleep(1.5)  # the Space animation, and the chrome's frame
        return self.state()

    def layout(self):
        return self.chrome("""
          const b = gBrowser.selectedBrowser, r = b.getBoundingClientRect();
          const root = document.documentElement;
          return {outer: [window.outerWidth, window.outerHeight], screen: [screen.width, screen.height],
                  // zen-fullpanel-outer-border is also set outside FullPanel (Zen's own card).
                  y: window.screenY, attrs: [...root.attributes].map(a => a.name)
                    .filter(n => n.startsWith('zen-fullpanel') && n != 'zen-fullpanel-outer-border'),
                  inset: b.browsingContext.zenObscuredTopInset, dpr: window.devicePixelRatio,
                  browser: [r.left, r.top, r.right, r.bottom], fullScreen: window.fullScreen};
        """)

    def quit(self):
        self.zen.stop()


def capture(name):
    path = os.path.join(OUT, name + ".png")
    subprocess.run(["screencapture", "-x", "-D", "1", path], check=True)
    return read_png(path)


def band_check(run, step, scrolled=False):
    """Captures the display and compares the areas beside the housing with
    the page content below the band."""
    s = run.state()
    h = s.get("housing")
    if not h:
        record(step, "FAIL", {"reason": "no housing", "state": s})
        return None
    img = capture(step)
    scale = img.width / s["window"]["width"]
    hb = h["y"] + h["height"]
    left_x = h["x"] - 60
    right_x = h["x"] + h["width"] + 60
    sample = lambda x, y: img.pixel(int(x * scale), int(y * scale))  # noqa: E731
    out = {
        "left_band": sample(left_x, 10), "right_band": sample(right_x, 10),
        "below_band": sample(left_x, hb + 70), "under_cut": sample(h["x"] + h["width"] / 2, hb + 3),
        "scale": scale,
    }
    return out


# --- steps --------------------------------------------------------------------

def step_standard(run):
    run.set_pref("zen.fullpanel.enabled", False)
    run.load()
    s = run.fullscreen(True)
    lay = run.layout()
    ok = s.get("state") == "disabled" and lay["outer"][1] < lay["screen"][1] and not lay["attrs"]
    record("standard: native fullscreen with FullPanel off", "PASS" if ok else "FAIL",
           {"state": s.get("state"), "outer": lay["outer"], "screen": lay["screen"], "attrs": lay["attrs"]})
    s = run.fullscreen(False)
    record("standard: exit", "PASS" if not s.get("fullscreen") else "FAIL", {"state": s.get("state")})


def step_fullpanel(run):
    run.set_pref("zen.fullpanel.enabled", True)
    run.load()
    s = run.fullscreen(True)
    lay = run.layout()
    ok = (s.get("state") == "active" and lay["outer"] == lay["screen"]
          and "zen-fullpanel-active" in lay["attrs"] and lay["inset"] > 0)
    record("fullpanel: whole display, notch scrolling engaged", "PASS" if ok else "FAIL",
           {"state": s.get("state"), "fallback": s.get("fallback"), "outer": lay["outer"],
            "screen": lay["screen"], "housing": s.get("housing"), "attrs": lay["attrs"],
            "inset": lay["inset"], "browser": lay["browser"]})
    pos = run.m.js("const r = document.getElementById('nav').getBoundingClientRect(); return [r.top, innerHeight]")
    record("fullpanel: fixed header below the housing", "PASS" if pos[0] * lay["dpr"] >= lay["inset"] - 1 else "FAIL",
           {"navTop": pos[0], "inset_css": lay["inset"] / lay["dpr"]})


def step_band(run):
    b = band_check(run, "band-at-top")
    if b:
        ok = near(b["left_band"], b["below_band"]) and near(b["right_band"], b["below_band"])
        record("band: at rest, Solid Color continues the page's top", "PASS" if ok else "FAIL", b)
    run.m.js("window.scrollTo(0, 420)")
    time.sleep(0.8)
    b2 = band_check(run, "band-scrolled")
    if b and b2:
        ok = not near(b2["left_band"], b["left_band"], 20)
        record("band: scrolled content shows beside the housing", "PASS" if ok else "FAIL", b2)
    hit = run.m.js("const e = document.elementFromPoint(40, 10); return e && e.className")
    record("band: hit testing in the band reaches the page", "PASS" if hit == "row" else "FAIL", {"hit": hit})
    run.m.js("window.scrollTo(0, 0)")
    time.sleep(0.8)
    b3 = band_check(run, "band-back-at-top")
    if b and b3:
        record("band: back at the top, no gap or seam", "PASS" if near(b3["left_band"], b["left_band"]) else "FAIL", b3)
    # Inner border: the card is cut away under and around the housing.
    if b:
        record("inner border: housing cut shows the gap, not the page", "PASS"
               if not near(b["under_cut"], b["below_band"], 20) else "FAIL", b)


def step_reveal(run):
    s = run.state()
    h = s["housing"]
    ctl("move", 200, 0)
    time.sleep(1.6)
    img = capture("reveal-shown")
    scale = img.width / s["window"]["width"]
    shown = img.pixel(int(200 * scale), int(12 * scale))
    ctl("move", h["x"] - 200, 600)
    time.sleep(2.0)
    img2 = capture("reveal-hidden")
    hidden = img2.pixel(int(200 * scale), int(12 * scale))
    lay = run.layout()
    record("menu bar: revealed from the top edge, hidden again", "PASS"
           if not near(shown, hidden, 10) and run.state().get("state") == "active" else "FAIL",
           {"shown": shown, "hidden": hidden, "outer": lay["outer"]})


def step_cycles(run):
    statuses = []
    for _ in range(3):
        s = run.fullscreen(False)
        lay = run.layout()
        statuses.append(("exit", s.get("state"), lay["inset"], lay["attrs"]))
        s = run.fullscreen(True)
        lay = run.layout()
        statuses.append(("enter", s.get("state"), lay["inset"], lay["outer"] == lay["screen"]))
    ok = all((st[1] == "inactive" and st[2] == 0 and st[3] == []) if st[0] == "exit"
             else (st[1] == "active" and st[2] > 0 and st[3]) for st in statuses)
    record("exit and re-entry x3", "PASS" if ok else "FAIL", {"cycles": statuses})


def step_switch(run):
    # In FullPanel: switch the pref off; this entry keeps FullPanel.
    run.set_pref("zen.fullpanel.enabled", False)
    time.sleep(0.5)
    kept = run.state().get("state")
    run.fullscreen(False)
    s = run.fullscreen(True)
    lay = run.layout()
    standard = s.get("state") == "disabled" and lay["outer"][1] < lay["screen"][1]
    run.set_pref("zen.fullpanel.enabled", True)
    time.sleep(0.5)
    still = run.layout()["outer"][1] < lay["screen"][1]
    run.fullscreen(False)
    s2 = run.fullscreen(True)
    back = s2.get("state") == "active" and run.layout()["outer"] == lay["screen"]
    record("mode switch: applies from the next entry, both directions",
           "PASS" if kept == "active" and standard and still and back else "FAIL",
           {"kept": kept, "standard_outer": lay["outer"], "standard_state": s.get("state"),
            "standard_kept_until_exit": still, "fullpanel_again": s2.get("state")})


def step_missioncontrol(run):
    rows = []
    for route in ("escape", "thumbnail"):
        run.activate()
        ctl("key", 126, "ctrl", "fn")  # Mission Control
        time.sleep(1.8)
        if route == "escape":
            ctl("key", 53)
        else:
            line = ctl("space", run.pid)
            idx = int(line.split("index=")[1].split()[0])
            count = int(line.split("count=")[1].split()[0])
            pt = ctl("bar", "builtin", count, idx).split()
            if len(pt) >= 2:
                ctl("click", pt[0], pt[1])
            else:
                ctl("key", 53)
        time.sleep(2.5)
        line = ctl("space", run.pid)
        s = run.state()
        lay = run.layout()
        b = band_check(run, f"mc-{route}")
        rows.append({"route": route, "space": line, "state": s.get("state"), "outer": lay["outer"],
                     "band": b and near(b["left_band"], b["below_band"])})
    ok = all(" shown=1" in f" {r['space']}" and r["state"] == "active" and r["band"] for r in rows)
    record("Mission Control return", "PASS" if ok else "FAIL", {"routes": rows})


def step_spaces(run):
    run.activate()
    ctl("key", 123, "ctrl", "fn")
    time.sleep(2.0)
    away = ctl("space", run.pid)
    ctl("key", 124, "ctrl", "fn")
    time.sleep(2.5)
    back = ctl("space", run.pid)
    s = run.state()
    b = band_check(run, "space-return")
    ok = " shown=0" in f" {away}" and " shown=1" in f" {back}" and s.get("state") == "active" and b and near(b["left_band"], b["below_band"])
    record("Space switch away and back (Control-arrows)", "PASS" if ok else "FAIL",
           {"away": away, "back": back, "state": s.get("state")})


def to_desktop_with_finder():
    ctl("key", 123, "ctrl", "fn")
    time.sleep(2.0)
    subprocess.run(["osascript", "-e", 'tell application "Finder" to activate'], check=False)
    time.sleep(1.2)


def step_dock(run, dock_title):
    to_desktop_with_finder()
    before = ctl("front")
    ctl("dock", dock_title)
    time.sleep(3.0)
    line = ctl("space", run.pid)
    front = ctl("front")
    s = run.state()
    ok = " shown=1" in f" {line}" and s.get("state") == "active"
    record("Dock click activation from the desktop", "PASS" if ok else "FAIL",
           {"before": before, "front": front, "space": line, "state": s.get("state"),
            "menu_bar_only": "shown=0" in line and dock_title.split()[0] in front})


def step_cmdtab(run):
    to_desktop_with_finder()
    before = ctl("front")
    ctl("cmdtab", 1)
    time.sleep(3.0)
    line = ctl("space", run.pid)
    front = ctl("front")
    s = run.state()
    ok = " shown=1" in f" {line}" and s.get("state") == "active"
    record("Command-Tab activation from the desktop", "PASS" if ok else "FAIL",
           {"before": before, "front": front, "space": line, "state": s.get("state"),
            "menu_bar_only": "shown=0" in line})


def step_display(run):
    modes = ctl("modes")
    with open(os.path.join(OUT, "modes.txt"), "w") as f:
        f.write(modes)
    # The current scale without the housing band (1800x1169 -> 1800x1125 on
    # the 14-inch panel), at the current refresh rate.
    current = next((l.split() for l in modes.splitlines() if l.endswith("current")), None)
    pick = None
    if current:
        w, h = current[1].split("x")
        for line in modes.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[1].split("x")[0] == w and parts[1] != current[1] \
                    and int(parts[1].split("x")[1]) < int(h) and parts[3] == current[3]:
                pick = parts[0]
    if not pick:
        record("display mode change", "INFO", {"reason": "no housing-less mode found", "modes": modes[:500]})
        return
    run.activate()
    hold = subprocess.Popen([SPACESCTL, "modehold", pick, "10"], stdout=subprocess.DEVNULL)
    time.sleep(5)
    during = run.state()
    lay = run.layout()
    hold.wait()
    time.sleep(4)
    after = run.state()
    lay2 = run.layout()
    ok = during.get("state") == "fallback" and during.get("fallback") == "noCameraHousing" and not lay["attrs"]
    record("display without a housing: ordinary fullscreen", "PASS" if ok else "FAIL",
           {"mode": pick, "during": {k: during.get(k) for k in ("state", "fallback")}, "attrs": lay["attrs"],
            "outer": lay["outer"]})
    record("display back with the housing", "PASS" if after.get("state") in ("active", "fallback") else "FAIL",
           {"after": {k: after.get(k) for k in ("state", "fallback")}, "outer": lay2["outer"],
            "attrs": lay2["attrs"]})


def step_restore(run, site):
    profile = run.zen.profile
    run.quit()
    time.sleep(2)
    global RUN
    run2 = Run(site, profile=profile)
    RUN = run2
    time.sleep(3)
    run2.activate()
    s = run2.state()
    lay = run2.layout()
    record("restore: relaunch restores the window", "INFO",
           {"state": s.get("state"), "fullscreen": s.get("fullscreen"), "fallback": s.get("fallback"),
            "outer": lay["outer"], "tabs": run2.chrome("return gBrowser.tabs.length")})
    if s.get("fullscreen"):
        run2.fullscreen(False)
    s = run2.fullscreen(True)
    lay = run2.layout()
    record("restore: next entry is FullPanel", "PASS" if s.get("state") == "active" and lay["outer"] == lay["screen"]
           else "FAIL", {"state": s.get("state"), "outer": lay["outer"]})
    return run2


RUN = None
ALL = ["standard", "fullpanel", "band", "reveal", "cycles", "switch", "missioncontrol", "spaces",
       "dock", "cmdtab", "display", "restore"]


def main():
    global RUN
    if os.environ.get("ZEN_HARDWARE") != "1" or not os.path.exists(SPACESCTL):
        sys.exit("Refusing: set ZEN_HARDWARE=1 and SPACESCTL (this run takes over the display).")
    steps = sys.argv[1:] or ALL
    os.makedirs(OUT, exist_ok=True)
    alerts = ctl("alerts")
    if alerts and "none" not in alerts.lower():
        sys.exit(f"A system dialog is on screen; not starting: {alerts}")
    site = Site()
    RUN = Run(site)
    app = RUN.zen.app
    dock_title = os.path.basename(app)[:-4]
    print(f"app {app} pid {RUN.pid} out {OUT}", flush=True)
    try:
        for step in steps:
            try:
                if step in ("band", "reveal", "cycles", "switch", "missioncontrol", "spaces", "dock",
                            "cmdtab", "display") and not RUN.state().get("active"):
                    RUN.set_pref("zen.fullpanel.enabled", True)
                    RUN.load()
                    RUN.fullscreen(True)
                if step == "dock":
                    step_dock(RUN, dock_title)
                elif step == "restore":
                    RUN = step_restore(RUN, site)
                else:
                    globals()[f"step_{step}"](RUN)
            except Exception as e:
                record(step, "FAIL", {"exception": repr(e), "trace": traceback.format_exc()[-800:]})
    finally:
        try:
            if RUN.state().get("fullscreen"):
                RUN.fullscreen(False)
        except Exception:
            pass
        RUN.quit()
        shutil.copy(os.path.join(RUN.zen.profile, "browser.log"), os.path.join(OUT, "browser.log"))
        passed = sum(r["status"] == "PASS" for r in results)
        failed = sum(r["status"] == "FAIL" for r in results)
        print(f"\n{passed} passed, {failed} failed; {OUT}")


if __name__ == "__main__":
    main()
