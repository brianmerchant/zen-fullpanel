# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""A small Marionette client and launcher for testing a built Zen app.

Release builds (--disable-tests) have no marionette harness in the objdir,
so the suites in this directory speak the Marionette protocol directly:
length-prefixed JSON over a localhost socket.

Every launch uses its own throwaway profile (never the user's), with
updates, telemetry and default-browser prompts off. Set ZEN_APP to the .app
bundle to test (default: the objdir's dist bundle).
"""

import glob
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

PREFS = {
    "app.update.auto": False,
    "app.update.disabledForTesting": True,
    "app.update.background.enabled": False,
    "app.update.checkInstallTime": False,
    "browser.shell.checkDefaultBrowser": False,
    "browser.startup.homepage_override.mstone": "ignore",
    "datareporting.policy.dataSubmissionEnabled": False,
    "toolkit.telemetry.enabled": False,
    "browser.aboutwelcome.enabled": False,
    "zen.welcome-screen.seen": True,
    "browser.download.useDownloadDir": True,
    "browser.download.always_ask_before_handling_new_types": False,
    "browser.tabs.warnOnClose": False,
    "browser.warnOnQuit": False,
    "browser.sessionstore.resume_from_crash": False,
    # Zen's "updated" sidebar card; its window sweep animation is skipped
    # through zen.updates.last-build-id (set per app in ZenApp.start).
    "zen.updates.show-update-notification": False,
}


def default_app():
    # The most recently built bundle: dist/ keeps a bundle from an earlier
    # brand when the brand changes.
    apps = glob.glob(os.path.join(ROOT, "engine", "obj-*", "dist", "*.app"))
    apps.sort(key=lambda a: os.path.getmtime(os.path.join(a, "Contents", "Info.plist")))
    return os.environ.get("ZEN_APP") or (apps[-1] if apps else None)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MarionetteError(Exception):
    pass


class Marionette:
    def __init__(self, port):
        self.port = port
        self.sock = None
        self.msg_id = 0
        self.context = "content"

    def connect(self, timeout=60):
        deadline = time.time() + timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), 2)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.25)
        self.sock.settimeout(120)
        self._recv()  # hello
        self.send("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {}}})

    def _recv(self):
        length = b""
        while not length.endswith(b":"):
            chunk = self.sock.recv(1)
            if not chunk:
                raise MarionetteError("connection closed")
            length += chunk
        size = int(length[:-1])
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise MarionetteError("connection closed")
            data += chunk
        return json.loads(data)

    def send(self, name, params=None):
        self.msg_id += 1
        body = json.dumps([0, self.msg_id, name, params or {}]).encode()
        self.sock.sendall(str(len(body)).encode() + b":" + body)
        while True:
            msg = self._recv()
            if msg[0] == 1 and msg[1] == self.msg_id:
                break
        if msg[2]:
            raise MarionetteError(f"{name}: {msg[2].get('error')}: {msg[2].get('message')}")
        result = msg[3]
        if isinstance(result, dict) and set(result) == {"value"}:
            return result["value"]
        return result

    def set_context(self, context):
        if context != self.context:
            self.send("Marionette:SetContext", {"value": context})
            self.context = context

    def js(self, script, args=None, context="content"):
        """Runs script; a returned promise is awaited."""
        self.set_context(context)
        # Scripts may use await: run the body as an async function.
        body = f"return (async function () {{ {script}\n }}).apply(this, arguments);"
        params = {"script": body, "args": args or [], "scriptTimeout": 60000}
        if context == "chrome":
            params["sandbox"] = "system"
        return self.send("WebDriver:ExecuteScript", params)

    def chrome(self, script, args=None):
        return self.js(script, args, "chrome")

    def navigate(self, url):
        self.set_context("content")
        self.send("WebDriver:Navigate", {"url": url})

    def back(self):
        self.set_context("content")
        self.send("WebDriver:Back")

    def click_at(self, x, y):
        """A real pointer click at viewport coordinates of the content."""
        self.set_context("content")
        self.send("WebDriver:PerformActions", {"actions": [{
            "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
            "actions": [
                {"type": "pointerMove", "x": int(x), "y": int(y), "origin": "viewport"},
                {"type": "pointerDown", "button": 0},
                {"type": "pointerUp", "button": 0},
            ],
        }]})
        self.send("WebDriver:ReleaseActions")

    def settle(self, frames=2):
        """Waits for frames in the content (field sync, reflow, paint)."""
        self.js(
            "return new Promise(r => { let n = arguments[0];"
            " const f = () => (--n ? requestAnimationFrame(f) : r());"
            " requestAnimationFrame(f); });",
            [frames],
        )

    def quit(self):
        try:
            self.set_context("chrome")
            self.send("Marionette:Quit", {"flags": ["eForceQuit"]})
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class ZenApp:
    """Launches a built app with a fresh profile and Marionette."""

    def __init__(self, app=None, prefs=None, env=None, profile_root=None, keep=False,
                 profile=None):
        self.app = app or default_app()
        if not self.app or not os.path.isdir(self.app):
            raise RuntimeError(f"no app bundle: {self.app}")
        self.prefs = dict(PREFS, **(prefs or {}))
        self.env = env or {}
        self.keep = keep
        root = profile_root or os.path.join(os.path.dirname(ROOT), "test-profiles")
        os.makedirs(root, exist_ok=True)
        # An existing profile is reused as it is (restoration tests).
        self.profile = profile or tempfile.mkdtemp(prefix="zentest-", dir=root)
        self.downloads = os.path.join(self.profile, "downloads")
        os.makedirs(self.downloads, exist_ok=True)
        self.port = free_port()
        self.proc = None
        self.m = None

    @property
    def binary(self):
        macos = os.path.join(self.app, "Contents", "MacOS")
        for name in ("zen", "firefox"):
            if os.path.exists(os.path.join(macos, name)):
                return os.path.join(macos, name)
        raise RuntimeError(f"no executable in {macos}")

    def start(self):
        prefs = dict(self.prefs)
        prefs["marionette.port"] = self.port
        prefs["browser.download.dir"] = self.downloads
        prefs["browser.download.folderList"] = 2
        ini = os.path.join(self.app, "Contents", "Resources", "application.ini")
        for line in open(ini):
            if line.startswith("BuildID="):
                prefs.setdefault("zen.updates.last-build-id", line.split("=", 1)[1].strip())
        with open(os.path.join(self.profile, "user.js"), "w") as f:
            for k, v in prefs.items():
                f.write(f"user_pref({json.dumps(k)}, {json.dumps(v)});\n")
        env = dict(os.environ, MOZ_CRASHREPORTER_DISABLE="1", **self.env)
        self.log = open(os.path.join(self.profile, "browser.log"), "w")
        self.proc = subprocess.Popen(
            [self.binary, "--marionette", "--remote-allow-system-access", "--no-remote",
             "--profile", self.profile],
            env=env, stdout=self.log, stderr=subprocess.STDOUT,
        )
        self.m = Marionette(self.port)
        self.m.connect()
        # Wait for the first browser window to finish its delayed startup.
        self.m.chrome(
            "return new Promise(r => { const w = Services.wm.getMostRecentWindow('navigator:browser');"
            " if (w && w.gBrowserInit && w.gBrowserInit.delayedStartupFinished) return r();"
            " const o = (s) => { Services.obs.removeObserver(o, 'browser-delayed-startup-finished'); r(); };"
            " Services.obs.addObserver(o, 'browser-delayed-startup-finished'); });"
        )
        return self.m

    def stop(self):
        if self.m:
            self.m.quit()
        if self.proc:
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log:
            self.log.close()
        if not self.keep:
            shutil.rmtree(self.profile, ignore_errors=True)


class ZenTestCase(unittest.TestCase):
    """One browser per test class."""

    prefs = {}

    @classmethod
    def setUpClass(cls):
        cls.zen = ZenApp(prefs=cls.prefs, keep=bool(os.environ.get("ZEN_KEEP_PROFILE")))
        cls.m = cls.zen.start()

    @classmethod
    def tearDownClass(cls):
        cls.zen.stop()
