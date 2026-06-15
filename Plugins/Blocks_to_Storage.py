import collections
import os
import re
import tempfile
import time
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, Set

import wx
from amulet_map_editor.programs.edit.api.behaviour import BlockSelectionBehaviour
from amulet_map_editor.programs.edit.api.operations import DefaultOperationUI

from amulet.api.block import Block
from amulet.api.block_entity import BlockEntity

try:
    from amulet_nbt import (
        NBTFile,
        TAG_Byte,
        TAG_Compound,
        TAG_Int,
        TAG_Float,
        TAG_List,
        TAG_Short,
        TAG_String,
        StringTag,
    )
except Exception:
    NBTFile = None
    TAG_Byte = None
    TAG_Compound = None
    TAG_Int = None
    TAG_Float = None
    TAG_List = None
    TAG_Short = None
    TAG_String = None
    StringTag = None

if TYPE_CHECKING:
    from amulet.api.level import BaseLevel
    from amulet_map_editor.programs.edit.api.canvas import EditCanvas

class PluginClassName(wx.Panel, DefaultOperationUI):

    SINGLE_CONTAINER_SLOT_COUNT = 27
    DOUBLE_CHEST_SLOT_COUNT = 54
    SHULKER_BOX_SLOT_COUNT = 27
    ITEM_STACK_LIMIT = 64
    DEFAULT_STACK_HEIGHT = 8
    MAX_STACK_HEIGHT = 40

    PROGRESS_INTERVAL = 500000
    LARGE_SELECTION_WARNING_THRESHOLD = 500000
    DEFAULT_GROUP_SPACING = 1
    MAX_GROUP_SPACING = 8
    SETTINGS_PANEL_MIN_HEIGHT = 360
    SETTINGS_PANEL_DEFAULT_HEIGHT = 440
    SETTINGS_PANEL_MAX_HEIGHT = 620

    FOUND_ENTRIES_FILENAME = "Found Entries.BTSP"
    DEFAULT_MINECRAFT_LANGUAGE_RELATIVE_PATH = Path(
        "XboxGames",
        "Minecraft for Windows",
        "Content",
        "data",
        "resource_packs",
        "vanilla",
        "texts",
        "en_US.lang",
    )

    CONTAINER_CHEST = "Chest"
    CONTAINER_BARREL = "Barrel"
    CONTAINER_SHULKER = "Shulker Box"

    NESTED_SHULKER_MODE_PRACTICAL = "Balanced - large groups only"
    NESTED_SHULKER_MODE_COMPACT = "Compact - all groups"

    SHULKER_COLORS = [
        "default",
        "white",
        "orange",
        "magenta",
        "light_blue",
        "yellow",
        "lime",
        "pink",
        "gray",
        "light_gray",
        "cyan",
        "purple",
        "blue",
        "brown",
        "green",
        "red",
        "black",
    ]

    VALUABLE_ITEM_FRAME_BLOCKS = {
        "minecraft:ancient_debris",
        "minecraft:diamond_ore",
        "minecraft:deepslate_diamond_ore",
        "minecraft:lapis_ore",
        "minecraft:deepslate_lapis_ore",
        "minecraft:emerald_ore",
        "minecraft:deepslate_emerald_ore",
        "minecraft:gold_ore",
        "minecraft:deepslate_gold_ore",
        "minecraft:raw_gold_block",
        "minecraft:raw_iron_block",
        "minecraft:raw_copper_block",
        "minecraft:amethyst_block",
        "minecraft:budding_amethyst",
        "minecraft:glow_frame",
    }

    AMBIGUOUS_FAST_SCAN_BLOCKS = {
        "minecraft:plant",
        "minecraft:double_plant",
        "minecraft:leaves",
        "minecraft:leaves2",
        "minecraft:log",
        "minecraft:log2",
        "minecraft:fence",
        "minecraft:planks",
        "minecraft:wood",
        "minecraft:stone_slab",
        "minecraft:stone_slab2",
        "minecraft:stone_slab3",
        "minecraft:stone_slab4",
        "minecraft:double_stone_slab",
        "minecraft:double_stone_slab2",
        "minecraft:double_stone_slab3",
        "minecraft:double_stone_slab4",
        "minecraft:infested_block",
        "minecraft:magma",
        "minecraft:magma_block",
        "minecraft:spawner",
        "minecraft:mob_spawner",
        "minecraft:cobweb",
        "minecraft:web",
        "minecraft:slab",
        "minecraft:double_slab",
        "minecraft:wooden_slab",
        "minecraft:double_wooden_slab",
        "minecraft:stairs",
        "minecraft:bed",
        "minecraft:item_frame_block",
        "minecraft:frame",
        "minecraft:glow_frame",
        "minecraft:sticky_piston_head",
        "minecraft:pitcher_crop",
        "minecraft:wall",
        "minecraft:door",
        "minecraft:glazed_terracotta",
        "minecraft:banner",
        "minecraft:standing_banner",
        "minecraft:wall_banner",
        "minecraft:sign",
        "minecraft:standing_sign",
        "minecraft:wall_sign",
        "minecraft:hanging_sign",
        "minecraft:wall_hanging_sign",
        "minecraft:oak_standing_sign",
        "minecraft:spruce_standing_sign",
        "minecraft:birch_standing_sign",
        "minecraft:jungle_standing_sign",
        "minecraft:acacia_standing_sign",
        "minecraft:dark_oak_standing_sign",
        "minecraft:mangrove_standing_sign",
        "minecraft:cherry_standing_sign",
        "minecraft:bamboo_standing_sign",
        "minecraft:crimson_standing_sign",
        "minecraft:warped_standing_sign",
        "minecraft:oak_hanging_sign",
        "minecraft:spruce_hanging_sign",
        "minecraft:birch_hanging_sign",
        "minecraft:jungle_hanging_sign",
        "minecraft:acacia_hanging_sign",
        "minecraft:dark_oak_hanging_sign",
        "minecraft:mangrove_hanging_sign",
        "minecraft:cherry_hanging_sign",
        "minecraft:bamboo_hanging_sign",
        "minecraft:crimson_hanging_sign",
        "minecraft:warped_hanging_sign",
        "minecraft:candle_cake",
        "minecraft:white_candle_cake",
        "minecraft:orange_candle_cake",
        "minecraft:magenta_candle_cake",
        "minecraft:light_blue_candle_cake",
        "minecraft:yellow_candle_cake",
        "minecraft:lime_candle_cake",
        "minecraft:pink_candle_cake",
        "minecraft:gray_candle_cake",
        "minecraft:light_gray_candle_cake",
        "minecraft:cyan_candle_cake",
        "minecraft:purple_candle_cake",
        "minecraft:blue_candle_cake",
        "minecraft:brown_candle_cake",
        "minecraft:green_candle_cake",
        "minecraft:red_candle_cake",
        "minecraft:black_candle_cake",
        "minecraft:candle",
        "minecraft:white_candle",
        "minecraft:orange_candle",
        "minecraft:magenta_candle",
        "minecraft:light_blue_candle",
        "minecraft:yellow_candle",
        "minecraft:lime_candle",
        "minecraft:pink_candle",
        "minecraft:gray_candle",
        "minecraft:light_gray_candle",
        "minecraft:cyan_candle",
        "minecraft:purple_candle",
        "minecraft:blue_candle",
        "minecraft:brown_candle",
        "minecraft:green_candle",
        "minecraft:red_candle",
        "minecraft:black_candle",
        "minecraft:bars",
        "minecraft:stonecutter_old",
        "minecraft:stonecutter_block",
        "minecraft:button",
        "minecraft:pressure_plate",
        "minecraft:trapdoor",
        "minecraft:fence_gate",
        "minecraft:head",
        "minecraft:wall_head",
    }

    SAFE_AMBIGUOUS_ITEM_FRAME_BLOCKS = {
        "minecraft:frame",
        "minecraft:glow_frame",
        "minecraft:web",
        "minecraft:cobweb",
        "minecraft:candle_cake",
        "minecraft:white_candle_cake",
        "minecraft:orange_candle_cake",
        "minecraft:magenta_candle_cake",
        "minecraft:light_blue_candle_cake",
        "minecraft:yellow_candle_cake",
        "minecraft:lime_candle_cake",
        "minecraft:pink_candle_cake",
        "minecraft:gray_candle_cake",
        "minecraft:light_gray_candle_cake",
        "minecraft:cyan_candle_cake",
        "minecraft:purple_candle_cake",
        "minecraft:blue_candle_cake",
        "minecraft:brown_candle_cake",
        "minecraft:green_candle_cake",
        "minecraft:red_candle_cake",
        "minecraft:black_candle_cake",
        "minecraft:candle",
        "minecraft:white_candle",
        "minecraft:orange_candle",
        "minecraft:magenta_candle",
        "minecraft:light_blue_candle",
        "minecraft:yellow_candle",
        "minecraft:lime_candle",
        "minecraft:pink_candle",
        "minecraft:gray_candle",
        "minecraft:light_gray_candle",
        "minecraft:cyan_candle",
        "minecraft:purple_candle",
        "minecraft:blue_candle",
        "minecraft:brown_candle",
        "minecraft:green_candle",
        "minecraft:red_candle",
        "minecraft:black_candle",
        "minecraft:oak_hanging_sign",
        "minecraft:spruce_hanging_sign",
        "minecraft:birch_hanging_sign",
        "minecraft:jungle_hanging_sign",
        "minecraft:acacia_hanging_sign",
        "minecraft:dark_oak_hanging_sign",
        "minecraft:mangrove_hanging_sign",
        "minecraft:cherry_hanging_sign",
        "minecraft:bamboo_hanging_sign",
        "minecraft:crimson_hanging_sign",
        "minecraft:warped_hanging_sign",
        "minecraft:stonecutter_block",
        "minecraft:fence_gate",
        "minecraft:trapdoor",
    }

    STATE_SENSITIVE_SCAN_BLOCKS = {
        "minecraft:bed",
        "minecraft:lilac",
        "minecraft:peony",
        "minecraft:rose_bush",
        "minecraft:sunflower",
        "minecraft:tall_grass",
        "minecraft:large_fern",
        "minecraft:tall_seagrass",
        "minecraft:seagrass",
        "minecraft:small_dripleaf",
        "minecraft:small_dripleaf_block",
        "minecraft:pitcher_plant",
        "minecraft:pitcher_crop",
        "minecraft:double_plant",
        "minecraft:wall",
        "minecraft:door",
        "minecraft:banner",
        "minecraft:standing_banner",
        "minecraft:wall_banner",
        "minecraft:sign",
        "minecraft:standing_sign",
        "minecraft:wall_sign",
        "minecraft:hanging_sign",
        "minecraft:wall_hanging_sign",
        "minecraft:oak_standing_sign",
        "minecraft:spruce_standing_sign",
        "minecraft:birch_standing_sign",
        "minecraft:jungle_standing_sign",
        "minecraft:acacia_standing_sign",
        "minecraft:dark_oak_standing_sign",
        "minecraft:mangrove_standing_sign",
        "minecraft:cherry_standing_sign",
        "minecraft:bamboo_standing_sign",
        "minecraft:crimson_standing_sign",
        "minecraft:warped_standing_sign",
        "minecraft:oak_hanging_sign",
        "minecraft:spruce_hanging_sign",
        "minecraft:birch_hanging_sign",
        "minecraft:jungle_hanging_sign",
        "minecraft:acacia_hanging_sign",
        "minecraft:dark_oak_hanging_sign",
        "minecraft:mangrove_hanging_sign",
        "minecraft:cherry_hanging_sign",
        "minecraft:bamboo_hanging_sign",
        "minecraft:crimson_hanging_sign",
        "minecraft:warped_hanging_sign",
        "minecraft:candle_cake",
        "minecraft:white_candle_cake",
        "minecraft:orange_candle_cake",
        "minecraft:magenta_candle_cake",
        "minecraft:light_blue_candle_cake",
        "minecraft:yellow_candle_cake",
        "minecraft:lime_candle_cake",
        "minecraft:pink_candle_cake",
        "minecraft:gray_candle_cake",
        "minecraft:light_gray_candle_cake",
        "minecraft:cyan_candle_cake",
        "minecraft:purple_candle_cake",
        "minecraft:blue_candle_cake",
        "minecraft:brown_candle_cake",
        "minecraft:green_candle_cake",
        "minecraft:red_candle_cake",
        "minecraft:black_candle_cake",
        "minecraft:candle",
        "minecraft:white_candle",
        "minecraft:orange_candle",
        "minecraft:magenta_candle",
        "minecraft:light_blue_candle",
        "minecraft:yellow_candle",
        "minecraft:lime_candle",
        "minecraft:pink_candle",
        "minecraft:gray_candle",
        "minecraft:light_gray_candle",
        "minecraft:cyan_candle",
        "minecraft:purple_candle",
        "minecraft:blue_candle",
        "minecraft:brown_candle",
        "minecraft:green_candle",
        "minecraft:red_candle",
        "minecraft:black_candle",
        "minecraft:bars",
        "minecraft:glazed_terracotta",
        "minecraft:wool",
        "minecraft:concrete",
        "minecraft:concrete_powder",
        "minecraft:stained_glass",
        "minecraft:stained_glass_pane",
        "minecraft:coral_block",
        "minecraft:button",
        "minecraft:pressure_plate",
        "minecraft:trapdoor",
        "minecraft:fence_gate",
        "minecraft:head",
        "minecraft:wall_head",
    }

    GENERIC_UNSAFE_ITEM_BLOCKS = {
        "minecraft:slab",
        "minecraft:double_slab",
        "minecraft:wooden_slab",
        "minecraft:double_wooden_slab",
        "minecraft:stairs",
        "minecraft:magma",
        "minecraft:plant",
        "minecraft:double_plant",
        "minecraft:leaves",
        "minecraft:leaves2",
        "minecraft:log",
        "minecraft:log2",
        "minecraft:fence",
        "minecraft:planks",
        "minecraft:wood",
        "minecraft:stone_slab",
        "minecraft:stone_slab2",
        "minecraft:stone_slab3",
        "minecraft:stone_slab4",
        "minecraft:double_stone_slab",
        "minecraft:double_stone_slab2",
        "minecraft:double_stone_slab3",
        "minecraft:double_stone_slab4",
        "minecraft:infested_block",
        "minecraft:stained_terracotta",
        "minecraft:wall",
        "minecraft:door",
        "minecraft:glazed_terracotta",
    }

    ITEM_NAME_OVERRIDES = {
        "minecraft:fire_fly_bush": "minecraft:firefly_bush",
        "minecraft:small_dripleaf": "minecraft:small_dripleaf_block",
        "minecraft:item_frame_block": "minecraft:frame",
        "minecraft:stonecutter": "minecraft:stonecutter_block",
        "minecraft:stonecutter_old": "minecraft:stonecutter_block",
        "minecraft:chain": "minecraft:iron_chain",
        "minecraft:oak_door": "minecraft:wooden_door",
        "minecraft:nether_bricks": "minecraft:nether_brick",
        "minecraft:red_nether_bricks": "minecraft:red_nether_brick",
        "minecraft:terracotta": "minecraft:hardened_clay",
        "minecraft:melon": "minecraft:melon_block",
        "minecraft:redstone_wire": "minecraft:redstone",
        "minecraft:cocoa": "minecraft:cocoa_beans",
        "minecraft:farmland": "minecraft:dirt",
        "minecraft:pumpkin_stem": "minecraft:pumpkin_seeds",
        "minecraft:attached_pumpkin_stem": "minecraft:pumpkin_seeds",
        "minecraft:melon_stem": "minecraft:melon_seeds",
        "minecraft:attached_melon_stem": "minecraft:melon_seeds",
        "minecraft:kelp_plant": "minecraft:kelp",
        "minecraft:tripwire": "minecraft:string",
        "minecraft:cave_vines": "minecraft:glow_berries",
        "minecraft:cave_vines_plant": "minecraft:glow_berries",
        "minecraft:weeping_vines_plant": "minecraft:weeping_vines",
        "minecraft:jack_o_lantern": "minecraft:lit_pumpkin",
        "minecraft:end_stone_bricks": "minecraft:end_bricks",
        "minecraft:powered_rail": "minecraft:golden_rail",
        "minecraft:rooted_dirt": "minecraft:dirt_with_roots",
        "minecraft:waxed_copper_block": "minecraft:waxed_copper",
        "minecraft:light_gray_glazed_terracotta": "minecraft:silver_glazed_terracotta",
        "minecraft:wall_sign": "minecraft:sign",
        "minecraft:carrots": "minecraft:carrot",
        "minecraft:potatoes": "minecraft:potato",
        "minecraft:beetroots": "minecraft:beetroot",
        "minecraft:oak_wall_sign": "minecraft:oak_sign",
        "minecraft:oak_wall_hanging_sign": "minecraft:oak_hanging_sign",
        "minecraft:spruce_wall_hanging_sign": "minecraft:spruce_hanging_sign",
        "minecraft:birch_wall_hanging_sign": "minecraft:birch_hanging_sign",
        "minecraft:jungle_wall_hanging_sign": "minecraft:jungle_hanging_sign",
        "minecraft:acacia_wall_hanging_sign": "minecraft:acacia_hanging_sign",
        "minecraft:dark_oak_wall_hanging_sign": "minecraft:dark_oak_hanging_sign",
        "minecraft:mangrove_wall_hanging_sign": "minecraft:mangrove_hanging_sign",
        "minecraft:cherry_wall_hanging_sign": "minecraft:cherry_hanging_sign",
        "minecraft:bamboo_wall_hanging_sign": "minecraft:bamboo_hanging_sign",
        "minecraft:crimson_wall_hanging_sign": "minecraft:crimson_hanging_sign",
        "minecraft:warped_wall_hanging_sign": "minecraft:warped_hanging_sign",
        "minecraft:spruce_wall_sign": "minecraft:spruce_sign",
        "minecraft:birch_wall_sign": "minecraft:birch_sign",
        "minecraft:jungle_wall_sign": "minecraft:jungle_sign",
        "minecraft:acacia_wall_sign": "minecraft:acacia_sign",
        "minecraft:dark_oak_wall_sign": "minecraft:dark_oak_sign",
        "minecraft:mangrove_wall_sign": "minecraft:mangrove_sign",
        "minecraft:cherry_wall_sign": "minecraft:cherry_sign",
        "minecraft:bamboo_wall_sign": "minecraft:bamboo_sign",
        "minecraft:crimson_wall_sign": "minecraft:crimson_sign",
        "minecraft:warped_wall_sign": "minecraft:warped_sign",
        "minecraft:standing_sign": "minecraft:sign",
        "minecraft:oak_standing_sign": "minecraft:oak_sign",
        "minecraft:spruce_standing_sign": "minecraft:spruce_sign",
        "minecraft:birch_standing_sign": "minecraft:birch_sign",
        "minecraft:jungle_standing_sign": "minecraft:jungle_sign",
        "minecraft:acacia_standing_sign": "minecraft:acacia_sign",
        "minecraft:dark_oak_standing_sign": "minecraft:dark_oak_sign",
        "minecraft:mangrove_standing_sign": "minecraft:mangrove_sign",
        "minecraft:cherry_standing_sign": "minecraft:cherry_sign",
        "minecraft:bamboo_standing_sign": "minecraft:bamboo_sign",
        "minecraft:crimson_standing_sign": "minecraft:crimson_sign",
        "minecraft:warped_standing_sign": "minecraft:warped_sign",
    }

    DOUBLE_SLAB_ITEM_OVERRIDES = {
        "minecraft:double_slab": "minecraft:slab",
        "minecraft:double_wooden_slab": "minecraft:wooden_slab",
        "minecraft:double_stone_slab": "minecraft:stone_slab",
        "minecraft:double_stone_slab2": "minecraft:stone_slab2",
        "minecraft:double_stone_slab3": "minecraft:stone_slab3",
        "minecraft:double_stone_slab4": "minecraft:stone_slab4",
    }

    CANDLE_CAKE_CANDLE_BY_BLOCK = {
        "minecraft:candle_cake": "minecraft:candle",
        "minecraft:white_candle_cake": "minecraft:white_candle",
        "minecraft:orange_candle_cake": "minecraft:orange_candle",
        "minecraft:magenta_candle_cake": "minecraft:magenta_candle",
        "minecraft:light_blue_candle_cake": "minecraft:light_blue_candle",
        "minecraft:yellow_candle_cake": "minecraft:yellow_candle",
        "minecraft:lime_candle_cake": "minecraft:lime_candle",
        "minecraft:pink_candle_cake": "minecraft:pink_candle",
        "minecraft:gray_candle_cake": "minecraft:gray_candle",
        "minecraft:light_gray_candle_cake": "minecraft:light_gray_candle",
        "minecraft:cyan_candle_cake": "minecraft:cyan_candle",
        "minecraft:purple_candle_cake": "minecraft:purple_candle",
        "minecraft:blue_candle_cake": "minecraft:blue_candle",
        "minecraft:brown_candle_cake": "minecraft:brown_candle",
        "minecraft:green_candle_cake": "minecraft:green_candle",
        "minecraft:red_candle_cake": "minecraft:red_candle",
        "minecraft:black_candle_cake": "minecraft:black_candle",
    }

    CANDLE_ITEM_BLOCKS = {
        "minecraft:candle",
        "minecraft:white_candle",
        "minecraft:orange_candle",
        "minecraft:magenta_candle",
        "minecraft:light_blue_candle",
        "minecraft:yellow_candle",
        "minecraft:lime_candle",
        "minecraft:pink_candle",
        "minecraft:gray_candle",
        "minecraft:light_gray_candle",
        "minecraft:cyan_candle",
        "minecraft:purple_candle",
        "minecraft:blue_candle",
        "minecraft:brown_candle",
        "minecraft:green_candle",
        "minecraft:red_candle",
        "minecraft:black_candle",
    }

    BED_COLOR_NAMES = [
        "white",
        "orange",
        "magenta",
        "light_blue",
        "yellow",
        "lime",
        "pink",
        "gray",
        "light_gray",
        "cyan",
        "purple",
        "blue",
        "brown",
        "green",
        "red",
        "black",
    ]

    BED_ITEM_DAMAGE_BY_COLOR = {
        color_name: color_index for color_index, color_name in enumerate(BED_COLOR_NAMES)
    }

    BED_COLOR_BY_ITEM_NAME = {
        f"minecraft:{color_name}_bed": color_name for color_name in BED_COLOR_NAMES
    }

    CARPET_COLOR_BY_ITEM_NAME = {
        f"minecraft:{color_name}_carpet": color_name for color_name in BED_COLOR_NAMES
    }

    WOOL_ITEM_BY_COLOR = {
        color_name: f"minecraft:{color_name}_wool" for color_name in BED_COLOR_NAMES
    }

    CONCRETE_ITEM_BY_COLOR = {
        color_name: f"minecraft:{color_name}_concrete" for color_name in BED_COLOR_NAMES
    }

    CONCRETE_POWDER_ITEM_BY_COLOR = {
        color_name: f"minecraft:{color_name}_concrete_powder" for color_name in BED_COLOR_NAMES
    }

    STAINED_GLASS_ITEM_BY_COLOR = {
        color_name: f"minecraft:{color_name}_stained_glass" for color_name in BED_COLOR_NAMES
    }

    STAINED_GLASS_PANE_ITEM_BY_COLOR = {
        color_name: f"minecraft:{color_name}_stained_glass_pane" for color_name in BED_COLOR_NAMES
    }

    CORAL_BLOCK_TYPES = {
        "tube",
        "brain",
        "bubble",
        "fire",
        "horn",
    }

    TERRACOTTA_ITEM_BY_COLOR = {
        color_name: f"minecraft:{color_name}_terracotta" for color_name in BED_COLOR_NAMES
    }

    GLAZED_TERRACOTTA_ITEM_BY_COLOR = {
        color_name: f"minecraft:{color_name}_glazed_terracotta" for color_name in BED_COLOR_NAMES
    }

    WALL_ITEM_BY_TYPE = {
        "cobblestone": "minecraft:cobblestone_wall",
        "mossy_cobblestone": "minecraft:mossy_cobblestone_wall",
        "granite": "minecraft:granite_wall",
        "diorite": "minecraft:diorite_wall",
        "andesite": "minecraft:andesite_wall",
        "sandstone": "minecraft:sandstone_wall",
        "brick": "minecraft:brick_wall",
        "stone_brick": "minecraft:stone_brick_wall",
        "mossy_stone_brick": "minecraft:mossy_stone_brick_wall",
        "nether_brick": "minecraft:nether_brick_wall",
        "end_brick": "minecraft:end_stone_brick_wall",
        "prismarine": "minecraft:prismarine_wall",
        "red_sandstone": "minecraft:red_sandstone_wall",
        "red_nether_brick": "minecraft:red_nether_brick_wall",
    }

    DOOR_ITEM_BY_TYPE = {
        "wood": "minecraft:oak_door",
        "oak": "minecraft:oak_door",
        "spruce": "minecraft:spruce_door",
        "birch": "minecraft:birch_door",
        "jungle": "minecraft:jungle_door",
        "acacia": "minecraft:acacia_door",
        "dark_oak": "minecraft:dark_oak_door",
        "mangrove": "minecraft:mangrove_door",
        "cherry": "minecraft:cherry_door",
        "bamboo": "minecraft:bamboo_door",
        "crimson": "minecraft:crimson_door",
        "warped": "minecraft:warped_door",
        "iron": "minecraft:iron_door",
    }

    SIGN_ITEM_BY_TYPE = {
        "wood": "minecraft:oak_sign",
        "oak": "minecraft:oak_sign",
        "spruce": "minecraft:spruce_sign",
        "birch": "minecraft:birch_sign",
        "jungle": "minecraft:jungle_sign",
        "acacia": "minecraft:acacia_sign",
        "dark_oak": "minecraft:dark_oak_sign",
        "mangrove": "minecraft:mangrove_sign",
        "cherry": "minecraft:cherry_sign",
        "bamboo": "minecraft:bamboo_sign",
        "crimson": "minecraft:crimson_sign",
        "warped": "minecraft:warped_sign",
        "pale_oak": "minecraft:pale_oak_sign",
    }

    HANGING_SIGN_ITEM_BY_TYPE = {
        "wood": "minecraft:oak_hanging_sign",
        "oak": "minecraft:oak_hanging_sign",
        "spruce": "minecraft:spruce_hanging_sign",
        "birch": "minecraft:birch_hanging_sign",
        "jungle": "minecraft:jungle_hanging_sign",
        "acacia": "minecraft:acacia_hanging_sign",
        "dark_oak": "minecraft:dark_oak_hanging_sign",
        "mangrove": "minecraft:mangrove_hanging_sign",
        "cherry": "minecraft:cherry_hanging_sign",
        "bamboo": "minecraft:bamboo_hanging_sign",
        "crimson": "minecraft:crimson_hanging_sign",
        "warped": "minecraft:warped_hanging_sign",
        "pale_oak": "minecraft:pale_oak_hanging_sign",
    }

    BARS_ITEM_BY_TYPE = {
        "iron": "minecraft:iron_bars",
        "copper": "minecraft:copper_bars",
        "exposed_copper": "minecraft:exposed_copper_bars",
        "weathered_copper": "minecraft:weathered_copper_bars",
        "oxidized_copper": "minecraft:oxidized_copper_bars",
        "waxed_copper": "minecraft:waxed_copper_bars",
        "waxed_exposed_copper": "minecraft:waxed_exposed_copper_bars",
        "waxed_weathered_copper": "minecraft:waxed_weathered_copper_bars",
        "waxed_oxidized_copper": "minecraft:waxed_oxidized_copper_bars",
    }

    COLOR_NAME_ALIASES = {
        "silver": "light_gray",
        "lightgrey": "light_gray",
        "light_grey": "light_gray",
        "grey": "gray",
    }

    BANNER_ITEM_PREFIX = "minecraft:banner_damage_"

    BANNER_COLOR_NAMES_BY_DAMAGE = [
        "black",
        "red",
        "green",
        "brown",
        "blue",
        "purple",
        "cyan",
        "light_gray",
        "gray",
        "pink",
        "lime",
        "yellow",
        "light_blue",
        "magenta",
        "orange",
        "white",
    ]

    BANNER_COLOR_NAME_BY_DAMAGE = {
        color_index: color_name for color_index, color_name in enumerate(BANNER_COLOR_NAMES_BY_DAMAGE)
    }

    BEDROCK_EN_US_DISPLAY_NAMES = {'acacia_button': ('tile.acacia_button.name', 'Acacia Button'),
 'acacia_door': ('item.acacia_door.name', 'Acacia Door'),
 'acacia_fence': ('tile.acaciaFence.name', 'Acacia Fence'),
 'acacia_fence_gate': ('tile.acacia_fence_gate.name', 'Acacia Fence Gate'),
 'acacia_hanging_sign': ('item.acacia_hanging_sign.name', 'Acacia Hanging Sign'),
 'acacia_pressure_plate': ('tile.acacia_pressure_plate.name', 'Acacia Pressure Plate'),
 'acacia_shelf': ('tile.acacia_shelf.name', 'Acacia Shelf'),
 'acacia_sign': ('item.acacia_sign.name', 'Acacia Sign'),
 'acacia_stairs': ('tile.acacia_stairs.name', 'Acacia Stairs'),
 'acacia_standing_sign': ('tile.acacia_standing_sign.name', 'Acacia Sign'),
 'acacia_trapdoor': ('tile.acacia_trapdoor.name', 'Acacia Trapdoor'),
 'acacia_wall_sign': ('tile.acacia_wall_sign.name', 'Acacia Wall Sign'),
 'activator_rail': ('tile.activator_rail.name', 'Activator Rail'),
 'air': ('item.air.name', 'Air'),
 'allow': ('tile.allow.name', 'Allow'),
 'amethyst_block': ('tile.amethyst_block.name', 'Block of Amethyst'),
 'amethyst_cluster': ('tile.amethyst_cluster.name', 'Amethyst Cluster'),
 'amethyst_shard': ('item.amethyst_shard.name', 'Amethyst Shard'),
 'ancient_debris': ('tile.ancient_debris.name', 'Ancient Debris'),
 'andesite_stairs': ('tile.andesite_stairs.name', 'Andesite Stairs'),
 'angler_pottery_sherd': ('item.angler_pottery_sherd.name', 'Angler Pottery Sherd'),
 'anvil': ('tile.anvil.name', 'Anvil'),
 'anvil_intact': ('tile.anvil.intact.name', 'Anvil'),
 'anvil_slightly_damaged': ('tile.anvil.slightlyDamaged.name', 'Chipped Anvil'),
 'anvil_very_damaged': ('tile.anvil.veryDamaged.name', 'Damaged Anvil'),
 'apple': ('item.apple.name', 'Apple'),
 'apple_enchanted': ('item.appleEnchanted.name', 'Enchanted Golden Apple'),
 'archer_pottery_sherd': ('item.archer_pottery_sherd.name', 'Archer Pottery Sherd'),
 'armadillo_scute': ('item.armadillo_scute.name', 'Armadillo Scute'),
 'armor_stand': ('item.armor_stand.name', 'Armor Stand'),
 'arms_up_pottery_sherd': ('item.arms_up_pottery_sherd.name', 'Arms Up Pottery Sherd'),
 'arrow': ('item.arrow.name', 'Arrow'),
 'axolotl_adult_body_single': ('item.axolotlAdultBodySingle.name', 'Adult %1$s Axolotl'),
 'axolotl_baby_body_single': ('item.axolotlBabyBodySingle.name', 'Baby %1$s Axolotl'),
 'axolotl_color_blue': ('item.axolotlColorBlue.name', 'Blue'),
 'axolotl_color_cyan': ('item.axolotlColorCyan.name', 'Cyan'),
 'axolotl_color_gold': ('item.axolotlColorGold.name', 'Gold'),
 'axolotl_color_lucy': ('item.axolotlColorLucy.name', 'Leucistic'),
 'axolotl_color_wild': ('item.axolotlColorWild.name', 'Brown'),
 'azalea': ('tile.azalea.name', 'Azalea'),
 'azalea_leaves': ('tile.azalea_leaves.name', 'Azalea Leaves'),
 'azalea_leaves_flowered': ('tile.azalea_leaves_flowered.name', 'Flowering Azalea Leaves'),
 'baked_potato': ('item.baked_potato.name', 'Baked Potato'),
 'bamboo': ('tile.bamboo.name', 'Bamboo'),
 'bamboo_block': ('tile.bamboo_block.name', 'Block of Bamboo'),
 'bamboo_button': ('tile.bamboo_button.name', 'Bamboo Button'),
 'bamboo_door': ('item.bamboo_door.name', 'Bamboo Door'),
 'bamboo_double_slab': ('tile.bamboo_double_slab.name', 'Bamboo Double Slab'),
 'bamboo_fence': ('tile.bamboo_fence.name', 'Bamboo Fence'),
 'bamboo_fence_gate': ('tile.bamboo_fence_gate.name', 'Bamboo Fence Gate'),
 'bamboo_hanging_sign': ('item.bamboo_hanging_sign.name', 'Bamboo Hanging Sign'),
 'bamboo_mosaic': ('tile.bamboo_mosaic.name', 'Bamboo Mosaic'),
 'bamboo_mosaic_double_slab': ('tile.bamboo_mosaic_double_slab.name', 'Bamboo Mosaic Double Slab'),
 'bamboo_mosaic_slab': ('tile.bamboo_mosaic_slab.name', 'Bamboo Mosaic Slab'),
 'bamboo_mosaic_stairs': ('tile.bamboo_mosaic_stairs.name', 'Bamboo Mosaic Stairs'),
 'bamboo_planks': ('tile.bamboo_planks.name', 'Bamboo Planks'),
 'bamboo_pressure_plate': ('tile.bamboo_pressure_plate.name', 'Bamboo Pressure Plate'),
 'bamboo_sapling': ('tile.bamboo_sapling.name', 'Bamboo Sapling'),
 'bamboo_shelf': ('tile.bamboo_shelf.name', 'Bamboo Shelf'),
 'bamboo_sign': ('item.bamboo_sign.name', 'Bamboo Sign'),
 'bamboo_slab': ('tile.bamboo_slab.name', 'Bamboo Slab'),
 'bamboo_stairs': ('tile.bamboo_stairs.name', 'Bamboo Stairs'),
 'bamboo_standing_sign': ('tile.bamboo_standing_sign.name', 'Bamboo Sign'),
 'bamboo_trapdoor': ('tile.bamboo_trapdoor.name', 'Bamboo Trapdoor'),
 'bamboo_wall_sign': ('tile.bamboo_wall_sign.name', 'Bamboo Wall Sign'),
 'banner_black': ('item.banner.black.name', 'Black Banner'),
 'banner_blue': ('item.banner.blue.name', 'Blue Banner'),
 'banner_brown': ('item.banner.brown.name', 'Brown Banner'),
 'banner_cyan': ('item.banner.cyan.name', 'Cyan Banner'),
 'banner_gray': ('item.banner.gray.name', 'Gray Banner'),
 'banner_green': ('item.banner.green.name', 'Green Banner'),
 'banner_illager_captain': ('item.banner.illager_captain.name', 'Ominous Banner'),
 'banner_light_blue': ('item.banner.lightBlue.name', 'Light Blue Banner'),
 'banner_lime': ('item.banner.lime.name', 'Lime Banner'),
 'banner_magenta': ('item.banner.magenta.name', 'Magenta Banner'),
 'banner_orange': ('item.banner.orange.name', 'Orange Banner'),
 'banner_pattern': ('item.banner_pattern.name', 'Banner Pattern'),
 'banner_pink': ('item.banner.pink.name', 'Pink Banner'),
 'banner_purple': ('item.banner.purple.name', 'Purple Banner'),
 'banner_red': ('item.banner.red.name', 'Red Banner'),
 'banner_silver': ('item.banner.silver.name', 'Light Gray Banner'),
 'banner_white': ('item.banner.white.name', 'White Banner'),
 'banner_yellow': ('item.banner.yellow.name', 'Yellow Banner'),
 'barrel': ('tile.barrel.name', 'Barrel'),
 'barrier': ('tile.barrier.name', 'Barrier'),
 'basalt': ('tile.basalt.name', 'Basalt'),
 'beacon': ('tile.beacon.name', 'Beacon'),
 'bed': ('tile.bed.name', 'Bed'),
 'bed_black': ('item.bed.black.name', 'Black Bed'),
 'bed_blue': ('item.bed.blue.name', 'Blue Bed'),
 'bed_brown': ('item.bed.brown.name', 'Brown Bed'),
 'bed_cyan': ('item.bed.cyan.name', 'Cyan Bed'),
 'bed_gray': ('item.bed.gray.name', 'Gray Bed'),
 'bed_green': ('item.bed.green.name', 'Green Bed'),
 'bed_light_blue': ('item.bed.lightBlue.name', 'Light Blue Bed'),
 'bed_lime': ('item.bed.lime.name', 'Lime Bed'),
 'bed_magenta': ('item.bed.magenta.name', 'Magenta Bed'),
 'bed_orange': ('item.bed.orange.name', 'Orange Bed'),
 'bed_pink': ('item.bed.pink.name', 'Pink Bed'),
 'bed_purple': ('item.bed.purple.name', 'Purple Bed'),
 'bed_red': ('item.bed.red.name', 'Red Bed'),
 'bed_silver': ('item.bed.silver.name', 'Light Gray Bed'),
 'bed_white': ('item.bed.white.name', 'White Bed'),
 'bed_yellow': ('item.bed.yellow.name', 'Yellow Bed'),
 'bedrock': ('tile.bedrock.name', 'Bedrock'),
 'bee_nest': ('tile.bee_nest.name', 'Bee Nest'),
 'beef': ('item.beef.name', 'Raw Beef'),
 'beehive': ('tile.beehive.name', 'Beehive'),
 'beetroot': ('item.beetroot.name', 'Beetroot'),
 'beetroot_seeds': ('item.beetroot_seeds.name', 'Beetroot Seeds'),
 'beetroot_soup': ('item.beetroot_soup.name', 'Beetroot Soup'),
 'bell': ('item.bell.name', 'Bell'),
 'big_dripleaf': ('tile.big_dripleaf.name', 'Big Dripleaf'),
 'birch_button': ('tile.birch_button.name', 'Birch Button'),
 'birch_door': ('item.birch_door.name', 'Birch Door'),
 'birch_fence': ('tile.birchFence.name', 'Birch Fence'),
 'birch_fence_gate': ('tile.birch_fence_gate.name', 'Birch Fence Gate'),
 'birch_hanging_sign': ('item.birch_hanging_sign.name', 'Birch Hanging Sign'),
 'birch_pressure_plate': ('tile.birch_pressure_plate.name', 'Birch Pressure Plate'),
 'birch_shelf': ('tile.birch_shelf.name', 'Birch Shelf'),
 'birch_sign': ('item.birch_sign.name', 'Birch Sign'),
 'birch_stairs': ('tile.birch_stairs.name', 'Birch Stairs'),
 'birch_standing_sign': ('tile.birch_standing_sign.name', 'Birch Sign'),
 'birch_trapdoor': ('tile.birch_trapdoor.name', 'Birch Trapdoor'),
 'birch_wall_sign': ('tile.birch_wall_sign.name', 'Birch Wall Sign'),
 'black_candle': ('tile.black_candle.name', 'Black Candle'),
 'black_candle_cake': ('tile.black_candle_cake.name', 'Cake with Black Candle'),
 'black_harness': ('item.black_harness.name', 'Black Harness'),
 'blackstone': ('tile.blackstone.name', 'Blackstone'),
 'blackstone_double_slab': ('tile.blackstone_double_slab.name', 'Blackstone Double Slab'),
 'blackstone_slab': ('tile.blackstone_slab.name', 'Blackstone Slab'),
 'blackstone_stairs': ('tile.blackstone_stairs.name', 'Blackstone Stairs'),
 'blackstone_wall': ('tile.blackstone_wall.name', 'Blackstone Wall'),
 'blade_pottery_sherd': ('item.blade_pottery_sherd.name', 'Blade Pottery Sherd'),
 'blast_furnace': ('tile.blast_furnace.name', 'Blast Furnace'),
 'blaze_powder': ('item.blaze_powder.name', 'Blaze Powder'),
 'blaze_rod': ('item.blaze_rod.name', 'Blaze Rod'),
 'blue_candle': ('tile.blue_candle.name', 'Blue Candle'),
 'blue_candle_cake': ('tile.blue_candle_cake.name', 'Cake with Blue Candle'),
 'blue_egg': ('item.blue_egg.name', 'Blue Egg'),
 'blue_harness': ('item.blue_harness.name', 'Blue Harness'),
 'blue_ice': ('tile.blue_ice.name', 'Blue Ice'),
 'boat_acacia': ('item.boat.acacia.name', 'Acacia Boat'),
 'boat_bamboo': ('item.boat.bamboo.name', 'Bamboo Raft'),
 'boat_big_oak': ('item.boat.big_oak.name', 'Dark Oak Boat'),
 'boat_birch': ('item.boat.birch.name', 'Birch Boat'),
 'boat_cherry': ('item.boat.cherry.name', 'Cherry Boat'),
 'boat_jungle': ('item.boat.jungle.name', 'Jungle Boat'),
 'boat_mangrove': ('item.boat.mangrove.name', 'Mangrove Boat'),
 'boat_oak': ('item.boat.oak.name', 'Oak Boat'),
 'boat_pale_oak': ('item.boat.pale_oak.name', 'Pale Oak Boat'),
 'boat_spruce': ('item.boat.spruce.name', 'Spruce Boat'),
 'bolt_armor_trim_smithing_template': ('item.bolt_armor_trim_smithing_template.name', 'Bolt Armor Trim'),
 'bone': ('item.bone.name', 'Bone'),
 'bone_block': ('tile.bone_block.name', 'Bone Block'),
 'book': ('item.book.name', 'Book'),
 'bookshelf': ('tile.bookshelf.name', 'Bookshelf'),
 'border_block': ('tile.border_block.name', 'Border'),
 'bordure_indented_banner_pattern': ('item.bordure_indented_banner_pattern.name', 'Bordure Indented Banner Pattern'),
 'bow': ('item.bow.name', 'Bow'),
 'bowl': ('item.bowl.name', 'Bowl'),
 'brain_coral_wall_fan': ('tile.brain_coral_wall_fan.name', 'Brain Coral Wall Fan'),
 'bread': ('item.bread.name', 'Bread'),
 'breeze_rod': ('item.breeze_rod.name', 'Breeze Rod'),
 'brewer_pottery_sherd': ('item.brewer_pottery_sherd.name', 'Brewer Pottery Sherd'),
 'brewing_stand': ('item.brewing_stand.name', 'Brewing Stand'),
 'brick': ('item.brick.name', 'Brick'),
 'brick_block': ('tile.brick_block.name', 'Bricks'),
 'brick_stairs': ('tile.brick_stairs.name', 'Brick Stairs'),
 'brown_candle': ('tile.brown_candle.name', 'Brown Candle'),
 'brown_candle_cake': ('tile.brown_candle_cake.name', 'Cake with Brown Candle'),
 'brown_egg': ('item.brown_egg.name', 'Brown Egg'),
 'brown_harness': ('item.brown_harness.name', 'Brown Harness'),
 'brown_mushroom': ('tile.brown_mushroom.name', 'Brown Mushroom'),
 'brown_mushroom_block_cap': ('tile.brown_mushroom_block.cap.name', 'Brown Mushroom Block'),
 'brown_mushroom_block_mushroom': ('tile.brown_mushroom_block.mushroom.name', 'Mushroom'),
 'brown_mushroom_block_stem': ('tile.brown_mushroom_block.stem.name', 'Mushroom Stem'),
 'brush': ('item.brush.name', 'Brush'),
 'bubble_column': ('tile.bubble_column.name', 'Bubble Column'),
 'bubble_coral_wall_fan': ('tile.bubble_coral_wall_fan.name', 'Bubble Coral Wall Fan'),
 'bucket': ('item.bucket.name', 'Bucket'),
 'bucket_axolotl': ('item.bucketAxolotl.name', 'Bucket of Axolotl'),
 'bucket_custom_fish': ('item.bucketCustomFish.name', 'Bucket of'),
 'bucket_fish': ('item.bucketFish.name', 'Bucket of Cod'),
 'bucket_lava': ('item.bucketLava.name', 'Lava Bucket'),
 'bucket_powder_snow': ('item.bucketPowderSnow.name', 'Powder Snow Bucket'),
 'bucket_puffer': ('item.bucketPuffer.name', 'Bucket of Pufferfish'),
 'bucket_salmon': ('item.bucketSalmon.name', 'Bucket of Salmon'),
 'bucket_tadpole': ('item.bucketTadpole.name', 'Bucket of Tadpole'),
 'bucket_tropical': ('item.bucketTropical.name', 'Bucket of Tropical Fish'),
 'bucket_water': ('item.bucketWater.name', 'Water Bucket'),
 'budding_amethyst': ('tile.budding_amethyst.name', 'Budding Amethyst'),
 'burn_pottery_sherd': ('item.burn_pottery_sherd.name', 'Burn Pottery Sherd'),
 'bush': ('tile.bush.name', 'Bush'),
 'cactus': ('tile.cactus.name', 'Cactus'),
 'cactus_flower': ('tile.cactus_flower.name', 'Cactus Flower'),
 'cake': ('item.cake.name', 'Cake'),
 'calcite': ('tile.calcite.name', 'Calcite'),
 'calibrated_sculk_sensor': ('tile.calibrated_sculk_sensor.name', 'Calibrated Sculk Sensor'),
 'camera': ('item.camera.name', 'Camera'),
 'campfire': ('tile.campfire.name', 'Campfire'),
 'candle': ('tile.candle.name', 'Candle'),
 'candle_cake': ('tile.candle_cake.name', 'Cake with Candle'),
 'carpet': ('tile.carpet.name', 'Carpet'),
 'carpet_black': ('tile.carpet.black.name', 'Black Carpet'),
 'carpet_blue': ('tile.carpet.blue.name', 'Blue Carpet'),
 'carpet_brown': ('tile.carpet.brown.name', 'Brown Carpet'),
 'carpet_cyan': ('tile.carpet.cyan.name', 'Cyan Carpet'),
 'carpet_gray': ('tile.carpet.gray.name', 'Gray Carpet'),
 'carpet_green': ('tile.carpet.green.name', 'Green Carpet'),
 'carpet_light_blue': ('tile.carpet.lightBlue.name', 'Light Blue Carpet'),
 'carpet_lime': ('tile.carpet.lime.name', 'Lime Carpet'),
 'carpet_magenta': ('tile.carpet.magenta.name', 'Magenta Carpet'),
 'carpet_orange': ('tile.carpet.orange.name', 'Orange Carpet'),
 'carpet_pink': ('tile.carpet.pink.name', 'Pink Carpet'),
 'carpet_purple': ('tile.carpet.purple.name', 'Purple Carpet'),
 'carpet_red': ('tile.carpet.red.name', 'Red Carpet'),
 'carpet_silver': ('tile.carpet.silver.name', 'Light Gray Carpet'),
 'carpet_white': ('tile.carpet.white.name', 'White Carpet'),
 'carpet_yellow': ('tile.carpet.yellow.name', 'Yellow Carpet'),
 'carrot': ('item.carrot.name', 'Carrot'),
 'carrot_on_astick': ('item.carrotOnAStick.name', 'Carrot on a Stick'),
 'carrots': ('tile.carrots.name', 'Carrots'),
 'cartography_table': ('tile.cartography_table.name', 'Cartography Table'),
 'carved_pumpkin': ('tile.carved_pumpkin.name', 'Carved Pumpkin'),
 'cauldron': ('item.cauldron.name', 'Cauldron'),
 'cave_vines': ('tile.cave_vines.name', 'Cave Vines'),
 'cave_vines_body_with_berries': ('tile.cave_vines_body_with_berries.name', 'Cave Vines'),
 'cave_vines_head_with_berries': ('tile.cave_vines_head_with_berries.name', 'Cave Vines'),
 'chain': ('tile.chain.name', 'Chain'),
 'chain_command_block': ('tile.chain_command_block.name', 'Chain Command Block'),
 'chainmail_boots': ('item.chainmail_boots.name', 'Chainmail Boots'),
 'chainmail_chestplate': ('item.chainmail_chestplate.name', 'Chainmail Chestplate'),
 'chainmail_helmet': ('item.chainmail_helmet.name', 'Chainmail Helmet'),
 'chainmail_leggings': ('item.chainmail_leggings.name', 'Chainmail Leggings'),
 'chalkboard': ('tile.chalkboard.name', 'Chalkboard'),
 'chalkboard_one_by_one': ('tile.chalkboard.oneByOne.name', 'Slate'),
 'chalkboard_three_by_two': ('tile.chalkboard.threeByTwo.name', 'Board'),
 'chalkboard_two_by_one': ('tile.chalkboard.twoByOne.name', 'Poster'),
 'charcoal': ('item.charcoal.name', 'Charcoal'),
 'cherry_button': ('tile.cherry_button.name', 'Cherry Button'),
 'cherry_door': ('item.cherry_door.name', 'Cherry Door'),
 'cherry_double_slab': ('tile.cherry_double_slab.name', 'Cherry Double Slab'),
 'cherry_fence': ('tile.cherry_fence.name', 'Cherry Fence'),
 'cherry_fence_gate': ('tile.cherry_fence_gate.name', 'Cherry Fence Gate'),
 'cherry_hanging_sign': ('item.cherry_hanging_sign.name', 'Cherry Hanging Sign'),
 'cherry_leaves': ('tile.cherry_leaves.name', 'Cherry Leaves'),
 'cherry_log': ('tile.cherry_log.name', 'Cherry Log'),
 'cherry_planks': ('tile.cherry_planks.name', 'Cherry Planks'),
 'cherry_pressure_plate': ('tile.cherry_pressure_plate.name', 'Cherry Pressure Plate'),
 'cherry_sapling': ('tile.cherry_sapling.name', 'Cherry Sapling'),
 'cherry_shelf': ('tile.cherry_shelf.name', 'Cherry Shelf'),
 'cherry_sign': ('item.cherry_sign.name', 'Cherry Sign'),
 'cherry_slab': ('tile.cherry_slab.name', 'Cherry Slab'),
 'cherry_stairs': ('tile.cherry_stairs.name', 'Cherry Stairs'),
 'cherry_standing_sign': ('tile.cherry_standing_sign.name', 'Cherry Sign'),
 'cherry_trapdoor': ('tile.cherry_trapdoor.name', 'Cherry Trapdoor'),
 'cherry_wall_sign': ('tile.cherry_wall_sign.name', 'Cherry Wall Sign'),
 'cherry_wood': ('tile.cherry_wood.name', 'Cherry Wood'),
 'chest': ('tile.chest.name', 'Chest'),
 'chest_boat_acacia': ('item.chest_boat.acacia.name', 'Acacia Boat with Chest'),
 'chest_boat_bamboo': ('item.chest_boat.bamboo.name', 'Bamboo Raft with Chest'),
 'chest_boat_big_oak': ('item.chest_boat.big_oak.name', 'Dark Oak Boat with Chest'),
 'chest_boat_birch': ('item.chest_boat.birch.name', 'Birch Boat with Chest'),
 'chest_boat_cherry': ('item.chest_boat.cherry.name', 'Cherry Boat with Chest'),
 'chest_boat_jungle': ('item.chest_boat.jungle.name', 'Jungle Boat with Chest'),
 'chest_boat_mangrove': ('item.chest_boat.mangrove.name', 'Mangrove Boat with Chest'),
 'chest_boat_oak': ('item.chest_boat.oak.name', 'Oak Boat with Chest'),
 'chest_boat_pale_oak': ('item.chest_boat.pale_oak.name', 'Pale Oak Boat with Chest'),
 'chest_boat_spruce': ('item.chest_boat.spruce.name', 'Spruce Boat with Chest'),
 'chest_minecart': ('item.chest_minecart.name', 'Minecart with Chest'),
 'chicken': ('item.chicken.name', 'Raw Chicken'),
 'chiseled_bookshelf': ('tile.chiseled_bookshelf.name', 'Chiseled Bookshelf'),
 'chiseled_copper': ('tile.chiseled_copper.name', 'Chiseled Copper'),
 'chiseled_deepslate': ('tile.chiseled_deepslate.name', 'Chiseled Deepslate'),
 'chiseled_nether_bricks': ('tile.chiseled_nether_bricks.name', 'Chiseled Nether Bricks'),
 'chiseled_polished_blackstone': ('tile.chiseled_polished_blackstone.name', 'Chiseled Polished Blackstone'),
 'chiseled_resin_bricks': ('tile.chiseled_resin_bricks.name', 'Chiseled Resin Bricks'),
 'chiseled_tuff': ('tile.chiseled_tuff.name', 'Chiseled Tuff'),
 'chiseled_tuff_bricks': ('tile.chiseled_tuff_bricks.name', 'Chiseled Tuff Bricks'),
 'chorus_flower': ('tile.chorus_flower.name', 'Chorus Flower'),
 'chorus_fruit': ('item.chorus_fruit.name', 'Chorus Fruit'),
 'chorus_fruit_popped': ('item.chorus_fruit_popped.name', 'Popped Chorus Fruit'),
 'chorus_plant': ('tile.chorus_plant.name', 'Chorus Plant'),
 'clay': ('tile.clay.name', 'Clay'),
 'clay_ball': ('item.clay_ball.name', 'Clay Ball'),
 'clock': ('item.clock.name', 'Clock'),
 'closed_eyeblossom': ('tile.closed_eyeblossom.name', 'Closed Eyeblossom'),
 'clownfish': ('item.clownfish.name', 'Tropical Fish'),
 'coal': ('item.coal.name', 'Coal'),
 'coal_block': ('tile.coal_block.name', 'Block of Coal'),
 'coal_ore': ('tile.coal_ore.name', 'Coal Ore'),
 'coast_armor_trim_smithing_template': ('item.coast_armor_trim_smithing_template.name', 'Coast Armor Trim'),
 'cobbled_deepslate': ('tile.cobbled_deepslate.name', 'Cobbled Deepslate'),
 'cobbled_deepslate_double_slab': ('tile.cobbled_deepslate_double_slab.name', 'Cobbled Deepslate Double Slab'),
 'cobbled_deepslate_slab': ('tile.cobbled_deepslate_slab.name', 'Cobbled Deepslate Slab'),
 'cobbled_deepslate_stairs': ('tile.cobbled_deepslate_stairs.name', 'Cobbled Deepslate Stairs'),
 'cobbled_deepslate_wall': ('tile.cobbled_deepslate_wall.name', 'Cobbled Deepslate Wall'),
 'cobblestone': ('tile.cobblestone.name', 'Cobblestone'),
 'cobblestone_wall_andesite': ('tile.cobblestone_wall.andesite.name', 'Andesite Wall'),
 'cobblestone_wall_brick': ('tile.cobblestone_wall.brick.name', 'Brick Wall'),
 'cobblestone_wall_diorite': ('tile.cobblestone_wall.diorite.name', 'Diorite Wall'),
 'cobblestone_wall_end_brick': ('tile.cobblestone_wall.end_brick.name', 'End Stone Brick Wall'),
 'cobblestone_wall_granite': ('tile.cobblestone_wall.granite.name', 'Granite Wall'),
 'cobblestone_wall_mossy': ('tile.cobblestone_wall.mossy.name', 'Mossy Cobblestone Wall'),
 'cobblestone_wall_mossy_stone_brick': ('tile.cobblestone_wall.mossy_stone_brick.name', 'Mossy Stone Brick Wall'),
 'cobblestone_wall_nether_brick': ('tile.cobblestone_wall.nether_brick.name', 'Nether Brick Wall'),
 'cobblestone_wall_normal': ('tile.cobblestone_wall.normal.name', 'Cobblestone Wall'),
 'cobblestone_wall_prismarine': ('tile.cobblestone_wall.prismarine.name', 'Prismarine Wall'),
 'cobblestone_wall_red_nether_brick': ('tile.cobblestone_wall.red_nether_brick.name', 'Red Nether Brick Wall'),
 'cobblestone_wall_red_sandstone': ('tile.cobblestone_wall.red_sandstone.name', 'Red Sandstone Wall'),
 'cobblestone_wall_sandstone': ('tile.cobblestone_wall.sandstone.name', 'Sandstone Wall'),
 'cobblestone_wall_stone_brick': ('tile.cobblestone_wall.stone_brick.name', 'Stone Brick Wall'),
 'cocoa': ('tile.cocoa.name', 'Cocoa'),
 'command_block': ('tile.command_block.name', 'Command Block'),
 'command_block_minecart': ('item.command_block_minecart.name', 'Minecart with Command Block'),
 'comparator': ('item.comparator.name', 'Redstone Comparator'),
 'compass': ('item.compass.name', 'Compass'),
 'composter': ('tile.composter.name', 'Composter'),
 'concrete_black': ('tile.concrete.black.name', 'Black Concrete'),
 'concrete_blue': ('tile.concrete.blue.name', 'Blue Concrete'),
 'concrete_brown': ('tile.concrete.brown.name', 'Brown Concrete'),
 'concrete_cyan': ('tile.concrete.cyan.name', 'Cyan Concrete'),
 'concrete_gray': ('tile.concrete.gray.name', 'Gray Concrete'),
 'concrete_green': ('tile.concrete.green.name', 'Green Concrete'),
 'concrete_light_blue': ('tile.concrete.lightBlue.name', 'Light Blue Concrete'),
 'concrete_lime': ('tile.concrete.lime.name', 'Lime Concrete'),
 'concrete_magenta': ('tile.concrete.magenta.name', 'Magenta Concrete'),
 'concrete_orange': ('tile.concrete.orange.name', 'Orange Concrete'),
 'concrete_pink': ('tile.concrete.pink.name', 'Pink Concrete'),
 'concrete_powder_black': ('tile.concretePowder.black.name', 'Black Concrete Powder'),
 'concrete_powder_blue': ('tile.concretePowder.blue.name', 'Blue Concrete Powder'),
 'concrete_powder_brown': ('tile.concretePowder.brown.name', 'Brown Concrete Powder'),
 'concrete_powder_cyan': ('tile.concretePowder.cyan.name', 'Cyan Concrete Powder'),
 'concrete_powder_gray': ('tile.concretePowder.gray.name', 'Gray Concrete Powder'),
 'concrete_powder_green': ('tile.concretePowder.green.name', 'Green Concrete Powder'),
 'concrete_powder_light_blue': ('tile.concretePowder.lightBlue.name', 'Light Blue Concrete Powder'),
 'concrete_powder_lime': ('tile.concretePowder.lime.name', 'Lime Concrete Powder'),
 'concrete_powder_magenta': ('tile.concretePowder.magenta.name', 'Magenta Concrete Powder'),
 'concrete_powder_orange': ('tile.concretePowder.orange.name', 'Orange Concrete Powder'),
 'concrete_powder_pink': ('tile.concretePowder.pink.name', 'Pink Concrete Powder'),
 'concrete_powder_purple': ('tile.concretePowder.purple.name', 'Purple Concrete Powder'),
 'concrete_powder_red': ('tile.concretePowder.red.name', 'Red Concrete Powder'),
 'concrete_powder_silver': ('tile.concretePowder.silver.name', 'Light Gray Concrete Powder'),
 'concrete_powder_white': ('tile.concretePowder.white.name', 'White Concrete Powder'),
 'concrete_powder_yellow': ('tile.concretePowder.yellow.name', 'Yellow Concrete Powder'),
 'concrete_purple': ('tile.concrete.purple.name', 'Purple Concrete'),
 'concrete_red': ('tile.concrete.red.name', 'Red Concrete'),
 'concrete_silver': ('tile.concrete.silver.name', 'Light Gray Concrete'),
 'concrete_white': ('tile.concrete.white.name', 'White Concrete'),
 'concrete_yellow': ('tile.concrete.yellow.name', 'Yellow Concrete'),
 'conduit': ('tile.conduit.name', 'Conduit'),
 'cooked_beef': ('item.cooked_beef.name', 'Steak'),
 'cooked_chicken': ('item.cooked_chicken.name', 'Cooked Chicken'),
 'cooked_fish': ('item.cooked_fish.name', 'Cooked Cod'),
 'cooked_porkchop': ('item.cooked_porkchop.name', 'Cooked Porkchop'),
 'cooked_rabbit': ('item.cooked_rabbit.name', 'Cooked Rabbit'),
 'cooked_salmon': ('item.cooked_salmon.name', 'Cooked Salmon'),
 'cookie': ('item.cookie.name', 'Cookie'),
 'copper_axe': ('item.copper_axe.name', 'Copper Axe'),
 'copper_bars': ('tile.copper_bars.name', 'Copper Bars'),
 'copper_block': ('tile.copper_block.name', 'Block of Copper'),
 'copper_boots': ('item.copper_boots.name', 'Copper Boots'),
 'copper_bulb': ('tile.copper_bulb.name', 'Copper Bulb'),
 'copper_chain': ('tile.copper_chain.name', 'Copper Chain'),
 'copper_chest': ('tile.copper_chest.name', 'Copper Chest'),
 'copper_chestplate': ('item.copper_chestplate.name', 'Copper Chestplate'),
 'copper_door': ('item.copper_door.name', 'Copper Door'),
 'copper_golem_statue': ('tile.copper_golem_statue.name', 'Copper Golem Statue'),
 'copper_grate': ('tile.copper_grate.name', 'Copper Grate'),
 'copper_helmet': ('item.copper_helmet.name', 'Copper Helmet'),
 'copper_hoe': ('item.copper_hoe.name', 'Copper Hoe'),
 'copper_horse_armor': ('item.copper_horse_armor.name', 'Copper Horse Armor'),
 'copper_ingot': ('item.copper_ingot.name', 'Copper Ingot'),
 'copper_lantern': ('tile.copper_lantern.name', 'Copper Lantern'),
 'copper_leggings': ('item.copper_leggings.name', 'Copper Leggings'),
 'copper_nautilus_armor': ('item.copper_nautilus_armor.name', 'Copper Nautilus Armor'),
 'copper_nugget': ('item.copper_nugget.name', 'Copper Nugget'),
 'copper_ore': ('tile.copper_ore.name', 'Copper Ore'),
 'copper_pickaxe': ('item.copper_pickaxe.name', 'Copper Pickaxe'),
 'copper_shovel': ('item.copper_shovel.name', 'Copper Shovel'),
 'copper_spear': ('item.copper_spear.name', 'Copper Spear'),
 'copper_sword': ('item.copper_sword.name', 'Copper Sword'),
 'copper_torch': ('tile.copper_torch.name', 'Copper Torch'),
 'copper_trapdoor': ('tile.copper_trapdoor.name', 'Copper Trapdoor'),
 'coral_block_blue': ('tile.coral_block.blue.name', 'Tube Coral Block'),
 'coral_block_blue_dead': ('tile.coral_block.blue_dead.name', 'Dead Tube Coral Block'),
 'coral_block_pink': ('tile.coral_block.pink.name', 'Brain Coral Block'),
 'coral_block_pink_dead': ('tile.coral_block.pink_dead.name', 'Dead Brain Coral Block'),
 'coral_block_purple': ('tile.coral_block.purple.name', 'Bubble Coral Block'),
 'coral_block_purple_dead': ('tile.coral_block.purple_dead.name', 'Dead Bubble Coral Block'),
 'coral_block_red': ('tile.coral_block.red.name', 'Fire Coral Block'),
 'coral_block_red_dead': ('tile.coral_block.red_dead.name', 'Dead Fire Coral Block'),
 'coral_block_yellow': ('tile.coral_block.yellow.name', 'Horn Coral Block'),
 'coral_block_yellow_dead': ('tile.coral_block.yellow_dead.name', 'Dead Horn Coral Block'),
 'coral_blue': ('tile.coral.blue.name', 'Tube Coral'),
 'coral_blue_dead': ('tile.coral.blue_dead.name', 'Dead Tube Coral'),
 'coral_fan_blue_fan': ('tile.coral_fan.blue_fan.name', 'Tube Coral Fan'),
 'coral_fan_dead_blue_fan': ('tile.coral_fan_dead.blue_fan.name', 'Dead Tube Coral Fan'),
 'coral_fan_dead_pink_fan': ('tile.coral_fan_dead.pink_fan.name', 'Dead Brain Coral Fan'),
 'coral_fan_dead_purple_fan': ('tile.coral_fan_dead.purple_fan.name', 'Dead Bubble Coral Fan'),
 'coral_fan_dead_red_fan': ('tile.coral_fan_dead.red_fan.name', 'Dead Fire Coral Fan'),
 'coral_fan_dead_yellow_fan': ('tile.coral_fan_dead.yellow_fan.name', 'Dead Horn Coral Fan'),
 'coral_fan_pink_fan': ('tile.coral_fan.pink_fan.name', 'Brain Coral Fan'),
 'coral_fan_purple_fan': ('tile.coral_fan.purple_fan.name', 'Bubble Coral Fan'),
 'coral_fan_red_fan': ('tile.coral_fan.red_fan.name', 'Fire Coral Fan'),
 'coral_fan_yellow_fan': ('tile.coral_fan.yellow_fan.name', 'Horn Coral Fan'),
 'coral_pink': ('tile.coral.pink.name', 'Brain Coral'),
 'coral_pink_dead': ('tile.coral.pink_dead.name', 'Dead Brain Coral'),
 'coral_purple': ('tile.coral.purple.name', 'Bubble Coral'),
 'coral_purple_dead': ('tile.coral.purple_dead.name', 'Dead Bubble Coral'),
 'coral_red': ('tile.coral.red.name', 'Fire Coral'),
 'coral_red_dead': ('tile.coral.red_dead.name', 'Dead Fire Coral'),
 'coral_yellow': ('tile.coral.yellow.name', 'Horn Coral'),
 'coral_yellow_dead': ('tile.coral.yellow_dead.name', 'Dead Horn Coral'),
 'cracked_deepslate_bricks': ('tile.cracked_deepslate_bricks.name', 'Cracked Deepslate Bricks'),
 'cracked_deepslate_tiles': ('tile.cracked_deepslate_tiles.name', 'Cracked Deepslate Tiles'),
 'cracked_nether_bricks': ('tile.cracked_nether_bricks.name', 'Cracked Nether Bricks'),
 'cracked_polished_blackstone_bricks': ('tile.cracked_polished_blackstone_bricks.name',
                                        'Cracked Polished Blackstone Bricks'),
 'crafter': ('tile.crafter.name', 'Crafter'),
 'crafting_table': ('tile.crafting_table.name', 'Crafting Table'),
 'creaking_heart': ('tile.creaking_heart.name', 'Creaking Heart'),
 'creeper_banner_pattern': ('item.creeper_banner_pattern.name', 'Creeper Charge Banner Pattern'),
 'crimson_button': ('tile.crimson_button.name', 'Crimson Button'),
 'crimson_door': ('item.crimson_door.name', 'Crimson Door'),
 'crimson_double_slab': ('tile.crimson_double_slab.name', 'Crimson Slab'),
 'crimson_fence': ('tile.crimson_fence.name', 'Crimson Fence'),
 'crimson_fence_gate': ('tile.crimson_fence_gate.name', 'Crimson Fence Gate'),
 'crimson_fungus': ('tile.crimson_fungus.name', 'Crimson Fungus'),
 'crimson_hanging_sign': ('item.crimson_hanging_sign.name', 'Crimson Hanging Sign'),
 'crimson_hyphae': ('tile.crimson_hyphae.name', 'Crimson Hyphae'),
 'crimson_nylium': ('tile.crimson_nylium.name', 'Crimson Nylium'),
 'crimson_planks': ('tile.crimson_planks.name', 'Crimson Planks'),
 'crimson_pressure_plate': ('tile.crimson_pressure_plate.name', 'Crimson Pressure Plate'),
 'crimson_roots_crimson_roots': ('tile.crimson_roots.crimsonRoots.name', 'Crimson Roots'),
 'crimson_shelf': ('tile.crimson_shelf.name', 'Crimson Shelf'),
 'crimson_sign': ('item.crimson_sign.name', 'Crimson Sign'),
 'crimson_slab': ('tile.crimson_slab.name', 'Crimson Slab'),
 'crimson_stairs': ('tile.crimson_stairs.name', 'Crimson Stairs'),
 'crimson_standing_sign': ('tile.crimson_standing_sign.name', 'Crimson Sign'),
 'crimson_stem': ('tile.crimson_stem.name', 'Crimson Stem'),
 'crimson_trapdoor': ('tile.crimson_trapdoor.name', 'Crimson Trapdoor'),
 'crimson_wall_sign': ('tile.crimson_wall_sign.name', 'Crimson Sign'),
 'crossbow': ('item.crossbow.name', 'Crossbow'),
 'crying_obsidian': ('tile.crying_obsidian.name', 'Crying Obsidian'),
 'cut_copper': ('tile.cut_copper.name', 'Cut Copper'),
 'cut_copper_slab': ('tile.cut_copper_slab.name', 'Cut Copper Slab'),
 'cut_copper_stairs': ('tile.cut_copper_stairs.name', 'Cut Copper Stairs'),
 'cyan_candle': ('tile.cyan_candle.name', 'Cyan Candle'),
 'cyan_candle_cake': ('tile.cyan_candle_cake.name', 'Cake with Cyan Candle'),
 'cyan_harness': ('item.cyan_harness.name', 'Cyan Harness'),
 'danger_pottery_sherd': ('item.danger_pottery_sherd.name', 'Danger Pottery Sherd'),
 'dark_oak_button': ('tile.dark_oak_button.name', 'Dark Oak Button'),
 'dark_oak_door': ('item.dark_oak_door.name', 'Dark Oak Door'),
 'dark_oak_fence': ('tile.darkOakFence.name', 'Dark Oak Fence'),
 'dark_oak_fence_gate': ('tile.dark_oak_fence_gate.name', 'Dark Oak Fence Gate'),
 'dark_oak_hanging_sign': ('item.dark_oak_hanging_sign.name', 'Dark Oak Hanging Sign'),
 'dark_oak_pressure_plate': ('tile.dark_oak_pressure_plate.name', 'Dark Oak Pressure Plate'),
 'dark_oak_shelf': ('tile.dark_oak_shelf.name', 'Dark Oak Shelf'),
 'dark_oak_stairs': ('tile.dark_oak_stairs.name', 'Dark Oak Stairs'),
 'dark_oak_trapdoor': ('tile.dark_oak_trapdoor.name', 'Dark Oak Trapdoor'),
 'dark_prismarine_stairs': ('tile.dark_prismarine_stairs.name', 'Dark Prismarine Stairs'),
 'darkoak_sign': ('item.darkoak_sign.name', 'Dark Oak Sign'),
 'darkoak_standing_sign': ('tile.darkoak_standing_sign.name', 'Dark Oak Sign'),
 'darkoak_wall_sign': ('tile.darkoak_wall_sign.name', 'Dark Oak Wall Sign'),
 'daylight_detector': ('tile.daylight_detector.name', 'Daylight Detector'),
 'daylight_detector_inverted': ('tile.daylight_detector_inverted.name', 'Daylight Detector Inverted'),
 'dead_brain_coral_wall_fan': ('tile.dead_brain_coral_wall_fan.name', 'Dead Brain Coral Wall Fan'),
 'dead_bubble_coral_wall_fan': ('tile.dead_bubble_coral_wall_fan.name', 'Dead Bubble Coral Wall Fan'),
 'dead_fire_coral_wall_fan': ('tile.dead_fire_coral_wall_fan.name', 'Dead Fire Coral Wall Fan'),
 'dead_horn_coral_wall_fan': ('tile.dead_horn_coral_wall_fan.name', 'Dead Horn Coral Wall Fan'),
 'dead_tube_coral_wall_fan': ('tile.dead_tube_coral_wall_fan.name', 'Dead Tube Coral Wall Fan'),
 'deadbush': ('tile.deadbush.name', 'Dead Bush'),
 'decorated_pot': ('tile.decorated_pot.name', 'Decorated Pot'),
 'deepslate': ('tile.deepslate.name', 'Deepslate'),
 'deepslate_brick_double_slab': ('tile.deepslate_brick_double_slab.name', 'Deepslate Brick Double Slab'),
 'deepslate_brick_slab': ('tile.deepslate_brick_slab.name', 'Deepslate Brick Slab'),
 'deepslate_brick_stairs': ('tile.deepslate_brick_stairs.name', 'Deepslate Brick Stairs'),
 'deepslate_brick_wall': ('tile.deepslate_brick_wall.name', 'Deepslate Brick Wall'),
 'deepslate_bricks': ('tile.deepslate_bricks.name', 'Deepslate Bricks'),
 'deepslate_coal_ore': ('tile.deepslate_coal_ore.name', 'Deepslate Coal Ore'),
 'deepslate_copper_ore': ('tile.deepslate_copper_ore.name', 'Deepslate Copper Ore'),
 'deepslate_diamond_ore': ('tile.deepslate_diamond_ore.name', 'Deepslate Diamond Ore'),
 'deepslate_emerald_ore': ('tile.deepslate_emerald_ore.name', 'Deepslate Emerald Ore'),
 'deepslate_gold_ore': ('tile.deepslate_gold_ore.name', 'Deepslate Gold Ore'),
 'deepslate_iron_ore': ('tile.deepslate_iron_ore.name', 'Deepslate Iron Ore'),
 'deepslate_lapis_ore': ('tile.deepslate_lapis_ore.name', 'Deepslate Lapis Lazuli Ore'),
 'deepslate_redstone_ore': ('tile.deepslate_redstone_ore.name', 'Deepslate Redstone Ore'),
 'deepslate_tile_double_slab': ('tile.deepslate_tile_double_slab.name', 'Deepslate Tile Double Slab'),
 'deepslate_tile_slab': ('tile.deepslate_tile_slab.name', 'Deepslate Tile Slab'),
 'deepslate_tile_stairs': ('tile.deepslate_tile_stairs.name', 'Deepslate Tile Stairs'),
 'deepslate_tile_wall': ('tile.deepslate_tile_wall.name', 'Deepslate Tile Wall'),
 'deepslate_tiles': ('tile.deepslate_tiles.name', 'Deepslate Tiles'),
 'deny': ('tile.deny.name', 'Deny'),
 'detector_rail': ('tile.detector_rail.name', 'Detector Rail'),
 'diamond': ('item.diamond.name', 'Diamond'),
 'diamond_axe': ('item.diamond_axe.name', 'Diamond Axe'),
 'diamond_block': ('tile.diamond_block.name', 'Block of Diamond'),
 'diamond_boots': ('item.diamond_boots.name', 'Diamond Boots'),
 'diamond_chestplate': ('item.diamond_chestplate.name', 'Diamond Chestplate'),
 'diamond_helmet': ('item.diamond_helmet.name', 'Diamond Helmet'),
 'diamond_hoe': ('item.diamond_hoe.name', 'Diamond Hoe'),
 'diamond_leggings': ('item.diamond_leggings.name', 'Diamond Leggings'),
 'diamond_nautilus_armor': ('item.diamond_nautilus_armor.name', 'Diamond Nautilus Armor'),
 'diamond_ore': ('tile.diamond_ore.name', 'Diamond Ore'),
 'diamond_pickaxe': ('item.diamond_pickaxe.name', 'Diamond Pickaxe'),
 'diamond_shovel': ('item.diamond_shovel.name', 'Diamond Shovel'),
 'diamond_spear': ('item.diamond_spear.name', 'Diamond Spear'),
 'diamond_sword': ('item.diamond_sword.name', 'Diamond Sword'),
 'diorite_stairs': ('tile.diorite_stairs.name', 'Diorite Stairs'),
 'dirt': ('tile.dirt.name', 'Dirt'),
 'dirt_coarse': ('tile.dirt.coarse.name', 'Coarse Dirt'),
 'dirt_default': ('tile.dirt.default.name', 'Dirt'),
 'dirt_with_roots': ('tile.dirt_with_roots.name', 'Rooted Dirt'),
 'disc_fragment': ('item.disc_fragment.name', 'Disc Fragment'),
 'dispenser': ('tile.dispenser.name', 'Dispenser'),
 'door_wood': ('tile.doorWood.name', 'Wooden Door'),
 'double_cut_copper_slab': ('tile.double_cut_copper_slab.name', 'Cut Copper Double Slab'),
 'double_plant': ('tile.double_plant.name', 'Plant'),
 'double_plant_fern': ('tile.double_plant.fern.name', 'Large Fern'),
 'double_plant_grass': ('tile.double_plant.grass.name', 'Tall Grass'),
 'double_plant_paeonia': ('tile.double_plant.paeonia.name', 'Peony'),
 'double_plant_rose': ('tile.double_plant.rose.name', 'Rose Bush'),
 'double_plant_sunflower': ('tile.double_plant.sunflower.name', 'Sunflower'),
 'double_plant_syringa': ('tile.double_plant.syringa.name', 'Lilac'),
 'double_stone_slab': ('tile.double_stone_slab.name', 'Stone Slab'),
 'double_stone_slab2_mossy_cobblestone': ('tile.double_stone_slab2.mossy_cobblestone.name',
                                          'Mossy Cobblestone Double Slab'),
 'double_stone_slab2_prismarine_bricks': ('tile.double_stone_slab2.prismarine.bricks.name',
                                          'Prismarine Brick Double Slab'),
 'double_stone_slab2_prismarine_dark': ('tile.double_stone_slab2.prismarine.dark.name',
                                        'Dark Prismarine Double Slab'),
 'double_stone_slab2_prismarine_rough': ('tile.double_stone_slab2.prismarine.rough.name', 'Prismarine DoubleSlab'),
 'double_stone_slab2_purpur': ('tile.double_stone_slab2.purpur.name', 'Purpur Double Slab'),
 'double_stone_slab2_red_nether_brick': ('tile.double_stone_slab2.red_nether_brick.name',
                                         'Red Nether Brick Double Slab'),
 'double_stone_slab2_red_sandstone': ('tile.double_stone_slab2.red_sandstone.name', 'Red Sandstone Slab'),
 'double_stone_slab2_sandstone_smooth': ('tile.double_stone_slab2.sandstone.smooth.name',
                                         'Smooth Sandstone Double Slab'),
 'double_stone_slab3_andesite': ('tile.double_stone_slab3.andesite.name', 'Andesite Double Slab'),
 'double_stone_slab3_andesite_smooth': ('tile.double_stone_slab3.andesite.smooth.name',
                                        'Polished Andesite Double Slab'),
 'double_stone_slab3_diorite': ('tile.double_stone_slab3.diorite.name', 'Diorite Double Slab'),
 'double_stone_slab3_diorite_smooth': ('tile.double_stone_slab3.diorite.smooth.name', 'Polished Diorite Double Slab'),
 'double_stone_slab3_end_brick': ('tile.double_stone_slab3.end_brick.name', 'End Stone Brick Double Slab'),
 'double_stone_slab3_granite': ('tile.double_stone_slab3.granite.name', 'Granite Double Slab'),
 'double_stone_slab3_granite_smooth': ('tile.double_stone_slab3.granite.smooth.name', 'Polished Granite Double Slab'),
 'double_stone_slab3_red_sandstone_smooth': ('tile.double_stone_slab3.red_sandstone.smooth.name',
                                             'Smooth Red Sandstone Double Slab'),
 'double_stone_slab4_cut_red_sandstone': ('tile.double_stone_slab4.cut_red_sandstone.name',
                                          'Cut Red Sandstone Double Slab'),
 'double_stone_slab4_cut_sandstone': ('tile.double_stone_slab4.cut_sandstone.name', 'Cut Sandstone Double Slab'),
 'double_stone_slab4_mossy_stone_brick': ('tile.double_stone_slab4.mossy_stone_brick.name',
                                          'Mossy Stone Brick Double Slab'),
 'double_stone_slab4_smooth_quartz': ('tile.double_stone_slab4.smooth_quartz.name', 'Smooth Quartz Double Slab'),
 'double_stone_slab4_stone': ('tile.double_stone_slab4.stone.name', 'Stone Double Slab'),
 'double_stone_slab_brick': ('tile.double_stone_slab.brick.name', 'Brick Slab'),
 'double_stone_slab_cobble': ('tile.double_stone_slab.cobble.name', 'Cobblestone Slab'),
 'double_stone_slab_nether_brick': ('tile.double_stone_slab.nether_brick.name', 'Nether Brick Slab'),
 'double_stone_slab_quartz': ('tile.double_stone_slab.quartz.name', 'Quartz Slab'),
 'double_stone_slab_sand': ('tile.double_stone_slab.sand.name', 'Sandstone Slab'),
 'double_stone_slab_smooth_stone_brick': ('tile.double_stone_slab.smoothStoneBrick.name', 'Stone Brick Slab'),
 'double_stone_slab_stone': ('tile.double_stone_slab.stone.name', 'Stone Slab'),
 'double_stone_slab_wood': ('tile.double_stone_slab.wood.name', 'Wooden Slab'),
 'double_wooden_slab_acacia': ('tile.double_wooden_slab.acacia.name', 'Acacia Double Slab'),
 'double_wooden_slab_big_oak': ('tile.double_wooden_slab.big_oak.name', 'Dark Oak Double Slab'),
 'double_wooden_slab_birch': ('tile.double_wooden_slab.birch.name', 'Birch Double Slab'),
 'double_wooden_slab_jungle': ('tile.double_wooden_slab.jungle.name', 'Jungle Double Slab'),
 'double_wooden_slab_oak': ('tile.double_wooden_slab.oak.name', 'Oak Double Slab'),
 'double_wooden_slab_spruce': ('tile.double_wooden_slab.spruce.name', 'Spruce Double Slab'),
 'dragon_breath': ('item.dragon_breath.name', "Dragon's Breath"),
 'dragon_egg': ('tile.dragon_egg.name', 'Dragon Egg'),
 'dried_ghast': ('tile.dried_ghast.name', 'Dried Ghast'),
 'dried_kelp': ('item.dried_kelp.name', 'Dried Kelp'),
 'dried_kelp_block': ('tile.dried_kelp_block.name', 'Dried Kelp Block'),
 'dripstone_block': ('tile.dripstone_block.name', 'Dripstone Block'),
 'dropper': ('tile.dropper.name', 'Dropper'),
 'dune_armor_trim_smithing_template': ('item.dune_armor_trim_smithing_template.name', 'Dune Armor Trim'),
 'dye_black': ('item.dye.black.name', 'Ink Sac'),
 'dye_black_new': ('item.dye.black_new.name', 'Black Dye'),
 'dye_blue': ('item.dye.blue.name', 'Lapis Lazuli'),
 'dye_blue_new': ('item.dye.blue_new.name', 'Blue Dye'),
 'dye_brown': ('item.dye.brown.name', 'Cocoa Beans'),
 'dye_brown_new': ('item.dye.brown_new.name', 'Brown Dye'),
 'dye_cyan': ('item.dye.cyan.name', 'Cyan Dye'),
 'dye_gray': ('item.dye.gray.name', 'Gray Dye'),
 'dye_green': ('item.dye.green.name', 'Green Dye'),
 'dye_light_blue': ('item.dye.lightBlue.name', 'Light Blue Dye'),
 'dye_lime': ('item.dye.lime.name', 'Lime Dye'),
 'dye_magenta': ('item.dye.magenta.name', 'Magenta Dye'),
 'dye_orange': ('item.dye.orange.name', 'Orange Dye'),
 'dye_pink': ('item.dye.pink.name', 'Pink Dye'),
 'dye_purple': ('item.dye.purple.name', 'Purple Dye'),
 'dye_red': ('item.dye.red.name', 'Red Dye'),
 'dye_silver': ('item.dye.silver.name', 'Light Gray Dye'),
 'dye_white': ('item.dye.white.name', 'Bone Meal'),
 'dye_white_new': ('item.dye.white_new.name', 'White Dye'),
 'dye_yellow': ('item.dye.yellow.name', 'Yellow Dye'),
 'echo_shard': ('item.echo_shard.name', 'Echo Shard'),
 'egg': ('item.egg.name', 'Egg'),
 'elytra': ('item.elytra.name', 'Elytra'),
 'emerald': ('item.emerald.name', 'Emerald'),
 'emerald_block': ('tile.emerald_block.name', 'Block of Emerald'),
 'emerald_ore': ('tile.emerald_ore.name', 'Emerald Ore'),
 'empty_locator_map': ('item.emptyLocatorMap.name', 'Empty Locator Map'),
 'empty_map': ('item.emptyMap.name', 'Empty Map'),
 'enchanted_book': ('item.enchanted_book.name', 'Enchanted Book'),
 'enchanting_table': ('tile.enchanting_table.name', 'Enchanting Table'),
 'end_brick_stairs': ('tile.end_brick_stairs.name', 'End Stone Brick Stairs'),
 'end_bricks': ('tile.end_bricks.name', 'End Stone Bricks'),
 'end_crystal': ('item.end_crystal.name', 'End Crystal'),
 'end_gateway': ('tile.end_gateway.name', 'End Gateway'),
 'end_portal': ('tile.end_portal.name', 'End Portal'),
 'end_portal_frame': ('tile.end_portal_frame.name', 'End Portal Frame'),
 'end_rod': ('tile.end_rod.name', 'End Rod'),
 'end_stone': ('tile.end_stone.name', 'End Stone'),
 'ender_chest': ('tile.enderChest.name', 'Ender Chest'),
 'ender_eye': ('item.ender_eye.name', 'Eye of Ender'),
 'ender_pearl': ('item.ender_pearl.name', 'Ender Pearl'),
 'experience_bottle': ('item.experience_bottle.name', "Bottle o' Enchanting"),
 'explorer_pottery_sherd': ('item.explorer_pottery_sherd.name', 'Explorer Pottery Sherd'),
 'exposed_chiseled_copper': ('tile.exposed_chiseled_copper.name', 'Exposed Chiseled Copper'),
 'exposed_copper': ('tile.exposed_copper.name', 'Exposed Copper'),
 'exposed_copper_bars': ('tile.exposed_copper_bars.name', 'Exposed Copper Bars'),
 'exposed_copper_bulb': ('tile.exposed_copper_bulb.name', 'Exposed Copper Bulb'),
 'exposed_copper_chain': ('tile.exposed_copper_chain.name', 'Exposed Copper Chain'),
 'exposed_copper_chest': ('tile.exposed_copper_chest.name', 'Exposed Copper Chest'),
 'exposed_copper_door': ('item.exposed_copper_door.name', 'Exposed Copper Door'),
 'exposed_copper_golem_statue': ('tile.exposed_copper_golem_statue.name', 'Exposed Copper Golem Statue'),
 'exposed_copper_grate': ('tile.exposed_copper_grate.name', 'Exposed Copper Grate'),
 'exposed_copper_lantern': ('tile.exposed_copper_lantern.name', 'Exposed Copper Lantern'),
 'exposed_copper_trapdoor': ('tile.exposed_copper_trapdoor.name', 'Exposed Copper Trapdoor'),
 'exposed_cut_copper': ('tile.exposed_cut_copper.name', 'Exposed Cut Copper'),
 'exposed_cut_copper_slab': ('tile.exposed_cut_copper_slab.name', 'Exposed Cut Copper Slab'),
 'exposed_cut_copper_stairs': ('tile.exposed_cut_copper_stairs.name', 'Exposed Cut Copper Stairs'),
 'exposed_double_cut_copper_slab': ('tile.exposed_double_cut_copper_slab.name', 'Exposed Cut Copper Double Slab'),
 'exposed_lightning_rod': ('tile.exposed_lightning_rod.name', 'Exposed Lightning Rod'),
 'eye_armor_trim_smithing_template': ('item.eye_armor_trim_smithing_template.name', 'Eye Armor Trim'),
 'farmland': ('tile.farmland.name', 'Farmland'),
 'feather': ('item.feather.name', 'Feather'),
 'fence': ('tile.fence.name', 'Oak Fence'),
 'fence_gate': ('tile.fence_gate.name', 'Oak Fence Gate'),
 'fermented_spider_eye': ('item.fermented_spider_eye.name', 'Fermented Spider Eye'),
 'field_masoned_banner_pattern': ('item.field_masoned_banner_pattern.name', 'Field Masoned Banner Pattern'),
 'fire': ('tile.fire.name', 'Fire'),
 'fire_coral_wall_fan': ('tile.fire_coral_wall_fan.name', 'Fire Coral Wall Fan'),
 'fireball': ('item.fireball.name', 'Fire Charge'),
 'firefly_bush': ('tile.firefly_bush.name', 'Firefly Bush'),
 'fireworks': ('item.fireworks.name', 'Firework Rocket'),
 'fireworks_charge': ('item.fireworksCharge.name', 'Firework Star'),
 'fish': ('item.fish.name', 'Raw Cod'),
 'fishing_rod': ('item.fishing_rod.name', 'Fishing Rod'),
 'fletching_table': ('tile.fletching_table.name', 'Fletching Table'),
 'flint': ('item.flint.name', 'Flint'),
 'flint_and_steel': ('item.flint_and_steel.name', 'Flint and Steel'),
 'flow_armor_trim_smithing_template': ('item.flow_armor_trim_smithing_template.name', 'Flow Armor Trim'),
 'flow_banner_pattern': ('item.flow_banner_pattern.name', 'Flow Banner Pattern'),
 'flow_pottery_sherd': ('item.flow_pottery_sherd.name', 'Flow Pottery Sherd'),
 'flower_banner_pattern': ('item.flower_banner_pattern.name', 'Flower Charge Banner Pattern'),
 'flower_pot': ('item.flower_pot.name', 'Flower Pot'),
 'flowering_azalea': ('tile.flowering_azalea.name', 'Flowering Azalea'),
 'flowing_lava': ('tile.flowing_lava.name', 'Lava'),
 'flowing_water': ('tile.flowing_water.name', 'Water'),
 'frame': ('item.frame.name', 'Item Frame'),
 'friend_pottery_sherd': ('item.friend_pottery_sherd.name', 'Friend Pottery Sherd'),
 'frog_spawn': ('tile.frog_spawn.name', 'Frogspawn'),
 'frosted_ice': ('tile.frosted_ice.name', 'Frosted Ice'),
 'furnace': ('tile.furnace.name', 'Furnace'),
 'ghast_tear': ('item.ghast_tear.name', 'Ghast Tear'),
 'gilded_blackstone': ('tile.gilded_blackstone.name', 'Gilded Blackstone'),
 'glass': ('tile.glass.name', 'Glass'),
 'glass_bottle': ('item.glass_bottle.name', 'Glass Bottle'),
 'glass_pane': ('tile.glass_pane.name', 'Glass Pane'),
 'glazed_terracotta_black': ('tile.glazedTerracotta.black.name', 'Black Glazed Terracotta'),
 'glazed_terracotta_blue': ('tile.glazedTerracotta.blue.name', 'Blue Glazed Terracotta'),
 'glazed_terracotta_brown': ('tile.glazedTerracotta.brown.name', 'Brown Glazed Terracotta'),
 'glazed_terracotta_cyan': ('tile.glazedTerracotta.cyan.name', 'Cyan Glazed Terracotta'),
 'glazed_terracotta_gray': ('tile.glazedTerracotta.gray.name', 'Gray Glazed Terracotta'),
 'glazed_terracotta_green': ('tile.glazedTerracotta.green.name', 'Green Glazed Terracotta'),
 'glazed_terracotta_light_blue': ('tile.glazedTerracotta.light_blue.name', 'Light Blue Glazed Terracotta'),
 'glazed_terracotta_lime': ('tile.glazedTerracotta.lime.name', 'Lime Glazed Terracotta'),
 'glazed_terracotta_magenta': ('tile.glazedTerracotta.magenta.name', 'Magenta Glazed Terracotta'),
 'glazed_terracotta_orange': ('tile.glazedTerracotta.orange.name', 'Orange Glazed Terracotta'),
 'glazed_terracotta_pink': ('tile.glazedTerracotta.pink.name', 'Pink Glazed Terracotta'),
 'glazed_terracotta_purple': ('tile.glazedTerracotta.purple.name', 'Purple Glazed Terracotta'),
 'glazed_terracotta_red': ('tile.glazedTerracotta.red.name', 'Red Glazed Terracotta'),
 'glazed_terracotta_silver': ('tile.glazedTerracotta.silver.name', 'Light Gray Glazed Terracotta'),
 'glazed_terracotta_white': ('tile.glazedTerracotta.white.name', 'White Glazed Terracotta'),
 'glazed_terracotta_yellow': ('tile.glazedTerracotta.yellow.name', 'Yellow Glazed Terracotta'),
 'globe_banner_pattern': ('item.globe_banner_pattern.name', 'Globe Banner Pattern'),
 'glow_berries': ('item.glow_berries.name', 'Glow Berries'),
 'glow_frame': ('item.glow_frame.name', 'Glow Item Frame'),
 'glow_ink_sac': ('item.glow_ink_sac.name', 'Glow Ink Sac'),
 'glow_lichen': ('tile.glow_lichen.name', 'Glow Lichen'),
 'glowingobsidian': ('tile.glowingobsidian.name', 'Glowing Obsidian'),
 'glowstone': ('tile.glowstone.name', 'Glowstone'),
 'glowstone_dust': ('item.glowstone_dust.name', 'Glowstone Dust'),
 'goat_horn': ('item.goat_horn.name', 'Goat Horn'),
 'gold_block': ('tile.gold_block.name', 'Block of Gold'),
 'gold_ingot': ('item.gold_ingot.name', 'Gold Ingot'),
 'gold_nugget': ('item.gold_nugget.name', 'Gold Nugget'),
 'gold_ore': ('tile.gold_ore.name', 'Gold Ore'),
 'golden_apple': ('item.golden_apple.name', 'Golden Apple'),
 'golden_axe': ('item.golden_axe.name', 'Golden Axe'),
 'golden_boots': ('item.golden_boots.name', 'Golden Boots'),
 'golden_carrot': ('item.golden_carrot.name', 'Golden Carrot'),
 'golden_chestplate': ('item.golden_chestplate.name', 'Golden Chestplate'),
 'golden_dandelion': ('tile.golden_dandelion.name', 'Golden Dandelion'),
 'golden_helmet': ('item.golden_helmet.name', 'Golden Helmet'),
 'golden_hoe': ('item.golden_hoe.name', 'Golden Hoe'),
 'golden_leggings': ('item.golden_leggings.name', 'Golden Leggings'),
 'golden_nautilus_armor': ('item.golden_nautilus_armor.name', 'Golden Nautilus Armor'),
 'golden_pickaxe': ('item.golden_pickaxe.name', 'Golden Pickaxe'),
 'golden_rail': ('tile.golden_rail.name', 'Powered Rail'),
 'golden_shovel': ('item.golden_shovel.name', 'Golden Shovel'),
 'golden_spear': ('item.golden_spear.name', 'Golden Spear'),
 'golden_sword': ('item.golden_sword.name', 'Golden Sword'),
 'granite_stairs': ('tile.granite_stairs.name', 'Granite Stairs'),
 'grass': ('tile.grass.name', 'Grass Block'),
 'grass_path': ('tile.grass_path.name', 'Dirt Path'),
 'gravel': ('tile.gravel.name', 'Gravel'),
 'gray_candle': ('tile.gray_candle.name', 'Gray Candle'),
 'gray_candle_cake': ('tile.gray_candle_cake.name', 'Cake with Gray Candle'),
 'gray_harness': ('item.gray_harness.name', 'Gray Harness'),
 'green_candle': ('tile.green_candle.name', 'Green Candle'),
 'green_candle_cake': ('tile.green_candle_cake.name', 'Cake with Green Candle'),
 'green_harness': ('item.green_harness.name', 'Green Harness'),
 'grindstone': ('tile.grindstone.name', 'Grindstone'),
 'gunpowder': ('item.gunpowder.name', 'Gunpowder'),
 'guster_banner_pattern': ('item.guster_banner_pattern.name', 'Guster Banner Pattern'),
 'guster_pottery_sherd': ('item.guster_pottery_sherd.name', 'Guster Pottery Sherd'),
 'hanging_roots': ('tile.hanging_roots.name', 'Hanging Roots'),
 'hardened_clay': ('tile.hardened_clay.name', 'Terracotta'),
 'hay_block': ('tile.hay_block.name', 'Hay Bale'),
 'heart_of_the_sea': ('item.heart_of_the_sea.name', 'Heart of the Sea'),
 'heart_pottery_sherd': ('item.heart_pottery_sherd.name', 'Heart Pottery Sherd'),
 'heartbreak_pottery_sherd': ('item.heartbreak_pottery_sherd.name', 'Heartbreak Pottery Sherd'),
 'heavy_core': ('tile.heavy_core.name', 'Heavy Core'),
 'heavy_weighted_pressure_plate': ('tile.heavy_weighted_pressure_plate.name', 'Heavy Weighted Pressure Plate'),
 'honey_block': ('tile.honey_block.name', 'Honey Block'),
 'honey_bottle': ('item.honey_bottle.name', 'Honey Bottle'),
 'honeycomb': ('item.honeycomb.name', 'Honeycomb'),
 'honeycomb_block': ('tile.honeycomb_block.name', 'Honeycomb Block'),
 'hopper': ('tile.hopper.name', 'Hopper'),
 'hopper_minecart': ('item.hopper_minecart.name', 'Minecart with Hopper'),
 'horn_coral_wall_fan': ('tile.horn_coral_wall_fan.name', 'Horn Coral Wall Fan'),
 'horsearmordiamond': ('item.horsearmordiamond.name', 'Diamond Horse Armor'),
 'horsearmorgold': ('item.horsearmorgold.name', 'Golden Horse Armor'),
 'horsearmoriron': ('item.horsearmoriron.name', 'Iron Horse Armor'),
 'horsearmorleather': ('item.horsearmorleather.name', 'Leather Horse Armor'),
 'host_armor_trim_smithing_template': ('item.host_armor_trim_smithing_template.name', 'Host Armor Trim'),
 'howl_pottery_sherd': ('item.howl_pottery_sherd.name', 'Howl Pottery Sherd'),
 'ice': ('tile.ice.name', 'Ice'),
 'infested_deepslate': ('tile.infested_deepslate.name', 'Infested Deepslate'),
 'invisible_bedrock': ('tile.invisibleBedrock.name', 'Invisible Bedrock'),
 'iron_axe': ('item.iron_axe.name', 'Iron Axe'),
 'iron_bars': ('tile.iron_bars.name', 'Iron Bars'),
 'iron_block': ('tile.iron_block.name', 'Block of Iron'),
 'iron_boots': ('item.iron_boots.name', 'Iron Boots'),
 'iron_chain': ('tile.iron_chain.name', 'Iron Chain'),
 'iron_chestplate': ('item.iron_chestplate.name', 'Iron Chestplate'),
 'iron_door': ('item.iron_door.name', 'Iron Door'),
 'iron_helmet': ('item.iron_helmet.name', 'Iron Helmet'),
 'iron_hoe': ('item.iron_hoe.name', 'Iron Hoe'),
 'iron_ingot': ('item.iron_ingot.name', 'Iron Ingot'),
 'iron_leggings': ('item.iron_leggings.name', 'Iron Leggings'),
 'iron_nautilus_armor': ('item.iron_nautilus_armor.name', 'Iron Nautilus Armor'),
 'iron_nugget': ('item.iron_nugget.name', 'Iron Nugget'),
 'iron_ore': ('tile.iron_ore.name', 'Iron Ore'),
 'iron_pickaxe': ('item.iron_pickaxe.name', 'Iron Pickaxe'),
 'iron_shovel': ('item.iron_shovel.name', 'Iron Shovel'),
 'iron_spear': ('item.iron_spear.name', 'Iron Spear'),
 'iron_sword': ('item.iron_sword.name', 'Iron Sword'),
 'iron_trapdoor': ('tile.iron_trapdoor.name', 'Iron Trapdoor'),
 'jigsaw': ('tile.jigsaw.name', 'Jigsaw Block'),
 'jukebox': ('tile.jukebox.name', 'Jukebox'),
 'jungle_button': ('tile.jungle_button.name', 'Jungle Button'),
 'jungle_door': ('item.jungle_door.name', 'Jungle Door'),
 'jungle_fence': ('tile.jungleFence.name', 'Jungle Fence'),
 'jungle_fence_gate': ('tile.jungle_fence_gate.name', 'Jungle Fence Gate'),
 'jungle_hanging_sign': ('item.jungle_hanging_sign.name', 'Jungle Hanging Sign'),
 'jungle_pressure_plate': ('tile.jungle_pressure_plate.name', 'Jungle Pressure Plate'),
 'jungle_shelf': ('tile.jungle_shelf.name', 'Jungle Shelf'),
 'jungle_sign': ('item.jungle_sign.name', 'Jungle Sign'),
 'jungle_stairs': ('tile.jungle_stairs.name', 'Jungle Stairs'),
 'jungle_standing_sign': ('tile.jungle_standing_sign.name', 'Jungle Sign'),
 'jungle_trapdoor': ('tile.jungle_trapdoor.name', 'Jungle Trapdoor'),
 'jungle_wall_sign': ('tile.jungle_wall_sign.name', 'Jungle Wall Sign'),
 'kelp': ('item.kelp.name', 'Kelp'),
 'ladder': ('tile.ladder.name', 'Ladder'),
 'lantern': ('tile.lantern.name', 'Lantern'),
 'lapis_block': ('tile.lapis_block.name', 'Block of Lapis Lazuli'),
 'lapis_ore': ('tile.lapis_ore.name', 'Lapis Lazuli Ore'),
 'large_amethyst_bud': ('tile.large_amethyst_bud.name', 'Large Amethyst Bud'),
 'lava': ('tile.lava.name', 'Lava'),
 'lead': ('item.lead.name', 'Lead'),
 'leaf_litter': ('tile.leaf_litter.name', 'Leaf Litter'),
 'leather': ('item.leather.name', 'Leather'),
 'leather_boots': ('item.leather_boots.name', 'Leather Boots'),
 'leather_chestplate': ('item.leather_chestplate.name', 'Leather Tunic'),
 'leather_helmet': ('item.leather_helmet.name', 'Leather Cap'),
 'leather_leggings': ('item.leather_leggings.name', 'Leather Pants'),
 'leaves': ('item.leaves.name', 'Leaves'),
 'leaves2_acacia': ('tile.leaves2.acacia.name', 'Acacia Leaves'),
 'leaves2_big_oak': ('tile.leaves2.big_oak.name', 'Dark Oak Leaves'),
 'leaves_acacia': ('tile.leaves.acacia.name', 'Acacia Leaves'),
 'leaves_big_oak': ('tile.leaves.big_oak.name', 'Dark Oak Leaves'),
 'leaves_birch': ('tile.leaves.birch.name', 'Birch Leaves'),
 'leaves_jungle': ('tile.leaves.jungle.name', 'Jungle Leaves'),
 'leaves_oak': ('tile.leaves.oak.name', 'Oak Leaves'),
 'leaves_spruce': ('tile.leaves.spruce.name', 'Spruce Leaves'),
 'lectern': ('tile.lectern.name', 'Lectern'),
 'lever': ('tile.lever.name', 'Lever'),
 'light_block': ('tile.light_block.name', 'Light'),
 'light_blue_candle': ('tile.light_blue_candle.name', 'Light Blue Candle'),
 'light_blue_candle_cake': ('tile.light_blue_candle_cake.name', 'Cake with Light Blue Candle'),
 'light_blue_harness': ('item.light_blue_harness.name', 'Light Blue Harness'),
 'light_gray_candle': ('tile.light_gray_candle.name', 'Light Gray Candle'),
 'light_gray_candle_cake': ('tile.light_gray_candle_cake.name', 'Cake with Light Gray Candle'),
 'light_gray_harness': ('item.light_gray_harness.name', 'Light Gray Harness'),
 'light_weighted_pressure_plate': ('tile.light_weighted_pressure_plate.name', 'Light Weighted Pressure Plate'),
 'lightning_rod': ('tile.lightning_rod.name', 'Lightning Rod'),
 'lime_candle': ('tile.lime_candle.name', 'Lime Candle'),
 'lime_candle_cake': ('tile.lime_candle_cake.name', 'Cake with Lime Candle'),
 'lime_harness': ('item.lime_harness.name', 'Lime Harness'),
 'lit_blast_furnace': ('tile.lit_blast_furnace.name', 'Lit Blast Furnace'),
 'lit_deepslate_redstone_ore': ('tile.lit_deepslate_redstone_ore.name', 'Lit Deepslate Redstone Ore'),
 'lit_furnace': ('tile.lit_furnace.name', 'Lit Furnace'),
 'lit_pumpkin': ('tile.lit_pumpkin.name', "Jack o'Lantern"),
 'lit_redstone_lamp': ('tile.lit_redstone_lamp.name', 'Lit Redstone Lamp'),
 'lit_redstone_ore': ('tile.lit_redstone_ore.name', 'Lit Redstone Ore'),
 'lit_smoker': ('tile.lit_smoker.name', 'Lit Smoker'),
 'lockedchest': ('tile.lockedchest.name', 'Locked chest'),
 'lodestone': ('tile.lodestone.name', 'Lodestone'),
 'lodestonecompass': ('item.lodestonecompass.name', 'Lodestone Compass'),
 'log': ('tile.log.name', 'Log'),
 'log_acacia': ('tile.log.acacia.name', 'Acacia Log'),
 'log_big_oak': ('tile.log.big_oak.name', 'Dark Oak Log'),
 'log_birch': ('tile.log.birch.name', 'Birch Log'),
 'log_jungle': ('tile.log.jungle.name', 'Jungle Log'),
 'log_oak': ('tile.log.oak.name', 'Oak Log'),
 'log_spruce': ('tile.log.spruce.name', 'Spruce Log'),
 'loom': ('tile.loom.name', 'Loom'),
 'mace': ('item.mace.name', 'Mace'),
 'magenta_candle': ('tile.magenta_candle.name', 'Magenta Candle'),
 'magenta_candle_cake': ('tile.magenta_candle_cake.name', 'Cake with Magenta Candle'),
 'magenta_harness': ('item.magenta_harness.name', 'Magenta Harness'),
 'magma': ('tile.magma.name', 'Magma Block'),
 'magma_cream': ('item.magma_cream.name', 'Magma Cream'),
 'mangrove_button': ('tile.mangrove_button.name', 'Mangrove Button'),
 'mangrove_door': ('item.mangrove_door.name', 'Mangrove Door'),
 'mangrove_double_slab': ('tile.mangrove_double_slab.name', 'Mangrove Double Slab'),
 'mangrove_fence': ('tile.mangrove_fence.name', 'Mangrove Fence'),
 'mangrove_fence_gate': ('tile.mangrove_fence_gate.name', 'Mangrove Fence Gate'),
 'mangrove_hanging_sign': ('item.mangrove_hanging_sign.name', 'Mangrove Hanging Sign'),
 'mangrove_leaves': ('tile.mangrove_leaves.name', 'Mangrove Leaves'),
 'mangrove_log': ('tile.mangrove_log.name', 'Mangrove Log'),
 'mangrove_planks': ('tile.mangrove_planks.name', 'Mangrove Planks'),
 'mangrove_pressure_plate': ('tile.mangrove_pressure_plate.name', 'Mangrove Pressure Plate'),
 'mangrove_propagule': ('tile.mangrove_propagule.name', 'Mangrove Propagule'),
 'mangrove_roots': ('tile.mangrove_roots.name', 'Mangrove Roots'),
 'mangrove_shelf': ('tile.mangrove_shelf.name', 'Mangrove Shelf'),
 'mangrove_sign': ('item.mangrove_sign.name', 'Mangrove Sign'),
 'mangrove_slab': ('tile.mangrove_slab.name', 'Mangrove Slab'),
 'mangrove_stairs': ('tile.mangrove_stairs.name', 'Mangrove Stairs'),
 'mangrove_standing_sign': ('tile.mangrove_standing_sign.name', 'Mangrove Sign'),
 'mangrove_trapdoor': ('tile.mangrove_trapdoor.name', 'Mangrove Trapdoor'),
 'mangrove_wall_sign': ('tile.mangrove_wall_sign.name', 'Mangrove Wall Sign'),
 'mangrove_wood': ('tile.mangrove_wood.name', 'Mangrove Wood'),
 'map': ('item.map.name', 'Map'),
 'map_exploration_buried_treasure': ('item.map.exploration.buried_treasure.name', 'Treasure Map'),
 'map_exploration_jungle_temple': ('item.map.exploration.jungle_temple.name', 'Jungle Explorer Map'),
 'map_exploration_mansion': ('item.map.exploration.mansion.name', 'Woodland Explorer Map'),
 'map_exploration_monument': ('item.map.exploration.monument.name', 'Ocean Explorer Map'),
 'map_exploration_swamp_hut': ('item.map.exploration.swamp_hut.name', 'Swamp Explorer Map'),
 'map_exploration_treasure': ('item.map.exploration.treasure.name', 'Treasure Map'),
 'map_exploration_trial_chambers': ('item.map.exploration.trial_chambers.name', 'Trial Explorer Map'),
 'map_exploration_village_desert': ('item.map.exploration.village_desert.name', 'Desert Village Map'),
 'map_exploration_village_plains': ('item.map.exploration.village_plains.name', 'Plains Village Map'),
 'map_exploration_village_savanna': ('item.map.exploration.village_savanna.name', 'Savanna Village Map'),
 'map_exploration_village_snowy': ('item.map.exploration.village_snowy.name', 'Snowy Village Map'),
 'map_exploration_village_taiga': ('item.map.exploration.village_taiga.name', 'Taiga Village Map'),
 'medium_amethyst_bud': ('tile.medium_amethyst_bud.name', 'Medium Amethyst Bud'),
 'melon': ('item.melon.name', 'Melon Slice'),
 'melon_block': ('tile.melon_block.name', 'Melon'),
 'melon_seeds': ('item.melon_seeds.name', 'Melon Seeds'),
 'melon_stem': ('tile.melon_stem.name', 'Melon Stem'),
 'milk': ('item.milk.name', 'Milk Bucket'),
 'minecart': ('item.minecart.name', 'Minecart'),
 'minecart_furnace': ('item.minecartFurnace.name', 'Minecart with Furnace'),
 'miner_pottery_sherd': ('item.miner_pottery_sherd.name', 'Miner Pottery Sherd'),
 'mob_spawner': ('tile.mob_spawner.name', 'Monster Spawner'),
 'mojang_banner_pattern': ('item.mojang_banner_pattern.name', 'Thing Banner Pattern'),
 'monster_egg': ('tile.monster_egg.name', 'Infested Stone'),
 'monster_egg_brick': ('tile.monster_egg.brick.name', 'Infested Stone Bricks'),
 'monster_egg_chiseledbrick': ('tile.monster_egg.chiseledbrick.name', 'Infested Chiseled Stone Brick'),
 'monster_egg_cobble': ('tile.monster_egg.cobble.name', 'Infested Cobblestone'),
 'monster_egg_crackedbrick': ('tile.monster_egg.crackedbrick.name', 'Infested Cracked Stone Brick'),
 'monster_egg_mossybrick': ('tile.monster_egg.mossybrick.name', 'Infested Mossy Stone Brick'),
 'monster_egg_stone': ('tile.monster_egg.stone.name', 'Infested Stone'),
 'moss_block': ('tile.moss_block.name', 'Moss Block'),
 'moss_carpet': ('tile.moss_carpet.name', 'Moss Carpet'),
 'mossy_cobblestone': ('tile.mossy_cobblestone.name', 'Mossy Cobblestone'),
 'mossy_cobblestone_stairs': ('tile.mossy_cobblestone_stairs.name', 'Mossy Cobblestone Stairs'),
 'mossy_stone_brick_stairs': ('tile.mossy_stone_brick_stairs.name', 'Mossy Stone Brick Stairs'),
 'mourner_pottery_sherd': ('item.mourner_pottery_sherd.name', 'Mourner Pottery Sherd'),
 'mud': ('tile.mud.name', 'Mud'),
 'mud_brick_double_slab': ('tile.mud_brick_double_slab.name', 'Mud Brick Double Slab'),
 'mud_brick_slab': ('tile.mud_brick_slab.name', 'Mud Brick Slab'),
 'mud_brick_stairs': ('tile.mud_brick_stairs.name', 'Mud Brick Stairs'),
 'mud_brick_wall': ('tile.mud_brick_wall.name', 'Mud Brick Wall'),
 'mud_bricks': ('tile.mud_bricks.name', 'Mud Bricks'),
 'muddy_mangrove_roots': ('tile.muddy_mangrove_roots.name', 'Muddy Mangrove Roots'),
 'mushroom': ('tile.mushroom.name', 'Mushroom'),
 'mushroom_stew': ('item.mushroom_stew.name', 'Mushroom Stew'),
 'mutton_cooked': ('item.muttonCooked.name', 'Cooked Mutton'),
 'mutton_raw': ('item.muttonRaw.name', 'Raw Mutton'),
 'mycelium': ('tile.mycelium.name', 'Mycelium'),
 'name_tag': ('item.name_tag.name', 'Name Tag'),
 'nautilus_shell': ('item.nautilus_shell.name', 'Nautilus Shell'),
 'nether_brick': ('tile.nether_brick.name', 'Nether Bricks'),
 'nether_brick_fence': ('tile.nether_brick_fence.name', 'Nether Brick Fence'),
 'nether_brick_stairs': ('tile.nether_brick_stairs.name', 'Nether Brick Stairs'),
 'nether_gold_ore': ('tile.nether_gold_ore.name', 'Nether Gold Ore'),
 'nether_sprouts': ('tile.nether_sprouts.name', 'Nether Sprouts'),
 'nether_star': ('item.netherStar.name', 'Nether Star'),
 'nether_wart': ('item.nether_wart.name', 'Nether Wart'),
 'nether_wart_block': ('tile.nether_wart_block.name', 'Nether Wart Block'),
 'netherbrick': ('item.netherbrick.name', 'Nether Brick'),
 'netherite_axe': ('item.netherite_axe.name', 'Netherite Axe'),
 'netherite_block': ('tile.netherite_block.name', 'Block of Netherite'),
 'netherite_boots': ('item.netherite_boots.name', 'Netherite Boots'),
 'netherite_chestplate': ('item.netherite_chestplate.name', 'Netherite Chestplate'),
 'netherite_helmet': ('item.netherite_helmet.name', 'Netherite Helmet'),
 'netherite_hoe': ('item.netherite_hoe.name', 'Netherite Hoe'),
 'netherite_horse_armor': ('item.netherite_horse_armor.name', 'Netherite Horse Armor'),
 'netherite_ingot': ('item.netherite_ingot.name', 'Netherite Ingot'),
 'netherite_leggings': ('item.netherite_leggings.name', 'Netherite Leggings'),
 'netherite_nautilus_armor': ('item.netherite_nautilus_armor.name', 'Netherite Nautilus Armor'),
 'netherite_pickaxe': ('item.netherite_pickaxe.name', 'Netherite Pickaxe'),
 'netherite_scrap': ('item.netherite_scrap.name', 'Netherite Scrap'),
 'netherite_shovel': ('item.netherite_shovel.name', 'Netherite Shovel'),
 'netherite_spear': ('item.netherite_spear.name', 'Netherite Spear'),
 'netherite_sword': ('item.netherite_sword.name', 'Netherite Sword'),
 'netherite_upgrade_smithing_template': ('item.netherite_upgrade_smithing_template.name', 'Netherite Upgrade'),
 'netherrack': ('tile.netherrack.name', 'Netherrack'),
 'netherreactor': ('tile.netherreactor.name', 'Nether Reactor Core'),
 'normal_stone_stairs': ('tile.normal_stone_stairs.name', 'Stone Stairs'),
 'noteblock': ('tile.noteblock.name', 'Note Block'),
 'oak_hanging_sign': ('item.oak_hanging_sign.name', 'Oak Hanging Sign'),
 'oak_shelf': ('tile.oak_shelf.name', 'Oak Shelf'),
 'oak_stairs': ('tile.oak_stairs.name', 'Oak Stairs'),
 'observer': ('tile.observer.name', 'Observer'),
 'obsidian': ('tile.obsidian.name', 'Obsidian'),
 'ochre_froglight': ('tile.ochre_froglight.name', 'Ochre Froglight'),
 'ominous_bottle': ('item.ominous_bottle.name', 'Ominous Bottle'),
 'ominous_trial_key': ('item.ominous_trial_key.name', 'Ominous Trial Key'),
 'open_eyeblossom': ('tile.open_eyeblossom.name', 'Open Eyeblossom'),
 'orange_candle': ('tile.orange_candle.name', 'Orange Candle'),
 'orange_candle_cake': ('tile.orange_candle_cake.name', 'Cake with Orange Candle'),
 'orange_harness': ('item.orange_harness.name', 'Orange Harness'),
 'ore_ruby': ('tile.oreRuby.name', 'Ruby Ore'),
 'oxidized_chiseled_copper': ('tile.oxidized_chiseled_copper.name', 'Oxidized Chiseled Copper'),
 'oxidized_copper': ('tile.oxidized_copper.name', 'Oxidized Copper'),
 'oxidized_copper_bars': ('tile.oxidized_copper_bars.name', 'Oxidized Copper Bars'),
 'oxidized_copper_bulb': ('tile.oxidized_copper_bulb.name', 'Oxidized Copper Bulb'),
 'oxidized_copper_chain': ('tile.oxidized_copper_chain.name', 'Oxidized Copper Chain'),
 'oxidized_copper_chest': ('tile.oxidized_copper_chest.name', 'Oxidized Copper Chest'),
 'oxidized_copper_door': ('item.oxidized_copper_door.name', 'Oxidized Copper Door'),
 'oxidized_copper_golem_statue': ('tile.oxidized_copper_golem_statue.name', 'Oxidized Copper Golem Statue'),
 'oxidized_copper_grate': ('tile.oxidized_copper_grate.name', 'Oxidized Copper Grate'),
 'oxidized_copper_lantern': ('tile.oxidized_copper_lantern.name', 'Oxidized Copper Lantern'),
 'oxidized_copper_trapdoor': ('tile.oxidized_copper_trapdoor.name', 'Oxidized Copper Trapdoor'),
 'oxidized_cut_copper': ('tile.oxidized_cut_copper.name', 'Oxidized Cut Copper'),
 'oxidized_cut_copper_slab': ('tile.oxidized_cut_copper_slab.name', 'Oxidized Cut Copper Slab'),
 'oxidized_cut_copper_stairs': ('tile.oxidized_cut_copper_stairs.name', 'Oxidized Cut Copper Stairs'),
 'oxidized_double_cut_copper_slab': ('tile.oxidized_double_cut_copper_slab.name', 'Oxidized Cut Copper Double Slab'),
 'oxidized_lightning_rod': ('tile.oxidized_lightning_rod.name', 'Oxidized Lightning Rod'),
 'packed_ice': ('tile.packed_ice.name', 'Packed Ice'),
 'packed_mud': ('tile.packed_mud.name', 'Packed Mud'),
 'painting': ('item.painting.name', 'Painting'),
 'pale_hanging_moss': ('tile.pale_hanging_moss.name', 'Pale Hanging Moss'),
 'pale_moss_block': ('tile.pale_moss_block.name', 'Pale Moss Block'),
 'pale_moss_carpet': ('tile.pale_moss_carpet.name', 'Pale Moss Carpet'),
 'pale_oak_button': ('tile.pale_oak_button.name', 'Pale Oak Button'),
 'pale_oak_door': ('item.pale_oak_door.name', 'Pale Oak Door'),
 'pale_oak_double_slab': ('tile.pale_oak_double_slab.name', 'Pale Oak Double Slab'),
 'pale_oak_fence': ('tile.pale_oak_fence.name', 'Pale Oak Fence'),
 'pale_oak_fence_gate': ('tile.pale_oak_fence_gate.name', 'Pale Oak Fence Gate'),
 'pale_oak_hanging_sign': ('item.pale_oak_hanging_sign.name', 'Pale Oak Hanging Sign'),
 'pale_oak_leaves': ('tile.pale_oak_leaves.name', 'Pale Oak Leaves'),
 'pale_oak_log': ('tile.pale_oak_log.name', 'Pale Oak Log'),
 'pale_oak_planks': ('tile.pale_oak_planks.name', 'Pale Oak Planks'),
 'pale_oak_pressure_plate': ('tile.pale_oak_pressure_plate.name', 'Pale Oak Pressure Plate'),
 'pale_oak_sapling': ('tile.pale_oak_sapling.name', 'Pale Oak Sapling'),
 'pale_oak_shelf': ('tile.pale_oak_shelf.name', 'Pale Oak Shelf'),
 'pale_oak_sign': ('item.pale_oak_sign.name', 'Pale Oak Sign'),
 'pale_oak_slab': ('tile.pale_oak_slab.name', 'Pale Oak Slab'),
 'pale_oak_stairs': ('tile.pale_oak_stairs.name', 'Pale Oak Stairs'),
 'pale_oak_standing_sign': ('tile.pale_oak_standing_sign.name', 'Pale Oak Sign'),
 'pale_oak_trapdoor': ('tile.pale_oak_trapdoor.name', 'Pale Oak Trapdoor'),
 'pale_oak_wall_sign': ('tile.pale_oak_wall_sign.name', 'Pale Oak Wall Sign'),
 'pale_oak_wood': ('tile.pale_oak_wood.name', 'Pale Oak Wood'),
 'paper': ('item.paper.name', 'Paper'),
 'pearlescent_froglight': ('tile.pearlescent_froglight.name', 'Pearlescent Froglight'),
 'phantom_membrane': ('item.phantom_membrane.name', 'Phantom Membrane'),
 'photo': ('item.photo.name', 'Photo'),
 'piglin_banner_pattern': ('item.piglin_banner_pattern.name', 'Snout Banner Pattern'),
 'pink_candle': ('tile.pink_candle.name', 'Pink Candle'),
 'pink_candle_cake': ('tile.pink_candle_cake.name', 'Cake with Pink Candle'),
 'pink_harness': ('item.pink_harness.name', 'Pink Harness'),
 'pink_petals': ('tile.pink_petals.name', 'Pink Petals'),
 'piston': ('tile.piston.name', 'Piston'),
 'piston_arm_collision': ('tile.piston_arm_collision.name', 'Piston Arm Collision'),
 'pitcher_crop': ('tile.pitcher_crop.name', 'Pitcher Crop'),
 'pitcher_plant': ('tile.pitcher_plant.name', 'Pitcher Plant'),
 'pitcher_pod': ('item.pitcher_pod.name', 'Pitcher Pod'),
 'planks': ('tile.planks.name', 'Wooden Planks'),
 'planks_acacia': ('tile.planks.acacia.name', 'Acacia Planks'),
 'planks_big_oak': ('tile.planks.big_oak.name', 'Dark Oak Planks'),
 'planks_birch': ('tile.planks.birch.name', 'Birch Planks'),
 'planks_jungle': ('tile.planks.jungle.name', 'Jungle Planks'),
 'planks_oak': ('tile.planks.oak.name', 'Oak Planks'),
 'planks_spruce': ('tile.planks.spruce.name', 'Spruce Planks'),
 'plenty_pottery_sherd': ('item.plenty_pottery_sherd.name', 'Plenty Pottery Sherd'),
 'podzol': ('tile.podzol.name', 'Podzol'),
 'pointed_dripstone': ('tile.pointed_dripstone.name', 'Pointed Dripstone'),
 'poisonous_potato': ('item.poisonous_potato.name', 'Poisonous Potato'),
 'polished_andesite_stairs': ('tile.polished_andesite_stairs.name', 'Polished Andesite Stairs'),
 'polished_basalt': ('tile.polished_basalt.name', 'Polished Basalt'),
 'polished_blackstone': ('tile.polished_blackstone.name', 'Polished Blackstone'),
 'polished_blackstone_brick_double_slab': ('tile.polished_blackstone_brick_double_slab.name',
                                           'Polished Blackstone Brick Double Slab'),
 'polished_blackstone_brick_slab': ('tile.polished_blackstone_brick_slab.name', 'Polished Blackstone Brick Slab'),
 'polished_blackstone_brick_stairs': ('tile.polished_blackstone_brick_stairs.name',
                                      'Polished Blackstone Brick Stairs'),
 'polished_blackstone_brick_wall': ('tile.polished_blackstone_brick_wall.name', 'Polished Blackstone Brick Wall'),
 'polished_blackstone_bricks': ('tile.polished_blackstone_bricks.name', 'Polished Blackstone Bricks'),
 'polished_blackstone_button': ('tile.polished_blackstone_button.name', 'Polished Blackstone Button'),
 'polished_blackstone_double_slab': ('tile.polished_blackstone_double_slab.name', 'Polished Blackstone Double Slab'),
 'polished_blackstone_pressure_plate': ('tile.polished_blackstone_pressure_plate.name',
                                        'Polished Blackstone Pressure Plate'),
 'polished_blackstone_slab': ('tile.polished_blackstone_slab.name', 'Polished Blackstone Slab'),
 'polished_blackstone_stairs': ('tile.polished_blackstone_stairs.name', 'Polished Blackstone Stairs'),
 'polished_blackstone_wall': ('tile.polished_blackstone_wall.name', 'Polished Blackstone Wall'),
 'polished_deepslate': ('tile.polished_deepslate.name', 'Polished Deepslate'),
 'polished_deepslate_double_slab': ('tile.polished_deepslate_double_slab.name', 'Polished Deepslate Double Slab'),
 'polished_deepslate_slab': ('tile.polished_deepslate_slab.name', 'Polished Deepslate Slab'),
 'polished_deepslate_stairs': ('tile.polished_deepslate_stairs.name', 'Polished Deepslate Stairs'),
 'polished_deepslate_wall': ('tile.polished_deepslate_wall.name', 'Polished Deepslate Wall'),
 'polished_diorite_stairs': ('tile.polished_diorite_stairs.name', 'Polished Diorite Stairs'),
 'polished_granite_stairs': ('tile.polished_granite_stairs.name', 'Polished Granite Stairs'),
 'polished_tuff': ('tile.polished_tuff.name', 'Polished Tuff'),
 'polished_tuff_double_slab': ('tile.polished_tuff_double_slab.name', 'Polished Tuff Double Slab'),
 'polished_tuff_slab': ('tile.polished_tuff_slab.name', 'Polished Tuff Slab'),
 'polished_tuff_stairs': ('tile.polished_tuff_stairs.name', 'Polished Tuff Stairs'),
 'polished_tuff_wall': ('tile.polished_tuff_wall.name', 'Polished Tuff Wall'),
 'porkchop': ('item.porkchop.name', 'Raw Porkchop'),
 'porkchop_cooked': ('item.porkchop_cooked.name', 'Cooked Porkchop'),
 'portal': ('tile.portal.name', 'Portal'),
 'portfolio': ('item.portfolio.name', 'Portfolio'),
 'potato': ('item.potato.name', 'Potato'),
 'potatoes': ('tile.potatoes.name', 'Potatoes'),
 'powder_snow': ('tile.powder_snow.name', 'Powder Snow'),
 'powered_comparator': ('tile.powered_comparator.name', 'Powered Comparator'),
 'powered_repeater': ('tile.powered_repeater.name', 'Powered Repeater'),
 'prismarine_bricks': ('tile.prismarine.bricks.name', 'Prismarine Bricks'),
 'prismarine_bricks_stairs': ('tile.prismarine_bricks_stairs.name', 'Prismarine Brick Stairs'),
 'prismarine_crystals': ('item.prismarine_crystals.name', 'Prismarine Crystals'),
 'prismarine_dark': ('tile.prismarine.dark.name', 'Dark Prismarine'),
 'prismarine_rough': ('tile.prismarine.rough.name', 'Prismarine'),
 'prismarine_shard': ('item.prismarine_shard.name', 'Prismarine Shard'),
 'prismarine_stairs': ('tile.prismarine_stairs.name', 'Prismarine Stairs'),
 'prize_pottery_sherd': ('item.prize_pottery_sherd.name', 'Prize Pottery Sherd'),
 'pufferfish': ('item.pufferfish.name', 'Pufferfish'),
 'pumpkin': ('tile.pumpkin.name', 'Pumpkin'),
 'pumpkin_pie': ('item.pumpkin_pie.name', 'Pumpkin Pie'),
 'pumpkin_seeds': ('item.pumpkin_seeds.name', 'Pumpkin Seeds'),
 'pumpkin_stem': ('tile.pumpkin_stem.name', 'Pumpkin Stem'),
 'purple_candle': ('tile.purple_candle.name', 'Purple Candle'),
 'purple_candle_cake': ('tile.purple_candle_cake.name', 'Cake with Purple Candle'),
 'purple_harness': ('item.purple_harness.name', 'Purple Harness'),
 'purpur_block_chiseled': ('tile.purpur_block.chiseled.name', 'Chiseled Purpur'),
 'purpur_block_default': ('tile.purpur_block.default.name', 'Purpur Block'),
 'purpur_block_lines': ('tile.purpur_block.lines.name', 'Purpur Pillar'),
 'purpur_stairs': ('tile.purpur_stairs.name', 'Purpur Stairs'),
 'quartz': ('item.quartz.name', 'Nether Quartz'),
 'quartz_block': ('tile.quartz_block.name', 'Block of Quartz'),
 'quartz_block_chiseled': ('tile.quartz_block.chiseled.name', 'Chiseled Quartz Block'),
 'quartz_block_default': ('tile.quartz_block.default.name', 'Block of Quartz'),
 'quartz_block_lines': ('tile.quartz_block.lines.name', 'Quartz Pillar'),
 'quartz_block_smooth': ('tile.quartz_block.smooth.name', 'Smooth Quartz Block'),
 'quartz_bricks': ('tile.quartz_bricks.name', 'Quartz Bricks'),
 'quartz_ore': ('tile.quartz_ore.name', 'Nether Quartz Ore'),
 'quartz_stairs': ('tile.quartz_stairs.name', 'Quartz Stairs'),
 'rabbit': ('item.rabbit.name', 'Raw Rabbit'),
 'rabbit_foot': ('item.rabbit_foot.name', "Rabbit's Foot"),
 'rabbit_hide': ('item.rabbit_hide.name', 'Rabbit Hide'),
 'rabbit_stew': ('item.rabbit_stew.name', 'Rabbit Stew'),
 'rail': ('tile.rail.name', 'Rail'),
 'raiser_armor_trim_smithing_template': ('item.raiser_armor_trim_smithing_template.name', 'Raiser Armor Trim'),
 'raw_copper': ('item.raw_copper.name', 'Raw Copper'),
 'raw_copper_block': ('tile.raw_copper_block.name', 'Block of Raw Copper'),
 'raw_gold': ('item.raw_gold.name', 'Raw Gold'),
 'raw_gold_block': ('tile.raw_gold_block.name', 'Block of Raw Gold'),
 'raw_iron': ('item.raw_iron.name', 'Raw Iron'),
 'raw_iron_block': ('tile.raw_iron_block.name', 'Block of Raw Iron'),
 'record': ('item.record.name', 'Music Disc'),
 'recovery_compass': ('item.recovery_compass.name', 'Recovery Compass'),
 'red_candle': ('tile.red_candle.name', 'Red Candle'),
 'red_candle_cake': ('tile.red_candle_cake.name', 'Cake with Red Candle'),
 'red_flower': ('tile.red_flower.name', 'Flower'),
 'red_flower_allium': ('tile.red_flower.allium.name', 'Allium'),
 'red_flower_blue_orchid': ('tile.red_flower.blueOrchid.name', 'Blue Orchid'),
 'red_flower_cornflower': ('tile.red_flower.cornflower.name', 'Cornflower'),
 'red_flower_houstonia': ('tile.red_flower.houstonia.name', 'Azure Bluet'),
 'red_flower_lily_of_the_valley': ('tile.red_flower.lilyOfTheValley.name', 'Lily of the Valley'),
 'red_flower_oxeye_daisy': ('tile.red_flower.oxeyeDaisy.name', 'Oxeye Daisy'),
 'red_flower_poppy': ('tile.red_flower.poppy.name', 'Poppy'),
 'red_flower_tulip_orange': ('tile.red_flower.tulipOrange.name', 'Orange Tulip'),
 'red_flower_tulip_pink': ('tile.red_flower.tulipPink.name', 'Pink Tulip'),
 'red_flower_tulip_red': ('tile.red_flower.tulipRed.name', 'Red Tulip'),
 'red_flower_tulip_white': ('tile.red_flower.tulipWhite.name', 'White Tulip'),
 'red_harness': ('item.red_harness.name', 'Red Harness'),
 'red_mushroom': ('tile.red_mushroom.name', 'Red Mushroom'),
 'red_mushroom_block': ('tile.red_mushroom_block.name', 'Red Mushroom Block'),
 'red_nether_brick': ('tile.red_nether_brick.name', 'Red Nether Bricks'),
 'red_nether_brick_stairs': ('tile.red_nether_brick_stairs.name', 'Red Nether Brick Stairs'),
 'red_sandstone': ('tile.red_sandstone.name', 'Red Sandstone'),
 'red_sandstone_chiseled': ('tile.red_sandstone.chiseled.name', 'Chiseled Red Sandstone'),
 'red_sandstone_cut': ('tile.red_sandstone.cut.name', 'Cut Red Sandstone'),
 'red_sandstone_default': ('tile.red_sandstone.default.name', 'Red Sandstone'),
 'red_sandstone_smooth': ('tile.red_sandstone.smooth.name', 'Smooth Red Sandstone'),
 'red_sandstone_stairs': ('tile.red_sandstone_stairs.name', 'Red Sandstone Stairs'),
 'redstone': ('item.redstone.name', 'Redstone Dust'),
 'redstone_block': ('tile.redstone_block.name', 'Block of Redstone'),
 'redstone_lamp': ('tile.redstone_lamp.name', 'Redstone Lamp'),
 'redstone_ore': ('tile.redstone_ore.name', 'Redstone Ore'),
 'redstone_torch': ('tile.redstone_torch.name', 'Redstone Torch'),
 'redstone_wire': ('tile.redstone_wire.name', 'Redstone Dust'),
 'reeds': ('item.reeds.name', 'Sugar Cane'),
 'reinforced_deepslate': ('tile.reinforced_deepslate.name', 'Reinforced Deepslate'),
 'repeater': ('item.repeater.name', 'Redstone Repeater'),
 'repeating_command_block': ('tile.repeating_command_block.name', 'Repeating Command Block'),
 'resin_block': ('tile.resin_block.name', 'Block of Resin'),
 'resin_brick': ('item.resin_brick.name', 'Resin Brick'),
 'resin_brick_double_slab': ('tile.resin_brick_double_slab.name', 'Resin Brick Double Slab'),
 'resin_brick_slab': ('tile.resin_brick_slab.name', 'Resin Brick Slab'),
 'resin_brick_stairs': ('tile.resin_brick_stairs.name', 'Resin Brick Stairs'),
 'resin_brick_wall': ('tile.resin_brick_wall.name', 'Resin Brick Wall'),
 'resin_bricks': ('tile.resin_bricks.name', 'Resin Bricks'),
 'resin_clump': ('tile.resin_clump.name', 'Resin Clump'),
 'respawn_anchor': ('tile.respawn_anchor.name', 'Respawn Anchor'),
 'rib_armor_trim_smithing_template': ('item.rib_armor_trim_smithing_template.name', 'Rib Armor Trim'),
 'rotten_flesh': ('item.rotten_flesh.name', 'Rotten Flesh'),
 'ruby': ('item.ruby.name', 'Ruby'),
 'saddle': ('item.saddle.name', 'Saddle'),
 'salmon': ('item.salmon.name', 'Raw Salmon'),
 'sand': ('tile.sand.name', 'Sand'),
 'sand_default': ('tile.sand.default.name', 'Sand'),
 'sand_red': ('tile.sand.red.name', 'Red Sand'),
 'sandstone': ('tile.sandstone.name', 'Sandstone'),
 'sandstone_chiseled': ('tile.sandstone.chiseled.name', 'Chiseled Sandstone'),
 'sandstone_cut': ('tile.sandstone.cut.name', 'Cut Sandstone'),
 'sandstone_default': ('tile.sandstone.default.name', 'Sandstone'),
 'sandstone_smooth': ('tile.sandstone.smooth.name', 'Smooth Sandstone'),
 'sandstone_stairs': ('tile.sandstone_stairs.name', 'Sandstone Stairs'),
 'sapling_acacia': ('tile.sapling.acacia.name', 'Acacia Sapling'),
 'sapling_big_oak': ('tile.sapling.big_oak.name', 'Dark Oak Sapling'),
 'sapling_birch': ('tile.sapling.birch.name', 'Birch Sapling'),
 'sapling_jungle': ('tile.sapling.jungle.name', 'Jungle Sapling'),
 'sapling_oak': ('tile.sapling.oak.name', 'Oak Sapling'),
 'sapling_spruce': ('tile.sapling.spruce.name', 'Spruce Sapling'),
 'scaffolding': ('tile.scaffolding.name', 'Scaffolding'),
 'scrape_pottery_sherd': ('item.scrape_pottery_sherd.name', 'Scrape Pottery Sherd'),
 'sculk': ('tile.sculk.name', 'Sculk'),
 'sculk_catalyst': ('tile.sculk_catalyst.name', 'Sculk Catalyst'),
 'sculk_sensor': ('tile.sculk_sensor.name', 'Sculk Sensor'),
 'sculk_shrieker': ('tile.sculk_shrieker.name', 'Sculk Shrieker'),
 'sculk_vein': ('tile.sculk_vein.name', 'Sculk Vein'),
 'sea_lantern': ('tile.seaLantern.name', 'Sea Lantern'),
 'sea_pickle': ('tile.sea_pickle.name', 'Sea Pickle'),
 'seagrass_seagrass': ('tile.seagrass.seagrass.name', 'Seagrass'),
 'sentry_armor_trim_smithing_template': ('item.sentry_armor_trim_smithing_template.name', 'Sentry Armor Trim'),
 'shaper_armor_trim_smithing_template': ('item.shaper_armor_trim_smithing_template.name', 'Shaper Armor Trim'),
 'sheaf_pottery_sherd': ('item.sheaf_pottery_sherd.name', 'Sheaf Pottery Sherd'),
 'shears': ('item.shears.name', 'Shears'),
 'shelter_pottery_sherd': ('item.shelter_pottery_sherd.name', 'Shelter Pottery Sherd'),
 'shield': ('item.shield.name', 'Shield'),
 'shield_black': ('item.shield.black.name', 'Black Shield'),
 'shield_blue': ('item.shield.blue.name', 'Blue Shield'),
 'shield_brown': ('item.shield.brown.name', 'Brown Shield'),
 'shield_cyan': ('item.shield.cyan.name', 'Cyan Shield'),
 'shield_gray': ('item.shield.gray.name', 'Gray Shield'),
 'shield_green': ('item.shield.green.name', 'Green Shield'),
 'shield_light_blue': ('item.shield.lightBlue.name', 'Light Blue Shield'),
 'shield_lime': ('item.shield.lime.name', 'Lime Shield'),
 'shield_magenta': ('item.shield.magenta.name', 'Magenta Shield'),
 'shield_orange': ('item.shield.orange.name', 'Orange Shield'),
 'shield_pink': ('item.shield.pink.name', 'Pink Shield'),
 'shield_purple': ('item.shield.purple.name', 'Purple Shield'),
 'shield_red': ('item.shield.red.name', 'Red Shield'),
 'shield_silver': ('item.shield.silver.name', 'Light Gray Shield'),
 'shield_white': ('item.shield.white.name', 'White Shield'),
 'shield_yellow': ('item.shield.yellow.name', 'Yellow Shield'),
 'short_dry_grass': ('tile.short_dry_grass.name', 'Short Dry Grass'),
 'shroomlight': ('tile.shroomlight.name', 'Shroomlight'),
 'shulker_box': ('tile.shulkerBox.name', 'Shulker Box'),
 'shulker_box_black': ('tile.shulkerBoxBlack.name', 'Black Shulker Box'),
 'shulker_box_blue': ('tile.shulkerBoxBlue.name', 'Blue Shulker Box'),
 'shulker_box_brown': ('tile.shulkerBoxBrown.name', 'Brown Shulker Box'),
 'shulker_box_cyan': ('tile.shulkerBoxCyan.name', 'Cyan Shulker Box'),
 'shulker_box_gray': ('tile.shulkerBoxGray.name', 'Gray Shulker Box'),
 'shulker_box_green': ('tile.shulkerBoxGreen.name', 'Green Shulker Box'),
 'shulker_box_light_blue': ('tile.shulkerBoxLightBlue.name', 'Light Blue Shulker Box'),
 'shulker_box_lime': ('tile.shulkerBoxLime.name', 'Lime Shulker Box'),
 'shulker_box_magenta': ('tile.shulkerBoxMagenta.name', 'Magenta Shulker Box'),
 'shulker_box_orange': ('tile.shulkerBoxOrange.name', 'Orange Shulker Box'),
 'shulker_box_pink': ('tile.shulkerBoxPink.name', 'Pink Shulker Box'),
 'shulker_box_purple': ('tile.shulkerBoxPurple.name', 'Purple Shulker Box'),
 'shulker_box_red': ('tile.shulkerBoxRed.name', 'Red Shulker Box'),
 'shulker_box_silver': ('tile.shulkerBoxSilver.name', 'Light Gray Shulker Box'),
 'shulker_box_white': ('tile.shulkerBoxWhite.name', 'White Shulker Box'),
 'shulker_box_yellow': ('tile.shulkerBoxYellow.name', 'Yellow Shulker Box'),
 'shulker_shell': ('item.shulker_shell.name', 'Shulker Shell'),
 'sign': ('item.sign.name', 'Oak Sign'),
 'silence_armor_trim_smithing_template': ('item.silence_armor_trim_smithing_template.name', 'Silence Armor Trim'),
 'skull_banner_pattern': ('item.skull_banner_pattern.name', 'Skull Charge Banner Pattern'),
 'skull_char': ('item.skull.char.name', 'Player Head'),
 'skull_creeper': ('item.skull.creeper.name', 'Creeper Head'),
 'skull_dragon': ('item.skull.dragon.name', 'Dragon Head'),
 'skull_piglin': ('item.skull.piglin.name', 'Piglin Head'),
 'skull_player': ('item.skull.player.name', "%s's Head"),
 'skull_pottery_sherd': ('item.skull_pottery_sherd.name', 'Skull Pottery Sherd'),
 'skull_skeleton': ('item.skull.skeleton.name', 'Skeleton Skull'),
 'skull_wither': ('item.skull.wither.name', 'Wither Skeleton Skull'),
 'skull_zombie': ('item.skull.zombie.name', 'Zombie Head'),
 'slime': ('tile.slime.name', 'Slime Block'),
 'slime_ball': ('item.slime_ball.name', 'Slimeball'),
 'small_amethyst_bud': ('tile.small_amethyst_bud.name', 'Small Amethyst Bud'),
 'small_dripleaf_block': ('tile.small_dripleaf_block.name', 'Small Dripleaf'),
 'smithing_table': ('tile.smithing_table.name', 'Smithing Table'),
 'smithing_template': ('item.smithing_template.name', 'Smithing Template'),
 'smoker': ('tile.smoker.name', 'Smoker'),
 'smooth_basalt': ('tile.smooth_basalt.name', 'Smooth Basalt'),
 'smooth_quartz_stairs': ('tile.smooth_quartz_stairs.name', 'Smooth Quartz Stairs'),
 'smooth_red_sandstone_stairs': ('tile.smooth_red_sandstone_stairs.name', 'Smooth Red Sandstone Stairs'),
 'smooth_sandstone_stairs': ('tile.smooth_sandstone_stairs.name', 'Smooth Sandstone Stairs'),
 'smooth_stone': ('tile.smooth_stone.name', 'Smooth Stone'),
 'sniffer_egg': ('tile.sniffer_egg.name', 'Sniffer Egg'),
 'snort_pottery_sherd': ('item.snort_pottery_sherd.name', 'Snort Pottery Sherd'),
 'snout_armor_trim_smithing_template': ('item.snout_armor_trim_smithing_template.name', 'Snout Armor Trim'),
 'snow': ('tile.snow.name', 'Snow Block'),
 'snow_layer': ('tile.snow_layer.name', 'Snow'),
 'snowball': ('item.snowball.name', 'Snowball'),
 'soul_campfire': ('tile.soul_campfire.name', 'Soul Campfire'),
 'soul_fire': ('tile.soul_fire.name', 'Soul Fire'),
 'soul_lantern': ('tile.soul_lantern.name', 'Soul Lantern'),
 'soul_sand': ('tile.soul_sand.name', 'Soul Sand'),
 'soul_soil': ('tile.soul_soil.name', 'Soul Soil'),
 'soul_torch': ('tile.soul_torch.name', 'Soul Torch'),
 'spawn_egg_entity_agent': ('item.spawn_egg.entity.agent.name', 'Agent Spawn Egg'),
 'spawn_egg_entity_allay': ('item.spawn_egg.entity.allay.name', 'Allay Spawn Egg'),
 'spawn_egg_entity_armadillo': ('item.spawn_egg.entity.armadillo.name', 'Armadillo Spawn Egg'),
 'spawn_egg_entity_axolotl': ('item.spawn_egg.entity.axolotl.name', 'Axolotl Spawn Egg'),
 'spawn_egg_entity_bat': ('item.spawn_egg.entity.bat.name', 'Bat Spawn Egg'),
 'spawn_egg_entity_bee': ('item.spawn_egg.entity.bee.name', 'Bee Spawn Egg'),
 'spawn_egg_entity_blaze': ('item.spawn_egg.entity.blaze.name', 'Blaze Spawn Egg'),
 'spawn_egg_entity_bogged': ('item.spawn_egg.entity.bogged.name', 'Bogged Spawn Egg'),
 'spawn_egg_entity_breeze': ('item.spawn_egg.entity.breeze.name', 'Breeze Spawn Egg'),
 'spawn_egg_entity_camel': ('item.spawn_egg.entity.camel.name', 'Camel Spawn Egg'),
 'spawn_egg_entity_camel_husk': ('item.spawn_egg.entity.camel_husk.name', 'Camel Husk Spawn Egg'),
 'spawn_egg_entity_cat': ('item.spawn_egg.entity.cat.name', 'Cat Spawn Egg'),
 'spawn_egg_entity_cave_spider': ('item.spawn_egg.entity.cave_spider.name', 'Cave Spider Spawn Egg'),
 'spawn_egg_entity_chicken': ('item.spawn_egg.entity.chicken.name', 'Chicken Spawn Egg'),
 'spawn_egg_entity_cod': ('item.spawn_egg.entity.cod.name', 'Cod Spawn Egg'),
 'spawn_egg_entity_copper_golem': ('item.spawn_egg.entity.copper_golem.name', 'Copper Golem Spawn Egg'),
 'spawn_egg_entity_cow': ('item.spawn_egg.entity.cow.name', 'Cow Spawn Egg'),
 'spawn_egg_entity_creaking': ('item.spawn_egg.entity.creaking.name', 'Creaking Spawn Egg'),
 'spawn_egg_entity_creeper': ('item.spawn_egg.entity.creeper.name', 'Creeper Spawn Egg'),
 'spawn_egg_entity_dolphin': ('item.spawn_egg.entity.dolphin.name', 'Dolphin Spawn Egg'),
 'spawn_egg_entity_donkey': ('item.spawn_egg.entity.donkey.name', 'Donkey Spawn Egg'),
 'spawn_egg_entity_drowned': ('item.spawn_egg.entity.drowned.name', 'Drowned Spawn Egg'),
 'spawn_egg_entity_elder_guardian': ('item.spawn_egg.entity.elder_guardian.name', 'Elder Guardian Spawn Egg'),
 'spawn_egg_entity_ender_dragon': ('item.spawn_egg.entity.ender_dragon.name', 'Ender Dragon Spawn Egg'),
 'spawn_egg_entity_enderman': ('item.spawn_egg.entity.enderman.name', 'Enderman Spawn Egg'),
 'spawn_egg_entity_endermite': ('item.spawn_egg.entity.endermite.name', 'Endermite Spawn Egg'),
 'spawn_egg_entity_evocation_illager': ('item.spawn_egg.entity.evocation_illager.name', 'Evoker Spawn Egg'),
 'spawn_egg_entity_fox': ('item.spawn_egg.entity.fox.name', 'Fox Spawn Egg'),
 'spawn_egg_entity_frog': ('item.spawn_egg.entity.frog.name', 'Frog Spawn Egg'),
 'spawn_egg_entity_ghast': ('item.spawn_egg.entity.ghast.name', 'Ghast Spawn Egg'),
 'spawn_egg_entity_glow_squid': ('item.spawn_egg.entity.glow_squid.name', 'Glow Squid Spawn Egg'),
 'spawn_egg_entity_goat': ('item.spawn_egg.entity.goat.name', 'Goat Spawn Egg'),
 'spawn_egg_entity_guardian': ('item.spawn_egg.entity.guardian.name', 'Guardian Spawn Egg'),
 'spawn_egg_entity_happy_ghast': ('item.spawn_egg.entity.happy_ghast.name', 'Happy Ghast Spawn Egg'),
 'spawn_egg_entity_hoglin': ('item.spawn_egg.entity.hoglin.name', 'Hoglin Spawn Egg'),
 'spawn_egg_entity_horse': ('item.spawn_egg.entity.horse.name', 'Horse Spawn Egg'),
 'spawn_egg_entity_husk': ('item.spawn_egg.entity.husk.name', 'Husk Spawn Egg'),
 'spawn_egg_entity_iron_golem': ('item.spawn_egg.entity.iron_golem.name', 'Iron Golem Spawn Egg'),
 'spawn_egg_entity_llama': ('item.spawn_egg.entity.llama.name', 'Llama Spawn Egg'),
 'spawn_egg_entity_magma_cube': ('item.spawn_egg.entity.magma_cube.name', 'Magma Cube Spawn Egg'),
 'spawn_egg_entity_mooshroom': ('item.spawn_egg.entity.mooshroom.name', 'Mooshroom Spawn Egg'),
 'spawn_egg_entity_mule': ('item.spawn_egg.entity.mule.name', 'Mule Spawn Egg'),
 'spawn_egg_entity_nautilus': ('item.spawn_egg.entity.nautilus.name', 'Nautilus Spawn Egg'),
 'spawn_egg_entity_npc': ('item.spawn_egg.entity.npc.name', 'NPC Spawn Egg'),
 'spawn_egg_entity_ocelot': ('item.spawn_egg.entity.ocelot.name', 'Ocelot Spawn Egg'),
 'spawn_egg_entity_panda': ('item.spawn_egg.entity.panda.name', 'Panda Spawn Egg'),
 'spawn_egg_entity_parched': ('item.spawn_egg.entity.parched.name', 'Parched Spawn Egg'),
 'spawn_egg_entity_parrot': ('item.spawn_egg.entity.parrot.name', 'Parrot Spawn Egg'),
 'spawn_egg_entity_phantom': ('item.spawn_egg.entity.phantom.name', 'Phantom Spawn Egg'),
 'spawn_egg_entity_pig': ('item.spawn_egg.entity.pig.name', 'Pig Spawn Egg'),
 'spawn_egg_entity_piglin': ('item.spawn_egg.entity.piglin.name', 'Piglin Spawn Egg'),
 'spawn_egg_entity_piglin_brute': ('item.spawn_egg.entity.piglin_brute.name', 'Piglin Brute Spawn Egg'),
 'spawn_egg_entity_pillager': ('item.spawn_egg.entity.pillager.name', 'Pillager Spawn Egg'),
 'spawn_egg_entity_polar_bear': ('item.spawn_egg.entity.polar_bear.name', 'Polar Bear Spawn Egg'),
 'spawn_egg_entity_pufferfish': ('item.spawn_egg.entity.pufferfish.name', 'Pufferfish Spawn Egg'),
 'spawn_egg_entity_rabbit': ('item.spawn_egg.entity.rabbit.name', 'Rabbit Spawn Egg'),
 'spawn_egg_entity_ravager': ('item.spawn_egg.entity.ravager.name', 'Ravager Spawn Egg'),
 'spawn_egg_entity_salmon': ('item.spawn_egg.entity.salmon.name', 'Salmon Spawn Egg'),
 'spawn_egg_entity_sheep': ('item.spawn_egg.entity.sheep.name', 'Sheep Spawn Egg'),
 'spawn_egg_entity_shulker': ('item.spawn_egg.entity.shulker.name', 'Shulker Spawn Egg'),
 'spawn_egg_entity_silverfish': ('item.spawn_egg.entity.silverfish.name', 'Silverfish Spawn Egg'),
 'spawn_egg_entity_skeleton': ('item.spawn_egg.entity.skeleton.name', 'Skeleton Spawn Egg'),
 'spawn_egg_entity_skeleton_horse': ('item.spawn_egg.entity.skeleton_horse.name', 'Skeleton Horse Spawn Egg'),
 'spawn_egg_entity_slime': ('item.spawn_egg.entity.slime.name', 'Slime Spawn Egg'),
 'spawn_egg_entity_sniffer': ('item.spawn_egg.entity.sniffer.name', 'Sniffer Spawn Egg'),
 'spawn_egg_entity_snow_golem': ('item.spawn_egg.entity.snow_golem.name', 'Snow Golem Spawn Egg'),
 'spawn_egg_entity_spider': ('item.spawn_egg.entity.spider.name', 'Spider Spawn Egg'),
 'spawn_egg_entity_squid': ('item.spawn_egg.entity.squid.name', 'Squid Spawn Egg'),
 'spawn_egg_entity_stray': ('item.spawn_egg.entity.stray.name', 'Stray Spawn Egg'),
 'spawn_egg_entity_strider': ('item.spawn_egg.entity.strider.name', 'Strider Spawn Egg'),
 'spawn_egg_entity_tadpole': ('item.spawn_egg.entity.tadpole.name', 'Tadpole Spawn Egg'),
 'spawn_egg_entity_trader_llama': ('item.spawn_egg.entity.trader_llama.name', 'Trader Llama Spawn Egg'),
 'spawn_egg_entity_tropicalfish': ('item.spawn_egg.entity.tropicalfish.name', 'Tropical Fish Spawn Egg'),
 'spawn_egg_entity_turtle': ('item.spawn_egg.entity.turtle.name', 'Turtle Spawn Egg'),
 'spawn_egg_entity_unknown': ('item.spawn_egg.entity.unknown.name', 'Spawn Egg'),
 'spawn_egg_entity_vex': ('item.spawn_egg.entity.vex.name', 'Vex Spawn Egg'),
 'spawn_egg_entity_villager': ('item.spawn_egg.entity.villager.name', 'Villager Spawn Egg'),
 'spawn_egg_entity_villager_v2': ('item.spawn_egg.entity.villager_v2.name', 'Villager Spawn Egg'),
 'spawn_egg_entity_vindicator': ('item.spawn_egg.entity.vindicator.name', 'Vindicator Spawn Egg'),
 'spawn_egg_entity_wandering_trader': ('item.spawn_egg.entity.wandering_trader.name', 'Wandering Trader Spawn Egg'),
 'spawn_egg_entity_warden': ('item.spawn_egg.entity.warden.name', 'Warden Spawn Egg'),
 'spawn_egg_entity_witch': ('item.spawn_egg.entity.witch.name', 'Witch Spawn Egg'),
 'spawn_egg_entity_wither': ('item.spawn_egg.entity.wither.name', 'Wither Spawn Egg'),
 'spawn_egg_entity_wither_skeleton': ('item.spawn_egg.entity.wither_skeleton.name', 'Wither Skeleton Spawn Egg'),
 'spawn_egg_entity_wolf': ('item.spawn_egg.entity.wolf.name', 'Wolf Spawn Egg'),
 'spawn_egg_entity_zoglin': ('item.spawn_egg.entity.zoglin.name', 'Zoglin Spawn Egg'),
 'spawn_egg_entity_zombie': ('item.spawn_egg.entity.zombie.name', 'Zombie Spawn Egg'),
 'spawn_egg_entity_zombie_horse': ('item.spawn_egg.entity.zombie_horse.name', 'Zombie Horse Spawn Egg'),
 'spawn_egg_entity_zombie_nautilus': ('item.spawn_egg.entity.zombie_nautilus.name', 'Zombie Nautilus Spawn Egg'),
 'spawn_egg_entity_zombie_pigman': ('item.spawn_egg.entity.zombie_pigman.name', 'Zombified Piglin Spawn Egg'),
 'spawn_egg_entity_zombie_villager': ('item.spawn_egg.entity.zombie_villager.name', 'Zombie Villager Spawn Egg'),
 'spawn_egg_entity_zombie_villager_v2': ('item.spawn_egg.entity.zombie_villager_v2.name',
                                         'Zombie Villager Spawn Egg'),
 'speckled_melon': ('item.speckled_melon.name', 'Glistering Melon Slice'),
 'spider_eye': ('item.spider_eye.name', 'Spider Eye'),
 'spire_armor_trim_smithing_template': ('item.spire_armor_trim_smithing_template.name', 'Spire Armor Trim'),
 'sponge_dry': ('tile.sponge.dry.name', 'Sponge'),
 'sponge_wet': ('tile.sponge.wet.name', 'Wet Sponge'),
 'spore_blossom': ('tile.spore_blossom.name', 'Spore Blossom'),
 'spruce_button': ('tile.spruce_button.name', 'Spruce Button'),
 'spruce_door': ('item.spruce_door.name', 'Spruce Door'),
 'spruce_fence': ('tile.spruceFence.name', 'Spruce Fence'),
 'spruce_fence_gate': ('tile.spruce_fence_gate.name', 'Spruce Fence Gate'),
 'spruce_hanging_sign': ('item.spruce_hanging_sign.name', 'Spruce Hanging Sign'),
 'spruce_pressure_plate': ('tile.spruce_pressure_plate.name', 'Spruce Pressure Plate'),
 'spruce_shelf': ('tile.spruce_shelf.name', 'Spruce Shelf'),
 'spruce_sign': ('item.spruce_sign.name', 'Spruce Sign'),
 'spruce_stairs': ('tile.spruce_stairs.name', 'Spruce Stairs'),
 'spruce_standing_sign': ('tile.spruce_standing_sign.name', 'Spruce Sign'),
 'spruce_trapdoor': ('tile.spruce_trapdoor.name', 'Spruce Trapdoor'),
 'spruce_wall_sign': ('tile.spruce_wall_sign.name', 'Spruce Wall Sign'),
 'spyglass': ('item.spyglass.name', 'Spyglass'),
 'stained_glass_black': ('tile.stained_glass.black.name', 'Black Stained Glass'),
 'stained_glass_blue': ('tile.stained_glass.blue.name', 'Blue Stained Glass'),
 'stained_glass_brown': ('tile.stained_glass.brown.name', 'Brown Stained Glass'),
 'stained_glass_cyan': ('tile.stained_glass.cyan.name', 'Cyan Stained Glass'),
 'stained_glass_gray': ('tile.stained_glass.gray.name', 'Gray Stained Glass'),
 'stained_glass_green': ('tile.stained_glass.green.name', 'Green Stained Glass'),
 'stained_glass_light_blue': ('tile.stained_glass.light_blue.name', 'Light Blue Stained Glass'),
 'stained_glass_lime': ('tile.stained_glass.lime.name', 'Lime Stained Glass'),
 'stained_glass_magenta': ('tile.stained_glass.magenta.name', 'Magenta Stained Glass'),
 'stained_glass_orange': ('tile.stained_glass.orange.name', 'Orange Stained Glass'),
 'stained_glass_pane_black': ('tile.stained_glass_pane.black.name', 'Black Stained Glass Pane'),
 'stained_glass_pane_blue': ('tile.stained_glass_pane.blue.name', 'Blue Stained Glass Pane'),
 'stained_glass_pane_brown': ('tile.stained_glass_pane.brown.name', 'Brown Stained Glass Pane'),
 'stained_glass_pane_cyan': ('tile.stained_glass_pane.cyan.name', 'Cyan Stained Glass Pane'),
 'stained_glass_pane_gray': ('tile.stained_glass_pane.gray.name', 'Gray Stained Glass Pane'),
 'stained_glass_pane_green': ('tile.stained_glass_pane.green.name', 'Green Stained Glass Pane'),
 'stained_glass_pane_light_blue': ('tile.stained_glass_pane.light_blue.name', 'Light Blue Stained Glass Pane'),
 'stained_glass_pane_lime': ('tile.stained_glass_pane.lime.name', 'Lime Stained Glass Pane'),
 'stained_glass_pane_magenta': ('tile.stained_glass_pane.magenta.name', 'Magenta Stained Glass Pane'),
 'stained_glass_pane_orange': ('tile.stained_glass_pane.orange.name', 'Orange Stained Glass Pane'),
 'stained_glass_pane_pink': ('tile.stained_glass_pane.pink.name', 'Pink Stained Glass Pane'),
 'stained_glass_pane_purple': ('tile.stained_glass_pane.purple.name', 'Purple Stained Glass Pane'),
 'stained_glass_pane_red': ('tile.stained_glass_pane.red.name', 'Red Stained Glass Pane'),
 'stained_glass_pane_silver': ('tile.stained_glass_pane.silver.name', 'Light Gray Stained Glass Pane'),
 'stained_glass_pane_white': ('tile.stained_glass_pane.white.name', 'White Stained Glass Pane'),
 'stained_glass_pane_yellow': ('tile.stained_glass_pane.yellow.name', 'Yellow Stained Glass Pane'),
 'stained_glass_pink': ('tile.stained_glass.pink.name', 'Pink Stained Glass'),
 'stained_glass_purple': ('tile.stained_glass.purple.name', 'Purple Stained Glass'),
 'stained_glass_red': ('tile.stained_glass.red.name', 'Red Stained Glass'),
 'stained_glass_silver': ('tile.stained_glass.silver.name', 'Light Gray Stained Glass'),
 'stained_glass_white': ('tile.stained_glass.white.name', 'White Stained Glass'),
 'stained_glass_yellow': ('tile.stained_glass.yellow.name', 'Yellow Stained Glass'),
 'stained_hardened_clay': ('tile.stained_hardened_clay.name', 'Terracotta'),
 'stained_hardened_clay_black': ('tile.stained_hardened_clay.black.name', 'Black Terracotta'),
 'stained_hardened_clay_blue': ('tile.stained_hardened_clay.blue.name', 'Blue Terracotta'),
 'stained_hardened_clay_brown': ('tile.stained_hardened_clay.brown.name', 'Brown Terracotta'),
 'stained_hardened_clay_cyan': ('tile.stained_hardened_clay.cyan.name', 'Cyan Terracotta'),
 'stained_hardened_clay_gray': ('tile.stained_hardened_clay.gray.name', 'Gray Terracotta'),
 'stained_hardened_clay_green': ('tile.stained_hardened_clay.green.name', 'Green Terracotta'),
 'stained_hardened_clay_light_blue': ('tile.stained_hardened_clay.lightBlue.name', 'Light Blue Terracotta'),
 'stained_hardened_clay_lime': ('tile.stained_hardened_clay.lime.name', 'Lime Terracotta'),
 'stained_hardened_clay_magenta': ('tile.stained_hardened_clay.magenta.name', 'Magenta Terracotta'),
 'stained_hardened_clay_orange': ('tile.stained_hardened_clay.orange.name', 'Orange Terracotta'),
 'stained_hardened_clay_pink': ('tile.stained_hardened_clay.pink.name', 'Pink Terracotta'),
 'stained_hardened_clay_purple': ('tile.stained_hardened_clay.purple.name', 'Purple Terracotta'),
 'stained_hardened_clay_red': ('tile.stained_hardened_clay.red.name', 'Red Terracotta'),
 'stained_hardened_clay_silver': ('tile.stained_hardened_clay.silver.name', 'Light Gray Terracotta'),
 'stained_hardened_clay_white': ('tile.stained_hardened_clay.white.name', 'White Terracotta'),
 'stained_hardened_clay_yellow': ('tile.stained_hardened_clay.yellow.name', 'Yellow Terracotta'),
 'standing_banner': ('tile.standing_banner.name', 'Banner'),
 'standing_banner_black': ('tile.standing_banner.black.name', 'Black Banner'),
 'standing_banner_blue': ('tile.standing_banner.blue.name', 'Blue Banner'),
 'standing_banner_brown': ('tile.standing_banner.brown.name', 'Brown Banner'),
 'standing_banner_cyan': ('tile.standing_banner.cyan.name', 'Cyan Banner'),
 'standing_banner_gray': ('tile.standing_banner.gray.name', 'Gray Banner'),
 'standing_banner_green': ('tile.standing_banner.green.name', 'Green Banner'),
 'standing_banner_light_blue': ('tile.standing_banner.lightBlue.name', 'Light Blue Banner'),
 'standing_banner_lime': ('tile.standing_banner.lime.name', 'Lime Banner'),
 'standing_banner_magenta': ('tile.standing_banner.magenta.name', 'Magenta Banner'),
 'standing_banner_orange': ('tile.standing_banner.orange.name', 'Orange Banner'),
 'standing_banner_pink': ('tile.standing_banner.pink.name', 'Pink Banner'),
 'standing_banner_purple': ('tile.standing_banner.purple.name', 'Purple Banner'),
 'standing_banner_red': ('tile.standing_banner.red.name', 'Red Banner'),
 'standing_banner_silver': ('tile.standing_banner.silver.name', 'Light Gray Banner'),
 'standing_banner_white': ('tile.standing_banner.white.name', 'Banner'),
 'standing_banner_yellow': ('tile.standing_banner.yellow.name', 'Yellow Banner'),
 'standing_sign': ('tile.standing_sign.name', 'Sign'),
 'steak': ('item.steak.name', 'Steak'),
 'stick': ('item.stick.name', 'Stick'),
 'sticky_piston': ('tile.sticky_piston.name', 'Sticky Piston'),
 'sticky_piston_arm_collision': ('tile.sticky_piston_arm_collision.name', 'Sticky Piston Arm Collision'),
 'stone_andesite': ('tile.stone.andesite.name', 'Andesite'),
 'stone_andesite_smooth': ('tile.stone.andesiteSmooth.name', 'Polished Andesite'),
 'stone_axe': ('item.stone_axe.name', 'Stone Axe'),
 'stone_brick_stairs': ('tile.stone_brick_stairs.name', 'Stone Brick Stairs'),
 'stone_button': ('tile.stone_button.name', 'Stone Button'),
 'stone_diorite': ('tile.stone.diorite.name', 'Diorite'),
 'stone_diorite_smooth': ('tile.stone.dioriteSmooth.name', 'Polished Diorite'),
 'stone_granite': ('tile.stone.granite.name', 'Granite'),
 'stone_granite_smooth': ('tile.stone.graniteSmooth.name', 'Polished Granite'),
 'stone_hoe': ('item.stone_hoe.name', 'Stone Hoe'),
 'stone_pickaxe': ('item.stone_pickaxe.name', 'Stone Pickaxe'),
 'stone_pressure_plate': ('tile.stone_pressure_plate.name', 'Stone Pressure Plate'),
 'stone_shovel': ('item.stone_shovel.name', 'Stone Shovel'),
 'stone_slab': ('tile.stone_slab.name', 'Stone Slab'),
 'stone_slab2_mossy_cobblestone': ('tile.stone_slab2.mossy_cobblestone.name', 'Mossy Cobblestone Slab'),
 'stone_slab2_prismarine_bricks': ('tile.stone_slab2.prismarine.bricks.name', 'Prismarine Brick Slab'),
 'stone_slab2_prismarine_dark': ('tile.stone_slab2.prismarine.dark.name', 'Dark Prismarine Slab'),
 'stone_slab2_prismarine_rough': ('tile.stone_slab2.prismarine.rough.name', 'Prismarine Slab'),
 'stone_slab2_purpur': ('tile.stone_slab2.purpur.name', 'Purpur Slab'),
 'stone_slab2_red_nether_brick': ('tile.stone_slab2.red_nether_brick.name', 'Red Nether Brick Slab'),
 'stone_slab2_red_sandstone': ('tile.stone_slab2.red_sandstone.name', 'Red Sandstone Slab'),
 'stone_slab2_sandstone_smooth': ('tile.stone_slab2.sandstone.smooth.name', 'Smooth Sandstone Slab'),
 'stone_slab3_andesite': ('tile.stone_slab3.andesite.name', 'Andesite Slab'),
 'stone_slab3_andesite_smooth': ('tile.stone_slab3.andesite.smooth.name', 'Polished Andesite Slab'),
 'stone_slab3_diorite': ('tile.stone_slab3.diorite.name', 'Diorite Slab'),
 'stone_slab3_diorite_smooth': ('tile.stone_slab3.diorite.smooth.name', 'Polished Diorite Slab'),
 'stone_slab3_end_brick': ('tile.stone_slab3.end_brick.name', 'End Stone Brick Slab'),
 'stone_slab3_granite': ('tile.stone_slab3.granite.name', 'Granite Slab'),
 'stone_slab3_granite_smooth': ('tile.stone_slab3.granite.smooth.name', 'Polished Granite Slab'),
 'stone_slab3_red_sandstone_smooth': ('tile.stone_slab3.red_sandstone.smooth.name', 'Smooth Red Sandstone Slab'),
 'stone_slab4_cut_red_sandstone': ('tile.stone_slab4.cut_red_sandstone.name', 'Cut Red Sandstone Slab'),
 'stone_slab4_cut_sandstone': ('tile.stone_slab4.cut_sandstone.name', 'Cut Sandstone Slab'),
 'stone_slab4_mossy_stone_brick': ('tile.stone_slab4.mossy_stone_brick.name', 'Mossy Stone Brick Slab'),
 'stone_slab4_smooth_quartz': ('tile.stone_slab4.smooth_quartz.name', 'Smooth Quartz Slab'),
 'stone_slab4_stone': ('tile.stone_slab4.stone.name', 'Stone Slab'),
 'stone_slab_brick': ('tile.stone_slab.brick.name', 'Brick Slab'),
 'stone_slab_cobble': ('tile.stone_slab.cobble.name', 'Cobblestone Slab'),
 'stone_slab_nether_brick': ('tile.stone_slab.nether_brick.name', 'Nether Brick Slab'),
 'stone_slab_quartz': ('tile.stone_slab.quartz.name', 'Quartz Slab'),
 'stone_slab_sand': ('tile.stone_slab.sand.name', 'Sandstone Slab'),
 'stone_slab_smooth_stone_brick': ('tile.stone_slab.smoothStoneBrick.name', 'Stone Brick Slab'),
 'stone_slab_stone': ('tile.stone_slab.stone.name', 'Smooth Stone Slab'),
 'stone_slab_wood': ('tile.stone_slab.wood.name', 'Wooden Slab'),
 'stone_spear': ('item.stone_spear.name', 'Stone Spear'),
 'stone_stairs': ('tile.stone_stairs.name', 'Cobblestone Stairs'),
 'stone_stone': ('tile.stone.stone.name', 'Stone'),
 'stone_sword': ('item.stone_sword.name', 'Stone Sword'),
 'stonebrick': ('tile.stonebrick.name', 'Stone Bricks'),
 'stonebrick_chiseled': ('tile.stonebrick.chiseled.name', 'Chiseled Stone Bricks'),
 'stonebrick_cracked': ('tile.stonebrick.cracked.name', 'Cracked Stone Bricks'),
 'stonebrick_default': ('tile.stonebrick.default.name', 'Stone Bricks'),
 'stonebrick_mossy': ('tile.stonebrick.mossy.name', 'Mossy Stone Bricks'),
 'stonebrick_smooth': ('tile.stonebrick.smooth.name', 'Smooth Stone Bricks'),
 'stonecutter': ('tile.stonecutter.name', 'Stonecutter'),
 'stonecutter_block': ('tile.stonecutter_block.name', 'Stonecutter'),
 'string': ('item.string.name', 'String'),
 'stripped_acacia_log': ('tile.stripped_acacia_log.name', 'Stripped Acacia Log'),
 'stripped_bamboo_block': ('tile.stripped_bamboo_block.name', 'Block of Stripped Bamboo'),
 'stripped_birch_log': ('tile.stripped_birch_log.name', 'Stripped Birch Log'),
 'stripped_cherry_log': ('tile.stripped_cherry_log.name', 'Stripped Cherry Log'),
 'stripped_cherry_wood': ('tile.stripped_cherry_wood.name', 'Stripped Cherry Wood'),
 'stripped_crimson_hyphae': ('tile.stripped_crimson_hyphae.name', 'Stripped Crimson Hyphae'),
 'stripped_crimson_stem': ('tile.stripped_crimson_stem.name', 'Stripped Crimson Stem'),
 'stripped_dark_oak_log': ('tile.stripped_dark_oak_log.name', 'Stripped Dark Oak Log'),
 'stripped_jungle_log': ('tile.stripped_jungle_log.name', 'Stripped Jungle Log'),
 'stripped_mangrove_log': ('tile.stripped_mangrove_log.name', 'Stripped Mangrove Log'),
 'stripped_mangrove_wood': ('tile.stripped_mangrove_wood.name', 'Stripped Mangrove Wood'),
 'stripped_oak_log': ('tile.stripped_oak_log.name', 'Stripped Oak Log'),
 'stripped_pale_oak_log': ('tile.stripped_pale_oak_log.name', 'Stripped Pale Oak Log'),
 'stripped_pale_oak_wood': ('tile.stripped_pale_oak_wood.name', 'Stripped Pale Oak Wood'),
 'stripped_spruce_log': ('tile.stripped_spruce_log.name', 'Stripped Spruce Log'),
 'stripped_warped_hyphae': ('tile.stripped_warped_hyphae.name', 'Stripped Warped Hyphae'),
 'stripped_warped_stem': ('tile.stripped_warped_stem.name', 'Stripped Warped Stem'),
 'structure_block': ('tile.structure_block.name', 'Structure Block'),
 'structure_void': ('tile.structure_void.name', 'Structure Void'),
 'sugar': ('item.sugar.name', 'Sugar'),
 'suspicious_gravel': ('tile.suspicious_gravel.name', 'Suspicious Gravel'),
 'suspicious_sand': ('tile.suspicious_sand.name', 'Suspicious Sand'),
 'suspicious_stew': ('item.suspicious_stew.name', 'Suspicious Stew'),
 'sweet_berries': ('item.sweet_berries.name', 'Sweet Berries'),
 'sweet_berry_bush': ('tile.sweet_berry_bush.name', 'Sweet Berry Bush'),
 'tall_dry_grass': ('tile.tall_dry_grass.name', 'Tall Dry Grass'),
 'tallgrass': ('tile.tallgrass.name', 'Short Grass'),
 'tallgrass_fern': ('tile.tallgrass.fern.name', 'Fern'),
 'tallgrass_grass': ('tile.tallgrass.grass.name', 'Short Grass'),
 'tallgrass_shrub': ('tile.tallgrass.shrub.name', 'Shrub'),
 'target': ('tile.target.name', 'Target'),
 'tide_armor_trim_smithing_template': ('item.tide_armor_trim_smithing_template.name', 'Tide Armor Trim'),
 'tinted_glass': ('tile.tinted_glass.name', 'Tinted Glass'),
 'tipped_arrow': ('item.tipped_arrow.name', 'Tipped Arrow'),
 'tnt': ('tile.tnt.name', 'TNT'),
 'tnt_minecart': ('item.tnt_minecart.name', 'Minecart with TNT'),
 'torch': ('tile.torch.name', 'Torch'),
 'torchflower': ('tile.torchflower.name', 'Torchflower'),
 'torchflower_crop': ('tile.torchflower_crop.name', 'Torchflower Crop'),
 'torchflower_seeds': ('item.torchflower_seeds.name', 'Torchflower Seeds'),
 'totem': ('item.totem.name', 'Totem of Undying'),
 'trapdoor': ('tile.trapdoor.name', 'Oak Trapdoor'),
 'trapped_chest': ('tile.trapped_chest.name', 'Trapped Chest'),
 'trial_key': ('item.trial_key.name', 'Trial Key'),
 'trial_spawner': ('tile.trial_spawner.name', 'Trial Spawner'),
 'trident': ('item.trident.name', 'Trident'),
 'trip_wire': ('tile.tripWire.name', 'Tripwire'),
 'tripwire_hook': ('tile.tripwire_hook.name', 'Tripwire Hook'),
 'tropical_body_betty_multi': ('item.tropicalBodyBettyMulti.name', '%1$s-%2$s Betty'),
 'tropical_body_betty_single': ('item.tropicalBodyBettySingle.name', '%1$s Betty'),
 'tropical_body_blockfish_multi': ('item.tropicalBodyBlockfishMulti.name', '%1$s-%2$s Blockfish'),
 'tropical_body_blockfish_single': ('item.tropicalBodyBlockfishSingle.name', '%1$s Blockfish'),
 'tropical_body_brinely_multi': ('item.tropicalBodyBrinelyMulti.name', '%1$s-%2$s Brinely'),
 'tropical_body_brinely_single': ('item.tropicalBodyBrinelySingle.name', '%1$s Brinely'),
 'tropical_body_clayfish_multi': ('item.tropicalBodyClayfishMulti.name', '%1$s-%2$s Clayfish'),
 'tropical_body_clayfish_single': ('item.tropicalBodyClayfishSingle.name', '%1$s Clayfish'),
 'tropical_body_dasher_multi': ('item.tropicalBodyDasherMulti.name', '%1$s-%2$s Dasher'),
 'tropical_body_dasher_single': ('item.tropicalBodyDasherSingle.name', '%1$s Dasher'),
 'tropical_body_flopper_multi': ('item.tropicalBodyFlopperMulti.name', '%1$s-%2$s Flopper'),
 'tropical_body_flopper_single': ('item.tropicalBodyFlopperSingle.name', '%1$s Flopper'),
 'tropical_body_glitter_multi': ('item.tropicalBodyGlitterMulti.name', '%1$s-%2$s Glitter'),
 'tropical_body_glitter_single': ('item.tropicalBodyGlitterSingle.name', '%1$s Glitter'),
 'tropical_body_kob_multi': ('item.tropicalBodyKobMulti.name', '%1$s-%2$s Kob'),
 'tropical_body_kob_single': ('item.tropicalBodyKobSingle.name', '%1$s Kob'),
 'tropical_body_snooper_multi': ('item.tropicalBodySnooperMulti.name', '%1$s-%2$s Snooper'),
 'tropical_body_snooper_single': ('item.tropicalBodySnooperSingle.name', '%1$s Snooper'),
 'tropical_body_spotty_multi': ('item.tropicalBodySpottyMulti.name', '%1$s-%2$s Spotty'),
 'tropical_body_spotty_single': ('item.tropicalBodySpottySingle.name', '%1$s Spotty'),
 'tropical_body_stripey_multi': ('item.tropicalBodyStripeyMulti.name', '%1$s-%2$s Stripey'),
 'tropical_body_stripey_single': ('item.tropicalBodyStripeySingle.name', '%1$s Stripey'),
 'tropical_body_sunstreak_multi': ('item.tropicalBodySunstreakMulti.name', '%1$s-%2$s SunStreak'),
 'tropical_body_sunstreak_single': ('item.tropicalBodySunstreakSingle.name', '%1$s SunStreak'),
 'tropical_color_blue': ('item.tropicalColorBlue.name', 'Blue'),
 'tropical_color_brown': ('item.tropicalColorBrown.name', 'Brown'),
 'tropical_color_gray': ('item.tropicalColorGray.name', 'Gray'),
 'tropical_color_green': ('item.tropicalColorGreen.name', 'Green'),
 'tropical_color_lime': ('item.tropicalColorLime.name', 'Lime'),
 'tropical_color_magenta': ('item.tropicalColorMagenta.name', 'Magenta'),
 'tropical_color_orange': ('item.tropicalColorOrange.name', 'Orange'),
 'tropical_color_plum': ('item.tropicalColorPlum.name', 'Plum'),
 'tropical_color_red': ('item.tropicalColorRed.name', 'Red'),
 'tropical_color_rose': ('item.tropicalColorRose.name', 'Rose'),
 'tropical_color_silver': ('item.tropicalColorSilver.name', 'Silver'),
 'tropical_color_sky': ('item.tropicalColorSky.name', 'Sky'),
 'tropical_color_teal': ('item.tropicalColorTeal.name', 'Teal'),
 'tropical_color_white': ('item.tropicalColorWhite.name', 'White'),
 'tropical_color_yellow': ('item.tropicalColorYellow.name', 'Yellow'),
 'tropical_school_anemone': ('item.tropicalSchoolAnemone.name', 'Anemone'),
 'tropical_school_black_tang': ('item.tropicalSchoolBlackTang.name', 'Black Tang'),
 'tropical_school_blue_dory': ('item.tropicalSchoolBlueDory.name', 'Blue Dory'),
 'tropical_school_butterfly_fish': ('item.tropicalSchoolButterflyFish.name', 'Butterfly Fish'),
 'tropical_school_cichlid': ('item.tropicalSchoolCichlid.name', 'Chichlid'),
 'tropical_school_clownfish': ('item.tropicalSchoolClownfish.name', 'Clownfish'),
 'tropical_school_cotton_candy_betta': ('item.tropicalSchoolCottonCandyBetta.name', 'Cotton Candy Betta'),
 'tropical_school_dottyback': ('item.tropicalSchoolDottyback.name', 'Dottyback'),
 'tropical_school_emperor_red_snapper': ('item.tropicalSchoolEmperorRedSnapper.name', 'Emperor Red Snapper'),
 'tropical_school_goatfish': ('item.tropicalSchoolGoatfish.name', 'Goatfish'),
 'tropical_school_moorish_idol': ('item.tropicalSchoolMoorishIdol.name', 'Moorish Idol'),
 'tropical_school_ornate_butterfly': ('item.tropicalSchoolOrnateButterfly.name', 'Ornate Butterfly'),
 'tropical_school_parrotfish': ('item.tropicalSchoolParrotfish.name', 'Parrotfish'),
 'tropical_school_queen_angel_fish': ('item.tropicalSchoolQueenAngelFish.name', 'Queen Angel Fish'),
 'tropical_school_red_cichlid': ('item.tropicalSchoolRedCichlid.name', 'Red Cichlid'),
 'tropical_school_red_lipped_blenny': ('item.tropicalSchoolRedLippedBlenny.name', 'Red Lipped Blenny'),
 'tropical_school_red_snapper': ('item.tropicalSchoolRedSnapper.name', 'Red Snapper'),
 'tropical_school_threadfin': ('item.tropicalSchoolThreadfin.name', 'Threadfin'),
 'tropical_school_tomato_clown': ('item.tropicalSchoolTomatoClown.name', 'Tomato Clown'),
 'tropical_school_triggerfish': ('item.tropicalSchoolTriggerfish.name', 'Triggerfish'),
 'tropical_school_yellow_tang': ('item.tropicalSchoolYellowTang.name', 'Yellow Tang'),
 'tropical_school_yellowtail_parrot': ('item.tropicalSchoolYellowtailParrot.name', 'Yellowtail Parrot'),
 'tube_coral_wall_fan': ('tile.tube_coral_wall_fan.name', 'Tube Coral Wall Fan'),
 'tuff': ('tile.tuff.name', 'Tuff'),
 'tuff_brick_double_slab': ('tile.tuff_brick_double_slab.name', 'Tuff Brick Double Slab'),
 'tuff_brick_slab': ('tile.tuff_brick_slab.name', 'Tuff Brick Slab'),
 'tuff_brick_stairs': ('tile.tuff_brick_stairs.name', 'Tuff Brick Stairs'),
 'tuff_brick_wall': ('tile.tuff_brick_wall.name', 'Tuff Brick Wall'),
 'tuff_bricks': ('tile.tuff_bricks.name', 'Tuff Bricks'),
 'tuff_double_slab': ('tile.tuff_double_slab.name', 'Tuff Double Slab'),
 'tuff_slab': ('tile.tuff_slab.name', 'Tuff Slab'),
 'tuff_stairs': ('tile.tuff_stairs.name', 'Tuff Stairs'),
 'tuff_wall': ('tile.tuff_wall.name', 'Tuff Wall'),
 'turtle_egg': ('tile.turtle_egg.name', 'Turtle Egg'),
 'turtle_helmet': ('item.turtle_helmet.name', 'Turtle Shell'),
 'turtle_shell_piece': ('item.turtle_shell_piece.name', 'Turtle Scute'),
 'twisting_vines': ('tile.twisting_vines.name', 'Twisting Vines'),
 'unknown': ('tile.unknown.name', 'Unknown'),
 'unlit_redstone_torch': ('tile.unlit_redstone_torch.name', 'Redstone Torch'),
 'unpowered_comparator': ('tile.unpowered_comparator.name', 'Unpowered Comparator'),
 'unpowered_repeater': ('tile.unpowered_repeater.name', 'Unpowered Repeater'),
 'vault': ('tile.vault.name', 'Vault'),
 'verdant_froglight': ('tile.verdant_froglight.name', 'Verdant Froglight'),
 'vex_armor_trim_smithing_template': ('item.vex_armor_trim_smithing_template.name', 'Vex Armor Trim'),
 'vine': ('tile.vine.name', 'Vines'),
 'wall_banner': ('tile.wall_banner.name', 'Wall Banner'),
 'wall_sign': ('tile.wall_sign.name', 'Wall Sign'),
 'ward_armor_trim_smithing_template': ('item.ward_armor_trim_smithing_template.name', 'Ward Armor Trim'),
 'warped_button': ('tile.warped_button.name', 'Warped Button'),
 'warped_door': ('item.warped_door.name', 'Warped Door'),
 'warped_double_slab': ('tile.warped_double_slab.name', 'Warped Slab'),
 'warped_fence': ('tile.warped_fence.name', 'Warped Fence'),
 'warped_fence_gate': ('tile.warped_fence_gate.name', 'Warped Fence Gate'),
 'warped_fungus': ('tile.warped_fungus.name', 'Warped Fungus'),
 'warped_fungus_on_a_stick': ('item.warped_fungus_on_a_stick.name', 'Warped Fungus on a Stick'),
 'warped_hanging_sign': ('item.warped_hanging_sign.name', 'Warped Hanging Sign'),
 'warped_hyphae': ('tile.warped_hyphae.name', 'Warped Hyphae'),
 'warped_nylium': ('tile.warped_nylium.name', 'Warped Nylium'),
 'warped_planks': ('tile.warped_planks.name', 'Warped Planks'),
 'warped_pressure_plate': ('tile.warped_pressure_plate.name', 'Warped Pressure Plate'),
 'warped_roots_warped_roots': ('tile.warped_roots.warpedRoots.name', 'Warped Roots'),
 'warped_shelf': ('tile.warped_shelf.name', 'Warped Shelf'),
 'warped_sign': ('item.warped_sign.name', 'Warped Sign'),
 'warped_slab': ('tile.warped_slab.name', 'Warped Slab'),
 'warped_stairs': ('tile.warped_stairs.name', 'Warped Stairs'),
 'warped_standing_sign': ('tile.warped_standing_sign.name', 'Warped Sign'),
 'warped_stem': ('tile.warped_stem.name', 'Warped Stem'),
 'warped_trapdoor': ('tile.warped_trapdoor.name', 'Warped Trapdoor'),
 'warped_wall_sign': ('tile.warped_wall_sign.name', 'Warped Sign'),
 'warped_wart_block': ('tile.warped_wart_block.name', 'Warped Wart Block'),
 'water': ('tile.water.name', 'Water'),
 'waterlily': ('tile.waterlily.name', 'Lily Pad'),
 'waxed_chiseled_copper': ('tile.waxed_chiseled_copper.name', 'Waxed Chiseled Copper'),
 'waxed_copper': ('tile.waxed_copper.name', 'Waxed Block of Copper'),
 'waxed_copper_bars': ('tile.waxed_copper_bars.name', 'Waxed Copper Bars'),
 'waxed_copper_bulb': ('tile.waxed_copper_bulb.name', 'Waxed Copper Bulb'),
 'waxed_copper_chain': ('tile.waxed_copper_chain.name', 'Waxed Copper Chain'),
 'waxed_copper_chest': ('tile.waxed_copper_chest.name', 'Waxed Copper Chest'),
 'waxed_copper_door': ('item.waxed_copper_door.name', 'Waxed Copper Door'),
 'waxed_copper_golem_statue': ('tile.waxed_copper_golem_statue.name', 'Waxed Copper Golem Statue'),
 'waxed_copper_grate': ('tile.waxed_copper_grate.name', 'Waxed Copper Grate'),
 'waxed_copper_lantern': ('tile.waxed_copper_lantern.name', 'Waxed Copper Lantern'),
 'waxed_copper_trapdoor': ('tile.waxed_copper_trapdoor.name', 'Waxed Copper Trapdoor'),
 'waxed_cut_copper': ('tile.waxed_cut_copper.name', 'Waxed Cut Copper'),
 'waxed_cut_copper_slab': ('tile.waxed_cut_copper_slab.name', 'Waxed Cut Copper Slab'),
 'waxed_cut_copper_stairs': ('tile.waxed_cut_copper_stairs.name', 'Waxed Cut Copper Stairs'),
 'waxed_double_cut_copper_slab': ('tile.waxed_double_cut_copper_slab.name', 'Waxed Cut Copper Double Slab'),
 'waxed_exposed_chiseled_copper': ('tile.waxed_exposed_chiseled_copper.name', 'Waxed Exposed Chiseled Copper'),
 'waxed_exposed_copper': ('tile.waxed_exposed_copper.name', 'Waxed Exposed Copper'),
 'waxed_exposed_copper_bars': ('tile.waxed_exposed_copper_bars.name', 'Waxed Exposed Copper Bars'),
 'waxed_exposed_copper_bulb': ('tile.waxed_exposed_copper_bulb.name', 'Waxed Exposed Copper Bulb'),
 'waxed_exposed_copper_chain': ('tile.waxed_exposed_copper_chain.name', 'Waxed Exposed Copper Chain'),
 'waxed_exposed_copper_chest': ('tile.waxed_exposed_copper_chest.name', 'Waxed Exposed Copper Chest'),
 'waxed_exposed_copper_door': ('item.waxed_exposed_copper_door.name', 'Waxed Exposed Copper Door'),
 'waxed_exposed_copper_golem_statue': ('tile.waxed_exposed_copper_golem_statue.name',
                                       'Waxed Exposed Copper Golem Statue'),
 'waxed_exposed_copper_grate': ('tile.waxed_exposed_copper_grate.name', 'Waxed Exposed Copper Grate'),
 'waxed_exposed_copper_lantern': ('tile.waxed_exposed_copper_lantern.name', 'Waxed Exposed Copper Lantern'),
 'waxed_exposed_copper_trapdoor': ('tile.waxed_exposed_copper_trapdoor.name', 'Waxed Exposed Copper Trapdoor'),
 'waxed_exposed_cut_copper': ('tile.waxed_exposed_cut_copper.name', 'Waxed Exposed Cut Copper'),
 'waxed_exposed_cut_copper_slab': ('tile.waxed_exposed_cut_copper_slab.name', 'Waxed Exposed Cut Copper Slab'),
 'waxed_exposed_cut_copper_stairs': ('tile.waxed_exposed_cut_copper_stairs.name', 'Waxed Exposed Cut Copper Stairs'),
 'waxed_exposed_double_cut_copper_slab': ('tile.waxed_exposed_double_cut_copper_slab.name',
                                          'Waxed Exposed Cut Copper Double Slab'),
 'waxed_exposed_lightning_rod': ('tile.waxed_exposed_lightning_rod.name', 'Waxed Exposed Lightning Rod'),
 'waxed_lightning_rod': ('tile.waxed_lightning_rod.name', 'Waxed Lightning Rod'),
 'waxed_oxidized_chiseled_copper': ('tile.waxed_oxidized_chiseled_copper.name', 'Waxed Oxidized Chiseled Copper'),
 'waxed_oxidized_copper': ('tile.waxed_oxidized_copper.name', 'Waxed Oxidized Copper'),
 'waxed_oxidized_copper_bars': ('tile.waxed_oxidized_copper_bars.name', 'Waxed Oxidized Copper Bars'),
 'waxed_oxidized_copper_bulb': ('tile.waxed_oxidized_copper_bulb.name', 'Waxed Oxidized Copper Bulb'),
 'waxed_oxidized_copper_chain': ('tile.waxed_oxidized_copper_chain.name', 'Waxed Oxidized Copper Chain'),
 'waxed_oxidized_copper_chest': ('tile.waxed_oxidized_copper_chest.name', 'Waxed Oxidized Copper Chest'),
 'waxed_oxidized_copper_door': ('item.waxed_oxidized_copper_door.name', 'Waxed Oxidized Copper Door'),
 'waxed_oxidized_copper_golem_statue': ('tile.waxed_oxidized_copper_golem_statue.name',
                                        'Waxed Oxidized Copper Golem Statue'),
 'waxed_oxidized_copper_grate': ('tile.waxed_oxidized_copper_grate.name', 'Waxed Oxidized Copper Grate'),
 'waxed_oxidized_copper_lantern': ('tile.waxed_oxidized_copper_lantern.name', 'Waxed Oxidized Copper Lantern'),
 'waxed_oxidized_copper_trapdoor': ('tile.waxed_oxidized_copper_trapdoor.name', 'Waxed Oxidized Copper Trapdoor'),
 'waxed_oxidized_cut_copper': ('tile.waxed_oxidized_cut_copper.name', 'Waxed Oxidized Cut Copper'),
 'waxed_oxidized_cut_copper_slab': ('tile.waxed_oxidized_cut_copper_slab.name', 'Waxed Oxidized Cut Copper Slab'),
 'waxed_oxidized_cut_copper_stairs': ('tile.waxed_oxidized_cut_copper_stairs.name',
                                      'Waxed Oxidized Cut Copper Stairs'),
 'waxed_oxidized_double_cut_copper_slab': ('tile.waxed_oxidized_double_cut_copper_slab.name',
                                           'Waxed Oxidized Cut Copper Double Slab'),
 'waxed_oxidized_lightning_rod': ('tile.waxed_oxidized_lightning_rod.name', 'Waxed Oxidized Lightning Rod'),
 'waxed_weathered_chiseled_copper': ('tile.waxed_weathered_chiseled_copper.name', 'Waxed Weathered Chiseled Copper'),
 'waxed_weathered_copper': ('tile.waxed_weathered_copper.name', 'Waxed Weathered Copper'),
 'waxed_weathered_copper_bars': ('tile.waxed_weathered_copper_bars.name', 'Waxed Weathered Copper Bars'),
 'waxed_weathered_copper_bulb': ('tile.waxed_weathered_copper_bulb.name', 'Waxed Weathered Copper Bulb'),
 'waxed_weathered_copper_chain': ('tile.waxed_weathered_copper_chain.name', 'Waxed Weathered Copper Chain'),
 'waxed_weathered_copper_chest': ('tile.waxed_weathered_copper_chest.name', 'Waxed Weathered Copper Chest'),
 'waxed_weathered_copper_door': ('item.waxed_weathered_copper_door.name', 'Waxed Weathered Copper Door'),
 'waxed_weathered_copper_golem_statue': ('tile.waxed_weathered_copper_golem_statue.name',
                                         'Waxed Weathered Copper Golem Statue'),
 'waxed_weathered_copper_grate': ('tile.waxed_weathered_copper_grate.name', 'Waxed Weathered Copper Grate'),
 'waxed_weathered_copper_lantern': ('tile.waxed_weathered_copper_lantern.name', 'Waxed Weathered Copper Lantern'),
 'waxed_weathered_copper_trapdoor': ('tile.waxed_weathered_copper_trapdoor.name', 'Waxed Weathered Copper Trapdoor'),
 'waxed_weathered_cut_copper': ('tile.waxed_weathered_cut_copper.name', 'Waxed Weathered Cut Copper'),
 'waxed_weathered_cut_copper_slab': ('tile.waxed_weathered_cut_copper_slab.name', 'Waxed Weathered Cut Copper Slab'),
 'waxed_weathered_cut_copper_stairs': ('tile.waxed_weathered_cut_copper_stairs.name',
                                       'Waxed Weathered Cut Copper Stairs'),
 'waxed_weathered_double_cut_copper_slab': ('tile.waxed_weathered_double_cut_copper_slab.name',
                                            'Waxed Weathered Cut Copper Double Slab'),
 'waxed_weathered_lightning_rod': ('tile.waxed_weathered_lightning_rod.name', 'Waxed Weathered Lightning Rod'),
 'wayfinder_armor_trim_smithing_template': ('item.wayfinder_armor_trim_smithing_template.name',
                                            'Wayfinder Armor Trim'),
 'weathered_chiseled_copper': ('tile.weathered_chiseled_copper.name', 'Weathered Chiseled Copper'),
 'weathered_copper': ('tile.weathered_copper.name', 'Weathered Copper'),
 'weathered_copper_bars': ('tile.weathered_copper_bars.name', 'Weathered Copper Bars'),
 'weathered_copper_bulb': ('tile.weathered_copper_bulb.name', 'Weathered Copper Bulb'),
 'weathered_copper_chain': ('tile.weathered_copper_chain.name', 'Weathered Copper Chain'),
 'weathered_copper_chest': ('tile.weathered_copper_chest.name', 'Weathered Copper Chest'),
 'weathered_copper_door': ('item.weathered_copper_door.name', 'Weathered Copper Door'),
 'weathered_copper_golem_statue': ('tile.weathered_copper_golem_statue.name', 'Weathered Copper Golem Statue'),
 'weathered_copper_grate': ('tile.weathered_copper_grate.name', 'Weathered Copper Grate'),
 'weathered_copper_lantern': ('tile.weathered_copper_lantern.name', 'Weathered Copper Lantern'),
 'weathered_copper_trapdoor': ('tile.weathered_copper_trapdoor.name', 'Weathered Copper Trapdoor'),
 'weathered_cut_copper': ('tile.weathered_cut_copper.name', 'Weathered Cut Copper'),
 'weathered_cut_copper_slab': ('tile.weathered_cut_copper_slab.name', 'Weathered Cut Copper Slab'),
 'weathered_cut_copper_stairs': ('tile.weathered_cut_copper_stairs.name', 'Weathered Cut Copper Stairs'),
 'weathered_double_cut_copper_slab': ('tile.weathered_double_cut_copper_slab.name',
                                      'Weathered Cut Copper Double Slab'),
 'weathered_lightning_rod': ('tile.weathered_lightning_rod.name', 'Weathered Lightning Rod'),
 'web': ('tile.web.name', 'Cobweb'),
 'weeping_vines': ('tile.weeping_vines.name', 'Weeping Vines'),
 'wheat': ('item.wheat.name', 'Wheat'),
 'wheat_seeds': ('item.wheat_seeds.name', 'Wheat Seeds'),
 'white_candle': ('tile.white_candle.name', 'White Candle'),
 'white_candle_cake': ('tile.white_candle_cake.name', 'Cake with White Candle'),
 'white_harness': ('item.white_harness.name', 'White Harness'),
 'wild_armor_trim_smithing_template': ('item.wild_armor_trim_smithing_template.name', 'Wild Armor Trim'),
 'wildflowers': ('tile.wildflowers.name', 'Wildflowers'),
 'wind_charge': ('item.wind_charge.name', 'Wind Charge'),
 'wither_rose': ('tile.wither_rose.name', 'Wither Rose'),
 'wolf_armor': ('item.wolf_armor.name', 'Wolf Armor'),
 'wood_acacia': ('tile.wood.acacia.name', 'Acacia Wood'),
 'wood_birch': ('tile.wood.birch.name', 'Birch Wood'),
 'wood_dark_oak': ('tile.wood.dark_oak.name', 'Dark Oak Wood'),
 'wood_jungle': ('tile.wood.jungle.name', 'Jungle Wood'),
 'wood_oak': ('tile.wood.oak.name', 'Oak Wood'),
 'wood_spruce': ('tile.wood.spruce.name', 'Spruce Wood'),
 'wood_stripped_acacia': ('tile.wood.stripped.acacia.name', 'Stripped Acacia Wood'),
 'wood_stripped_birch': ('tile.wood.stripped.birch.name', 'Stripped Birch Wood'),
 'wood_stripped_dark_oak': ('tile.wood.stripped.dark_oak.name', 'Stripped Dark Oak Wood'),
 'wood_stripped_jungle': ('tile.wood.stripped.jungle.name', 'Stripped Jungle Wood'),
 'wood_stripped_oak': ('tile.wood.stripped.oak.name', 'Stripped Oak Wood'),
 'wood_stripped_spruce': ('tile.wood.stripped.spruce.name', 'Stripped Spruce Wood'),
 'wooden_axe': ('item.wooden_axe.name', 'Wooden Axe'),
 'wooden_button': ('tile.wooden_button.name', 'Oak Button'),
 'wooden_door': ('item.wooden_door.name', 'Oak Door'),
 'wooden_hoe': ('item.wooden_hoe.name', 'Wooden Hoe'),
 'wooden_pickaxe': ('item.wooden_pickaxe.name', 'Wooden Pickaxe'),
 'wooden_pressure_plate': ('tile.wooden_pressure_plate.name', 'Oak Pressure Plate'),
 'wooden_shovel': ('item.wooden_shovel.name', 'Wooden Shovel'),
 'wooden_slab': ('tile.wooden_slab.name', 'Wood Slab'),
 'wooden_slab_acacia': ('tile.wooden_slab.acacia.name', 'Acacia Slab'),
 'wooden_slab_big_oak': ('tile.wooden_slab.big_oak.name', 'Dark Oak Slab'),
 'wooden_slab_birch': ('tile.wooden_slab.birch.name', 'Birch Slab'),
 'wooden_slab_jungle': ('tile.wooden_slab.jungle.name', 'Jungle Slab'),
 'wooden_slab_oak': ('tile.wooden_slab.oak.name', 'Oak Slab'),
 'wooden_slab_spruce': ('tile.wooden_slab.spruce.name', 'Spruce Slab'),
 'wooden_spear': ('item.wooden_spear.name', 'Wooden Spear'),
 'wooden_sword': ('item.wooden_sword.name', 'Wooden Sword'),
 'wool': ('tile.wool.name', 'Wool'),
 'wool_black': ('tile.wool.black.name', 'Black Wool'),
 'wool_blue': ('tile.wool.blue.name', 'Blue Wool'),
 'wool_brown': ('tile.wool.brown.name', 'Brown Wool'),
 'wool_cyan': ('tile.wool.cyan.name', 'Cyan Wool'),
 'wool_gray': ('tile.wool.gray.name', 'Gray Wool'),
 'wool_green': ('tile.wool.green.name', 'Green Wool'),
 'wool_light_blue': ('tile.wool.lightBlue.name', 'Light Blue Wool'),
 'wool_lime': ('tile.wool.lime.name', 'Lime Wool'),
 'wool_magenta': ('tile.wool.magenta.name', 'Magenta Wool'),
 'wool_orange': ('tile.wool.orange.name', 'Orange Wool'),
 'wool_pink': ('tile.wool.pink.name', 'Pink Wool'),
 'wool_purple': ('tile.wool.purple.name', 'Purple Wool'),
 'wool_red': ('tile.wool.red.name', 'Red Wool'),
 'wool_silver': ('tile.wool.silver.name', 'Light Gray Wool'),
 'wool_white': ('tile.wool.white.name', 'White Wool'),
 'wool_yellow': ('tile.wool.yellow.name', 'Yellow Wool'),
 'writable_book': ('item.writable_book.name', 'Book and Quill'),
 'written_book': ('item.written_book.name', 'Written Book'),
 'yellow_candle': ('tile.yellow_candle.name', 'Yellow Candle'),
 'yellow_candle_cake': ('tile.yellow_candle_cake.name', 'Cake with Yellow Candle'),
 'yellow_flower': ('tile.yellow_flower.name', 'Flower'),
 'yellow_flower_dandelion': ('tile.yellow_flower.dandelion.name', 'Dandelion'),
 'yellow_harness': ('item.yellow_harness.name', 'Yellow Harness')}

    DISPLAY_NAME_AUDIT_MANUAL_REVIEW = set()

    ABC_SORT_NAME_OVERRIDES = {
        "minecraft:cobweb": "cobweb",
        "minecraft:web": "cobweb",
        "minecraft:frame": "item_frame",
        "minecraft:glow_frame": "glow_item_frame",
        "minecraft:iron_chain": "iron_chain",
        "minecraft:wooden_door": "oak_door",
        "minecraft:hardened_clay": "terracotta",
        "minecraft:silver_glazed_terracotta": "light_gray_glazed_terracotta",
        "minecraft:melon_block": "melon",
        "minecraft:undyed_shulker_box": "shulker_box",
        "minecraft:normal_stone_slab": "stone_slab",
        "minecraft:normal_stone_double_slab": "stone_double_slab",
        "minecraft:fence_gate": "oak_fence_gate",
        "minecraft:trapdoor": "oak_trapdoor",
        "minecraft:string": "string",
        "minecraft:glow_berries": "glow_berries",
        "minecraft:lit_pumpkin": "jack_o_lantern",
        "minecraft:end_bricks": "end_stone_bricks",
        "minecraft:golden_rail": "powered_rail",
        "minecraft:dirt_with_roots": "rooted_dirt",
    }

    ITEM_FRAME_NO_BLOCK_TAG_ITEMS = {
        "minecraft:bed",
        "minecraft:pitcher_pod",
        "minecraft:pumpkin_seeds",
        "minecraft:melon_seeds",
        "minecraft:melon_slice",
        "minecraft:redstone",
        "minecraft:carrot",
        "minecraft:potato",
        "minecraft:beetroot",
        "minecraft:cocoa_beans",
        "minecraft:banner",
        "minecraft:sign",
        "minecraft:oak_sign",
        "minecraft:spruce_sign",
        "minecraft:birch_sign",
        "minecraft:jungle_sign",
        "minecraft:acacia_sign",
        "minecraft:dark_oak_sign",
        "minecraft:mangrove_sign",
        "minecraft:cherry_sign",
        "minecraft:bamboo_sign",
        "minecraft:crimson_sign",
        "minecraft:warped_sign",
        "minecraft:oak_hanging_sign",
        "minecraft:spruce_hanging_sign",
        "minecraft:birch_hanging_sign",
        "minecraft:jungle_hanging_sign",
        "minecraft:acacia_hanging_sign",
        "minecraft:dark_oak_hanging_sign",
        "minecraft:mangrove_hanging_sign",
        "minecraft:cherry_hanging_sign",
        "minecraft:bamboo_hanging_sign",
        "minecraft:crimson_hanging_sign",
        "minecraft:warped_hanging_sign",
        "minecraft:candle",
        "minecraft:white_candle",
        "minecraft:orange_candle",
        "minecraft:magenta_candle",
        "minecraft:light_blue_candle",
        "minecraft:yellow_candle",
        "minecraft:lime_candle",
        "minecraft:pink_candle",
        "minecraft:gray_candle",
        "minecraft:light_gray_candle",
        "minecraft:cyan_candle",
        "minecraft:purple_candle",
        "minecraft:blue_candle",
        "minecraft:brown_candle",
        "minecraft:green_candle",
        "minecraft:red_candle",
        "minecraft:black_candle",
        "minecraft:frame",
        "minecraft:glow_frame",
        "minecraft:carpet",
    }

    NON_STACKABLE_ITEMS = {
        "minecraft:bed",
        "minecraft:shulker_box",
        "minecraft:undyed_shulker_box",
    }

    DOUBLE_HEIGHT_DEDUP_BLOCKS = {
        "minecraft:bed",
        "minecraft:lilac",
        "minecraft:peony",
        "minecraft:rose_bush",
        "minecraft:sunflower",
        "minecraft:tall_grass",
        "minecraft:large_fern",
        "minecraft:tall_seagrass",
        "minecraft:seagrass",
        "minecraft:small_dripleaf",
        "minecraft:small_dripleaf_block",
        "minecraft:pitcher_plant",
        "minecraft:pitcher_crop",
    }

    KNOWN_UNSAFE_ITEM_BLOCKS = {
        "minecraft:piston_head",
        "minecraft:sticky_piston_head",
        "minecraft:sticky_piston_arm_collision",
        "minecraft:piston_arm_collision",
        "minecraft:moving_piston",
        "minecraft:moving_block",
    }

    AIR_BLOCKS = {
        "minecraft:air",
        "minecraft:cave_air",
        "minecraft:void_air",
    }

    DEFAULT_EXCLUDED_BLOCKS = {
        "minecraft:air",
        "minecraft:cave_air",
        "minecraft:void_air",
        "minecraft:bedrock",
        "minecraft:water",
        "minecraft:flowing_water",
        "minecraft:lava",
        "minecraft:flowing_lava",
        "minecraft:budding_amethyst",
        "minecraft:infested_stone",
        "minecraft:infested_cobblestone",
        "minecraft:infested_stone_bricks",
        "minecraft:infested_mossy_stone_bricks",
        "minecraft:infested_cracked_stone_bricks",
        "minecraft:infested_chiseled_stone_bricks",
        "minecraft:infested_deepslate",
        "minecraft:infested_block",
        "minecraft:bubble_column",
        "minecraft:sticky_piston_head",
        "minecraft:sticky_piston_arm_collision",
        "minecraft:piston_arm_collision",
        "minecraft:moving_block",
        "minecraft:structure_block",
        "minecraft:structure_void",
        "minecraft:barrier",
        "minecraft:light",
        "minecraft:end_gateway",
        "minecraft:end_portal",
        "minecraft:portal",
        "minecraft:fire",
        "minecraft:soul_fire",
        "minecraft:moving_piston",
        "minecraft:piston_head",
        "minecraft:command_block",
        "minecraft:repeating_command_block",
        "minecraft:chain_command_block",
        "minecraft:jigsaw",
        "minecraft:mob_spawner",
        "minecraft:spawner",
        "minecraft:monster_spawner",
        "minecraft:trial_spawner",
        "minecraft:vault",
    }

    def __init__(
        self,
        parent: wx.Window,
        canvas: "EditCanvas",
        world: "BaseLevel",
        options_path: str,
    ):
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)

        self._world_platform = getattr(world.level_wrapper, "platform", "universal")
        self._world_version = getattr(world.level_wrapper, "version", None)
        self._scan_order: List[str] = []

        self._report_lines: List[str] = []
        self._last_report_text: str = ""

        self._fast_scan_failed = False
        self._fast_scan_fail_reason = ""
        self._fast_clear_failed = False
        self._fast_clear_fail_reason = ""
        self._ambiguous_fast_scan_fallbacks = 0

        self._external_language_aliases: Dict[str, Tuple[str, str]] = {}
        self._external_language_raw_entries: Dict[str, str] = {}
        self._found_entries_aliases: Dict[str, Tuple[str, str]] = {}
        self._found_entries_raw_entries: Dict[str, str] = {}
        self._external_language_loaded_path = ""
        self._external_language_loaded_mtime = None
        self._external_language_load_error = ""
        self._external_language_loaded_count = 0
        self._external_language_used: Dict[str, Tuple[str, str, str]] = {}
        self._found_entries_used: Dict[str, Tuple[str, str, str]] = {}
        self._pending_found_entries: Dict[str, str] = {}
        self._found_entries_write_error = ""
        self._found_entries_written_count = 0
        self._external_language_prepared = False
        self._display_name_resolution_cache: Dict[
            str,
            Optional[Tuple[str, str, str]],
        ] = {}

        self._configure_tooltips()

        self._sizer = wx.BoxSizer(wx.VERTICAL)

        self.settings_panel = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.settings_panel.SetScrollRate(0, 20)
        self.settings_panel.SetMinSize((320, self.SETTINGS_PANEL_MIN_HEIGHT))
        self.settings_panel.SetInitialSize((-1, self.SETTINGS_PANEL_DEFAULT_HEIGHT))
        self.settings_sizer = wx.BoxSizer(wx.VERTICAL)
        self.settings_panel.SetSizer(self.settings_sizer)
        self.Bind(wx.EVT_SIZE, self._on_panel_resized)

        title = wx.StaticText(self.settings_panel, label="Blocks to Storage")
        self.settings_sizer.Add(title, 0, wx.ALL, 6)

        self._add_settings_section("Storage settings")

        container_row = wx.BoxSizer(wx.HORIZONTAL)
        container_label = wx.StaticText(self.settings_panel, label="Storage container")
        self.storage_choice = wx.Choice(
            self.settings_panel,
            choices=[
                self.CONTAINER_CHEST,
                self.CONTAINER_BARREL,
                self.CONTAINER_SHULKER,
            ],
        )
        self.storage_choice.SetSelection(0)
        self.storage_choice.Bind(wx.EVT_CHOICE, self._on_storage_choice_changed)

        container_row.Add(container_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        container_row.Add(self.storage_choice, 1)
        self.settings_sizer.Add(container_row, 0, wx.ALL | wx.EXPAND, 6)

        self.shulker_color_row = wx.BoxSizer(wx.HORIZONTAL)
        shulker_color_label = wx.StaticText(self.settings_panel, label="Shulker color")
        self.shulker_color_choice = wx.Choice(self.settings_panel, choices=self.SHULKER_COLORS)
        self.shulker_color_choice.SetSelection(0)

        self.shulker_color_row.Add(shulker_color_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.shulker_color_row.Add(self.shulker_color_choice, 1)
        self.settings_sizer.Add(self.shulker_color_row, 0, wx.ALL | wx.EXPAND, 6)

        self.use_double_chests = wx.CheckBox(self.settings_panel, label="Use double chests")
        self.use_double_chests.SetValue(False)
        self.settings_sizer.Add(self.use_double_chests, 0, wx.ALL, 6)

        stack_row = wx.BoxSizer(wx.HORIZONTAL)
        stack_label = wx.StaticText(self.settings_panel, label="Vertical stack height")
        self.stack_height = wx.SpinCtrl(
            self.settings_panel,
            min=1,
            max=self.MAX_STACK_HEIGHT,
            initial=self.DEFAULT_STACK_HEIGHT,
            size=(80, -1),
        )
        stack_row.Add(stack_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        stack_row.Add(self.stack_height, 0)
        self.settings_sizer.Add(stack_row, 0, wx.ALL, 6)

        self._add_settings_section("Export behavior")

        self.include_unusual = wx.CheckBox(self.settings_panel, label="Include unusual blocks")
        self.include_unusual.SetValue(False)
        self.settings_sizer.Add(self.include_unusual, 0, wx.ALL, 6)

        self.preserve_bedrock = wx.CheckBox(self.settings_panel, label="Preserve bedrock")
        self.preserve_bedrock.SetValue(True)
        self.settings_sizer.Add(self.preserve_bedrock, 0, wx.ALL, 6)

        self.alphabetical_order = wx.CheckBox(self.settings_panel, label="ABC item order")
        self.alphabetical_order.SetValue(True)
        self.settings_sizer.Add(self.alphabetical_order, 0, wx.ALL, 6)

        self._add_settings_section("Separated groups")

        self.separate_types = wx.CheckBox(self.settings_panel, label="One block type per storage group")
        self.separate_types.SetValue(False)
        self.separate_types.Bind(wx.EVT_CHECKBOX, self._on_separate_types_changed)
        self.settings_sizer.Add(self.separate_types, 0, wx.ALL, 6)

        self.add_group_item_frames = wx.CheckBox(self.settings_panel, label="Add item frames for separated groups")
        self.add_group_item_frames.SetValue(False)
        self.settings_sizer.Add(self.add_group_item_frames, 0, wx.ALL, 6)

        group_spacing_row = wx.BoxSizer(wx.HORIZONTAL)
        self.group_spacing_label = wx.StaticText(self.settings_panel, label="Spacing between separated groups")
        self.group_spacing = wx.SpinCtrl(
            self.settings_panel,
            min=0,
            max=self.MAX_GROUP_SPACING,
            initial=self.DEFAULT_GROUP_SPACING,
            size=(80, -1),
        )
        group_spacing_row.Add(self.group_spacing_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        group_spacing_row.Add(self.group_spacing, 0)
        self.settings_sizer.Add(group_spacing_row, 0, wx.ALL, 6)

        self._add_settings_section("Nested shulker storage")

        self.use_nested_shulker_storage = wx.CheckBox(self.settings_panel, label="Pack into shulker boxes inside storage")
        self.use_nested_shulker_storage.SetValue(False)
        self.use_nested_shulker_storage.Bind(wx.EVT_CHECKBOX, self._on_nested_shulker_storage_changed)
        self.settings_sizer.Add(self.use_nested_shulker_storage, 0, wx.ALL, 6)

        self.nested_shulker_mode_row = wx.BoxSizer(wx.HORIZONTAL)
        self.nested_shulker_mode_label = wx.StaticText(self.settings_panel, label="Nested shulker mode")
        self.nested_shulker_mode_choice = wx.Choice(
            self.settings_panel,
            choices=[
                self.NESTED_SHULKER_MODE_PRACTICAL,
                self.NESTED_SHULKER_MODE_COMPACT,
            ],
        )
        self.nested_shulker_mode_choice.SetSelection(0)
        self.nested_shulker_mode_row.Add(self.nested_shulker_mode_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.nested_shulker_mode_row.Add(self.nested_shulker_mode_choice, 1)
        self.settings_sizer.Add(self.nested_shulker_mode_row, 0, wx.ALL | wx.EXPAND, 6)

        self.nested_shulker_color_row = wx.BoxSizer(wx.HORIZONTAL)
        self.nested_shulker_color_label = wx.StaticText(self.settings_panel, label="Nested shulker color")
        self.nested_shulker_color_choice = wx.Choice(self.settings_panel, choices=self.SHULKER_COLORS)
        self.nested_shulker_color_choice.SetSelection(0)
        self.nested_shulker_color_row.Add(self.nested_shulker_color_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.nested_shulker_color_row.Add(self.nested_shulker_color_choice, 1)
        self.settings_sizer.Add(self.nested_shulker_color_row, 0, wx.ALL | wx.EXPAND, 6)

        self._add_settings_section("Performance and safety")

        self.fast_direct_scan = wx.CheckBox(self.settings_panel, label="Fast direct chunk scan")
        self.fast_direct_scan.SetValue(True)
        self.settings_sizer.Add(self.fast_direct_scan, 0, wx.ALL, 6)

        self.fast_direct_clear = wx.CheckBox(self.settings_panel, label="Fast direct chunk clear")
        self.fast_direct_clear.SetValue(True)
        self.settings_sizer.Add(self.fast_direct_clear, 0, wx.ALL, 6)

        self.show_large_selection_warning = wx.CheckBox(self.settings_panel, label="Show large selection warning")
        self.show_large_selection_warning.SetValue(True)
        self.settings_sizer.Add(self.show_large_selection_warning, 0, wx.ALL, 6)

        self._add_settings_section("Display-name data")

        self.use_found_entries_cache = wx.CheckBox(
            self.settings_panel,
            label=f"Use plugin-created {self.FOUND_ENTRIES_FILENAME} cache",
        )
        self.use_found_entries_cache.SetValue(True)
        self.use_found_entries_cache.Bind(
            wx.EVT_CHECKBOX,
            self._on_display_name_dependency_changed,
        )
        self.settings_sizer.Add(
            self.use_found_entries_cache,
            0,
            wx.ALL,
            6,
        )

        self.use_installed_language_data = wx.CheckBox(
            self.settings_panel,
            label="Use installed Minecraft en_US.lang as fallback",
        )
        self.use_installed_language_data.SetValue(False)
        self.use_installed_language_data.Bind(
            wx.EVT_CHECKBOX,
            self._on_installed_language_data_changed,
        )
        self.settings_sizer.Add(self.use_installed_language_data, 0, wx.ALL, 6)

        self.auto_detect_language_file = wx.CheckBox(
            self.settings_panel,
            label="Automatically detect the Minecraft language file",
        )
        self.auto_detect_language_file.SetValue(False)
        self.auto_detect_language_file.Bind(
            wx.EVT_CHECKBOX,
            self._on_auto_detect_language_file_changed,
        )
        self.settings_sizer.Add(self.auto_detect_language_file, 0, wx.ALL, 6)

        self.language_file_row = wx.BoxSizer(wx.HORIZONTAL)
        self.language_file_label = wx.StaticText(
            self.settings_panel,
            label="Language file",
        )
        self.language_file_path = wx.TextCtrl(
            self.settings_panel,
            value=str(
                Path("C:/") / self.DEFAULT_MINECRAFT_LANGUAGE_RELATIVE_PATH
            ),
        )
        self.browse_language_file_button = wx.Button(
            self.settings_panel,
            label="Browse...",
        )
        self.browse_language_file_button.Bind(
            wx.EVT_BUTTON,
            self._browse_for_language_file,
        )
        self.language_file_row.Add(
            self.language_file_label,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            8,
        )
        self.language_file_row.Add(self.language_file_path, 1, wx.RIGHT, 6)
        self.language_file_row.Add(self.browse_language_file_button, 0)
        self.settings_sizer.Add(
            self.language_file_row,
            0,
            wx.ALL | wx.EXPAND,
            6,
        )

        self.save_found_language_entries = wx.CheckBox(
            self.settings_panel,
            label=f"Save newly resolved entries to {self.FOUND_ENTRIES_FILENAME}",
        )
        self.save_found_language_entries.SetValue(False)
        self.save_found_language_entries.Bind(
            wx.EVT_CHECKBOX,
            self._on_display_name_dependency_changed,
        )
        self.settings_sizer.Add(
            self.save_found_language_entries,
            0,
            wx.ALL,
            6,
        )

        self.simulate_missing_display_name = wx.CheckBox(
            self.settings_panel,
            label="Simulate missing embedded display-name entry",
        )
        self.simulate_missing_display_name.SetValue(False)
        self.simulate_missing_display_name.Bind(
            wx.EVT_CHECKBOX,
            self._on_simulate_missing_display_name_changed,
        )
        self.settings_sizer.Add(
            self.simulate_missing_display_name,
            0,
            wx.ALL,
            6,
        )

        self.simulated_missing_alias_row = wx.BoxSizer(wx.HORIZONTAL)
        self.simulated_missing_alias_label = wx.StaticText(
            self.settings_panel,
            label="Entry alias to ignore",
        )
        self.simulated_missing_alias = wx.TextCtrl(
            self.settings_panel,
            value="oak_log",
        )
        self.simulated_missing_alias_row.Add(
            self.simulated_missing_alias_label,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            8,
        )
        self.simulated_missing_alias_row.Add(self.simulated_missing_alias, 1)
        self.settings_sizer.Add(
            self.simulated_missing_alias_row,
            0,
            wx.ALL | wx.EXPAND,
            6,
        )

        self.delete_display_name_data_button = wx.Button(
            self.settings_panel,
            label="Delete plugin-created display-name data...",
        )
        self.delete_display_name_data_button.Bind(
            wx.EVT_BUTTON,
            self._delete_plugin_created_display_name_data,
        )
        self.settings_sizer.Add(
            self.delete_display_name_data_button,
            0,
            wx.ALL | wx.EXPAND,
            6,
        )

        self._add_settings_section("Debug and diagnostics")

        self.include_item_frame_audit = wx.CheckBox(
            self.settings_panel,
            label="Include item frame label audit in report",
        )
        self.include_item_frame_audit.SetValue(False)
        self.settings_sizer.Add(self.include_item_frame_audit, 0, wx.ALL, 6)

        self.include_display_name_audit = wx.CheckBox(
            self.settings_panel,
            label="Include display-name ABC audit in report",
        )
        self.include_display_name_audit.SetValue(False)
        self.settings_sizer.Add(self.include_display_name_audit, 0, wx.ALL, 6)

        self._sizer.Add(self.settings_panel, 0, wx.ALL | wx.EXPAND, 0)

        self.run_export_button = wx.Button(self, label="Delete Blocks to Storage")
        self.run_export_button.Bind(wx.EVT_BUTTON, self._run_export)
        self._sizer.Add(self.run_export_button, 0, wx.ALL | wx.EXPAND, 6)

        self.save_report_button = wx.Button(self, label="Save Last Report...")
        self.save_report_button.Bind(wx.EVT_BUTTON, self._save_last_report)
        self.save_report_button.Enable(False)
        self._sizer.Add(self.save_report_button, 0, wx.ALL | wx.EXPAND, 6)

        self.text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, 420),
        )
        self.text.SetMinSize((320, 260))
        self.text.SetForegroundColour((0, 255, 0))
        self.text.SetBackgroundColour((0, 0, 0))
        self._sizer.Add(self.text, 1, wx.ALL | wx.EXPAND, 6)

        self.SetSizer(self._sizer)
        self.SetMinSize((380, 700))

        self._set_tooltip(
            container_label,
            "Choose which storage block will hold the collected blocks. Chests support the double chest option. Barrels and shulker boxes use normal 27-slot storage.",
        )
        self._set_tooltip(
            self.storage_choice,
            "Choose which storage block will hold the collected blocks. Chests support the double chest option. Barrels and shulker boxes use normal 27-slot storage.",
        )
        self._set_tooltip(
            shulker_color_label,
            "Choose the shulker box color. Default creates the normal undyed shulker box.",
        )
        self._set_tooltip(
            self.shulker_color_choice,
            "Choose the shulker box color. Default creates the normal undyed shulker box.",
        )
        self._set_tooltip(
            stack_label,
            "Controls how many storage blocks can stack vertically before the plugin starts a new line. Default is 8. Maximum is 40.",
        )
        self._set_tooltip(
            self.stack_height,
            "Controls how many storage blocks can stack vertically before the plugin starts a new line. Default is 8. Maximum is 40.",
        )
        self._set_tooltip(
            self.include_unusual,
            "Includes normally skipped blocks such as water, lava, bubble columns, budding amethyst, infested blocks, barrier, light, portal blocks, command blocks, and other technical blocks.",
        )
        self._set_tooltip(
            self.preserve_bedrock,
            "Keeps bedrock blocks in the selected area instead of replacing them with air. This is on by default to avoid deleting the bottom bedrock layer.",
        )
        self._set_tooltip(
            self.fast_direct_scan,
            "Scans blocks directly from chunk data instead of calling get_version_block for every selected block. This is much faster on large selections, but some older / legacy block names may be less specific.",
        )
        self._set_tooltip(
            self.fast_direct_clear,
            "Clears blocks directly in chunk data using one cached air block ID per chunk. This is faster than the safer per-block write helper. If it fails, the plugin falls back to the safer clear method.",
        )
        self._set_tooltip(
            self.show_large_selection_warning,
            "Shows a confirmation popup before running on selections estimated at 500,000 blocks or more.",
        )
        self._set_tooltip(
            self.use_found_entries_cache,
            f"Uses previously saved entries from {self.FOUND_ENTRIES_FILENAME} independently of the installed Minecraft language fallback. This is on by default. If the file is missing, empty or unreadable, the plugin safely continues with embedded names without repeated checks.",
        )
        self._set_tooltip(
            self.use_installed_language_data,
            "Allows unresolved ABC display names to use a local Minecraft Bedrock Edition en_US.lang file. This is disabled by default. Embedded verified names always keep priority.",
        )
        self._set_tooltip(
            self.auto_detect_language_file,
            "When enabled, checks only known Minecraft for Windows installation locations on available drive letters. It is off by default and does not recursively search any drive.",
        )
        self._set_tooltip(
            self.language_file_label,
            "Path to the Minecraft Bedrock Edition en_US.lang file used for unresolved display names.",
        )
        self._set_tooltip(
            self.language_file_path,
            "Path to the Minecraft Bedrock Edition en_US.lang file. You may enter a path manually or use Browse.",
        )
        self._set_tooltip(
            self.browse_language_file_button,
            "Select the Minecraft Bedrock Edition en_US.lang file manually.",
        )
        self._set_tooltip(
            self.save_found_language_entries,
            f"Atomically saves newly used external display-name entries to {self.FOUND_ENTRIES_FILENAME}. Existing entries are preserved and embedded plugin data is never modified.",
        )
        self._set_tooltip(
            self.delete_display_name_data_button,
            f"Finds and deletes only plugin-created {self.FOUND_ENTRIES_FILENAME} files and the plugin-created fallback data folder when it becomes empty. A confirmation window lists every exact path before deletion. Minecraft language files, worlds, reports and the plugin are never deleted.",
        )
        self._set_tooltip(
            self.simulate_missing_display_name,
            "Testing only. Makes one item behave as though its embedded display-name entry is missing, allowing the external fallback and cache paths to be tested without editing the plugin.",
        )
        self._set_tooltip(
            self.simulated_missing_alias_label,
            "Internal item alias to ignore in the embedded table during testing, for example oak_log.",
        )
        self._set_tooltip(
            self.simulated_missing_alias,
            "Internal item alias to ignore in the embedded table during testing, for example oak_log. Only one alias is supported.",
        )
        self._set_tooltip(
            self.include_item_frame_audit,
            "Adds detailed item-frame label diagnostics to the export report, including internal item keys, final Bedrock item names, damage values, storage coordinates, frame coordinates and Block-tag usage. Leave this disabled during normal use.",
        )
        self._set_tooltip(
            self.include_display_name_audit,
            "Adds display-name and ABC sorting diagnostics to the export report. It compares the language-based sort result with the fallback sort key without changing conversion, storage contents, item frames or placement. Leave this disabled during normal use.",
        )
        self._set_tooltip(
            self.separate_types,
            "Keeps each block type in its own storage group. Example: stone goes into its own containers, dirt goes into its own containers, and so on.",
        )
        self._set_tooltip(
            self.add_group_item_frames,
            "Only works when One block type per storage group is enabled. Adds one regular item frame or glow item frame to the first storage container for each block type group.",
        )
        self._set_tooltip(
            self.group_spacing_label,
            "Controls the empty side space between separated block groups. Only applies when One block type per storage group is enabled. Item frames automatically reserve front space separately.",
        )
        self._set_tooltip(
            self.group_spacing,
            "Controls the empty side space between separated block groups. Range is 0 to 8. Default is 1. Item frames automatically reserve front space separately.",
        )
        self._set_tooltip(
            self.alphabetical_order,
            "Sorts block types by their Bedrock Edition display names before packing them into storage. Verified language names are used when available, with tested overrides and internal-name fallbacks for unresolved or ambiguous items. Turning this off keeps first-seen scan order.",
        )
        self._set_tooltip(
            self.use_double_chests,
            "Only applies when Storage container is set to Chest. Uses connected double chests with 54 slots instead of single chests with 27 slots.",
        )
        self._set_tooltip(
            self.use_nested_shulker_storage,
            "Advanced. Puts collected blocks into shulker boxes, then puts those shulker boxes inside the generated storage containers. This can greatly reduce how many containers are placed, but it uses more complex nested item data.",
        )
        self._set_tooltip(
            self.nested_shulker_mode_label,
            "Choose how nested shulker storage is used. Balanced mode leaves small block groups directly in storage and only uses shulker boxes for large groups. Compact mode uses shulker boxes for almost every group to save the most space.",
        )
        self._set_tooltip(
            self.nested_shulker_mode_choice,
            "Choose how nested shulker storage is used. Balanced mode leaves small block groups directly in storage and only uses shulker boxes for large groups. Compact mode uses shulker boxes for almost every group to save the most space.",
        )
        self._set_tooltip(
            self.nested_shulker_color_label,
            "Choose the color of the generated shulker boxes used inside storage containers. Default creates normal undyed shulker boxes.",
        )
        self._set_tooltip(
            self.nested_shulker_color_choice,
            "Choose the color of the generated shulker boxes used inside storage containers. Default creates normal undyed shulker boxes.",
        )
        self._set_tooltip(
            self.run_export_button,
            "Scans the selected area, counts exportable blocks, clears the selected blocks, and places the collected blocks into the chosen storage type.",
        )
        self._set_tooltip(
            self.save_report_button,
            "Saves the latest export report as a text file. You can choose the save location after clicking this button.",
        )
        self._set_tooltip(
            self.text,
            "Shows the export log, block counts, skipped blocks, placement summary, timing, speed, and report details for the latest run.",
        )

        self._update_option_visibility()

    def bind_events(self):
        super().bind_events()
        self._selection.bind_events()
        self._selection.enable()

    def enable(self):
        self._selection = BlockSelectionBehaviour(self.canvas)
        self._selection.enable()

    def _configure_tooltips(self) -> None:
        try:
            wx.ToolTip.SetDelay(450)
        except Exception:
            pass

        try:
            wx.ToolTip.SetAutoPop(15000)
        except Exception:
            pass

        try:
            wx.ToolTip.SetReshow(250)
        except Exception:
            pass

    def _set_tooltip(self, window, text: str) -> None:
        try:
            window.SetToolTip(wx.ToolTip(text))
        except Exception:
            try:
                window.SetToolTip(text)
            except Exception:
                pass

    def _add_settings_section(self, label: str) -> None:
        section_label = wx.StaticText(self.settings_panel, label=label)

        try:
            font = section_label.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            section_label.SetFont(font)
        except Exception:
            pass

        self.settings_sizer.Add(section_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)

    def _needs_safe_block_lookup(self, item_name: Optional[str]) -> bool:
        if not item_name:
            return False

        item_name = str(item_name)
        if item_name in self.STATE_SENSITIVE_SCAN_BLOCKS:
            return True
        if item_name in self.AMBIGUOUS_FAST_SCAN_BLOCKS:
            return True

        return item_name.endswith(
            (
                "_door",
                "_sign",
                "_hanging_sign",
                "_banner",
                "_candle_cake",
                "_bars",
                "_button",
                "_pressure_plate",
                "_trapdoor",
                "_fence_gate",
                "_head",
            )
        ) or (
            item_name.endswith("_candle")
            and not item_name.endswith("_candle_cake")
        )

    def _get_selected_container(self) -> str:
        value = self.storage_choice.GetStringSelection()
        if not value:
            return self.CONTAINER_CHEST
        return value

    def _on_storage_choice_changed(self, _):
        self._update_option_visibility()

    def _on_separate_types_changed(self, _):
        self._update_option_visibility()

    def _on_nested_shulker_storage_changed(self, _):
        self._update_option_visibility()

    def _on_display_name_dependency_changed(self, _) -> None:
        self._update_option_visibility()

    def _on_installed_language_data_changed(self, _) -> None:
        self._update_option_visibility()

    def _on_auto_detect_language_file_changed(self, _) -> None:
        self._update_option_visibility()

    def _on_simulate_missing_display_name_changed(self, _) -> None:
        self._update_option_visibility()

    def _browse_for_language_file(self, _) -> None:
        current_value = self.language_file_path.GetValue().strip()
        default_directory = ""
        default_file = "en_US.lang"

        if current_value:
            current_path = Path(current_value)
            default_directory = str(current_path.parent)
            default_file = current_path.name or default_file

        dialog = wx.FileDialog(
            self,
            message="Select Minecraft Bedrock Edition en_US.lang",
            defaultDir=default_directory,
            defaultFile=default_file,
            wildcard="Minecraft language files (*.lang)|*.lang|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )

        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.language_file_path.SetValue(dialog.GetPath())
        finally:
            dialog.Destroy()

    def _on_panel_resized(self, event) -> None:
        self._resize_settings_panel()
        try:
            event.Skip()
        except Exception:
            pass

    def _resize_settings_panel(self) -> None:
        try:
            _width, height = self.GetClientSize()
        except Exception:
            return

        if height <= 0:
            return

        target_height = int(height * 0.48)
        target_height = max(self.SETTINGS_PANEL_MIN_HEIGHT, target_height)
        target_height = min(self.SETTINGS_PANEL_MAX_HEIGHT, target_height)

        try:
            self.settings_panel.SetMinSize((320, target_height))
            self.settings_panel.SetInitialSize((-1, target_height))
            self.settings_panel.FitInside()
            self.settings_panel.Layout()
            self.Layout()
        except Exception:
            pass

    def _update_option_visibility(self) -> None:
        container = self._get_selected_container()

        is_chest = container == self.CONTAINER_CHEST
        is_shulker = container == self.CONTAINER_SHULKER
        separate_groups_enabled = self.separate_types.GetValue()
        nested_shulker_allowed = not is_shulker
        nested_shulker_enabled = (
            nested_shulker_allowed
            and hasattr(self, "use_nested_shulker_storage")
            and self.use_nested_shulker_storage.GetValue()
        )

        self.use_double_chests.Show(is_chest)
        self.add_group_item_frames.Show(separate_groups_enabled)
        self.group_spacing_label.Show(separate_groups_enabled)
        self.group_spacing.Show(separate_groups_enabled)

        if hasattr(self, "use_nested_shulker_storage"):
            self.use_nested_shulker_storage.Show(nested_shulker_allowed)

        if hasattr(self, "nested_shulker_mode_row"):
            for child in self.nested_shulker_mode_row.GetChildren():
                window = child.GetWindow()
                if window is not None:
                    window.Show(nested_shulker_enabled)

        if hasattr(self, "nested_shulker_color_row"):
            for child in self.nested_shulker_color_row.GetChildren():
                window = child.GetWindow()
                if window is not None:
                    window.Show(nested_shulker_enabled)

        external_language_enabled = (
            hasattr(self, "use_installed_language_data")
            and self.use_installed_language_data.GetValue()
        )
        btsp_cache_enabled = (
            hasattr(self, "use_found_entries_cache")
            and self.use_found_entries_cache.GetValue()
        )
        automatic_detection_checked = (
            hasattr(self, "auto_detect_language_file")
            and self.auto_detect_language_file.GetValue()
        )
        save_entries_checked = (
            hasattr(self, "save_found_language_entries")
            and self.save_found_language_entries.GetValue()
        )
        simulation_checked = (
            hasattr(self, "simulate_missing_display_name")
            and self.simulate_missing_display_name.GetValue()
        )

        if hasattr(self, "auto_detect_language_file"):
            self.auto_detect_language_file.Show(
                external_language_enabled
                or automatic_detection_checked
            )

        if hasattr(self, "language_file_row"):
            show_manual_language_path = (
                external_language_enabled
                and not automatic_detection_checked
            )
            for child in self.language_file_row.GetChildren():
                window = child.GetWindow()
                if window is not None:
                    window.Show(show_manual_language_path)

        if hasattr(self, "save_found_language_entries"):
            self.save_found_language_entries.Show(
                external_language_enabled
                or save_entries_checked
            )

        if hasattr(self, "simulate_missing_display_name"):
            self.simulate_missing_display_name.Show(
                btsp_cache_enabled
                or external_language_enabled
                or simulation_checked
            )

        if hasattr(self, "delete_display_name_data_button"):
            self.delete_display_name_data_button.Show(True)

        if hasattr(self, "simulated_missing_alias_row"):
            for child in self.simulated_missing_alias_row.GetChildren():
                window = child.GetWindow()
                if window is not None:
                    window.Show(simulation_checked)

        if not separate_groups_enabled:
            self.add_group_item_frames.SetValue(False)

        for child in self.shulker_color_row.GetChildren():
            window = child.GetWindow()
            if window is not None:
                window.Show(is_shulker)

        if not is_chest:
            self.use_double_chests.SetValue(False)

        if is_shulker and hasattr(self, "use_nested_shulker_storage"):
            self.use_nested_shulker_storage.SetValue(False)

        try:
            self.settings_panel.FitInside()
            self._resize_settings_panel()
            self.Layout()
            self.GetParent().Layout()
        except Exception:
            pass

    def _estimate_selection_volume(self) -> Optional[int]:
        selection = list(self.canvas.selection.selection_group.selection_boxes)
        total = 0

        for box in selection:
            try:
                total += int(len(box))
                continue
            except Exception:
                pass

            try:
                x_len = int(box.max_x) - int(box.min_x)
                y_len = int(box.max_y) - int(box.min_y)
                z_len = int(box.max_z) - int(box.min_z)

                if x_len > 0 and y_len > 0 and z_len > 0:
                    total += x_len * y_len * z_len
            except Exception:
                return None

        return total

    def _confirm_large_selection(self) -> bool:
        if not self.show_large_selection_warning.GetValue():
            return True

        estimated_volume = self._estimate_selection_volume()

        if estimated_volume is None:
            return True

        if estimated_volume < self.LARGE_SELECTION_WARNING_THRESHOLD:
            return True

        message = (
            "Large selection warning\n\n"
            f"Estimated selected blocks: {estimated_volume:,}\n\n"
            "This operation may take several minutes, especially if many storage containers need to be created.\n\n"
            "The plugin will scan the selection, clear exportable blocks, preserve protected bedrock if enabled, "
            "and place the collected blocks into storage containers.\n\n"
            "Continue?"
        )

        dialog = wx.MessageDialog(
            self,
            message,
            "Confirm Large Operation",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )

        try:
            result = dialog.ShowModal()
        finally:
            dialog.Destroy()

        return result == wx.ID_YES

    def _format_seconds(self, seconds: float) -> str:
        seconds = float(seconds)
        if seconds < 60:
            return f"{seconds:.2f} seconds"

        minutes = int(seconds // 60)
        remaining_seconds = seconds - (minutes * 60)

        if minutes < 60:
            return f"{minutes} minute(s), {remaining_seconds:.2f} seconds"

        hours = int(minutes // 60)
        remaining_minutes = minutes - (hours * 60)
        return f"{hours} hour(s), {remaining_minutes} minute(s), {remaining_seconds:.2f} seconds"

    def _format_rate(self, amount: int, seconds: float, label: str) -> str:
        seconds = float(seconds)
        if seconds <= 0:
            return f"{amount:,} {label}/second"

        rate = amount / seconds
        return f"{rate:,.2f} {label}/second"

    def _get_skipped_block_reason(self, item_name: str) -> str:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))

        if item_name == "unknown_block":
            return "Unknown / unsupported blocks"

        if item_name == "minecraft:bedrock" and self.preserve_bedrock.GetValue():
            return "Protected blocks preserved"

        if item_name in self.KNOWN_UNSAFE_ITEM_BLOCKS:
            return "Unsafe technical blocks"

        if item_name in self.GENERIC_UNSAFE_ITEM_BLOCKS:
            return "Unsupported generic block names"

        if not self.include_unusual.GetValue() and item_name in self.DEFAULT_EXCLUDED_BLOCKS:
            return "Default excluded blocks"

        return "Other skipped blocks"

    def _log_skipped_block_report(
        self,
        skipped_counts: Dict[str, int],
        skipped_by_reason: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> None:
        if not skipped_counts:
            self._log("Skipped blocks: none")
            return

        if skipped_by_reason is None:
            skipped_by_reason = collections.defaultdict(lambda: collections.defaultdict(int))
            for item_name, amount in skipped_counts.items():
                reason = self._get_skipped_block_reason(item_name)
                skipped_by_reason[reason][item_name] += int(amount)

        self._log("Skipped blocks by reason:")
        for reason in sorted(skipped_by_reason.keys()):
            reason_counts = skipped_by_reason[reason]
            reason_total = sum(reason_counts.values())
            self._log(f"{reason}: {reason_total:,}")
            for item_name in sorted(reason_counts.keys()):
                self._log(f"  {item_name} -> {reason_counts[item_name]:,}")

    def _clear_log(self) -> None:
        try:
            wx.CallAfter(self.text.SetValue, "")
        except Exception:
            try:
                self.text.SetValue("")
            except Exception:
                pass

    def _append_log_text(self, message: str) -> None:
        try:
            self.text.AppendText(message + "\n")
        except Exception:
            pass

    def _log(self, message: str) -> None:
        print(message)

        try:
            self._report_lines.append(message)
        except Exception:
            pass

        try:
            wx.CallAfter(self._append_log_text, message)
        except Exception:
            self._append_log_text(message)

    def _reset_report(self) -> None:
        self._report_lines = []
        self._last_report_text = ""
        try:
            self.save_report_button.Enable(False)
        except Exception:
            pass

    def _finalize_report(self) -> None:
        self._last_report_text = "\n".join(self._report_lines).strip()

        if self._last_report_text:
            try:
                wx.CallAfter(self.save_report_button.Enable, True)
            except Exception:
                try:
                    self.save_report_button.Enable(True)
                except Exception:
                    pass

    def _save_last_report(self, _):
        if not self._last_report_text:
            wx.MessageBox(
                "No report is available yet. Run the exporter first.",
                "No Report",
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        default_name = "Blocks to Storage export report; " + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"

        with wx.FileDialog(
            self,
            message="Save export report",
            defaultFile=default_name,
            wildcard="Text files (*.txt)|*.txt|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return

            path = dialog.GetPath()

        try:
            with open(path, "w", encoding="utf-8") as report_file:
                report_file.write(self._last_report_text)
                report_file.write("\n")
            wx.MessageBox(
                f"Report saved:\n{path}",
                "Report Saved",
                wx.OK | wx.ICON_INFORMATION,
            )
        except Exception as exc:
            wx.MessageBox(
                f"Could not save report:\n{exc}",
                "Save Failed",
                wx.OK | wx.ICON_ERROR,
            )

    def _iter_selected_positions(self):
        selection = list(self.canvas.selection.selection_group.selection_boxes)

        for box in selection:
            for pos in box:
                yield int(pos[0]), int(pos[1]), int(pos[2])

    def _get_single_storage_row_facing(
        self,
        x: int,
        z: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> str:
        min_x, _min_y, min_z, max_x, _max_y, max_z = bounds

        x_len = (max_x - min_x) + 1
        z_len = (max_z - min_z) + 1
        center_x = (min_x + max_x) / 2.0
        center_z = (min_z + max_z) / 2.0

        if x_len <= z_len:
            if z <= center_z:
                return "south"
            return "north"

        if x <= center_x:
            return "east"
        return "west"

    def _get_inward_facing(
        self,
        x: int,
        z: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> str:
        return self._get_single_storage_row_facing(x, z, bounds)

    def _get_double_chest_facing(
        self,
        pair_axis: str,
        x1: int,
        z1: int,
        x2: int,
        z2: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> str:
        min_x, _min_y, min_z, max_x, _max_y, max_z = bounds
        center_x = (min_x + max_x) / 2.0
        center_z = (min_z + max_z) / 2.0
        pair_center_x = (x1 + x2) / 2.0
        pair_center_z = (z1 + z2) / 2.0

        if pair_axis == "x":
            if pair_center_z <= center_z:
                return "south"
            return "north"

        if pair_center_x <= center_x:
            return "east"
        return "west"

    def _get_primary_offset_for_visual_index(
        self,
        primary_axis: str,
        visual_index: int,
        line_index: int,
        primary_len: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> int:
        min_x, _min_y, min_z, _max_x, _max_y, _max_z = bounds

        if primary_axis == "x":
            x = min_x
            z = min_z + line_index
            facing = self._get_single_storage_row_facing(x, z, bounds)
            if facing == "north":
                return (primary_len - 1) - visual_index
            return visual_index

        x = min_x + line_index
        z = min_z
        facing = self._get_single_storage_row_facing(x, z, bounds)
        if facing == "east":
            return (primary_len - 1) - visual_index
        return visual_index

    def _get_double_chest_primary_offset_for_visual_index(
        self,
        pair_axis: str,
        visual_index: int,
        line_index: int,
        primary_block_len: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> int:
        min_x, _min_y, min_z, _max_x, _max_y, _max_z = bounds

        if pair_axis == "x":
            x1 = min_x
            x2 = min_x + 1
            z1 = min_z + line_index
            z2 = z1
            facing = self._get_double_chest_facing(pair_axis, x1, z1, x2, z2, bounds)
            if facing == "north":
                return (primary_block_len - 2) - visual_index
            return visual_index

        x1 = min_x + line_index
        x2 = x1
        z1 = min_z
        z2 = min_z + 1
        facing = self._get_double_chest_facing(pair_axis, x1, z1, x2, z2, bounds)
        if facing == "east":
            return (primary_block_len - 2) - visual_index
        return visual_index

    def _get_double_chest_connections(
        self,
        pair_axis: str,
        facing: str,
    ) -> Tuple[str, str]:
        if pair_axis == "x":
            if facing == "north":
                return "left", "right"
            if facing == "south":
                return "right", "left"
            return "left", "right"

        if facing == "east":
            return "left", "right"
        if facing == "west":
            return "right", "left"

        return "left", "right"

    def _get_double_chest_left_right(
        self,
        first_pos: Tuple[int, int, int],
        second_pos: Tuple[int, int, int],
        pair_axis: str,
        facing: str,
    ) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], str, str]:
        connection_1, connection_2 = self._get_double_chest_connections(pair_axis, facing)

        x1, _y1, z1 = first_pos
        x2, _y2, z2 = second_pos

        first_is_visual_left = True

        if facing == "east":
            first_is_visual_left = z1 > z2
        elif facing == "west":
            first_is_visual_left = z1 < z2
        elif facing == "south":
            first_is_visual_left = x1 < x2
        elif facing == "north":
            first_is_visual_left = x1 > x2

        if first_is_visual_left:
            return first_pos, second_pos, connection_1, connection_2

        return second_pos, first_pos, connection_2, connection_1

    def _normalize_name(self, value) -> str:
        text = str(value) if value is not None else ""
        if not text:
            return ""
        if text.startswith("universal_minecraft:"):
            text = text.replace("universal_minecraft:", "minecraft:", 1)
        if ":" in text:
            return text
        return f"minecraft:{text}"

    def _get_namespaced_block_name(self, block) -> Optional[str]:
        namespace = getattr(block, "namespace", "minecraft") or "minecraft"
        base_name = getattr(block, "base_name", None) or getattr(block, "namespaced_name", None)

        if base_name is None:
            return None

        namespace = self._normalize_name(namespace)
        if namespace.startswith("minecraft:"):
            namespace = "minecraft"

        return self._normalize_name(f"{namespace}:{str(base_name)}")

    def _tag_to_python_value(self, value):
        for attr in ("py_data", "value"):
            try:
                return getattr(value, attr)
            except Exception:
                pass

        try:
            if hasattr(value, "__int__"):
                return int(value)
        except Exception:
            pass

        text = str(value)

        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]

        return text

    def _get_block_property(self, block, names: Sequence[str]):
        properties = getattr(block, "properties", None)

        if not properties:
            return None

        for name in names:
            try:
                if name in properties:
                    return self._tag_to_python_value(properties.get(name))
            except Exception:
                pass

        return None

    def _is_truthy_state_value(self, value) -> bool:
        value = self._tag_to_python_value(value)

        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            return value != 0

        text = str(value).strip().lower()
        text = text.strip('"').strip("'")

        if text in ("1", "1b", "true", "upper", "top", "head"):
            return True

        if "true" in text:
            return True

        if re.search(r"\b1\b", text):
            return True

        return False

    def _is_upper_half_block(self, block, key: str) -> bool:
        if key not in self.DOUBLE_HEIGHT_DEDUP_BLOCKS and key != "minecraft:door" and not str(key).endswith("_door"):
            return False

        upper_value = self._get_block_property(
            block,
            (
                "upper_block_bit",
                "top_slot_bit",
                "head_piece_bit",
                "is_upper",
                "upper",
                "half",
                "part",
            ),
        )

        return self._is_truthy_state_value(upper_value)

    def _get_nbt_child(self, nbt, key: str):
        if nbt is None:
            return None

        containers = [nbt]

        try:
            containers.append(nbt.value)
        except Exception:
            pass

        try:
            containers.append(nbt.tag)
        except Exception:
            pass

        for container in containers:
            if container is None:
                continue

            try:
                if key in container:
                    return container[key]
            except Exception:
                pass

            try:
                value = container.get(key)
                if value is not None:
                    return value
            except Exception:
                pass

        return None

    def _get_block_entity_nbt_value(self, block_entity, key: str):
        if block_entity is None:
            return None

        nbt = getattr(block_entity, "nbt", None)
        value = self._get_nbt_child(nbt, key)

        if value is None:
            return None

        return self._tag_to_python_value(value)

    def _get_bed_color_name(self, block, block_entity) -> Optional[str]:
        color = self._get_block_entity_nbt_value(block_entity, "color")

        if color is None:
            color = self._get_block_property(block, ("color", "bed_color"))

        if color is None:
            return None

        if isinstance(color, int):
            if 0 <= color < len(self.BED_COLOR_NAMES):
                return self.BED_COLOR_NAMES[color]
            return None

        color_text = str(color).strip().lower()

        if color_text.startswith("minecraft:"):
            color_text = color_text.split(":", 1)[1]

        color_text = color_text.replace(" ", "_")

        if color_text.endswith("_bed"):
            color_text = color_text[:-4]

        if color_text in self.BED_COLOR_NAMES:
            return color_text

        return None

    def _get_block_color_name(self, block, block_entity=None) -> Optional[str]:
        color = self._get_block_entity_nbt_value(block_entity, "color")

        if color is None:
            color = self._get_block_property(
                block,
                (
                    "color",
                    "colour",
                    "color_bit",
                    "color_value",
                    "minecraft:color",
                ),
            )

        if color is None:
            return None

        if isinstance(color, int):
            if 0 <= color < len(self.BED_COLOR_NAMES):
                return self.BED_COLOR_NAMES[color]
            return None

        color_text = str(color).strip().lower()

        if color_text.startswith("minecraft:"):
            color_text = color_text.split(":", 1)[1]

        color_text = color_text.replace(" ", "_").replace("-", "_")
        color_text = self.COLOR_NAME_ALIASES.get(color_text, color_text)

        if color_text in self.BED_COLOR_NAMES:
            return color_text

        return None

    def _get_colored_variant_item_name(
        self,
        block,
        item_by_color: Dict[str, str],
        block_entity=None,
    ) -> Optional[str]:
        color_name = self._get_block_color_name(block, block_entity)

        if color_name is None:
            return None

        return item_by_color.get(color_name)

    def _get_coral_block_item_name(self, block, key: str) -> Optional[str]:
        key_text = str(key).strip().lower()
        if key_text.startswith("minecraft:"):
            key_text = key_text.split(":", 1)[1]

        is_dead = key_text.startswith("dead_")
        coral_type = None

        for candidate in self.CORAL_BLOCK_TYPES:
            if candidate in key_text:
                coral_type = candidate
                break

        if coral_type is None:
            raw_type = self._get_block_property(
                block,
                (
                    "coral_color",
                    "coral_type",
                    "coral",
                    "type",
                    "color",
                    "colour",
                ),
            )

            if raw_type is not None:
                type_text = str(raw_type).strip().lower()
                if type_text.startswith("minecraft:"):
                    type_text = type_text.split(":", 1)[1]
                type_text = type_text.replace(" ", "_").replace("-", "_")

                for candidate in self.CORAL_BLOCK_TYPES:
                    if candidate in type_text:
                        coral_type = candidate
                        break

        dead_value = self._get_block_property(
            block,
            (
                "dead_bit",
                "dead",
                "is_dead",
            ),
        )
        if self._is_truthy_state_value(dead_value):
            is_dead = True

        if coral_type is None:
            return None

        prefix = "dead_" if is_dead else ""
        return f"minecraft:{prefix}{coral_type}_coral_block"

    def _get_stained_terracotta_item_name(self, block, block_entity=None) -> Optional[str]:
        color_name = self._get_block_color_name(block, block_entity)

        if color_name is None:
            return None

        return self.TERRACOTTA_ITEM_BY_COLOR.get(color_name)

    def _get_glazed_terracotta_item_name(self, block, block_entity=None) -> Optional[str]:
        color_name = self._get_block_color_name(block, block_entity)

        if color_name is None:
            return None

        return self.GLAZED_TERRACOTTA_ITEM_BY_COLOR.get(color_name)

    def _get_candle_cake_item_name(self, block, key: str) -> str:
        key = self.ITEM_NAME_OVERRIDES.get(str(key), str(key))

        if key in self.CANDLE_CAKE_CANDLE_BY_BLOCK:
            return key

        color = self._get_block_property(
            block,
            (
                "color",
                "colour",
                "candle_color",
                "candle_colour",
                "candle_type",
                "candle",
                "type",
            ),
        )
        color_text = self._normalize_state_text(color)

        if not color_text:
            block_key = self._get_namespaced_block_name(block) or ""
            block_key = block_key.split(":", 1)[1] if ":" in block_key else block_key
            color_text = self._normalize_state_text(block_key)

        if color_text in ("candle", "candle_cake", "none", "normal", ""):
            return "minecraft:candle_cake"

        color_text = color_text.removesuffix("_candle_cake")
        color_text = color_text.removesuffix("_candle")
        color_text = self.COLOR_NAME_ALIASES.get(color_text, color_text)

        colored_key = f"minecraft:{color_text}_candle_cake"
        if colored_key in self.CANDLE_CAKE_CANDLE_BY_BLOCK:
            return colored_key

        return key

    def _get_candle_export_amount(self, block, item_name: str) -> int:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))

        if item_name not in self.CANDLE_ITEM_BLOCKS:
            return 1

        candle_count = self._get_block_property(
            block,
            (
                "candles",
                "candle_count",
                "cluster_count",
                "count",
            ),
        )

        try:
            candle_count_value = int(candle_count)
        except Exception:
            return 1

        if 0 <= candle_count_value <= 3:
            return candle_count_value + 1

        if 1 <= candle_count_value <= 4:
            return candle_count_value

        return 1

    def _normalize_state_text(self, value) -> str:
        if value is None:
            return ""

        text = str(self._tag_to_python_value(value)).strip().lower()

        if text.startswith("minecraft:"):
            text = text.split(":", 1)[1]

        return text.replace(" ", "_").replace("-", "_")

    def _get_wall_item_name(self, block) -> Optional[str]:
        wall_type = self._get_block_property(
            block,
            (
                "wall_block_type",
                "wall_type",
                "stone_wall_type",
                "wall_material",
                "material",
                "type",
            ),
        )
        wall_type = self._normalize_state_text(wall_type)

        if not wall_type:
            return None

        wall_type = wall_type.removesuffix("_wall")
        return self.WALL_ITEM_BY_TYPE.get(wall_type)

    def _get_door_item_name(self, block) -> Optional[str]:
        door_type = self._get_block_property(
            block,
            (
                "door_type",
                "wood_type",
                "wood",
                "material",
                "type",
            ),
        )
        door_type = self._normalize_state_text(door_type)

        if not door_type:
            return None

        door_type = door_type.removesuffix("_door")
        return self.DOOR_ITEM_BY_TYPE.get(door_type)

    def _get_sign_family_type(self, block) -> str:
        block_key = self._get_namespaced_block_name(block) or ""
        block_key = block_key.split(":", 1)[1] if ":" in block_key else block_key

        sign_type = self._get_block_property(
            block,
            (
                "wood_type",
                "sign_type",
                "hanging_sign_type",
                "material",
                "type",
            ),
        )
        sign_type = self._normalize_state_text(sign_type)

        sign_type_aliases = {
            "darkoak": "dark_oak",
            "paleoak": "pale_oak",
        }
        sign_type = sign_type_aliases.get(sign_type, sign_type)

        if not sign_type or sign_type in ("standing", "wall", "hanging", "sign"):
            sign_type = self._normalize_state_text(block_key)

        if sign_type in ("sign", "standing_sign", "wall_sign"):
            return "oak"

        if sign_type in ("hanging_sign", "wall_hanging_sign"):
            return "oak"

        if sign_type.endswith("_wall_hanging_sign"):
            sign_type = sign_type[:-18]

        if sign_type.endswith("_hanging_sign"):
            sign_type = sign_type[:-13]

        if sign_type.endswith("_wall_sign"):
            sign_type = sign_type[:-10]

        if sign_type.endswith("_standing_sign"):
            sign_type = sign_type[:-14]

        if sign_type.endswith("_sign"):
            sign_type = sign_type[:-5]

        sign_type = sign_type_aliases.get(sign_type, sign_type)
        return sign_type

    def _get_sign_item_name(self, block) -> Optional[str]:
        sign_type = self._get_sign_family_type(block)
        if not sign_type:
            return None
        return self.SIGN_ITEM_BY_TYPE.get(sign_type)

    def _get_hanging_sign_item_name(self, block) -> Optional[str]:
        sign_type = self._get_sign_family_type(block)
        if not sign_type:
            return None
        return self.HANGING_SIGN_ITEM_BY_TYPE.get(sign_type)

    def _get_bars_item_name(self, block) -> str:
        bars_type = self._get_block_property(
            block,
            (
                "bars_type",
                "bar_type",
                "copper_type",
                "oxidization",
                "oxidation",
                "weathering",
                "material",
                "type",
            ),
        )
        bars_type = self._normalize_state_text(bars_type)

        if not bars_type:
            block_key = self._get_namespaced_block_name(block) or ""
            block_key = block_key.split(":", 1)[1] if ":" in block_key else block_key
            bars_type = self._normalize_state_text(block_key)

        bars_type = bars_type.removesuffix("_bars")
        bars_type = bars_type.removesuffix("_bar")

        waxed = self._get_block_property(block, ("waxed", "waxed_bit", "is_waxed"))
        is_waxed = self._is_truthy_state_value(waxed)

        if bars_type in ("bars", "iron", ""):
            return "minecraft:iron_bars"

        if bars_type in ("none", "unweathered", "normal"):
            bars_type = "copper"

        if is_waxed and not bars_type.startswith("waxed_"):
            bars_type = f"waxed_{bars_type}"

        return self.BARS_ITEM_BY_TYPE.get(bars_type, "minecraft:iron_bars")

    def _get_pitcher_crop_item_name(self, block) -> str:
        growth = self._get_block_property(block, ("growth", "age"))

        try:
            growth_value = int(growth)
        except Exception:
            growth_value = -1

        if growth_value >= 4:
            return "minecraft:pitcher_plant"

        return "minecraft:pitcher_pod"

    def _get_item_frame_item_name(self, block, key: str) -> str:
        if key == "minecraft:glow_frame":
            return "minecraft:glow_frame"

        if key == "minecraft:frame":
            return "minecraft:frame"

        glowing = self._get_block_property(block, ("glowing", "glow", "is_glowing"))

        if self._is_truthy_state_value(glowing):
            return "minecraft:glow_frame"

        return "minecraft:frame"

    def _get_banner_item_name(self, block, block_entity) -> str:
        base_color = self._get_block_entity_nbt_value(block_entity, "Base")

        if base_color is None:
            base_color = self._get_block_property(
                block,
                (
                    "base",
                    "Base",
                    "color",
                    "colour",
                    "ground_sign_direction",
                ),
            )

        try:
            base_color_value = int(base_color)
        except Exception:
            base_color_value = 0

        base_color_value = max(0, min(15, base_color_value))
        return f"{self.BANNER_ITEM_PREFIX}{base_color_value}"

    def _is_banner_item_key(self, item_name: str) -> bool:
        return str(item_name).startswith(self.BANNER_ITEM_PREFIX)

    def _make_item_extra_tag(self, item_name: str):
        if not self._is_banner_item_key(item_name):
            return None

        if TAG_Compound is None or TAG_Int is None:
            return None

        tag = TAG_Compound()
        tag["Type"] = TAG_Int(0)
        return tag

    def _get_item_nbt_name_damage(self, item_name: str) -> Tuple[str, int]:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))

        if self._is_banner_item_key(item_name):
            try:
                banner_damage = int(item_name.replace(self.BANNER_ITEM_PREFIX, "", 1))
            except Exception:
                banner_damage = 0
            return "minecraft:banner", max(0, min(15, banner_damage))

        if item_name in self.BED_COLOR_BY_ITEM_NAME:
            color_name = self.BED_COLOR_BY_ITEM_NAME[item_name]
            return "minecraft:bed", self.BED_ITEM_DAMAGE_BY_COLOR.get(color_name, 0)

        if item_name in self.CARPET_COLOR_BY_ITEM_NAME:
            color_name = self.CARPET_COLOR_BY_ITEM_NAME[item_name]
            return "minecraft:carpet", self.BED_ITEM_DAMAGE_BY_COLOR.get(color_name, 0)

        return item_name, 0

    def _get_cached_item_nbt_name_damage(
        self,
        item_name: str,
        item_info_cache: Optional[Dict[str, Tuple[str, int]]] = None,
    ) -> Tuple[str, int]:
        cache_key = str(item_name)

        if item_info_cache is None:
            return self._get_item_nbt_name_damage(cache_key)

        cached = item_info_cache.get(cache_key)
        if cached is not None:
            return cached

        value = self._get_item_nbt_name_damage(cache_key)
        item_info_cache[cache_key] = value
        return value

    def _should_write_item_block_tag(self, item_name: str) -> bool:
        actual_name, _damage = self._get_item_nbt_name_damage(item_name)
        return actual_name not in self.ITEM_FRAME_NO_BLOCK_TAG_ITEMS

    def _classify_block(self, block, block_entity=None) -> Tuple[Optional[str], Optional[str]]:
        key = self._get_namespaced_block_name(block)

        if key is None:
            return None, "unknown_block"

        if key == "minecraft:snow":
            key = "minecraft:snow_layer"
        elif key == "minecraft:snow_block":
            key = "minecraft:snow"

        if key in ("minecraft:item_frame_block", "minecraft:frame", "minecraft:glow_frame"):
            key = self._get_item_frame_item_name(block, key)
        elif key in ("minecraft:banner", "minecraft:standing_banner", "minecraft:wall_banner"):
            key = self._get_banner_item_name(block, block_entity)
        elif (
            key in ("minecraft:sign", "minecraft:standing_sign", "minecraft:wall_sign")
            or key.endswith("_standing_sign")
            or key.endswith("_wall_sign")
        ):
            sign_item = self._get_sign_item_name(block)
            key = sign_item if sign_item else self.ITEM_NAME_OVERRIDES.get(key, key)
        elif (
            key in ("minecraft:hanging_sign", "minecraft:wall_hanging_sign")
            or key.endswith("_hanging_sign")
            or key.endswith("_wall_hanging_sign")
        ):
            hanging_sign_item = self._get_hanging_sign_item_name(block)
            key = hanging_sign_item if hanging_sign_item else self.ITEM_NAME_OVERRIDES.get(key, key)
        elif key == "minecraft:candle_cake" or key.endswith("_candle_cake"):
            key = self._get_candle_cake_item_name(block, key)
        elif key == "minecraft:bars" or key.endswith("_bars"):
            key = self._get_bars_item_name(block)
        else:
            key = self.ITEM_NAME_OVERRIDES.get(key, key)

        if key in self.AIR_BLOCKS or key.endswith(":air"):
            return None, None

        if self._is_upper_half_block(block, key):
            return None, None

        if key == "minecraft:bed":
            bed_color = self._get_bed_color_name(block, block_entity)
            if bed_color:
                key = f"minecraft:{bed_color}_bed"

        if key == "minecraft:carpet":
            carpet_color = self._get_block_color_name(block, block_entity)
            if carpet_color:
                key = f"minecraft:{carpet_color}_carpet"

        if key == "minecraft:wool":
            wool_item = self._get_colored_variant_item_name(
                block,
                self.WOOL_ITEM_BY_COLOR,
                block_entity,
            )
            if wool_item:
                key = wool_item

        if key == "minecraft:concrete":
            concrete_item = self._get_colored_variant_item_name(
                block,
                self.CONCRETE_ITEM_BY_COLOR,
                block_entity,
            )
            if concrete_item:
                key = concrete_item

        if key == "minecraft:concrete_powder":
            concrete_powder_item = self._get_colored_variant_item_name(
                block,
                self.CONCRETE_POWDER_ITEM_BY_COLOR,
                block_entity,
            )
            if concrete_powder_item:
                key = concrete_powder_item

        if key == "minecraft:stained_glass":
            stained_glass_item = self._get_colored_variant_item_name(
                block,
                self.STAINED_GLASS_ITEM_BY_COLOR,
                block_entity,
            )
            if stained_glass_item:
                key = stained_glass_item

        if key == "minecraft:stained_glass_pane":
            stained_glass_pane_item = self._get_colored_variant_item_name(
                block,
                self.STAINED_GLASS_PANE_ITEM_BY_COLOR,
                block_entity,
            )
            if stained_glass_pane_item:
                key = stained_glass_pane_item

        if key == "minecraft:coral_block" or key.endswith("_coral_block"):
            coral_block_item = self._get_coral_block_item_name(block, key)
            if coral_block_item:
                key = coral_block_item

        if key == "minecraft:stained_terracotta":
            terracotta_item = self._get_stained_terracotta_item_name(block, block_entity)
            if terracotta_item:
                key = terracotta_item

        if key == "minecraft:glazed_terracotta":
            glazed_terracotta_item = self._get_glazed_terracotta_item_name(block, block_entity)
            if glazed_terracotta_item:
                key = glazed_terracotta_item

        if key == "minecraft:wall":
            wall_item = self._get_wall_item_name(block)
            if wall_item:
                key = wall_item

        if key == "minecraft:door":
            door_item = self._get_door_item_name(block)
            if door_item:
                key = door_item

        if not self.include_unusual.GetValue() and key in self.CANDLE_CAKE_CANDLE_BY_BLOCK:
            key = "minecraft:cake"

        if key == "minecraft:pitcher_crop":
            key = self._get_pitcher_crop_item_name(block)

        if key == "minecraft:bedrock":
            return None, key

        if key in self.KNOWN_UNSAFE_ITEM_BLOCKS:
            return None, key

        if not self.include_unusual.GetValue() and key in self.DEFAULT_EXCLUDED_BLOCKS:
            return None, key

        return key, None

    def _is_safe_item_key(self, item_name: Optional[str]) -> bool:
        if item_name is None:
            return False

        item_name = str(item_name)
        item_name = self.ITEM_NAME_OVERRIDES.get(item_name, item_name)

        if not item_name.strip():
            return False

        if item_name in self.KNOWN_UNSAFE_ITEM_BLOCKS:
            return False

        if item_name in self.GENERIC_UNSAFE_ITEM_BLOCKS:
            return False

        return True

    def _get_extra_export_items_for_block(self, block) -> List[Tuple[str, int]]:
        if self.include_unusual.GetValue():
            return []

        key = self._get_namespaced_block_name(block)

        if key is None:
            return []

        key = self.ITEM_NAME_OVERRIDES.get(key, key)

        candle_item = self.CANDLE_CAKE_CANDLE_BY_BLOCK.get(key)
        if candle_item:
            return [(candle_item, 1)]

        return []

    def _get_double_slab_export_item(self, item_name: str) -> Optional[str]:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))

        override = self.DOUBLE_SLAB_ITEM_OVERRIDES.get(item_name)
        if override:
            return override

        if item_name.endswith("_double_slab"):
            return item_name[:-len("_double_slab")] + "_slab"

        return None

    def _record_export_count(self, counts: Dict[str, int], item_name: str, amount: int = 1) -> None:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))
        amount = int(amount)

        if not self.include_unusual.GetValue():
            slab_item = self._get_double_slab_export_item(item_name)
            if slab_item:
                item_name = slab_item
                amount *= 2

        if not self._is_safe_item_key(item_name):
            return

        if counts[item_name] == 0:
            self._scan_order.append(item_name)

        counts[item_name] += amount

    def _universal_string(self, value: str):
        if StringTag is not None:
            return StringTag(value)
        if TAG_String is not None:
            return TAG_String(value)
        return value

    def _make_universal_air(self) -> Block:
        return Block("universal_minecraft", "air")

    def _make_universal_chest(self, facing: str = "north", connection: str = "none") -> Block:
        return Block(
            "universal_minecraft",
            "chest",
            {
                "material": self._universal_string("wood"),
                "facing": self._universal_string(facing),
                "connection": self._universal_string(connection),
            },
        )

    def _make_universal_barrel(self, facing: str = "east") -> Block:
        return Block(
            "universal_minecraft",
            "barrel",
            {
                "facing": self._universal_string(facing),
                "open": self._universal_string("false"),
            },
        )

    def _get_storage_entity_name(self) -> str:
        container = self._get_selected_container()

        if container == self.CONTAINER_BARREL:
            return "barrel"

        if container == self.CONTAINER_SHULKER:
            return "shulker_box"

        return "chest"

    def _make_inventory_nbt(
        self,
        stacks: Sequence[Tuple[str, int]],
        pair_position: Optional[Tuple[int, int]] = None,
        pair_lead: Optional[bool] = None,
        item_info_cache: Optional[Dict[str, Tuple[str, int]]] = None,
    ):
        if NBTFile is None:
            raise RuntimeError("amulet_nbt is unavailable in this environment.")
        if TAG_Compound is None or TAG_List is None or TAG_Byte is None or TAG_String is None or TAG_Short is None:
            raise RuntimeError("amulet_nbt tag helpers are unavailable in this environment.")

        the_nbt = TAG_Compound()
        the_nbt["isMovable"] = TAG_Byte(1)
        the_nbt["Findable"] = TAG_Byte(0)
        the_nbt["Items"] = items = TAG_List()

        if pair_position is not None and TAG_Int is not None:
            pair_x, pair_z = pair_position
            the_nbt["pairx"] = TAG_Int(int(pair_x))
            the_nbt["pairz"] = TAG_Int(int(pair_z))

        if pair_lead is not None:
            the_nbt["pairlead"] = TAG_Byte(1 if pair_lead else 0)

        for slot, stack in enumerate(stacks):
            item_name = stack[0]
            count = stack[1]
            nested_items = stack[2] if len(stack) > 2 else None

            if not str(item_name).strip():
                continue

            actual_name, damage_value = self._get_cached_item_nbt_name_damage(item_name, item_info_cache)

            if not actual_name.strip():
                continue

            item = TAG_Compound()
            item["Slot"] = TAG_Byte(int(slot))
            item["Name"] = TAG_String(actual_name)
            item["Count"] = TAG_Byte(int(count))
            item["Damage"] = TAG_Short(int(damage_value))

            if nested_items:
                item["tag"] = self._make_shulker_item_tag(nested_items, item_info_cache)
            else:
                extra_tag = self._make_item_extra_tag(item_name)
                if extra_tag is not None:
                    item["tag"] = extra_tag

            items.append(item)

        return NBTFile(the_nbt)

    def _normalize_display_name_for_audit(self, value: str) -> str:
        value = str(value).strip().lower()

        if value.startswith("minecraft:"):
            value = value.split(":", 1)[1]

        value = value.replace("&", " and ")
        value = re.sub(r"[^a-z0-9]+", "_", value)
        value = re.sub(r"_+", "_", value)
        return value.strip("_")

    def _reset_external_language_operation_state(self) -> None:
        self._external_language_used = {}
        self._found_entries_used = {}
        self._pending_found_entries = {}
        self._found_entries_write_error = ""
        self._found_entries_written_count = 0
        self._external_language_prepared = False
        self._display_name_resolution_cache = {}

    def _release_operation_display_name_caches(self) -> None:
        self._external_language_used = {}
        self._found_entries_used = {}
        self._pending_found_entries = {}
        self._display_name_resolution_cache = {}

    def _normalize_language_alias(self, value: str) -> str:
        value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
        value = value.lower().replace("-", "_").replace(" ", "_")
        value = re.sub(r"_+", "_", value)
        return value.strip("_")

    def _language_key_to_alias(self, language_key: str) -> Optional[str]:
        key = str(language_key).strip()
        if not key.endswith(".name"):
            return None
        if not key.startswith(("tile.", "item.", "block.")):
            return None

        parts = key.split(".")
        if len(parts) < 3:
            return None

        alias_parts = [
            self._normalize_language_alias(part)
            for part in parts[1:-1]
        ]
        alias = "_".join(part for part in alias_parts if part)
        return alias or None

    def _is_safe_language_value(self, value: str) -> bool:
        value = str(value).strip()
        if not value:
            return False
        if "\x00" in value or "\r" in value or "\n" in value:
            return False
        if re.search(r"%\d*\$?[a-zA-Z]", value):
            return False
        return True

    def _parse_display_name_file(
        self,
        path: Path,
    ) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, str]]:
        aliases: Dict[str, Tuple[str, str]] = {}
        raw_entries: Dict[str, str] = {}

        content = path.read_text(encoding="utf-8-sig", errors="replace")
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            language_key, display_name = line.split("=", 1)
            language_key = language_key.strip()
            display_name = display_name.strip()

            alias = self._language_key_to_alias(language_key)
            if alias is None or not self._is_safe_language_value(display_name):
                continue

            if alias not in aliases:
                aliases[alias] = (language_key, display_name)
            if language_key not in raw_entries:
                raw_entries[language_key] = display_name

        return aliases, raw_entries

    def _get_plugin_directory(self) -> Path:
        try:
            return Path(__file__).resolve().parent
        except Exception:
            return Path.cwd()

    def _get_plugin_created_display_name_paths(self) -> List[Path]:
        plugin_file = self._get_plugin_directory() / self.FOUND_ENTRIES_FILENAME
        fallback_directory = Path.home() / ".blocks_to_storage"
        fallback_file = fallback_directory / self.FOUND_ENTRIES_FILENAME

        paths: List[Path] = []
        seen = set()

        for candidate in (
            plugin_file,
            fallback_file,
            fallback_directory,
        ):
            candidate_text = str(candidate)
            if candidate_text in seen:
                continue
            seen.add(candidate_text)

            try:
                if candidate.exists():
                    paths.append(candidate)
            except Exception:
                continue

        return paths

    def _clear_loaded_display_name_data(self) -> None:
        self._external_language_aliases = {}
        self._external_language_raw_entries = {}
        self._found_entries_aliases = {}
        self._found_entries_raw_entries = {}
        self._external_language_loaded_path = ""
        self._external_language_loaded_mtime = None
        self._external_language_load_error = ""
        self._external_language_loaded_count = 0
        self._external_language_used = {}
        self._found_entries_used = {}
        self._pending_found_entries = {}
        self._found_entries_write_error = ""
        self._found_entries_written_count = 0
        self._external_language_prepared = False
        self._display_name_resolution_cache = {}

    def _delete_plugin_created_display_name_data(self, _) -> None:
        found_paths = self._get_plugin_created_display_name_paths()

        if not found_paths:
            wx.MessageBox(
                "No plugin-created display-name files or folders were found.",
                "Blocks to Storage",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        listed_paths = "\n".join(
            f"• {path}"
            for path in found_paths
        )
        message = (
            "Blocks to Storage found the following plugin-created data:\n\n"
            f"{listed_paths}\n\n"
            "Only these listed files and the plugin-created fallback folder "
            "will be deleted. The fallback folder is removed only if it is "
            "empty after its cache file is deleted.\n\n"
            "The plugin, Minecraft language files, worlds and export reports "
            "will not be deleted. You may cancel and use the paths above to "
            "delete files manually or selectively.\n\n"
            "Continue?"
        )

        dialog = wx.MessageDialog(
            self,
            message,
            "Delete plugin-created display-name data?",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )

        try:
            if dialog.ShowModal() != wx.ID_YES:
                return
        finally:
            dialog.Destroy()

        deleted: List[Path] = []
        failed: List[Tuple[Path, str]] = []

        files = [
            path
            for path in found_paths
            if path.name == self.FOUND_ENTRIES_FILENAME
        ]
        folders = [
            path
            for path in found_paths
            if path.name == ".blocks_to_storage"
        ]

        for file_path in files:
            try:
                if file_path.is_file():
                    file_path.unlink()
                    deleted.append(file_path)
            except Exception as exc:
                failed.append((file_path, str(exc)))

        for folder_path in folders:
            try:
                if folder_path.is_dir() and not any(folder_path.iterdir()):
                    folder_path.rmdir()
                    deleted.append(folder_path)
            except Exception as exc:
                failed.append((folder_path, str(exc)))

        self._clear_loaded_display_name_data()

        result_lines = []
        if deleted:
            result_lines.append("Deleted:")
            result_lines.extend(f"• {path}" for path in deleted)

        if failed:
            if result_lines:
                result_lines.append("")
            result_lines.append("Could not delete:")
            result_lines.extend(
                f"• {path}\n  Reason: {reason}"
                for path, reason in failed
            )

        if not result_lines:
            result_lines.append(
                "No files were deleted. They may already have been removed."
            )

        wx.MessageBox(
            "\n".join(result_lines),
            "Blocks to Storage",
            wx.OK | (
                wx.ICON_WARNING
                if failed
                else wx.ICON_INFORMATION
            ),
            self,
        )

    def _get_existing_found_entries_path(self) -> Optional[Path]:
        candidates = [
            self._get_plugin_directory() / self.FOUND_ENTRIES_FILENAME,
            Path.home() / ".blocks_to_storage" / self.FOUND_ENTRIES_FILENAME,
        ]

        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except Exception:
                continue

        return None

    def _get_found_entries_path(self) -> Optional[Path]:
        candidate_directories = [
            self._get_plugin_directory(),
            Path.home() / ".blocks_to_storage",
        ]

        for directory in candidate_directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                test_path = directory / ".btsp_write_test.tmp"
                with test_path.open("w", encoding="utf-8") as handle:
                    handle.write("test")
                test_path.unlink()
                return directory / self.FOUND_ENTRIES_FILENAME
            except Exception:
                continue

        return None

    def _detect_installed_language_file(self) -> Optional[Path]:
        configured = self.language_file_path.GetValue().strip()
        candidates: List[Path] = []

        if configured:
            candidates.append(Path(configured))

        for drive_code in range(ord("C"), ord("Z") + 1):
            drive_root = Path(f"{chr(drive_code)}:/")
            candidates.append(
                drive_root / self.DEFAULT_MINECRAFT_LANGUAGE_RELATIVE_PATH
            )

        seen = set()
        for candidate in candidates:
            candidate_text = str(candidate)
            if candidate_text in seen:
                continue
            seen.add(candidate_text)

            try:
                if candidate.is_file():
                    return candidate
            except Exception:
                continue

        return None

    def _get_selected_language_file(self) -> Optional[Path]:
        if not self.use_installed_language_data.GetValue():
            return None

        configured = self.language_file_path.GetValue().strip()
        if configured:
            configured_path = Path(configured)
            try:
                if configured_path.is_file():
                    return configured_path
            except Exception:
                pass

        if self.auto_detect_language_file.GetValue():
            detected = self._detect_installed_language_file()
            if detected is not None:
                try:
                    self.language_file_path.SetValue(str(detected))
                except Exception:
                    pass
                return detected

        return None

    def _load_found_entries_file(self) -> None:
        self._found_entries_aliases = {}
        self._found_entries_raw_entries = {}

        if not self.use_found_entries_cache.GetValue():
            return

        found_path = self._get_existing_found_entries_path()
        if found_path is None:
            return

        try:
            (
                aliases,
                raw_entries,
            ) = self._parse_display_name_file(found_path)

            if aliases:
                self._found_entries_aliases = aliases
                self._found_entries_raw_entries = raw_entries
        except Exception:
            self._found_entries_aliases = {}
            self._found_entries_raw_entries = {}

    def _ensure_external_language_data_loaded(self) -> bool:
        if self._external_language_prepared:
            return bool(
                self._found_entries_aliases
                or self._external_language_aliases
            )

        self._external_language_prepared = True
        self._external_language_aliases = {}
        self._external_language_raw_entries = {}
        self._external_language_loaded_path = ""
        self._external_language_loaded_mtime = None
        self._external_language_load_error = ""
        self._external_language_loaded_count = 0

        self._load_found_entries_file()

        if not self.use_installed_language_data.GetValue():
            return bool(self._found_entries_aliases)

        language_path = self._get_selected_language_file()
        if language_path is None:
            self._external_language_load_error = "Language file not found."
            return bool(self._found_entries_aliases)

        try:
            modified_time = language_path.stat().st_mtime_ns
            (
                self._external_language_aliases,
                self._external_language_raw_entries,
            ) = self._parse_display_name_file(language_path)
            self._external_language_loaded_path = str(language_path)
            self._external_language_loaded_mtime = modified_time
            self._external_language_loaded_count = len(
                self._external_language_aliases
            )
        except Exception as exc:
            self._external_language_aliases = {}
            self._external_language_raw_entries = {}
            self._external_language_loaded_path = ""
            self._external_language_loaded_mtime = None
            self._external_language_load_error = str(exc)
            self._external_language_loaded_count = 0

        return bool(
            self._found_entries_aliases
            or self._external_language_aliases
        )

    def _get_simulated_missing_item_alias(self) -> str:
        if not self.simulate_missing_display_name.GetValue():
            return ""
        return self._normalize_display_name_for_audit(
            self.simulated_missing_alias.GetValue()
        )

    def _should_ignore_embedded_display_name(self, item_name: str) -> bool:
        simulated_alias = self._get_simulated_missing_item_alias()
        if not simulated_alias:
            return False

        item_alias = self._normalize_display_name_for_audit(item_name)
        return item_alias == simulated_alias

    def _queue_found_entry(
        self,
        language_key: str,
        display_name: str,
    ) -> None:
        if not self.save_found_language_entries.GetValue():
            return
        if language_key in self._found_entries_raw_entries:
            return
        if language_key in self._pending_found_entries:
            return
        if not self._is_safe_language_value(display_name):
            return

        self._pending_found_entries[language_key] = display_name

    def _write_pending_found_entries(self) -> None:
        if not self._pending_found_entries:
            return

        destination = self._get_found_entries_path()
        if destination is None:
            self._found_entries_write_error = "No writable data directory was available."
            return

        existing_entries: Dict[str, str] = {}
        existing_comments: List[str] = []

        if destination.is_file():
            try:
                content = destination.read_text(
                    encoding="utf-8-sig",
                    errors="replace",
                )
                for raw_line in content.splitlines():
                    stripped = raw_line.strip()
                    if stripped.startswith("#"):
                        existing_comments.append(raw_line)
                    elif "=" in raw_line:
                        key, value = raw_line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if key and key not in existing_entries:
                            existing_entries[key] = value
            except Exception as exc:
                self._found_entries_write_error = str(exc)
                return

        added_count = 0
        for key, value in sorted(self._pending_found_entries.items()):
            if key not in existing_entries:
                existing_entries[key] = value
                added_count += 1

        if added_count == 0:
            return

        header = [
            "# Blocks to Storage discovered display-name entries",
            "# Format version: 1",
            "# Source language: en_US",
            "# Entries below were missing from the plugin's embedded table.",
            "",
        ]

        output_lines = header + [
            f"{key}={value}"
            for key, value in sorted(existing_entries.items())
        ]
        output_text = "\n".join(output_lines).rstrip() + "\n"

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=destination.name + ".",
                suffix=".tmp",
                dir=str(destination.parent),
                delete=False,
            ) as handle:
                handle.write(output_text)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except Exception:
                    pass
                temporary_path = Path(handle.name)

            os.replace(str(temporary_path), str(destination))
            self._found_entries_written_count = added_count
            self._found_entries_write_error = ""
            self._load_found_entries_file()
        except Exception as exc:
            self._found_entries_write_error = str(exc)
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except Exception:
                    pass

    def _log_external_language_summary(self) -> None:
        cache_enabled = self.use_found_entries_cache.GetValue()
        installed_enabled = self.use_installed_language_data.GetValue()

        self._log(f"Found Entries cache enabled: {cache_enabled}")
        if cache_enabled:
            self._log(
                f"Found Entries aliases loaded: "
                f"{len(self._found_entries_aliases):,}"
            )
            self._log(
                f"Found Entries entries used: "
                f"{len(self._found_entries_used):,}"
            )

        self._log(f"Installed language fallback enabled: {installed_enabled}")
        if installed_enabled:
            loaded = bool(self._external_language_aliases)
            self._log(f"Installed language file loaded: {loaded}")
            self._log(
                f"Installed language aliases loaded: "
                f"{self._external_language_loaded_count:,}"
            )
            self._log(
                f"Installed language entries used: "
                f"{len(self._external_language_used):,}"
            )
            self._log(
                f"New entries written to {self.FOUND_ENTRIES_FILENAME}: "
                f"{self._found_entries_written_count:,}"
            )

            if self._external_language_load_error:
                self._log(
                    f"Installed language load issue: "
                    f"{self._external_language_load_error}"
                )

            if (
                self.include_display_name_audit.GetValue()
                and loaded
                and self._external_language_loaded_path
            ):
                self._log(
                    f"Installed language file: "
                    f"{Path(self._external_language_loaded_path).name}"
                )

        if self._found_entries_write_error:
            self._log(
                f"{self.FOUND_ENTRIES_FILENAME} write issue: "
                f"{self._found_entries_write_error}"
            )

        if self.include_display_name_audit.GetValue():
            if self._external_language_used:
                self._log("Installed language fallback matches:")
                for item_name, (
                    display_name,
                    language_key,
                    alias,
                ) in sorted(self._external_language_used.items()):
                    self._log(
                        f'  {item_name} -> "{display_name}" '
                        f"[{language_key}], alias {alias}"
                    )

            if self._found_entries_used:
                self._log(f"{self.FOUND_ENTRIES_FILENAME} matches:")
                for item_name, (
                    display_name,
                    language_key,
                    alias,
                ) in sorted(self._found_entries_used.items()):
                    self._log(
                        f'  {item_name} -> "{display_name}" '
                        f"[{language_key}], alias {alias}"
                    )

    def _get_language_display_candidates(self, item_name: str) -> List[str]:
        item_name = str(item_name)
        actual_name, _damage_value = self._get_item_nbt_name_damage(item_name)

        raw_candidates = [
            item_name,
            actual_name,
            self.ABC_SORT_NAME_OVERRIDES.get(item_name, ""),
        ]

        if self._is_banner_item_key(item_name):
            try:
                banner_damage = int(item_name.replace(self.BANNER_ITEM_PREFIX, "", 1))
            except Exception:
                banner_damage = 0

            color_name = self.BANNER_COLOR_NAME_BY_DAMAGE.get(
                max(0, min(15, banner_damage)),
                "white",
            )
            raw_candidates.extend(
                (
                    f"banner_{color_name}",
                    f"{color_name}_banner",
                )
            )

        candidates: List[str] = []
        seen = set()

        def add_candidate(candidate_value: str) -> None:
            normalized = self._normalize_display_name_for_audit(candidate_value)
            if normalized and normalized not in seen:
                candidates.append(normalized)
                seen.add(normalized)

        for raw_candidate in raw_candidates:
            candidate = self._normalize_display_name_for_audit(raw_candidate)
            if not candidate:
                continue

            add_candidate(candidate)

            if candidate.startswith("light_gray_"):
                add_candidate("silver_" + candidate[len("light_gray_"):])

            if "_light_gray" in candidate:
                add_candidate(candidate.replace("_light_gray", "_silver"))

            for color_name in self.BED_COLOR_NAMES:
                color_prefix = color_name + "_"
                if not candidate.startswith(color_prefix):
                    continue

                family_name = candidate[len(color_prefix):]
                language_color = "silver" if color_name == "light_gray" else color_name

                add_candidate(f"{family_name}_{color_name}")
                add_candidate(f"{family_name}_{language_color}")
                add_candidate(f"{language_color}_{family_name}")
                break

            safe_family_aliases = {
                "leaves": "leaves",
                "log": "log",
                "wood": "wood",
                "planks": "planks",
                "slab": "slab",
                "wall": "wall",
                "stairs": "stairs",
                "sign": "sign",
                "trapdoor": "trapdoor",
                "fence": "fence",
                "fence_gate": "fence_gate",
                "button": "button",
                "pressure_plate": "pressure_plate",
                "terracotta": "stained_hardened_clay",
                "stained_glass": "stained_glass",
                "stained_glass_pane": "stained_glass_pane",
            }

            for family_name, language_family in safe_family_aliases.items():
                suffix = "_" + family_name
                if candidate.endswith(suffix):
                    prefix = candidate[:-len(suffix)]
                    if prefix:
                        add_candidate(f"{language_family}_{prefix}")
                        add_candidate(f"{prefix}_{language_family}")

        return candidates

    def _resolve_language_display_name(
        self,
        item_name: str,
    ) -> Optional[Tuple[str, str, str]]:
        item_name = str(item_name)

        if item_name in self._display_name_resolution_cache:
            return self._display_name_resolution_cache[item_name]

        candidates = self._get_language_display_candidates(item_name)
        ignore_embedded = self._should_ignore_embedded_display_name(item_name)

        if not ignore_embedded:
            for candidate in candidates:
                result = self.BEDROCK_EN_US_DISPLAY_NAMES.get(candidate)
                if result is not None:
                    language_key, display_name = result
                    resolved = (
                        str(display_name),
                        str(language_key),
                        candidate,
                    )
                    self._display_name_resolution_cache[item_name] = resolved
                    return resolved

        use_btsp_cache = self.use_found_entries_cache.GetValue()
        use_installed_language = self.use_installed_language_data.GetValue()

        if not use_btsp_cache and not use_installed_language:
            self._display_name_resolution_cache[item_name] = None
            return None

        self._ensure_external_language_data_loaded()

        for candidate in candidates:
            result = self._found_entries_aliases.get(candidate)
            if result is not None:
                language_key, display_name = result
                resolved = (
                    str(display_name),
                    str(language_key),
                    candidate,
                )
                self._found_entries_used[item_name] = resolved
                self._display_name_resolution_cache[item_name] = resolved
                return resolved

        if not use_installed_language:
            self._display_name_resolution_cache[item_name] = None
            return None

        for candidate in candidates:
            result = self._external_language_aliases.get(candidate)
            if result is None:
                continue

            language_key, display_name = result

            embedded_conflict = self.BEDROCK_EN_US_DISPLAY_NAMES.get(candidate)
            if embedded_conflict is not None and not ignore_embedded:
                continue

            resolved = (
                str(display_name),
                str(language_key),
                candidate,
            )
            self._external_language_used[item_name] = resolved
            self._queue_found_entry(str(language_key), str(display_name))
            self._display_name_resolution_cache[item_name] = resolved
            return resolved

        self._display_name_resolution_cache[item_name] = None
        return None

    def _log_display_name_audit(self, counts: Dict[str, int]) -> None:
        resolved_count = 0
        matching_count = 0
        differences = []
        unresolved = []
        manual_review = []

        for item_name in self._get_ordered_item_names(counts):
            current_sort_key = self._normalize_display_name_for_audit(
                self._get_fallback_display_sort_key(item_name)
            )
            actual_name, damage_value = self._get_item_nbt_name_damage(item_name)

            if item_name in self.DISPLAY_NAME_AUDIT_MANUAL_REVIEW:
                resolved = self._resolve_language_display_name(item_name)
                if resolved is None:
                    manual_review.append(
                        (
                            str(item_name),
                            str(actual_name),
                            int(damage_value),
                            current_sort_key,
                            "",
                            "",
                        )
                    )
                else:
                    display_name, language_key, _matched_alias = resolved
                    manual_review.append(
                        (
                            str(item_name),
                            str(actual_name),
                            int(damage_value),
                            current_sort_key,
                            display_name,
                            language_key,
                        )
                    )
                continue

            resolved = self._resolve_language_display_name(item_name)

            if resolved is None:
                unresolved.append(
                    (
                        str(item_name),
                        str(actual_name),
                        int(damage_value),
                        current_sort_key,
                    )
                )
                continue

            display_name, language_key, matched_alias = resolved
            proposed_sort_key = self._normalize_display_name_for_audit(display_name)
            resolved_count += 1

            if proposed_sort_key == current_sort_key:
                matching_count += 1
                continue

            differences.append(
                (
                    str(item_name),
                    display_name,
                    language_key,
                    matched_alias,
                    current_sort_key,
                    proposed_sort_key,
                )
            )

        self._log("Display-name ABC audit:")
        self._log(f"Resolved item groups: {resolved_count:,}")
        self._log(f"Previous fallback sort key already matches: {matching_count:,}")
        self._log(f"Language-based sort-key differences: {len(differences):,}")
        self._log(f"Unresolved item groups: {len(unresolved):,}")
        self._log(f"Manual-review item groups: {len(manual_review):,}")

        if differences:
            self._log("Language-based sort differences:")
            for (
                item_name,
                display_name,
                language_key,
                matched_alias,
                current_sort_key,
                proposed_sort_key,
            ) in differences:
                self._log(
                    f'  {item_name} -> "{display_name}" [{language_key}], '
                    f"alias {matched_alias}, current {current_sort_key}, "
                    f"proposed {proposed_sort_key}"
                )

        if unresolved:
            self._log("Unresolved display names:")
            for item_name, actual_name, damage_value, current_sort_key in unresolved:
                self._log(
                    f"  {item_name} -> {actual_name}, damage {damage_value}, "
                    f"current {current_sort_key}"
                )

        if manual_review:
            self._log("Display names requiring manual review:")
            for (
                item_name,
                actual_name,
                damage_value,
                current_sort_key,
                display_name,
                language_key,
            ) in manual_review:
                if display_name:
                    self._log(
                        f'  {item_name} -> "{display_name}" [{language_key}], '
                        f"actual {actual_name}, damage {damage_value}, "
                        f"current {current_sort_key}"
                    )
                else:
                    self._log(
                        f"  {item_name} -> unresolved, actual {actual_name}, "
                        f"damage {damage_value}, current {current_sort_key}"
                    )

    def _normalize_abc_sort_text(self, display_name: str) -> str:
        display_name = str(display_name).strip().lower()

        if display_name.startswith("minecraft:"):
            display_name = display_name.split(":", 1)[1]

        display_name = display_name.replace(" ", "_").replace("-", "_")
        display_name = self.COLOR_NAME_ALIASES.get(display_name, display_name)

        if display_name.startswith("silver_"):
            display_name = "light_gray_" + display_name[len("silver_"):]

        while "__" in display_name:
            display_name = display_name.replace("__", "_")

        return display_name

    def _get_fallback_display_sort_key(self, item_name: str) -> str:
        item_name = str(item_name)
        display_name = self.ABC_SORT_NAME_OVERRIDES.get(item_name, item_name)
        return self._normalize_abc_sort_text(display_name)

    def _get_display_sort_key(self, item_name: str) -> str:
        item_name = str(item_name)

        if self._is_banner_item_key(item_name):
            try:
                banner_damage = int(item_name.replace(self.BANNER_ITEM_PREFIX, "", 1))
            except Exception:
                banner_damage = 0

            color_name = self.BANNER_COLOR_NAME_BY_DAMAGE.get(
                max(0, min(15, banner_damage)),
                "banner",
            )
            return self._normalize_abc_sort_text(f"{color_name}_banner")

        if item_name not in self.DISPLAY_NAME_AUDIT_MANUAL_REVIEW:
            resolved = self._resolve_language_display_name(item_name)
            if resolved is not None:
                display_name, _language_key, _matched_alias = resolved
                language_sort_key = self._normalize_display_name_for_audit(display_name)
                if language_sort_key:
                    return language_sort_key

        return self._get_fallback_display_sort_key(item_name)

    def _get_item_sort_key(self, item_name: str) -> str:
        return self._get_display_sort_key(item_name)

    def _get_ordered_item_names(self, counts: Dict[str, int]) -> List[str]:
        if self.alphabetical_order.GetValue():
            return sorted(
                counts.keys(),
                key=lambda item_name: (self._get_item_sort_key(item_name), str(item_name)),
            )

        ordered: List[str] = []
        seen = set()

        for item_name in self._scan_order:
            if item_name in counts and item_name not in seen:
                ordered.append(item_name)
                seen.add(item_name)

        for item_name in counts.keys():
            if item_name not in seen:
                ordered.append(item_name)
                seen.add(item_name)

        return ordered

    def _get_container_slot_count(self) -> int:
        if self._get_selected_container() == self.CONTAINER_CHEST and self.use_double_chests.GetValue():
            return self.DOUBLE_CHEST_SLOT_COUNT
        return self.SINGLE_CONTAINER_SLOT_COUNT

    def _use_nested_shulker_storage(self) -> bool:
        if not hasattr(self, "use_nested_shulker_storage"):
            return False

        if self._get_selected_container() == self.CONTAINER_SHULKER:
            return False

        return bool(self.use_nested_shulker_storage.GetValue())

    def _get_nested_shulker_item_name(self) -> str:
        color = "default"

        try:
            color = self.nested_shulker_color_choice.GetStringSelection()
        except Exception:
            pass

        if not color or color == "default":
            return "minecraft:undyed_shulker_box"

        return f"minecraft:{color}_shulker_box"

    def _get_nested_shulker_mode(self) -> str:
        try:
            mode = self.nested_shulker_mode_choice.GetStringSelection()
        except Exception:
            mode = ""

        if not mode:
            return self.NESTED_SHULKER_MODE_PRACTICAL

        return mode

    def _should_pack_stacks_into_nested_shulkers(
        self,
        item_name: str,
        stacks: Sequence[Tuple[str, int]],
        mode: Optional[str] = None,
    ) -> bool:
        if self._is_shulker_item_name(item_name):
            return False

        if not stacks:
            return False

        if mode is None:
            mode = self._get_nested_shulker_mode()

        if mode == self.NESTED_SHULKER_MODE_COMPACT:
            return True

        return len(stacks) > self.SHULKER_BOX_SLOT_COUNT

    def _is_shulker_item_name(self, item_name: str) -> bool:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))
        return item_name == "minecraft:shulker_box" or item_name.endswith("_shulker_box")

    def _make_shulker_item_tag(
        self,
        nested_items: Sequence[Tuple[str, int]],
        item_info_cache: Optional[Dict[str, Tuple[str, int]]] = None,
    ):
        if TAG_Compound is None or TAG_List is None or TAG_Byte is None or TAG_String is None or TAG_Short is None:
            raise RuntimeError("amulet_nbt tag helpers are unavailable in this environment.")

        tag = TAG_Compound()
        tag["Items"] = items = TAG_List()

        for slot, nested_stack in enumerate(nested_items):
            item_name = nested_stack[0]
            count = nested_stack[1]

            if not str(item_name).strip():
                continue

            actual_name, damage_value = self._get_cached_item_nbt_name_damage(item_name, item_info_cache)

            if not actual_name.strip():
                continue

            item = TAG_Compound()
            item["Slot"] = TAG_Byte(int(slot))
            item["Name"] = TAG_String(actual_name)
            item["Count"] = TAG_Byte(int(count))
            item["Damage"] = TAG_Short(int(damage_value))

            extra_tag = self._make_item_extra_tag(item_name)
            if extra_tag is not None:
                item["tag"] = extra_tag

            items.append(item)

        return tag

    def _pack_stacks_into_nested_shulker_items(
        self,
        stacks: Sequence[Tuple[str, int]],
        shulker_item_name: Optional[str] = None,
    ) -> List[Tuple[str, int, List[Tuple[str, int]]]]:
        if shulker_item_name is None:
            shulker_item_name = self._get_nested_shulker_item_name()

        stack_list = list(stacks)
        return [
            (shulker_item_name, 1, list(stack_list[index:index + self.SHULKER_BOX_SLOT_COUNT]))
            for index in range(0, len(stack_list), self.SHULKER_BOX_SLOT_COUNT)
        ]

    def _count_nested_shulker_items(self, inventories: Sequence[Sequence[Tuple]]) -> int:
        total = 0

        for inventory in inventories:
            for stack in inventory:
                if len(stack) > 2:
                    total += 1

        return total

    def _get_item_stack_limit(self, item_name: str) -> int:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))
        actual_name, _damage_value = self._get_item_nbt_name_damage(item_name)

        if item_name in self.NON_STACKABLE_ITEMS or actual_name in self.NON_STACKABLE_ITEMS:
            return 1

        if item_name in self.BED_COLOR_BY_ITEM_NAME:
            return 1

        if self._is_shulker_item_name(item_name):
            return 1

        return self.ITEM_STACK_LIMIT

    def _split_into_stacks(self, item_name: str, total_count: int) -> List[Tuple[str, int]]:
        item_name = self.ITEM_NAME_OVERRIDES.get(item_name, item_name)

        if not self._is_safe_item_key(item_name):
            return []

        stack_limit = self._get_item_stack_limit(item_name)
        stack_limit = max(1, min(self.ITEM_STACK_LIMIT, int(stack_limit)))

        remaining = int(total_count)
        if remaining <= 0:
            return []

        full_stacks, leftover = divmod(remaining, stack_limit)
        stacks = [(item_name, stack_limit)] * full_stacks

        if leftover:
            stacks.append((item_name, leftover))

        return stacks

    def _pack_stacks_into_containers(
        self,
        stacks: Sequence[Tuple[str, int]],
        slot_count: int,
    ) -> List[List[Tuple[str, int]]]:
        slot_count = max(1, int(slot_count))
        stack_list = list(stacks)

        return [
            list(stack_list[index:index + slot_count])
            for index in range(0, len(stack_list), slot_count)
        ]

    def _build_container_payloads_and_group_starts(
        self,
        counts: Dict[str, int],
    ) -> Tuple[List[List[Tuple]], List[Tuple[str, int]]]:
        if self._use_nested_shulker_storage():
            return self._build_nested_shulker_payloads_and_group_starts(counts)

        payloads: List[List[Tuple]] = []
        group_starts: List[Tuple[str, int]] = []
        slot_count = self._get_container_slot_count()
        item_names = self._get_ordered_item_names(counts)

        if self.separate_types.GetValue():
            for item_name in item_names:
                stacks = self._split_into_stacks(item_name, counts[item_name])
                if not stacks:
                    continue
                group_starts.append((item_name, len(payloads)))
                payloads.extend(
                    self._pack_stacks_into_containers(
                        stacks,
                        slot_count,
                    )
                )
        else:
            all_stacks: List[Tuple[str, int]] = []
            for item_name in item_names:
                all_stacks.extend(self._split_into_stacks(item_name, counts[item_name]))
            payloads = self._pack_stacks_into_containers(all_stacks, slot_count)

        return payloads, group_starts

    def _build_nested_shulker_payloads_and_group_starts(
        self,
        counts: Dict[str, int],
    ) -> Tuple[List[List[Tuple]], List[Tuple[str, int]]]:
        payloads: List[List[Tuple]] = []
        group_starts: List[Tuple[str, int]] = []
        slot_count = self._get_container_slot_count()
        item_names = self._get_ordered_item_names(counts)
        nested_mode = self._get_nested_shulker_mode()
        nested_shulker_item_name = self._get_nested_shulker_item_name()

        if self.separate_types.GetValue():
            for item_name in item_names:
                stacks = self._split_into_stacks(item_name, counts[item_name])
                if not stacks:
                    continue

                if self._should_pack_stacks_into_nested_shulkers(item_name, stacks, nested_mode):
                    main_entries = self._pack_stacks_into_nested_shulker_items(stacks, nested_shulker_item_name)
                else:
                    main_entries = stacks

                if not main_entries:
                    continue

                group_starts.append((item_name, len(payloads)))
                payloads.extend(self._pack_stacks_into_containers(main_entries, slot_count))
        else:
            all_main_entries: List[Tuple] = []

            for item_name in item_names:
                stacks = self._split_into_stacks(item_name, counts[item_name])
                if not stacks:
                    continue

                if self._should_pack_stacks_into_nested_shulkers(item_name, stacks, nested_mode):
                    all_main_entries.extend(self._pack_stacks_into_nested_shulker_items(stacks, nested_shulker_item_name))
                else:
                    all_main_entries.extend(stacks)

            payloads = self._pack_stacks_into_containers(all_main_entries, slot_count)

        return payloads, group_starts

    def _get_chunk(self, cx: int, cz: int):
        attempts = (
            lambda: self.world.get_chunk(cx, cz, self.canvas.dimension),
            lambda: self.world.get_chunk(cx, cz),
            lambda: self.world.get_chunk(self.canvas.dimension, cx, cz),
        )

        last_error = None
        for attempt in attempts:
            try:
                chunk = attempt()
                if chunk is not None:
                    return chunk
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f"Could not load chunk ({cx}, {cz}): {last_error}")

    def _chunk_coords(self, x: int, z: int) -> Tuple[int, int]:
        return x // 16, z // 16

    def _local_coords(self, x: int, z: int) -> Tuple[int, int]:
        return x % 16, z % 16

    def _try_get_palette_block(self, palette, block_id):
        attempts = (
            lambda: palette[block_id],
            lambda: palette.get_block(block_id),
            lambda: palette.block(block_id),
            lambda: palette.get(block_id),
        )

        last_error = None
        for attempt in attempts:
            try:
                block = attempt()
                if block is not None:
                    return block
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f"Could not read block from palette id {block_id}: {last_error}")

    def _get_block_direct_from_chunk(self, chunk, x: int, y: int, z: int):
        dx, dz = self._local_coords(x, z)
        block_id = chunk.blocks[dx, y, dz]
        return self._try_get_palette_block(chunk.block_palette, block_id)

    def _get_block_for_scan(self, x: int, y: int, z: int, chunk_cache: Dict[Tuple[int, int], object]):
        if self.fast_direct_scan.GetValue() and not self._fast_scan_failed:
            try:
                cx, cz = self._chunk_coords(x, z)
                key = (cx, cz)

                if key not in chunk_cache:
                    chunk_cache[key] = self._get_chunk(cx, cz)

                chunk = chunk_cache[key]
                return self._get_block_direct_from_chunk(chunk, x, y, z)
            except Exception as exc:
                self._fast_scan_failed = True
                self._fast_scan_fail_reason = str(exc)
                self._log(f"Fast direct chunk scan failed. Falling back to safe scan. Reason: {exc}")

        return self._get_block_safe_for_scan(x, y, z)

    def _get_block_safe_for_scan(self, x: int, y: int, z: int):
        block, _ent = self.world.get_version_block(
            x,
            y,
            z,
            self.canvas.dimension,
            (self._world_platform, self._world_version),
        )
        return block

    def _get_block_and_entity_safe_for_scan(self, x: int, y: int, z: int):
        block, ent = self.world.get_version_block(
            x,
            y,
            z,
            self.canvas.dimension,
            (self._world_platform, self._world_version),
        )
        return block, ent

    def _write_universal_block_to_chunk(
        self,
        chunk,
        x: int,
        y: int,
        z: int,
        universal_block: Block,
        universal_block_entity: Optional[BlockEntity] = None,
    ) -> None:
        dx, dz = self._local_coords(x, z)

        block_id = chunk.block_palette.get_add_block(universal_block)
        chunk.blocks[dx, y, dz] = block_id

        if universal_block_entity is None:
            try:
                chunk.block_entities.pop((x, y, z), None)
            except Exception:
                try:
                    if (x, y, z) in chunk.block_entities:
                        del chunk.block_entities[(x, y, z)]
                except Exception:
                    pass
        else:
            chunk.block_entities[(x, y, z)] = universal_block_entity

        try:
            chunk.changed = True
        except Exception:
            pass

    def _write_air_direct_to_chunk(
        self,
        chunk,
        x: int,
        y: int,
        z: int,
        air_id,
    ) -> None:
        dx, dz = self._local_coords(x, z)
        chunk.blocks[dx, y, dz] = air_id

        try:
            chunk.block_entities.pop((x, y, z), None)
        except Exception:
            try:
                if (x, y, z) in chunk.block_entities:
                    del chunk.block_entities[(x, y, z)]
            except Exception:
                pass

        try:
            chunk.changed = True
        except Exception:
            pass

    def _scan_selection(self):
        counts: Dict[str, int] = collections.defaultdict(int)
        skipped_counts: Dict[str, int] = collections.defaultdict(int)
        skipped_by_reason: Dict[str, Dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))
        protected_positions: Set[Tuple[int, int, int]] = set()

        self._scan_order = []
        self._fast_scan_failed = False
        self._fast_scan_fail_reason = ""
        self._ambiguous_fast_scan_fallbacks = 0

        min_x = min_y = min_z = None
        max_x = max_y = max_z = None

        scanned_positions = 0
        scan_progress_start = time.perf_counter()
        chunk_cache: Dict[Tuple[int, int], object] = {}

        for x, y, z in self._iter_selected_positions():
            scanned_positions += 1

            if scanned_positions % self.PROGRESS_INTERVAL == 0:
                elapsed = time.perf_counter() - scan_progress_start
                self._log(
                    f"Scan progress: {scanned_positions:,} selected positions checked "
                    f"({self._format_seconds(elapsed)} elapsed)"
                )

            if min_x is None:
                min_x = max_x = x
                min_y = max_y = y
                min_z = max_z = z
            else:
                min_x = x if x < min_x else min_x
                min_y = y if y < min_y else min_y
                min_z = z if z < min_z else min_z
                max_x = x if x > max_x else max_x
                max_y = y if y > max_y else max_y
                max_z = z if z > max_z else max_z

            block = self._get_block_for_scan(x, y, z, chunk_cache)
            scan_block = block
            raw_scan_key = self._get_namespaced_block_name(block)
            export_key, skipped_key = self._classify_block(block)

            raw_scan_needs_safe_lookup = self._needs_safe_block_lookup(raw_scan_key)
            ambiguous_lookup_needed = (
                export_key in self.AMBIGUOUS_FAST_SCAN_BLOCKS
                or raw_scan_key in self.AMBIGUOUS_FAST_SCAN_BLOCKS
            )
            needs_safe_lookup = (
                raw_scan_needs_safe_lookup
                or ambiguous_lookup_needed
                or self._needs_safe_block_lookup(export_key)
                or self._needs_safe_block_lookup(skipped_key)
            )

            if needs_safe_lookup:
                try:
                    safe_block, safe_block_entity = self._get_block_and_entity_safe_for_scan(x, y, z)
                    safe_export_key, safe_skipped_key = self._classify_block(safe_block, safe_block_entity)

                    if safe_export_key is not None or safe_skipped_key is not None:
                        scan_block = safe_block
                        export_key = safe_export_key
                        skipped_key = safe_skipped_key
                        if ambiguous_lookup_needed:
                            self._ambiguous_fast_scan_fallbacks += 1
                    elif export_key in self.STATE_SENSITIVE_SCAN_BLOCKS or skipped_key in self.STATE_SENSITIVE_SCAN_BLOCKS:
                        export_key = safe_export_key
                        skipped_key = safe_skipped_key
                except Exception:
                    pass

            if export_key is not None and not self._is_safe_item_key(export_key):
                skipped_key = export_key
                export_key = None

            extra_export_items = self._get_extra_export_items_for_block(scan_block)

            if skipped_key == "minecraft:bedrock" and self.preserve_bedrock.GetValue():
                protected_positions.add((x, y, z))

            if skipped_key is not None:
                skipped_reason = self._get_skipped_block_reason(skipped_key)
                skipped_counts[skipped_key] += 1
                skipped_by_reason[skipped_reason][skipped_key] += 1
                for extra_item_name, extra_amount in extra_export_items:
                    self._record_export_count(counts, extra_item_name, extra_amount)
                continue

            if export_key is not None:
                export_amount = self._get_candle_export_amount(scan_block, export_key)
                self._record_export_count(counts, export_key, export_amount)

            for extra_item_name, extra_amount in extra_export_items:
                self._record_export_count(counts, extra_item_name, extra_amount)

        if min_x is None:
            return counts, skipped_counts, skipped_by_reason, protected_positions, None, scanned_positions

        return counts, skipped_counts, skipped_by_reason, protected_positions, (min_x, min_y, min_z, max_x, max_y, max_z), scanned_positions

    def _is_protected_position(
        self,
        x: int,
        y: int,
        z: int,
        protected_positions: Set[Tuple[int, int, int]],
    ) -> bool:
        return (x, y, z) in protected_positions

    def _get_group_spacing_value(self) -> int:
        try:
            return max(0, min(self.MAX_GROUP_SPACING, int(self.group_spacing.GetValue())))
        except Exception:
            return self.DEFAULT_GROUP_SPACING

    def _get_front_line_stride(self) -> int:
        if self.separate_types.GetValue() and self.add_group_item_frames.GetValue():
            return 3
        return 1

    def _get_group_ranges(
        self,
        group_starts: Sequence[Tuple[str, int]],
        container_count: int,
    ) -> List[Tuple[str, int, int]]:
        ranges: List[Tuple[str, int, int]] = []

        for index, (item_name, start_index) in enumerate(group_starts):
            if index + 1 < len(group_starts):
                end_index = int(group_starts[index + 1][1])
            else:
                end_index = int(container_count)
            ranges.append((item_name, int(start_index), end_index))

        return ranges

    def _plan_single_storage_positions(
        self,
        container_count: int,
        bounds: Tuple[int, int, int, int, int, int],
        protected_positions: Set[Tuple[int, int, int]],
    ) -> List[Tuple[int, int, int]]:
        min_x, min_y, min_z, max_x, max_y, max_z = bounds

        x_len = (max_x - min_x) + 1
        y_len = (max_y - min_y) + 1
        z_len = (max_z - min_z) + 1

        stack_height = int(self.stack_height.GetValue())
        stack_height = max(1, min(self.MAX_STACK_HEIGHT, stack_height))
        stack_height = min(stack_height, y_len)

        if x_len <= z_len:
            primary_axis = "x"
            primary_len = x_len
            secondary_len = z_len
        else:
            primary_axis = "z"
            primary_len = z_len
            secondary_len = x_len

        positions: List[Tuple[int, int, int]] = []

        if container_count <= 0:
            return positions

        for line_index in range(secondary_len):
            for visual_primary_index in range(primary_len):
                primary_offset = self._get_primary_offset_for_visual_index(
                    primary_axis,
                    visual_primary_index,
                    line_index,
                    primary_len,
                    bounds,
                )

                for vertical_offset in range(stack_height):
                    y = min_y + vertical_offset

                    if primary_axis == "x":
                        x = min_x + primary_offset
                        z = min_z + line_index
                    else:
                        x = min_x + line_index
                        z = min_z + primary_offset

                    if self._is_protected_position(x, y, z, protected_positions):
                        continue

                    positions.append((x, y, z))

                    if len(positions) >= container_count:
                        return positions

        raise RuntimeError(
            f"Not enough non-protected room in the selected area for {container_count} storage containers. "
            f"Protected bedrock positions may be blocking storage placement."
        )

    def _plan_single_storage_positions_by_group(
        self,
        group_starts: Sequence[Tuple[str, int]],
        container_count: int,
        bounds: Tuple[int, int, int, int, int, int],
        protected_positions: Set[Tuple[int, int, int]],
    ) -> List[Tuple[int, int, int]]:
        min_x, min_y, min_z, max_x, max_y, max_z = bounds

        x_len = (max_x - min_x) + 1
        y_len = (max_y - min_y) + 1
        z_len = (max_z - min_z) + 1

        stack_height = int(self.stack_height.GetValue())
        stack_height = max(1, min(self.MAX_STACK_HEIGHT, stack_height))
        stack_height = min(stack_height, y_len)

        if x_len <= z_len:
            primary_axis = "x"
            primary_len = x_len
            secondary_len = z_len
        else:
            primary_axis = "z"
            primary_len = z_len
            secondary_len = x_len

        group_spacing = self._get_group_spacing_value()
        front_line_stride = self._get_front_line_stride()

        if group_spacing >= primary_len and len(group_starts) > 1:
            raise RuntimeError(
                "Not enough side room for the selected separated-group spacing. "
                f"Primary row length is {primary_len} block(s), but spacing is set to {group_spacing}. "
                "Increase the selected area size or reduce the spacing between separated groups."
            )

        positions: List[Tuple[int, int, int]] = [None] * container_count
        group_ranges = self._get_group_ranges(group_starts, container_count)

        current_line = 0
        current_primary = 0

        def make_pos(visual_primary_index: int, line_index: int, vertical_offset: int) -> Tuple[int, int, int]:
            primary_offset = self._get_primary_offset_for_visual_index(
                primary_axis,
                visual_primary_index,
                line_index,
                primary_len,
                bounds,
            )
            y = min_y + vertical_offset
            if primary_axis == "x":
                return min_x + primary_offset, y, min_z + line_index
            return min_x + line_index, y, min_z + primary_offset

        for _item_name, start_index, end_index in group_ranges:
            group_needed = end_index - start_index
            group_placed = 0

            while group_placed < group_needed:
                if current_line >= secondary_len:
                    raise RuntimeError(
                        "Not enough room in the selected area for separated storage groups with the current spacing. "
                        "Increase the selected area size, reduce the spacing between separated groups, reduce vertical stack height, or disable item frames."
                    )

                if current_primary >= primary_len:
                    current_line += front_line_stride
                    current_primary = 0
                    continue

                for vertical_offset in range(stack_height):
                    if group_placed >= group_needed:
                        break

                    x, y, z = make_pos(current_primary, current_line, vertical_offset)

                    if self._is_protected_position(x, y, z, protected_positions):
                        continue

                    positions[start_index + group_placed] = (x, y, z)
                    group_placed += 1

                current_primary += 1

            current_primary += group_spacing
            if current_primary >= primary_len:
                current_line += front_line_stride
                current_primary = 0

        if any(pos is None for pos in positions):
            raise RuntimeError("Storage placement failed because one or more separated group positions could not be planned.")

        return positions

    def _choose_double_chest_axis(self, x_len: int, z_len: int) -> str:
        if x_len >= 2 and z_len >= 2:
            if x_len <= z_len:
                return "x"
            return "z"

        if x_len >= 2:
            return "x"

        if z_len >= 2:
            return "z"

        raise RuntimeError("Not enough horizontal room for double chests.")

    def _plan_double_chest_positions(
        self,
        container_count: int,
        bounds: Tuple[int, int, int, int, int, int],
        protected_positions: Set[Tuple[int, int, int]],
    ) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int], str]]:
        min_x, min_y, min_z, max_x, max_y, max_z = bounds

        x_len = (max_x - min_x) + 1
        y_len = (max_y - min_y) + 1
        z_len = (max_z - min_z) + 1

        stack_height = int(self.stack_height.GetValue())
        stack_height = max(1, min(self.MAX_STACK_HEIGHT, stack_height))
        stack_height = min(stack_height, y_len)

        pairs: List[Tuple[Tuple[int, int, int], Tuple[int, int, int], str]] = []

        if container_count <= 0:
            return pairs

        pair_axis = self._choose_double_chest_axis(x_len, z_len)

        if pair_axis == "x":
            primary_block_len = x_len
            primary_len = x_len // 2
            secondary_len = z_len
        else:
            primary_block_len = z_len
            primary_len = z_len // 2
            secondary_len = x_len

        for line_index in range(secondary_len):
            for visual_pair_index in range(primary_len):
                visual_primary_block = visual_pair_index * 2
                primary_block_offset = self._get_double_chest_primary_offset_for_visual_index(
                    pair_axis,
                    visual_primary_block,
                    line_index,
                    primary_block_len,
                    bounds,
                )

                for vertical_offset in range(stack_height):
                    y = min_y + vertical_offset

                    if pair_axis == "x":
                        x1 = min_x + primary_block_offset
                        z1 = min_z + line_index
                        x2 = x1 + 1
                        z2 = z1
                    else:
                        x1 = min_x + line_index
                        z1 = min_z + primary_block_offset
                        x2 = x1
                        z2 = z1 + 1

                    if self._is_protected_position(x1, y, z1, protected_positions):
                        continue

                    if self._is_protected_position(x2, y, z2, protected_positions):
                        continue

                    pairs.append(((x1, y, z1), (x2, y, z2), pair_axis))

                    if len(pairs) >= container_count:
                        return pairs

        raise RuntimeError(
            f"Not enough non-protected room in the selected area for {container_count} double chests. "
            f"Protected bedrock positions may be blocking storage placement."
        )

    def _plan_double_chest_positions_by_group(
        self,
        group_starts: Sequence[Tuple[str, int]],
        container_count: int,
        bounds: Tuple[int, int, int, int, int, int],
        protected_positions: Set[Tuple[int, int, int]],
    ) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int], str]]:
        min_x, min_y, min_z, max_x, max_y, max_z = bounds

        x_len = (max_x - min_x) + 1
        y_len = (max_y - min_y) + 1
        z_len = (max_z - min_z) + 1

        stack_height = int(self.stack_height.GetValue())
        stack_height = max(1, min(self.MAX_STACK_HEIGHT, stack_height))
        stack_height = min(stack_height, y_len)

        pair_axis = self._choose_double_chest_axis(x_len, z_len)

        if pair_axis == "x":
            primary_block_len = x_len
            secondary_len = z_len
        else:
            primary_block_len = z_len
            secondary_len = x_len

        group_spacing = self._get_group_spacing_value()
        front_line_stride = self._get_front_line_stride()

        if group_spacing >= primary_block_len and len(group_starts) > 1:
            raise RuntimeError(
                "Not enough side room for the selected separated-group spacing. "
                f"Primary row length is {primary_block_len} block(s), but spacing is set to {group_spacing}. "
                "Increase the selected area size or reduce the spacing between separated groups."
            )

        pairs: List[Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int], str]]] = [None] * container_count
        group_ranges = self._get_group_ranges(group_starts, container_count)

        current_line = 0
        current_primary_block = 0

        def make_pair(visual_primary_block: int, line_index: int, vertical_offset: int):
            primary_block_offset = self._get_double_chest_primary_offset_for_visual_index(
                pair_axis,
                visual_primary_block,
                line_index,
                primary_block_len,
                bounds,
            )
            y = min_y + vertical_offset
            if pair_axis == "x":
                x1 = min_x + primary_block_offset
                z1 = min_z + line_index
                return (x1, y, z1), (x1 + 1, y, z1), pair_axis
            x1 = min_x + line_index
            z1 = min_z + primary_block_offset
            return (x1, y, z1), (x1, y, z1 + 1), pair_axis

        for _item_name, start_index, end_index in group_ranges:
            group_needed = end_index - start_index
            group_placed = 0

            while group_placed < group_needed:
                if current_line >= secondary_len:
                    raise RuntimeError(
                        "Not enough room in the selected area for separated double-chest groups with the current spacing. "
                        "Increase the selected area size, reduce the spacing between separated groups, reduce vertical stack height, or disable item frames."
                    )

                if current_primary_block + 1 >= primary_block_len:
                    current_line += front_line_stride
                    current_primary_block = 0
                    continue

                for vertical_offset in range(stack_height):
                    if group_placed >= group_needed:
                        break

                    first_pos, second_pos, planned_pair_axis = make_pair(current_primary_block, current_line, vertical_offset)
                    x1, y1, z1 = first_pos
                    x2, y2, z2 = second_pos

                    if self._is_protected_position(x1, y1, z1, protected_positions):
                        continue

                    if self._is_protected_position(x2, y2, z2, protected_positions):
                        continue

                    pairs[start_index + group_placed] = (first_pos, second_pos, planned_pair_axis)
                    group_placed += 1

                current_primary_block += 2

            current_primary_block += group_spacing
            if current_primary_block + 1 >= primary_block_len:
                current_line += front_line_stride
                current_primary_block = 0

        if any(pair is None for pair in pairs):
            raise RuntimeError("Double-chest placement failed because one or more separated group positions could not be planned.")

        return pairs

    def _clear_selection_safe(
        self,
        protected_positions: Set[Tuple[int, int, int]],
    ) -> Tuple[int, int]:
        universal_air = self._make_universal_air()
        chunk_cache = {}

        checked_positions = 0
        preserved_bedrock = 0
        cleared_blocks = 0
        clear_progress_start = time.perf_counter()

        for x, y, z in self._iter_selected_positions():
            checked_positions += 1

            if checked_positions % self.PROGRESS_INTERVAL == 0:
                elapsed = time.perf_counter() - clear_progress_start
                self._log(
                    f"Clear progress: {checked_positions:,} selected positions checked "
                    f"({self._format_seconds(elapsed)} elapsed)"
                )

            if self._is_protected_position(x, y, z, protected_positions):
                preserved_bedrock += 1
                continue

            cx, cz = self._chunk_coords(x, z)
            key = (cx, cz)

            if key not in chunk_cache:
                chunk_cache[key] = self._get_chunk(cx, cz)

            chunk = chunk_cache[key]
            self._write_universal_block_to_chunk(
                chunk,
                x,
                y,
                z,
                universal_air,
                None,
            )
            cleared_blocks += 1

        return preserved_bedrock, cleared_blocks

    def _clear_selection_fast(
        self,
        protected_positions: Set[Tuple[int, int, int]],
    ) -> Tuple[int, int]:
        universal_air = self._make_universal_air()
        chunk_cache = {}
        air_id_cache = {}

        checked_positions = 0
        preserved_bedrock = 0
        cleared_blocks = 0
        clear_progress_start = time.perf_counter()

        for x, y, z in self._iter_selected_positions():
            checked_positions += 1

            if checked_positions % self.PROGRESS_INTERVAL == 0:
                elapsed = time.perf_counter() - clear_progress_start
                self._log(
                    f"Clear progress: {checked_positions:,} selected positions checked "
                    f"({self._format_seconds(elapsed)} elapsed)"
                )

            if self._is_protected_position(x, y, z, protected_positions):
                preserved_bedrock += 1
                continue

            cx, cz = self._chunk_coords(x, z)
            key = (cx, cz)

            if key not in chunk_cache:
                chunk_cache[key] = self._get_chunk(cx, cz)

            chunk = chunk_cache[key]

            if key not in air_id_cache:
                air_id_cache[key] = chunk.block_palette.get_add_block(universal_air)

            self._write_air_direct_to_chunk(
                chunk,
                x,
                y,
                z,
                air_id_cache[key],
            )
            cleared_blocks += 1

        return preserved_bedrock, cleared_blocks

    def _clear_selection_in_chunks(
        self,
        protected_positions: Set[Tuple[int, int, int]],
    ) -> Tuple[int, int, str]:
        self._fast_clear_failed = False
        self._fast_clear_fail_reason = ""

        if self.fast_direct_clear.GetValue():
            try:
                preserved_bedrock, cleared_blocks = self._clear_selection_fast(protected_positions)
                return preserved_bedrock, cleared_blocks, "used successfully"
            except Exception as exc:
                self._fast_clear_failed = True
                self._fast_clear_fail_reason = str(exc)
                self._log(f"Fast direct chunk clear failed. Falling back to safe clear. Reason: {exc}")

        preserved_bedrock, cleared_blocks = self._clear_selection_safe(protected_positions)

        if self.fast_direct_clear.GetValue():
            return preserved_bedrock, cleared_blocks, "failed, used safe clear fallback"

        return preserved_bedrock, cleared_blocks, "disabled"

    def _build_single_storage_placement_context(self) -> Dict[str, object]:
        container = self._get_selected_container()
        entity_name = self._get_storage_entity_name()
        block_cache: Dict[str, Block] = {}

        if container == self.CONTAINER_SHULKER:
            shulker_color = self.shulker_color_choice.GetStringSelection()
            if not shulker_color:
                shulker_color = "default"
        else:
            shulker_color = "default"

        return {
            "container": container,
            "entity_name": entity_name,
            "shulker_color": shulker_color,
            "block_cache": block_cache,
        }

    def _get_cached_single_storage_block(self, placement_context: Dict[str, object], facing: str) -> Block:
        block_cache = placement_context["block_cache"]

        if facing in block_cache:
            return block_cache[facing]

        container = placement_context["container"]

        if container == self.CONTAINER_BARREL:
            block = self._make_universal_barrel(facing=facing)
        elif container == self.CONTAINER_SHULKER:
            block = Block(
                "universal_minecraft",
                "shulker_box",
                {
                    "color": self._universal_string(str(placement_context["shulker_color"])),
                    "facing": self._universal_string(facing),
                },
            )
        else:
            block = self._make_universal_chest(facing=facing, connection="none")

        block_cache[facing] = block
        return block

    def _place_single_storage_in_chunks(
        self,
        positions: Sequence[Tuple[int, int, int]],
        inventories: Sequence[Sequence[Tuple[str, int]]],
        bounds: Tuple[int, int, int, int, int, int],
    ) -> None:
        placement_context = self._build_single_storage_placement_context()
        entity_name = str(placement_context["entity_name"])
        item_info_cache: Dict[str, Tuple[str, int]] = {}
        chunk_cache = {}

        for (x, y, z), stacks in zip(positions, inventories):
            facing = self._get_inward_facing(x, z, bounds)
            universal_block = self._get_cached_single_storage_block(placement_context, facing)

            nbt = self._make_inventory_nbt(stacks, item_info_cache=item_info_cache)
            universal_entity = BlockEntity("universal_minecraft", entity_name, x, y, z, nbt)

            cx, cz = self._chunk_coords(x, z)
            key = (cx, cz)

            if key not in chunk_cache:
                chunk_cache[key] = self._get_chunk(cx, cz)

            chunk = chunk_cache[key]
            self._write_universal_block_to_chunk(
                chunk,
                x,
                y,
                z,
                universal_block,
                universal_entity,
            )

    def _place_double_chests_in_chunks(
        self,
        chest_pairs: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int], str]],
        chest_inventories: Sequence[Sequence[Tuple[str, int]]],
        bounds: Tuple[int, int, int, int, int, int],
    ) -> None:
        item_info_cache: Dict[str, Tuple[str, int]] = {}
        chunk_cache = {}

        for (first_pos, second_pos, pair_axis), stacks in zip(chest_pairs, chest_inventories):
            x1, _y1, z1 = first_pos
            x2, _y2, z2 = second_pos
            facing = self._get_double_chest_facing(pair_axis, x1, z1, x2, z2, bounds)
            left_pos, right_pos, left_connection, right_connection = self._get_double_chest_left_right(
                first_pos,
                second_pos,
                pair_axis,
                facing,
            )

            left_x, left_y, left_z = left_pos
            right_x, right_y, right_z = right_pos

            left_half = list(stacks[:self.SINGLE_CONTAINER_SLOT_COUNT])
            right_half = list(stacks[self.SINGLE_CONTAINER_SLOT_COUNT:])

            left_nbt = self._make_inventory_nbt(
                left_half,
                pair_position=(right_x, right_z),
                pair_lead=True,
                item_info_cache=item_info_cache,
            )
            right_nbt = self._make_inventory_nbt(
                right_half,
                pair_position=(left_x, left_z),
                pair_lead=False,
                item_info_cache=item_info_cache,
            )

            left_entity = BlockEntity("universal_minecraft", "chest", left_x, left_y, left_z, left_nbt)
            right_entity = BlockEntity("universal_minecraft", "chest", right_x, right_y, right_z, right_nbt)

            left_chest = self._make_universal_chest(facing=facing, connection=left_connection)
            right_chest = self._make_universal_chest(facing=facing, connection=right_connection)

            for x, y, z, chest_block, chest_entity in (
                (left_x, left_y, left_z, left_chest, left_entity),
                (right_x, right_y, right_z, right_chest, right_entity),
            ):
                cx, cz = self._chunk_coords(x, z)
                key = (cx, cz)

                if key not in chunk_cache:
                    chunk_cache[key] = self._get_chunk(cx, cz)

                chunk = chunk_cache[key]
                self._write_universal_block_to_chunk(
                    chunk,
                    x,
                    y,
                    z,
                    chest_block,
                    chest_entity,
                )

    def _is_valuable_item_for_frame(self, item_name: str) -> bool:
        return item_name in self.VALUABLE_ITEM_FRAME_BLOCKS

    def _make_universal_item_frame_block(self, facing: str, glowing: bool) -> Block:
        return Block(
            "universal_minecraft",
            "item_frame_block",
            {
                "facing": self._universal_string(facing),
                "map_item": self._universal_string("false"),
                "glowing": self._universal_string("true" if glowing else "false"),
            },
        )

    def _make_item_frame_nbt(self, item_name: str):
        if NBTFile is None:
            raise RuntimeError("amulet_nbt is unavailable in this environment.")
        if TAG_Compound is None or TAG_Byte is None or TAG_String is None or TAG_Short is None:
            raise RuntimeError("amulet_nbt tag helpers are unavailable in this environment.")

        if not str(item_name).strip():
            raise RuntimeError("Cannot create an item frame for an empty item name.")

        actual_name, damage_value = self._get_item_nbt_name_damage(item_name)

        if not actual_name.strip():
            raise RuntimeError("Cannot create an item frame for an empty item name.")

        the_nbt = TAG_Compound()
        the_nbt["isMovable"] = TAG_Byte(1)

        item = TAG_Compound()
        item["Count"] = TAG_Byte(1)
        item["Damage"] = TAG_Short(int(damage_value))
        item["Name"] = TAG_String(actual_name)
        item["WasPickedUp"] = TAG_Byte(0)

        extra_tag = self._make_item_extra_tag(item_name)
        if extra_tag is not None:
            item["tag"] = extra_tag

        if self._should_write_item_block_tag(item_name):
            block = TAG_Compound()
            block["name"] = TAG_String(actual_name)
            block["states"] = TAG_Compound()

            if TAG_Int is not None:
                block["version"] = TAG_Int(17841153)

            item["Block"] = block

        the_nbt["Item"] = item

        if TAG_Float is not None:
            the_nbt["ItemDropChance"] = TAG_Float(1.0)
            the_nbt["ItemRotation"] = TAG_Float(0.0)

        return NBTFile(the_nbt)

    def _get_front_position(self, x: int, y: int, z: int, facing: str) -> Tuple[int, int, int]:
        if facing == "east":
            return x + 1, y, z
        if facing == "west":
            return x - 1, y, z
        if facing == "south":
            return x, y, z + 1
        if facing == "north":
            return x, y, z - 1
        return x, y, z

    def _is_position_inside_bounds(
        self,
        x: int,
        y: int,
        z: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> bool:
        min_x, min_y, min_z, max_x, max_y, max_z = bounds
        return min_x <= x <= max_x and min_y <= y <= max_y and min_z <= z <= max_z

    def _collect_storage_occupied_positions(self, use_double_chests: bool, storage_positions) -> Set[Tuple[int, int, int]]:
        occupied: Set[Tuple[int, int, int]] = set()

        if use_double_chests:
            for first_pos, second_pos, _pair_axis in storage_positions:
                occupied.add(first_pos)
                occupied.add(second_pos)
        else:
            for pos in storage_positions:
                occupied.add(pos)

        return occupied

    def _place_group_item_frames(
        self,
        group_starts: Sequence[Tuple[str, int]],
        storage_positions,
        use_double_chests: bool,
        bounds: Tuple[int, int, int, int, int, int],
        protected_positions: Set[Tuple[int, int, int]],
    ) -> Tuple[
        int,
        int,
        Dict[str, Dict[str, int]],
        List[Tuple[str, str, int, Tuple[int, int, int], Tuple[int, int, int], bool]],
    ]:
        if not self.separate_types.GetValue():
            return 0, 0, {}, []

        if not self.add_group_item_frames.GetValue():
            return 0, 0, {}, []

        chunk_cache = {}
        storage_occupied_positions = self._collect_storage_occupied_positions(use_double_chests, storage_positions)

        placed_frames = 0
        skipped_frames = 0
        skipped_details: Dict[str, Dict[str, int]] = collections.defaultdict(
            lambda: collections.defaultdict(int)
        )
        label_audit: List[
            Tuple[str, str, int, Tuple[int, int, int], Tuple[int, int, int], bool]
        ] = []

        def record_skip(item_name: str, reason: str) -> None:
            nonlocal skipped_frames
            skipped_frames += 1
            safe_name = str(item_name).strip() or "<empty item name>"
            skipped_details[reason][safe_name] += 1

        for item_name, storage_index in group_starts:
            if not str(item_name).strip():
                record_skip(item_name, "Missing or empty item name")
                continue

            if not self._is_safe_item_key(item_name):
                record_skip(item_name, "Unsafe or unsupported item key")
                continue

            try:
                if use_double_chests:
                    first_pos, second_pos, pair_axis = storage_positions[storage_index]
                    x1, _y1, z1 = first_pos
                    x2, _y2, z2 = second_pos
                    facing = self._get_double_chest_facing(pair_axis, x1, z1, x2, z2, bounds)
                    left_pos, _right_pos, _left_connection, _right_connection = self._get_double_chest_left_right(
                        first_pos,
                        second_pos,
                        pair_axis,
                        facing,
                    )
                    x, y, z = left_pos
                else:
                    x, y, z = storage_positions[storage_index]
                    facing = self._get_inward_facing(x, z, bounds)

                frame_x, frame_y, frame_z = self._get_front_position(x, y, z, facing)

                if not self._is_position_inside_bounds(frame_x, frame_y, frame_z, bounds):
                    record_skip(item_name, "Frame position outside selection bounds")
                    continue

                if self._is_protected_position(frame_x, frame_y, frame_z, protected_positions):
                    record_skip(item_name, "Frame position is protected")
                    continue

                if (frame_x, frame_y, frame_z) in storage_occupied_positions:
                    record_skip(item_name, "Frame position overlaps generated storage")
                    continue

                if item_name in self.AMBIGUOUS_FAST_SCAN_BLOCKS and item_name not in self.SAFE_AMBIGUOUS_ITEM_FRAME_BLOCKS:
                    record_skip(item_name, "Unsafe ambiguous item-frame label")
                    continue

                actual_name, damage_value = self._get_item_nbt_name_damage(item_name)
                writes_block_tag = self._should_write_item_block_tag(item_name)

                glowing = self._is_valuable_item_for_frame(item_name)
                frame_block = self._make_universal_item_frame_block(facing=facing, glowing=glowing)
                frame_nbt = self._make_item_frame_nbt(item_name)
                entity_name = "GlowItemFrame" if glowing else "ItemFrame"
                frame_entity = BlockEntity("", entity_name, frame_x, frame_y, frame_z, frame_nbt)

                cx, cz = self._chunk_coords(frame_x, frame_z)
                key = (cx, cz)

                if key not in chunk_cache:
                    chunk_cache[key] = self._get_chunk(cx, cz)

                chunk = chunk_cache[key]
                self._write_universal_block_to_chunk(
                    chunk,
                    frame_x,
                    frame_y,
                    frame_z,
                    frame_block,
                    frame_entity,
                )
                placed_frames += 1
                label_audit.append(
                    (
                        str(item_name),
                        str(actual_name),
                        int(damage_value),
                        (int(x), int(y), int(z)),
                        (int(frame_x), int(frame_y), int(frame_z)),
                        bool(writes_block_tag),
                    )
                )
            except Exception:
                record_skip(item_name, "Item-frame payload or world write failed")

        return (
            placed_frames,
            skipped_frames,
            {reason: dict(items) for reason, items in skipped_details.items()},
            label_audit,
        )

    def _run_export(self, _):
        self._clear_log()
        self._reset_report()
        self._update_option_visibility()

        if not self._confirm_large_selection():
            self._log("Operation cancelled before start by large selection warning.")
            self._finalize_report()
            return

        try:
            self.canvas.run_operation(
                self._run_export_operation,
                title="Blocks to Storage",
                msg="Moving selected blocks into storage...",
                throw_exceptions=False,
            )
        except TypeError:
            try:
                self.canvas.run_operation(
                    self._run_export_operation,
                    "Blocks to Storage",
                    "Moving selected blocks into storage...",
                    False,
                )
            except Exception as exc:
                self._log(f"Operation failed to start: {exc}")
                self._finalize_report()
        except Exception as exc:
            self._log(f"Operation failed to start: {exc}")
            self._finalize_report()

    def _run_export_operation(self):
        total_start = time.perf_counter()
        self._reset_external_language_operation_state()

        if (
            self.use_found_entries_cache.GetValue()
            or self.use_installed_language_data.GetValue()
        ):
            self._ensure_external_language_data_loaded()

        try:
            self._log("Blocks to Storage Export Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log("Starting block scan...")
            self._log(f"World wrapper: {self._world_platform} / {self._world_version}")
            self._log(f"Fast direct chunk scan: {self.fast_direct_scan.GetValue()}")
            self._log(f"Fast direct chunk clear: {self.fast_direct_clear.GetValue()}")
            self._log(f"Large selection warning enabled: {self.show_large_selection_warning.GetValue()}")
            self._log(f"Item frame label audit enabled: {self.include_item_frame_audit.GetValue()}")
            self._log(f"Display-name ABC audit enabled: {self.include_display_name_audit.GetValue()}")
            self._log(f"Found Entries cache enabled: {self.use_found_entries_cache.GetValue()}")
            self._log(f"Installed language fallback enabled: {self.use_installed_language_data.GetValue()}")
            self._log(f"Save found display-name entries: {self.save_found_language_entries.GetValue()}")
            self._log(f"Simulate missing display-name entry: {self.simulate_missing_display_name.GetValue()}")
            if self.simulate_missing_display_name.GetValue():
                self._log(
                    f"Simulated missing alias: "
                    f"{self._get_simulated_missing_item_alias() or '(empty)'}"
                )

            container = self._get_selected_container()
            use_double_chests = container == self.CONTAINER_CHEST and self.use_double_chests.GetValue()

            self._log(f"Storage container: {container}")
            self._log(f"Nested shulker storage: {self._use_nested_shulker_storage()}")
            if self._use_nested_shulker_storage():
                self._log(f"Nested shulker mode: {self._get_nested_shulker_mode()}")
                if self._get_nested_shulker_mode() == self.NESTED_SHULKER_MODE_PRACTICAL:
                    self._log("Nested shulker threshold: more than 27 stacks per block group")
                self._log(f"Nested shulker color: {self.nested_shulker_color_choice.GetStringSelection()}")

            if container == self.CONTAINER_SHULKER:
                self._log(f"Shulker color: {self.shulker_color_choice.GetStringSelection()}")
                self._log("Shulker facing: sideways/inward")

            scan_start = time.perf_counter()
            counts, skipped_counts, skipped_by_reason, protected_positions, bounds, scanned_positions = self._scan_selection()
            scan_time = time.perf_counter() - scan_start

            if not bounds:
                self._log("No selection found.")
                self._log("")
                self._log(f"Total operation time: {self._format_seconds(time.perf_counter() - total_start)}")
                return

            min_x, min_y, min_z, max_x, max_y, max_z = bounds
            self._log(f"Selection bounds: x {min_x} to {max_x}, y {min_y} to {max_y}, z {min_z} to {max_z}")
            self._log(f"Selected positions scanned: {scanned_positions:,}")
            self._log(f"Scan time: {self._format_seconds(scan_time)}")
            self._log(f"Scan speed: {self._format_rate(scanned_positions, scan_time, 'blocks')}")

            if self._fast_scan_failed:
                self._log("Fast direct chunk scan result: failed, used safe scan fallback")
                self._log(f"Fast scan fail reason: {self._fast_scan_fail_reason}")
            elif self.fast_direct_scan.GetValue():
                self._log("Fast direct chunk scan result: used successfully")
            else:
                self._log("Fast direct chunk scan result: disabled")

            if self._ambiguous_fast_scan_fallbacks:
                self._log(f"Ambiguous fast scan block fallbacks: {self._ambiguous_fast_scan_fallbacks:,}")

            if not counts:
                self._log("No exportable blocks found.")

                self._log("")
                self._log_skipped_block_report(skipped_counts, skipped_by_reason)

                self._log("")
                self._log(f"Total operation time: {self._format_seconds(time.perf_counter() - total_start)}")
                return

            planning_start = time.perf_counter()

            total_blocks = sum(counts.values())
            total_skipped = sum(skipped_counts.values())

            inventories, group_starts = self._build_container_payloads_and_group_starts(counts)
            container_count = len(inventories)
            nested_shulker_count = self._count_nested_shulker_items(inventories)

            if use_double_chests:
                if self.separate_types.GetValue():
                    storage_positions = self._plan_double_chest_positions_by_group(
                        group_starts,
                        container_count,
                        bounds,
                        protected_positions,
                    )
                else:
                    storage_positions = self._plan_double_chest_positions(container_count, bounds, protected_positions)
                planned_physical_blocks = len(storage_positions) * 2
            else:
                if self.separate_types.GetValue():
                    storage_positions = self._plan_single_storage_positions_by_group(
                        group_starts,
                        container_count,
                        bounds,
                        protected_positions,
                    )
                else:
                    storage_positions = self._plan_single_storage_positions(container_count, bounds, protected_positions)
                planned_physical_blocks = len(storage_positions)

            planning_time = time.perf_counter() - planning_start

            self._log("")
            self._log(f"Exportable blocks found: {total_blocks:,}")
            self._log(f"Skipped non-air blocks: {total_skipped:,}")

            if use_double_chests:
                self._log(f"Double chests needed: {container_count:,}")
                self._log(f"Physical chest blocks planned: {planned_physical_blocks:,}")
            else:
                self._log(f"Storage containers needed: {container_count:,}")
                self._log(f"Physical storage blocks planned: {planned_physical_blocks:,}")

            if self._use_nested_shulker_storage():
                self._log(f"Nested shulker boxes created: {nested_shulker_count:,}")

            self._log(f"Vertical stack height: {self.stack_height.GetValue()}")
            self._log(f"ABC item order: {self.alphabetical_order.GetValue()}")
            self._log(f"One block type per storage group: {self.separate_types.GetValue()}")
            if self.separate_types.GetValue():
                self._log(f"Spacing between separated groups: {self._get_group_spacing_value()}")
            self._log(f"Add item frames for separated groups: {self.add_group_item_frames.GetValue()}")
            if self.separate_types.GetValue() and self.add_group_item_frames.GetValue():
                self._log("Item frame front clearance: 2 block(s)")
            self._log(f"Include unusual blocks: {self.include_unusual.GetValue()}")
            self._log(f"Preserve bedrock: {self.preserve_bedrock.GetValue()}")
            self._log(f"Protected bedrock positions: {len(protected_positions):,}")
            self._log(f"Planning time: {self._format_seconds(planning_time)}")

            self._log("")
            self._log("Exported blocks:")
            for item_name in self._get_ordered_item_names(counts):
                self._log(f"{item_name} -> {counts[item_name]:,}")

            if self.include_display_name_audit.GetValue():
                self._log("")
                self._log_display_name_audit(counts)

            self._write_pending_found_entries()
            self._log("")
            self._log_external_language_summary()

            self._log("")
            self._log_skipped_block_report(skipped_counts, skipped_by_reason)

            clear_start = time.perf_counter()
            preserved_bedrock, cleared_blocks, fast_clear_result = self._clear_selection_in_chunks(protected_positions)
            clear_time = time.perf_counter() - clear_start

            place_start = time.perf_counter()
            if use_double_chests:
                self._place_double_chests_in_chunks(storage_positions, inventories, bounds)
            else:
                self._place_single_storage_in_chunks(storage_positions, inventories, bounds)

            (
                placed_item_frames,
                skipped_item_frames,
                skipped_item_frame_details,
                item_frame_label_audit,
            ) = self._place_group_item_frames(
                group_starts,
                storage_positions,
                use_double_chests,
                bounds,
                protected_positions,
            )
            place_time = time.perf_counter() - place_start

            edit_time = clear_time + place_time
            total_time = time.perf_counter() - total_start

            self._log("")
            if self.preserve_bedrock.GetValue():
                self._log(f"Preserved bedrock blocks during clear: {preserved_bedrock:,}")

            self._log(f"Cleared blocks: {cleared_blocks:,}")
            self._log(f"Clear time: {self._format_seconds(clear_time)}")
            self._log(f"Clear speed: {self._format_rate(cleared_blocks, clear_time, 'blocks')}")
            self._log(f"Fast direct chunk clear result: {fast_clear_result}")

            if self._fast_clear_failed:
                self._log(f"Fast clear fail reason: {self._fast_clear_fail_reason}")

            self._log(f"Placed storage units: {container_count:,}")
            self._log(f"Placed physical storage blocks: {planned_physical_blocks:,}")
            if self._use_nested_shulker_storage():
                self._log(f"Placed nested shulker boxes: {nested_shulker_count:,}")
            self._log(f"Placed item frames: {placed_item_frames:,}")
            self._log(f"Skipped item frames: {skipped_item_frames:,}")

            if skipped_item_frame_details:
                self._log("Skipped item frame labels:")
                for reason in sorted(skipped_item_frame_details.keys()):
                    reason_items = skipped_item_frame_details[reason]
                    reason_total = sum(reason_items.values())
                    self._log(f"{reason}: {reason_total:,}")
                    for item_name in sorted(reason_items.keys()):
                        self._log(f"  {item_name} -> {reason_items[item_name]:,}")

            if self.include_item_frame_audit.GetValue() and item_frame_label_audit:
                self._log("Item frame label audit:")
                for (
                    item_name,
                    actual_name,
                    damage_value,
                    storage_pos,
                    frame_pos,
                    writes_block_tag,
                ) in item_frame_label_audit:
                    self._log(
                        f"  {item_name} -> {actual_name}, damage {damage_value}, "
                        f"storage {storage_pos}, frame {frame_pos}, "
                        f"Block tag: {writes_block_tag}"
                    )

            self._log(f"Place time: {self._format_seconds(place_time)}")
            self._log(f"Placement speed: {self._format_rate(planned_physical_blocks, place_time, 'storage blocks')}")

            self._log(f"Clear / place time: {self._format_seconds(edit_time)}")
            self._log(f"Total operation time: {self._format_seconds(total_time)}")
            self._log("")
            self._log("Finished. The selected blocks were moved into storage.")

        except Exception as exc:
            self._log("")
            self._log(f"Operation failed: {exc}")
            self._log(f"Total operation time before failure: {self._format_seconds(time.perf_counter() - total_start)}")
        finally:
            try:
                self._finalize_report()
            finally:
                self._release_operation_display_name_caches()

export = dict(name="Blocks to Storage", operation=PluginClassName)
