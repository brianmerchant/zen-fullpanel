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
