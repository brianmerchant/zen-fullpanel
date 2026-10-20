// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.

// Builds configs/branding/fullpanel from configs/branding/release: the same
// files, with the logo's light rings recolored amber so the development
// build (Zen FullPanel) is never mistaken for an official Zen release.
// Usage, from the repository root: node scripts/fullpanel/make-branding.mjs

import { cpSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import sharp from "sharp";

const source = "configs/branding/release";
const target = "configs/branding/fullpanel";
const accent = [255, 149, 0]; // macOS system orange

rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });
// Surfer regenerates the icns from logo-mac.png at import.
rmSync(join(target, "firefox.icns"), { force: true });

const luminance = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

for (const name of readdirSync(target)) {
  if (!/^logo.*\.png$/.test(name)) {
    continue;
  }
  const path = join(target, name);
  const { data, info } = await sharp(path)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  // The logo is a dark tile (~#202020) with cream rings (~#F0EEE2);
  // anti-aliased edges in between keep their proportion.
  const dark = 32;
  const light = 238;
  for (let i = 0; i < data.length; i += 4) {
    const t = Math.min(
      1,
      Math.max(0, (luminance(data[i], data[i + 1], data[i + 2]) - dark) / (light - dark))
    );
    for (let c = 0; c < 3; c++) {
      data[i + c] = Math.round(dark + (accent[c] - dark) * t);
    }
  }
  await sharp(data, { raw: info }).png().toFile(path + ".tmp");
  cpSync(path + ".tmp", path);
  rmSync(path + ".tmp");
}
console.log(`Wrote ${target}`);
