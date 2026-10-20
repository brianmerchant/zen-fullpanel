# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Informational public-site pass for notch scrolling (needs network).

For each site, with a 38 CSS px obscured inset and then without: what is hit
in the band and just below it at scroll 0, the top of the first fixed or
sticky header, the band color, and what reaches the band after scrolling.
Logged out, throwaway profile, ordinary window. One NOTCH-SITE json line per
site and inset:

  python3 scripts/fullpanel/notch-scroll/drive_sites.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from zentest import ZenApp  # noqa: E402

BAND = 38
SITES = [
    "https://www.apple.com/",
    "https://www.youtube.com/",
    "https://github.com/",
    "https://www.wikipedia.org/",
    "https://www.reddit.com/",
    "https://developer.mozilla.org/en-US/docs/Web/CSS",
]

PROBE = """
const [band] = arguments;
const w = innerWidth;
const desc = (el) => el ? (el.localName + (el.id ? "#" + el.id : "") +
  (typeof el.className == "string" && el.className ? "." + el.className.trim().split(/\\s+/)[0] : "")) : null;
const deep = (x, y) => { let el = document.elementFromPoint(x, y);
  while (el && el.shadowRoot) { const n = el.shadowRoot.elementFromPoint(x, y); if (!n || n == el) break; el = n; }
  return el; };
let header = null;
for (const el of document.querySelectorAll("body *")) {
  const cs = getComputedStyle(el);
  if ((cs.position == "fixed" || cs.position == "sticky") && el.offsetHeight > 20 &&
      el.offsetWidth > w / 2) { const r = el.getBoundingClientRect();
    if (r.top < 200 && r.bottom > 0) { header = {el: desc(el), top: r.top, pos: cs.position}; break; } }
}
return {scrollY, innerHeight, rootTop: document.documentElement.getBoundingClientRect().top,
  bandHit: desc(deep(w / 2 - 200, band / 2)), belowHit: desc(deep(w / 2, band + 8)), header};
"""

BAND_PIXEL = """
const wg = gBrowser.selectedBrowser.browsingContext.currentWindowGlobal;
const bitmap = await wg.drawSnapshot(null, 1, "rgb(255,0,255)");
const c = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
c.width = bitmap.width; c.height = bitmap.height;
const g = c.getContext("2d"); g.drawImage(bitmap, 0, 0);
return [...g.getImageData(Math.floor(bitmap.width / 2) - 200, 10, 1, 1).data].slice(0, 3);
"""


def main():
    zen = ZenApp()
    m = zen.start()
    try:
        for band in (BAND, 0):
            m.chrome(
                "gBrowser.selectedBrowser.browsingContext.zenObscuredTopInset ="
                " Math.round(arguments[0] * window.devicePixelRatio);", [band])
            for url in SITES:
                out = {"band": band, "url": url}
                try:
                    m.navigate(url)
                    time.sleep(2.5)
                    out["top"] = m.js(PROBE, [BAND])
                    out["bandPixel"] = m.chrome(BAND_PIXEL)
                    m.js("window.scrollTo(0, 700)")
                    time.sleep(0.8)
                    out["scrolled"] = m.js(PROBE, [BAND])
                except Exception as e:  # network or site errors are reported
                    out["error"] = str(e).splitlines()[0][:200]
                print("NOTCH-SITE " + json.dumps(out), flush=True)
    finally:
        zen.stop()


if __name__ == "__main__":
    main()
