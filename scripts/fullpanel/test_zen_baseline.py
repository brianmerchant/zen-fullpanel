# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Acceptance checks that a build is the complete Zen browser.

Guards against the earlier failure mode: a build that launches but is a
partly initialized Zen (unofficial "Nightly" branding, missing Zen strings
and therefore empty menus). Runs the built app with a throwaway profile:

  python3 scripts/fullpanel/test_zen_baseline.py [-v]

ZEN_APP=/path/to/App.app selects another bundle; ZEN_EXPECT_NAME,
ZEN_EXPECT_BUNDLE_ID and ZEN_EXPECT_CHANNEL override the expected identity
(defaults: stock Zen release).
"""

import http.server
import json
import math
import os
import plistlib
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zentest import ZenTestCase, default_app  # noqa: E402

EXPECT_NAME = os.environ.get("ZEN_EXPECT_NAME", "Zen")
EXPECT_BUNDLE_ID = os.environ.get("ZEN_EXPECT_BUNDLE_ID", "app.zen-browser.zen")
EXPECT_CHANNEL = os.environ.get("ZEN_EXPECT_CHANNEL", "release")
EXPECT_VERSION = os.environ.get("ZEN_EXPECT_VERSION", "1.23.3b")


def make_wav(path, seconds=3):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        frames = b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 22050)))
            for i in range(22050 * seconds)
        )
        w.writeframes(frames)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/download.bin"):
            body = b"zen-download-test\n" * 1000
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="zen-download.bin"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


class Server:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="zen-site-")
        pages = {
            "index.html": "<!doctype html><title>Zen Test Home</title><h1 id=h>home</h1><a id=next href=page2.html>next</a>",
            "page2.html": "<!doctype html><title>Zen Test Page 2</title><p id=p>two</p>",
            "tall.html": "<!doctype html><title>Tall</title><body style='margin:0'>"
            + "".join(f"<div style='height:200px'>row {i}</div>" for i in range(60)),
            "audio.html": "<!doctype html><title>Audio</title><audio id=a src=tone.wav></audio>",
            "video.html": """<!doctype html><title>Video</title>
