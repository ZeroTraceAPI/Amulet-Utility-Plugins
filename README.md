# Amulet Utility Plugins

A collection of free utility plugins for Amulet Map Editor and optional companion tools for Minecraft Bedrock Edition. The project focuses on practical world-editing automation, cleanup, interface improvements, and reducing repetitive work.

Some tools are designed for specific workflows or edge cases, but each is intended to make Amulet or Minecraft Bedrock editing faster, easier, or more manageable. Bug reports, feature requests, testing notes, and new ideas are welcome.

## Current Plugins

### [Auto Light](Plugins/Auto%20Light)

Places selected light sources across Minecraft Bedrock world regions using fixed-radius or optional brightness-aware coverage. It supports configurable spacing, attachment rules, conservative plant replacement, persistent settings, and operation reports.

### [Auto Farmland](Plugins/Auto%20Farmland) (Coming Soon)

Converts eligible exposed terrain into farmland and can plant single crops, alternating rows, assorted crops, or melon and pumpkin stem layouts. It also supports repeatable growth patterns, existing-hydration detection, safe irrigation, and 67 selectable waterlogged upper-slab covers.

### [Blocks to Storage](Plugins/Blocks%20to%20Storage)

Collects blocks from selected regions and stores the resulting items instead of discarding them. It supports several container layouts, separated and labeled groups, nested shulker packing, Bedrock-aware item conversion, persistent settings, and detailed export reports.

### [Dark Mode UI](Plugins/Dark%20Mode%20UI)

Applies a reversible dark theme to Amulet's wxPython interface, including newly shown panels and supported plugin consoles. It changes interface colors only and does not modify the world.

## Optional Companion Tool

### [World Chunk Pre-Generator](Companion-Tools/World-Chunk-Pre-Generator)

Temporarily moves the player through a centered square area so Minecraft Bedrock Edition cam generate and save nearby chunks in advance. It is intended for Amulet preparation, map testing, and reducing later terrain-generation pauses. It does not keep chunks loaded after the operation ends.

See the tool's [README](Companion-Tools/World-Chunk-Pre-Generator/README.md) for installation and usage or [`COMMANDS.md`](Companion-Tools/World-Chunk-Pre-Generator/COMMANDS.md) for commands.

## Screenshots

Preview media is available in the [`Media`](Media) folder, with separate folders for [Auto Light](Media/Auto-Light), [Auto Farmland](Media/Auto-Farmland), [Blocks to Storage](Media/Blocks-to-Storage), and [Dark Mode UI](Media/Dark-Mode-UI).

![Amulet Utility Plugins preview](Media/Misc/Cover.gif)

## Plugin Installation and Compatibility

1. Download any plugin `.py` file you want to use.
2. Move it into:

```text
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\plugins\operations
```

3. Restart Amulet Editor.
4. Open the Operations tab and refresh the plugin list if needed.

Create the folders manually if they do not already exist.

The plugins are currently tested and supported on Windows. Other operating systems may work but are not currently verified. World Chunk Pre-Generator is designed for Minecraft Bedrock Edition, and its import and activation steps may differ by platform.

## Availability, Contact, and Contributing

All plugins and companion tools are free from the original maintainer, with no required payment or forced paywall. Donations may be accepted but are optional.

The official source is the [Amulet Utility Plugins GitHub repository](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins). When sharing, forking, modifying, packaging, or redistributing these tools, please link back to the official repository so users can find a clean and current copy.

Contributions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for details. Use GitHub Issues or GitHub Discussions for public questions, bug reports, requests, and testing notes when possible.

If you do not want to create a GitHub account, contact the maintainer at:

`ZeroTraceAPI@proton.me`

Include the plugin or tool version, Amulet version, Minecraft Bedrock Edition version, and a clear description when relevant. Email support is not guaranteed, but reasonable project-related messages are welcome.
