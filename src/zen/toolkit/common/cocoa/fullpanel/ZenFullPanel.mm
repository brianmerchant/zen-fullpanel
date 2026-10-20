/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#include "mozilla/ZenFullPanel.h"

#include "mozilla/Preferences.h"
#include "mozilla/Services.h"
#include "nsCocoaUtils.h"
#include "nsIObserverService.h"
#include "nsIWidget.h"
#include "nsPIDOMWindow.h"
#include "nsThreadUtils.h"
#include "WidgetUtils.h"

#import <AppKit/AppKit.h>

#import "FullPanelSession.h"

namespace zen::fullpanel {

using ::mozilla::Preferences;
using ::mozilla::widget::WidgetUtils;

static constexpr char kEnabledPref[] = "zen.fullpanel.enabled";
static constexpr char kStateTopic[] = "zen-fullpanel-state-changed";

static bool sInitialized = false;
static bool sNotifyPending = false;

static bool PrefersFullPanel() {
  return Preferences::GetBool(kEnabledPref, false);
}

// The chrome re-reads every window's state, so one notification per event
// loop turn is enough. Never sent from inside AppKit's own callbacks.
static void NotifyChrome() {
  if (sNotifyPending) {
    return;
  }
  sNotifyPending = true;
  NS_DispatchToMainThread(NS_NewRunnableFunction("zen::fullpanel::Notify", [] {
    sNotifyPending = false;
    if (nsCOMPtr<nsIObserverService> obs =
            mozilla::services::GetObserverService()) {
      obs->NotifyObservers(nullptr, kStateTopic, nullptr);
    }
  }));
}

// FullPanel or standard native fullscreen, as the pref says. A window in
// fullscreen keeps the mode it entered with; it changes on exit, so a switch
// always takes effect from the next entry (as Talos's Develop toggle).
static void SyncSession(NSWindow* aWindow) {
  FullPanelSession* session = [FullPanelSession sessionForWindow:aWindow];
  if (!session || (aWindow.styleMask & NSWindowStyleMaskFullScreen)) {
    return;
  }
  const bool enabled = PrefersFullPanel();
  if (session.enabled != enabled) {
    session.enabled = enabled;
  }
}

static void EnabledPrefChanged(const char* aPref, void* aClosure) {
  for (NSWindow* window in NSApp.windows) {
    SyncSession(window);
  }
  NotifyChrome();
}

static void EnsureInitialized() {
  if (sInitialized) {
    return;
  }
  sInitialized = true;
  Preferences::RegisterCallback(EnabledPrefChanged,
                                nsDependentCString(kEnabledPref));
  // Lives for the process. Every session posts it, on the main thread, for
  // entry, exit, fallback, Space returns and screen changes.
  [NSNotificationCenter.defaultCenter
      addObserverForName:FullPanelSessionStateDidChangeNotification
                  object:nil
                   queue:nil
              usingBlock:^(NSNotification*) {
                NotifyChrome();
              }];
  // After FullPanelKit's own exit handling, which also observes this.
  [NSNotificationCenter.defaultCenter
      addObserverForName:NSWindowDidExitFullScreenNotification
                  object:nil
                   queue:nil
              usingBlock:^(NSNotification* aNote) {
                NSWindow* window = [aNote.object retain];
                NS_DispatchToMainThread(NS_NewRunnableFunction(
                    "zen::fullpanel::SyncSession", [window] {
                      SyncSession(window);
                      [window release];
                    }));
              }];
}

void AttachBrowserWindow(NSWindow* aWindow) {
  NS_OBJC_BEGIN_TRY_IGNORE_BLOCK;

  // FullPanelKit's minimum. Below it no session exists, so none of its code
  // runs and fullscreen is Zen's own.
  if (@available(macOS 13.0, *)) {
  } else {
    return;
  }
  if (!aWindow || [FullPanelSession sessionForWindow:aWindow]) {
    return;
  }
  EnsureInitialized();
  NSError* error = nil;
  FullPanelSession* session = [FullPanelSession attachToWindow:aWindow
                                                         error:&error];
  if (!session) {
    NSLog(@"Zen FullPanel: not attached to %@: %@", aWindow.className,
          error.localizedDescription);
    return;
  }
  session.enabled = PrefersFullPanel();
  NotifyChrome();

  NS_OBJC_END_TRY_IGNORE_BLOCK;
}

void DetachBrowserWindow(NSWindow* aWindow) {
  NS_OBJC_BEGIN_TRY_IGNORE_BLOCK;

  if (!aWindow) {
    return;
  }
  [[FullPanelSession sessionForWindow:aWindow] detach];

  NS_OBJC_END_TRY_IGNORE_BLOCK;
}

static NSString* StateName(FullPanelState aState) {
  switch (aState) {
    case FullPanelStateDisabled:
      return @"disabled";
    case FullPanelStateInactive:
      return @"inactive";
    case FullPanelStateActive:
      return @"active";
    case FullPanelStateFallback:
      return @"fallback";
  }
  return @"unknown";
}

static NSString* FallbackName(FullPanelFallbackReason aReason) {
  switch (aReason) {
    case FullPanelFallbackReasonNone:
      return @"none";
    case FullPanelFallbackReasonNoCameraHousing:
      return @"noCameraHousing";
    case FullPanelFallbackReasonAppKitUnavailable:
      return @"appKitUnavailable";
    case FullPanelFallbackReasonSkyLightUnavailable:
      return @"skyLightUnavailable";
    case FullPanelFallbackReasonMenuBarAlwaysShown:
      return @"menuBarAlwaysShown";
    case FullPanelFallbackReasonFrameNotAccepted:
      return @"frameNotAccepted";
  }
  return @"unknown";
}

// A screen rect (global, bottom-left origin) relative to the window's
// top-left corner. Browser windows use a full-size content view, so this is
// also the chrome's coordinate space (in points).
static NSDictionary* WindowRect(NSRect aScreenRect, NSRect aWindowFrame) {
  return @{
    @"x" : @(NSMinX(aScreenRect) - NSMinX(aWindowFrame)),
    @"y" : @(NSMaxY(aWindowFrame) - NSMaxY(aScreenRect)),
    @"width" : @(NSWidth(aScreenRect)),
    @"height" : @(NSHeight(aScreenRect)),
  };
}

nsresult DescribeWindow(mozIDOMWindowProxy* aWindow, nsAString& aResult) {
  NS_OBJC_BEGIN_TRY_BLOCK_RETURN;

  aResult.AssignLiteral("{}");
  if (!aWindow) {
    return NS_ERROR_INVALID_ARG;
  }
  nsCOMPtr<nsIWidget> widget =
      WidgetUtils::DOMWindowToWidget(nsPIDOMWindowOuter::From(aWindow));
  if (!widget) {
    return NS_OK;
  }
  NSWindow* window = (NSWindow*)widget->GetNativeData(NS_NATIVE_WINDOW);
  FullPanelSession* session =
      window ? [FullPanelSession sessionForWindow:window] : nil;
  if (!session) {
    return NS_OK;
  }

  @autoreleasepool {
    NSMutableDictionary* state = [NSMutableDictionary dictionary];
    state[@"available"] = @([FullPanelSession systemSupportAvailable]);
    state[@"attached"] = @(session.attached);
    state[@"enabled"] = @(session.enabled);
    state[@"state"] = StateName(session.state);
    state[@"fallback"] = FallbackName(session.fallbackReason);
    state[@"active"] = @(session.active);
    state[@"fullscreen"] =
        @((window.styleMask & NSWindowStyleMaskFullScreen) != 0);
    const NSRect frame = window.frame;
    state[@"window"] = WindowRect(frame, frame);
    FullPanelDisplayGeometry* geometry = session.geometry;
    if (geometry.hasCameraHousing) {
      state[@"topInset"] = @(geometry.topInset);
      if (!NSIsEmptyRect(geometry.cameraHousingRect)) {
        state[@"housing"] = WindowRect(geometry.cameraHousingRect, frame);
      }
    }
    NSData* json = [NSJSONSerialization dataWithJSONObject:state
                                                   options:0
                                                     error:nil];
    if (json) {
      NSString* string = [[[NSString alloc] initWithData:json
                                                encoding:NSUTF8StringEncoding]
          autorelease];
      nsCocoaUtils::GetStringForNSString(string, aResult);
    }
  }
  return NS_OK;

  NS_OBJC_END_TRY_BLOCK_RETURN(NS_OK);
}

}  // namespace zen::fullpanel
