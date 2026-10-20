// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.

// FullPanel fullscreen in the browser chrome (macOS).
//
// The native side (ZenFullPanel.mm, FullPanelKit) gives a browser window a
// native fullscreen Space that also covers the areas beside the camera
// housing. This module lays the chrome out around the housing:
//
// - Notch scrolling "solid" (default, Talos's Solid Color): a page whose top
//   lies under the housing gets an obscured top inset (BrowsingContext
//   zenObscuredTopInset). Gecko lays the page out below the housing and lets
//   it scroll up into the band beside it; at rest the band shows the page's
//   top-edge color (ZenObscuredInset.cpp). "off": the content area starts
//   below the housing instead.
// - Window border (Talos's Develop toggles): the inner border cuts the page
//   card away around the housing and outlines the cut; the outer border is
//   Zen's gap and rounded corners around the card.
// - Tools > Browser Tools > Fullscreen switches all of this.
//
// Everything is driven by events (native state notifications, prefs,
// fullscreen, resize, tab changes) and coalesced into one animation frame.
// Outside FullPanel fullscreen nothing here changes the layout.

const PREF_ENABLED = "zen.fullpanel.enabled";
const PREF_MODE = "zen.fullpanel.notch-scroll-mode";
const PREF_INNER = "zen.fullpanel.inner-border";
const PREF_OUTER = "zen.fullpanel.outer-border";
const PREFS = [PREF_ENABLED, PREF_MODE, PREF_INNER, PREF_OUTER];
const STATE_TOPIC = "zen-fullpanel-state-changed";
const MODES = ["solid", "off"];
const SVG_NS = "http://www.w3.org/2000/svg";

// Measured from photos of the display: macOS publishes only the housing's
// rectangle (Talos NotchCutoutModifier).
const HOUSING_CORNER_RADIUS = 6;
const SHOULDER_RADIUS = 6;

class nsZenFullPanel {
  #state = {};
  #frame = 0;
  #housing = null; // CSS px, window coordinates, while active.
  #insets = new WeakMap(); // browser -> device px last set
  #resizeObserver = null;
  #outline = null;
  #menu = null;

  // Automated tests only (scripts/fullpanel/test_fullpanel_chrome.py): a
  // native state to use instead of the window's own, then update().
  testState = null;

