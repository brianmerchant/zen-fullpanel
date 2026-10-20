# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""FullPanel integration checks in an ordinary window (no fullscreen).

- Native: every browser window (Gecko's ToolbarWindow) has a FullPanelKit
  session that follows zen.fullpanel.enabled.
- Chrome: with an injected FullPanel state (gZenFullPanel.testState), the
  notch inset, the content-area offset, the inner/outer borders and their
  removal; the Tools > Browser Tools > Fullscreen menu.

  python3 scripts/fullpanel/test_fullpanel_chrome.py [-v]
"""

import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zentest import ZenTestCase  # noqa: E402

HOUSING_W = 185
HOUSING_H = 38

APPLY = """
  const [state] = arguments;
  gZenFullPanel.testState = state;
  gZenFullPanel.update();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
"""

READ = """
  const root = document.documentElement;
  const b = gBrowser.selectedBrowser;
  const panels = document.getElementById('tabbrowser-tabpanels');
  const wrapper = document.getElementById('zen-appcontent-wrapper');
  const outline = document.getElementById('zen-fullpanel-outline');
  const r = b.getBoundingClientRect();
  return {
    attrs: ['zen-fullpanel-active', 'zen-fullpanel-notch-scroll', 'zen-fullpanel-inner-border',
            'zen-fullpanel-outer-border'].filter(a => root.hasAttribute(a)),
    inset: b.browsingContext.zenObscuredTopInset,
    dpr: window.devicePixelRatio,
    browserTop: r.top, browserLeft: r.left, browserRight: r.right,
    scrollbarInset: b.style.getPropertyValue('--zen-fullpanel-scrollbar-inset'),
    clip: panels.style.getPropertyValue('clip-path'),
    outline: outline ? outline.firstChild.getAttribute('d') : null,
    wrapperPadding: parseFloat(getComputedStyle(wrapper).paddingTop),
    tabboxMargin: getComputedStyle(document.getElementById('zen-tabbox-wrapper')).marginRight,
    separation: parseFloat(getComputedStyle(root).getPropertyValue('--zen-element-separation')),
  };
"""


class TestFullPanelNative(ZenTestCase):
    def state(self, script_window="window"):
        return json.loads(self.m.chrome(f"return Services.zen.fullPanelState({script_window})"))

    def test_session_attached_and_follows_pref(self):
        s = self.state()
        self.assertTrue(s.get("attached"), s)
        self.assertFalse(s["enabled"], s)
        self.assertEqual(s["state"], "disabled", s)
        self.assertTrue(s["available"], s)
        self.m.chrome("Services.prefs.setBoolPref('zen.fullpanel.enabled', true)")
        try:
            s = self.state()
            self.assertTrue(s["enabled"], s)
            self.assertEqual(s["state"], "inactive", s)
            self.assertFalse(s["active"], s)
        finally:
            self.m.chrome("Services.prefs.setBoolPref('zen.fullpanel.enabled', false)")
        self.assertEqual(self.state()["state"], "disabled")

    def test_new_window_attached(self):
        s = json.loads(self.m.chrome("""
          const win = OpenBrowserWindow();
          await new Promise(r => win.addEventListener('load', r, {once: true}));
          const state = Services.zen.fullPanelState(win);
          win.close();
          return state;
        """))
        self.assertTrue(s.get("attached"), s)

    def test_built_in_display_geometry(self):
        s = self.state()
        # On a notched built-in display the housing is reported even while
        # windowed; elsewhere it is simply absent.
        if "housing" in s:
            self.assertGreater(s["housing"]["width"], 100, s)
            self.assertGreater(s["topInset"], 20, s)

    def test_other_windows_get_no_session(self):
        s = json.loads(self.m.chrome("""
          const win = Services.ww.openWindow(null, 'about:blank', '_blank', 'chrome,width=300,height=200', null);
          for (let i = 0; i < 50 && win.document.readyState != 'complete'; i++)
            await new Promise(r => setTimeout(r, 100));
          const state = Services.zen.fullPanelState(win);
          win.close();
          return state;
        """))
        self.assertEqual(s, {})


class TestFullPanelChrome(ZenTestCase):
    def setUp(self):
        self.m.chrome("""
          for (const p of ['zen.fullpanel.notch-scroll-mode', 'zen.fullpanel.inner-border',
                           'zen.fullpanel.outer-border']) Services.prefs.clearUserPref(p);
        """)
        self.width = self.m.chrome("return window.innerWidth")

    def tearDown(self):
        self.m.chrome(APPLY + "gZenFullPanel.testState = null; gZenFullPanel.update();", [None])

    def active_state(self, **extra):
        x = (self.width - HOUSING_W) / 2
        state = {
            "attached": True, "enabled": True, "state": "active", "active": True,
            "fullscreen": True, "fallback": "none", "topInset": HOUSING_H,
            "housing": {"x": x, "y": 0, "width": HOUSING_W, "height": HOUSING_H},
        }
        state.update(extra)
        return state

    def apply(self, state):
        self.m.chrome(APPLY, [state])
        return self.m.chrome(READ)

    def test_defaults(self):
        prefs = self.m.chrome("""
          return [Services.prefs.getBoolPref('zen.fullpanel.enabled'),
                  Services.prefs.getStringPref('zen.fullpanel.notch-scroll-mode'),
                  Services.prefs.getBoolPref('zen.fullpanel.inner-border'),
                  Services.prefs.getBoolPref('zen.fullpanel.outer-border')];
        """)
        self.assertEqual(prefs, [False, "solid", True, True])

    def test_inactive_changes_nothing(self):
        r = self.apply({"attached": True, "enabled": True, "state": "inactive", "active": False})
        self.assertEqual(r["attrs"], ["zen-fullpanel-outer-border"], r)
        self.assertEqual(r["inset"], 0)
        self.assertEqual(r["clip"], "")
        self.assertIsNone(r["outline"])
        self.assertEqual(r["wrapperPadding"], 0)

    def test_solid_inset(self):
        r = self.apply(self.active_state())
        self.assertIn("zen-fullpanel-notch-scroll", r["attrs"], r)
        # Talos: housing bottom + gutter clearance, from the page's top.
        expected_css = max(0, HOUSING_H + r["separation"] - r["browserTop"])
        self.assertGreater(expected_css, 0, r)
        self.assertAlmostEqual(r["inset"], round(math.ceil(expected_css) * r["dpr"]), delta=r["dpr"], msg=r)
        self.assertEqual(r["scrollbarInset"], f"{r['inset'] / r['dpr']:g}px", r)
        self.assertEqual(r["wrapperPadding"], 0, "content reaches the top edge")

    def test_new_tab_gets_inset_before_first_layout(self):
        self.apply(self.active_state())
        insets = self.m.chrome("""
          const tab = gBrowser.addTrustedTab('about:blank');
          const first = tab.linkedBrowser.browsingContext.zenObscuredTopInset;
          gBrowser.removeTab(tab, {animate: false});
          return [first, gBrowser.selectedBrowser.browsingContext.zenObscuredTopInset];
        """)
        self.assertEqual(insets[0], insets[1])
        self.assertGreater(insets[0], 0)

    def test_off_mode_pads_content(self):
        self.m.chrome("Services.prefs.setStringPref('zen.fullpanel.notch-scroll-mode', 'off')")
        r = self.apply(self.active_state())
        self.assertNotIn("zen-fullpanel-notch-scroll", r["attrs"], r)
        self.assertEqual(r["inset"], 0, r)
        single = self.m.chrome("return document.documentElement.getAttribute('zen-single-toolbar') == 'true'")
        if single:
            self.assertAlmostEqual(r["wrapperPadding"], HOUSING_H, delta=0.5, msg=r)
        self.assertGreaterEqual(r["browserTop"], HOUSING_H, r)

    def test_inner_border_cuts_around_housing(self):
        r = self.apply(self.active_state())
        self.assertIn("evenodd", r["clip"], r)
        self.assertTrue(r["outline"] and r["outline"].startswith("M"), r)
        # The cut is clipped from hit testing: nothing of the card is there.
        hit = self.m.chrome("""
          const panels = document.getElementById('tabbrowser-tabpanels');
          const el = document.elementFromPoint(window.innerWidth / 2, arguments[0]);
          return {inPanels: panels.contains(el), id: el && el.id};
        """, [HOUSING_H / 2])
        self.assertFalse(hit["inPanels"], hit)
        # Beside the housing the card is still there.
        side = self.m.chrome("""
          const panels = document.getElementById('tabbrowser-tabpanels');
          const r = panels.getBoundingClientRect();
          const el = document.elementFromPoint(r.left + 40, r.top + 12);
          return panels.contains(el);
        """)
        self.assertTrue(side)

    def test_inner_border_off(self):
        self.m.chrome("Services.prefs.setBoolPref('zen.fullpanel.inner-border', false)")
        r = self.apply(self.active_state())
        self.assertNotIn("zen-fullpanel-inner-border", r["attrs"])
        self.assertEqual(r["clip"], "")
        self.assertIsNone(r["outline"])
        self.assertGreater(r["inset"], 0, "notch scrolling is independent of the border")

    def test_outer_border_off_runs_edge_to_edge(self):
        on = self.apply(self.active_state())
        self.assertNotEqual(on["tabboxMargin"], "0px", on)
        self.m.chrome("Services.prefs.setBoolPref('zen.fullpanel.outer-border', false);"
                      " await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));")
        off = self.m.chrome(READ)
        self.assertNotIn("zen-fullpanel-outer-border", off["attrs"])
        self.assertEqual(off["tabboxMargin"], "0px", off)
        # No clearance: the inset is the housing's own bottom.
        self.assertLess(off["inset"], on["inset"], (on, off))
        expected = max(0, HOUSING_H - off["browserTop"])
        self.assertAlmostEqual(off["inset"], round(expected * off["dpr"]), delta=off["dpr"], msg=off)

    def test_prefs_apply_live(self):
        self.apply(self.active_state())
        self.m.chrome("Services.prefs.setStringPref('zen.fullpanel.notch-scroll-mode', 'off')")
        self.m.chrome("await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));")
        self.assertEqual(self.m.chrome(READ)["inset"], 0)
        self.m.chrome("Services.prefs.setStringPref('zen.fullpanel.notch-scroll-mode', 'solid')")
        self.m.chrome("await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));")
        self.assertGreater(self.m.chrome(READ)["inset"], 0)

    def test_leaving_fullpanel_restores_everything(self):
        self.apply(self.active_state())
        r = self.apply({"attached": True, "enabled": True, "state": "inactive", "active": False})
        self.assertEqual(r["inset"], 0)
        self.assertEqual(r["clip"], "")
        self.assertIsNone(r["outline"])
        self.assertEqual(r["scrollbarInset"], "")
        self.assertEqual(r["attrs"], ["zen-fullpanel-outer-border"])

    def test_menu(self):
        menu = self.m.chrome("""
          const popup = document.getElementById('zen-fullpanel-popup');
          if (!popup) return null;
          await document.l10n.translateFragment(document.getElementById('menuWebDeveloperPopup'));
          popup.dispatchEvent(new Event('popupshowing'));
          await document.l10n.translateFragment(popup);
          const items = [...popup.querySelectorAll('menuitem')].map(i => ({
            label: i.getAttribute('label'), checked: i.getAttribute('checked') == 'true',
            hidden: i.hidden}));
          return {parent: popup.parentNode.getAttribute('label'), items,
                  inBrowserTools: !!popup.closest('#menuWebDeveloperPopup')};
        """)
        self.assertIsNotNone(menu)
        self.assertTrue(menu["inBrowserTools"])
        self.assertEqual(menu["parent"], "Fullscreen")
        labels = [i["label"] for i in menu["items"]]
        for label in ("Standard Native Fullscreen", "FullPanel Fullscreen", "Inner Border",
                      "Outer Border", "Solid Color"):
            self.assertIn(label, labels)
        checked = [i["label"] for i in menu["items"] if i["checked"]]
        self.assertEqual(checked, ["Standard Native Fullscreen", "Inner Border", "Outer Border",
                                   "Solid Color"])
        self.assertTrue(any(l and l.startswith("Status:") for l in labels), labels)

    def test_menu_commands_set_prefs(self):
        prefs = self.m.chrome("""
          const popup = document.getElementById('zen-fullpanel-popup');
          const item = (pref, value) => popup.querySelector(
            `menuitem[data-pref="${pref}"]` + (value ? `[data-value="${value}"]` : ''));
          const fire = (el) => { if (el.getAttribute('type') == 'checkbox') {
              el.getAttribute('checked') == 'true' ? el.removeAttribute('checked') : el.setAttribute('checked', 'true'); }
            el.dispatchEvent(new CustomEvent('command', {bubbles: true})); };
          popup.dispatchEvent(new Event('popupshowing'));
          fire(item('zen.fullpanel.enabled', 'true'));
          fire(item('zen.fullpanel.notch-scroll-mode', 'off'));
          fire(item('zen.fullpanel.inner-border'));
          const after = [Services.prefs.getBoolPref('zen.fullpanel.enabled'),
                         Services.prefs.getStringPref('zen.fullpanel.notch-scroll-mode'),
                         Services.prefs.getBoolPref('zen.fullpanel.inner-border')];
          fire(item('zen.fullpanel.enabled', 'false'));
          fire(item('zen.fullpanel.notch-scroll-mode', 'solid'));
          fire(item('zen.fullpanel.inner-border'));
          return [after, [Services.prefs.getBoolPref('zen.fullpanel.enabled'),
                          Services.prefs.getStringPref('zen.fullpanel.notch-scroll-mode'),
                          Services.prefs.getBoolPref('zen.fullpanel.inner-border')]];
        """)
        self.assertEqual(prefs[0], [True, "off", False])
        self.assertEqual(prefs[1], [False, "solid", True])


if __name__ == "__main__":
    unittest.main()
