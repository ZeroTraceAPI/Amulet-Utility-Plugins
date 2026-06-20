"""Auto Farmland plugin for Amulet Map Editor.

Purpose:
- Scan the selected Bedrock world area for safe exposed surfaces.
- Replace grass blocks with farmland, or build a conservative raised farmland layer.
- Plant one crop, alternating crop rows, assorted crops, or stem layouts.
- Detect existing irrigation and plan additional water sources efficiently.
- Optionally cover new water with a selected waterlogged upper slab.
- Use dedicated row and fruit-lane logic for melon and pumpkin stems.
- Validate and apply the complete farm as one undoable operation.

Navigation:
1. Imports and constants
2. Plan data containers
3. UI construction
4. Settings persistence and report helpers
5. Selection, block and plant helpers
6. Surface scanning and crop layout
7. Hydration and water planning
8. Plan assembly, validation and writing
9. Main Amulet operation wrapper
"""

from __future__ import annotations

import ast
import heapq
from collections import Counter
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import wx

from amulet.api.block import Block
from amulet_map_editor.programs.edit.api.behaviour import BlockSelectionBehaviour
from amulet_map_editor.programs.edit.api.operations import DefaultOperationUI
from amulet.utils import block_coords_to_chunk_coords
from amulet_nbt import TAG_Int, TAG_String


Position = Tuple[int, int, int]
BoxTuple = Tuple[int, int, int, int, int, int]
ReadResult = Tuple[Block, object, bool]


# -----------------------------------------------------------------------------
# Bedrock block references
# -----------------------------------------------------------------------------

AIR_NAMES = {"air", "cave_air", "void_air"}
WATER_NAMES = {"water", "flowing_water"}
GRASS_BLOCK_NAMES = {"grass_block"}
FARMLAND_NAMES = {"farmland"}

# Creative-accessible Bedrock upper slabs verified from the supplied
# construction samples. Every entry uses the same vertical-half state, while
# the explicit display-name mapping avoids guessing block identifiers.
SLAB_BLOCK_NAMES = {
    "Acacia Slab": "acacia_slab",
    "Andesite Slab": "andesite_slab",
    "Bamboo Mosaic Slab": "bamboo_mosaic_slab",
    "Bamboo Slab": "bamboo_slab",
    "Birch Slab": "birch_slab",
    "Blackstone Slab": "blackstone_slab",
    "Brick Slab": "brick_slab",
    "Cherry Slab": "cherry_slab",
    "Cinnabar Brick Slab": "cinnabar_brick_slab",
    "Cinnabar Slab": "cinnabar_slab",
    "Cobbled Deepslate Slab": "cobbled_deepslate_slab",
    "Cobblestone Slab": "cobblestone_slab",
    "Crimson Slab": "crimson_slab",
    "Cut Copper Slab": "cut_copper_slab",
    "Cut Red Sandstone Slab": "cut_red_sandstone_slab",
    "Cut Sandstone Slab": "cut_sandstone_slab",
    "Dark Oak Slab": "dark_oak_slab",
    "Dark Prismarine Slab": "dark_prismarine_slab",
    "Deepslate Brick Slab": "deepslate_brick_slab",
    "Deepslate Tile Slab": "deepslate_tile_slab",
    "Diorite Slab": "diorite_slab",
    "End Stone Brick Slab": "end_stone_brick_slab",
    "Exposed Cut Copper Slab": "exposed_cut_copper_slab",
    "Granite Slab": "granite_slab",
    "Jungle Slab": "jungle_slab",
    "Mangrove Slab": "mangrove_slab",
    "Mossy Cobblestone Slab": "mossy_cobblestone_slab",
    "Mossy Stone Brick Slab": "mossy_stone_brick_slab",
    "Mud Brick Slab": "mud_brick_slab",
    "Nether Brick Slab": "nether_brick_slab",
    "Oak Slab": "oak_slab",
    "Oxidized Cut Copper Slab": "oxidized_cut_copper_slab",
    "Pale Oak Slab": "pale_oak_slab",
    "Polished Andesite Slab": "polished_andesite_slab",
    "Polished Blackstone Brick Slab": "polished_blackstone_brick_slab",
    "Polished Blackstone Slab": "polished_blackstone_slab",
    "Polished Cinnabar Slab": "polished_cinnabar_slab",
    "Polished Deepslate Slab": "polished_deepslate_slab",
    "Polished Diorite Slab": "polished_diorite_slab",
    "Polished Granite Slab": "polished_granite_slab",
    "Polished Sulfur Slab": "polished_sulfur_slab",
    "Polished Tuff Slab": "polished_tuff_slab",
    "Prismarine Brick Slab": "prismarine_brick_slab",
    "Prismarine Slab": "prismarine_slab",
    "Purpur Slab": "purpur_slab",
    "Quartz Slab": "quartz_slab",
    "Red Nether Brick Slab": "red_nether_brick_slab",
    "Red Sandstone Slab": "red_sandstone_slab",
    "Resin Brick Slab": "resin_brick_slab",
    "Sandstone Slab": "sandstone_slab",
    "Smooth Quartz Slab": "smooth_quartz_slab",
    "Smooth Red Sandstone Slab": "smooth_red_sandstone_slab",
    "Smooth Sandstone Slab": "smooth_sandstone_slab",
    "Smooth Stone Slab": "smooth_stone_slab",
    "Spruce Slab": "spruce_slab",
    "Stone Brick Slab": "stone_brick_slab",
    "Stone Slab": "normal_stone_slab",
    "Sulfur Brick Slab": "sulfur_brick_slab",
    "Sulfur Slab": "sulfur_slab",
    "Tuff Brick Slab": "tuff_brick_slab",
    "Tuff Slab": "tuff_slab",
    "Warped Slab": "warped_slab",
    "Waxed Cut Copper Slab": "waxed_cut_copper_slab",
    "Waxed Exposed Cut Copper Slab": "waxed_exposed_cut_copper_slab",
    "Waxed Oxidized Cut Copper Slab": "waxed_oxidized_cut_copper_slab",
    "Waxed Weathered Cut Copper Slab": "waxed_weathered_cut_copper_slab",
    "Weathered Cut Copper Slab": "weathered_cut_copper_slab",
}
SLAB_CHOICES = tuple(SLAB_BLOCK_NAMES)

STANDARD_CROPS = (
    "Wheat",
    "Carrots",
    "Potatoes",
    "Beetroot",
)

CROP_LAYOUT_CHOICES = (
    "Farmland only",
    "Single Crop",
    "Alternating Crop Rows",
    "Assorted Crops",
    "Melon Stem",
    "Pumpkin Stem",
)

MULTI_CROP_LAYOUTS = {"Alternating Crop Rows", "Assorted Crops"}
STEM_CROPS = {"Melon Stem", "Pumpkin Stem"}
GROWTH_MODE_CHOICES = ("Fixed growth state", "Random growth range")
PATTERN_SEED_MAX = 999_999

CROP_BLOCK_NAMES = {
    "Wheat": "wheat",
    "Carrots": "carrots",
    "Potatoes": "potatoes",
    "Beetroot": "beetroot",
    "Melon Stem": "melon_stem",
    "Pumpkin Stem": "pumpkin_stem",
}

GROWTH_DESCRIPTIONS = {
    0: "Just planted",
    1: "Very young",
    2: "Young",
    3: "Early growth",
    4: "Mid growth",
    5: "Late growth",
    6: "Nearly mature",
    7: "Fully mature",
}

# Auto Farmland uses a deliberately conservative decorative-plant list.
# The option may clear small flowers, grass, carpets, moss, harmless bushes,
# fungi and similar decoration. Existing crops, saplings, propagules, berry
# bushes, cactus or bamboo columns, big dripleaf columns, fruiting vines and
# unfamiliar plants remain protected.
REPLACEABLE_DECORATIVE_PLANTS = {
    # Grass, ferns and dry vegetation
    "short_grass",
    "tall_grass",
    "short_dry_grass",
    "tall_dry_grass",
    "fern",
    "large_fern",

    # Small flowers
    "dandelion",
    "golden_dandelion",
    "poppy",
    "blue_orchid",
    "allium",
    "azure_bluet",
    "red_tulip",
    "orange_tulip",
    "white_tulip",
    "pink_tulip",
    "oxeye_daisy",
    "cornflower",
    "lily_of_the_valley",
    "wither_rose",
    "closed_eyeblossom",
    "open_eyeblossom",
    "cactus_flower",

    # Double-height flowers
    "sunflower",
    "lilac",
    "rose_bush",
    "peony",

    # Bushes and low shrubs
    "bush",
    "firefly_bush",
    "azalea",
    "flowering_azalea",

    # Nether fungi and roots
    "crimson_fungus",
    "warped_fungus",
    "crimson_roots",
    "warped_roots",
    "nether_sprouts",

    # Mushrooms and dead vegetation
    "dead_bush",
    "brown_mushroom",
    "red_mushroom",

    # Ground cover and attached decoration
    "pink_petals",
    "leaf_litter",
    "wildflowers",
    "moss_carpet",
    "pale_moss_carpet",
    "vine",
    "glow_lichen",
    "hanging_roots",
    "pale_hanging_moss",
    "spore_blossom",

    # Small dripleaf uses a paired upper / lower Bedrock state. The legacy alias
    # is retained for older translated worlds.
    "small_dripleaf",
    "small_dripleaf_block",
}

# Paired plants need their matching selected half cleared as one safe action.
# The helper checks both the block identity and the saved upper / lower state.
DOUBLE_HEIGHT_PLANTS = {
    "tall_grass",
    "large_fern",
    "sunflower",
    "lilac",
    "rose_bush",
    "peony",
    "small_dripleaf",
    "small_dripleaf_block",
    "pale_moss_carpet",
}


# Raised mode defaults to natural-looking terrain. The support is retained and
# farmland is placed above it, so this list is about visual and structural
# suitability rather than Minecraft's tilling rules.
NATURAL_RAISED_SUPPORTS = {
    "grass_block",
    "dirt",
    "coarse_dirt",
    "rooted_dirt",
    "podzol",
    "mycelium",
    "mud",
    "packed_mud",
    "clay",
    "sand",
    "red_sand",
    "gravel",
    "moss_block",
}

# Families that should never be assumed to be a safe full support block. The
# "Any safe full block" mode is still conservative and rejects unknown shapes
# when their names indicate a partial, interactive, fluid or plant-like block.
UNSAFE_SUPPORT_KEYWORDS = (
    "air",
    "water",
    "lava",
    "plant",
    "grass",
    "flower",
    "fern",
    "mushroom",
    "roots",
    "bush",
    "sapling",
    "leaves",
    "vine",
    "kelp",
    "seagrass",
    "coral",
    "cactus",
    "bamboo",
    "reeds",
    "crop",
    "stem",
    "slab",
    "stairs",
    "fence",
    "wall",
    "pane",
    "carpet",
    "rail",
    "button",
    "lever",
    "pressure_plate",
    "door",
    "trapdoor",
    "sign",
    "banner",
    "torch",
    "lantern",
    "candle",
    "chain",
    "ladder",
    "scaffolding",
    "bed",
    "chest",
    "barrel",
    "shulker",
    "hopper",
    "furnace",
    "smoker",
    "brewing_stand",
    "anvil",
    "bell",
    "cauldron",
    "campfire",
    "snow_layer",
    "powder_snow",
    "portal",
    "fire",
    "farmland",
)

# Existing water is read from a four-block horizontal hydration border. The
# separate two-block context border is used by safety and fruit-lane checks.
SAFETY_CONTEXT_RADIUS = 2
HYDRATION_RADIUS = 4
LARGE_COLUMN_WARNING_THRESHOLD = 500_000
PROGRESS_INTERVAL = 100_000


# -----------------------------------------------------------------------------
# Plan data containers
# -----------------------------------------------------------------------------


@dataclass
class SurfaceCandidate:
    """One validated farm column and the changes required above it."""

    farmland_pos: Position
    crop_pos: Position
    clear_positions: Set[Position] = field(default_factory=set)
    originals: Dict[Position, Tuple[Block, object]] = field(default_factory=dict)


@dataclass
class FarmPlan:
    """Complete pre-write plan assembled before any world modification."""

    selection_boxes: Tuple[BoxTuple, ...]
    candidate_by_farmland: Dict[Position, SurfaceCandidate]
    farmland_positions: Set[Position]
    crop_positions: Dict[Position, str]
    crop_growth_states: Dict[Position, int]
    water_positions: Set[Position]
    existing_water_positions: Set[Position]
    hydrated_positions: Set[Position]
    reserved_fruit_positions: Set[Position]
    clear_positions: Set[Position]
    originals: Dict[Position, Tuple[Block, object]]
    counters: Dict[str, int]
    warnings: List[str]
    settings: Dict[str, object]


# -----------------------------------------------------------------------------
# Main plugin UI
# -----------------------------------------------------------------------------


