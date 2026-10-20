# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Checks that the vendored FullPanelKit core is byte-identical to the
release recorded in its UPSTREAM.json, with no files added or missing.
Optionally compares against a FullPanelKit checkout as well:

  python3 -I scripts/fullpanel/verify-vendor.py [~/Projects/FullPanelKit]
"""

import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, "src/zen/toolkit/common/cocoa/fullpanel/FullPanelKitCore")
OWN = {"UPSTREAM.json", "moz.build"}


def main():
    meta = json.load(open(os.path.join(DEST, "UPSTREAM.json")))
    want = meta["sha256"]
    have = {}
    for root, _, names in os.walk(DEST):
        for n in names:
            p = os.path.relpath(os.path.join(root, n), DEST)
            if p not in OWN:
                have[p] = hashlib.sha256(open(os.path.join(DEST, p), "rb").read()).hexdigest()
    problems = [f"modified: {p}" for p in want if p in have and have[p] != want[p]]
    problems += [f"missing: {p}" for p in want if p not in have]
    problems += [f"unexpected: {p}" for p in have if p not in want]
    if len(sys.argv) > 1:
        repo = os.path.expanduser(sys.argv[1])
        for p, digest in want.items():
            src = p if p in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md") else f"Sources/FullPanelKitCore/{p}"
            blob = subprocess.run(["git", "-C", repo, "show", f"{meta['commit']}:{src}"],
                                  capture_output=True, check=True).stdout
            if hashlib.sha256(blob).hexdigest() != digest:
                problems.append(f"differs from {meta['commit'][:7]}: {p}")
    for p in problems:
        print(p)
    print(f"FullPanelKit {meta.get('tag') or meta['commit'][:7]}: {len(want)} files, "
          f"{'OK' if not problems else f'{len(problems)} problem(s)'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
