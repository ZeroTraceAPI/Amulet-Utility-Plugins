# Auto Light

Auto Light is an Amulet Map Editor operation plugin for placing light sources across selected Minecraft Bedrock Edition world regions. It is intended to reduce repetitive lighting work in caves, tunnels, farms, builds, underground spaces, testing areas, and other large selections.

## Main Features

* Places torches, lanterns, copper lights, sea lanterns, or firefly bushes.
* Supports fixed-distance detection through Legacy Light Radius.
* Supports optional calculated coverage based on recognized Minecraft Bedrock Edition light-source strength and saved block state.
* Includes spread placement and regular row / grid spacing.
* Supports floor, wall, and ceiling attachment rules where appropriate.
* Can replace approved grass, flowers, and other small decorative plants at placement positions.
* Handles connected plant halves so supported tall plants are not left incomplete or floating.
* Keeps block selection available while the floating window is open.
* Uses a resizable custom floating window with a compact launcher in Amulet's Operations panel.
* Includes an optional visual light-source selector using Amulet's cached Minecraft textures, with text-only fallback.
* Remembers the main-window size, Manage Plugin Files window size, report-console visibility, and visual-selector preference.
* Saves settings automatically and includes local settings-management tools.
* Includes a built-in operation report with warnings, timing, and placement details.

## Installation

1. Download one Auto Light `.py` file from this folder or the repository's [Releases](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/releases) page.
2. Move the file into:

```text
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\plugins\operations
```

3. Restart Amulet Editor.
4. Open a world, open the Operations tab, and refresh the plugin list if needed.

## Commented and Uncommented Files

Some releases provide two versions of the plugin source:

* **Uncommented:** Recommended for normal use in Amulet. It contains the same plugin logic in a smaller, cleaner file with most explanatory comments and docstrings removed.
* **Commented:** Intended for people who want to read, study, review, modify, or navigate the code more easily. It includes explanatory comments and docstrings, so the file is larger.

Both versions work in Amulet and are intended to behave the same. Python ignores comments after reading the source, so the practical loading-speed difference is normally very small. The uncommented version mainly provides a smaller and cleaner normal-use file, while the commented version provides better code documentation.

Install only one version at a time. Installing both can create duplicate operation entries because each file registers the same plugin.


## Basic Use

1. Create a backup of the world before making any changes in case you change your mind.
2. Open a Minecraft Bedrock Edition world in Amulet.
3. Open **Auto Light** from the Operations tab. Its floating window opens automatically, and the compact launcher remains available for focusing or reopening it.
4. Select the area that should be checked.
5. Choose a light type and detection mode.
6. Adjust spacing and the placement options shown for that light type.
7. Select **Place Lights**.
8. Review the built-in report before saving the world.

## Light Types

Supported light types:

* Torch
* Soul Torch
* Copper Torch
* Lantern
* Soul Lantern
* Copper Lantern
* Exposed Copper Lantern
* Weathered Copper Lantern
* Oxidized Copper Lantern
* Copper Bulb
* Exposed Copper Bulb
* Weathered Copper Bulb
* Oxidized Copper Bulb
* Sea Lantern
* Firefly Bush

Copper lanterns and bulbs can optionally use waxed variants. Copper bulbs can also be placed in their lit state.

## Detection Modes

### Legacy Light Radius

Legacy mode checks for recognized pre-existing light-source blocks within one fixed radius. The source's actual brightness is ignored, so weak and strong sources use the same selected distance.

This remains the default mode and is useful when a predictable fixed-distance rule is preferred.

### Calculated Light Coverage

Calculated coverage estimates open-space block-light decay from recognized Minecraft Bedrock Edition light sources. Stronger sources cover farther than weaker sources, supported active and inactive states are considered, and lights placed during the current operation contribute to later placement decisions.

The strongest nearby source is used. Light values are not added together.

Calculated coverage is an estimate, not a full Minecraft lighting simulation. It does not currently model walls, block opacity, slabs, stairs, or other light-blocking geometry. Use Legacy Light Radius when fixed and fully predictable spacing is more important than brightness-aware estimates.

### Inactive Light Sources

**Treat inactive light sources as lit** is enabled by default. This helps prevent permanent lights from being placed next to lamps, bulbs, campfires, furnaces, candles, and other conditional sources that may be activated later.

Disable it to use the current supported in-world state of those sources instead.

## Placement and Spacing

**Light Spacing** controls the minimum gap between lights placed during the current operation.

* In row / grid mode, the value means the number of blocks skipped before the next placement. A value of 5 skips five blocks and places on the sixth.
* In spread mode, it controls the older spread-distance behavior.

Additional controls appear when relevant:

* **Allow floor torches**
* **Allow wall torches**
* **Allow floor lanterns**
* **Allow ceiling lanterns**
* **Waxed copper variants**
* **Lit copper bulbs**
* **Only place on air**
* **Replace plants / grass with lights**

When plant replacement is enabled, Auto Light uses a conservative approved list rather than clearing every plant-like block. Existing productive or unfamiliar plants are not treated as safe replacement targets automatically.

## Settings and Reports

Settings are saved automatically to:

```text
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\Config\plugins\edit_plugins\Auto Light.config
```

**Manage Plugin Files...** can save, reset, repair, import, export, delete, or open the folder for the config file. Unknown settings entries are preserved where possible so future options are not discarded unnecessarily.

The built-in console reports:

* Active settings and selection details
* Recognized light-source information
* Placement and skip totals
* Missing or unavailable chunks
* Warnings and operation timing
* Performance information

Use **Save Report** to save the latest report as a UTF-8 text file.

## Things to Consider

* Auto Light is designed for Minecraft Bedrock Edition worlds.
* Calculated coverage estimates recognized block light and should not be treated as an exact copy of Minecraft's complete lighting engine.
* Unavailable selection or neighboring chunks are skipped safely and reported instead of stopping the entire operation.
* Overlapping selection boxes are deduplicated so the same coordinates are not processed repeatedly.
* Large selections may take time depending on world data, settings, and system performance.
* Review the result in Amulet and keep the backup until you are satisfied with the changes.

## Screenshots

Screenshots and preview media are available in [`Media/Auto-Light`](Media/Auto-Light).

## Support and Contact

Report problems through [GitHub Issues](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/issues) and include the Auto Light version, Amulet version, Minecraft Bedrock Edition version, settings used, and the saved report when relevant.

If you do not want to create a GitHub account, contact the maintainer at `ZeroTraceAPI@proton.me`. Email support is not guaranteed, but reasonable project-related messages are welcome.

The official source is the [Amulet Utility Plugins GitHub repository](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins).
