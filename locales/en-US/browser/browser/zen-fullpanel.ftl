# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Tools > Browser Tools > Fullscreen (macOS). "FullPanel" is a product name
# (FullPanelKit) and is not translated.

zen-fullpanel-menu =
    .label = Fullscreen
zen-fullpanel-mode-native =
    .label = Standard Native Fullscreen
zen-fullpanel-mode-fullpanel =
    .label = FullPanel Fullscreen
zen-fullpanel-border-header =
    .label = Window Border
zen-fullpanel-border-inner =
    .label = Inner Border
zen-fullpanel-border-outer =
    .label = Outer Border
zen-fullpanel-notch-header =
    .label = Notch Scrolling Mode
zen-fullpanel-notch-solid =
    .label = Solid Color
zen-fullpanel-notch-off =
    .label = Off (Below Camera Housing)

# Status line at the bottom of the menu.
# $state: one of active, inactive, disabled, fallback, unavailable
# $reason: why ordinary fullscreen is used (English diagnostic name)
zen-fullpanel-status =
    .label =
        { $state ->
            [active] Status: FullPanel active
            [inactive] Status: FullPanel ready
            [fallback] Status: Standard fullscreen ({ $reason })
            [unavailable] Status: FullPanel unavailable on this window
           *[disabled] Status: Standard native fullscreen
        }
zen-fullpanel-next-entry =
    .label = Changes apply when you next enter fullscreen
