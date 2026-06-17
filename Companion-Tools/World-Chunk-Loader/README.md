# World Chunk Loader

World Chunk Loader is an optional Minecraft Bedrock Edition behavior pack that moves the player through a centered square area so Minecraft loads, generates, and saves nearby chunks.

It is mainly included to help prepare worlds for Amulet and the plugins in this repository, but it can also be useful for map preparation, testing, pre-generating areas or reducing chunk loading during normal play.

## Installation

### Windows

1. Download the `.mcpack` file.
2. Make sure Minecraft is fully closed.
3. Double-click the file.
4. Allow Minecraft to open and import the behavior pack.
5. Edit or create a world.
6. Open the Behavior Packs section.
7. Activate the World Chunk Loader Behavior Pack.

Create a copy of the world first in case you change your mind.

Import and activation steps may differ on other Minecraft Bedrock platforms.

## Using World Chunk Loader

World Chunk Loader includes:

* A reliable mode for normal use.
* A faster mode for devices and worlds that can keep up with it.
* Commands for safely stopping a run.
* Cleanup commands for interrupted runs.
* Automatic return to the position where the command was started.


## Behavior

World Chunk Loader:

* Saves the player's starting position before beginning.
* Moves back and forth in rows until the selected area is complete.
* Keeps the requested area centered on the starting position.
* Returns the player after completion or safe cancellation.
* Briefly protects airborne return positions so creative players have time to resume flying.
* Removes temporary data after the operation finishes.
* Allows only one active loading session at a time.
* Avoids replacing existing non-air blocks at temporary chunk-loading positions.

## Things to Consider

* Very large regions can take a long time and increase the world size.
* Performance depends on the device, world, and enabled packs.
* Minecraft may save extra surrounding chunks beyond the requested square.
* A crash, forced shutdown, or pack removal can interrupt automatic cleanup.
* Create a world backup before applying this pack to your world.

## Credits

World Chunk Loader was inspired by the Bedrock World Generator project created by BSavage81, with earlier efficiency work credited to ThatElektrika.

Their project:

[BSavage81 / bedrock-world-generator](https://github.com/bsavage81/bedrock-world-generator)

The current implementation uses a rewritten function structure, new temporary data, serpentine movement, new area-coverage logic, new cleanup and return systems, and new messages.

Credit is retained for the original project concept and its role as the foundation and inspiration for this tool.

## License

World Chunk Loader is covered by the repository's root Mozilla Public License 2.0
