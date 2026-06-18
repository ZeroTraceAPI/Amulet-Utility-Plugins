# World Chunk Pre-Generator

World Chunk Pre-Generator is an optional Minecraft Bedrock Edition behavior pack that temporarily moves the player through a centered square area so Minecraft generates and saves nearby chunks ahead of time.

It does not create a permanent chunk-loading area, keep distant chunks active, or continue loading chunks after the operation ends.

The pack is mainly included to prepare worlds for Amulet and the plugins in this repository. It can also be useful for map preparation, testing, pre-generating areas, and reducing terrain-generation pauses during later play.

## Installation

### Windows

1. Download the `.mcpack` file.
2. Make sure Minecraft is fully closed.
3. Double-click the file.
4. Allow Minecraft to open and import the behavior pack.
5. Edit or create a world.
6. Open the Behavior Packs section.
7. Activate the World Chunk Pre-Generator Behavior Pack.

Create a copy of the world first in case you change your mind.

Import and activation steps may differ on other Minecraft Bedrock platforms.

## Using World Chunk Pre-Generator

World Chunk Pre-Generator includes:

* A reliable mode with the most movement overlap.
* A faster mode that stays close to the requested area size.
* A batch mode that processes 4 × 4 chunk areas for much faster large runs.
* Five shared speed presets ranging from 5 ticks to 1 tick per cycle.
* Commands for safely stopping a run.
* Cleanup commands for interrupted runs.
* Automatic return to the position where the command was started.

Commands use short names such as `/function load_250`, `/function fast_250`, and `/function batch_250`.

Speed 4, which runs every 2 game ticks, is the default. Use `/function speed_1` through `/function speed_5` to change the shared speed, `/function speed_status` to view it, or `/function speed_reset` to restore the default.

These commands start a temporary pre-generation run and do not keep chunks loaded after it finishes.

See [`COMMANDS.md`](COMMANDS.md) for available sizes, speed presets, and command usage.

## Behavior

World Chunk Pre-Generator:

* Saves the player's starting position before beginning.
* Moves the player back and forth in rows until the selected area is complete.
* Keeps the requested area centered on the starting position.
* Causes Minecraft to generate and save chunks encountered during the run.
* Briefly waits at important boundaries so nearby chunks can finish generating and saving.
* Returns the player after completion or safe cancellation.
* Briefly protects airborne return positions so creative players have time to resume flying.
* Removes temporary data after the operation finishes.
* Allows only one active pre-generation session at a time.
* Avoids replacing existing non-air blocks at temporary movement positions.

Reliable and Fast modes stay close to the requested size. Batch mode works in 64-block groups and rounds the requested area up to the next multiple of 64.

## Things to Consider

* Very large regions can take a long time and increase the world size.
* Higher speed presets require the device and world to generate and save chunks more quickly.
* Speed 5 runs every game tick and should be tested with a smaller area before large runs.
* Performance depends on the device, world, simulation distance, render distance, and enabled packs.
* Minecraft may generate and save additional surrounding chunks beyond the requested square.
* A crash, forced shutdown, or pack removal can interrupt automatic cleanup.
* Create a world backup before applying this pack to your world.

## Credits

World Chunk Pre-Generator was inspired by the Bedrock World Generator project created by BSavage81, with earlier efficiency work credited to ThatElektrika.

Their project:

[BSavage81 / bedrock-world-generator](https://github.com/bsavage81/bedrock-world-generator)

The current implementation uses a rewritten function structure, new temporary data, serpentine movement, new area-coverage logic, new cleanup and return systems, and new messages.

Credit is retained for the original project concept and its role as the foundation and inspiration for this tool.

## License

World Chunk Pre-Generator is covered by the repository's root Mozilla Public License 2.0.