<canvas id=c width=320 height=180></canvas><video id=v playsinline></video>
<script>
// Encode a short clip with MediaRecorder, then decode and play it back.
window.makeClip = async () => {
  const c = document.getElementById('c'), g = c.getContext('2d');
  const stream = c.captureStream(30);
  const rec = new MediaRecorder(stream, {mimeType: 'video/webm'});
  const chunks = [];
  rec.ondataavailable = e => chunks.push(e.data);
  let n = 0;
  const draw = () => { g.fillStyle = `hsl(${n++ * 7},80%,50%)`; g.fillRect(0, 0, 320, 180); };
  const timer = setInterval(draw, 33);
  rec.start();
  await new Promise(r => setTimeout(r, 1500));
  rec.stop();
  await new Promise(r => rec.onstop = r);
  clearInterval(timer);
  const v = document.getElementById('v');
  v.src = URL.createObjectURL(new Blob(chunks, {type: 'video/webm'}));
  v.muted = true;
  await v.play();
  await new Promise(r => setTimeout(r, 700));
  return {time: v.currentTime, paused: v.paused, w: v.videoWidth, h: v.videoHeight,
          decoded: v.getVideoPlaybackQuality().totalVideoFrames};
};
</script>""",
        }
        for name, text in pages.items():
            with open(os.path.join(self.dir, name), "w") as f:
                f.write(text)
        make_wav(os.path.join(self.dir, "tone.wav"))
        handler = lambda *a, **k: Handler(*a, directory=self.dir, **k)  # noqa: E731
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}/{path}"

    def close(self):
        self.httpd.shutdown()
        shutil.rmtree(self.dir, ignore_errors=True)


class TestIdentity(unittest.TestCase):
    def test_bundle(self):
        app = default_app()
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        self.assertEqual(info["CFBundleIdentifier"], EXPECT_BUNDLE_ID)
        self.assertEqual(info["CFBundleName"], EXPECT_NAME)
        self.assertEqual(os.path.basename(app), EXPECT_NAME + ".app")
        self.assertEqual(info.get("CFBundleShortVersionString"), EXPECT_VERSION)
        self.assertNotIn("Nightly", os.path.basename(app))


class TestZenBaseline(ZenTestCase):
    prefs = {"media.autoplay.default": 0, "media.autoplay.blocking_policy": 0}

    @classmethod
    def setUpClass(cls):
        cls.server = Server()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.close()

    def wait_chrome(self, script, args=None, timeout=20):
        deadline = time.time() + timeout
        while True:
            value = self.m.chrome(script, args)
            if value or time.time() > deadline:
                return value
            time.sleep(0.2)

    def test_app_constants(self):
        info = self.m.chrome("""
          return {name: Services.appinfo.name, channel: AppConstants.MOZ_UPDATE_CHANNEL,
                  display: AppConstants.MOZ_APP_VERSION_DISPLAY,
                  brand: AppConstants.MOZ_APP_BASENAME,
                  official: AppConstants.MOZILLA_OFFICIAL};
        """)
        self.assertEqual(info["channel"], EXPECT_CHANNEL, info)
        self.assertEqual(info["display"], EXPECT_VERSION, info)
        brand = self.m.chrome(
            "return Services.strings.createBundle('chrome://branding/locale/brand.properties')"
            ".GetStringFromName('brandShortName')"
        )
        self.assertEqual(brand, EXPECT_NAME)

    def test_zen_interface_initialized(self):
        ok = self.wait_chrome("""
          return !!(window.gZenWorkspaces && window.gZenUIManager && window.gZenVerticalTabsManager
                    && window.gZenCompactModeManager && window.gZenViewSplitter
                    && document.querySelector('zen-workspace')
                    && document.getElementById('zen-main-app-wrapper')
                    && document.getElementById('zen-sidebar-top-buttons'));
        """)
        self.assertTrue(ok)
        tabs_box = self.m.chrome(
            "const r = document.getElementById('navigator-toolbox').getBoundingClientRect();"
            " return [r.width, r.height];"
        )
        self.assertGreater(tabs_box[0], 40, "vertical sidebar visible")

    def test_menubar_fully_localized(self):
        result = self.m.chrome("""
          const bar = document.getElementById('main-menubar');
          await document.l10n.translateFragment(bar);
          const missing = [];
          let count = 0;
          for (const el of bar.querySelectorAll('menu, menuitem')) {
            if (el.hidden || el.closest('[hidden]') || !el.hasAttribute('data-l10n-id')) continue;
            count++;
            if (!el.getAttribute('label')) missing.push(el.id || el.getAttribute('data-l10n-id'));
          }
          const top = [...bar.children].filter(m => !m.hidden).map(m => m.getAttribute('label'));
          return {count, missing, top,
                  appearance: !!bar.querySelector('menu[data-l10n-id="zen-menubar-appearance"][label]'),
                  spaces: document.getElementById('zen-spaces-menubar')?.getAttribute('label')};
        """)
        self.assertGreater(result["count"], 50, result)
        self.assertEqual(result["missing"], [], result)
        self.assertTrue(result["appearance"], result)
        self.assertTrue(result["spaces"], result)
        for label in ("File", "Edit", "View", "History", "Bookmarks", "Tools", "Window", "Help"):
            self.assertIn(label, result["top"], result)

    def test_zen_strings_present(self):
        missing = self.m.chrome("""
          const ids = ['zen-menubar-appearance', 'zen-panel-ui-workspaces-create',
                       'zen-workspaces-change-theme', 'zen-menubar-new-blank-window'];
          const values = await document.l10n.formatMessages(ids.map(id => ({id})));
          return ids.filter((id, i) => !values[i] || !(values[i].value || values[i].attributes?.length));
        """)
        self.assertEqual(missing, [])

    def test_tabs_and_navigation(self):
        m = self.m
        m.navigate(self.server.url("index.html"))
        self.assertEqual(m.js("return document.title"), "Zen Test Home")
        m.js("document.getElementById('next').click()")
        self.wait_chrome("return gBrowser.selectedBrowser.contentTitle == 'Zen Test Page 2'")
        m.back()
        self.assertEqual(m.js("return document.title"), "Zen Test Home")
        count = m.chrome("""
          const before = gBrowser.tabs.length;
          const tab = gBrowser.addTrustedTab(arguments[0]);
          gBrowser.selectedTab = tab;
          await new Promise(r => { const b = tab.linkedBrowser;
            const check = () => b.contentTitle == 'Zen Test Page 2' ? r() : setTimeout(check, 100); check(); });
          const opened = gBrowser.tabs.length;
          gBrowser.removeTab(tab, {animate: false});
          return [before, opened, gBrowser.tabs.length];
        """, [self.server.url("page2.html")])
        self.assertEqual(count[1], count[0] + 1, count)
        self.assertEqual(count[2], count[0], count)

    def test_multiple_windows(self):
        counts = self.m.chrome("""
          const count = () => [...Services.wm.getEnumerator('navigator:browser')].length;
          const before = count();
          const win = OpenBrowserWindow();
          await new Promise(r => win.addEventListener('load', r, {once: true}));
          await new Promise(r => { const o = (s) => { if (s == win) { Services.obs.removeObserver(o,
            'browser-delayed-startup-finished'); r(); } };
            Services.obs.addObserver(o, 'browser-delayed-startup-finished'); });
          const ui = !!(win.gZenWorkspaces && win.document.querySelector('zen-workspace'));
          const opened = count();
          win.close();
          await new Promise(r => setTimeout(r, 500));
          return [before, opened, count(), ui];
        """)
        self.assertEqual(counts[1], counts[0] + 1, counts)
        self.assertEqual(counts[2], counts[0], counts)
        self.assertTrue(counts[3], "Zen UI in the new window")

    def test_settings(self):
        self.m.navigate("about:preferences")
        result = self.m.js("""
          const visible = () => [...document.querySelectorAll('moz-page-nav-button[id^=category], #categories > richlistitem')]
            .filter(i => !i.hidden).map(i => i.id);
          for (let i = 0; i < 50 && !visible().length; i++) await new Promise(r => setTimeout(r, 100));
          const cats = visible();
          // Open Zen's own Look and Feel pane.
          gotoPref('paneZenLooks');
          await new Promise(r => setTimeout(r, 500));
          const shown = [...document.querySelectorAll('[data-category=paneZenLooks]')]
            .filter(e => !e.hidden && e.getBoundingClientRect().height > 0).length;
          return {cats, shown};
        """)
        for cat in ("category-zen-looks", "category-zen-tabs-management", "category-zen-CKS",
                    "category-privacy", "category-search"):
            self.assertIn(cat, result["cats"], result)
        self.assertGreater(result["shown"], 0, result)
        self.m.navigate("about:blank")

    def test_sidebar_toggle(self):
        widths = self.m.chrome("""
          const tb = document.getElementById('navigator-toolbox');
          const pref = 'zen.view.sidebar-expanded';
          const was = Services.prefs.getBoolPref(pref);
          const w0 = tb.getBoundingClientRect().width;
          Services.prefs.setBoolPref(pref, !was);
          await new Promise(r => setTimeout(r, 800));
          const w1 = tb.getBoundingClientRect().width;
          Services.prefs.setBoolPref(pref, was);
          await new Promise(r => setTimeout(r, 800));
          return [w0, w1, tb.getBoundingClientRect().width];
        """)
        self.assertNotAlmostEqual(widths[0], widths[1], delta=20, msg=widths)
        self.assertAlmostEqual(widths[0], widths[2], delta=2, msg=widths)

    def test_download(self):
        self.m.chrome("""
          const { Downloads } = ChromeUtils.importESModule('resource://gre/modules/Downloads.sys.mjs');
          const list = await Downloads.getList(Downloads.ALL);
          for (const d of await list.getAll()) await list.remove(d);
        """)
        self.m.navigate(self.server.url("index.html"))
        self.m.js("location.href = '/download.bin'")
        done = self.wait_chrome("""
          const { Downloads } = ChromeUtils.importESModule('resource://gre/modules/Downloads.sys.mjs');
          const list = await Downloads.getList(Downloads.ALL);
          const all = await list.getAll();
          return all.length && all[0].succeeded ? all[0].target.path : null;
        """, timeout=30)
        self.assertTrue(done, "download finished")
        self.assertTrue(os.path.exists(done), done)
        self.assertEqual(os.path.getsize(done), len(b"zen-download-test\n") * 1000)

    def test_extension(self):
        ext_dir = tempfile.mkdtemp(prefix="zen-ext-")
        with open(os.path.join(ext_dir, "manifest.json"), "w") as f:
            json.dump({
                "manifest_version": 2, "name": "Zen test extension", "version": "1.0",
                "browser_specific_settings": {"gecko": {"id": "zen-test@example.invalid"}},
                "content_scripts": [{"matches": ["http://127.0.0.1/*"], "js": ["cs.js"],
                                     "run_at": "document_end"}],
            }, f)
        with open(os.path.join(ext_dir, "cs.js"), "w") as f:
            f.write("document.documentElement.dataset.zenExtension = 'ran';\n")
        try:
            addon = self.m.chrome("""
              const { AddonManager } = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
              const file = new FileUtils.File(arguments[0]);
              const addon = await AddonManager.installTemporaryAddon(file);
              return {id: addon.id, active: addon.isActive};
            """, [ext_dir])
            self.assertTrue(addon["active"], addon)
            self.m.navigate(self.server.url("page2.html"))
            ran = None
            for _ in range(50):
                ran = self.m.js("return document.documentElement.dataset.zenExtension")
                if ran:
                    break
                time.sleep(0.1)
            self.assertEqual(ran, "ran")
        finally:
            self.m.chrome("""
              const { AddonManager } = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
              const a = await AddonManager.getAddonByID('zen-test@example.invalid');
              if (a) await a.uninstall();
            """)
            shutil.rmtree(ext_dir, ignore_errors=True)

    def test_scrolling(self):
        self.m.navigate(self.server.url("tall.html"))
        y = self.m.js("window.scrollTo(0, 3000); return new Promise(r => requestAnimationFrame(() => r(scrollY)));")
        self.assertEqual(y, 3000)
        # A real wheel event through the widget and APZ.
        self.m.set_context("content")
        self.m.send("WebDriver:PerformActions", {"actions": [{
            "type": "wheel", "id": "wheel", "actions": [
                {"type": "scroll", "x": 200, "y": 200, "deltaX": 0, "deltaY": -600}]}]})
        self.m.send("WebDriver:ReleaseActions")
        time.sleep(1.0)
        y2 = self.m.js("return scrollY")
        self.assertLess(y2, 3000)

    def test_audio(self):
        self.m.navigate(self.server.url("audio.html"))
        state = self.m.js("""
          const a = document.getElementById('a');
          await a.play();
          await new Promise(r => setTimeout(r, 1200));
          return {time: a.currentTime, paused: a.paused, duration: a.duration};
        """)
        self.assertFalse(state["paused"], state)
        self.assertGreater(state["time"], 0.5, state)
        self.assertAlmostEqual(state["duration"], 3, delta=0.1)
        playing = self.m.chrome("return gBrowser.selectedTab.hasAttribute('soundplaying')")
        self.assertTrue(playing, "tab shows the sound indicator")
        self.m.navigate("about:blank")

    def test_video(self):
        self.m.navigate(self.server.url("video.html"))
        state = self.m.js("return makeClip()")
        self.assertFalse(state["paused"], state)
        self.assertGreater(state["time"], 0.2, state)
        self.assertEqual((state["w"], state["h"]), (320, 180), state)
        self.assertGreater(state["decoded"], 5, state)


if __name__ == "__main__":
    unittest.main()