class AutoFarmland(wx.Panel, DefaultOperationUI):
    """Surface-aware farmland, crop and irrigation planner."""

    SETTINGS_CONFIG_FILENAME = "Auto Farmland.config"
    SETTINGS_CONFIG_FORMAT_VERSION = 3
    SETTINGS_SAVE_DELAY_MS = 500
    MAX_SETTINGS_CONFIG_BYTES = 1024 * 1024

    # The settings area is scrollable, so it may shrink to preserve the
    # requested console height when Amulet's operation panel has limited room.
    SETTINGS_VIEWPORT_MIN_HEIGHT = 280
    SETTINGS_VIEWPORT_HEIGHT = 500
    SETTINGS_VIEWPORT_MAX_HEIGHT = 620
    CONSOLE_PREFERRED_HEIGHT = 220
    CONSOLE_MIN_HEIGHT = 220
    CONSOLE_SEMANTIC_NAME = "AmuletPluginConsole:AutoFarmland"

    def __init__(self, parent, canvas, world, options_path):
        """Build the operation panel and initialize persistent state."""
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)

        self._selection = None
        self._settings_config_save_call = None
        self._settings_config_applying = False
        self._settings_defaults: Dict[str, object] = {}
        self._settings_config_unknown_data: Dict[str, object] = {}
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._report_lines: List[str] = []
        self._last_report_text = ""

        wx.ToolTip.SetAutoPop(28000)

        root = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(root)

        self.scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.scroll.SetScrollRate(0, 15)
        self.scroll.SetMinSize((320, self.SETTINGS_VIEWPORT_MIN_HEIGHT))
        self.scroll.SetInitialSize((-1, self.SETTINGS_VIEWPORT_HEIGHT))
        root.Add(self.scroll, 0, wx.EXPAND)

        # Rebalance the scrollable settings viewport whenever Amulet changes
        # the available operation-panel height. The console's preferred height
        # is reserved before the settings viewport is assigned its share.
        self.Bind(wx.EVT_SIZE, self._on_panel_resized)

        content = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetSizer(content)
        content.AddSpacer(8)

        title = wx.StaticText(self.scroll, label="Auto Farmland")
        title.SetToolTip(
            "Plans farmland, crops and irrigation across the exposed surface of "
            "the selected Bedrock area."
        )
        content.Add(title, 0, wx.ALL, 6)

        # -----------------------------------------------------------------
        # Farmland placement category
        # -----------------------------------------------------------------
        placement_box = wx.StaticBoxSizer(
            wx.VERTICAL,
            self.scroll,
            label="Farmland Placement",
        )

        self.replace_grass_cb = wx.CheckBox(
            self.scroll,
            label="Replace grass blocks with farmland",
        )
        self.replace_grass_cb.SetValue(True)
        self.replace_grass_cb.SetToolTip(
            "Enabled: eligible exposed grass blocks become farmland at their "
            "current level. Disabled: the original support remains and farmland "
            "is placed one block above safe exposed surfaces."
        )
        placement_box.Add(self.replace_grass_cb, 0, wx.ALL, 5)

        self.placement_explanation = wx.StaticText(
            self.scroll,
            label=(
                "Eligible grass blocks are replaced with farmland at their "
                "current position."
            ),
        )
        self.placement_explanation.Wrap(350)
        placement_box.Add(self.placement_explanation, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 7)

        self.raised_support_label = wx.StaticText(
            self.scroll,
            label="Raised farmland support",
        )
        placement_box.Add(self.raised_support_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.raised_support_choice = wx.Choice(
            self.scroll,
            choices=("Natural terrain only", "Any safe full block"),
        )
        self.raised_support_choice.SetSelection(0)
        self.raised_support_choice.SetToolTip(
            "Controls which retained surface blocks may support farmland in "
            "raised mode. Partial, fluid, interactive and block-entity supports "
            "are always rejected."
        )
        placement_box.Add(self.raised_support_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.replace_plants_cb = wx.CheckBox(
            self.scroll,
            label="Replace decorative plants above targets",
        )
        self.replace_plants_cb.SetValue(True)
        self.replace_plants_cb.SetToolTip(
            "Allows a narrow safe list of grass, ferns, flowers and similar "
            "decoration to be removed. Existing crops and productive plants are protected."
        )
        placement_box.Add(self.replace_plants_cb, 0, wx.ALL, 5)

        self.skip_isolated_raised_cb = wx.CheckBox(
            self.scroll,
            label="Skip isolated raised farmland",
        )
        self.skip_isolated_raised_cb.SetValue(True)
        self.skip_isolated_raised_cb.SetToolTip(
            "Prevents raised mode from scattering single farmland blocks across "
            "rough terrain. A selection containing only one valid column is still allowed."
        )
        placement_box.Add(self.skip_isolated_raised_cb, 0, wx.ALL, 5)

        content.Add(placement_box, 0, wx.ALL | wx.EXPAND, 6)

        # -----------------------------------------------------------------
        # Crop category
        # -----------------------------------------------------------------
        crop_box = wx.StaticBoxSizer(wx.VERTICAL, self.scroll, label="Crop Settings")

        crop_layout_label = wx.StaticText(self.scroll, label="Crop Layout")
        crop_box.Add(crop_layout_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.crop_layout_choice = wx.Choice(
            self.scroll,
            choices=CROP_LAYOUT_CHOICES,
        )
        self.crop_layout_choice.SetSelection(1)
        self.crop_layout_choice.SetToolTip(
            "Choose farmland only, one standard crop, alternating crop rows, "
            "deterministically assorted crops, or a melon / pumpkin stem layout."
        )
        crop_box.Add(self.crop_layout_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.single_crop_label = wx.StaticText(self.scroll, label="Single Crop")
        crop_box.Add(self.single_crop_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.single_crop_choice = wx.Choice(self.scroll, choices=STANDARD_CROPS)
        self.single_crop_choice.SetSelection(0)
        self.single_crop_choice.SetToolTip(
            "The standard crop used by Single Crop layout."
        )
        crop_box.Add(self.single_crop_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.selected_crops_label = wx.StaticText(
            self.scroll,
            label="Crops included in the layout",
        )
        crop_box.Add(self.selected_crops_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        selected_crops_grid = wx.FlexGridSizer(rows=2, cols=2, vgap=2, hgap=12)
        self.crop_wheat_cb = wx.CheckBox(self.scroll, label="Wheat")
        self.crop_carrots_cb = wx.CheckBox(self.scroll, label="Carrots")
        self.crop_potatoes_cb = wx.CheckBox(self.scroll, label="Potatoes")
        self.crop_beetroot_cb = wx.CheckBox(self.scroll, label="Beetroot")
        for crop_control in (
            self.crop_wheat_cb,
            self.crop_carrots_cb,
            self.crop_potatoes_cb,
            self.crop_beetroot_cb,
        ):
            crop_control.SetValue(True)
            crop_control.SetToolTip(
                "Include this crop in Alternating Crop Rows and Assorted Crops."
            )
            selected_crops_grid.Add(crop_control, 0, wx.ALL, 3)
        crop_box.Add(selected_crops_grid, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.row_direction_label = wx.StaticText(self.scroll, label="Row Direction")
        crop_box.Add(self.row_direction_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.row_direction_choice = wx.Choice(
            self.scroll,
            choices=("Automatic", "Along X", "Along Z"),
        )
        self.row_direction_choice.SetSelection(0)
        self.row_direction_choice.SetToolTip(
            "Alternating crops change across rows perpendicular to this axis. "
            "Automatic chooses the longer horizontal axis separately for each "
            "selection box. When boxes overlap, the earlier selection keeps the "
            "shared columns so later boxes cannot rewrite its row pattern. Stem "
            "rows use the same direction setting."
        )
        crop_box.Add(self.row_direction_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.growth_mode_label = wx.StaticText(self.scroll, label="Growth Mode")
        crop_box.Add(self.growth_mode_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.growth_mode_choice = wx.Choice(
            self.scroll,
            choices=GROWTH_MODE_CHOICES,
        )
        self.growth_mode_choice.SetSelection(0)
        self.growth_mode_choice.SetToolTip(
            "Use one fixed growth state or a deterministic random state between "
            "the selected minimum and maximum."
        )
        crop_box.Add(self.growth_mode_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.growth_label = wx.StaticText(self.scroll, label="Fixed Growth State")
        crop_box.Add(self.growth_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        growth_row = wx.BoxSizer(wx.HORIZONTAL)
        self.growth_slider = wx.Slider(
            self.scroll,
            value=0,
            minValue=0,
            maxValue=7,
        )
        self.growth_box = wx.TextCtrl(self.scroll, value="0", size=(48, -1))
        growth_row.Add(self.growth_slider, 1, wx.RIGHT, 6)
        growth_row.Add(self.growth_box, 0)
        crop_box.Add(growth_row, 0, wx.ALL | wx.EXPAND, 5)
        self.growth_row = growth_row

        self.growth_description = wx.StaticText(
            self.scroll,
            label="State 0 of 7 - Just planted",
        )
        crop_box.Add(self.growth_description, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 7)

        self.random_growth_min_label = wx.StaticText(
            self.scroll,
            label="Minimum Random Growth",
        )
        crop_box.Add(self.random_growth_min_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        random_growth_min_row = wx.BoxSizer(wx.HORIZONTAL)
        self.random_growth_min_slider = wx.Slider(
            self.scroll,
            value=0,
            minValue=0,
            maxValue=7,
        )
        self.random_growth_min_box = wx.TextCtrl(
            self.scroll, value="0", size=(48, -1)
        )
        random_growth_min_row.Add(self.random_growth_min_slider, 1, wx.RIGHT, 6)
        random_growth_min_row.Add(self.random_growth_min_box, 0)
        crop_box.Add(random_growth_min_row, 0, wx.ALL | wx.EXPAND, 5)
        self.random_growth_min_row = random_growth_min_row

        self.random_growth_max_label = wx.StaticText(
            self.scroll,
            label="Maximum Random Growth",
        )
        crop_box.Add(self.random_growth_max_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        random_growth_max_row = wx.BoxSizer(wx.HORIZONTAL)
        self.random_growth_max_slider = wx.Slider(
            self.scroll,
            value=7,
            minValue=0,
            maxValue=7,
        )
        self.random_growth_max_box = wx.TextCtrl(
            self.scroll, value="7", size=(48, -1)
        )
        random_growth_max_row.Add(self.random_growth_max_slider, 1, wx.RIGHT, 6)
        random_growth_max_row.Add(self.random_growth_max_box, 0)
        crop_box.Add(random_growth_max_row, 0, wx.ALL | wx.EXPAND, 5)
        self.random_growth_max_row = random_growth_max_row

        self.growth_range_description = wx.StaticText(
            self.scroll,
            label="Random range: state 0 through state 7",
        )
        crop_box.Add(
            self.growth_range_description,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM,
            7,
        )

        self.pattern_seed_label = wx.StaticText(self.scroll, label="Pattern Seed")
        crop_box.Add(self.pattern_seed_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        pattern_seed_row = wx.BoxSizer(wx.HORIZONTAL)
        self.pattern_seed_slider = wx.Slider(
            self.scroll,
            value=0,
            minValue=0,
            maxValue=PATTERN_SEED_MAX,
        )
        self.pattern_seed_box = wx.TextCtrl(self.scroll, value="0", size=(72, -1))
        self.randomize_seed_button = wx.Button(
            self.scroll,
            label="Randomize Seed",
        )
        self.randomize_seed_button.SetToolTip(
            "Choose another saved seed. The same seed and coordinates always "
            "produce the same assorted crops and random growth states."
        )
        pattern_seed_row.Add(self.pattern_seed_slider, 1, wx.RIGHT, 6)
        pattern_seed_row.Add(self.pattern_seed_box, 0, wx.RIGHT, 6)
        pattern_seed_row.Add(self.randomize_seed_button, 0)
        crop_box.Add(pattern_seed_row, 0, wx.ALL | wx.EXPAND, 5)
        self.pattern_seed_row = pattern_seed_row

        self.stem_spacing_label = wx.StaticText(
            self.scroll,
            label="Blocks skipped between stems",
        )
        crop_box.Add(self.stem_spacing_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        stem_spacing_row = wx.BoxSizer(wx.HORIZONTAL)
        self.stem_spacing_slider = wx.Slider(
            self.scroll,
            value=1,
            minValue=0,
            maxValue=2,
        )
        self.stem_spacing_box = wx.TextCtrl(self.scroll, value="1", size=(48, -1))
        stem_spacing_row.Add(self.stem_spacing_slider, 1, wx.RIGHT, 6)
        stem_spacing_row.Add(self.stem_spacing_box, 0)
        crop_box.Add(stem_spacing_row, 0, wx.ALL | wx.EXPAND, 5)
        self.stem_spacing_row = stem_spacing_row

        content.Add(crop_box, 0, wx.ALL | wx.EXPAND, 6)

        # -----------------------------------------------------------------
        # Irrigation category
        # -----------------------------------------------------------------
        water_box = wx.StaticBoxSizer(wx.VERTICAL, self.scroll, label="Irrigation")

        self.add_water_cb = wx.CheckBox(
            self.scroll,
            label="Add water sources where safely needed",
        )
        self.add_water_cb.SetValue(True)
        self.add_water_cb.SetToolTip(
            "Detects existing hydration first, then greedily places safe source "
            "blocks that cover the most remaining farmland. Water is never forced "
            "into an invalid or poorly surrounded position."
        )
        water_box.Add(self.add_water_cb, 0, wx.ALL, 5)

        self.moisture_label = wx.StaticText(self.scroll, label="Initial farmland moisture")
        water_box.Add(self.moisture_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.moisture_choice = wx.Choice(
            self.scroll,
            choices=(
                "Match planned irrigation",
                "Force dry",
                "Force fully hydrated",
            ),
        )
        self.moisture_choice.SetSelection(0)
        self.moisture_choice.SetToolTip(
            "Match planned irrigation writes moisture 7 only where existing or "
            "planned water covers the farmland. Forced moisture may later change "
            "normally in-game."
        )
        water_box.Add(self.moisture_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.water_cover_label = wx.StaticText(self.scroll, label="Water Cover")
        water_box.Add(self.water_cover_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.water_cover_choice = wx.Choice(
            self.scroll,
            choices=("Open Water", "Waterlogged Upper Slab"),
        )
        self.water_cover_choice.SetSelection(0)
        self.water_cover_choice.SetToolTip(
            "Choose open source water or cover each new source with a "
            "waterlogged upper slab."
        )
        water_box.Add(self.water_cover_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.slab_type_label = wx.StaticText(self.scroll, label="Slab Type")
        water_box.Add(self.slab_type_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.slab_type_choice = wx.Choice(self.scroll, choices=SLAB_CHOICES)
        oak_slab_index = self.slab_type_choice.FindString("Oak Slab")
        self.slab_type_choice.SetSelection(
            oak_slab_index if oak_slab_index != wx.NOT_FOUND else 0
        )
        self.slab_type_choice.SetToolTip(
            "Select the upper slab placed over each new water source. The slab "
            "stores source water as an Amulet extra block layer."
        )
        water_box.Add(self.slab_type_choice, 0, wx.ALL | wx.EXPAND, 5)

        content.Add(water_box, 0, wx.ALL | wx.EXPAND, 6)

        # -----------------------------------------------------------------
        # File management and operation status
        # -----------------------------------------------------------------
        self.manage_plugin_files_button = wx.Button(
            self.scroll,
            label="Manage Plugin Files...",
        )
        self.manage_plugin_files_button.SetToolTip(
            "Open folders, reset, repair, import, export, or delete the files "
            "used by Auto Farmland and its settings config."
        )
        content.Add(
            self.manage_plugin_files_button,
            0,
            wx.ALL | wx.EXPAND,
            6,
        )

        self.status = wx.StaticText(self.scroll, label="Ready")
        self.status.SetToolTip(
            "Shows the current operation state and the most recent result."
        )
        content.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        content.AddSpacer(4)

        # The primary operation and report controls stay outside the scrollable
        # settings viewport so they remain visible while settings are adjusted.
        self.create_button = wx.Button(self, label="Create Farm")
        self.create_button.SetToolTip(
            "Builds the farm plan, validates it, and applies the resulting world "
            "changes as one Amulet operation."
        )
        root.Add(self.create_button, 0, wx.ALL | wx.EXPAND, 6)

        self.save_report_button = wx.Button(self, label="Save Last Report...")
        self.save_report_button.Enable(False)
        self.save_report_button.SetToolTip(
            "Saves the latest Auto Farmland operation report as UTF-8 text."
        )
        root.Add(self.save_report_button, 0, wx.ALL | wx.EXPAND, 6)

        self.text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, self.CONSOLE_PREFERRED_HEIGHT),
        )
        self.text.SetName(self.CONSOLE_SEMANTIC_NAME)
        self.text.SetMinSize((340, self.CONSOLE_MIN_HEIGHT))
        self.text.SetForegroundColour(wx.Colour(0, 255, 0))
        self.text.SetBackgroundColour(wx.Colour(0, 0, 0))
        # Proportion 1 lets the console consume all vertical room left after
        # the fixed operation controls and the dynamically sized settings view.
        root.Add(self.text, 1, wx.ALL | wx.EXPAND, 4)

        self._bind_slider_and_text(self.growth_slider, self.growth_box, 0, 7)
        self._bind_slider_and_text(
            self.random_growth_min_slider,
            self.random_growth_min_box,
            0,
            7,
        )
        self._bind_slider_and_text(
            self.random_growth_max_slider,
            self.random_growth_max_box,
            0,
            7,
        )
        self._bind_slider_and_text(
            self.pattern_seed_slider,
            self.pattern_seed_box,
            0,
            PATTERN_SEED_MAX,
        )
        self._bind_slider_and_text(
            self.stem_spacing_slider,
            self.stem_spacing_box,
            0,
            2,
        )

        self.replace_grass_cb.Bind(wx.EVT_CHECKBOX, self._on_ui_setting_changed)
        self.replace_plants_cb.Bind(wx.EVT_CHECKBOX, self._on_ui_setting_changed)
        self.skip_isolated_raised_cb.Bind(wx.EVT_CHECKBOX, self._on_ui_setting_changed)
        self.raised_support_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        self.crop_layout_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        self.single_crop_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        self.growth_mode_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        self.row_direction_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        for crop_control in (
            self.crop_wheat_cb,
            self.crop_carrots_cb,
            self.crop_potatoes_cb,
            self.crop_beetroot_cb,
        ):
            crop_control.Bind(wx.EVT_CHECKBOX, self._on_ui_setting_changed)
        self.add_water_cb.Bind(wx.EVT_CHECKBOX, self._on_ui_setting_changed)
        self.moisture_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        self.water_cover_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        self.slab_type_choice.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)

        self.growth_slider.Bind(wx.EVT_SLIDER, self._on_growth_changed)
        self.growth_box.Bind(wx.EVT_TEXT, self._on_growth_text_changed)
        self.random_growth_min_slider.Bind(
            wx.EVT_SLIDER, self._on_random_growth_changed
        )
        self.random_growth_min_box.Bind(
            wx.EVT_TEXT, self._on_random_growth_changed
        )
        self.random_growth_max_slider.Bind(
            wx.EVT_SLIDER, self._on_random_growth_changed
        )
        self.random_growth_max_box.Bind(
            wx.EVT_TEXT, self._on_random_growth_changed
        )
        self.randomize_seed_button.Bind(wx.EVT_BUTTON, self._randomize_pattern_seed)

        self.create_button.Bind(wx.EVT_BUTTON, self._run_operation)
        self.manage_plugin_files_button.Bind(
            wx.EVT_BUTTON,
            self._manage_plugin_files,
        )
        self.save_report_button.Bind(wx.EVT_BUTTON, self._save_last_report)

        self.Layout()
        self.scroll.FitInside()
        self.SetMinSize((400, 780))
        try:
            wx.CallAfter(self._resize_settings_viewport)
        except Exception:
            self._resize_settings_viewport()

        self._initialize_settings_persistence()
        self._update_ui_visibility()
        self._update_growth_description()

    # -----------------------------------------------------------------
    # Responsive settings / console sizing
    # -----------------------------------------------------------------

    def _on_panel_resized(self, event) -> None:
        """Rebalance the settings viewport and console after a panel resize."""
        self._resize_settings_viewport()
        try:
            event.Skip()
        except Exception:
            pass

    def _resize_settings_viewport(self) -> None:
        """Reserve the requested console height before sizing settings.

        The previous layout gave the settings viewport a hard 500-pixel minimum
        and added the console with no stretch proportion. When the operation
        panel could not satisfy both requests, wxPython preserved the settings
        area and silently compressed the console. This calculation makes the
        settings area yield first because all of its controls remain reachable
        through scrolling.
        """
        try:
            _width, panel_height = self.GetClientSize()
        except Exception:
            return

        if panel_height <= 0:
            return

        try:
            create_height = self.create_button.GetBestSize().GetHeight()
        except Exception:
            create_height = 30
        try:
            save_height = self.save_report_button.GetBestSize().GetHeight()
        except Exception:
            save_height = 30

        # Vertical border space from the two buttons and console sizer entries:
        # 12 + 12 + 8 pixels, plus a small allowance for platform differences.
        fixed_controls_height = create_height + save_height + 40
        requested_console_height = max(
            int(self.CONSOLE_MIN_HEIGHT),
            int(self.CONSOLE_PREFERRED_HEIGHT),
        )
        target_height = (
            int(panel_height)
            - fixed_controls_height
            - requested_console_height
        )
        target_height = max(
            int(self.SETTINGS_VIEWPORT_MIN_HEIGHT),
            target_height,
        )
        target_height = min(
            int(self.SETTINGS_VIEWPORT_MAX_HEIGHT),
            target_height,
        )

        try:
            self.scroll.SetMinSize((320, target_height))
            self.scroll.SetInitialSize((-1, target_height))
            self.scroll.FitInside()
            self.scroll.Layout()
            self.Layout()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Amulet selection integration
    # -----------------------------------------------------------------

    def bind_events(self):
        """Bind Amulet selection events when this operation becomes active."""
        super().bind_events()
        if self._selection is None:
            self._selection = BlockSelectionBehaviour(self.canvas)
        self._selection.bind_events()
        self._selection.enable()

    def enable(self):
        """Enable Amulet's block-selection behavior for this operation panel."""
        if self._selection is None:
            self._selection = BlockSelectionBehaviour(self.canvas)
        self._selection.enable()

    # -----------------------------------------------------------------
    # Settings persistence and plugin-file management
    # -----------------------------------------------------------------

    def _settings_config_path(self) -> Path:
        """Return the stable per-user Auto Farmland settings path."""
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return (
            root
            / "AmuletTeam"
            / "AmuletMapEditor"
            / "Config"
            / "plugins"
            / "edit_plugins"
            / self.SETTINGS_CONFIG_FILENAME
        )

    @staticmethod
    def _plugin_directory() -> Path:
        """Return the folder containing the loaded plugin source file."""
        return Path(__file__).resolve().parent

    def _settings_registry(self) -> Mapping[str, wx.Window]:
        """Map stable config keys to user-controlled wx controls."""
        return {
            "replace_grass": self.replace_grass_cb,
            "raised_support": self.raised_support_choice,
            "replace_plants": self.replace_plants_cb,
            "skip_isolated_raised": self.skip_isolated_raised_cb,
            "crop_layout": self.crop_layout_choice,
            "single_crop": self.single_crop_choice,
            "crop_wheat": self.crop_wheat_cb,
            "crop_carrots": self.crop_carrots_cb,
            "crop_potatoes": self.crop_potatoes_cb,
            "crop_beetroot": self.crop_beetroot_cb,
            "growth_mode": self.growth_mode_choice,
            "growth": self.growth_slider,
            "random_growth_min": self.random_growth_min_slider,
            "random_growth_max": self.random_growth_max_slider,
            "row_direction": self.row_direction_choice,
            "stem_spacing": self.stem_spacing_slider,
            "pattern_seed": self.pattern_seed_slider,
            "add_water": self.add_water_cb,
            "moisture": self.moisture_choice,
            "water_cover": self.water_cover_choice,
            "slab_type": self.slab_type_choice,
        }

    @staticmethod
    def _control_value(control):
        """Convert one supported wx control value into JSON-safe data."""
        if isinstance(control, wx.CheckBox):
            return bool(control.GetValue())
        if isinstance(control, wx.Choice):
            return str(control.GetStringSelection())
        if isinstance(control, wx.Slider):
            return int(control.GetValue())
        raise TypeError(f"Unsupported settings control: {type(control).__name__}")

    @staticmethod
    def _setting_value_is_valid(control, value) -> bool:
        """Return whether a saved value can safely be applied to a control."""
        if isinstance(control, wx.CheckBox):
            return isinstance(value, bool)
        if isinstance(control, wx.Choice):
            return isinstance(value, str) and control.FindString(value) != wx.NOT_FOUND
        if isinstance(control, wx.Slider):
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and control.GetMin() <= value <= control.GetMax()
            )
        return False

    @classmethod
    def _set_control_value(cls, control, value) -> bool:
        """Apply one validated saved value to a supported control."""
        if not cls._setting_value_is_valid(control, value):
            return False

        try:
            if isinstance(control, wx.CheckBox):
                control.SetValue(value)
                return True
            if isinstance(control, wx.Choice):
                control.SetSelection(control.FindString(value))
                return True
            if isinstance(control, wx.Slider):
                control.SetValue(value)
                return True
        except Exception:
            return False

        return False

    def _capture_settings(self) -> Dict[str, object]:
        """Collect the current UI settings as JSON-safe values."""
        data = {
            key: self._control_value(control)
            for key, control in self._settings_registry().items()
        }
        data["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        data["plugin"] = "Auto Farmland"
        return data

    @staticmethod
    def _migrate_legacy_settings_data(
        data: Mapping[str, object],
    ) -> Dict[str, object]:
        """Map the previous single-crop config keys into the layout system."""
        migrated = dict(data)

        old_crop = migrated.get("crop")
        if "crop_layout" not in migrated and isinstance(old_crop, str):
            if old_crop == "None - Farmland only":
                migrated["crop_layout"] = "Farmland only"
            elif old_crop in STANDARD_CROPS:
                migrated["crop_layout"] = "Single Crop"
                migrated.setdefault("single_crop", old_crop)
            elif old_crop in STEM_CROPS:
                migrated["crop_layout"] = old_crop

        if "row_direction" not in migrated and isinstance(
            migrated.get("stem_direction"), str
        ):
            migrated["row_direction"] = migrated["stem_direction"]

        old_water_cover = migrated.get("water_cover")
        if old_water_cover == "Open water":
            migrated["water_cover"] = "Open Water"
        elif old_water_cover == "Waterlogged upper-half oak slab":
            migrated["water_cover"] = "Waterlogged Upper Slab"
            migrated.setdefault("slab_type", "Oak Slab")

        return migrated

    def _apply_settings_data(self, data: Mapping[str, object]) -> None:
        """Apply recognized settings while ignoring unknown or invalid entries."""
        if not isinstance(data, Mapping):
            return

        data = self._migrate_legacy_settings_data(data)
        self._settings_config_applying = True
        try:
            for key, control in self._settings_registry().items():
                if key in data:
                    self._set_control_value(control, data[key])
            self.growth_box.ChangeValue(str(self.growth_slider.GetValue()))
            self.random_growth_min_box.ChangeValue(
                str(self.random_growth_min_slider.GetValue())
            )
            self.random_growth_max_box.ChangeValue(
                str(self.random_growth_max_slider.GetValue())
            )
            self.pattern_seed_box.ChangeValue(str(self.pattern_seed_slider.GetValue()))
            self.stem_spacing_box.ChangeValue(str(self.stem_spacing_slider.GetValue()))
        finally:
            self._settings_config_applying = False

        self._update_ui_visibility()
        self._update_growth_description()
        try:
            self.scroll.FitInside()
            self.Layout()
        except Exception:
            pass

    def _load_settings_config_data(
        self,
        path: Optional[Path] = None,
    ) -> Optional[Dict[str, object]]:
        """Read and validate a settings object without applying it."""
        target = Path(path) if path is not None else self._settings_config_path()
        self._settings_config_load_error = ""

        try:
            if not target.is_file():
                raise FileNotFoundError(f"Settings file was not found: {target}")
            if target.stat().st_size > self.MAX_SETTINGS_CONFIG_BYTES:
                raise ValueError("The settings file exceeds the 1 MiB safety limit.")
            loaded = json.loads(target.read_text(encoding="utf-8-sig"))
            if not isinstance(loaded, dict):
                raise ValueError("The settings file root must be a JSON object.")
            return dict(loaded)
        except Exception as exc:
            self._settings_config_load_error = str(exc)
            return None

    def _normalize_settings_config_data(
        self,
        data: Optional[Mapping[str, object]],
        *,
        add_missing_defaults: bool,
    ) -> Dict[str, object]:
        """Preserve unknown keys while validating every recognized setting."""
        normalized: Dict[str, object] = (
            self._migrate_legacy_settings_data(data)
            if isinstance(data, Mapping)
            else {}
        )
        defaults = (
            self._settings_defaults
            if isinstance(self._settings_defaults, Mapping)
            else self._capture_settings()
        )

        for key, control in self._settings_registry().items():
            if key in normalized and self._setting_value_is_valid(control, normalized[key]):
                continue
            if add_missing_defaults and key in defaults:
                normalized[key] = defaults[key]
            else:
                normalized.pop(key, None)

        normalized["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        normalized["plugin"] = "Auto Farmland"
        return normalized

    def _merge_settings_config_data(
        self,
        existing: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        """Preserve unknown entries while updating all current settings."""
        if isinstance(existing, Mapping):
            merged: Dict[str, object] = dict(existing)
        elif isinstance(self._settings_config_unknown_data, Mapping):
            merged = dict(self._settings_config_unknown_data)
        else:
            merged = {}

        merged.update(self._capture_settings())
        return self._normalize_settings_config_data(
            merged,
            add_missing_defaults=True,
        )

    @staticmethod
    def _write_text_atomically(path: Path, content: str) -> None:
        """Write text through a temporary file, then atomically replace the target."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _initialize_settings_persistence(self) -> None:
        """Capture defaults, load saved values, and normalize the active config."""
        self._settings_defaults = self._capture_settings()
        path = self._settings_config_path()

        if not path.is_file():
            self._settings_config_unknown_data = {}
            self._write_settings_config(create_if_missing=True)
            return

        loaded = self._load_settings_config_data(path)
        if loaded is None:
            self._log(
                "Settings warning: Auto Farmland.config could not be loaded; "
                "current defaults are active. Reason: "
                f"{self._settings_config_load_error or 'Unknown error'}"
            )
            return

        normalized = self._normalize_settings_config_data(
            loaded,
            add_missing_defaults=True,
        )
        self._settings_config_unknown_data = dict(normalized)
        self._apply_settings_data(normalized)

        # Rewriting adds defaults introduced by newer builds while preserving
        # unknown keys from older or newer compatible versions.
        self._write_settings_config(create_if_missing=False)

    def _write_settings_config(self, create_if_missing: bool = True) -> bool:
        """Atomically create or update the active settings config."""
        if self._settings_config_applying:
            return False

        path = self._settings_config_path()
        if not create_if_missing and not path.exists():
            return True

        data = self._merge_settings_config_data()
        payload = json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        self._settings_config_write_error = ""
        try:
            self._write_text_atomically(path, payload)
            self._settings_config_unknown_data = dict(data)
            return True
        except Exception as exc:
            self._settings_config_write_error = str(exc)
            self._log(f"Settings warning: could not save Auto Farmland.config: {exc}")
            return False

    def _stop_pending_settings_save(self) -> None:
        """Cancel a delayed settings write before an explicit file action."""
        try:
            if self._settings_config_save_call is not None:
                self._settings_config_save_call.Stop()
        except Exception:
            pass
        self._settings_config_save_call = None

    def _schedule_settings_save(self, event=None) -> None:
        """Debounce automatic settings writes after a control changes."""
        try:
            if event is not None:
                event.Skip()
        except Exception:
            pass

        if self._settings_config_applying:
            return

        self._stop_pending_settings_save()
        self._settings_config_save_call = wx.CallLater(
            self.SETTINGS_SAVE_DELAY_MS,
            self._write_settings_config,
        )

    def _reset_settings_to_defaults(self) -> bool:
        """Restore current defaults and rewrite the active config."""
        defaults = self._settings_defaults
        if not isinstance(defaults, Mapping):
            self._settings_config_write_error = "Current defaults are unavailable."
            return False

        self._stop_pending_settings_save()
        self._apply_settings_data(defaults)
        self._settings_config_unknown_data = {}
        return self._write_settings_config(create_if_missing=True)

    @staticmethod
    def _repair_json_missing_line_commas(content: str) -> str:
        """Add commas between clearly adjacent JSON object entries."""
        lines = content.splitlines()
        repaired = list(lines)

        for index, line in enumerate(lines[:-1]):
            current = line.rstrip()
            stripped = current.strip()
            if not stripped or stripped.endswith((",", "{", "[", ":")):
                continue

            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index >= len(lines):
                continue

            if not lines[next_index].lstrip().startswith('"'):
                continue

            if (
                stripped.endswith(("}", "]", '"'))
                or re.search(r"(?:true|false|null|-?\d+(?:\.\d+)?)$", stripped)
            ):
                repaired[index] = current + ","

        return "\n".join(repaired)

    def _attempt_parse_repaired_settings_config(
        self,
        content: str,
    ) -> Tuple[Optional[Dict[str, object]], List[str]]:
        """Attempt bounded, data-only repairs and report what succeeded."""
        repairs: List[str] = []

        def try_json(candidate: str, repair_name: str):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    if repair_name:
                        repairs.append(repair_name)
                    return dict(parsed)
            except Exception:
                pass
            return None

        normalized = content.lstrip("\ufeff")
        data = try_json(normalized, "")
        if data is not None:
            return data, repairs

        without_trailing_commas = re.sub(r",(\s*[}\]])", r"\1", normalized)
        data = try_json(without_trailing_commas, "removed trailing commas")
        if data is not None:
            return data, repairs

        with_line_commas = self._repair_json_missing_line_commas(
            without_trailing_commas
        )
        data = try_json(with_line_commas, "restored missing entry commas")
        if data is not None:
            return data, repairs

        # ast.literal_eval parses data only and does not execute Python code.
        try:
            literal_data = ast.literal_eval(with_line_commas)
            if isinstance(literal_data, dict):
                repairs.append("normalized Python-style JSON values")
                return dict(literal_data), repairs
        except Exception:
            pass

        return None, repairs

    def _merge_recovered_settings_config_data(
        self,
        recovered: Mapping[str, object],
    ) -> Dict[str, object]:
        """Preserve recovered values and add valid current defaults as needed."""
        return self._normalize_settings_config_data(
            recovered,
            add_missing_defaults=True,
        )

    def _repair_existing_settings_config(self) -> None:
        """Conservatively repair and atomically replace the active config."""
        path = self._settings_config_path()
        if not path.is_file():
            wx.MessageBox(
                "No active Auto Farmland settings file was found.",
                "Auto Farmland",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        try:
            if path.stat().st_size > self.MAX_SETTINGS_CONFIG_BYTES:
                raise ValueError("The settings file exceeds the 1 MiB safety limit.")
            content = path.read_text(encoding="utf-8-sig", errors="strict")
        except Exception as exc:
            wx.MessageBox(
                f"The settings file could not be read.\n\nReason: {exc}",
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        repaired_data, repairs = self._attempt_parse_repaired_settings_config(content)
        if repaired_data is None:
            wx.MessageBox(
                "The settings file could not be repaired safely.\n\n"
                "No changes were made. Correct the JSON manually or import a "
                "known-good settings file.",
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        confirmation_lines = [
            "Repair and normalize the active Auto Farmland settings file?",
            "",
            "Recognized settings will be validated before they are applied.",
            "Unknown entries will be preserved.",
            "Missing current settings will be added with their defaults.",
            "The original file changes only after the repaired file is complete.",
        ]
        if repairs:
            confirmation_lines.extend(
                ["", "Detected repairs:", *[f"• {item}" for item in repairs]]
            )
        else:
            confirmation_lines.extend(
                [
                    "",
                    "The JSON is readable. It will be normalized and merged "
                    "with the current setting structure.",
                ]
            )

        confirmation = wx.MessageDialog(
            self,
            "\n".join(confirmation_lines),
            "Repair settings config?",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        try:
            if confirmation.ShowModal() != wx.ID_YES:
                return
        finally:
            confirmation.Destroy()

        merged = self._merge_recovered_settings_config_data(repaired_data)
        normalized_content = json.dumps(
            merged,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        self._stop_pending_settings_save()
        try:
            self._write_text_atomically(path, normalized_content)
        except Exception as exc:
            wx.MessageBox(
                "The repaired settings file could not be written.\n\n"
                f"Reason: {exc}",
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._settings_config_unknown_data = dict(merged)
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_data(merged)

        wx.MessageBox(
            "The settings file was repaired and reloaded successfully.",
            "Auto Farmland",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _import_settings_config(self) -> None:
        """Import a valid backup into the stable active config location."""
        dialog = wx.FileDialog(
            self,
            "Import Auto Farmland settings",
            wildcard=(
                "Auto Farmland config (*.config)|*.config|All files (*.*)|*.*"
            ),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            source_path = Path(dialog.GetPath())
        finally:
            dialog.Destroy()

        data = self._load_settings_config_data(source_path)
        if data is None:
            wx.MessageBox(
                "The selected settings file could not be imported.\n\n"
                f"Reason: {self._settings_config_load_error or 'Invalid file'}",
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        merged = self._merge_recovered_settings_config_data(data)
        content = json.dumps(
            merged,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        self._stop_pending_settings_save()
        try:
            self._write_text_atomically(self._settings_config_path(), content)
        except Exception as exc:
            wx.MessageBox(
                "The selected settings were valid, but the active settings file "
                "could not be written.\n\n"
                f"Reason: {exc}",
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._settings_config_unknown_data = dict(merged)
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_data(merged)

        wx.MessageBox(
            "Settings imported successfully.",
            "Auto Farmland",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _export_settings_config(self) -> None:
        """Export a backup without changing the active config location."""
        active_path = self._settings_config_path()
        existing: Optional[Dict[str, object]] = None

        if active_path.is_file():
            existing = self._load_settings_config_data(active_path)
            if existing is None:
                wx.MessageBox(
                    "The active settings file is malformed or unreadable.\n\n"
                    "Repair it before exporting so unknown saved entries are not "
                    "silently lost.",
                    "Auto Farmland",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
                return

        dialog = wx.FileDialog(
            self,
            "Export Auto Farmland settings",
            defaultFile=self.SETTINGS_CONFIG_FILENAME,
            wildcard=(
                "Auto Farmland config (*.config)|*.config|All files (*.*)|*.*"
            ),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            destination = Path(dialog.GetPath())
        finally:
            dialog.Destroy()

        merged = self._merge_settings_config_data(existing)
        content = json.dumps(
            merged,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        try:
            self._write_text_atomically(destination, content)
        except Exception as exc:
            wx.MessageBox(
                f"Could not export the settings file.\n\nReason: {exc}",
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        wx.MessageBox(
            "Settings exported successfully.",
            "Auto Farmland",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _show_plugin_file_action_dialog(
        self,
        actions: Sequence[Tuple[str, str]],
    ) -> Optional[int]:
        """Show a centered action picker with stable description space."""
        parent = wx.GetTopLevelParent(self) or self
        dialog = wx.Dialog(
            parent,
            title="Manage Auto Farmland Plugin Files",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        dialog.SetMinSize((480, 365))
        dialog.SetSize((540, 400))

        outer = wx.BoxSizer(wx.VERTICAL)
        description = wx.StaticText(
            dialog,
            label="Choose an Auto Farmland file-management action.",
        )
        description.SetMinSize((-1, 82))
        description.Wrap(455)
        outer.Add(description, 0, wx.EXPAND | wx.ALL, 12)

        choices = wx.ListBox(
            dialog,
            choices=[label for label, _description in actions],
            style=wx.LB_SINGLE,
        )
        outer.Add(choices, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        buttons = wx.StdDialogButtonSizer()
        open_button = wx.Button(dialog, wx.ID_OK, "Open")
        close_button = wx.Button(dialog, wx.ID_CANCEL, "Close")
        open_button.Enable(False)
        buttons.AddButton(open_button)
        buttons.AddButton(close_button)
        buttons.Realize()
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 12)
        dialog.SetSizer(outer)

        def update_description(event):
            selection = choices.GetSelection()
            if selection == wx.NOT_FOUND:
                open_button.Enable(False)
                return
            description.SetLabel(actions[selection][1])
            description.Wrap(455)
            open_button.Enable(True)
            dialog.Layout()

        def open_selected(event):
            if choices.GetSelection() != wx.NOT_FOUND:
                dialog.EndModal(wx.ID_OK)

        choices.Bind(wx.EVT_LISTBOX, update_description)
        choices.Bind(wx.EVT_LISTBOX_DCLICK, open_selected)

        try:
            dialog.CenterOnParent()
        except Exception:
            dialog.Centre()

        try:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            selection = choices.GetSelection()
            return selection if selection != wx.NOT_FOUND else None
        finally:
            dialog.Destroy()

    def _manage_plugin_files(self, _event) -> None:
        """Provide explicit local management for the plugin and its config."""
        actions = [
            (
                "Open plugin folder",
                "Open the folder containing the loaded Auto Farmland Python plugin.",
            ),
            (
                "Open settings folder",
                "Open the local Amulet edit-plugins settings folder containing "
                "Auto Farmland.config and other plugin config files.",
            ),
            (
                "Reset saved settings to defaults",
                "Restore every Auto Farmland option to the current plugin defaults "
                "and rewrite the active settings file.",
            ),
            (
                "Attempt to repair existing settings config",
                "Try a conservative manual repair when simple JSON damage prevents "
                "Auto Farmland.config from loading. Unknown recovered values are "
                "preserved where possible.",
            ),
            (
                "Import settings...",
                "Copy a selected Auto Farmland settings backup into the stable "
                "active config location and load its recognized values.",
            ),
            (
                "Export settings...",
                "Save a backup copy of the current Auto Farmland settings without "
                "moving or changing the active config path.",
            ),
            (
                "Delete settings config",
                "Delete only Auto Farmland.config and restore the visible controls "
                "to plugin defaults. Worlds and the plugin file are not changed.",
            ),
        ]

        action = self._show_plugin_file_action_dialog(actions)
        if action is None:
            return

        if action == 0:
            try:
                wx.LaunchDefaultApplication(str(self._plugin_directory()))
            except Exception as exc:
                wx.MessageBox(
                    f"Could not open the plugin folder.\n\nReason: {exc}",
                    "Auto Farmland",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            return

        if action == 1:
            try:
                directory = self._settings_config_path().parent
                directory.mkdir(parents=True, exist_ok=True)
                wx.LaunchDefaultApplication(str(directory))
            except Exception as exc:
                wx.MessageBox(
                    f"Could not open the settings folder.\n\nReason: {exc}",
                    "Auto Farmland",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            return

        if action == 2:
            confirmation = wx.MessageDialog(
                self,
                "Reset all Auto Farmland settings to their current defaults?\n\n"
                "The active settings file will be rewritten.",
                "Reset saved settings?",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            )
            try:
                confirmed = confirmation.ShowModal() == wx.ID_YES
            finally:
                confirmation.Destroy()
            if not confirmed:
                return

            if self._reset_settings_to_defaults():
                wx.MessageBox(
                    "Auto Farmland settings were reset successfully.",
                    "Auto Farmland",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                wx.MessageBox(
                    "The settings could not be reset.\n\n"
                    f"Reason: {self._settings_config_write_error or 'Unknown error'}",
                    "Auto Farmland",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            return

        if action == 3:
            self._repair_existing_settings_config()
            return

        if action == 4:
            self._import_settings_config()
            return

        if action == 5:
            self._export_settings_config()
            return

        confirmation = wx.MessageDialog(
            self,
            "Delete Auto Farmland.config?\n\n"
            "The visible settings will return to defaults. Worlds and the plugin "
            "file will not be changed.",
            "Delete Auto Farmland settings?",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        try:
            confirmed = confirmation.ShowModal() == wx.ID_YES
        finally:
            confirmation.Destroy()
        if not confirmed:
            return

        self._stop_pending_settings_save()
        path = self._settings_config_path()
        try:
            if path.is_file():
                path.unlink()
        except Exception as exc:
            wx.MessageBox(
                f"The settings file could not be deleted.\n\nReason: {exc}",
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        defaults = self._settings_defaults
        if isinstance(defaults, Mapping):
            self._apply_settings_data(defaults)
        self._settings_config_unknown_data = {}
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""

        wx.MessageBox(
            "Auto Farmland.config was deleted and visible settings were restored "
            "to defaults.",
            "Auto Farmland",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # -----------------------------------------------------------------
    # UI behavior
    # -----------------------------------------------------------------

    def _bind_slider_and_text(self, slider, text_box, minimum, maximum) -> None:
        """Keep one slider and numeric text box synchronized."""
        def on_slider(event):
            text_box.ChangeValue(str(slider.GetValue()))
            self._schedule_settings_save(event)

        def on_text(event):
            try:
                value = int(text_box.GetValue())
                value = max(minimum, min(maximum, value))
                slider.SetValue(value)
            except (TypeError, ValueError):
                pass
            self._schedule_settings_save(event)

        slider.Bind(wx.EVT_SLIDER, on_slider)
        text_box.Bind(wx.EVT_TEXT, on_text)

    def _on_ui_setting_changed(self, event) -> None:
        """Refresh dependent controls and queue a settings save."""
        self._update_ui_visibility()
        self._update_growth_description()
        self._schedule_settings_save(event)

    def _on_growth_changed(self, event) -> None:
        """Mirror fixed growth changes and refresh its description."""
        self.growth_box.ChangeValue(str(self.growth_slider.GetValue()))
        self._update_growth_description()
        self._schedule_settings_save(event)

    def _on_growth_text_changed(self, event) -> None:
        """Clamp typed fixed growth and refresh its description."""
        try:
            value = int(self.growth_box.GetValue())
            self.growth_slider.SetValue(max(0, min(7, value)))
        except (TypeError, ValueError):
            pass
        self._update_growth_description()
        self._schedule_settings_save(event)

    def _on_random_growth_changed(self, event) -> None:
        """Refresh the displayed random range and save it."""
        self._update_growth_description()
        self._schedule_settings_save(event)

    def _randomize_pattern_seed(self, event) -> None:
        """Generate, display and save a new deterministic pattern seed."""
        seed = int(datetime.now().timestamp() * 1_000_000) % (PATTERN_SEED_MAX + 1)
        self.pattern_seed_slider.SetValue(seed)
        self.pattern_seed_box.ChangeValue(str(seed))
        self._schedule_settings_save(event)

    def _update_growth_description(self) -> None:
        """Refresh fixed and random growth descriptions."""
        value = int(self.growth_slider.GetValue())
        description = GROWTH_DESCRIPTIONS.get(value, "Unknown")
        self.growth_description.SetLabel(
            f"State {value} of 7 - {description}"
        )

        minimum = int(self.random_growth_min_slider.GetValue())
        maximum = int(self.random_growth_max_slider.GetValue())
        low, high = sorted((minimum, maximum))
        self.growth_range_description.SetLabel(
            f"Random range: state {low} through state {high}"
        )

    def _selected_crop_controls(self) -> Tuple[Tuple[str, wx.CheckBox], ...]:
        """Return standard crops in their stable displayed order."""
        return (
            ("Wheat", self.crop_wheat_cb),
            ("Carrots", self.crop_carrots_cb),
            ("Potatoes", self.crop_potatoes_cb),
            ("Beetroot", self.crop_beetroot_cb),
        )

    def _update_ui_visibility(self) -> None:
        """Show only controls relevant to the current farm settings."""
        replace_mode = bool(self.replace_grass_cb.GetValue())
        layout = self.crop_layout_choice.GetStringSelection()
        standard_layout = layout in {
            "Single Crop",
            "Alternating Crop Rows",
            "Assorted Crops",
        }
        multi_crop_layout = layout in MULTI_CROP_LAYOUTS
        stem_mode = layout in STEM_CROPS
        row_mode = layout == "Alternating Crop Rows" or stem_mode
        growth_mode = self.growth_mode_choice.GetStringSelection()
        random_growth = (
            standard_layout and growth_mode == "Random growth range"
        )
        fixed_growth = stem_mode or (standard_layout and not random_growth)
        seed_needed = layout == "Assorted Crops" or random_growth
        add_water = bool(self.add_water_cb.GetValue())

        self.placement_explanation.SetLabel(
            "Eligible grass blocks are replaced with farmland at their current position."
            if replace_mode
            else (
                "Farmland is placed one block above safe exposed surfaces. "
                "Existing support blocks remain unchanged."
            )
        )
        self.placement_explanation.Wrap(350)

        self.raised_support_label.Show(not replace_mode)
        self.raised_support_choice.Show(not replace_mode)
        self.skip_isolated_raised_cb.Show(not replace_mode)

        self.single_crop_label.Show(layout == "Single Crop")
        self.single_crop_choice.Show(layout == "Single Crop")
        self.selected_crops_label.Show(multi_crop_layout)
        for _crop, control in self._selected_crop_controls():
            control.Show(multi_crop_layout)

        self.row_direction_label.Show(row_mode)
        self.row_direction_choice.Show(row_mode)

        self.growth_mode_label.Show(standard_layout)
        self.growth_mode_choice.Show(standard_layout)
        self.growth_label.Show(fixed_growth)
        self.growth_slider.Show(fixed_growth)
        self.growth_box.Show(fixed_growth)
        self.growth_description.Show(fixed_growth)

        self.random_growth_min_label.Show(random_growth)
        self.random_growth_min_slider.Show(random_growth)
        self.random_growth_min_box.Show(random_growth)
        self.random_growth_max_label.Show(random_growth)
        self.random_growth_max_slider.Show(random_growth)
        self.random_growth_max_box.Show(random_growth)
        self.growth_range_description.Show(random_growth)

        self.pattern_seed_label.Show(seed_needed)
        self.pattern_seed_slider.Show(seed_needed)
        self.pattern_seed_box.Show(seed_needed)
        self.randomize_seed_button.Show(seed_needed)

        self.stem_spacing_label.Show(stem_mode)
        self.stem_spacing_slider.Show(stem_mode)
        self.stem_spacing_box.Show(stem_mode)

        slab_cover = (
            add_water
            and self.water_cover_choice.GetStringSelection()
            == "Waterlogged Upper Slab"
        )
        self.moisture_label.Show(add_water)
        self.moisture_choice.Show(add_water)
        self.water_cover_label.Show(add_water)
        self.water_cover_choice.Show(add_water)
        self.slab_type_label.Show(slab_cover)
        self.slab_type_choice.Show(slab_cover)

        try:
            self.scroll.FitInside()
            self.Layout()
            self.GetParent().Layout()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Report helpers
    # -----------------------------------------------------------------

    def _clear_log(self) -> None:
        """Reset the visible and in-memory operation report."""
        self._report_lines = []
        self._last_report_text = ""
        self.save_report_button.Enable(False)
        try:
            self.text.SetValue("")
        except Exception:
            pass

    def _append_log_text(self, message: str) -> None:
        """Append one line to the visible report console."""
        try:
            self.text.AppendText(str(message) + "\n")
        except Exception:
            pass

    def _log(self, message: object = "") -> None:
        """Write one report line to stdout, memory and the console."""
        text = str(message)
        print(text)
        self._report_lines.append(text)
        try:
            wx.CallAfter(self._append_log_text, text)
        except Exception:
            self._append_log_text(text)

    def _log_section(self, title: str, rows: Iterable[Tuple[str, object]]) -> None:
        """Write one labeled report section."""
        self._log("")
        self._log(title)
        for label, value in rows:
            self._log(f"{label}: {value}")

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        """Format elapsed time for operation reports."""
        if seconds < 60:
            return f"{seconds:.2f} seconds"
        minutes = int(seconds // 60)
        remaining = seconds - minutes * 60
        return f"{minutes} minute(s), {remaining:.2f} seconds"

    def _finalize_report(self) -> None:
        """Store the completed report and enable report saving."""
        self._last_report_text = "\n".join(self._report_lines).strip()
        self.save_report_button.Enable(bool(self._last_report_text))

    def _save_last_report(self, _event) -> None:
        """Save the latest report as a UTF-8 text file."""
        if not self._last_report_text:
            wx.MessageBox(
                "No Auto Farmland report is available yet.",
                "No Report",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        default_name = (
            "Auto Farmland report; "
            + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".txt"
        )
        dialog = wx.FileDialog(
            self,
            message="Save Auto Farmland report",
            defaultFile=default_name,
            wildcard="Text files (*.txt)|*.txt|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = Path(dialog.GetPath())
            path.write_text(self._last_report_text + "\n", encoding="utf-8", newline="\n")
        except Exception as exc:
            wx.MessageBox(
                f"The report could not be saved.\n\nReason: {exc}",
                "Save Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )
        finally:
            dialog.Destroy()

    # -----------------------------------------------------------------
    # Selection and general block helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _normalize_box_tuple(box) -> BoxTuple:
        """Convert an Amulet selection box into a stable tuple."""
        if isinstance(box, tuple) and len(box) == 6:
            return tuple(int(value) for value in box)  # type: ignore[return-value]
        return (
            int(box.min_x),
            int(box.max_x),
            int(box.min_y),
            int(box.max_y),
            int(box.min_z),
            int(box.max_z),
        )

    @staticmethod
    def _position_in_boxes(pos: Position, boxes: Sequence[BoxTuple]) -> bool:
        """Return whether a position is inside any selected box."""
        x, y, z = pos
        for min_x, max_x, min_y, max_y, min_z, max_z in boxes:
            if (
                min_x <= x < max_x
                and min_y <= y < max_y
                and min_z <= z < max_z
            ):
                return True
        return False

    @staticmethod
    def _selection_column_estimate(boxes: Sequence[BoxTuple]) -> int:
        """Estimate selected horizontal columns before scanning."""
        return sum((box[1] - box[0]) * (box[5] - box[4]) for box in boxes)

    @staticmethod
    def _merge_intervals(intervals: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Merge overlapping or touching half-open Y intervals."""
        if not intervals:
            return []
        ordered = sorted(intervals)
        merged = [ordered[0]]
        for start, end in ordered[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def _build_column_ranges(
        self,
        boxes: Sequence[BoxTuple],
    ) -> Dict[Tuple[int, int], List[Tuple[int, int]]]:
        """Build merged selected Y ranges for each X / Z column."""
        columns: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        for min_x, max_x, min_y, max_y, min_z, max_z in boxes:
            for x in range(min_x, max_x):
                for z in range(min_z, max_z):
                    columns.setdefault((x, z), []).append((min_y, max_y))
        for key, intervals in list(columns.items()):
            columns[key] = self._merge_intervals(intervals)
        return columns

    @staticmethod
    def _iter_y_desc(intervals: Sequence[Tuple[int, int]]):
        """Yield selected Y coordinates from highest to lowest."""
        for min_y, max_y in sorted(intervals, reverse=True):
            for y in range(max_y - 1, min_y - 1, -1):
                yield y

    @staticmethod
    def _tag_value(value):
        """Extract a plain Python value from a common NBT tag wrapper."""
        for attribute in ("py_data", "value"):
            try:
                return getattr(value, attribute)
            except Exception:
                pass
        return value

    @classmethod
    def _state_bool(cls, value) -> Optional[bool]:
        """Interpret common Bedrock state values as a boolean."""
        if value is None:
            return None
        raw = cls._tag_value(value)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        text = str(raw).strip().lower()
        if text in {"true", "1", "yes", "upper", "top"}:
            return True
        if text in {"false", "0", "no", "lower", "bottom"}:
            return False
        return None

    @staticmethod
    def _is_air(block: Block) -> bool:
        """Return whether a block is one of the supported air identities."""
        return block.base_name in AIR_NAMES

    @staticmethod
    def _block_layers(block: Block):
        """Yield the base block and any attached extra block layers."""
        yield block
        for extra in getattr(block, "extra_blocks", ()) or ():
            yield extra

    def _block_contains_water(self, block: Block) -> bool:
        """Return whether any block layer contains water."""
        return any(layer.base_name in WATER_NAMES for layer in self._block_layers(block))

    def _is_replaceable_plant(self, block: Block) -> bool:
        """Return whether decorative plant replacement may clear a block."""
        return block.base_name in REPLACEABLE_DECORATIVE_PLANTS

    @staticmethod
    def _is_missing_chunk_error(exc: Exception) -> bool:
        """Recognize Amulet missing-chunk exceptions without importing internals."""
        return exc.__class__.__name__ == "ChunkDoesNotExist"

    def _read_block_cached(
        self,
        pos: Position,
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
    ) -> ReadResult:
        """Read a block once per operation and cache missing chunks."""
        if pos in cache:
            return cache[pos]

        x, y, z = pos
        cx, cz = block_coords_to_chunk_coords(x, z)
        if (cx, cz) in missing_chunks:
            result = (Block("minecraft", "air"), None, False)
            cache[pos] = result
            return result

        try:
            if not self.world.has_chunk(cx, cz, dim):
                missing_chunks.add((cx, cz))
                result = (Block("minecraft", "air"), None, False)
            else:
                block, entity = self.world.get_version_block(
                    x,
                    y,
                    z,
                    dim,
                    (plat, ver),
                )
                result = (block, entity, True)
        except Exception as exc:
            if self._is_missing_chunk_error(exc):
                missing_chunks.add((cx, cz))
                result = (Block("minecraft", "air"), None, False)
            else:
                raise

        cache[pos] = result
        return result

    def _connected_plant_positions(
        self,
        pos: Position,
        block: Block,
        boxes: Sequence[BoxTuple],
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
    ) -> Optional[Set[Position]]:
        """Return all selected halves that must be cleared, or None if unsafe."""
        positions = {pos}
        if block.base_name not in DOUBLE_HEIGHT_PLANTS:
            return positions

        x, y, z = pos
        props = getattr(block, "properties", {}) or {}
        upper_bit = props.get("upper_block_bit")
        half = props.get("half")

        candidates = [(x, y + 1, z), (x, y - 1, z)]
        upper_value = self._state_bool(upper_bit)
        if upper_value is not None:
            candidates = [(x, y - 1, z)] if upper_value else [(x, y + 1, z)]
        elif half is not None:
            half_text = str(self._tag_value(half)).strip().lower()
            if half_text in {"upper", "top"}:
                candidates = [(x, y - 1, z)]
            elif half_text in {"lower", "bottom"}:
                candidates = [(x, y + 1, z)]

        for partner_pos in candidates:
            partner_block, partner_entity, available = self._read_block_cached(
                partner_pos,
                dim,
                plat,
                ver,
                cache,
                missing_chunks,
            )
            if not available or partner_block.base_name != block.base_name:
                continue
            if partner_entity is not None:
                return None
            if not self._position_in_boxes(partner_pos, boxes):
                return None
            positions.add(partner_pos)
            break

        return positions

    def _classify_clear_target(
        self,
        pos: Position,
        boxes: Sequence[BoxTuple],
        replace_plants: bool,
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
    ) -> Tuple[bool, Set[Position], Dict[Position, Tuple[Block, object]], str]:
        """Validate whether a target may remain, clear, or block planning."""
        block, entity, available = self._read_block_cached(
            pos,
            dim,
            plat,
            ver,
            cache,
            missing_chunks,
        )
        originals = {pos: (block, entity)}

        if not available:
            return False, set(), originals, "unavailable_chunk"
        if entity is not None:
            return False, set(), originals, "block_entity"
        if self._is_air(block):
            return True, set(), originals, "air"
        if not replace_plants or not self._is_replaceable_plant(block):
            return False, set(), originals, "protected_obstruction"
        if not self._position_in_boxes(pos, boxes):
            return False, set(), originals, "outside_selection"

        connected = self._connected_plant_positions(
            pos,
            block,
            boxes,
            dim,
            plat,
            ver,
            cache,
            missing_chunks,
        )
        if connected is None:
            return False, set(), originals, "connected_plant_outside_selection"

        for connected_pos in connected:
            connected_block, connected_entity, available = self._read_block_cached(
                connected_pos,
                dim,
                plat,
                ver,
                cache,
                missing_chunks,
            )
            if not available or connected_entity is not None:
                return False, set(), originals, "connected_plant_unsafe"
            originals[connected_pos] = (connected_block, connected_entity)

        return True, connected, originals, "replaceable_plant"

    def _is_safe_raised_support(self, block: Block, entity, support_mode: str) -> bool:
        """Return whether a block may support raised farmland."""
        if entity is not None:
            return False
        if self._block_contains_water(block):
            return False
        name = block.base_name
        if name in AIR_NAMES or name in FARMLAND_NAMES:
            return False
        if name in NATURAL_RAISED_SUPPORTS:
            return True
        if support_mode == "Natural terrain only":
            return False
        return not any(keyword in name for keyword in UNSAFE_SUPPORT_KEYWORDS)

    # -----------------------------------------------------------------
    # Exact block constructors from the supplied Bedrock construction samples
    # -----------------------------------------------------------------

    @staticmethod
    def _farmland_block(moisture: int) -> Block:
        """Construct Bedrock farmland with the requested moisture state."""
        return Block(
            "minecraft",
            "farmland",
            {"moisturized_amount": TAG_Int(int(moisture))},
        )

    @staticmethod
    def _crop_block(crop: str, growth: int) -> Block:
        """Construct one Bedrock crop or stem at the requested growth state."""
        base_name = CROP_BLOCK_NAMES[crop]
        properties = {"growth": TAG_Int(int(growth))}
        if crop in STEM_CROPS:
            properties["facing_direction"] = TAG_Int(0)
        return Block("minecraft", base_name, properties)

    @staticmethod
    def _source_water_block() -> Block:
        """Construct a Bedrock source-water block."""
        return Block(
            "minecraft",
            "water",
            {"liquid_depth": TAG_Int(0)},
        )

    def _planned_water_block(self, water_cover: str, slab_type: str) -> Block:
        """Construct open water or the selected waterlogged upper slab."""
        water = self._source_water_block()
        if water_cover == "Waterlogged Upper Slab":
            slab_name = SLAB_BLOCK_NAMES.get(
                slab_type,
                SLAB_BLOCK_NAMES["Oak Slab"],
            )
            return Block(
                "minecraft",
                slab_name,
                {"minecraft:vertical_half": TAG_String("top")},
                extra_blocks=water,
            )
        return water

    # -----------------------------------------------------------------
    # Surface scanning
    # -----------------------------------------------------------------

    def _scan_surface_candidates(
        self,
        boxes: Sequence[BoxTuple],
        settings: Mapping[str, object],
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
        counters: Dict[str, int],
    ) -> Dict[Position, SurfaceCandidate]:
        """Find the highest safe farm candidate in each selected column."""
        replace_mode = bool(settings["replace_grass"])
        replace_plants = bool(settings["replace_plants"])
        crop_layout = str(settings["crop_layout"])
        crop_selected = crop_layout != "Farmland only"
        support_mode = str(settings["raised_support"])

        column_ranges = self._build_column_ranges(boxes)
        counters["columns_scanned"] = len(column_ranges)
        candidates: Dict[Position, SurfaceCandidate] = {}

        for index, ((x, z), intervals) in enumerate(column_ranges.items(), start=1):
            if index % PROGRESS_INTERVAL == 0:
                self._log(f"Surface scan progress: {index:,} columns checked")

            encountered_protected_top = False
            for y in self._iter_y_desc(intervals):
                pos = (x, y, z)
                block, entity, available = self._read_block_cached(
                    pos,
                    dim,
                    plat,
                    ver,
                    cache,
                    missing_chunks,
                )
                if not available:
                    counters["unavailable_columns"] += 1
                    encountered_protected_top = True
                    break
                if self._is_air(block):
                    continue
                if self._is_replaceable_plant(block):
                    if replace_plants:
                        continue
                    counters["protected_top_blocks"] += 1
                    encountered_protected_top = True
                    break

                # The first non-air, non-decorative block is the actual exposed
                # support. Never continue downward to buried grass or farmland.
                if entity is not None:
                    counters["block_entity_supports"] += 1
                    break

                if block.base_name in FARMLAND_NAMES:
                    farmland_pos = pos
                elif replace_mode:
                    if block.base_name not in GRASS_BLOCK_NAMES:
                        counters["ineligible_supports"] += 1
                        break
                    farmland_pos = pos
                else:
                    if not self._is_safe_raised_support(block, entity, support_mode):
                        counters["ineligible_supports"] += 1
                        break
                    farmland_pos = (x, y + 1, z)
                    if not self._position_in_boxes(farmland_pos, boxes):
                        counters["insufficient_selected_height"] += 1
                        break

                crop_pos = (farmland_pos[0], farmland_pos[1] + 1, farmland_pos[2])
                if crop_selected and not self._position_in_boxes(crop_pos, boxes):
                    counters["insufficient_selected_height"] += 1
                    break

                clear_positions: Set[Position] = set()
                originals: Dict[Position, Tuple[Block, object]] = {
                    pos: (block, entity)
                }

                # Raised farmland occupies an air / plant position above the support.
                if farmland_pos != pos:
                    ok, clears, target_originals, reason = self._classify_clear_target(
                        farmland_pos,
                        boxes,
                        replace_plants,
                        dim,
                        plat,
                        ver,
                        cache,
                        missing_chunks,
                    )
                    originals.update(target_originals)
                    if not ok:
                        counters[reason] = counters.get(reason, 0) + 1
                        break
                    clear_positions.update(clears)

                # Farmland must not be covered. This check is required even in
                # Farmland-only mode. A decorative plant can be cleared only when
                # its complete connected form passes the safety checks.
                ok, clears, target_originals, reason = self._classify_clear_target(
                    crop_pos,
                    boxes,
                    replace_plants,
                    dim,
                    plat,
                    ver,
                    cache,
                    missing_chunks,
                )
                originals.update(target_originals)
                if not ok:
                    counters[reason] = counters.get(reason, 0) + 1
                    break
                clear_positions.update(clears)

                candidate = SurfaceCandidate(
                    farmland_pos=farmland_pos,
                    crop_pos=crop_pos,
                    clear_positions=clear_positions,
                    originals=originals,
                )
                candidates[farmland_pos] = candidate
                counters["eligible_candidates"] += 1
                break

            if encountered_protected_top:
                continue

        return candidates

    @staticmethod
    def _connected_components(positions: Set[Position]) -> List[Set[Position]]:
        """Split horizontal positions into four-neighbor components."""
        remaining = set(positions)
        components: List[Set[Position]] = []
        while remaining:
            start = remaining.pop()
            component = {start}
            stack = [start]
            while stack:
                x, y, z = stack.pop()
                for neighbor in (
                    (x - 1, y, z),
                    (x + 1, y, z),
                    (x, y, z - 1),
                    (x, y, z + 1),
                ):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        stack.append(neighbor)
            components.append(component)
        return components

    def _remove_isolated_raised_candidates(
        self,
        candidates: Dict[Position, SurfaceCandidate],
        settings: Mapping[str, object],
        counters: Dict[str, int],
    ) -> Dict[Position, SurfaceCandidate]:
        """Remove isolated raised candidates when that option is enabled."""
        if bool(settings["replace_grass"]):
            return candidates
        if not bool(settings["skip_isolated_raised"]):
            return candidates
        if len(candidates) <= 1:
            return candidates

        retained: Set[Position] = set()
        for component in self._connected_components(set(candidates)):
            if len(component) == 1:
                counters["isolated_raised_skips"] += 1
            else:
                retained.update(component)
        return {pos: candidates[pos] for pos in retained}

    def _scan_read_only_safety_context(
        self,
        candidates: Mapping[Position, SurfaceCandidate],
        boxes: Sequence[BoxTuple],
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
        counters: Dict[str, int],
    ) -> None:
        """Read the relevant two-block context outside the selected farm.

        The plugin never writes to these coordinates. Reading the boundary
        context makes terrain edges, nearby obstructions and unavailable chunks
        known before fruit-lane and irrigation planning proceeds. Interior
        positions are already represented by the candidate and target scans, so
        only coordinates outside the selection are added here.
        """
        context_positions: Set[Position] = set()
        for candidate in candidates.values():
            x, farmland_y, z = candidate.farmland_pos
            for dx in range(-SAFETY_CONTEXT_RADIUS, SAFETY_CONTEXT_RADIUS + 1):
                for dz in range(-SAFETY_CONTEXT_RADIUS, SAFETY_CONTEXT_RADIUS + 1):
                    if dx == 0 and dz == 0:
                        continue
                    for context_y in (farmland_y - 1, farmland_y, farmland_y + 1, farmland_y + 2):
                        pos = (x + dx, context_y, z + dz)
                        if not self._position_in_boxes(pos, boxes):
                            context_positions.add(pos)

        for pos in context_positions:
            self._read_block_cached(
                pos,
                dim,
                plat,
                ver,
                cache,
                missing_chunks,
            )
        counters["safety_context_positions_read"] = len(context_positions)

    # -----------------------------------------------------------------
    # Crop layout
    # -----------------------------------------------------------------

    @staticmethod
    def _combined_selection_bounds(boxes: Sequence[BoxTuple]) -> Tuple[int, int, int, int]:
        """Return combined horizontal bounds for selected boxes."""
        return (
            min(box[0] for box in boxes),
            max(box[1] for box in boxes),
            min(box[4] for box in boxes),
            max(box[5] for box in boxes),
        )

    def _row_axis(self, boxes: Sequence[BoxTuple], direction_setting: str) -> str:
        """Resolve an explicit or automatic row axis."""
        if direction_setting == "Along X":
            return "x"
        if direction_setting == "Along Z":
            return "z"
        min_x, max_x, min_z, max_z = self._combined_selection_bounds(boxes)
        return "x" if (max_x - min_x) >= (max_z - min_z) else "z"

    @staticmethod
    def _selection_box_index_for_position(
        pos: Position,
        boxes: Sequence[BoxTuple],
    ) -> int:
        """Return the first selection box that owns one selected position.

        Automatic row layouts treat each selection box as an independent field.
        Touching boxes do not share any blocks and therefore never influence one
        another. If boxes overlap, however, the same farmland column cannot use
        two different row axes. The earlier selection box keeps ownership of the
        shared column, and later boxes apply their layout only to positions that
        were not already claimed. This preserves an existing field instead of
        allowing a later, smaller box to cut a different row direction through it.
        """
        x, y, z = pos
        for index, box in enumerate(boxes):
            min_x, max_x, min_y, max_y, min_z, max_z = box
            if (
                min_x <= x < max_x
                and min_y <= y < max_y
                and min_z <= z < max_z
            ):
                return index

        # Surface candidates are created only from selected positions, so this
        # is a defensive fallback rather than an expected path.
        return 0

    @staticmethod
    def _selected_standard_crops(
        settings: Mapping[str, object],
    ) -> Tuple[str, ...]:
        """Return enabled standard crops in stable UI order."""
        selected: List[str] = []
        key_by_crop = {
            "Wheat": "crop_wheat",
            "Carrots": "crop_carrots",
            "Potatoes": "crop_potatoes",
            "Beetroot": "crop_beetroot",
        }
        for crop in STANDARD_CROPS:
            if bool(settings.get(key_by_crop[crop], False)):
                selected.append(crop)
        return tuple(selected)

    @staticmethod
    def _deterministic_value(
        pos: Position,
        seed: int,
        salt: int = 0,
    ) -> int:
        """Return a stable 64-bit value for coordinates, seed and purpose."""
        x, y, z = pos
        value = (
            (int(seed) & 0xFFFFFFFFFFFFFFFF)
            ^ ((x & 0xFFFFFFFFFFFFFFFF) * 0x9E3779B185EBCA87)
            ^ ((y & 0xFFFFFFFFFFFFFFFF) * 0xC2B2AE3D27D4EB4F)
            ^ ((z & 0xFFFFFFFFFFFFFFFF) * 0x165667B19E3779F9)
            ^ ((int(salt) & 0xFFFFFFFFFFFFFFFF) * 0x85EBCA77C2B2AE63)
        ) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 30
        value = (value * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 27
        value = (value * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 31
        return value & 0xFFFFFFFFFFFFFFFF

    def _plan_crop_layout(
        self,
        candidates: Dict[Position, SurfaceCandidate],
        boxes: Sequence[BoxTuple],
        settings: Mapping[str, object],
        counters: Dict[str, int],
    ) -> Tuple[Set[Position], Dict[Position, str], Set[Position], Set[Position]]:
        """Assign farmland, crops, fruit lanes and water-eligible positions."""
        layout = str(settings["crop_layout"])
        if layout == "Farmland only":
            return set(candidates), {}, set(), set(candidates)

        if layout == "Single Crop":
            crop = str(settings["single_crop"])
            crop_positions = {
                candidate.crop_pos: crop
                for candidate in candidates.values()
            }
            return set(candidates), crop_positions, set(), set(candidates)

        if layout in MULTI_CROP_LAYOUTS:
            selected_crops = self._selected_standard_crops(settings)
            crop_positions: Dict[Position, str] = {}
            min_x, _max_x, min_z, _max_z = self._combined_selection_bounds(boxes)

            if layout == "Alternating Crop Rows":
                direction_setting = str(settings["row_direction"])

                if direction_setting == "Automatic":
                    # Each selection box is an independent field for automatic
                    # orientation. This prevents one long X-oriented box from
                    # forcing a separate long Z-oriented box to use X rows, or
                    # vice versa. Earlier boxes own overlapping columns, so a
                    # later selection cannot cut its axis through an existing
                    # field. The crop sequence begins at each box's local
                    # cross-axis edge for a clean, predictable pattern.
                    candidates_by_box: Dict[
                        int,
                        List[Tuple[Position, SurfaceCandidate]],
                    ] = {}
                    for farmland_pos, candidate in candidates.items():
                        box_index = self._selection_box_index_for_position(
                            farmland_pos,
                            boxes,
                        )
                        candidates_by_box.setdefault(box_index, []).append(
                            (farmland_pos, candidate)
                        )

                    for box_index in sorted(candidates_by_box):
                        box = boxes[box_index]
                        row_axis = self._row_axis((box,), "Automatic")
                        origin = box[4] if row_axis == "x" else box[0]

                        for farmland_pos, candidate in candidates_by_box[box_index]:
                            cross = (
                                farmland_pos[2]
                                if row_axis == "x"
                                else farmland_pos[0]
                            )
                            crop = selected_crops[
                                (cross - origin) % len(selected_crops)
                            ]
                            crop_positions[candidate.crop_pos] = crop
                else:
                    # Explicit directions intentionally remain global so every
                    # selected box follows the user's chosen axis and alignment.
                    row_axis = self._row_axis(boxes, direction_setting)
                    for farmland_pos, candidate in candidates.items():
                        cross = (
                            farmland_pos[2]
                            if row_axis == "x"
                            else farmland_pos[0]
                        )
                        origin = min_z if row_axis == "x" else min_x
                        crop = selected_crops[
                            (cross - origin) % len(selected_crops)
                        ]
                        crop_positions[candidate.crop_pos] = crop
            else:
                seed = int(settings["pattern_seed"])
                for candidate in candidates.values():
                    index = self._deterministic_value(
                        candidate.crop_pos,
                        seed,
                        salt=1,
                    ) % len(selected_crops)
                    crop_positions[candidate.crop_pos] = selected_crops[index]

            return set(candidates), crop_positions, set(), set(candidates)

        crop = layout
        replace_mode = bool(settings["replace_grass"])
        direction_setting = str(settings["row_direction"])
        step = int(settings["stem_spacing"]) + 1

        candidate_positions = set(candidates)
        stem_farmland: Set[Position] = set()
        crop_positions: Dict[Position, str] = {}
        reserved_fruit: Set[Position] = set()
        water_eligible: Set[Position] = set()

        # Automatic orientation treats each selection box as an independent
        # field. Earlier boxes keep any overlapping columns so later boxes cannot
        # cut another stem axis through them. Explicit Along X / Along Z continues
        # to use one global layout.
        stem_layout_groups: List[Tuple[str, Set[Position]]] = []
        if direction_setting == "Automatic":
            positions_by_box: Dict[int, Set[Position]] = {}
            for pos in candidate_positions:
                box_index = self._selection_box_index_for_position(pos, boxes)
                positions_by_box.setdefault(box_index, set()).add(pos)

            for box_index in sorted(positions_by_box):
                row_axis = self._row_axis((boxes[box_index],), "Automatic")
                stem_layout_groups.append(
                    (row_axis, positions_by_box[box_index])
                )
        else:
            stem_layout_groups.append(
                (self._row_axis(boxes, direction_setting), candidate_positions)
            )

        for row_axis, group_positions in stem_layout_groups:
            # Group by farmland elevation so alternating rows do not
            # accidentally connect terraces that share X / Z coordinates.
            positions_by_y: Dict[int, Set[Position]] = {}
            for pos in group_positions:
                positions_by_y.setdefault(pos[1], set()).add(pos)

            for farmland_y, terrace_positions in positions_by_y.items():
                if row_axis == "x":
                    cross_values = [pos[2] for pos in terrace_positions]
                    along_values = [pos[0] for pos in terrace_positions]
                else:
                    cross_values = [pos[0] for pos in terrace_positions]
                    along_values = [pos[2] for pos in terrace_positions]

                cross_origin = min(cross_values)
                along_origin = min(along_values)

                for pos in sorted(terrace_positions):
                    x, _y, z = pos
                    cross = z if row_axis == "x" else x
                    along = x if row_axis == "x" else z
                    offset = cross - cross_origin

                    if offset % 2 == 1:
                        reserved_fruit.add(pos)
                        if not replace_mode:
                            stem_farmland.add(pos)
                        continue

                    water_eligible.add(pos)
                    if (along - along_origin) % step != 0:
                        if not replace_mode:
                            stem_farmland.add(pos)
                        counters["stem_spacing_skips"] += 1
                        continue

                    fruit_pos = None
                    for delta in (1, -1):
                        test = (
                            (x, farmland_y, z + delta)
                            if row_axis == "x"
                            else (x + delta, farmland_y, z)
                        )
                        if test in reserved_fruit or (
                            test in terrace_positions
                            and (
                                (
                                    (
                                        test[2]
                                        if row_axis == "x"
                                        else test[0]
                                    )
                                    - cross_origin
                                )
                                % 2
                                == 1
                            )
                        ):
                            fruit_pos = test
                            break

                    if fruit_pos is None or fruit_pos not in terrace_positions:
                        counters["stems_without_fruit_space"] += 1
                        if not replace_mode:
                            stem_farmland.add(pos)
                        continue

                    reserved_fruit.add(fruit_pos)
                    stem_farmland.add(pos)
                    crop_positions[candidates[pos].crop_pos] = crop
                    counters["stems_planned"] += 1

        if not replace_mode:
            stem_farmland.update(candidate_positions)
            water_eligible.update(candidate_positions - reserved_fruit)

        return stem_farmland, crop_positions, reserved_fruit, water_eligible

    def _growth_for_crop_position(
        self,
        crop_pos: Position,
        settings: Mapping[str, object],
    ) -> int:
        """Resolve fixed or deterministic random crop growth."""
        layout = str(settings["crop_layout"])
        if layout in STEM_CROPS:
            return int(settings["growth"])
        if str(settings["growth_mode"]) != "Random growth range":
            return int(settings["growth"])

        low, high = sorted(
            (
                int(settings["random_growth_min"]),
                int(settings["random_growth_max"]),
            )
        )
        span = high - low + 1
        value = self._deterministic_value(
            crop_pos,
            int(settings["pattern_seed"]),
            salt=2,
        )
        return low + (value % span)

    # -----------------------------------------------------------------
    # Hydration and water planning
    # -----------------------------------------------------------------

    @staticmethod
    def _positions_hydrated_by_water(
        water_pos: Position,
        farmland_positions: Set[Position],
    ) -> Set[Position]:
        """Return planned farmland covered by one water source."""
        wx_, wy, wz = water_pos
        covered: Set[Position] = set()
        for dx in range(-HYDRATION_RADIUS, HYDRATION_RADIUS + 1):
            for dz in range(-HYDRATION_RADIUS, HYDRATION_RADIUS + 1):
                for farmland_y in (wy, wy - 1):
                    pos = (wx_ + dx, farmland_y, wz + dz)
                    if pos in farmland_positions:
                        covered.add(pos)
        return covered

    def _detect_existing_hydration(
        self,
        farmland_positions: Set[Position],
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
        counters: Dict[str, int],
    ) -> Tuple[Set[Position], Set[Position]]:
        """Find existing water and the farmland it already hydrates."""
        hydrated: Set[Position] = set()
        water_positions: Set[Position] = set()
        water_lookup: Dict[Position, bool] = {}

        for farmland_pos in farmland_positions:
            fx, fy, fz = farmland_pos
            if farmland_pos in hydrated:
                continue
            found_for_this = False
            for dx in range(-HYDRATION_RADIUS, HYDRATION_RADIUS + 1):
                if found_for_this:
                    break
                for dz in range(-HYDRATION_RADIUS, HYDRATION_RADIUS + 1):
                    if found_for_this:
                        break
                    for water_y in (fy, fy + 1):
                        water_pos = (fx + dx, water_y, fz + dz)
                        contains_water = water_lookup.get(water_pos)
                        if contains_water is None:
                            block, _entity, available = self._read_block_cached(
                                water_pos,
                                dim,
                                plat,
                                ver,
                                cache,
                                missing_chunks,
                            )
                            contains_water = bool(available and self._block_contains_water(block))
                            water_lookup[water_pos] = contains_water
                        if contains_water:
                            water_positions.add(water_pos)
                            hydrated.update(
                                self._positions_hydrated_by_water(
                                    water_pos,
                                    farmland_positions,
                                )
                            )
                            found_for_this = True
                            break

        counters["existing_water_sources_found"] = len(water_positions)
        counters["farmland_hydrated_by_existing_water"] = len(hydrated)
        return hydrated, water_positions

    def _water_position_surrounded(
        self,
        water_pos: Position,
        replace_mode: bool,
        planned_farmland: Set[Position],
        candidate_by_farmland: Mapping[Position, SurfaceCandidate],
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
    ) -> bool:
        """Validate the conservative surroundings rule for new water."""
        x, y, z = water_pos
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx == 0 and dz == 0:
                    continue
                neighbor = (x + dx, y, z + dz)
                if neighbor in planned_farmland:
                    continue
                if not replace_mode:
                    block, entity, available = self._read_block_cached(
                        neighbor,
                        dim,
                        plat,
                        ver,
                        cache,
                        missing_chunks,
                    )
                    if not (
                        available
                        and entity is None
                        and block.base_name in FARMLAND_NAMES
                    ):
                        return False
                    continue

                # Replace mode may count existing grass or farmland without
                # converting it solely to surround the planned source.
                block, entity, available = self._read_block_cached(
                    neighbor,
                    dim,
                    plat,
                    ver,
                    cache,
                    missing_chunks,
                )
                if not (
                    available
                    and entity is None
                    and block.base_name in (GRASS_BLOCK_NAMES | FARMLAND_NAMES)
                ):
                    return False
        return True

    def _plan_new_water(
        self,
        farmland_positions: Set[Position],
        candidate_positions: Set[Position],
        reserved_fruit_positions: Set[Position],
        existing_hydrated: Set[Position],
        candidate_by_farmland: Mapping[Position, SurfaceCandidate],
        settings: Mapping[str, object],
        dim,
        plat,
        ver,
        cache: Dict[Position, ReadResult],
        missing_chunks: Set[Tuple[int, int]],
        counters: Dict[str, int],
    ) -> Set[Position]:
        """Choose safe new water sources with greedy coverage planning."""
        if not bool(settings["add_water"]):
            return set()

        replace_mode = bool(settings["replace_grass"])
        usable_candidates: List[Position] = []
        for pos in sorted(candidate_positions):
            if pos in reserved_fruit_positions:
                continue
            if pos not in candidate_by_farmland:
                continue
            if not self._water_position_surrounded(
                pos,
                replace_mode,
                farmland_positions,
                candidate_by_farmland,
                dim,
                plat,
                ver,
                cache,
                missing_chunks,
            ):
                counters["water_surrounding_rule_skips"] += 1
                continue
            usable_candidates.append(pos)

        counters["safe_water_candidates"] = len(usable_candidates)
        uncovered = set(farmland_positions) - set(existing_hydrated)
        if not uncovered or not usable_candidates:
            return set()

        # Coverage is computed lazily. Retaining an 80-position set for every
        # possible source would use excessive memory on large fields; only the
        # small number of sources actually selected keep their coverage sets.
        selected_coverage: Dict[Position, Set[Position]] = {}
        heap: List[Tuple[int, int, int, int, int, Position]] = []

        xs = [pos[0] for pos in farmland_positions]
        zs = [pos[2] for pos in farmland_positions]
        min_x = min(xs) if xs else 0
        min_z = min(zs) if zs else 0

        for pos in usable_candidates:
            coverage = self._positions_hydrated_by_water(pos, farmland_positions)
            coverage.discard(pos)
            score = len(coverage & uncovered)
            if score <= 0:
                continue
            x, y, z = pos
            # A 9x9 hydration tile is centered four blocks from its edge.
            # Prefer that repeating phase when equal-coverage candidates tie;
            # this avoids a center-first choice turning an 18x9 rectangle into
            # three sources when two perfectly tiled sources are sufficient.
            grid_phase_penalty = (
                abs(((x - min_x) % 9) - 4)
                + abs(((z - min_z) % 9) - 4)
            )
            heapq.heappush(
                heap,
                (-score, grid_phase_penalty, x, z, y, pos),
            )

        selected: Set[Position] = set()
        while uncovered and heap:
            neg_score, grid_phase_penalty, x, z, y, pos = heapq.heappop(heap)
            current_coverage = self._positions_hydrated_by_water(
                pos,
                farmland_positions,
            )
            current_coverage.discard(pos)
            current_score = len(current_coverage & uncovered)
            if current_score <= 0:
                continue
            if current_score != -neg_score:
                heapq.heappush(
                    heap,
                    (-current_score, grid_phase_penalty, x, z, y, pos),
                )
                continue

            selected.add(pos)
            selected_coverage[pos] = current_coverage
            uncovered.discard(pos)
            uncovered.difference_update(current_coverage)

        # Remove redundant planned sources when all final farmland remains
        # covered by existing water or another planned source.
        coverage_count: Dict[Position, int] = {
            pos: (1 if pos in existing_hydrated else 0)
            for pos in farmland_positions
        }
        for water_pos in selected:
            for farmland_pos in selected_coverage[water_pos]:
                coverage_count[farmland_pos] = coverage_count.get(farmland_pos, 0) + 1

        for water_pos in sorted(selected, reverse=True):
            affected = selected_coverage[water_pos]
            affected_remains_covered = bool(affected) and all(
                coverage_count.get(pos, 0) > 1 for pos in affected
            )
            # When the source replaced a planned farmland block, removing the
            # source restores that farmland. It must already be covered by an
            # existing or different planned source before this source is removed.
            restored_position_covered = (
                water_pos not in farmland_positions
                or coverage_count.get(water_pos, 0) > 0
            )
            if affected_remains_covered and restored_position_covered:
                selected.remove(water_pos)
                for farmland_pos in affected:
                    coverage_count[farmland_pos] -= 1
                counters["redundant_water_sources_removed"] += 1

        counters["new_water_sources_planned"] = len(selected)
        return selected

    # -----------------------------------------------------------------
    # Complete plan assembly
    # -----------------------------------------------------------------

    def _build_plan(
        self,
        boxes: Sequence[BoxTuple],
        settings: Mapping[str, object],
        dim,
        plat,
        ver,
    ) -> FarmPlan:
        """Assemble the complete farm plan without writing to the world."""
        cache: Dict[Position, ReadResult] = {}
        missing_chunks: Set[Tuple[int, int]] = set()
        counters: Dict[str, int] = {
            "columns_scanned": 0,
            "eligible_candidates": 0,
            "unavailable_columns": 0,
            "protected_top_blocks": 0,
            "block_entity_supports": 0,
            "ineligible_supports": 0,
            "insufficient_selected_height": 0,
            "protected_obstruction": 0,
            "block_entity": 0,
            "outside_selection": 0,
            "connected_plant_outside_selection": 0,
            "connected_plant_unsafe": 0,
            "unavailable_chunk": 0,
            "isolated_raised_skips": 0,
            "stem_spacing_skips": 0,
            "stems_without_fruit_space": 0,
            "stems_planned": 0,
            "water_surrounding_rule_skips": 0,
            "safe_water_candidates": 0,
            "existing_water_sources_found": 0,
            "farmland_hydrated_by_existing_water": 0,
            "new_water_sources_planned": 0,
            "redundant_water_sources_removed": 0,
            "decorative_plants_planned_for_removal": 0,
            "safety_context_positions_read": 0,
        }
        warnings: List[str] = []

        candidates = self._scan_surface_candidates(
            boxes,
            settings,
            dim,
            plat,
            ver,
            cache,
            missing_chunks,
            counters,
        )
        candidates = self._remove_isolated_raised_candidates(
            candidates,
            settings,
            counters,
        )
        self._scan_read_only_safety_context(
            candidates,
            boxes,
            dim,
            plat,
            ver,
            cache,
            missing_chunks,
            counters,
        )

        (
            farmland_positions,
            crop_positions,
            reserved_fruit_positions,
            water_candidate_positions,
        ) = self._plan_crop_layout(candidates, boxes, settings, counters)
        existing_hydrated, existing_water_positions = self._detect_existing_hydration(
            farmland_positions,
            dim,
            plat,
            ver,
            cache,
            missing_chunks,
            counters,
        )

        water_positions = self._plan_new_water(
            farmland_positions,
            water_candidate_positions,
            reserved_fruit_positions,
            existing_hydrated,
            candidates,
            settings,
            dim,
            plat,
            ver,
            cache,
            missing_chunks,
            counters,
        )

        # A planned source occupies a former farmland candidate. Remove both its
        # farmland and any crop assigned directly above it.
        for water_pos in water_positions:
            farmland_positions.discard(water_pos)
            candidate = candidates.get(water_pos)
            if candidate is not None:
                crop_positions.pop(candidate.crop_pos, None)

        # Growth is assigned only after irrigation has removed any crop target
        # that became a water source. This keeps crop and growth reports exact.
        crop_growth_states = {
            crop_pos: self._growth_for_crop_position(crop_pos, settings)
            for crop_pos in crop_positions
        }

        hydrated_positions = set(existing_hydrated) & farmland_positions
        for water_pos in water_positions:
            hydrated_positions.update(
                self._positions_hydrated_by_water(
                    water_pos,
                    farmland_positions,
                )
            )

        clear_positions: Set[Position] = set()
        originals: Dict[Position, Tuple[Block, object]] = {}

        used_candidate_positions = set(farmland_positions) | set(water_positions)
        for farmland_pos in used_candidate_positions:
            candidate = candidates[farmland_pos]
            clear_positions.update(candidate.clear_positions)
            originals.update(candidate.originals)

        # Reserve fruit spaces by clearing only already-approved decorative
        # plants. Replace mode leaves their supporting grass / dirt untouched.
        for fruit_pos in reserved_fruit_positions:
            candidate = candidates.get(fruit_pos)
            if candidate is None:
                continue
            clear_positions.update(candidate.clear_positions)
            originals.update(candidate.originals)

        counters["decorative_plants_planned_for_removal"] = len(clear_positions)
        counters["missing_chunks"] = len(missing_chunks)
        counters["farmland_planned"] = len(farmland_positions)
        counters["crops_planned"] = len(crop_positions)
        counters["unhydrated_farmland"] = len(farmland_positions - hydrated_positions)

        if bool(settings["add_water"]) and counters["unhydrated_farmland"]:
            warnings.append(
                f"{counters['unhydrated_farmland']:,} farmland position(s) could not "
                "be hydrated by existing water or a safe new source."
            )
        if missing_chunks:
            warnings.append(
                f"{len(missing_chunks):,} unavailable chunk(s) were treated as unsafe and skipped."
            )
        if str(settings["crop_layout"]) in STEM_CROPS and not crop_positions:
            warnings.append(
                "No melon or pumpkin stem had a valid selected fruit lane after safety checks."
            )
        if (
            bool(settings["add_water"])
            and not water_positions
            and farmland_positions - existing_hydrated
        ):
            warnings.append(
                "No safe new water position satisfied the surrounding-ground rule."
            )
        if (
            bool(settings["add_water"])
            and str(settings["moisture"]) == "Force fully hydrated"
            and farmland_positions - hydrated_positions
        ):
            warnings.append(
                "Forced moisture writes wet farmland even where no lasting water coverage exists."
            )

        return FarmPlan(
            selection_boxes=tuple(boxes),
            candidate_by_farmland=candidates,
            farmland_positions=farmland_positions,
            crop_positions=crop_positions,
            crop_growth_states=crop_growth_states,
            water_positions=water_positions,
            existing_water_positions=existing_water_positions,
            hydrated_positions=hydrated_positions,
            reserved_fruit_positions=reserved_fruit_positions,
            clear_positions=clear_positions,
            originals=originals,
            counters=counters,
            warnings=warnings,
            settings=dict(settings),
        )

    # -----------------------------------------------------------------
    # Plan validation and writing
    # -----------------------------------------------------------------

    def _moisture_for_position(self, pos: Position, plan: FarmPlan) -> int:
        """Resolve the initial farmland moisture for one position."""
        if not bool(plan.settings["add_water"]):
            return 0
        mode = str(plan.settings["moisture"])
        if mode == "Force dry":
            return 0
        if mode == "Force fully hydrated":
            return 7
        return 7 if pos in plan.hydrated_positions else 0

    def _build_write_maps(
        self,
        plan: FarmPlan,
    ) -> Tuple[Dict[Position, Block], Dict[Position, Tuple[Block, object]]]:
        """Build final block writes and their expected original states."""
        writes: Dict[Position, Block] = {}
        expected: Dict[Position, Tuple[Block, object]] = dict(plan.originals)
        air = Block("minecraft", "air")

        for pos in plan.clear_positions:
            writes[pos] = air

        for farmland_pos in plan.farmland_positions:
            writes[farmland_pos] = self._farmland_block(
                self._moisture_for_position(farmland_pos, plan)
            )
            candidate = plan.candidate_by_farmland[farmland_pos]
            expected.update(candidate.originals)

        for crop_pos, crop in plan.crop_positions.items():
            growth = int(plan.crop_growth_states[crop_pos])
            writes[crop_pos] = self._crop_block(crop, growth)
            farmland_pos = (crop_pos[0], crop_pos[1] - 1, crop_pos[2])
            candidate = plan.candidate_by_farmland.get(farmland_pos)
            if candidate is not None:
                expected.update(candidate.originals)

        water_block = self._planned_water_block(
            str(plan.settings["water_cover"]),
            str(plan.settings["slab_type"]),
        )
        for water_pos in plan.water_positions:
            writes[water_pos] = water_block
            candidate = plan.candidate_by_farmland[water_pos]
            expected.update(candidate.originals)

        # A final target write supersedes an intermediate air clear at the same
        # coordinate. Connected partner positions remain explicit air writes.
        return writes, expected

    def _validate_plan_unchanged(
        self,
        expected: Mapping[Position, Tuple[Block, object]],
        dim,
        plat,
        ver,
    ) -> Tuple[bool, Optional[Position], str]:
        """Confirm planned source blocks still match before writing."""
        for pos, (expected_block, expected_entity) in expected.items():
            x, y, z = pos
            cx, cz = block_coords_to_chunk_coords(x, z)
            try:
                if not self.world.has_chunk(cx, cz, dim):
                    return False, pos, "chunk became unavailable"
                current_block, current_entity = self.world.get_version_block(
                    x,
                    y,
                    z,
                    dim,
                    (plat, ver),
                )
            except Exception as exc:
                return False, pos, str(exc)

            if current_block != expected_block:
                return False, pos, "block changed after planning"
            if (current_entity is None) != (expected_entity is None):
                return False, pos, "block-entity state changed after planning"

        return True, None, ""

    def _apply_plan(
        self,
        plan: FarmPlan,
        dim,
        plat,
        ver,
    ) -> Tuple[int, int]:
        """Validate and apply the complete plan in deterministic order."""
        writes, expected = self._build_write_maps(plan)
        valid, changed_pos, reason = self._validate_plan_unchanged(
            expected,
            dim,
            plat,
            ver,
        )
        if not valid:
            raise RuntimeError(
                "The world changed after planning at "
                f"{changed_pos}: {reason}. No Auto Farmland writes were started."
            )

        # Deterministic order: clear upper decoration first, write farmland and
        # water next, then crops. This avoids temporary support inconsistencies.
        crop_positions = set(plan.crop_positions)
        ground_positions = set(plan.farmland_positions) | set(plan.water_positions)

        ordered_positions = sorted(
            writes,
            key=lambda pos: (
                2 if pos in crop_positions else 1 if pos in ground_positions else 0,
                pos[1],
                pos[0],
                pos[2],
            ),
        )

        changed_chunks: Set[Tuple[int, int]] = set()
        for pos in ordered_positions:
            x, y, z = pos
            self.world.set_version_block(
                x,
                y,
                z,
                dim,
                (plat, ver),
                writes[pos],
                None,
            )
            changed_chunks.add(block_coords_to_chunk_coords(x, z))

        for cx, cz in changed_chunks:
            try:
                chunk = self.world.get_chunk(cx, cz, dim)
                chunk.changed = True
            except Exception as exc:
                if not self._is_missing_chunk_error(exc):
                    raise

        return len(writes), len(changed_chunks)

    # -----------------------------------------------------------------
    # Report output
    # -----------------------------------------------------------------

    def _report_plan(
        self,
        plan: FarmPlan,
        planning_time: float,
        write_time: float,
        writes_applied: int,
        changed_chunks: int,
    ) -> None:
        """Write the completed operation report."""
        counters = plan.counters
        settings = plan.settings
        layout = str(settings["crop_layout"])

        self._log("Auto Farmland Report")
        self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log("Mode: Create farm")

        setting_rows: List[Tuple[str, object]] = [
            (
                "Farmland placement",
                "Replace exposed grass blocks"
                if settings["replace_grass"]
                else "Raised above safe supports",
            ),
            ("Raised support", settings["raised_support"]),
            (
                "Replace decorative plants",
                "On" if settings["replace_plants"] else "Off",
            ),
            ("Crop layout", layout),
        ]

        if layout == "Single Crop":
            setting_rows.append(("Crop", settings["single_crop"]))
        elif layout in MULTI_CROP_LAYOUTS:
            setting_rows.append(
                (
                    "Selected crops",
                    ", ".join(self._selected_standard_crops(settings)),
                )
            )
        if layout == "Alternating Crop Rows" or layout in STEM_CROPS:
            row_direction = str(settings["row_direction"])
            if row_direction == "Automatic":
                x_boxes = sum(
                    1
                    for box in plan.selection_boxes
                    if self._row_axis((box,), "Automatic") == "x"
                )
                z_boxes = len(plan.selection_boxes) - x_boxes
                setting_rows.append(
                    ("Row direction", "Automatic per selection box")
                )
                setting_rows.append(
                    (
                        "Resolved row axes",
                        f"Along X: {x_boxes}; Along Z: {z_boxes}",
                    )
                )
            else:
                setting_rows.append(("Row direction", row_direction))
        if layout in STEM_CROPS:
            setting_rows.append(("Stem spacing", settings["stem_spacing"]))

        if layout != "Farmland only":
            if layout in STEM_CROPS or settings["growth_mode"] == "Fixed growth state":
                growth = int(settings["growth"])
                setting_rows.append(
                    ("Growth", f"{growth} - {GROWTH_DESCRIPTIONS[growth]}")
                )
            else:
                low, high = sorted(
                    (
                        int(settings["random_growth_min"]),
                        int(settings["random_growth_max"]),
                    )
                )
                setting_rows.append(("Growth", f"Random range {low} to {high}"))

        if layout == "Assorted Crops" or (
            layout not in STEM_CROPS
            and layout != "Farmland only"
            and settings["growth_mode"] == "Random growth range"
        ):
            setting_rows.append(("Pattern seed", settings["pattern_seed"]))

        setting_rows.extend(
            [
                ("Add water", "On" if settings["add_water"] else "Off"),
                (
                    "Initial moisture",
                    settings["moisture"] if settings["add_water"] else "Dry",
                ),
                (
                    "Water cover",
                    settings["water_cover"]
                    if settings["add_water"]
                    else "Not used",
                ),
            ]
        )
        if (
            settings["add_water"]
            and settings["water_cover"] == "Waterlogged Upper Slab"
        ):
            setting_rows.append(("Slab type", settings["slab_type"]))
        setting_rows.extend(
            [
                (
                    "Safety context border",
                    f"{SAFETY_CONTEXT_RADIUS} blocks, read only",
                ),
                (
                    "Hydration border",
                    f"{HYDRATION_RADIUS} blocks, read only",
                ),
            ]
        )
        self._log_section("Settings", setting_rows)

        self._log_section(
            "Surface scan",
            (
                ("Selection boxes", len(plan.selection_boxes)),
                ("Surface columns scanned", f"{counters['columns_scanned']:,}"),
                ("Eligible exposed candidates", f"{counters['eligible_candidates']:,}"),
                ("Ineligible supports", f"{counters['ineligible_supports']:,}"),
                ("Protected top blocks", f"{counters['protected_top_blocks']:,}"),
                ("Block-entity supports", f"{counters['block_entity_supports']:,}"),
                ("Insufficient selected height", f"{counters['insufficient_selected_height']:,}"),
                ("Protected obstructions", f"{counters['protected_obstruction']:,}"),
                ("Isolated raised positions skipped", f"{counters['isolated_raised_skips']:,}"),
                ("Read-only safety-context positions", f"{counters['safety_context_positions_read']:,}"),
                ("Unavailable chunks", f"{counters['missing_chunks']:,}"),
            ),
        )

        if layout in STEM_CROPS:
            self._log_section(
                "Stem layout",
                (
                    ("Stems planned", f"{counters['stems_planned']:,}"),
                    ("Spacing exclusions", f"{counters['stem_spacing_skips']:,}"),
                    ("Stems without selected fruit space", f"{counters['stems_without_fruit_space']:,}"),
                    ("Reserved fruit positions", f"{len(plan.reserved_fruit_positions):,}"),
                ),
            )

        if plan.crop_positions:
            crop_counts = Counter(plan.crop_positions.values())
            crop_rows: List[Tuple[str, object]] = [
                (crop, f"{crop_counts.get(crop, 0):,}")
                for crop in (*STANDARD_CROPS, "Melon Stem", "Pumpkin Stem")
                if crop_counts.get(crop, 0)
            ]
            crop_rows.append(("Total crops", f"{len(plan.crop_positions):,}"))
            self._log_section("Crop placement", crop_rows)

            growth_counts = Counter(plan.crop_growth_states.values())
            if len(growth_counts) > 1 or (
                layout not in STEM_CROPS
                and settings["growth_mode"] == "Random growth range"
            ):
                self._log_section(
                    "Growth distribution",
                    [
                        (
                            f"State {state} - {GROWTH_DESCRIPTIONS[state]}",
                            f"{growth_counts.get(state, 0):,}",
                        )
                        for state in range(8)
                        if growth_counts.get(state, 0)
                    ],
                )

        self._log_section(
            "Irrigation",
            (
                ("Existing water sources used", f"{len(plan.existing_water_positions):,}"),
                ("Farmland hydrated by existing water", f"{counters['farmland_hydrated_by_existing_water']:,}"),
                ("Safe new-water candidates", f"{counters['safe_water_candidates']:,}"),
                ("Surrounding-rule exclusions", f"{counters['water_surrounding_rule_skips']:,}"),
                ("New water sources planned", f"{len(plan.water_positions):,}"),
                ("Redundant sources removed", f"{counters['redundant_water_sources_removed']:,}"),
                ("Final hydrated farmland", f"{len(plan.hydrated_positions):,}"),
                ("Final unhydrated farmland", f"{counters['unhydrated_farmland']:,}"),
            ),
        )

        self._log_section(
            "Final plan",
            (
                ("Farmland blocks", f"{len(plan.farmland_positions):,}"),
                ("Crop blocks", f"{len(plan.crop_positions):,}"),
                ("New water blocks", f"{len(plan.water_positions):,}"),
                ("Decorative plant positions cleared", f"{len(plan.clear_positions):,}"),
                ("Planned target writes", f"{writes_applied:,}"),
            ),
        )

        self._log_section(
            "Applied changes",
            (
                ("World positions written", f"{writes_applied:,}"),
                ("Changed chunks", f"{changed_chunks:,}"),
            ),
        )

        self._log_section(
            "Performance",
            (
                ("Planning time", self._format_seconds(planning_time)),
                ("Write time", self._format_seconds(write_time)),
                ("Total time", self._format_seconds(planning_time + write_time)),
            ),
        )

        if plan.warnings:
            self._log("")
            self._log("Warnings")
            for warning in plan.warnings:
                self._log(f"• {warning}")

        self._log("")
        self._log(
            f"Outcome: applied {writes_applied:,} planned world change(s) successfully."
        )

    # -----------------------------------------------------------------
    # Main operation
    # -----------------------------------------------------------------

    def _snapshot_ui_settings(self) -> Dict[str, object]:
        """Capture every operation setting before the worker starts."""
        selected = {crop: control.GetValue() for crop, control in self._selected_crop_controls()}
        return {
            "replace_grass": bool(self.replace_grass_cb.GetValue()),
            "raised_support": self.raised_support_choice.GetStringSelection(),
            "replace_plants": bool(self.replace_plants_cb.GetValue()),
            "skip_isolated_raised": bool(self.skip_isolated_raised_cb.GetValue()),
            "crop_layout": self.crop_layout_choice.GetStringSelection(),
            "single_crop": self.single_crop_choice.GetStringSelection(),
            "crop_wheat": bool(selected["Wheat"]),
            "crop_carrots": bool(selected["Carrots"]),
            "crop_potatoes": bool(selected["Potatoes"]),
            "crop_beetroot": bool(selected["Beetroot"]),
            "growth_mode": self.growth_mode_choice.GetStringSelection(),
            "growth": int(self.growth_slider.GetValue()),
            "random_growth_min": int(self.random_growth_min_slider.GetValue()),
            "random_growth_max": int(self.random_growth_max_slider.GetValue()),
            "row_direction": self.row_direction_choice.GetStringSelection(),
            "stem_spacing": int(self.stem_spacing_slider.GetValue()),
            "pattern_seed": int(self.pattern_seed_slider.GetValue()),
            "add_water": bool(self.add_water_cb.GetValue()),
            "moisture": self.moisture_choice.GetStringSelection(),
            "water_cover": self.water_cover_choice.GetStringSelection(),
            "slab_type": self.slab_type_choice.GetStringSelection(),
        }

    def _validate_operation_settings(
        self,
        settings: Mapping[str, object],
    ) -> Optional[str]:
        """Return a user-facing validation error, if any."""
        layout = str(settings["crop_layout"])
        if layout in MULTI_CROP_LAYOUTS:
            selected = self._selected_standard_crops(settings)
            if len(selected) < 2:
                return (
                    f"{layout} requires at least two selected standard crops."
                )
        if (
            settings["add_water"]
            and settings["water_cover"] == "Waterlogged Upper Slab"
            and settings["slab_type"] not in SLAB_BLOCK_NAMES
        ):
            return "The selected slab type is not supported."
        return None

    def _run_operation(self, _event) -> None:
        """Capture selection state and run one undoable Amulet operation."""
        self._clear_log()

        selection_group = self.canvas.selection.selection_group
        if not selection_group:
            self._log("Auto Farmland Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log("Operation not started: no selection was found.")
            self._finalize_report()
            wx.MessageBox("No selection was found.", "Auto Farmland", wx.OK | wx.ICON_ERROR, self)
            return

        boxes = tuple(
            self._normalize_box_tuple(box)
            for box in selection_group.selection_boxes
        )
        boxes = tuple(
            box
            for box in boxes
            if box[0] < box[1] and box[2] < box[3] and box[4] < box[5]
        )
        if not boxes:
            self._log("Operation not started: no valid selection boxes were found.")
            self._finalize_report()
            return

        estimated_columns = self._selection_column_estimate(boxes)
        if estimated_columns >= LARGE_COLUMN_WARNING_THRESHOLD:
            answer = wx.MessageBox(
                "Large Auto Farmland selection\n\n"
                f"Estimated selected surface columns: {estimated_columns:,}\n\n"
                "The planner stores surface candidates and hydration coverage in "
                "memory before it changes the world. Continue?",
                "Confirm Large Operation",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                self,
            )
            if answer != wx.YES:
                self._log("Operation cancelled at the large-selection warning.")
                self._finalize_report()
                return

        dim = self.canvas.dimension
        plat = self.world.level_wrapper.platform
        ver = self.world.level_wrapper.version
        settings = self._snapshot_ui_settings()
        settings_error = self._validate_operation_settings(settings)
        if settings_error:
            self._log("Auto Farmland Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log(f"Operation not started: {settings_error}")
            self._finalize_report()
            wx.MessageBox(
                settings_error,
                "Auto Farmland",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self.status.SetLabel("Planning farm...")

        def operation():
            planning_start = perf_counter()
            try:
                plan = self._build_plan(boxes, settings, dim, plat, ver)
                planning_time = perf_counter() - planning_start

                write_start = perf_counter()
                writes_applied, changed_chunks = self._apply_plan(
                    plan,
                    dim,
                    plat,
                    ver,
                )
                write_time = perf_counter() - write_start

                self._report_plan(
                    plan,
                    planning_time,
                    write_time,
                    writes_applied,
                    changed_chunks,
                )

                wx.CallAfter(
                    self.status.SetLabel,
                    f"Done: {writes_applied:,} world positions written.",
                )
            except Exception as exc:
                elapsed = perf_counter() - planning_start
                self._log("Auto Farmland Report")
                self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self._log("")
                self._log("Operation failure")
                self._log(f"Error type: {exc.__class__.__name__}")
                self._log(f"Error: {exc}")
                self._log(f"Elapsed time: {self._format_seconds(elapsed)}")
                wx.CallAfter(self.status.SetLabel, "Auto Farmland failed. Review the report.")
                raise
            finally:
                self._finalize_report()

        try:
            self.canvas.run_operation(operation)
        except Exception as exc:
            if not self._report_lines:
                self._log("Auto Farmland Report")
                self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self._log("")
                self._log(f"Operation failed to start: {exc}")
                self._finalize_report()
            raise


# Amulet discovers this plugin through the module-level export mapping.
# Keep it even though normal Python call-site analysis cannot see the reference.
export = dict(name="Auto Farmland", operation=AutoFarmland)
