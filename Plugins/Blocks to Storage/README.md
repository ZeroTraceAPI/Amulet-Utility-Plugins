# Blocks to Storage

Blocks to Storage is an Amulet Map Editor operation plugin that collects blocks from a selected Minecraft Bedrock Edition world region and places the resulting items into storage instead of permanently discarding them.

The plugin scans and counts the selection, converts supported placed blocks into safe inventory items for Minecraft Bedrock Edition, clears the selected positions, and builds the requested storage layout inside the selected bounds.

## Main Features

* Stores recovered items in chests, barrels, or shulker boxes.
* Supports single chests, double chests, colored shulker boxes, and adjustable vertical stacks.
* Sorts groups by visible Minecraft Bedrock Edition display names or preserves first-seen scan order.
* Can keep each block type in a separate storage group with adjustable spacing.
* Can label separated groups with regular or glow item frames.
* Can pack large exports into shulker-box items stored inside the generated containers.
* Includes state-aware handling for many legacy, imported, generic, placed-only, colored, and variant block identities.
* Uses conservative conversion authority and safely skips unresolved or unsafe item identities by default.
* Includes fast direct chunk scanning and clearing with safer fallback behavior.
* Saves settings automatically and includes detailed reports and optional diagnostics.

## Installation

1. Download one Blocks to Storage `.py` file from this folder or the repository's [Releases](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/releases) page.
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


## Before You Run It

Blocks to Storage intentionally removes blocks from the selection and replaces part of the cleared area with storage. Create a backup of the world before making any changes in case you change your mind, and inspect the selection carefully before starting.

The selected area must be large enough to hold the generated containers. Storage is planned inside the selected bounds, using the available horizontal area and the selected vertical stack height. Protected positions, separated-group spacing, item-frame clearance, and double-chest pairs can reduce the usable space.

The operation stops with a report when the selected area cannot hold the required storage layout.

## Basic Use

1. Create a backup of the world before making any changes in case you change your mind.
2. Open a Minecraft Bedrock Edition world in Amulet.
3. Open **Blocks to Storage** from the Operations tab.
4. Select the blocks to collect and enough room for the resulting storage.
5. Choose the storage container and layout options.
6. Review **Safety** settings, especially **Preserve bedrock** and **Include unusual blocks**.
7. Select **Delete Blocks to Storage**.
8. Review the report, inspect the storage contents, and verify important conversions before saving the world.

## Storage Options

### Storage Container

Choose one of the following:

* **Chest**, with optional 54-slot double chests.
* **Barrel**, using 27-slot containers.
* **Shulker Box**, using 27-slot containers with a selectable color.

**Vertical stack height** controls how many containers may be stacked before the layout begins another line. The default is 8 and the maximum is 40, limited by the selected height.

### ABC Item Order

When enabled, groups are sorted using verified Minecraft Bedrock Edition display names where available. Tested overrides and internal-name fallbacks are used for unresolved names.

When disabled, groups keep first-seen scan order.

Sorting changes organization only. It does not change item conversion, item data, or quantities.

### Separated Groups and Item Frames

**One block type per storage group** keeps each resulting item type in its own container sequence.

Additional options can:

* Add spacing between groups.
* Add an item frame to the first container in each group.
* Use glow item frames for selected valuable groups and regular item frames for common groups.

Item-frame placement reserves front clearance. A selection that is large enough for containers without labels may still be too small once group spacing and frame clearance are enabled.

### Nested Shulker Storage

**Pack into shulker boxes inside storage** fills shulker-box items first and places those items inside the main generated containers. This can greatly reduce the number of physical storage blocks required.

Available modes:

* **Balanced - large groups only**, which leaves smaller groups directly in storage.
* **Compact - all groups**, which uses nested shulker boxes for nearly every group to minimize physical storage.

Nested shulker storage uses more complex item data. Verify important exports in-game before removing the backup.

## Export and Safety Options

### Preserve Bedrock

Enabled by default. Bedrock positions are retained during clearing and excluded from storage placement.

This can reduce the room available for generated containers, especially near the bottom of the world.

### Include Unusual Blocks

Disabled by default. When enabled, supported technical or normally unobtainable block forms may be exported using their unusual item representation.

Leave this disabled for normal survival-friendly exports. Unsafe technical blocks and unresolved identities can still be skipped even when this option is enabled.

### Large Selection Warning

Enabled by default for selections estimated at 500,000 blocks or more. Large exports may require significant time and memory depending on the selection, world, conversion complexity, and storage mode.

## Block-to-Item Conversion

