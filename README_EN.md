# mania-sunny-rework-web

A Chrome extension (compatible with Edge and other Chromium browsers) for osu!mania beatmap difficulty and PP estimation based on [Sunny Rework](https://github.com/sunnyxxy/Star-Rating-Rebirth). View Sunny Rework star ratings, RC tiers, and real-time PP calculations directly on osu! beatmap pages.

> [中文版 (Chinese)](./README.md)

## Features

- **Sunny Rework Stars** — Star rating estimation for 4K/6K/7K using the Sunny Rework algorithm
- **Daniel Algorithm** — 4K RC tier estimation (Alpha ~ Theta) via Daniel
- **RC / LN Tiers** — Auto-displays RC tier or RC+LN mixed tier based on LN ratio
- **PP Estimation** — Real-time PP for NM/DT/HT columns, supports custom speed (0.5x ~ 2.0x)
- **MOD Support** — Mod combinations: SV1/SV2/NF/EZ/HO/IN and more
- **Custom OD** — Independently adjust OD value, auto-recalculates star rating
- **Judgment Input** — Manually enter miss & judgment counts to compute actual accuracy PP
- **HO/IN Toggle** — One-click switch between HO (rice only) and IN (reverse) modes with separate star/PP calculations

## Installation

> For browsers other than Chrome, please search for "how to load unpacked extensions" for your specific browser.

1. Download the repository ZIP or `git clone`
2. Open Chrome, go to `chrome://extensions/`
3. Enable "Developer mode"
4. Click "Load unpacked" and select the repository folder
5. Open any osu! beatmap page (e.g., `https://osu.ppy.sh/beatmapsets/xxx#mania/xxx`)
6. A persistent difficulty analysis panel appears at the bottom-right corner
7. Click the extension icon to view the full analysis panel

> ⚠️ **When updating the extension, always "Remove" first, then "Load unpacked" again. Clicking the refresh button directly may leave stale code and cause issues (the developer wasted a lot of time debugging this).**

## Usage

| Feature | Description |
|---------|-------------|
| **DT / NM / HT** | Three columns showing 1.5x / 1.0x / 0.75x star ratings and PP |
| **Speed Slider** | Custom speed from 0.5x ~ 2.0x with preset shortcut buttons |
| **Judgment Input** | Enter 320/300/200/100/50/miss counts for real-time PP |
| **Algorithm Switch** | Auto / Daniel / Sunny difficulty estimation modes |
| **MOD Buttons** | Toggle SV1/SV2/NF/EZ/HO/IN, auto-recalculates |
| **Custom OD** | Modify OD value, triggers automatic recalculation |

## Algorithm References

- [Sunny Rework](https://github.com/sunnyxxy/Star-Rating-Rebirth) — Core star rating algorithm
   - [@sunnyxxy](https://github.com/sunnyxxy)
- [Daniel](https://github.com/TheBagelOfMan/Daniel) — 4K RC tier estimation
   - [@TheBagelOfMan](https://github.com/TheBagelOfMan)
- [osumania_map_analyser](https://github.com/LeoBlackMT/osumania_map_analyser) — RC/LN tier mapping reference
   - [@LeoBlackMT](https://github.com/LeoBlackMT) and myself

## License

MIT