  constructor() {
    window.addEventListener("load", () => this.#init(), { once: true });
  }

  get mode() {
    const mode = Services.prefs.getStringPref(PREF_MODE, "solid");
    return MODES.includes(mode) ? mode : "solid";
  }

  #init() {
    window.MozXULElement.insertFTLIfNeeded("browser/zen-fullpanel.ftl");
    Services.obs.addObserver(this, STATE_TOPIC);
    for (const pref of PREFS) {
      Services.prefs.addObserver(pref, this);
    }
    for (const name of [
      "resize",
      "fullscreen",
      "sizemodechange",
      "MozDOMFullscreen:Entered",
      "MozDOMFullscreen:Exited",
    ]) {
      // Capture: DOM fullscreen events are dispatched at the <browser>.
      window.addEventListener(name, this, true);
    }
    window.addEventListener("TabSelect", this);
    window.addEventListener("TabBrowserInserted", this);
    this.#resizeObserver = new window.ResizeObserver(() => this.update());
    const tabbox = document.getElementById("tabbrowser-tabbox");
    if (tabbox) {
      // Toolbar mode, sidebar and split changes move the content area.
      this.#resizeObserver.observe(tabbox);
    }
    this.#initMenu();
    window.addEventListener("unload", () => this.#uninit(), { once: true });
    this.update();
  }

  #uninit() {
    Services.obs.removeObserver(this, STATE_TOPIC);
    for (const pref of PREFS) {
      Services.prefs.removeObserver(pref, this);
    }
    this.#resizeObserver?.disconnect();
    if (this.#frame) {
      window.cancelAnimationFrame(this.#frame);
      this.#frame = 0;
    }
  }

  observe() {
    this.update();
  }

  handleEvent(event) {
    if (event.type === "TabBrowserInserted") {
      // Synchronously, so a new tab's first layout already has its inset.
      const browser = event.target.linkedBrowser;
      if (browser) {
        this.#applyBrowser(browser, this.#selectedRect());
      }
      return;
    }
    this.update();
  }

  // Native notifications and DOM fullscreen events arrive in either order:
  // coalesce after the current dispatch, without a polling timer.
  update() {
    if (this.#frame) {
      return;
    }
    this.#frame = window.requestAnimationFrame(() => {
      this.#frame = 0;
      this.#apply();
    });
  }

  #readState() {
    if (this.testState) {
      return this.testState;
    }
    try {
      return JSON.parse(Services.zen.fullPanelState(window)) || {};
    } catch (e) {
      console.error("ZenFullPanel: cannot read the native state", e);
      return {};
    }
  }

  #apply() {
    const state = (this.#state = this.#readState());
    const root = document.documentElement;
    // Fullscreen web content (video) covers the whole display itself.
    const active =
      !!state.active && !!state.housing && !document.fullscreenElement;

    root.toggleAttribute("zen-fullpanel-active", active);
    root.toggleAttribute("zen-fullpanel-notch-scroll", active && this.mode === "solid");
    root.toggleAttribute(
      "zen-fullpanel-inner-border",
      active && Services.prefs.getBoolPref(PREF_INNER, true)
    );
    root.toggleAttribute(
      "zen-fullpanel-outer-border",
      !active || Services.prefs.getBoolPref(PREF_OUTER, true)
    );

    if (active) {
      // Points to CSS pixels of this chrome document.
      const scale = window.desktopToDeviceScale / window.devicePixelRatio;
      const h = state.housing;
      this.#housing = {
        left: h.x * scale,
        top: h.y * scale,
        right: (h.x + h.width) * scale,
        bottom: (h.y + h.height) * scale,
      };
      root.style.setProperty("--zen-fullpanel-housing-left", `${this.#housing.left}px`);
      root.style.setProperty("--zen-fullpanel-housing-right", `${this.#housing.right}px`);
      root.style.setProperty("--zen-fullpanel-housing-bottom", `${this.#housing.bottom}px`);
    } else {
      this.#housing = null;
      for (const name of ["left", "right", "bottom"]) {
        root.style.removeProperty(`--zen-fullpanel-housing-${name}`);
      }
    }
    // Reading geometry from here on flushes the attribute changes above.
    this.#applyAll();
    this.#updateOutline();
  }

  // The gap the page card keeps from the screen edges, which it also keeps
  // around the housing (0 with the outer border off): Talos's clearance.
  get #clearance() {
    if (!document.documentElement.hasAttribute("zen-fullpanel-outer-border")) {
      return 0;
    }
    const value = window
      .getComputedStyle(document.documentElement)
      .getPropertyValue("--zen-element-separation");
    return parseFloat(value) || 0;
  }

  // The housing widened by the clearance on both sides and below.
  get #cut() {
    if (!this.#housing) {
      return null;
    }
    const c = this.#clearance;
    return {
      left: this.#housing.left - c,
      right: this.#housing.right + c,
      top: this.#housing.top,
      bottom: this.#housing.bottom + c,
    };
  }

  #selectedRect() {
    return window.gBrowser?.selectedBrowser?.getBoundingClientRect() ?? null;
  }

  // Talos's WebViewNotchScroll.insetTop: how far down from the page's top
  // the page has to start to clear the housing, if the visible page lies
  // under it; else 0. In device pixels, so it keeps its physical size under
  // full zoom.
  #insetFor(browser, fallbackRect) {
    const cut = this.#cut;
    if (!cut || this.mode !== "solid" || document.fullscreenElement) {
      return 0;
    }
    let rect = browser.getBoundingClientRect();
    if (!rect.width && !rect.height) {
      // Background tabs share the selected browser's position.
      rect = fallbackRect;
    }
    if (
      !rect ||
      rect.left >= cut.right ||
      rect.right <= cut.left ||
      rect.top >= cut.bottom ||
      rect.bottom <= cut.top
    ) {
      return 0;
    }
    const css = Math.ceil(Math.max(0, cut.bottom - rect.top));
    return Math.round(css * window.devicePixelRatio);
  }

  #applyBrowser(browser, fallbackRect) {
    const bc = browser.browsingContext;
    if (!bc) {
      return;
    }
    const px = this.#insetFor(browser, fallbackRect);
    if (this.#insets.get(browser) !== px || bc.zenObscuredTopInset !== px) {
      this.#insets.set(browser, px);
      try {
        bc.zenObscuredTopInset = px;
      } catch (e) {
        // A browsing context that is being discarded.
        return;
      }
    }
    // Keeps the page's scrollbar out of the band too (zen-fullpanel.css; the
    // property is chrome-only, so it is set from the stylesheet).
    if (px) {
      browser.style.setProperty(
        "--zen-fullpanel-scrollbar-inset",
        `${px / window.devicePixelRatio}px`
      );
    } else {
      browser.style.removeProperty("--zen-fullpanel-scrollbar-inset");
    }
  }

  #applyAll() {
    const browsers = window.gBrowser?.browsers;
    if (!browsers) {
      return;
    }
    const fallbackRect = this.#selectedRect();
    for (const browser of browsers) {
      this.#applyBrowser(browser, fallbackRect);
    }
  }

  // Inner border: the page card is cut away around the housing (the gap
  // shows there, as along the screen edges) and its edge follows the cut:
  // down beside the housing, along under it, back up. The cut and the line
  // are one path, so they always coincide (Talos NotchCutoutGeometry).
  #updateOutline() {
    const panels = document.getElementById("tabbrowser-tabpanels");
    const tabbox = document.getElementById("tabbrowser-tabbox");
    const cut = this.#cut;
    const wanted =
      cut &&
      panels &&
      tabbox &&
      document.documentElement.hasAttribute("zen-fullpanel-inner-border");
    const area = wanted ? panels.getBoundingClientRect() : null;
    // Nil unless the housing reaches into the card below its top edge.
    const geometry =
      area &&
      cut.left < area.right &&
      cut.right > area.left &&
      cut.bottom >= area.top + HOUSING_CORNER_RADIUS + this.#clearance + SHOULDER_RADIUS
        ? this.#outlineGeometry(cut, area)
        : null;
    if (!geometry) {
      panels?.style.removeProperty("clip-path");
      this.#outline?.remove();
      this.#outline = null;
      return;
    }

    // Everything except the cut (even-odd), with room for the card's shadow.
    const pad = 64;
    const outer =
      `M ${-pad} ${-pad} H ${area.width + pad} V ${area.height + pad} ` +
      `H ${-pad} Z`;
    panels.style.setProperty(
      "clip-path",
      `path(evenodd, "${outer} ${geometry.region(-area.left, -area.top)}")`
    );

    if (!this.#outline) {
      this.#outline = document.createElementNS(SVG_NS, "svg");
      this.#outline.id = "zen-fullpanel-outline";
      this.#outline.appendChild(document.createElementNS(SVG_NS, "path"));
    }
    if (this.#outline.parentNode !== tabbox) {
      tabbox.appendChild(this.#outline);
    }
    const box = tabbox.getBoundingClientRect();
    this.#outline.setAttribute("width", box.width);
    this.#outline.setAttribute("height", box.height);
    this.#outline.firstChild.setAttribute(
      "d",
      geometry.outline(-box.left, -box.top)
    );
  }

  #outlineGeometry(cut, area) {
    const top = area.top;
    const bottomRadius = HOUSING_CORNER_RADIUS + this.#clearance;
    const r = Math.min(bottomRadius, (cut.right - cut.left) / 2);
    const s = SHOULDER_RADIUS;
    const n = (v) => Math.round(v * 100) / 100;
    // SVG arcs between the same tangent points as Talos's addArc calls.
    const outline = (dx, dy) => {
      const x0 = n(cut.left + dx),
        x1 = n(cut.right + dx),
        y0 = n(top + dy),
        y1 = n(cut.bottom + dy);
      return (
        `M ${n(x0 - s)} ${y0} A ${s} ${s} 0 0 1 ${x0} ${n(y0 + s)} ` +
        `V ${n(y1 - r)} A ${r} ${r} 0 0 0 ${n(x0 + r)} ${y1} ` +
        `H ${n(x1 - r)} A ${r} ${r} 0 0 0 ${x1} ${n(y1 - r)} ` +
        `V ${n(y0 + s)} A ${s} ${s} 0 0 1 ${n(x1 + s)} ${y0}`
      );
    };
    // What is cut away: inside the outline, and the gap above it.
    const region = (dx, dy) => {
      const above = n(Math.min(cut.top, top) - 1 + dy);
      return (
        `${outline(dx, dy)} V ${above} H ${n(cut.left - s + dx)} Z`
      );
    };
    return { outline, region };
  }

  // Tools > Browser Tools > Fullscreen. One submenu; every item is a pref,
  // so changes persist and apply without a rebuild.
  #initMenu() {
    const popup = document.getElementById("menuWebDeveloperPopup");
    if (!popup) {
      return;
    }
    const fragment = window.MozXULElement.parseXULToFragment(`
      <menuseparator id="zen-fullpanel-separator"/>
      <menu id="zen-fullpanel-menu" data-l10n-id="zen-fullpanel-menu">
        <menupopup id="zen-fullpanel-popup">
          <menuitem type="radio" name="zen-fullpanel-mode" data-pref="${PREF_ENABLED}" data-value="false"
                    data-l10n-id="zen-fullpanel-mode-native"/>
          <menuitem type="radio" name="zen-fullpanel-mode" data-pref="${PREF_ENABLED}" data-value="true"
                    data-l10n-id="zen-fullpanel-mode-fullpanel"/>
          <menuseparator/>
          <menuitem disabled="true" data-l10n-id="zen-fullpanel-border-header"/>
          <menuitem type="checkbox" data-pref="${PREF_INNER}" data-l10n-id="zen-fullpanel-border-inner"/>
          <menuitem type="checkbox" data-pref="${PREF_OUTER}" data-l10n-id="zen-fullpanel-border-outer"/>
          <menuseparator/>
          <menuitem disabled="true" data-l10n-id="zen-fullpanel-notch-header"/>
          <menuitem type="radio" name="zen-fullpanel-notch" data-pref="${PREF_MODE}" data-value="solid"
                    data-l10n-id="zen-fullpanel-notch-solid"/>
          <menuitem type="radio" name="zen-fullpanel-notch" data-pref="${PREF_MODE}" data-value="off"
                    data-l10n-id="zen-fullpanel-notch-off"/>
          <menuseparator/>
          <menuitem id="zen-fullpanel-status" disabled="true" data-l10n-id="zen-fullpanel-status"
                    data-l10n-args='{"state":"disabled","reason":""}'/>
          <menuitem id="zen-fullpanel-next-entry" disabled="true" hidden="true"
                    data-l10n-id="zen-fullpanel-next-entry"/>
        </menupopup>
      </menu>`);
    popup.appendChild(fragment);
    this.#menu = document.getElementById("zen-fullpanel-popup");
    this.#menu.addEventListener("popupshowing", () => this.#updateMenu());
    this.#menu.addEventListener("command", (event) => {
      const item = event.target;
      const pref = item.dataset.pref;
      if (pref === PREF_MODE) {
        Services.prefs.setStringPref(pref, item.dataset.value);
      } else if (pref === PREF_ENABLED) {
        Services.prefs.setBoolPref(pref, item.dataset.value === "true");
      } else if (pref) {
        Services.prefs.setBoolPref(pref, item.getAttribute("checked") === "true");
      }
    });
  }

  #updateMenu() {
    const state = this.#readState();
    const enabled = Services.prefs.getBoolPref(PREF_ENABLED, false);
    for (const item of this.#menu.querySelectorAll("menuitem[data-pref]")) {
      const pref = item.dataset.pref;
      let checked;
      if (pref === PREF_ENABLED) {
        checked = String(enabled) === item.dataset.value;
      } else if (pref === PREF_MODE) {
        checked = this.mode === item.dataset.value;
      } else {
        checked = Services.prefs.getBoolPref(pref, true);
      }
      if (checked) {
        item.setAttribute("checked", "true");
      } else {
        item.removeAttribute("checked");
      }
    }
    const status = this.#menu.querySelector("#zen-fullpanel-status");
    const name = !state.attached
      ? "unavailable"
      : state.state === "fallback"
        ? "fallback"
        : state.state || "disabled";
    document.l10n.setArgs(status, { state: name, reason: state.fallback ?? "" });
    // In fullscreen, the mode switch takes effect from the next entry.
    this.#menu.querySelector("#zen-fullpanel-next-entry").hidden =
      !state.fullscreen;
  }
}

if (AppConstants.platform === "macosx") {
  window.gZenFullPanel = new nsZenFullPanel();
}
