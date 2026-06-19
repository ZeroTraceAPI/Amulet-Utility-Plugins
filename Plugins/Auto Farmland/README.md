# Auto Farmland

Auto Farmland is an Amulet Map Editor operation plugin for converting exposed terrain into farmland, planting crops, and planning safe irrigation across selected Minecraft Bedrock Edition world regions.

## Main Features

* Replaces eligible exposed grass blocks with farmland or creates a raised farmland layer above retained terrain.
* Supports farmland-only operations, one crop, alternating crop rows, assorted crops, and melon or pumpkin stem layouts.
* Supports fixed growth states and deterministic random growth ranges.
* Resolves automatic row direction separately for each selection box.
* Detects existing water before planning new irrigation.
* Adds open water or waterlogged upper-slab covers when safe positions are available.
* Includes 67 selectable upper-slab types, including sulfur and cinnabar variants.
* Protects block entities, productive plants, unsupported surfaces, and unfamiliar obstructions.
* Validates the completed plan before writing and applies it as one undoable Amulet operation.
* Saves settings automatically and includes a built-in operation report.

## Installation

1. Download one Auto Farmland `.py` file from this folder or the repository's [Releases](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/releases) page.
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
3. Open **Auto Farmland** from the Operations tab.
4. Select the terrain and enough vertical space for the intended farmland and crops.
5. Choose the farmland placement mode and crop layout.
6. Configure growth, row direction, stem spacing, and irrigation.
7. Select **Create Farm**.
8. Review the built-in report and inspect the result before saving the world.

## Farmland Placement

### Replace Grass Blocks

When **Replace grass blocks with farmland** is enabled, eligible exposed grass blocks become farmland at their current position. Existing farmland can also remain part of the plan.

The plugin does not continue downward to buried grass when the top exposed block is ineligible. Each selected horizontal column uses its highest safe exposed candidate.

### Raised Farmland

When grass replacement is disabled, the original support block remains and farmland is placed one block above it.

Raised mode supports:

* **Natural terrain only**, for a conservative list of natural-looking full supports.
* **Any safe full block**, which allows more full blocks while still rejecting partial, fluid, interactive, plant-like, and block-entity supports.

**Skip isolated raised farmland** can prevent scattered single farmland blocks from appearing across rough terrain.

### Decorative Plants

**Replace decorative plants above targets** allows a narrow approved list of grass, ferns, flowers, fungi, moss carpets, and similar decoration to be removed when required.

Existing crops, saplings, berry bushes, cactus, bamboo, productive vines, unfamiliar plants, and other protected blocks are not cleared automatically. Supported paired plants are removed together only when the connected form passes the safety checks.

## Crop Layouts

### Farmland Only

Creates farmland without planting crops.

### Single Crop

Plants Wheat, Carrots, Potatoes, or Beetroot across all eligible farmland.

### Alternating Crop Rows

Alternates the selected standard crops by row.

* **Automatic** chooses the longer horizontal axis separately for each selection box.
* **Along X** or **Along Z** applies one explicit direction and alignment across the selected area.
* Earlier selection boxes keep ownership of overlapping columns so later boxes do not rewrite their row pattern.

### Assorted Crops

Distributes the selected standard crops using the saved pattern seed. The same seed and world coordinates reproduce the same crop pattern.

### Melon and Pumpkin Stems

Creates dedicated stem rows with neighboring fruit lanes. **Blocks skipped between stems** controls stem spacing from 0 through 2 blocks.

The planner reserves fruit positions and skips stems that do not have a safe neighboring fruit lane. Raised mode may retain farmland under reserved lanes, while replace mode avoids converting grass used only as fruit space.

## Growth Settings

Standard crops support:

* **Fixed growth state**, from state 0 through 7.
* **Random growth range**, using deterministic values between the selected minimum and maximum.

The pattern seed controls assorted crop choices and randomized growth. The same seed and coordinates produce the same result, which makes layouts repeatable.

Stem layouts use the selected fixed growth state.

## Irrigation

Auto Farmland checks for existing water within normal farmland hydration range before adding new sources.

When **Add water sources where safely needed** is enabled, the planner selects safe source positions that cover the most remaining farmland. Water is not forced into positions that fail the surrounding-support checks or conflict with reserved fruit lanes.

New water can be placed as:

* **Open Water**
* **Waterlogged Upper Slab**

Waterlogged covers use upper-half slabs with source water stored as an Amulet extra block layer.

Initial farmland moisture can be set to:

* **Match planned irrigation**
* **Force dry**
* **Force fully hydrated**

Forced moisture values may later change normally when the world runs in Minecraft.

## Safety and Selection Behavior

Auto Farmland plans first and writes afterward. Before applying the farm, it checks that the relevant source blocks still match the plan.

The plugin also:

* Requires farmland and crop positions to remain inside the selected height.
* Protects block entities and unsupported top blocks.
* Reads nearby boundary context without writing outside the selected farm.
* Skips unavailable chunks safely.
* Prevents later overlapping selection boxes from changing earlier layout ownership.
* Applies the completed farm as one undoable Amulet operation.

If the selection is too short, obstructed, disconnected, or unsuitable for the chosen mode, some columns may be skipped and explained in the report.

## Settings and Reports

Settings are saved automatically to:

```text
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\Config\plugins\edit_plugins\Auto Farmland.config
```

**Manage Plugin Files...** can reset, repair, import, export, or delete the settings file and can open the relevant plugin or settings folders.

The built-in report includes:

* Active settings and selection details
* Eligible and skipped surface columns
* Farmland, crop, growth, stem, and fruit-lane totals
* Existing and newly planned irrigation
* Missing or unavailable chunks
* Planning and write timing
* Warnings and validation results

Use **Save Last Report...** to save the latest report as a UTF-8 text file.

## Things to Consider

* Auto Farmland is designed for Minecraft Bedrock Edition worlds.
* Automatic row direction may differ between separate selection boxes by design.
* Existing hydration is reused when possible, but safe placement rules can leave some farmland without newly added water.
* Waterlogged slab covers depend on Minecraft Bedrock Edition extra-block data being preserved correctly by the target world and Amulet version.
* Large or irregular selections may require more planning time.
* Keep the backup until you are satisfied with the changes, even though the operation supports Amulet undo.

## Screenshots

Screenshots and preview media are available in [`Media/Auto-Farmland`](Media/Auto-Farmland).

## Support and Contact

Report problems through [GitHub Issues](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/issues) and include the Auto Farmland version, Amulet version, Minecraft Bedrock Edition version, settings used, and the saved report when relevant.

If you do not want to create a GitHub account, contact the maintainer at `ZeroTraceAPI@proton.me`. Email support is not guaranteed, but reasonable project-related messages are welcome.

The official source is the [Amulet Utility Plugins GitHub repository](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins).
