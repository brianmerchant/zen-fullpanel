# Building zen-fullpanel (macOS arm64)

The same sequence as upstream's macOS release workflow
(`.github/workflows/macos-release-build.yml`), run natively instead of
cross-compiled, without upstream's secrets (API keys, signing, PGO data).

## Toolchain

| Tool | Version | Source |
|---|---|---|
| macOS / Xcode | 27.0.1 / Xcode with SDK 27; release mozconfig picks CLT SDK 26.5 | `configs/macos/mozconfig` |
| Node.js | 22 (`.nvmrc`) | `/opt/homebrew/opt/node@22/bin` first in `PATH` |
| Rust | 1.95.0 (`.rust-toolchain`) | `rustup toolchain install 1.95.0`; selected with `RUSTUP_TOOLCHAIN=1.95.0` (the user's default toolchain is untouched) |
| Python | 3.11+ (`.python-version` says 3.11; mach ran with 3.14) | Homebrew |
| GNU tar | 1.35 | Homebrew `gnu-tar` |
| sccache | 0.17 | `~/.mozbuild/sccache` (from `mach bootstrap`) |
| Clang, cbindgen, nasm, node for mach | bootstrapped | `~/.mozbuild` |

Disk: about 7.5 GB for `engine/` (with its git), 0.8 GB for the Firefox
tarball in `.surfer/engine`, about 12 GB for the objdir, up to 20 GB of
sccache. Check `df -h` first; keep at least 40 GB free.

## Local overlay (not committed)

`mozconfig` at the repository root is gitignored; Surfer appends it to
`engine/mozconfig`. Use:

```sh
# Local build overlay (gitignored; surfer merges it into engine/mozconfig).
ac_add_options --with-ccache="$HOME/.mozbuild/sccache/sccache"
mk_add_options "export SCCACHE_CACHE_SIZE=20G"
export SCCACHE_CACHE_SIZE=20G
export RUSTUP_TOOLCHAIN=1.95.0
mk_add_options "export RUSTUP_TOOLCHAIN=1.95.0"
```

## Environment for every step

```sh
export PATH=/opt/homebrew/opt/node@22/bin:$PATH
export SURFER_PLATFORM=darwin SURFER_COMPAT=aarch64
export RUSTUP_TOOLCHAIN=1.95.0
```

## From a fresh checkout

```sh
npm ci
# 1. Select the brand. "release" = stock Zen (baseline);
#    "fullpanel" = Zen FullPanel (own bundle id, profile, no updater).
npx surfer ci --brand fullpanel --display-version 1.23.3b
# 2. Firefox source for surfer.json's version (158.0) into engine/.
npm run download
# 3. Zen's prefs, service dumps, branding, src/ files and patches.
npm run import
# 4. Toolchains into ~/.mozbuild only (no Homebrew installs or upgrades).
(cd engine && ./mach --no-interactive bootstrap --application-choice browser --no-system-changes)
# 5. Zen's own strings. Upstream does this inside
#    scripts/download-language-packs.sh; that script also rewrites global
#    git config and deletes ~/tools, so run only the part an en-US build needs.
python3 scripts/copy_language_pack.py en-US
# 6. Release configuration without PGO data or LTO (16 GB machine).
ZEN_RELEASE=1 ZEN_GA_DISABLE_PGO=1 ZEN_DISABLE_LTO=1 npm run build -- --jobs 7
```

The app is `engine/obj-aarch64-apple-darwin/dist/<Brand>.app`. It is a
developer bundle (it links into the objdir). For a self-contained copy run
`(cd engine && ./mach package)` and use the `.app` inside the resulting
`dist/*.dmg`, or stage it as in [STAGING](#staging).

Step 5 is what the earlier attempt missed; without it every Zen menu item is
blank. `python3 scripts/fullpanel/test_zen_baseline.py` checks for it.

## Incremental work

- Files under `src/` that are not patches are **symlinked** into `engine/`
  by `npm run import`, one link per file. Editing an existing one takes
  effect in the next build at once, including a build already running; a
  new file needs `npm run import` to get its link. So keep `src/` still
  while building something that must stay pristine (such as the upstream
  baseline), or stash first. Then `npm run build -- --jobs 7` builds only
  what changed.
- `npm run import` re-applies every patch (each is reverse-applied first,
  then applied), so a patch regenerated with `surfer export` from the
  current `engine/` imports cleanly.
- Edit Gecko files in `engine/`, then turn the change into a tracked patch:
  `npx surfer export <path-relative-to-engine>` writes
  `src/<path>-<ext>.patch` — except for files that an external patch also
  changes (`grep -l 'b/<path>' src/external-patches -r`); for those use
  `scripts/fullpanel/remake-patches.py`. Essential changes must exist as such a patch;
  `engine/` is not tracked and is replaced by the next download.
- `npm run build:ui` (`mach build faster`) is enough for JS/CSS/FTL-only
  changes.
- Switching the brand in an existing objdir (e.g. the `release` baseline,
  then `fullpanel`) leaves `dist/bin` symlinks pointing into the old
  branding directory (the jar packager does not re-point existing links), so
  the app keeps the old brand strings and icons. Remove just those links,
  then build: `find engine/obj-*/dist/bin -type l -lname '*/browser/branding/release/*' -delete`.
  `test_zen_baseline.py` (brand name check) catches it.
- Changing `surfer.json`'s brand, `configs/*/mozconfig` or the changeset
  re-runs configure; with `AUTOCLOBBER=1` (release mozconfig) a CLOBBER
  change rebuilds from scratch. sccache keeps that to minutes.

## Updating FullPanelKit

```sh
scripts/fullpanel/vendor-fullpanelkit.sh v0.1.1   # tag or commit
python3 -I scripts/fullpanel/verify-vendor.py     # hashes vs UPSTREAM.json
```

The script copies `Sources/FullPanelKitCore`, `LICENSE`, `NOTICE` and
`THIRD_PARTY_NOTICES.md` unmodified from `~/Projects/FullPanelKit` at that
ref and rewrites `UPSTREAM.json`. Read the SDK's API diff first
(`git -C ~/Projects/FullPanelKit diff <old>..<new> -- Sources/FullPanelKitCore/include`).
Zen uses `FullPanelSession` (`attachToWindow:error:`, `sessionForWindow:`,
`enabled`, `state`, `fallbackReason`, `active`, `geometry`, `detach`,
`systemSupportAvailable`) and `FullPanelSessionStateDidChangeNotification`.
Do not run `npm run lc:fix` on the vendored folder: it would add MPL
headers to MIT files.

## Updating to a new Zen release (rebase)

```sh
git fetch upstream tag <new-tag> --no-tags
git switch -c feature/zen-fullpanel-<new-tag> <new-tag>   # keep the old branch
git cherry-pick <first-fullpanel-commit>^..feature/zen-fullpanel
```

Conflicts, if any, are in the few upstream files the fork touches:
`surfer.json` (the `fullpanel` brand), `configs/macos/mozconfig` (identity
block at the end), `src/zen/common/ZenPreloadedScripts.js`,
`src/zen/common/jar.inc.mn`, `src/browser/base/content/zen-assets.inc.xhtml`,
`src/zen/toolkit/common/{moz.build,cocoa/moz.build,ZenCommonUtils.cpp,nsIZenCommonUtils.idl}`
and the patches that extend upstream patches
(`src/widget/cocoa/nsCocoaWindow-mm.patch`,
`src/docshell/base/BrowsingContext-h.patch`,
`src/dom/chrome-webidl/BrowsingContext-webidl.patch`).

Extended patches: `nsCocoaWindow-mm.patch` and `moz-configure.patch` are
also touched by external patches, so never `surfer export` them; run
`python3 -I scripts/fullpanel/remake-patches.py --upstream <new-tag>`, which
rebuilds each as upstream's new patch plus the FullPanel hunks (anchored
edits kept in the script) and stops if an anchor moved.
`BrowsingContext-h.patch` and `BrowsingContext-webidl.patch` have no
external patches: re-make the hunk in `engine/` and `surfer export` them. If the Firefox version changed, `npm run download` replaces `engine/`;
check every FullPanel layout patch still applies (`npm run import` stops at
the first that does not).

Then rebuild from step 1 with the new `--display-version`, and run all
suites in [TESTING.md](TESTING.md).

## Staging

`scripts/fullpanel/stage-app.sh` copies the built bundle with
`ditto --noextattr`, resolving the objdir symlinks, to
`~/Projects/Builds/Zen-FullPanel/current/`, signs it ad hoc, and writes
`BUILD-INFO.txt` (commits, brand, bundle id, hashes, toolchain).
