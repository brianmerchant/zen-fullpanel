# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Layout checks for notch scrolling (obscured top inset, Solid Color band).

These drive the real built browser but set BrowsingContext.zenObscuredTopInset
directly, so they verify Gecko's layout, painting and hit-testing in an
ordinary window, without a FullPanel session:

  python3 scripts/fullpanel/notch-scroll/test_notch_scroll.py [-v]
"""

import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from zentest import ZenTestCase  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
BAND = 38  # CSS px (== points at 100% UI scale), as on the M1 Pro 14".
ROW_COLORS = [(200, 30, 30), (30, 160, 60), (30, 60, 200), (200, 150, 20)]
BODY_BG = (245, 245, 247)


def fixture(name):
    return "file://" + os.path.join(FIXTURES, name)


def close(a, b, tol=1.0):
    return abs(a - b) <= tol


def color_near(px, rgb, tol=12):
    return all(abs(px[i] - rgb[i]) <= tol for i in range(3))


class TestNotchScroll(ZenTestCase):
    def setUp(self):
        self.set_inset(0)
        self.set_zoom(1.0)

    def tearDown(self):
        self.set_inset(0)
        self.set_zoom(1.0)

    # --- helpers ---------------------------------------------------------

    def set_inset(self, css_px):
        self.m.chrome(
            """
            const bc = gBrowser.selectedBrowser.browsingContext;
            bc.zenObscuredTopInset = Math.round(arguments[0] * window.devicePixelRatio);
            return bc.zenObscuredTopInset;
            """,
            [css_px],
        )

    def set_zoom(self, zoom):
        self.m.chrome(
            "gBrowser.selectedBrowser.browsingContext.fullZoom = arguments[0];", [zoom]
        )

    def settle(self):
        self.m.settle()

    def load(self, name):
        self.m.navigate(fixture(name))
        self.settle()

    def js(self, script, args=None):
        return self.m.js(script, args)

    def rect(self, id_):
        return self.js(
            "const r = document.getElementById(arguments[0]).getBoundingClientRect();"
            "return {top: r.top, bottom: r.bottom, left: r.left, right: r.right};",
            [id_],
        )

    def scroll_to(self, y):
        self.js("window.scrollTo(0, arguments[0]);", [y])
        self.settle()

    def pixels(self, points):
        """Samples the composited viewport (drawSnapshot) at CSS points."""
        return self.m.chrome(
            """
            const [points] = arguments;
            const wg = gBrowser.selectedBrowser.browsingContext.currentWindowGlobal;
            const bitmap = await wg.drawSnapshot(null, 1, "rgb(255,0,255)");
            const canvas = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
            canvas.width = bitmap.width;
            canvas.height = bitmap.height;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(bitmap, 0, 0);
            return points.map(([x, y]) => Array.from(ctx.getImageData(x, y, 1, 1).data));
            """,
            [points],
        )

    def band_color(self):
        width = self.js("return window.innerWidth")
        return self.pixels([[width // 2, BAND // 2]])[0]

    def hit(self, x, y):
        return self.js(
            """
            const el = document.elementFromPoint(arguments[0], arguments[1]);
            const row = el && el.closest(".row");
            return {tag: el ? el.localName : null, id: el ? el.id : null,
                    row: row ? row.id : null};
            """,
            [x, y],
        )

    def clicks(self):
        return self.js("return JSON.parse(document.documentElement.dataset.clicks || '[]')")

    # --- layout ------------------------------------------------------------

    def test_flag_off_is_unchanged(self):
        self.load("fixed-nav.html")
        self.assertTrue(close(self.rect("nav")["top"], 0))
        self.assertEqual(self.js("return document.documentElement.getBoundingClientRect().top"), 0)

    def test_safe_initial_layout_without_shift(self):
        self.set_inset(BAND)
        self.load("fixed-nav.html")
        probe = self.js("return JSON.parse(document.documentElement.dataset.probe || '[]')")
        self.assertTrue(len(probe) >= 3, probe)
        for sample in probe:
            # Already below the band at DOMContentLoaded: no later shift.
            self.assertTrue(close(sample["navTop"], BAND), json.dumps(probe))
            self.assertTrue(close(sample["rootTop"], BAND), json.dumps(probe))
        vh = self.js("return window.innerHeight")
        self.assertTrue(close(self.rect("bottombar")["bottom"], vh))
        self.assertTrue(self.rect("search")["top"] >= BAND)

    def test_scroll_under_paints_real_content(self):
        self.set_inset(BAND)
        self.load("fixed-nav.html")
        width = self.js("return window.innerWidth")
        # At the top the band continues the document's top edge (the body),
        # not the fixed nav below it.
        top_px = self.pixels([[5, 10], [width - 5, 10]])
        for px in top_px:
            self.assertTrue(color_near(px, BODY_BG), top_px)
        self.scroll_to(400)
        hit = self.hit(5, 10)
        self.assertIsNotNone(hit["row"], hit)
        px = self.pixels([[5, 10], [width - 5, 10]])
        for p in px:
            self.assertTrue(any(color_near(p, c) for c in ROW_COLORS), px)
        self.assertTrue(close(self.rect("nav")["top"], BAND))
        self.scroll_to(0)
        self.assertTrue(close(self.rect("nav")["top"], BAND))
        self.assertTrue(close(self.rect("row1")["top"], BAND + 52))

    def test_continuous_scroll_has_no_gap(self):
        # Every scroll offset across the band: the band shows the band color
        # above the document's top and real content below it, nothing else.
        self.set_inset(BAND)
        self.load("repaint.html")
        for y in range(0, BAND + 4, 2):
            self.scroll_to(y)
            column = self.pixels([[20, v] for v in range(0, BAND, 3)])
            for p in column:
                self.assertTrue(color_near(p, (200, 30, 30), 3), (y, column))

    def test_sticky_sticks_below_band(self):
        self.set_inset(BAND)
        self.load("sticky-nav.html")
        self.assertTrue(close(self.rect("nav")["top"], BAND + 300))
        self.scroll_to(1200)
        self.assertTrue(close(self.rect("nav")["top"], BAND), self.rect("nav"))
        self.assertIsNotNone(self.hit(5, 10)["row"])
        self.scroll_to(0)
        self.assertTrue(close(self.rect("nav")["top"], BAND + 300))

    def test_absolute_header_uses_offset_icb(self):
        self.set_inset(BAND)
        self.load("gradient-abs.html")
        self.assertTrue(close(self.rect("nav")["top"], BAND))
        self.assertTrue(close(self.rect("masthead")["top"], BAND))

    def test_scroll_into_view_and_fragment(self):
        self.set_inset(BAND)
        self.load("anchors.html")
        self.js("document.getElementById('target').scrollIntoView();")
        self.settle()
        self.assertTrue(close(self.rect("target")["top"], BAND), self.rect("target"))
        self.scroll_to(0)
        self.js("location.hash = '#target';")
        self.settle()
        self.assertTrue(close(self.rect("target")["top"], BAND), self.rect("target"))

    def test_clicks_in_band_reach_content(self):
        self.set_inset(BAND)
        self.load("fixed-nav.html")
        self.scroll_to(400)
        self.assertIsNotNone(self.hit(30, 10)["row"])
        self.m.click_at(30, 10)
        clicks = self.clicks()
        self.assertTrue(clicks, clicks)
        self.assertTrue(close(clicks[-1]["y"], 10), clicks)
        nav = self.rect("navLeft")
        self.m.click_at(nav["left"] + 5, nav["top"] + 5)
        self.assertEqual(self.clicks()[-1]["id"], "navLeft")

    def test_live_toggle(self):
        self.load("fixed-nav.html")
        self.assertTrue(close(self.rect("nav")["top"], 0))
        self.set_inset(BAND)
        self.settle()
        self.assertTrue(close(self.rect("nav")["top"], BAND))
        self.set_inset(0)
        self.settle()
        self.assertTrue(close(self.rect("nav")["top"], 0))
        self.assertEqual(self.js("return document.documentElement.getBoundingClientRect().top"), 0)

    def test_zoom_keeps_physical_band(self):
        self.set_inset(BAND)
        self.load("fixed-nav.html")
        self.set_zoom(1.5)
        self.settle()
        dpr = self.js("return window.devicePixelRatio")
        base = self.m.chrome("return window.devicePixelRatio")
        self.assertTrue(close(dpr, base * 1.5, 0.01), (dpr, base))
        self.assertTrue(close(self.rect("nav")["top"], BAND / 1.5), self.rect("nav"))

    def test_navigation_keeps_inset(self):
        self.set_inset(BAND)
        self.load("sticky-nav.html")
        self.load("fixed-nav.html")
        probe = self.js("return JSON.parse(document.documentElement.dataset.probe || '[]')")
        self.assertTrue(close(probe[0]["navTop"], BAND), json.dumps(probe))
        self.m.back()
        self.settle()
        self.assertTrue(close(self.rect("nav")["top"], BAND + 300))

    # --- Solid Color band ----------------------------------------------------

    def test_band_uses_root_gradient_top(self):
        self.set_inset(BAND)
        self.load("gradient-abs.html")
        for p in self.pixels([[5, 5], [5, 30], [5, BAND + 2]]):
            self.assertTrue(color_near(p, (20, 40, 110), 6), p)

    def test_band_uses_hero_gradient_not_canvas(self):
        # GitHub's case: canvas rgb(13,17,23), hero gradient top rgb(0,2,64).
        self.set_inset(BAND)
        self.load("hero-gradient.html")
        width = self.js("return window.innerWidth")
        px = self.pixels([[5, 10], [width // 2, 30], [width - 5, 10]])
        for p in px:
            self.assertTrue(color_near(p, (0, 2, 64), 4), px)
        self.scroll_to(BAND + 100)
        self.assertFalse(color_near(self.pixels([[5, 10]])[0], (13, 17, 23), 2))

    def test_band_uses_in_flow_top_element(self):
        self.set_inset(BAND)
        self.load("anchors.html")
        # The top edge is the in-flow #hero100 (#ddd) over the body (#f5f5f7).
        self.assertTrue(color_near(self.pixels([[5, 10]])[0], (221, 221, 221), 3))

    def test_band_is_one_solid_color(self):
        self.set_inset(BAND)
        self.load("vote.html?l=200,30,30&m=30,160,60&r=30,60,200")
        width = self.js("return window.innerWidth")
        # Clear of the right edge, where macOS draws its translucent overlay
        # scrollbar (this test sets the inset directly, without the chrome's
        # scrollbar inset).
        px = self.pixels([[x, y] for x in (5, width // 2, width - 30) for y in (2, BAND // 2, BAND - 2)])
        for p in px:
            self.assertEqual(p[:3], px[0][:3], px)

    def test_band_vote_middle_when_all_differ(self):
        self.set_inset(BAND)
        self.load("vote.html?l=200,30,30&m=30,160,60&r=30,60,200")
        self.assertTrue(color_near(self.band_color(), (30, 160, 60), 2))

    def test_band_vote_two_equal_samples_win(self):
        self.set_inset(BAND)
        self.load("vote.html?l=200,30,30&m=30,160,60&r=200,30,30")
        self.assertTrue(color_near(self.band_color(), (200, 30, 30), 2))

    def test_band_composites_translucent_top(self):
        self.set_inset(BAND)
        self.load("translucent.html")
        self.assertTrue(color_near(self.band_color(), (102, 102, 255), 3), self.band_color())

    def test_band_follows_repaint_only_change(self):
        self.set_inset(BAND)
        self.load("repaint.html")
        self.assertTrue(color_near(self.band_color(), (200, 30, 30), 2))
        self.js("document.getElementById('head').style.background = 'rgb(30, 60, 200)'")
        color = None
        for _ in range(30):
            time.sleep(0.1)
            color = self.band_color()
            if color_near(color, (30, 60, 200), 2):
                break
        self.assertTrue(color_near(color, (30, 60, 200), 2), color)

    def test_band_keeps_color_while_scrolled(self):
        self.set_inset(BAND)
        self.load("repaint.html")
        self.scroll_to(600)
        self.js("document.getElementById('head').style.background = 'rgb(30, 60, 200)'")
        time.sleep(0.6)
        self.scroll_to(0)
        # Back at the top, the next sample picks the new color up.
        color = None
        for _ in range(30):
            time.sleep(0.1)
            color = self.band_color()
            if color_near(color, (30, 60, 200), 2):
                break
        self.assertTrue(color_near(color, (30, 60, 200), 2), color)


if __name__ == "__main__":
    unittest.main()
