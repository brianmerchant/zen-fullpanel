# zen-fullpanel

Zen Browser (stable 1.23.3b, Firefox 158.0) with native **FullPanelKit**
fullscreen on MacBooks with a camera housing, and Talos's iPhone-style notch
scrolling. Unofficial; not affiliated with the Zen team.

- Fork: https://github.com/brianmerchant/zen-fullpanel, branch
  `feature/zen-fullpanel`
- Upstream baseline: tag `1.23.3b` = `6adb8106286306d882008e5f886367d91dbef740`
  (zen-browser/desktop, release published 2026-10-16)
- FullPanelKit: `e1f0b0b` (branch `fix/pinned-titlebar-reveal`: v0.1.0 plus
  the reveal-latch fix for opaque titlebar windows), vendored unmodified (MIT)
- [BUILDING.md](BUILDING.md) · [TESTING.md](TESTING.md) ·
  [IDENTITY.md](IDENTITY.md) · [AUDIT.md](AUDIT.md)

## What it does

Fullscreen is always AppKit's own native fullscreen Space: the green button,
View > Enter Full Screen, Control-Command-F, and windows restored into
fullscreen at launch. Tools > Browser Tools > **Fullscreen** chooses how:

| Menu item | Pref (persisted per profile) | Default |
|---|---|---|
| Standard Native Fullscreen / FullPanel Fullscreen | `zen.fullpanel.enabled` | Standard (opt-in) |
| Window Border > Inner Border | `zen.fullpanel.inner-border` | on |
| Window Border > Outer Border | `zen.fullpanel.outer-border` | on |
| Notch Scrolling Mode > Solid Color / Off | `zen.fullpanel.notch-scroll-mode` | Solid Color |

- **Standard**: Zen's fullscreen, unchanged (the window stops below the
  camera housing band).
- **FullPanel**: the same native fullscreen Space, but the window covers the
  whole display (1800 × 1169 on the 14-inch MacBook Pro), including the
  areas beside the housing. The menu bar is hidden and slides in from the
  top edge as usual. A mode switch made while in fullscreen applies from the
  next entry; everything else applies at once. On a display without a
  housing, or if a private AppKit/SkyLight interface is unavailable, it is
  ordinary fullscreen (FullPanelKit's fallback; the menu shows why).
- **Solid Color notch scrolling** (Talos): a page whose top lies under the
  housing starts below it, exactly as in a slightly shorter window (fixed
  and sticky headers included), and scrolls up into the band beside the
  housing. At rest the band shows the page's top-edge color.
  **Off**: the content area starts below the housing.
- **Inner Border**: the page card is cut away around the housing (with the
  card's gap as clearance) and outlined along the cut; nothing of the page
  is drawn or clickable under the housing. **Outer Border**: Zen's gap and
  rounded corners around the page card; off, the page runs edge to edge.

Ordinary (windowed) browsing and every non-browser window are untouched.

## How it works

```
nsCocoaWindow (Gecko)                       browser chrome (JS/CSS)
  SetWindowClass("navigator:browser")         ZenFullPanel.mjs
    └ zen::fullpanel::AttachBrowserWindow       ├ Services.zen.fullPanelState(window)  → JSON
        └ FullPanelSession.attach(ToolbarWindow) ├ "zen-fullpanel-state-changed" observer
            enabled ← zen.fullpanel.enabled      ├ root attributes + housing CSS variables
  DestroyNativeWindow → detach                   ├ BrowsingContext.zenObscuredTopInset (device px)
  window recreation  → attach again              ├ clip-path cut + SVG outline (inner border)
                                                 └ Tools > Browser Tools > Fullscreen menu
Gecko layout (content process)
  zen::ObscuredTopInset(presContext)
    nsCanvasFrame: root element and ICB start below the inset; Solid Color band
    ViewportFrame: fixed containing block starts below it
    StickyScrollContainer: sticky limits start below it
    ScrollContainerFrame: scroll padding (scrollIntoView, fragments, find)
    ReflowInput: static positions of fixed/abs boxes
```

FullPanelKit attaches to Gecko's own `NSWindow` subclass (`ToolbarWindow`)
without changing its class, delegate or frame handling; it answers AppKit's
private "reserve the menu-bar band?" question for that window only, and
manages the menu-bar overlay and Mission Control returns. Gecko's
`ToolbarWindow` already uses a full-size content view, so enabling FullPanel
causes no frame shift.

## Source changes

Zen's own code (`src/zen/`, copied into `engine/zen/` by `npm run import`):

- `src/zen/toolkit/common/cocoa/fullpanel/` — `ZenFullPanel.{h,mm}` adapter,
  `FullPanelKitCore/` (vendored SDK, `UPSTREAM.json`, `moz.build` with the
  MIT `LICENSES` declaration)
- `src/zen/toolkit/common/ZenObscuredInset.{h,cpp}` — inset accessor and the
  Solid Color band sampler; `nsIZenCommonUtils.idl`, `ZenCommonUtils.cpp`
  (`fullPanelState`)
- `src/zen/common/modules/ZenFullPanel.mjs`, `src/zen/common/styles/zen-fullpanel.css`
- `prefs/zen/fullpanel.yaml`, `locales/en-US/browser/browser/zen-fullpanel.ftl`
- registrations: `src/zen/common/{jar.inc.mn,ZenPreloadedScripts.js}`,
  `src/browser/base/content/zen-assets.inc.xhtml`,
  `src/zen/toolkit/common/{moz.build,cocoa/moz.build}`

### Gecko changes

Tracked as Surfer patches under `src/` and re-applied by every import:

| Patch | Change |
|---|---|
| `src/toolkit/moz-configure.patch` (extends Zen's) | `ZEN_APP_PROFILE` env option implying `MOZ_APP_PROFILE` (fork identity) |
| `src/widget/cocoa/nsCocoaWindow-mm.patch` (extends Zen's) | attach in `SetWindowClass` and after native-window recreation; detach in `DestroyNativeWindow` |
| `src/docshell/base/BrowsingContext-h.patch` (extends Zen's) | synced field `ZenObscuredTopInset` (top-level, embedder-set, ≥ 0) |
| `src/dom/chrome-webidl/BrowsingContext-webidl.patch` (extends Zen's) | `zenObscuredTopInset` attribute |
| `src/docshell/base/CanonicalBrowsingContext-cpp.patch` | carry the field across BrowsingContext replacement |
| `src/layout/generic/nsCanvasFrame-cpp.patch` | root element and ICB below the inset; Solid Color band item |
| `src/layout/generic/ViewportFrame-cpp.patch` | fixed containing block below the inset |
| `src/layout/generic/StickyScrollContainer-cpp.patch` | sticky limits below the inset |
| `src/layout/generic/ScrollContainerFrame-cpp.patch` | root scroll padding includes the inset |
| `src/layout/generic/ReflowInput-cpp.patch` | hypothetical (static) positions use the offset containing blocks |

Fork identity: `surfer.json` (`fullpanel` brand), `configs/branding/fullpanel/`,
`configs/macos/mozconfig` (identity block) — see [IDENTITY.md](IDENTITY.md).
