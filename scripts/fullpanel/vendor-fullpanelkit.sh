#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Replaces the vendored FullPanelKit core with the files at <ref> (tag or
# commit) of a FullPanelKit checkout, unmodified, and rewrites UPSTREAM.json.
# Zen's own moz.build in that folder is kept.
#
#   scripts/fullpanel/vendor-fullpanelkit.sh v0.1.0 [~/Projects/FullPanelKit]
set -euo pipefail
REF="${1:?usage: vendor-fullpanelkit.sh <tag-or-commit> [fullpanelkit-checkout]}"
REPO="${2:-$HOME/Projects/FullPanelKit}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$ROOT/src/zen/toolkit/common/cocoa/fullpanel/FullPanelKitCore"
COMMIT="$(git -C "$REPO" rev-parse "$REF^{commit}")"
TAG="$(git -C "$REPO" describe --tags --exact-match "$COMMIT" 2>/dev/null || true)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$REPO" archive "$COMMIT" Sources/FullPanelKitCore LICENSE NOTICE THIRD_PARTY_NOTICES.md | tar -x -C "$TMP"
cp "$DEST/moz.build" "$TMP/moz.build"
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$TMP/Sources/FullPanelKitCore/." "$DEST/"
cp "$TMP/LICENSE" "$TMP/NOTICE" "$TMP/THIRD_PARTY_NOTICES.md" "$TMP/moz.build" "$DEST/"
python3 -I - "$DEST" "$COMMIT" "$TAG" <<'PY'
import hashlib, json, os, sys
dest, commit, tag = sys.argv[1:4]
files = {}
for root, _, names in os.walk(dest):
    for n in names:
        p = os.path.relpath(os.path.join(root, n), dest)
        if p in ("UPSTREAM.json", "moz.build"):
            continue
        files[p] = hashlib.sha256(open(os.path.join(dest, p), "rb").read()).hexdigest()
doc = {
    "project": "FullPanelKit",
    "repository": "https://github.com/brianmerchant/FullPanelKit",
    "tag": tag or None,
    "commit": commit,
    "license": "MIT",
    "paths": "Sources/FullPanelKitCore/**, LICENSE, NOTICE, THIRD_PARTY_NOTICES.md (unmodified)",
    "update": "scripts/fullpanel/vendor-fullpanelkit.sh <tag-or-commit>",
    "sha256": dict(sorted(files.items())),
}
with open(os.path.join(dest, "UPSTREAM.json"), "w") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
print(f"Vendored FullPanelKit {tag or commit}: {len(files)} files")
PY
