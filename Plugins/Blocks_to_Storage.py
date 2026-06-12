import collections
import re
import time
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

        self.include_item_frame_audit = wx.CheckBox(
            self.settings_panel,
            label="Include item frame label audit in report",
        )
        self.include_item_frame_audit.SetValue(False)
        self.settings_sizer.Add(self.include_item_frame_audit, 0, wx.ALL, 6)

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
            self.include_item_frame_audit,
            "Adds a detailed item-frame label audit to the export report. The audit includes internal item keys, final Bedrock item names, damage values, storage coordinates, frame coordinates, and Block-tag usage. Leave this disabled for normal reports.",
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
            "Sorts block types alphabetically before packing them into storage. Turning this off keeps the order based on when each block type was first found during the scan.",
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

    def _make_universal_shulker_box(self, facing: str = "east") -> Block:
        color = self.shulker_color_choice.GetStringSelection()
        if not color:
            color = "default"

        return Block(
            "universal_minecraft",
            "shulker_box",
            {
                "color": self._universal_string(color),
                "facing": self._universal_string(facing),
            },
        )

    def _make_universal_storage_block(self, facing: str) -> Block:
        container = self._get_selected_container()

        if container == self.CONTAINER_BARREL:
            return self._make_universal_barrel(facing=facing)

        if container == self.CONTAINER_SHULKER:
            return self._make_universal_shulker_box(facing=facing)

        return self._make_universal_chest(facing=facing, connection="none")

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

        display_name = self.ABC_SORT_NAME_OVERRIDES.get(item_name, item_name)
        return self._normalize_abc_sort_text(display_name)

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
            self._finalize_report()

export = dict(name="Blocks to Storage", operation=PluginClassName)
