# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Regenerates the Zen patches that the FullPanel fork extends, as
upstream Zen's patch plus the FullPanel hunks, and nothing else.

`surfer export` cannot be used for these files: Firefox and LibreWolf
external patches (src/external-patches/) change the same files, and export
would fold their hunks into Zen's patch. Run after rebasing onto a new Zen
release, then `npm run import`:

  python3 -I scripts/fullpanel/remake-patches.py [--upstream <git ref>]

<git ref> holds upstream's versions of the patches (default 1.23.3b, the
baseline release tag). The pristine Firefox files come from engine/'s git
HEAD (Surfer commits the downloaded source). An anchor that no longer
matches exactly once stops the script: re-make that hunk by hand.
"""

import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (anchor, replacement): each anchor must occur exactly once in Zen's file.
COCOA_EDITS = [
    (
        '#include "mozilla/nsZenDragAndDrop.h"\n',
        '#include "mozilla/nsZenDragAndDrop.h"\n#include "mozilla/ZenFullPanel.h"\n',
    ),
    (
        """  mIsBrowserWindow = true;
  Preferences::RegisterCallback(ZenWindowVibrancyPrefChanged,
                                "zen.widget.macos.window-vibrancy", this);
  UpdateWindowMaterial();
}
""",
        """  mIsBrowserWindow = true;
  Preferences::RegisterCallback(ZenWindowVibrancyPrefChanged,
                                "zen.widget.macos.window-vibrancy", this);
  UpdateWindowMaterial();
  // FullPanel fullscreen (opt-in) for Gecko's own window class only.
  if ([mWindow isKindOfClass:[ToolbarWindow class]]) {
    zen::fullpanel::AttachBrowserWindow(mWindow);
  }
}
""",
    ),
    (
        """  EndOurNativeTransition();

  // We are about to destroy mWindow.""",
        """  EndOurNativeTransition();

  // Restore the menu bar and presentation state FullPanel may own.
  if (mIsBrowserWindow) {
    zen::fullpanel::DetachBrowserWindow(mWindow);
  }

  // We are about to destroy mWindow.""",
    ),
    (
        """  // Re-import state.
  [mWindow importState:state];
""",
        """  // Re-import state.
  [mWindow importState:state];

  // A browser window recreated as a ToolbarWindow gets its FullPanel session
  // again (the old one went with the old window).
  if (mIsBrowserWindow && [mWindow isKindOfClass:[ToolbarWindow class]]) {
    zen::fullpanel::AttachBrowserWindow(mWindow);
  }
""",
    ),
]


MOZ_CONFIGURE_EDITS = [
    (
        """project_flag(
    "MOZ_APP_PROFILE",
    default="zen",
""",
        """# zen-fullpanel: a brand may use its own profile folder (configs/macos/mozconfig).
option(env="ZEN_APP_PROFILE", help="Profile folder name, instead of zen", nargs=1)
imply_option("MOZ_APP_PROFILE", depends_if("ZEN_APP_PROFILE")(lambda v: v[0]))

project_flag(
    "MOZ_APP_PROFILE",
    default="zen",
""",
    ),
]

# engine path -> (Zen patch, edits)
FILES = {
    "widget/cocoa/nsCocoaWindow.mm": ("src/widget/cocoa/nsCocoaWindow-mm.patch", COCOA_EDITS),
    "toolkit/moz.configure": ("src/toolkit/moz-configure.patch", MOZ_CONFIGURE_EDITS),
}


def run(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw).stdout


def remake(path, patch, edits, upstream):
    pristine = run("git", "-C", os.path.join(ROOT, "engine"), "show", f"HEAD:{path}")
    upstream_patch = run("git", "-C", ROOT, "show", f"{upstream}:{patch}")
    with tempfile.TemporaryDirectory() as tmp:
        for side in ("a", "b", "work"):
            os.makedirs(os.path.join(tmp, side, os.path.dirname(path)))
        with open(os.path.join(tmp, "a", path), "w") as f:
            f.write(pristine)
        # Upstream's patch on the pristine file, in a scratch repository.
        work = os.path.join(tmp, "work")
        with open(os.path.join(work, path), "w") as f:
            f.write(pristine)
        run("git", "init", "-q", work)
        subprocess.run(["git", "apply", "--include", path, "-"], input=upstream_patch,
                       text=True, cwd=work, check=True)
        text = open(os.path.join(work, path)).read()
        for anchor, replacement in edits:
            if text.count(anchor) != 1:
                sys.exit(f"{path}: anchor not found exactly once (re-make by hand):\n{anchor}")
            text = text.replace(anchor, replacement, 1)
        with open(os.path.join(tmp, "b", path), "w") as f:
            f.write(text)
        diff = subprocess.run(
            ["git", "diff", "--no-index", "--no-prefix", "--full-index", f"a/{path}", f"b/{path}"],
            cwd=tmp, capture_output=True, text=True,
        ).stdout
    if not diff:
        sys.exit(f"{path}: empty diff")
    with open(os.path.join(ROOT, patch), "w") as f:
        f.write(diff)
    print(f"Wrote {patch}: upstream {upstream} + {len(edits)} FullPanel hunks")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", default="1.23.3b", help="git ref with upstream's patches")
    opts = ap.parse_args()
    for path, (patch, edits) in FILES.items():
        remake(path, patch, edits, opts.upstream)

if __name__ == "__main__":
    main()
