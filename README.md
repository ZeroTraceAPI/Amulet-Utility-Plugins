# Amulet Utility Plugins

A collection of free utility plugins for Amulet Map Editor, focused on Minecraft Bedrock Edition world editing, automation, cleanup, and quality-of-life tools.

These plugins are made for practical editing workflows. Some tools may be niche or built for specific edge cases, but each one is designed to save time, reduce repetitive work, or make certain Amulet editing tasks easier to manage.

Whether you are a map creator, builder, technical player, tester, or someone cleaning up a world, these plugins are meant to help with problems that can be tedious, time-consuming, or awkward to handle manually in Amulet or in-game.

If this repository does not currently have a tool for the problem you are trying to solve, feedback and feature requests are welcome. Useful ideas may be considered for future plugins or updates.


## Current Plugins

### Auto Light

Auto Light helps place light sources in dark areas of a selected Minecraft Bedrock Edition world region.

It is intended to reduce the amount of manual lighting work needed in caves, builds, underground areas, surface areas, farms, tunnels, and other spaces where visibility or hostile mob spawning may be a concern.

This can be useful for map cleanup, spawn-proofing, build preparation, testing areas, or quickly improving lighting across larger selected regions.

### Blocks to Storage

Blocks to Storage collects blocks from a selected Minecraft Bedrock Edition world region and places them into storage containers instead of permanently deleting them.

It can count and sort collected blocks, keep different block types separate, add item-frame labels, and pack large amounts of blocks into shulker boxes. It also handles many block variations automatically so the stored items keep the correct type, color, name, and other supported details.

This can be useful for clearing large areas, recovering materials from world edits, organizing blocks, testing maps, or turning a selected region into a compact storage area.

### Dark Mode UI

Dark Mode UI applies a reversible dark theme to Amulet's wxPython interface after the 3d editor or plugin system loads.

It keeps a persistent controller attached to the Amulet window, can re-theme newly shown panels and includes buttons to open or delete the plugin config file.

This can be useful for long editing sessions, low-light environments, screenshots, or users who prefer a darker interface. The plugin changes UI colors only and does not edit the world.


## Screenshots

Preview screenshots are available in the [`Media`](Media) folder.

Plugin screenshot folders:

* Auto Light: [`Media/Auto-Light`](Media/Auto-Light)
* Blocks to Storage: [`Media/Blocks-to-Storage`](Media/Blocks-to-Storage)
* Dark Mode UI: [`Media/Dark-Mode-UI`](Media/Dark-Mode-UI)

![Amulet Utility Plugins preview](Media/Misc/Cover_1.png)

## Installation (Windows)

1. Download the plugin file you want to use.
2. Move the file into:
```
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\plugins\operations
```
3. Restart Amulet Editor.
4. Open the Operations tab and refresh the plugins if needed.

Create the folders manually if needed.


## Compatibility Notes

These plugins are currently tested on Windows. They may work on other operating systems, but Windows is the supported environment for now.


## Cost

These plugins are free from the original maintainer. Donations may be accepted, but there is no required payment or forced paywall.

## Official Source

The official source is the [Amulet Utility Plugins GitHub repository](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins).

If you share, fork, modify, package, or redistribute these plugins, please link back to the official source so users can find a clean and current copy.

## Contributing

Contributions are welcome. This includes bug reports, feature requests, new ideas, testing notes, documentation improvements, and code changes. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) for more details.

## Contact

For questions, reports, requests, and public discussion, please use GitHub Issues or GitHub Discussions when possible. 
If you do not want to create a GitHub account, you can contact the maintainer by email:

`ZeroTraceAPI@proton.me`

When relevant, include the plugin version, Amulet version, Minecraft Bedrock version, and a clear description. 
Email support is not guaranteed, but reasonable project-related messages are welcome.
