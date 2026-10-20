# Testing zen-fullpanel

All suites drive a built app through Marionette (`scripts/fullpanel/zentest.py`,
a protocol client: release builds have no test harness) with a throwaway
profile under `~/Projects/Zen-FullPanelKit/test-profiles/`. Updates and
telemetry are off in these profiles; no user profile is opened. `ZEN_APP`
selects the bundle (default: `engine/obj-*/dist/*.app`).

| Suite | What | Needs |
|---|---|---|
| `python3 -I scripts/fullpanel/verify-vendor.py ~/Projects/FullPanelKit` | vendored FullPanelKit is byte-identical to its release | — |
| `python3 scripts/fullpanel/test_zen_baseline.py -v` | the build is the complete Zen browser: identity, Zen UI, every menubar item labelled, Zen strings, tabs, navigation, windows, settings (Zen panes), sidebar, download, extension, scrolling, audio, video | a build |
| `python3 scripts/fullpanel/notch-scroll/test_notch_scroll.py -v` | Gecko notch layout and the Solid Color band in an ordinary window (inset set directly) | a FullPanel build |
| `python3 scripts/fullpanel/test_fullpanel_chrome.py -v` | native session per browser window and the pref; chrome layout with an injected FullPanel state; the menu | a FullPanel build |
| `ZEN_HARDWARE=1 SPACESCTL=… python3 scripts/fullpanel/hardware_fullscreen.py` | real native fullscreen on the notched display (see below) | the Mac, unattended, Accessibility + Screen Recording |
| `python3 scripts/fullpanel/notch-scroll/drive_sites.py` | informational: public sites with and without the inset | network |

For a stock-identity build set nothing; for Zen FullPanel:

```sh
export ZEN_EXPECT_NAME="Zen FullPanel" ZEN_EXPECT_BUNDLE_ID=io.github.brianmerchant.fullpanel.zen \
       ZEN_EXPECT_CHANNEL=fullpanel
```

## Hardware run

`hardware_fullscreen.py` takes over the display for a few minutes and uses
FullPanelKit's `spacesctl` for system input (build it outside the
FullPanelKit checkout: `swift build -c debug --product spacesctl
--scratch-path <dir>` in `Tools/SpacesHarness`). Steps, each PASS/FAIL with
measurements in `~/Projects/Zen-FullPanelKit/test-runs/<time>/`:

1. `standard` — FullPanel off: native fullscreen is camera-safe (1800 × 1130), no FullPanel chrome.
2. `fullpanel` — FullPanel on: the window covers the display (1800 × 1169), housing reported, inset engaged, a fixed header stays below the housing.
3. `band` — screen captures: at rest the areas beside the housing match the page's top; scrolled, page content shows there and is hit-testable; back at the top, no seam; the inner border's cut shows the gap.
4. `reveal` — the menu bar slides in at the top edge and hides again.
5. `cycles` — three exits and re-entries.
6. `switch` — Standard ↔ FullPanel while in fullscreen applies from the next entry.
7. `missioncontrol` — Mission Control returns (Escape, Space thumbnail).
8. `spaces` — Control-arrow away and back.
9. `dock`, `cmdtab` — activation from the desktop by Dock click and Command-Tab: the fullscreen Space must come forward (the known FullPanelKit issue: activation selects the menu bar without showing the Space).
10. `display` — the built-in panel in a mode without the housing (`spacesctl modehold`): ordinary fullscreen, then back.
11. `restore` — quit in fullscreen, relaunch the same profile.

## Manual acceptance (not automatable here)

- Trackpad scrolling and rubber-band at the top of a page in FullPanel.
- Clicking and typing in a page element scrolled beside the housing.
- Video in DOM fullscreen (YouTube `f`) from FullPanel fullscreen.
- Split View tiling (FullPanelKit rejects it: ordinary tile).
- External display with "Displays have separate Spaces".

## Results

See the end of this file (filled in per run).

### 2026-10-20, MacBook Pro 14" (M1 Pro), macOS 27.0.1

Stock baseline (1.23.3b `6adb810`, release brand, `Zen.app`):

