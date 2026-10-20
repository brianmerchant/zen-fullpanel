/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#ifndef mozilla_ZenFullPanel_h__
#define mozilla_ZenFullPanel_h__

#include "nsError.h"
#include "nsStringFwd.h"

#ifdef __OBJC__
@class NSWindow;
#else
typedef struct objc_object NSWindow;
#endif

class mozIDOMWindowProxy;

/**
 * FullPanelKit fullscreen for Zen browser windows (macOS only).
 *
 * FullPanelKit (vendored in FullPanelKitCore/, MIT) attaches a session to
 * Gecko's own NSWindow subclass (ToolbarWindow). Fullscreen stays AppKit's
 * native fullscreen Space; while the session is enabled, AppKit lays the
 * window out over the whole display, including the areas beside the camera
 * housing, and the menu bar is revealed from the top edge.
 *
 * Opt-in: sessions follow the "zen.fullpanel.enabled" pref (default false).
 * Changing it applies from the next fullscreen entry. With it off, Zen's
 * fullscreen is unchanged.
 */
namespace zen::fullpanel {

/* Attaches a session to a top-level browser window. Idempotent. */
void AttachBrowserWindow(NSWindow* aWindow);

/* Restores system state and removes the session, before Gecko releases the
 * native window. */
void DetachBrowserWindow(NSWindow* aWindow);

/* JSON describing the FullPanel state of aWindow's native window, for the
 * browser chrome (ZenFullPanel.mjs). Geometry is in points, relative to the
 * window's top-left corner. "{}" for a window without a session. */
nsresult DescribeWindow(mozIDOMWindowProxy* aWindow, nsAString& aResult);

}  // namespace zen::fullpanel

#endif  // mozilla_ZenFullPanel_h__
