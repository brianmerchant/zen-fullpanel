# Zen FullPanel: application identity

The fork builds as **Zen FullPanel**, a development identity that coexists
with stock Zen and never presents itself as an official Zen release. It is
the Surfer brand `fullpanel` (`surfer.json`) plus a brand-keyed block at the
end of `configs/macos/mozconfig`. Building with `--brand release` still
produces stock Zen's identity (used for the baseline).

| | Stock Zen (`release`) | Zen FullPanel (`fullpanel`) |
|---|---|---|
| Bundle | `Zen.app` | `Zen FullPanel.app` |
| `CFBundleIdentifier` | `app.zen-browser.zen` | `io.github.brianmerchant.fullpanel.zen` (`--with-distribution-id` + Zen's `MOZ_MACBUNDLE_ID`) |
| Display name, brand strings | Zen / Zen Browser | Zen FullPanel (`brand.ftl`, `brand.properties`) |
| Icon | Zen logo | Zen logo with amber rings (`scripts/fullpanel/make-branding.mjs`) |
| Profile root | `~/Library/Application Support/zen` | `~/Library/Application Support/zen-fullpanel` (`ZEN_APP_PROFILE`, which implies `MOZ_APP_PROFILE`; a 3-line addition to Zen's `toolkit/moz.configure` patch, since that project flag accepts no mozconfig value) |
| Update channel | `release` | `fullpanel` |
| Updater | yes (`updates.zen-browser.app`) | **none** (`--disable-updater`: no updater binary, no update service) |
| Executable | `zen` | `zen` (unchanged; inside its own bundle) |
| Version | 1.23.3b | 1.23.3b (display version from `surfer.json`) |

## Coexistence audit

- **Profiles.** Separate root, so the fork never reads, migrates or locks a
  stock Zen profile. Remote control (`-remote` / single instance) is keyed
  by profile, so the two never hand URLs to each other.
- **Launch Services.** Different bundle identifier: Dock, Command-Tab,
  default-browser registration, notifications, window restoration
  (`~/Library/Saved Application State/<bundle id>.savedState`), keychain
  items, TCC grants and `defaults` are all separate.
- **URL handling.** The fork declares the same URL schemes and document
  types as Zen (http, https, file, .html...). It only becomes a handler if
  the user picks it as the default browser; nothing registers it
  automatically. `browser.shell.checkDefaultBrowser` is unchanged.
- **Updates.** Without the updater there is nothing that could download
  Zen's release MAR and replace the binary. The update channel is also
  `fullpanel`, which Zen's update server does not serve.
- **Native messaging and extensions.** Native messaging hosts are looked up
  in the profile-independent `~/Library/Application Support/Mozilla/...`
  locations shared by all Gecko browsers; that is the same as stock Zen.

## Licensing

- Zen and Firefox source: MPL-2.0. The fork's modified and new files are
  MPL-2.0 and public in `brianmerchant/zen-fullpanel`; the build records its
  source changeset (`about:buildconfig`, `MOZ_SOURCE_CHANGESET`).
- FullPanelKit core: MIT, vendored unmodified with its `LICENSE`, `NOTICE`
  and `THIRD_PARTY_NOTICES.md`; the notice is reproduced in
  `about:license` (`LICENSES["fullpanelkit"]`).

## Before any public binary distribution

Not done; needed first:

1. **Name and logo.** "Zen" and the Zen logo are Zen's marks. The amber logo
   and "Zen FullPanel" are fine for a private demonstration, but a public
   build needs either written permission from the Zen team or a name and
   icon of its own (keep "based on Zen Browser" as a factual statement).
2. **About dialog and links.** Zen's about dialog, credits
   (`about:credits` → zen-browser.app), privacy policy, donation and
   "What's new" links still point at Zen. They should point at the fork, or
   say plainly that this is an unofficial build.
3. **Crash reports and telemetry.** Disabled in Zen's release configuration;
   keep it that way.
4. **Signing and notarization.** The build is ad-hoc signed. A distributed
   build needs a Developer ID signature, hardened runtime with Gecko's
   entitlements, and notarization.
5. **API keys.** Zen's Safe Browsing, Mozilla location and Google location
   keys are unpublished CI secrets and are not in this build (Safe Browsing
   lists and network geolocation do not work). A public build needs its own
   keys or must leave them out.
6. **Source offer.** Link the exact source revision from the release notes,
   as MPL-2.0 section 3.2 requires for executable distribution.