| Suite | Result |
|---|---|
| `test_zen_baseline.py` | 14/14 OK (menubar: 88 items, 0 unlabelled; Zen's Spaces menu and panes present) |
| Window capture | Zen's sidebar UI (URL field, Spaces, New Tab, update card) |
| Native fullscreen | 1800 × 1130 (camera-safe) on the 1800 × 1169 display, back to the window |

Zen FullPanel (`ce63685`, `fullpanel` brand), both the objdir bundle and the
staged self-contained app (`~/Projects/Builds/Zen-FullPanel/staging/ce63685-fpk1911fa2`):

| Suite | Result |
|---|---|
| `verify-vendor.py` | 25 files identical to FullPanelKit v0.1.0 |
| `test_zen_baseline.py` (Zen FullPanel identity) | 14/14 OK |
| `test_fullpanel_chrome.py` | 16/16 OK |
| `notch-scroll/test_notch_scroll.py` | 20/20 OK |
| User profile folder `~/Library/Application Support/zen` | unchanged (mtimes compared before and after) |

Found and fixed while testing: inline style cannot set the chrome-only
`-moz-scrollbar-inset-block` (now set from `zen-fullpanel.css`); a brand
switch in an existing objdir left the old brand strings (BUILDING.md); Zen's
post-update overlay covered the window in fresh profiles, which had made a
hit-test assertion pass trivially (test profiles now skip it).

Hardware run (`hardware_fullscreen.py`, staged app `ce63685`, built-in
1800 × 1169 @120 Hz, unattended; runs `test-runs/20261020-165429`, `-170200`):

| Step | Result |
|---|---|
| Standard native fullscreen (FullPanel off) | PASS — 1800 × 1130, no FullPanel chrome; exit PASS |
| FullPanel fullscreen | PASS — window 1800 × 1169 = display; housing 220 × 38 pt at x 790; inset 38 pt; the page's fixed header at 38 |
| Band at rest (screen capture) | PASS — left and right of the housing = the page's top section; the inner-border cut shows the gap |
| Band scrolled | PASS — page rows beside the housing; hit test in the band reaches the row |
| Band back at the top | PASS — same pixels as before, no seam |
| Exit and re-entry × 3 | PASS — inactive with inset 0 after each exit; active, full display, inset 38 after each entry |
| Mode switch in fullscreen, both directions | PASS — applies from the next entry |
| Dock click from the desktop (Finder front) | PASS — fullscreen Space shown, app front, still active |
| Command-Tab from the desktop | PASS — same; the "menu bar only" activation did not occur |
| Display without the housing (1800 × 1125, `modehold`) | PASS — ordinary fullscreen, fallback `noCameraHousing`, FullPanel chrome off; back with the housing: active again in the same entry |
| Relaunch after quitting in fullscreen | INFO — Zen restores the window and tab **windowed** (1800 × 1130), not in fullscreen; the next entry is FullPanel (PASS) |
| Menu bar reveal at the top edge | NOT VERIFIED — a synthetic pointer warp to y = 0 did not reveal the menu bar (captures identical); needs a real pointer |
| **Mission Control return (Escape; Space thumbnail)** | **FAIL** — see below |
| **Space switch away and back** | **FAIL** — see below |

#### FullPanelKit defect: black menu-bar band after any Space return

After Mission Control (either route) or a Control-arrow Space switch, the
window's Space comes back (`shown=1`), the session stays `active` and the
window keeps the whole display, but the band beside the housing is opaque
black and stays so (sampled at 0.5, 1.5, 3, 6 and 10 s) until fullscreen is
left and re-entered. Content below the band is correct.

FullPanelKit's trace (`-FullPanelTrace` via the app's defaults domain): on
opening Mission Control it logs `reveal visible=1 source=titlebar-alpha`
and sets `overlay backdrop=opaque`; every later return re-applies
`backdrop=opaque`. `FPKFullScreenTitlebar -reread` treats the menu bar as
revealed while the fullscreen titlebar window's alpha is > 0.01, and only
un-reveals when it drops to ≤ 0.01. For Gecko's `ToolbarWindow` that alpha is
**1.00 while the menu bar is hidden** (`titlebar-followed … alpha=1.00 …
reveal=0` right after entry), so the first transient "menu bar visible"
latches the reveal for the rest of the session. Likely trigger, not
verified: Gecko adds a titlebar accessory view controller to
`ToolbarWindow` (to shift its toolbar with the menu bar), which keeps that
titlebar window opaque; a real top-edge reveal will most likely latch the
same way.

With FullPanelKit's documented `FullPanelRevealIntegration` option off
(user default, measured, then removed), the same returns keep the correct
band for 10 s (`test-runs/20261020-170037`). The fix belongs in FullPanelKit's
reveal sensing (it cannot assume the titlebar window fades); Zen ships
unchanged.
