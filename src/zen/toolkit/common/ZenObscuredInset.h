/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#ifndef mozilla_ZenObscuredInset_h__
#define mozilla_ZenObscuredInset_h__

#include "mozilla/Maybe.h"
#include "nsColor.h"
#include "nsCoord.h"

class nsIFrame;
class nsPresContext;

namespace mozilla {
namespace dom {
class BrowsingContext;
}  // namespace dom

namespace zen {

/**
 * Obscured top inset ("notch scrolling"), in app units, for the root scroll
 * container of a top-level content document. The browser chrome
 * (ZenFullPanel.mjs) sets BrowsingContext::ZenObscuredTopInset in device
 * pixels while the top of a page lies under the camera housing in FullPanel
 * fullscreen.
 *
 * Semantics follow WebKit's obscuredContentInsets as Talos uses them: the
 * initial containing block, the fixed-position containing block, sticky
 * constraints and the scroll snapport start below the inset, so a page lays
 * out as in a slightly shorter window, while the root scroll port (and
 * therefore scrolled content) still covers the band and scrolls up into it.
 *
 * Returns 0 for every other document, so the layout hooks are no-ops by
 * default.
 */
nscoord ObscuredTopInset(const nsPresContext* aPresContext);

/** Re-lays out the document of aContext after its inset changed. */
void ObscuredTopInsetChanged(dom::BrowsingContext* aContext);

/**
 * Talos's "Solid Color" notch band: at rest the band above the root element
 * shows the document's top-edge color alone. That is the in-flow CSS paint
 * stack a few pixels below the band, sampled at 15%, 50% and 85% of the
 * width (two equal samples win, else the middle one); backgrounds composited
 * over the canvas color, a vertical linear gradient contributing its top
 * stop, fixed-position subtrees skipped (they stay below the band). Derived
 * from styles via hit-testing, never from pixels.
 *
 * ScheduleBandColorUpdate() recomputes it once the current reflow finishes;
 * NoteBandPainted() re-samples at most every 250 ms after paints while the
 * page is at its top (repaint-only changes). BandColor() returns it for
 * painting, or Nothing() to use the canvas color.
 */
void ScheduleBandColorUpdate(nsIFrame* aCanvasFrame);
void NoteBandPainted(nsIFrame* aCanvasFrame);
Maybe<nscolor> BandColor(const nsIFrame* aCanvasFrame);

}  // namespace zen
}  // namespace mozilla

#endif  // mozilla_ZenObscuredInset_h__
