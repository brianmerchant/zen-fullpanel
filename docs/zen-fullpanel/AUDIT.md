# Phase 1 audit (2026-10-20)

What existed before the zen-fullpanel fork, what was reused, and what was
kept aside. Nothing listed here was deleted.

## Zen checkout `~/Projects/Zen-FullPanelKit/zen-desktop`

| Item | Found |
|---|---|
| Clone | Shallow, partial (`blob:none`), grafted at `185e856` = tag `1.23.2b` (Firefox 157.0.1) |
| Remote | `origin` = zen-browser/desktop, fetching `stable` only. Now `upstream` (push disabled); `origin` = brianmerchant/zen-fullpanel |
| Branches | `stable` and `feature/fullpanelkit-macos` both at `185e856` (no own commits); `experiment/notch-scroll` = `e9854cb` (FullPanel adapter, old vendored SDK) → `921baf2` (Gecko obscured top inset) → `bf62c92` (top-edge band color) |
| Working tree | Clean; no stashes |
| `engine/` | 19 GB: Firefox 157.0.1 + Zen 1.23.2b + experiment patches, 308 modified files; objdir 14 GB |
| Build output | `dist/Nightly.app`, dev build, `--with-branding=browser/branding/unofficial`, update channel `unofficial` |
| `.surfer` | No `dynamicConfig.brand.json` / `buildMode.json`: brand defaulted to `unofficial` |

Moved, not deleted: `engine/` → `~/Projects/Zen-FullPanelKit/archive/engine-157.0.1-experiment-notch-scroll/`,
`.surfer` copy → `archive/surfer-state-157.0.1/` (see `archive/README.md`).
The objdir uses absolute paths; move it back to rebuild it. Freeing its
19 GB is the owner's call.

### Why the earlier build was "Nightly with an incomplete Zen UI"

1. **Brand never selected.** Upstream CI runs `surfer ci --brand release`
   before `download`/`import`/`build`. Without it Surfer's dynamic config
   defaults to `brand=unofficial`, `buildMode=dev`: Mozilla's unofficial
   branding, bundle `Nightly.app`, channel `unofficial`.
2. **Zen's strings never reached the engine.** Upstream's
   `scripts/download-language-packs.sh` ends with
   `scripts/copy_language_pack.py`, which copies `locales/en-US/browser/**`
   (all 14 `zen-*.ftl`, including `zen-menubar.ftl`) into
   `engine/browser/locales/en-US`. The archived engine has **0** `zen*` files
   there, so every Zen menu and label with a `data-l10n-id` rendered empty.
   This is the "missing menu" failure. `surfer import` itself succeeded
   (all patches applied).

Fixed in the procedure (BUILDING.md); `test_zen_baseline.py` now fails on
either: it checks the bundle name, channel, version and that every visible
menubar item has a label.

## Reusable work found

| Source | Commit | Reused as |
|---|---|---|
| Zen `experiment/notch-scroll` | `921baf2`, `bf62c92` | Gecko layout patches (canvas, reflow, viewport, sticky, scroll padding) applied unchanged to Firefox 158; BrowsingContext field re-derived on top of 1.23.3b's own patches; `ZenObscuredInset` band sampler, aligned with Talos Solid Color; chrome module structure; fixtures and layout tests |
| Zen `experiment/notch-scroll` | `e9854cb` | **Not reused**: vendored a pre-release SDK (`ff07917`) and a 922-line controller that copied the engine and added `BaseWindow` frame-setter forwarding and `window:willUseFullScreenContentSize:`. FullPanelKit 0.1.0 attaches to an application's own `NSWindow` subclass without any of that |
| Talos `feature/fullpanelkit-macos` | `34834f1` (on `7736280`) | Solid Color semantics (`WebViewNotchScroll.swift`), inset rule (housing bottom + gutter clearance, only when the page is under the housing), Develop toggles (FullPanel Fullscreen, Inner Border, Outer Border, Notch Band), notch cutout geometry (`BrowserInterfaceMask.swift`) |
| Talos | `2b61086` (reverted by `7736280`) | **Not reproduced**: re-entering a restored fullscreen window through FullPanel bounced new windows. Zen likewise leaves a window restored straight into fullscreen in ordinary fullscreen until its next entry (FullPanelKit `.fallback` with an adoption diagnostic) |
| Chromeless `experiment/notch-claude` | `b6c6407` | Compared only. Its `hybrid` mode (per-document collision detector, per-origin hints) is a WebKit workaround and was not ported; its band color lacks the fixed-subtree rule Talos uses |
| FullPanelKit | tag `v0.1.0` = `1911fa2` (`main` = `e5feaf7`, docs only since) | Core sources vendored unmodified; since `ce83d59` from `e1f0b0b` (`fix/pinned-titlebar-reveal`, the reveal-latch fix; see TESTING.md "Root cause") |

### Solid Color: Talos vs the earlier Zen band

| | Talos Solid Color | Earlier Zen (`bf62c92`) | zen-fullpanel |
|---|---|---|---|
| Samples | 15 %, 50 %, 85 % of the width, 6 px below the band | center ± 150 px | Talos |
| Vote | two equal samples, else the middle | center = right, else left | Talos |
| Translucent top element | alpha-composited over what is behind | a ≥ 50 % opaque layer's own tint | Talos |
| Fixed/sticky-position subtrees | skipped | skipped | same |
| Gradient | top stop of a vertical linear gradient | same | same |
| Canvas | html/body background, else WebKit's base | Gecko's canvas background | Gecko's (what Gecko actually paints) |
| Update | load milestones, mutations/transitions/image loads (250 ms throttle), resize, return to top | after each reflow at the top | after each reflow, and ≤ 250 ms after paints, at the top |
| Cross-fade | none for Solid (only snapshot styles fade) | none | none |

## Other locations (untouched)

- `~/Projects/FullPanelKit` `main` `e5feaf7`, clean, = GitHub.
- `~/Projects/Talos-FullPanelKit` `34834f1`, clean.
- `~/Projects/Chromeless` `b6c6407`.
- `~/Library/Application Support/zen` (4 profiles, `installs.ini`/`profiles.ini`
  last modified 2026-10-12). No stock `Zen.app` is installed.
