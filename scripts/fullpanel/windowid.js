// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.

// Prints the CGWindowID of the largest normal window of a process, for
// `screencapture -l` (which captures that window even when it is covered).
//   osascript -l JavaScript scripts/fullpanel/windowid.js <pid>
ObjC.import("CoreGraphics");
function run(argv) {
  const pid = Number(argv[0]);
  const list = ObjC.deepUnwrap(ObjC.castRefToObject(
    $.CGWindowListCopyWindowInfo($.kCGWindowListOptionAll, 0)));
  let best = null;
  for (const w of list) {
    if (w.kCGWindowOwnerPID !== pid || w.kCGWindowLayer !== 0) continue;
    const area = w.kCGWindowBounds.Width * w.kCGWindowBounds.Height;
    if (!best || area > best.area) best = { id: w.kCGWindowNumber, area };
  }
  return best ? String(best.id) : "";
}
