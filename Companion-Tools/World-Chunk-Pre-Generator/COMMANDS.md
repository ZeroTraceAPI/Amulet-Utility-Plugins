# World Chunk Pre-Generator Commands

World Chunk Pre-Generator provides reliable and fast commands for pre-generating and saving a centered square area around the player.

Run commands from the position you want to use as the center of the area.

## Reliable Mode

Reliable mode moves 4 blocks per step.

This is the recommended mode for normal use and for devices or worlds that may need more time to generate and save chunks.

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

Fast mode moves 8 blocks per step.

It can finish more quickly, but Minecraft must still have enough time to generate and save each area. Test it with a smaller size before using it on a large region to make sure your device or world can handle it.

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

## Available Sizes

The following sizes are available in both reliable and fast modes:

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

pre-generates approximately `250 × 250` block area centered on the position where the command was started.

The number is not a radius. A `250 × 250` area extends approximately 125 blocks in each direction from the starting position: north, south, east, and west.

Minecraft may also generate and save some surrounding chunks because the game normally loads an area around the player.

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
* Avoid closing Minecraft until the operation finishes.
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
