#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Packages the current build (mach package), extracts the self-contained app
# from the dmg into ~/Projects/Builds/Zen-FullPanel/staging/<commit>/,
# verifies it and writes BUILD-INFO.txt. With --promote, moves the existing
# current/ to archive/<its label>/ (never overwriting) and the staged build
# to current/. Follows ~/Projects/Builds/README.md.
#
#   scripts/fullpanel/stage-app.sh [--promote] [--note "verification summary"]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILDS="$HOME/Projects/Builds/Zen-FullPanel"
PROMOTE=0
NOTE="not yet verified on hardware"
while [ $# -gt 0 ]; do
  case "$1" in
    --promote) PROMOTE=1 ;;
    --note) NOTE="$2"; shift ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$ROOT"
COMMIT="$(git rev-parse HEAD)"
SHORT="$(git rev-parse --short HEAD)"
BRANCH="$(git branch --show-current)"
DIRTY="$(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
OBJ="$(ls -d engine/obj-*-apple-darwin | head -1)"
STAMP="$(grep '^SourceStamp=' "$OBJ"/dist/bin/application.ini | cut -d= -f2)"
if [ "$STAMP" != "$COMMIT" ]; then
  echo "warning: build source stamp $STAMP is not HEAD $COMMIT (rebuild after committing)" >&2
fi

(cd engine && ./mach package) >/dev/null
DMG="$(ls -t "$OBJ"/dist/*.dmg | head -1)"
LABEL="$SHORT-fpk$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"][:7])' \
  src/zen/toolkit/common/cocoa/fullpanel/FullPanelKitCore/UPSTREAM.json)"
STAGE="$BUILDS/staging/$LABEL"
rm -rf "$STAGE"
mkdir -p "$STAGE"
MNT="$(mktemp -d)"
hdiutil attach -readonly -nobrowse -mountpoint "$MNT" "$DMG" >/dev/null
APP="$(ls -d "$MNT"/*.app | head -1)"
ditto --noextattr "$APP" "$STAGE/$(basename "$APP")"
hdiutil detach "$MNT" >/dev/null
rmdir "$MNT"
cp "$DMG" "$STAGE/"
STAGED="$STAGE/$(basename "$APP")"

# mach package signs ad hoc; re-sign the whole bundle ad hoc so every
# nested binary and the bundle agree after extraction.
codesign --force --deep --sign - "$STAGED" >/dev/null 2>&1
codesign --verify --deep --strict "$STAGED"
PLIST="$STAGED/Contents/Info.plist"
{
  echo "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleName' "$PLIST") — Zen Browser fork with FullPanelKit fullscreen"
  echo
  echo "Source:        github.com/brianmerchant/zen-fullpanel, branch $BRANCH"
  echo "               commit $COMMIT ($([ "$DIRTY" = 0 ] && echo clean || echo "DIRTY: $DIRTY tracked files modified"))"
  echo "Build stamp:   $STAMP"
  echo "Upstream:      zen-browser/desktop $(git describe --tags --abbrev=0 2>/dev/null || echo '?') (Firefox $(grep -m1 '^Milestone=' "$OBJ"/dist/bin/platform.ini | cut -d= -f2))"
  echo "FullPanelKit:  $(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("tag") or "", d["commit"])' src/zen/toolkit/common/cocoa/fullpanel/FullPanelKitCore/UPSTREAM.json) (vendored, unmodified)"
  echo "Bundle id:     $(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$PLIST")"
  echo "Version:       $(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST")"
  echo "Profile root:  ~/Library/Application Support/$(grep '^Profile=' "$STAGED/Contents/Resources/application.ini" | cut -d= -f2)"
  echo "Updater:       $([ -e "$STAGED/Contents/MacOS/updater.app" ] && echo PRESENT || echo none)"
  echo "Architecture:  $(lipo -archs "$STAGED/Contents/MacOS/zen")"
  echo "Signature:     ad hoc ($(codesign -dv "$STAGED" 2>&1 | grep -m1 '^Signature' || echo 'Signature=adhoc'))"
  echo "Config:        ZEN_RELEASE=1 ZEN_GA_DISABLE_PGO=1 ZEN_DISABLE_LTO=1; Rust ${RUSTUP_TOOLCHAIN:-?}; $(sw_vers -productVersion)"
  echo "Built:         $(grep -m1 '^BuildID=' "$OBJ"/dist/bin/application.ini | cut -d= -f2)"
  echo "Staged:        $(date '+%Y-%m-%d %H:%M %Z') by scripts/fullpanel/stage-app.sh"
  echo "SHA-256:"
  shasum -a 256 "$STAGED/Contents/MacOS/zen" "$STAGED/Contents/MacOS/XUL" "$STAGE/$(basename "$DMG")" | sed "s|$STAGE/||; s|^|  |"
  echo
  echo "Verification:  $NOTE"
} > "$STAGE/BUILD-INFO.txt"
cat "$STAGE/BUILD-INFO.txt"

if [ "$PROMOTE" = 1 ]; then
  mkdir -p "$BUILDS/archive"
  if [ -d "$BUILDS/current" ] && [ -n "$(ls -A "$BUILDS/current")" ]; then
    OLD="$(cat "$BUILDS/current/.label" 2>/dev/null || date +%Y%m%d-%H%M%S)"
    if [ -e "$BUILDS/archive/$OLD" ]; then
      echo "archive/$OLD exists; not overwriting" >&2
      exit 1
    fi
    mv "$BUILDS/current" "$BUILDS/archive/$OLD"
  fi
  mv "$STAGE" "$BUILDS/current"
  echo "$LABEL" > "$BUILDS/current/.label"
  echo "Promoted to $BUILDS/current"
fi