Minecraft world blocks do not always use the same identity or data as inventory items. Blocks to Storage therefore converts supported source blocks before writing them into containers or item frames.

The normal conversion order favors:

1. Built-in state-aware and integrated handling.
2. Verified item-name and data overrides.
3. User-approved `Conversion Entries.BTSP` rules, when enabled.
4. Plugin-reviewed Amulet fallback handling, when enabled.
5. A safe skip when no verified result is available.

The plugin includes handling for many families such as slabs, stairs, walls, doors, signs, logs, leaves, plants, beds, banners, candles, coral, colored blocks, copper variants, sulfur, cinnabar, and imported or legacy identities.

Double slabs normally export as two matching slab items when unusual blocks are disabled. With unusual blocks enabled, supported double-slab block identities can be retained instead.

Some blocks are skipped deliberately to avoid empty, ghost, malformed, or unsafe item entries. The report separates intentional safety skips from unknown or unsupported conversions.

## Optional Display-Name and Conversion Files

**Manage plugin files...** provides local management for the plugin's settings and optional data files.

### `Blocks to Storage.config`

Stores persistent plugin settings.

### `Found Entries.BTSP`

Caches discovered display names and supported conservative identity evidence. It can be used independently of the installed Minecraft language-file fallback.

### `Conversion Entries.BTSP`

Contains user-approved local block-to-item rules. The plugin reads this file when enabled but does not automatically write active rules into it.

### `Conversion Candidates.BTSP`

Stores inactive observations for testing and future review. Candidate entries never change exports or become active conversion rules automatically.

### Minecraft `en_US.lang`

An optional local Minecraft for Windows language file can help resolve missing display names and conservative identity evidence. Built-in verified data keeps priority.

Automatic detection is disabled by default and checks only known installation locations. The plugin does not perform recursive drive searches or send data online.

Missing, empty, malformed, inaccessible, read-only, or oversized optional files do not stop normal exports. Malformed files are preserved rather than silently replaced.

## Performance

**Fast direct chunk scan** and **Fast direct chunk clear** are enabled by default.

* Direct scanning reads chunk data efficiently and rechecks state-sensitive or ambiguous blocks through safer Amulet paths where needed.
* Direct clearing uses cached chunk data for speed.
* Genuine direct-scan or direct-clear failures fall back to safer Amulet behavior where supported.
* Ungenerated or unavailable chunks are skipped or handled safely and are included in the report.

## Reports and Diagnostics

The built-in console reports:

* Selected source-block counts
* Resulting inventory-item counts
* Conversion and display-name sources
* Skipped blocks grouped by reason
* Storage, nested shulker, and item-frame totals
* Protected and unavailable positions
* Scan, clear, placement, and total timing
* Fast-path results and fallback information

Use **Save Last Report...** to save the latest report as a text file.

Normal users can leave **Debug and Diagnostics** and **Advanced Diagnostics** collapsed and disabled. Those options are intended for conversion development, item-frame audits, translator probes, comparison reports, and controlled testing of unresolved writes.

**Attempt unresolved item writes** is a testing option and should remain disabled for normal exports.

## Settings Location

Persistent settings are stored at:

```text
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\Config\plugins\edit_plugins\Blocks to Storage.config
```

Config and supported plugin-managed data writes use temporary files and atomic replacement where applicable. Unknown settings entries are preserved where possible.

## Important Notes

* Blocks to Storage is designed for Minecraft Bedrock Edition worlds.
* The selection is both the source area and the available storage-placement area.
* Block counts and resulting item counts can differ because some blocks convert into different items or quantities.
* Some placed blocks have no safe inventory equivalent and are skipped intentionally.
* Imported Java, legacy, or translated structure data is normalized only when a safe Minecraft Bedrock Edition item equivalent can be identified.
* Item frames and nested shulker boxes use more complex Minecraft Bedrock Edition item data and should be verified after major exports.
* Keep the backup until the result has been checked in both Amulet and Minecraft and you are satisfied with the changes.

## Screenshots

Screenshots and preview media are available in [`Media/Blocks-to-Storage`](Media/Blocks-to-Storage).

## Support and Contact

Report problems through [GitHub Issues](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/issues) and include the Blocks to Storage version, Amulet version, Minecraft Bedrock Edition version, settings used, the saved report, and the identity of any incorrectly converted or skipped block.

If you do not want to create a GitHub account, contact the maintainer at `ZeroTraceAPI@proton.me`. Email support is not guaranteed, but reasonable project-related messages are welcome.

The official source is the [Amulet Utility Plugins GitHub repository](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins).
