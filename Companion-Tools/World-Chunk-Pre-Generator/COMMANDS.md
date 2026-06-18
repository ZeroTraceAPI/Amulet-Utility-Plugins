# World Chunk Pre-Generator Commands

World Chunk Pre-Generator provides reliable, fast, and batch commands for pre-generating and saving a centered square area around the player.

Run commands from the position you want to use as the center of the area.

## Choose a Speed

The selected speed is shared by Reliable, Fast, and Batch modes.

```mcfunction
/function speed_1
/function speed_2
/function speed_3
/function speed_4
/function speed_5
```

The available speed presets are:

* Speed 1: every 5 game ticks.
* Speed 2: every 4 game ticks.
* Speed 3: every 3 game ticks.
* Speed 4: every 2 game ticks. This is the default.
* Speed 5: every game tick. This is the maximum and should be tested on your device before large runs.

The selected speed remains active for later operations.

Use these commands to view or reset it:

```mcfunction
/function speed_status
/function speed_reset
```

`speed_reset` restores Speed 4.

## Reliable Mode

Reliable mode moves 4 blocks per cycle.

It provides the most movement overlap and is intended for devices or worlds that need more time to generate and save chunks.

Examples:

```mcfunction
/function load_250
/function load_500
/function load_1000
/function load_2500
```

Command format:

```mcfunction
/function load_SIZE
```

## Fast Mode

Fast mode moves 8 blocks per cycle.

It finishes more quickly than Reliable mode while staying close to the requested area size. Test it with a smaller size before using it on a large region.

Examples:

```mcfunction
/function fast_250
/function fast_500
/function fast_1000
/function fast_2500
```

Command format:

```mcfunction
/function fast_SIZE
```

## Batch Mode

Batch mode processes a 4 × 4 chunk area per cycle and moves 64 blocks at a time.

It is usually the fastest mode and is best suited to large pre-generation jobs. Because it works in 64-block groups, it rounds the requested size up to the next multiple of 64.

Examples:

```mcfunction
/function batch_250
/function batch_500
/function batch_1000
/function batch_2500
```

Command format:

```mcfunction
/function batch_SIZE
```

For example, `batch_1000` pre-generates a `1024 × 1024` block area.

## Available Sizes

The following sizes are available in Reliable, Fast, and Batch modes:

```text
250
500
750
1000
1250
1500
1750
2000
2250
2500
3000
4000
5000
6000
7000
8000
9000
10000
15000
```

## Region Size

The number in a command is the approximate width and length of the square area in blocks.

For example:

```mcfunction
/function load_250
```

pre-generates an area approximately `250 × 250` blocks in size, centered on the position where the command was started.

The number is not a radius. A `250 × 250` area extends approximately 125 blocks in each direction from the starting position: north, south, east, and west.

Reliable and Fast modes stay close to the requested size. Batch mode rounds upward to the next 64-block group. Minecraft may also generate and save surrounding chunks because it normally loads an area around the player.

## Stop an Active Run

```mcfunction
/function stop
```

This safely cancels the active pre-generation operation, returns the player when the saved return position is available, and removes temporary runtime data.

## Emergency Cleanup

```mcfunction
/function cleanup
```

Use this after a crash, forced shutdown, interrupted operation, or another problem that prevented normal cleanup.

It removes temporary World Chunk Pre-Generator data and attempts to return the active player when the saved return position is still available.

## Remove Data from Older Versions

```mcfunction
/function remove_legacy_data
```

This removes objectives, tags, markers, structures, and ticking-area names left by older World Generator and pre-rewrite World Chunk Loader versions.

Run it once when upgrading a world that used one of those older versions.

## During an Operation

While World Chunk Pre-Generator is running:

* Do not run another pre-generation command.
* Do not remove or disable the behavior pack.
* Avoid closing Minecraft until the operation and final cleanup has finished.
* Use `/function stop` when you need to cancel safely.

## After an Interrupted Operation

After reopening the world, run:

```mcfunction
/function cleanup
```

If the world previously used an older version, you should also run:

```mcfunction
/function remove_legacy_data
```
