from __future__ import annotations

import ast
import ctypes
import heapq
from collections import Counter
import json
import os
import re
import tempfile
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import wx

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None

from amulet.api.block import Block
from amulet_map_editor.programs.edit.api.behaviour import BlockSelectionBehaviour
from amulet_map_editor.programs.edit.api.operations import DefaultOperationUI
from amulet.utils import block_coords_to_chunk_coords
from amulet_nbt import TAG_Int, TAG_String

Position = Tuple[int, int, int]
BoxTuple = Tuple[int, int, int, int, int, int]
ReadResult = Tuple[Block, object, bool]

AIR_NAMES = {"air", "cave_air", "void_air"}
WATER_NAMES = {"water", "flowing_water"}
GRASS_BLOCK_NAMES = {"grass_block"}
FARMLAND_NAMES = {"farmland"}

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

SLAB_ICON_ITEM_IDS = {
    display_name: (
        "stone_slab" if block_name == "normal_stone_slab" else block_name
    )
    for display_name, block_name in SLAB_BLOCK_NAMES.items()
}

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

REPLACEABLE_DECORATIVE_PLANTS = {

    "short_grass",
    "tall_grass",
    "short_dry_grass",
    "tall_dry_grass",
    "fern",
    "large_fern",

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

    "sunflower",
    "lilac",
    "rose_bush",
    "peony",

    "bush",
    "firefly_bush",
    "azalea",
    "flowering_azalea",

    "crimson_fungus",
    "warped_fungus",
    "crimson_roots",
    "warped_roots",
    "nether_sprouts",

    "dead_bush",
    "brown_mushroom",
    "red_mushroom",

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

    "small_dripleaf",
    "small_dripleaf_block",
}

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

SAFETY_CONTEXT_RADIUS = 2
HYDRATION_RADIUS = 4
LARGE_COLUMN_WARNING_THRESHOLD = 500_000
PROGRESS_INTERVAL = 100_000

CUSTOM_UI_NAME_PREFIX = "AmuletUtilityCustomUI"
CUSTOM_UI_THEME_OWNED_ATTR = "_amulet_utility_theme_owned"

FLOATING_DEFAULT_SIZE = (520, 760)
FLOATING_MIN_SIZE = (440, 580)
MANAGE_DIALOG_DEFAULT_SIZE = (560, 460)
MANAGE_DIALOG_MIN_SIZE = (554, 410)

AUTO_FARMLAND_THEME = {

    "passive_window": wx.Colour(11, 29, 15),
    "passive_surface": wx.Colour(20, 40, 25),
    "passive_surface_alt": wx.Colour(20, 35, 25),
    "passive_border": wx.Colour(45, 65, 54),

    "window": wx.Colour(15, 20, 17),
    "surface": wx.Colour(23, 30, 25),
    "surface_alt": wx.Colour(21, 28, 24),
    "surface_hover": wx.Colour(32, 44, 36),
    "surface_pressed": wx.Colour(27, 78, 49),
    "border": wx.Colour(50, 85, 58),
    "border_soft": wx.Colour(43, 56, 48),
    "text": wx.Colour(232, 239, 234),
    "muted": wx.Colour(157, 174, 163),
    "accent": wx.Colour(45, 153, 86),
    "accent_hover": wx.Colour(62, 183, 105),
    "accent_pressed": wx.Colour(33, 122, 68),
    "accent_soft": wx.Colour(29, 91, 55),
    "disabled": wx.Colour(78, 91, 82),
    "console_bg": wx.Colour(5, 9, 6),
    "console_text": wx.Colour(91, 224, 125),
    "warning": wx.Colour(220, 181, 79),
}

TOOLTIP_BORDER_COLOUR = AUTO_FARMLAND_THEME["accent_hover"]
TOOLTIP_BORDER_WIDTH = 2

CHOICE_POPUP_TRANSPARENT_COLOUR = wx.Colour(1, 2, 3)

UI_CARD_MARGIN = 10
UI_CARD_PADDING = 12
UI_CONTROL_GAP = 7
UI_FOOTER_MARGIN = 12
UI_SCROLLBAR_WIDTH = 12

UI_MAIN_CONTENT_MAX_WIDTH = 588

UI_CHECKBOX_HEIGHT = 24
UI_CHECKBOX_BOX_SIZE = 18
UI_CHECKBOX_LEFT_PADDING = 2
UI_CHECKBOX_LABEL_GAP = 8
UI_CHECKBOX_RIGHT_PADDING = 12
UI_CHECKBOX_TEXT_VERTICAL_PADDING = 6

UI_CHECKBOX_GAP_REDUCTION = 5
UI_CHECKBOX_CONTROL_GAP = max(
    0,
    UI_CONTROL_GAP - UI_CHECKBOX_GAP_REDUCTION,
)
UI_CHECKBOX_CARD_GAP = max(
    0,
    UI_CARD_PADDING - UI_CHECKBOX_GAP_REDUCTION,
)

UI_CHECKBOX_GROUP_TRANSITION_GAP = max(
    0,
    UI_CHECKBOX_CARD_GAP - UI_CHECKBOX_CONTROL_GAP,
)

UI_FINAL_CHECKBOX_BOTTOM_EXTRA = 4

_CHECKBOX_SPACING_SIZERS = {}
_CHECKBOX_SPACING_BASELINES = {}
_CHECKBOX_SPACING_REFRESH_PENDING = set()
_CHECKBOX_GROUP_END_SPACERS = {}

def _register_checkbox_spacing_sizer(sizer):
    try:
        _CHECKBOX_SPACING_SIZERS[id(sizer)] = sizer
    except Exception:
        pass

def _sizer_item_window(item):
    try:
        return item.GetWindow()
    except Exception:
        return None

def _sizer_item_is_shown(item):
    window = _sizer_item_window(item)
    if window is not None:
        try:
            return bool(window.IsShown())
        except Exception:
            return True

    try:
        child_sizer = item.GetSizer()
    except Exception:
        child_sizer = None

    if child_sizer is not None:
        try:
            children = child_sizer.GetChildren()
        except Exception:
            return True

        for child in children:
            try:
                if child.IsSpacer():
                    continue
            except Exception:
                pass

            if _sizer_item_is_shown(child):
                return True

        return False

    return True

def _read_spacer_size(item):
    spacer = item.GetSpacer()
    try:
        return int(spacer.width), int(spacer.height)
    except Exception:
        return int(spacer[0]), int(spacer[1])

def _capture_checkbox_spacing_baseline(sizer):
    records = []
    item_count = int(sizer.GetItemCount())

    for index in range(item_count):
        item = sizer.GetItem(index)
        if item.IsSpacer():
            width, height = _read_spacer_size(item)
            records.append(
                {
                    "kind": "spacer",
                    "width": width,
                    "height": height,
                }
            )
        else:
            records.append(
                {
                    "kind": "item",
                    "flags": int(item.GetFlag()),
                    "border": int(item.GetBorder()),
                }
            )

    baseline = {
        "count": item_count,
        "records": records,
    }
    _CHECKBOX_SPACING_BASELINES[id(sizer)] = baseline
    return baseline

def _restore_checkbox_spacing_baseline(sizer, baseline):
    for index, record in enumerate(baseline["records"]):
        item = sizer.GetItem(index)
        if record["kind"] == "spacer":
            item.SetSpacer(
                (
                    int(record["width"]),
                    int(record["height"]),
                )
            )
        else:
            item.SetFlag(int(record["flags"]))
            try:
                item.SetBorder(int(record["border"]))
            except Exception:
                pass

def _is_checkbox_marker(items, baseline, index):
    if index < 0 or index + 1 >= len(items):
        return False

    record = baseline["records"][index]
    if (
        record["kind"] != "spacer"
        or int(record["height"]) != 0
    ):
        return False

    next_window = _sizer_item_window(items[index + 1])
    return isinstance(next_window, ModernCheckBox)

def _spacer_belongs_to_hidden_checkbox(items, index):
    if index <= 0:
        return False

    previous_window = _sizer_item_window(items[index - 1])
    if not isinstance(previous_window, ModernCheckBox):
        return False

    try:
        return not bool(previous_window.IsShown())
    except Exception:
        return False

def _refresh_checkbox_spacing(sizer):
    try:
        item_count = int(sizer.GetItemCount())
    except Exception:
        return

    baseline = _CHECKBOX_SPACING_BASELINES.get(id(sizer))
    if (
        baseline is None
        or int(baseline.get("count", -1)) != item_count
    ):
        try:
            baseline = _capture_checkbox_spacing_baseline(sizer)
        except Exception:
            return

    try:
        _restore_checkbox_spacing_baseline(sizer, baseline)
    except Exception:
        return

    items = [sizer.GetItem(index) for index in range(item_count)]

    group_end_indices = _CHECKBOX_GROUP_END_SPACERS.get(id(sizer), ())
    for spacer_index, spacer_item in enumerate(items):
        if spacer_index in group_end_indices:
            continue
        try:
            is_spacer = spacer_item.IsSpacer()
        except Exception:
            is_spacer = False
        if not is_spacer or not _spacer_belongs_to_hidden_checkbox(
            items,
            spacer_index,
        ):
            continue
        record = baseline["records"][spacer_index]
        if record.get("kind") != "spacer":
            continue
        try:
            spacer_item.SetSpacer((int(record["width"]), 0))
        except Exception:
            pass

    for checkbox_index, checkbox_item in enumerate(items):
        checkbox = _sizer_item_window(checkbox_item)
        if not isinstance(checkbox, ModernCheckBox):
            continue

        try:
            if not checkbox.IsShown():
                continue
        except Exception:
            pass

        marker_index = checkbox_index - 1
        if not _is_checkbox_marker(
            items,
            baseline,
            marker_index,
        ):
            continue

        marker_item = items[marker_index]
        desired_gap = 0
        scan_index = marker_index - 1

        while scan_index >= 0:
            previous_item = items[scan_index]
            record = baseline["records"][scan_index]

            if previous_item.IsSpacer():

                if scan_index in _CHECKBOX_GROUP_END_SPACERS.get(
                    id(sizer),
                    (),
                ):
                    scan_index -= 1
                    continue

                if _is_checkbox_marker(
                    items,
                    baseline,
                    scan_index,
                ):
                    scan_index -= 1
                    continue

                if _spacer_belongs_to_hidden_checkbox(
                    items,
                    scan_index,
                ):
                    scan_index -= 1
                    continue

                original_height = max(
                    0,
                    int(record["height"]),
                )

                previous_window = (
                    _sizer_item_window(items[scan_index - 1])
                    if scan_index > 0
                    else None
                )
                if isinstance(previous_window, ModernCheckBox):

                    try:
                        previous_visible = previous_window.IsShown()
                    except Exception:
                        previous_visible = True

                    if previous_visible:
                        desired_gap = original_height
                    else:
                        scan_index -= 1
                        continue
                else:
                    desired_gap = max(
                        0,
                        original_height
                        - int(UI_CHECKBOX_GAP_REDUCTION),
                    )

                previous_item.SetSpacer(
                    (
                        int(record["width"]),
                        0,
                    )
                )
                break

            if not _sizer_item_is_shown(previous_item):
                scan_index -= 1
                continue

            original_flags = int(record["flags"])
            original_border = max(
                0,
                int(record["border"]),
            )

            if original_flags & wx.BOTTOM:
                desired_gap = max(
                    0,
                    original_border
                    - int(UI_CHECKBOX_GAP_REDUCTION),
                )
                previous_item.SetFlag(
                    original_flags & ~wx.BOTTOM
                )
            break

        marker_item.SetSpacer((0, desired_gap))

    try:
        sizer.Layout()
    except Exception:
        pass

    try:
        containing_window = sizer.GetContainingWindow()
    except Exception:
        containing_window = None

    if containing_window is not None:
        try:
            containing_window.InvalidateBestSize()
        except Exception:
            pass
        try:
            containing_window.Layout()
        except Exception:
            pass

def _schedule_checkbox_spacing_refresh(sizer=None):
    if sizer is None:
        pending_sizers = list(_CHECKBOX_SPACING_SIZERS.values())
    else:
        _register_checkbox_spacing_sizer(sizer)
        pending_sizers = [sizer]

    for pending_sizer in pending_sizers:
        key = id(pending_sizer)
        if key in _CHECKBOX_SPACING_REFRESH_PENDING:
            continue

        _CHECKBOX_SPACING_REFRESH_PENDING.add(key)

        def refresh(target=pending_sizer, target_key=key):
            _CHECKBOX_SPACING_REFRESH_PENDING.discard(
                target_key
            )
            _refresh_checkbox_spacing(target)

            if not _CHECKBOX_SPACING_REFRESH_PENDING:
                try:
                    containing_window = target.GetContainingWindow()
                except Exception:
                    containing_window = None
                if containing_window is not None:
                    try:
                        _refresh_wrapped_text_layout(containing_window)
                    except Exception:
                        pass

        try:
            wx.CallAfter(refresh)
        except Exception:
            refresh()

def _tighten_gap_before_checkbox(sizer):
    _register_checkbox_spacing_sizer(sizer)

    try:
        sizer.AddSpacer(0)
    except Exception:
        return

    _schedule_checkbox_spacing_refresh(sizer)

def _add_checkbox_group_bottom_spacing(sizer):
    _register_checkbox_spacing_sizer(sizer)
    try:
        item = sizer.AddSpacer(
            max(0, int(UI_FINAL_CHECKBOX_BOTTOM_EXTRA))
        )
        index = int(sizer.GetItemCount()) - 1
        _CHECKBOX_GROUP_END_SPACERS.setdefault(
            id(sizer),
            set(),
        ).add(index)
        return item
    except Exception:
        return None

def _set_checkbox_group_bottom_spacing_visible(item, visible):
    if item is None:
        return
    try:
        item.Show(bool(visible))
    except Exception:
        pass

def _invalidate_layout_best_size_chain(window):
    current = window
    for _depth in range(12):
        if current is None:
            break
        try:
            current.InvalidateBestSize()
        except Exception:
            pass
        try:
            current = current.GetParent()
        except Exception:
            break

def _set_window_sizer_item_visible(window, visible):
    if window is None:
        return

    show = bool(visible)
    item = None
    try:
        containing_sizer = window.GetContainingSizer()
    except Exception:
        containing_sizer = None

    if containing_sizer is not None:
        try:
            item = containing_sizer.GetItem(window)
        except Exception:
            item = None

    if item is not None:
        try:
            item.Show(show)
        except Exception:
            pass

    try:
        window.Show(show)
    except Exception:
        pass

    try:
        parent = window.GetParent()
    except Exception:
        parent = None
    _invalidate_layout_best_size_chain(parent)

def _set_sizer_item_visible(item, visible):
    if item is None:
        return
    try:
        item.Show(bool(visible))
    except Exception:
        pass

    containing_window = None
    try:
        window = item.GetWindow()
    except Exception:
        window = None
    if window is not None:
        try:
            containing_window = window.GetParent()
        except Exception:
            containing_window = None
    else:
        try:
            child_sizer = item.GetSizer()
        except Exception:
            child_sizer = None
        if child_sizer is not None:
            try:
                containing_window = child_sizer.GetContainingWindow()
            except Exception:
                containing_window = None

    _invalidate_layout_best_size_chain(containing_window)

CHOICE_POPUP_RADIUS = 12

SLAB_SELECTOR_ICON_COLUMNS = 4
SLAB_SELECTOR_VISIBLE_ROWS = 4
SLAB_SELECTOR_TILE_HEIGHT = 104
SLAB_SELECTOR_ICON_SIZE = 72
SLAB_SELECTOR_TWO_LINE_SPACING_REDUCTION = 2
SLAB_SELECTOR_ICON_OFFSET = 10
SLAB_SELECTOR_ICON_BOTTOM_PADDING = 4
SLAB_SELECTOR_MIN_WIDTH = 520
SLAB_SELECTOR_GRID_GAP = 5
SLAB_SELECTOR_POPUP_RADIUS = CHOICE_POPUP_RADIUS

CROP_VISUAL_STAGE_MAP = {
    "Wheat": (0, 1, 2, 3, 4, 5, 6, 7),
    "Carrots": (0, 0, 1, 1, 2, 2, 2, 3),
    "Potatoes": (0, 0, 1, 1, 2, 2, 2, 3),
    "Beetroot": (0, 0, 1, 1, 2, 2, 2, 3),
}

CROP_TEXTURE_PREFIX = {
    "Wheat": "wheat_stage",
    "Carrots": "carrots_stage",
    "Potatoes": "potatoes_stage",
    "Beetroot": "beetroots_stage",
}

STEM_TEXTURE_NAME = {
    "Melon Stem": "melon_stem",
    "Pumpkin Stem": "pumpkin_stem",
}

def _mark_custom_ui_owned(window, semantic_name=None):
    try:
        setattr(window, CUSTOM_UI_THEME_OWNED_ATTR, True)
    except Exception:
        pass
    try:
        name = semantic_name or f"{CUSTOM_UI_NAME_PREFIX}:Control"
        window.SetName(name)
    except Exception:
        pass
    return window

def _try_apply_dark_native_theme(window):
    if os.name != "nt":
        return False
    try:
        handle = int(window.GetHandle())
        if not handle:
            return False
        set_window_theme = ctypes.windll.uxtheme.SetWindowTheme
        set_window_theme.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
        set_window_theme.restype = ctypes.c_int
        result = set_window_theme(
            ctypes.c_void_p(handle),
            "DarkMode_Explorer",
            None,
        )
        if result == 0:
            try:
                window.Refresh(True)
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False

def _dip(window, value):
    try:
        return int(window.FromDIP(value))
    except Exception:
        return int(value)

def _parent_background(window):
    try:
        parent = window.GetParent()
        color = parent.GetBackgroundColour() if parent is not None else None
        if color is not None and color.IsOk():
            return color
    except Exception:
        pass
    return AUTO_FARMLAND_THEME["window"]

def _graphics_text_size(graphics_context, text):
    try:
        extent = graphics_context.GetTextExtent(str(text))
        return float(extent[0]), float(extent[1])
    except Exception:
        return 0.0, 0.0

def _emit_command_event(window, event_binder):
    try:
        event = wx.CommandEvent(event_binder.typeId, window.GetId())
        event.SetEventObject(window)
        window.GetEventHandler().ProcessEvent(event)
    except Exception:
        pass

def _make_text(parent, label, point_size=None, bold=False, muted=False):
    control = wx.StaticText(parent, label=label)
    _mark_custom_ui_owned(control)
    try:
        font = control.GetFont()
        if point_size is not None:
            font.SetPointSize(point_size)
        if bold:
            font.SetWeight(wx.FONTWEIGHT_BOLD)
        control.SetFont(font)
    except Exception:
        pass
    try:
        control.SetForegroundColour(
            AUTO_FARMLAND_THEME["muted"] if muted else AUTO_FARMLAND_THEME["text"]
        )
        control.SetBackgroundColour(parent.GetBackgroundColour())
    except Exception:
        pass
    return control

def _wrap_static_text_lines(device_context, text, maximum_width):
    maximum_width = max(1, int(maximum_width))
    wrapped_lines = []

    for paragraph in str(text).splitlines() or [""]:
        words = paragraph.split()
        if not words:
            wrapped_lines.append("")
            continue

        current_line = words[0]
        for word in words[1:]:
            candidate = f"{current_line} {word}"
            try:
                candidate_width = device_context.GetTextExtent(candidate)[0]
            except Exception:
                candidate_width = maximum_width + 1

            if candidate_width <= maximum_width:
                current_line = candidate
            else:
                wrapped_lines.append(current_line)
                current_line = word

        wrapped_lines.append(current_line)

    return wrapped_lines or [""]

def _refresh_wrapped_text_layout(control_reference):
    try:
        control = control_reference()
    except Exception:
        control = control_reference

    if control is None:
        return

    try:
        parent = control.GetParent()
    except Exception:
        parent = None

    current = control
    for _depth in range(12):
        if current is None:
            break
        try:
            current.InvalidateBestSize()
        except Exception:
            pass
        try:
            current = current.GetParent()
        except Exception:
            break

    try:
        if parent is not None:
            parent.Layout()
    except Exception:
        pass

    ancestor = parent
    for _depth in range(12):
        if ancestor is None:
            break

        sync_layout = getattr(ancestor, "_modern_sync_layout", None)
        if callable(sync_layout):
            try:
                sync_layout()
            except Exception:
                pass
            break

        try:
            ancestor = ancestor.GetParent()
        except Exception:
            break

def _make_wrapped_text(
    parent,
    label,
    point_size=None,
    bold=False,
    muted=False,
):
    container = wx.Panel(
        parent,
        style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
    )
    _mark_custom_ui_owned(container)
    try:
        container.SetBackgroundColour(parent.GetBackgroundColour())
    except Exception:
        pass

    text_control = _make_text(
        container,
        label,
        point_size=point_size,
        bold=bold,
        muted=muted,
    )
    try:
        text_control.SetWindowStyleFlag(
            text_control.GetWindowStyleFlag()
            | wx.ST_NO_AUTORESIZE
        )
    except Exception:
        pass

    container_sizer = wx.BoxSizer(wx.VERTICAL)
    container_sizer.Add(text_control, 0, wx.EXPAND)
    container.SetSizer(container_sizer)

    text_state = {"source": str(label)}
    layout_state = {
        "signature": None,
        "parent_layout_pending": False,
    }

    try:
        container_reference = weakref.ref(container)
        text_reference = weakref.ref(text_control)
    except Exception:
        container_reference = lambda: container
        text_reference = lambda: text_control

    def measure_line_height(control, device_context):
        try:
            measured_height = int(
                device_context.GetTextExtent("Ag")[1]
            )
        except Exception:
            measured_height = 0
        try:
            character_height = int(control.GetCharHeight())
        except Exception:
            character_height = 0
        return max(
            _dip(control, 12),
            measured_height,
            character_height,
        )

    def queue_parent_layout():
        if layout_state["parent_layout_pending"]:
            return
        layout_state["parent_layout_pending"] = True

        def perform_parent_layout():
            layout_state["parent_layout_pending"] = False
            _refresh_wrapped_text_layout(container_reference)

        try:
            wx.CallAfter(perform_parent_layout)
        except Exception:
            perform_parent_layout()

    def apply_wrap(width=None):
        wrapped_container = container_reference()
        wrapped_control = text_reference()
        if wrapped_container is None or wrapped_control is None:
            return

        try:
            client_width = int(
                width
                if width is not None
                else wrapped_container.GetClientSize().width
            )
        except Exception:
            client_width = 0

        if client_width <= _dip(wrapped_container, 40):
            return

        available_width = max(
            _dip(wrapped_container, 80),
            client_width - _dip(wrapped_container, 2),
        )

        try:
            device_context = wx.ClientDC(wrapped_control)
            device_context.SetFont(wrapped_control.GetFont())
            lines = _wrap_static_text_lines(
                device_context,
                text_state["source"],
                available_width,
            )
            rendered_text = "\n".join(lines)
            line_height = measure_line_height(
                wrapped_control,
                device_context,
            )
            line_gap = _dip(wrapped_control, 1)
            required_height = (
                len(lines) * line_height
                + max(0, len(lines) - 1) * line_gap
                + _dip(wrapped_control, 1)
            )
        except Exception:
            return

        layout_signature = (
            available_width,
            rendered_text,
            required_height,
        )
        if layout_state["signature"] == layout_signature:
            return

        layout_state["signature"] = layout_signature

        try:
            if wrapped_control.GetLabel() != rendered_text:
                wx.StaticText.SetLabel(
                    wrapped_control,
                    rendered_text,
                )
        except Exception:
            pass

        height_changed = False

        try:
            text_minimum = wrapped_control.GetMinSize()
            if int(text_minimum.height) != required_height:
                wrapped_control.SetMinSize(
                    (-1, required_height)
                )
                height_changed = True
        except Exception:
            pass

        try:
            container_minimum = wrapped_container.GetMinSize()
            if (
                int(container_minimum.width) != 1
                or int(container_minimum.height) != required_height
            ):
                wrapped_container.SetMinSize(
                    (1, required_height)
                )
                height_changed = True
        except Exception:
            pass

        if height_changed:
            try:
                wrapped_container.Layout()
            except Exception:
                pass
            queue_parent_layout()

    def on_size(event):
        try:
            apply_wrap(event.GetSize().width)
        except Exception:
            pass
        event.Skip()

    try:
        initial_context = wx.ClientDC(text_control)
        initial_context.SetFont(text_control.GetFont())
        initial_height = measure_line_height(
            text_control,
            initial_context,
        ) + _dip(text_control, 1)
    except Exception:
        initial_height = _dip(container, 16)

    text_control.SetMinSize((-1, initial_height))
    container.SetMinSize((1, initial_height))
    container.Bind(wx.EVT_SIZE, on_size)

    container._responsive_text_state = text_state
    container._responsive_text_control = text_control
    container._responsive_layout_state = layout_state
    container._responsive_wrap_callback = apply_wrap

    try:
        wx.CallAfter(apply_wrap)
    except Exception:
        pass

    return container

def _set_wrapped_text(control, label):
    try:
        text_state = control._responsive_text_state
        layout_state = control._responsive_layout_state
        apply_wrap = control._responsive_wrap_callback
    except Exception:
        return False

    text_state["source"] = str(label)
    layout_state["signature"] = None

    try:
        apply_wrap()
        return True
    except Exception:
        return False

class AmuletCropIconCache:

    TEXTURE_LIMIT = 4 * 1024 * 1024

    def __init__(self):
        self._loaded = False
        self._resource_roots = []
        self._textures = {}
        self._bitmap_cache = {}

    @staticmethod
    def _local_app_data_root():
        value = os.environ.get("LOCALAPPDATA", "").strip()
        if value:
            return Path(value)
        return Path.home() / "AppData" / "Local"

    @classmethod
    def _java_cache_root(cls):
        return (
            cls._local_app_data_root()
            / "AmuletTeam"
            / "AmuletMapEditor"
            / "Cache"
            / "resource_packs"
            / "java"
        )

    @staticmethod
    def _safe_mtime(path):
        try:
            return float(Path(path).stat().st_mtime)
        except Exception:
            return 0.0

    def _discover_resource_roots(self):
        root = self._java_cache_root()
        try:
            children = [child for child in root.iterdir() if child.is_dir()]
        except Exception:
            children = []
        children.sort(
            key=lambda child: (
                child.name.lower() == "vanilla",
                -self._safe_mtime(child),
                child.name.lower(),
            )
        )
        roots = []
        for child in children:
            candidate = child / "assets" / "minecraft"
            if candidate.is_dir():
                roots.append(candidate)
        vanilla = root / "vanilla" / "assets" / "minecraft"
        if vanilla.is_dir() and vanilla not in roots:
            roots.append(vanilla)
        self._resource_roots = roots

    def _find_texture_path(self, texture_name):
        relative = Path("textures") / "block" / f"{texture_name}.png"
        for root in self._resource_roots:
            candidate = root / relative
            try:
                if candidate.is_file() and candidate.stat().st_size <= self.TEXTURE_LIMIT:
                    return candidate
            except Exception:
                continue
        return None

    def _load_texture(self, texture_name):
        if texture_name in self._textures:
            return self._textures[texture_name]
        if Image is None:
            self._textures[texture_name] = None
            return None
        path = self._find_texture_path(texture_name)
        if path is None:
            self._textures[texture_name] = None
            return None
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
        except Exception:
            image = None
        self._textures[texture_name] = image
        return image

    @staticmethod
    def _nearest_filter():
        try:
            return Image.Resampling.NEAREST
        except Exception:
            return Image.NEAREST

    @staticmethod
    def _pil_to_bitmap(image):
        image = image.convert("RGBA")
        width, height = image.size
        raw = image.tobytes()
        try:
            return wx.Bitmap.FromBufferRGBA(width, height, raw)
        except Exception:
            wx_image = wx.Image(width, height)
            wx_image.SetData(image.convert("RGB").tobytes())
            wx_image.SetAlpha(image.getchannel("A").tobytes())
            return wx.Bitmap(wx_image)

    @staticmethod
    def _stem_tint(state):
        state = max(0, min(7, int(state)))
        return (
            min(255, state * 32),
            max(0, 255 - state * 8),
            min(255, state * 4),
        )

    @classmethod
    def _tint_stem(cls, image, state):
        image = image.convert("RGBA")
        red_tint, green_tint, blue_tint = cls._stem_tint(state)
        pixels = []
        for red, green, blue, alpha in image.getdata():
            if alpha <= 0:
                pixels.append((0, 0, 0, 0))
                continue
            intensity = (red + green + blue) / (3.0 * 255.0)
            pixels.append(
                (
                    int(round(red_tint * intensity)),
                    int(round(green_tint * intensity)),
                    int(round(blue_tint * intensity)),
                    alpha,
                )
            )
        tinted = Image.new("RGBA", image.size, (0, 0, 0, 0))
        tinted.putdata(pixels)
        return tinted

    def _source_sprite(self, crop, state):
        state = max(0, min(7, int(state)))
        if crop in CROP_TEXTURE_PREFIX:
            visual_stage = CROP_VISUAL_STAGE_MAP[crop][state]
            return self._load_texture(
                f"{CROP_TEXTURE_PREFIX[crop]}{visual_stage}"
            )
        texture_name = STEM_TEXTURE_NAME.get(crop)
        if not texture_name:
            return None
        source = self._load_texture(texture_name)
        if source is None:
            return None

        height = max(2, min(16, (state + 1) * 2))
        source = self._tint_stem(source, state)
        segment = source.crop((0, 0, source.width, min(height, source.height)))
        canvas = Image.new("RGBA", source.size, (0, 0, 0, 0))
        canvas.alpha_composite(segment, (0, source.height - segment.height))
        return canvas

    def ensure_loaded(self):
        if self._loaded:
            return self.available_count() > 0
        self._loaded = True
        if Image is None:
            return False
        self._discover_resource_roots()

        for crop in (*STANDARD_CROPS, "Melon Stem", "Pumpkin Stem"):
            self._source_sprite(crop, 0)
        return self.available_count() > 0

    def available_count(self):
        if not self._loaded:
            self.ensure_loaded()
        count = 0
        for crop in (*STANDARD_CROPS, "Melon Stem", "Pumpkin Stem"):
            if self._source_sprite(crop, 0) is not None:
                count += 1
        return count

    def get_bitmap(self, crop, state, size):
        self.ensure_loaded()
        try:
            state = max(0, min(7, int(state)))
            size = max(12, int(size))
        except Exception:
            return wx.NullBitmap
        key = (str(crop), state, size)
        if key in self._bitmap_cache:
            return self._bitmap_cache[key]
        source = self._source_sprite(str(crop), state)
        if source is None:
            return wx.NullBitmap

        padding = max(2, int(round(size * 0.07)))
        available = max(1, size - padding * 2)
        rendered = source.resize((available, available), self._nearest_filter())
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(rendered, (padding, padding))
        try:
            bitmap = self._pil_to_bitmap(canvas)
        except Exception:
            bitmap = wx.NullBitmap
        self._bitmap_cache[key] = bitmap
        return bitmap

class AmuletSlabIconCache:

    MODEL_JSON_LIMIT = 2 * 1024 * 1024
    TEXTURE_LIMIT = 4 * 1024 * 1024

    BASE_ICON_SIZE = 96

    def __init__(self):
        self._loaded = False
        self._resource_roots = []
        self._base_icons = {}
        self._bitmap_cache = {}
        self._compact_bitmap_cache = {}

    @staticmethod
    def _local_app_data_root():
        value = os.environ.get("LOCALAPPDATA", "").strip()
        if value:
            return Path(value)
        return Path.home() / "AppData" / "Local"

    @classmethod
    def _java_cache_root(cls):
        return (
            cls._local_app_data_root()
            / "AmuletTeam"
            / "AmuletMapEditor"
            / "Cache"
            / "resource_packs"
            / "java"
        )

    @staticmethod
    def _safe_mtime(path):
        try:
            return float(Path(path).stat().st_mtime)
        except Exception:
            return 0.0

    @staticmethod
    def _safe_json(path, size_limit):
        try:
            path = Path(path)
            if not path.is_file() or path.stat().st_size > int(size_limit):
                return None
            with path.open("r", encoding="utf-8-sig") as handle:
                return json.load(handle)
        except Exception:
            return None

    def _discover_resource_roots(self):
        root = self._java_cache_root()
        try:
            children = [child for child in root.iterdir() if child.is_dir()]
        except Exception:
            children = []
        children.sort(
            key=lambda child: (
                child.name.lower() == "vanilla",
                -self._safe_mtime(child),
                child.name.lower(),
            )
        )
        roots = []
        for child in children:
            candidate = child / "assets" / "minecraft"
            if candidate.is_dir():
                roots.append(candidate)
        vanilla = root / "vanilla" / "assets" / "minecraft"
        if vanilla.is_dir() and vanilla not in roots:
            roots.append(vanilla)
        self._resource_roots = roots

    def _find_resource_file(self, relative_path):
        relative_path = Path(relative_path)
        for root in self._resource_roots:
            candidate = root / relative_path
            try:
                if candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    @staticmethod
    def _model_relative_path(model_reference):
        reference = str(model_reference or "").strip()
        if not reference:
            return None
        if ":" in reference:
            _namespace, reference = reference.split(":", 1)
        reference = reference.strip("/").replace("\\", "/")
        return Path("models") / f"{reference}.json"

    @staticmethod
    def _texture_relative_path(texture_reference):
        reference = str(texture_reference or "").strip()
        if not reference:
            return None
        if ":" in reference:
            _namespace, reference = reference.split(":", 1)
        reference = reference.strip("/").replace("\\", "/")
        return Path("textures") / f"{reference}.png"

    def _resolve_item_textures(self, item_id):
        item_path = self._find_resource_file(Path("items") / f"{item_id}.json")
        item_data = self._safe_json(item_path, self.MODEL_JSON_LIMIT) if item_path else None
        if not isinstance(item_data, dict):
            return None

        model_entry = item_data.get("model")
        if isinstance(model_entry, dict):
            model_reference = model_entry.get("model")
        elif isinstance(model_entry, str):
            model_reference = model_entry
        else:
            model_reference = None
        if not isinstance(model_reference, str) or not model_reference:
            return None

        chain = []
        current = model_reference
        visited = set()
        for _ in range(16):
            marker = str(current).lower()
            if marker in visited:
                break
            visited.add(marker)
            relative = self._model_relative_path(current)
            model_path = self._find_resource_file(relative) if relative else None
            model_data = self._safe_json(model_path, self.MODEL_JSON_LIMIT) if model_path else None
            if not isinstance(model_data, dict):
                break
            chain.append(model_data)
            parent = model_data.get("parent")
            if not isinstance(parent, str) or not parent:
                break
            current = parent

        if not chain:
            return None

        textures = {}
        for model_data in reversed(chain):
            model_textures = model_data.get("textures", {})
            if isinstance(model_textures, dict):
                textures.update(model_textures)

        def resolve_reference(value):
            for _ in range(12):
                if not isinstance(value, str) or not value:
                    return None
                if not value.startswith("#"):
                    return value
                value = textures.get(value[1:])
            return None

        top = resolve_reference(
            textures.get("top") or textures.get("all") or textures.get("side")
        )
        side = resolve_reference(
            textures.get("side") or textures.get("all") or textures.get("top")
        )
        if not top or not side:
            return None
        return top, side

    def _load_texture(self, texture_reference):
        relative = self._texture_relative_path(texture_reference)
        path = self._find_resource_file(relative) if relative else None
        if path is None:
            return None
        try:
            if path.stat().st_size > self.TEXTURE_LIMIT:
                return None
            with Image.open(path) as source:
                return source.convert("RGBA")
        except Exception:
            return None

    @staticmethod
    def _nearest_filter():
        try:
            return Image.Resampling.NEAREST
        except Exception:
            return Image.NEAREST

    @staticmethod
    def _smooth_filter():
        try:
            return Image.Resampling.LANCZOS
        except Exception:
            return Image.LANCZOS

    @staticmethod
    def _first_animation_frame(texture):
        texture = texture.convert("RGBA")
        width, height = texture.size
        if width > 0 and height > width and height % width == 0:
            return texture.crop((0, 0, width, width))
        if height > 0 and width > height and width % height == 0:
            return texture.crop((0, 0, height, height))
        return texture

    @staticmethod
    def _shade_pixel(pixel, factor):
        red, green, blue, alpha = pixel
        return (
            max(0, min(255, int(round(red * factor)))),
            max(0, min(255, int(round(green * factor)))),
            max(0, min(255, int(round(blue * factor)))),
            alpha,
        )

    @classmethod
    def _render_slab_icon(cls, top_texture, side_texture):
        render_size = cls.BASE_ICON_SIZE * 4
        geometry_scale = render_size / 128.0
        top = cls._first_animation_frame(top_texture).resize(
            (16, 16), cls._nearest_filter()
        )
        side = cls._first_animation_frame(side_texture).resize(
            (16, 16), cls._nearest_filter()
        )

        side = side.crop((0, 8, 16, 16))

        canvas = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas, "RGBA")
        center_x = render_size / 2.0
        top_y = 28.0 * geometry_scale
        face_width = 76.0 * geometry_scale
        face_height = 36.0 * geometry_scale
        side_height = 24.0 * geometry_scale

        def point(origin, basis_x, basis_y, u, v):
            return (
                origin[0] + basis_x[0] * u + basis_y[0] * v,
                origin[1] + basis_x[1] * u + basis_y[1] * v,
            )

        top_origin = (center_x, top_y)
        top_x = (face_width / 2.0, face_height / 2.0)
        top_y_basis = (-face_width / 2.0, face_height / 2.0)
        left_origin = (center_x - face_width / 2.0, top_y + face_height / 2.0)
        left_x = (face_width / 2.0, face_height / 2.0)
        left_y = (0.0, side_height)
        right_origin = (center_x + face_width / 2.0, top_y + face_height / 2.0)
        right_x = (-face_width / 2.0, face_height / 2.0)
        right_y = (0.0, side_height)

        def draw_face(texture, width, height, origin, basis_x, basis_y, shade):
            for source_y in range(height):
                for source_x in range(width):
                    pixel = texture.getpixel((source_x, source_y))
                    if pixel[3] <= 0:
                        continue
                    u0 = source_x / float(width)
                    v0 = source_y / float(height)
                    u1 = (source_x + 1) / float(width)
                    v1 = (source_y + 1) / float(height)
                    polygon = [
                        point(origin, basis_x, basis_y, u0, v0),
                        point(origin, basis_x, basis_y, u1, v0),
                        point(origin, basis_x, basis_y, u1, v1),
                        point(origin, basis_x, basis_y, u0, v1),
                    ]
                    draw.polygon(polygon, fill=cls._shade_pixel(pixel, shade))

        draw_face(side, 16, 8, left_origin, left_x, left_y, 0.84)
        draw_face(side, 16, 8, right_origin, right_x, right_y, 0.68)
        draw_face(top, 16, 16, top_origin, top_x, top_y_basis, 1.06)
        return canvas.resize(
            (cls.BASE_ICON_SIZE, cls.BASE_ICON_SIZE), cls._smooth_filter()
        )

    @staticmethod
    def _content_bbox(image):
        try:
            return image.convert("RGBA").getchannel("A").getbbox()
        except Exception:
            return None

    @classmethod
    def _fit_icon_to_size(cls, image, size, padding=0):
        image = image.convert("RGBA")
        size = max(8, int(size))
        padding = max(0, int(padding))
        bounds = cls._content_bbox(image)
        if bounds is not None:
            image = image.crop(bounds)
        available = max(1, size - padding * 2)
        scale = min(
            available / float(max(1, image.width)),
            available / float(max(1, image.height)),
        )
        width = max(1, int(round(image.width * scale)))
        height = max(1, int(round(image.height * scale)))
        image = image.resize((width, height), cls._smooth_filter())
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(
            image, ((size - width) // 2, (size - height) // 2)
        )
        return canvas

    @staticmethod
    def _pil_to_bitmap(image):
        image = image.convert("RGBA")
        width, height = image.size
        raw = image.tobytes()
        try:
            return wx.Bitmap.FromBufferRGBA(width, height, raw)
        except Exception:
            wx_image = wx.Image(width, height)
            wx_image.SetData(image.convert("RGB").tobytes())
            wx_image.SetAlpha(image.getchannel("A").tobytes())
            return wx.Bitmap(wx_image)

    def ensure_loaded(self):
        if self._loaded:
            return bool(self._base_icons)
        self._loaded = True
        if Image is None or ImageDraw is None:
            return False
        self._discover_resource_roots()
        for display_name, item_id in SLAB_ICON_ITEM_IDS.items():
            texture_references = self._resolve_item_textures(item_id)
            if texture_references is None:
                continue
            top_reference, side_reference = texture_references
            top_texture = self._load_texture(top_reference)
            side_texture = self._load_texture(side_reference)
            if top_texture is None or side_texture is None:
                continue
            try:
                self._base_icons[display_name] = self._render_slab_icon(
                    top_texture, side_texture
                )
            except Exception:
                continue
        return bool(self._base_icons)

    def available_count(self):
        self.ensure_loaded()
        return len(self._base_icons)

    def get_bitmap(self, choice, size, padding=0):
        self.ensure_loaded()
        choice = str(choice)
        size = max(8, int(size))
        padding = max(0, int(padding))
        key = (choice, size, padding)
        if key in self._bitmap_cache:
            return self._bitmap_cache[key]
        image = self._base_icons.get(choice)
        if image is None:
            return wx.NullBitmap
        bitmap = self._pil_to_bitmap(
            self._fit_icon_to_size(image, size, padding=padding)
        )
        self._bitmap_cache[key] = bitmap
        return bitmap

    def get_compact_bitmap(self, choice, size):
        self.ensure_loaded()
        choice = str(choice)
        size = max(12, int(size))
        key = (choice, size)
        if key in self._compact_bitmap_cache:
            return self._compact_bitmap_cache[key]
        image = self._base_icons.get(choice)
        if image is None:
            return wx.NullBitmap
        bitmap = self._pil_to_bitmap(
            self._fit_icon_to_size(image, size, padding=2)
        )
        self._compact_bitmap_cache[key] = bitmap
        return bitmap

def _rounded_scanline_inset(width, height, radius, y):
    width = max(1, int(width))
    height = max(1, int(height))
    radius = max(1, min(int(radius), width // 2, height // 2))
    y = int(y)

    if y < radius:
        vertical = radius - (y + 0.5)
    elif y >= height - radius:
        vertical = (y + 0.5) - (height - radius)
    else:
        return 0

    remaining = max(0.0, float(radius * radius) - vertical * vertical)
    inset = int(max(0.0, radius - remaining ** 0.5) + 0.999)
    return min(radius, inset)

class RoundedPanel(wx.Panel):

    def __init__(
        self,
        parent,
        background=None,
        border=None,
        radius=12,
        clear_background=None,
    ):
        super().__init__(
            parent,
            style=(
                wx.BORDER_NONE
                | wx.FULL_REPAINT_ON_RESIZE
                | wx.CLIP_CHILDREN
            ),
        )
        _mark_custom_ui_owned(self)
        self._fill = background or AUTO_FARMLAND_THEME["passive_surface"]
        self._border = border or AUTO_FARMLAND_THEME["passive_border"]
        self._radius = radius

        self._clear_background = clear_background
        self.SetBackgroundColour(self._fill)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(False), event.Skip()))

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        clear_colour = self._clear_background or _parent_background(self)
        dc.SetBackground(wx.Brush(clear_colour))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return

        radius = max(1, _dip(self, self._radius))
        if self._clear_background is not None:

            width = int(size.width)
            height = int(size.height)

            dc.SetPen(wx.Pen(self._border, 1))
            dc.SetBrush(wx.Brush(self._border))
            for y in range(height):
                outer_inset = _rounded_scanline_inset(
                    width,
                    height,
                    radius,
                    y,
                )
                row_width = width - outer_inset * 2
                if row_width > 0:
                    dc.DrawRectangle(
                        outer_inset,
                        y,
                        row_width,
                        1,
                    )

            border_width = 1
            inner_x = border_width
            inner_y = border_width
            inner_width = max(1, width - border_width * 2)
            inner_height = max(1, height - border_width * 2)
            inner_radius = max(1, radius - border_width)

            dc.SetPen(wx.Pen(self._fill, 1))
            dc.SetBrush(wx.Brush(self._fill))
            for local_y in range(inner_height):
                inner_inset = _rounded_scanline_inset(
                    inner_width,
                    inner_height,
                    inner_radius,
                    local_y,
                )
                row_width = inner_width - inner_inset * 2
                if row_width > 0:
                    dc.DrawRectangle(
                        inner_x + inner_inset,
                        inner_y + local_y,
                        row_width,
                        1,
                    )
            return

        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(self._border, 1))
        gc.SetBrush(wx.Brush(self._fill))
        inset = 0.5
        gc.DrawRoundedRectangle(
            inset,
            inset,
            max(1, size.width - 1),
            max(1, size.height - 1),
            radius,
        )

class ModernButton(wx.Control):

    def __init__(
        self,
        parent,
        label,
        primary=False,
        compact=False,
        content_alignment="center",
        trailing_chevron=False,
    ):
        super().__init__(
            parent,
            style=(
                wx.BORDER_NONE
                | wx.WANTS_CHARS
                | wx.FULL_REPAINT_ON_RESIZE
            ),
        )
        _mark_custom_ui_owned(self)
        self._label = str(label)
        self._primary = bool(primary)
        self._hovered = False
        self._pressed = False

        self._busy = False

        self._available = True
        self._protect_from_external_disable = False
        self._compact = bool(compact)
        self._content_alignment = str(content_alignment)
        self._trailing_chevron = bool(trailing_chevron)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.SetMinSize((-1, _dip(self, 34 if compact else 40)))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_SET_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_KILL_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(False), event.Skip()))

    def SetLabel(self, label):
        self._label = str(label)
        self.Refresh(False)

    def GetLabel(self):
        return self._label

    def DoGetBestClientSize(self):
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(self._label)
        return wx.Size(width + _dip(self, 34), max(height + _dip(self, 16), _dip(self, 34 if self._compact else 40)))

    def ProtectFromExternalDisable(self, protect=True):
        self._protect_from_external_disable = bool(protect)
        try:
            wx.Control.Enable(self, True)
        except Exception:
            pass
        self._update_cursor()
        self.Refresh(False)

    def SetAvailable(self, available=True):
        self._available = bool(available)
        if not self._available:
            self._pressed = False
        try:
            wx.Control.Enable(self, True)
        except Exception:
            try:
                super().Enable(True)
            except Exception:
                pass
        self._update_cursor()
        self.Refresh(False)
        return self._available

    def IsAvailable(self):
        return bool(self._available)

    def Enable(self, enable=True):

        if self._protect_from_external_disable and not bool(enable):
            try:
                wx.Control.Enable(self, True)
            except Exception:
                pass
            self._update_cursor()
            self.Refresh(False)
            return True
        return self.SetAvailable(enable)

    def SetBusy(self, busy=True):
        self._busy = bool(busy)
        if not self._busy:
            self._pressed = False
        try:
            wx.Control.Enable(self, True)
        except Exception:
            pass
        self._update_cursor()
        self.Refresh(False)

    def IsBusy(self):
        return bool(self._busy)

    def _update_cursor(self):
        interactive = self._available and not self._busy
        try:
            self.SetCursor(
                wx.Cursor(wx.CURSOR_HAND if interactive else wx.CURSOR_ARROW)
            )
        except Exception:
            pass

    def _colors(self):
        enabled = self._available
        if not enabled or self._busy:
            return AUTO_FARMLAND_THEME["surface_alt"], AUTO_FARMLAND_THEME["disabled"], AUTO_FARMLAND_THEME["border_soft"]
        if self._primary:
            if self._pressed:
                fill = AUTO_FARMLAND_THEME["accent_pressed"]
            elif self._hovered:
                fill = AUTO_FARMLAND_THEME["accent_hover"]
            else:
                fill = AUTO_FARMLAND_THEME["accent"]
            return fill, AUTO_FARMLAND_THEME["text"], fill
        if self._pressed:
            fill = AUTO_FARMLAND_THEME["surface_pressed"]
        elif self._hovered:
            fill = AUTO_FARMLAND_THEME["surface_hover"]
        else:
            fill = AUTO_FARMLAND_THEME["surface_alt"]
        return fill, AUTO_FARMLAND_THEME["text"], AUTO_FARMLAND_THEME["border"]

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_parent_background(self)))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return
        fill, text_color, border = self._colors()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(0.5, 0.5, max(1, size.width - 1), max(1, size.height - 1), _dip(self, 9))
        gc.SetFont(self.GetFont(), text_color)
        text_width, text_height = _graphics_text_size(gc, self._label)
        if self._content_alignment == "left":
            text_x = _dip(self, 12)
        else:
            text_x = (size.width - text_width) / 2
        gc.DrawText(
            self._label,
            text_x,
            (size.height - text_height) / 2,
        )

        if self._trailing_chevron:
            arrow_x = size.width - _dip(self, 18)
            arrow_y = size.height / 2
            gc.SetPen(wx.Pen(text_color, 2))
            gc.StrokeLine(
                arrow_x - _dip(self, 4),
                arrow_y - _dip(self, 2),
                arrow_x,
                arrow_y + _dip(self, 2),
            )
            gc.StrokeLine(
                arrow_x,
                arrow_y + _dip(self, 2),
                arrow_x + _dip(self, 4),
                arrow_y - _dip(self, 2),
            )

        if self.HasFocus() and self._available and not self._busy:
            gc.SetPen(wx.Pen(AUTO_FARMLAND_THEME["accent_hover"], 1))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawRoundedRectangle(2.5, 2.5, max(1, size.width - 5), max(1, size.height - 5), _dip(self, 7))

    def _on_enter(self, event):
        self._hovered = True
        self.Refresh(False)
        event.Skip()

    def _on_leave(self, event):
        self._hovered = False
        if not self.HasCapture():
            self._pressed = False
        self.Refresh(False)
        event.Skip()

    def _on_left_down(self, event):
        if not self._available or self._busy:
            return
        self.SetFocus()
        self._pressed = True
        try:
            self.CaptureMouse()
        except Exception:
            pass
        self.Refresh(False)

    def _on_left_up(self, event):
        if not self._available or self._busy:
            return
        was_pressed = self._pressed
        self._pressed = False
        try:
            if self.HasCapture():
                self.ReleaseMouse()
        except Exception:
            pass
        self.Refresh(False)
        if was_pressed and self.GetClientRect().Contains(event.GetPosition()):
            _emit_command_event(self, wx.EVT_BUTTON)

    def _on_key_down(self, event):
        if self._available and not self._busy and event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            _emit_command_event(self, wx.EVT_BUTTON)
            return
        event.Skip()

class ModernCheckBox(wx.Control):

    def __init__(self, parent, label, value=False):
        super().__init__(parent, style=wx.BORDER_NONE | wx.WANTS_CHARS | wx.FULL_REPAINT_ON_RESIZE)
        _mark_custom_ui_owned(self)
        self._label = str(label)
        self._value = bool(value)
        self._hovered = False
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.SetMinSize((-1, _dip(self, UI_CHECKBOX_HEIGHT)))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_LEFT_UP, self._on_activate)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_SET_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_KILL_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(False), event.Skip()))

    def SetLabel(self, label):
        self._label = str(label)
        self.Refresh(False)

    def GetLabel(self):
        return self._label

    def GetValue(self):
        return bool(self._value)

    def SetValue(self, value):
        self._value = bool(value)
        self.Refresh(False)

    def DoGetBestClientSize(self):
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(self._label)
        width_overhead = (
            _dip(self, UI_CHECKBOX_LEFT_PADDING)
            + _dip(self, UI_CHECKBOX_BOX_SIZE)
            + _dip(self, UI_CHECKBOX_LABEL_GAP)
            + _dip(self, UI_CHECKBOX_RIGHT_PADDING)
        )
        return wx.Size(
            width + width_overhead,
            max(
                height + _dip(self, UI_CHECKBOX_TEXT_VERTICAL_PADDING),
                _dip(self, UI_CHECKBOX_HEIGHT),
            ),
        )

    def Enable(self, enable=True):
        result = super().Enable(enable)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if enable else wx.CURSOR_ARROW))
        self.Refresh(False)
        return result

    def Show(self, show=True):
        result = super().Show(show)
        _schedule_checkbox_spacing_refresh()
        return result

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_parent_background(self)))
        dc.Clear()
        size = self.GetClientSize()
        box_size = _dip(self, UI_CHECKBOX_BOX_SIZE)
        box_x = _dip(self, UI_CHECKBOX_LEFT_PADDING)
        box_y = max(0, (size.height - box_size) / 2)
        enabled = self.IsEnabled()
        fill = AUTO_FARMLAND_THEME["accent"] if self._value and enabled else AUTO_FARMLAND_THEME["surface_alt"]
        if self._hovered and enabled and not self._value:
            fill = AUTO_FARMLAND_THEME["surface_hover"]
        border = AUTO_FARMLAND_THEME["accent_hover"] if self.HasFocus() and enabled else AUTO_FARMLAND_THEME["border"]
        text_color = AUTO_FARMLAND_THEME["text"] if enabled else AUTO_FARMLAND_THEME["disabled"]
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(box_x + 0.5, box_y + 0.5, box_size - 1, box_size - 1, _dip(self, 4))
        if self._value:
            gc.SetPen(wx.Pen(AUTO_FARMLAND_THEME["text"], max(2, _dip(self, 2))))
            gc.StrokeLine(box_x + box_size * 0.25, box_y + box_size * 0.52, box_x + box_size * 0.43, box_y + box_size * 0.70)
            gc.StrokeLine(box_x + box_size * 0.43, box_y + box_size * 0.70, box_x + box_size * 0.76, box_y + box_size * 0.31)
        gc.SetFont(self.GetFont(), text_color)
        _tw, th = _graphics_text_size(gc, self._label)
        gc.DrawText(
            self._label,
            box_x
            + box_size
            + _dip(self, UI_CHECKBOX_LABEL_GAP),
            (size.height - th) / 2,
        )

    def _on_enter(self, event):
        self._hovered = True
        self.Refresh(False)
        event.Skip()

    def _on_leave(self, event):
        self._hovered = False
        self.Refresh(False)
        event.Skip()

    def _toggle(self):
        if not self.IsEnabled():
            return
        self._value = not self._value
        self.Refresh(False)
        _emit_command_event(self, wx.EVT_CHECKBOX)

    def _on_activate(self, _event):
        self.SetFocus()
        self._toggle()

    def _on_key_down(self, event):
        if event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._toggle()
            return
        event.Skip()

class ModernSlider(wx.Control):

    def __init__(self, parent, value, minValue, maxValue):
        super().__init__(parent, style=wx.BORDER_NONE | wx.WANTS_CHARS | wx.FULL_REPAINT_ON_RESIZE)
        _mark_custom_ui_owned(self)
        self._minimum = int(minValue)
        self._maximum = max(self._minimum, int(maxValue))
        self._value = max(self._minimum, min(self._maximum, int(value)))
        self._dragging = False
        self._hovered = False
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.SetMinSize((_dip(self, 180), _dip(self, 30)))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_SET_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_KILL_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(False), event.Skip()))

    def GetValue(self):
        return int(self._value)

    def SetValue(self, value):
        value = max(self._minimum, min(self._maximum, int(value)))
        if value != self._value:
            self._value = value
            self.Refresh(False)

    def GetMin(self):
        return int(self._minimum)

    def GetMax(self):
        return int(self._maximum)

    def _track_bounds(self):
        size = self.GetClientSize()
        margin = _dip(self, 10)
        return margin, max(margin + 1, size.width - margin)

    def _value_from_x(self, x):
        start, end = self._track_bounds()
        if end <= start or self._maximum <= self._minimum:
            return self._minimum
        ratio = max(0.0, min(1.0, (float(x) - start) / (end - start)))
        return int(round(self._minimum + ratio * (self._maximum - self._minimum)))

    def _set_from_x(self, x, emit=True):
        new_value = self._value_from_x(x)
        if new_value == self._value:
            return
        self._value = new_value
        self.Refresh(False)
        if emit:
            _emit_command_event(self, wx.EVT_SLIDER)

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_parent_background(self)))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return
        start, end = self._track_bounds()
        center_y = size.height / 2
        ratio = 0.0 if self._maximum == self._minimum else (self._value - self._minimum) / (self._maximum - self._minimum)
        knob_x = start + ratio * (end - start)
        track_height = _dip(self, 5)
        knob_radius = _dip(self, 7 if self._dragging or self._hovered else 6)
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(AUTO_FARMLAND_THEME["border_soft"]))
        gc.DrawRoundedRectangle(start, center_y - track_height / 2, max(1, end - start), track_height, track_height / 2)
        gc.SetBrush(wx.Brush(AUTO_FARMLAND_THEME["accent"] if self.IsEnabled() else AUTO_FARMLAND_THEME["disabled"]))
        gc.DrawRoundedRectangle(start, center_y - track_height / 2, max(1, knob_x - start), track_height, track_height / 2)
        gc.SetPen(wx.Pen(AUTO_FARMLAND_THEME["accent_hover"] if self.HasFocus() else AUTO_FARMLAND_THEME["border"], 1))
        gc.SetBrush(wx.Brush(AUTO_FARMLAND_THEME["accent_hover"] if self._hovered and self.IsEnabled() else AUTO_FARMLAND_THEME["accent"]))
        gc.DrawEllipse(knob_x - knob_radius, center_y - knob_radius, knob_radius * 2, knob_radius * 2)

    def _on_enter(self, event):
        self._hovered = True
        self.Refresh(False)
        event.Skip()

    def _on_leave(self, event):
        self._hovered = False
        if not self._dragging:
            self.Refresh(False)
        event.Skip()

    def _on_left_down(self, event):
        if not self.IsEnabled():
            return
        self.SetFocus()
        self._dragging = True
        try:
            self.CaptureMouse()
        except Exception:
            pass
        self._set_from_x(event.GetX(), emit=True)

    def _on_motion(self, event):
        if self._dragging and event.Dragging() and event.LeftIsDown():
            self._set_from_x(event.GetX(), emit=True)
        else:
            event.Skip()

    def _on_left_up(self, event):
        if not self._dragging:
            return
        self._dragging = False
        self._set_from_x(event.GetX(), emit=True)
        try:
            if self.HasCapture():
                self.ReleaseMouse()
        except Exception:
            pass
        self.Refresh(False)

    def _on_key_down(self, event):
        if not self.IsEnabled():
            event.Skip()
            return
        key = event.GetKeyCode()
        target = self._value
        if key in (wx.WXK_LEFT, wx.WXK_DOWN):
            target -= 1
        elif key in (wx.WXK_RIGHT, wx.WXK_UP):
            target += 1
        elif key == wx.WXK_HOME:
            target = self._minimum
        elif key == wx.WXK_END:
            target = self._maximum
        else:
            event.Skip()
            return
        old = self._value
        self.SetValue(target)
        if self._value != old:
            _emit_command_event(self, wx.EVT_SLIDER)

class ModernScrollViewport(wx.Panel):

    def __init__(self, parent, background=None):
        super().__init__(
            parent,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN | wx.FULL_REPAINT_ON_RESIZE,
        )
        _mark_custom_ui_owned(self)
        self._background = background or AUTO_FARMLAND_THEME["window"]
        self.SetBackgroundColour(self._background)
        try:
            self.SetDoubleBuffered(True)
        except Exception:
            pass

        self._content = wx.Panel(
            self,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(self._content)
        self._content.SetBackgroundColour(self._background)
        self._content_sizer = None
        self._offset = 0.0
        self._content_height = 1

        self.Bind(wx.EVT_SIZE, self._on_size)

    def GetContentWindow(self):
        return self._content

    def SetContentSizer(self, sizer):
        self._content_sizer = sizer
        self._content.SetSizer(sizer)
        self._modern_sync_layout()

    def _modern_sync_layout(self):
        try:
            client = self.GetClientSize()
            width = max(1, int(client.width))
            viewport_height = max(1, int(client.height))
        except Exception:
            return

        sizer = self._content_sizer
        if sizer is None:
            content_height = viewport_height
        else:
            try:

                current_height = max(1, int(self._content.GetSize().height))
                self._content.SetSize((width, current_height))
                self._content.Layout()
                minimum = sizer.CalcMin()
                content_height = max(viewport_height, int(minimum.height))
            except Exception:
                content_height = viewport_height

        self._content_height = max(1, content_height)
        try:
            self._content.SetSize((width, self._content_height))
            self._content.Layout()
        except Exception:
            pass

        maximum = max(0.0, float(self._content_height - viewport_height))
        self._offset = max(0.0, min(float(self._offset), maximum))
        try:
            self._content.SetPosition((0, -int(round(self._offset))))
        except Exception:
            pass
        try:
            self.Refresh(False)
        except Exception:
            pass

    def _modern_scroll_metrics(self):
        try:
            viewport = max(1, int(self.GetClientSize().height))
        except Exception:
            viewport = 1
        content = max(viewport, int(self._content_height))
        maximum = max(0.0, float(content - viewport))
        offset = max(0.0, min(float(self._offset), maximum))
        return offset, float(viewport), float(content), maximum, 1

    def _modern_scroll_to_pixel(self, offset, refresh=True):
        _old, _viewport, _content, maximum, _ppu = self._modern_scroll_metrics()
        offset = max(0.0, min(float(offset), maximum))
        if abs(offset - self._offset) < 0.5:
            return
        self._offset = offset
        try:

            self._content.SetPosition((0, -int(round(offset))))
        except Exception:
            return
        if refresh:
            try:
                self.Refresh(False)
            except Exception:
                pass

    def ScrollChildIntoView(self, child, margin=4):
        if child is None:
            return
        try:
            content_screen = self._content.ClientToScreen((0, 0))
            child_screen = child.ClientToScreen((0, 0))
            child_top = float(child_screen.y - content_screen.y)
            child_bottom = child_top + float(child.GetSize().height)
            viewport_height = float(max(1, self.GetClientSize().height))
            margin = float(max(0, _dip(self, margin)))
        except Exception:
            return

        offset, _viewport, _content, maximum, _ppu = self._modern_scroll_metrics()
        target = offset
        if child_top - margin < offset:
            target = child_top - margin
        elif child_bottom + margin > offset + viewport_height:
            target = child_bottom + margin - viewport_height
        self._modern_scroll_to_pixel(max(0.0, min(target, maximum)))

    def _on_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        try:
            wx.CallAfter(self._modern_sync_layout)
        except Exception:
            self._modern_sync_layout()

class ModernScrollBar(wx.Control):

    def __init__(self, parent, target, on_scrolled=None):
        super().__init__(
            parent,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE,
        )
        _mark_custom_ui_owned(self)
        self._target_ref = weakref.ref(target)
        self._on_scrolled = on_scrolled
        self._hovered = False
        self._dragging = False
        self._drag_offset = 0.0
        self._drag_mouse_y = None
        self._drag_timer = wx.Timer(self)
        self._wheel_remainder = 0.0
        self._wheel_pixels = float(_dip(target, 36))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((_dip(self, UI_SCROLLBAR_WIDTH), -1))
        self.SetMaxSize((_dip(self, UI_SCROLLBAR_WIDTH), -1))
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_TIMER, self._on_drag_timer, self._drag_timer)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)
        self.Bind(
            wx.EVT_SIZE,
            lambda event: (self.Refresh(False), event.Skip()),
        )

        self._wheel_bound_windows = weakref.WeakSet()
        self._bind_wheel_tree(target)
        target.Bind(wx.EVT_SIZE, self._on_target_size)

    def _target(self):
        try:
            return self._target_ref()
        except Exception:
            return None

    def _bind_wheel_tree(self, root):
        pending = [root]
        seen = set()
        while pending:
            window = pending.pop()
            if window is None or id(window) in seen:
                continue
            seen.add(id(window))
            try:
                already_bound = window in self._wheel_bound_windows
            except Exception:
                already_bound = True
            if not already_bound:
                try:
                    self._wheel_bound_windows.add(window)
                    window.Bind(wx.EVT_MOUSEWHEEL, self._on_target_mousewheel)
                except Exception:
                    pass
            try:
                pending.extend(window.GetChildren())
            except Exception:
                pass

    def _metrics(self):
        target = self._target()
        if target is None:
            return 0.0, 1.0, 1.0, 0.0, 1
        try:
            return target._modern_scroll_metrics()
        except Exception:
            return 0.0, 1.0, 1.0, 0.0, 1

    def _thumb_geometry(self):
        size = self.GetClientSize()
        track_top = float(_dip(self, 3))
        track_height = max(1.0, float(size.height) - track_top * 2.0)
        offset, viewport, content, maximum, _pixels_per_unit = self._metrics()
        if maximum <= 0.0 or content <= viewport:
            return track_top, track_height, track_top, track_height, maximum
        min_thumb = float(_dip(self, 30))
        thumb_height = max(min_thumb, track_height * (viewport / content))
        thumb_height = min(track_height, thumb_height)
        movable = max(1.0, track_height - thumb_height)
        thumb_top = track_top + movable * (offset / maximum)
        return track_top, track_height, thumb_top, thumb_height, maximum

    def _scroll_to_pixel(self, offset):
        target = self._target()
        if target is None:
            return
        _current, _viewport, _content, maximum, _pixels_per_unit = self._metrics()
        offset = max(0.0, min(float(offset), maximum))
        try:
            target._modern_scroll_to_pixel(
                offset,
                refresh=not self._dragging,
            )
        except Exception:
            return

        self.Refresh(False)

    def _notify_scrolled(self):
        self.Refresh(False)
        callback = self._on_scrolled
        if callback is None:
            return
        try:
            callback()
        except TypeError:
            try:
                callback(None)
            except Exception:
                pass
        except Exception:
            pass

    def sync(self):
        target = self._target()
        if target is None:
            return
        try:
            target._modern_sync_layout()
        except Exception:
            pass
        self._bind_wheel_tree(target)
        try:
            self.Refresh(False)
        except Exception:
            pass

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_parent_background(self)))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return

        track_top, track_height, thumb_top, thumb_height, maximum = (
            self._thumb_geometry()
        )
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        track_width = float(_dip(self, 5))
        track_x = (float(size.width) - track_width) / 2.0
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(AUTO_FARMLAND_THEME["surface_alt"]))
        gc.DrawRoundedRectangle(
            track_x,
            track_top,
            track_width,
            track_height,
            track_width / 2.0,
        )
        if maximum <= 0.0:
            return

        thumb_width = float(
            _dip(self, 7 if self._hovered or self._dragging else 6)
        )
        thumb_x = (float(size.width) - thumb_width) / 2.0
        thumb_color = (
            AUTO_FARMLAND_THEME["accent_hover"]
            if self._dragging
            else AUTO_FARMLAND_THEME["accent"]
            if self._hovered
            else AUTO_FARMLAND_THEME["border"]
        )
        gc.SetBrush(wx.Brush(thumb_color))
        gc.DrawRoundedRectangle(
            thumb_x,
            thumb_top,
            thumb_width,
            thumb_height,
            thumb_width / 2.0,
        )

    def _on_enter(self, event):
        self._hovered = True
        self.Refresh(False)
        event.Skip()

    def _on_leave(self, event):
        self._hovered = False
        if not self._dragging:
            self.Refresh(False)
        event.Skip()

    def _on_left_down(self, event):
        _track_top, _track_height, thumb_top, thumb_height, maximum = (
            self._thumb_geometry()
        )
        if maximum <= 0.0:
            return

        mouse_y = float(event.GetY())
        self._drag_mouse_y = mouse_y
        if thumb_top <= mouse_y <= thumb_top + thumb_height:
            self._dragging = True
            self._drag_offset = mouse_y - thumb_top
        else:
            self._dragging = True
            self._drag_offset = thumb_height / 2.0
            self._drag_to(mouse_y)

        try:
            self.CaptureMouse()
        except Exception:
            pass
        try:

            self._drag_timer.Start(8)
        except Exception:
            pass
        self.Refresh(False)

    def _drag_to(self, mouse_y):
        track_top, track_height, _thumb_top, thumb_height, maximum = (
            self._thumb_geometry()
        )
        if maximum <= 0.0:
            return
        movable = max(1.0, track_height - thumb_height)
        desired_top = max(
            track_top,
            min(float(mouse_y) - self._drag_offset, track_top + movable),
        )
        ratio = (desired_top - track_top) / movable
        self._scroll_to_pixel(ratio * maximum)

    def _on_motion(self, event):
        if self._dragging and event.Dragging() and event.LeftIsDown():
            self._drag_mouse_y = float(event.GetY())
            return
        event.Skip()

    def _on_drag_timer(self, _event):
        if not self._dragging:
            try:
                self._drag_timer.Stop()
            except Exception:
                pass
            return

        try:
            mouse_state = wx.GetMouseState()
            if not mouse_state.LeftIsDown():
                self._finish_drag()
                self._notify_scrolled()
                return
        except Exception:
            pass

        try:
            point = self.ScreenToClient(wx.GetMousePosition())
            self._drag_mouse_y = float(point.y)
        except Exception:
            pass
        if self._drag_mouse_y is not None:
            self._drag_to(self._drag_mouse_y)

    def _finish_drag(self):
        self._dragging = False
        self._drag_mouse_y = None
        try:
            self._drag_timer.Stop()
        except Exception:
            pass
        try:
            if self.HasCapture():
                self.ReleaseMouse()
        except Exception:
            pass

        target = self._target()
        if target is not None:
            try:
                target.Refresh(False)
            except Exception:
                pass
        self.Refresh(False)

    def _on_left_up(self, event):
        was_dragging = self._dragging
        if was_dragging:
            self._drag_mouse_y = float(event.GetY())
            self._drag_to(self._drag_mouse_y)
        self._finish_drag()
        if was_dragging:
            self._notify_scrolled()

    def _on_capture_lost(self, _event):
        self._finish_drag()

    def _on_target_mousewheel(self, event):
        target = self._target()
        if target is None:
            event.Skip()
            return
        try:
            rotation = float(event.GetWheelRotation())
            delta = float(event.GetWheelDelta() or 120)
            lines = max(1, int(event.GetLinesPerAction() or 3))
        except Exception:
            event.Skip()
            return

        self._wheel_remainder += rotation / delta
        whole_steps = int(self._wheel_remainder)
        if whole_steps == 0:
            return
        self._wheel_remainder -= whole_steps

        offset, _viewport, _content, maximum, _pixels_per_unit = self._metrics()
        if maximum <= 0.0:
            event.Skip()
            return
        wheel_pixels = max(float(_dip(target, 24)), self._wheel_pixels)
        self._scroll_to_pixel(
            offset - whole_steps * lines * wheel_pixels / 3.0
        )
        self._notify_scrolled()

    def _on_target_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        try:
            wx.CallAfter(self.sync)
        except Exception:
            self.sync()

class ModernChoiceOption(ModernButton):

    def __init__(self, parent, label, selected=False, row_height=34):
        super().__init__(
            parent,
            label,
            primary=False,
            compact=True,
            content_alignment="left",
        )
        self._selected = bool(selected)
        self.SetMinSize((-1, _dip(self, row_height)))

    def SetSelected(self, selected):
        self._selected = bool(selected)
        self.Refresh(False)

    def _colors(self):
        if not self.IsEnabled():
            return (
                AUTO_FARMLAND_THEME["surface_alt"],
                AUTO_FARMLAND_THEME["disabled"],
                AUTO_FARMLAND_THEME["border_soft"],
            )
        if self._pressed:
            return (
                AUTO_FARMLAND_THEME["accent_pressed"],
                AUTO_FARMLAND_THEME["text"],
                AUTO_FARMLAND_THEME["accent_pressed"],
            )
        if self._hovered:
            return (
                AUTO_FARMLAND_THEME["surface_hover"],
                AUTO_FARMLAND_THEME["text"],
                AUTO_FARMLAND_THEME["accent_hover"],
            )
        if self._selected:
            return (
                AUTO_FARMLAND_THEME["surface_pressed"],
                AUTO_FARMLAND_THEME["text"],
                AUTO_FARMLAND_THEME["accent"],
            )
        return (
            AUTO_FARMLAND_THEME["surface_alt"],
            AUTO_FARMLAND_THEME["text"],
            AUTO_FARMLAND_THEME["border_soft"],
        )

class ModernIconChoiceOption(ModernChoiceOption):

    def __init__(self, parent, label, bitmap, selected=False):
        super().__init__(
            parent,
            label,
            selected=selected,
            row_height=SLAB_SELECTOR_TILE_HEIGHT,
        )
        self._bitmap = bitmap
        try:
            font = self.GetFont()
            font.SetPointSize(max(7, font.GetPointSize() - 1))
            self.SetFont(font)
        except Exception:
            pass

    @staticmethod
    def _wrapped_lines(graphics_context, text, maximum_width):
        words = str(text).split()
        if not words:
            return [""]
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            width, _height = _graphics_text_size(graphics_context, candidate)
            if width <= maximum_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        if len(lines) <= 2:
            return lines
        second = " ".join(lines[1:])
        while second:
            candidate = second + "…"
            width, _height = _graphics_text_size(graphics_context, candidate)
            if width <= maximum_width:
                second = candidate
                break
            second = second[:-1].rstrip()
        return [lines[0], second or "…"]

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_parent_background(self)))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return
        fill, text_color, border = self._colors()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(
            0.5,
            0.5,
            max(1, size.width - 1),
            max(1, size.height - 1),
            _dip(self, 9),
        )

        bitmap = self._bitmap
        bitmap_ok = False
        try:
            bitmap_ok = bool(bitmap is not None and bitmap.IsOk())
        except Exception:
            bitmap_ok = False
        if bitmap_ok:
            bitmap_width = float(bitmap.GetWidth())
            bitmap_height = float(bitmap.GetHeight())
            icon_x = (size.width - bitmap_width) / 2.0
            centered_icon_y = (size.height - bitmap_height) / 2.0
            requested_icon_y = (
                centered_icon_y
                + _dip(self, SLAB_SELECTOR_ICON_OFFSET)
            )

            maximum_icon_y = max(
                0.0,
                float(
                    size.height
                    - bitmap_height
                    - _dip(
                        self,
                        SLAB_SELECTOR_ICON_BOTTOM_PADDING,
                    )
                ),
            )
            icon_y = min(requested_icon_y, maximum_icon_y)

            gc.DrawBitmap(
                bitmap,
                icon_x,
                icon_y,
                bitmap_width,
                bitmap_height,
            )
        else:
            placeholder = "?"
            try:
                placeholder_font = self.GetFont()
                placeholder_font.SetWeight(wx.FONTWEIGHT_BOLD)
                placeholder_font.SetPointSize(
                    max(10, placeholder_font.GetPointSize() + 3)
                )
                gc.SetFont(placeholder_font, AUTO_FARMLAND_THEME["muted"])
            except Exception:
                pass
            text_width, text_height = _graphics_text_size(gc, placeholder)
            gc.DrawText(
                placeholder,
                (size.width - text_width) / 2.0,
                (size.height - text_height) / 2.0,
            )

        gc.SetFont(self.GetFont(), text_color)
        lines = self._wrapped_lines(
            gc,
            self._label,
            max(20.0, float(size.width - _dip(self, 12))),
        )
        line_y = float(_dip(self, 6))
        shadow_color = AUTO_FARMLAND_THEME["console_bg"]
        for line in lines:
            text_width, text_height = _graphics_text_size(gc, line)
            text_x = (size.width - text_width) / 2.0

            gc.SetFont(self.GetFont(), shadow_color)
            gc.DrawText(line, text_x + 1, line_y + 1)
            gc.SetFont(self.GetFont(), text_color)
            gc.DrawText(line, text_x, line_y)

            line_y += max(
                1.0,
                text_height
                + _dip(self, 1)
                - _dip(
                    self,
                    SLAB_SELECTOR_TWO_LINE_SPACING_REDUCTION,
                ),
            )

        if self.HasFocus() and self.IsAvailable() and not self.IsBusy():
            gc.SetPen(wx.Pen(AUTO_FARMLAND_THEME["accent_hover"], 1))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawRoundedRectangle(
                2.5,
                2.5,
                max(1, size.width - 5),
                max(1, size.height - 5),
                _dip(self, 7),
            )

class ModernChoicePopup(wx.Frame):

    def __init__(self, owner):
        parent = wx.GetTopLevelParent(owner) or owner
        style = wx.FRAME_NO_TASKBAR | wx.BORDER_NONE
        try:
            style |= wx.FRAME_FLOAT_ON_PARENT
        except Exception:
            pass
        super().__init__(parent, title="", style=style)
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoFarmlandChoicePopup",
        )
        self._owner_ref = weakref.ref(owner)
        self._buttons = []
        self._dismiss_notified = True
        self._closing = False
        self._popup_radius = SLAB_SELECTOR_POPUP_RADIUS
        self._transparent_corner_colour = (
            CHOICE_POPUP_TRANSPARENT_COLOUR
        )
        self._windows_corner_transparency = False
        self.SetBackgroundColour(
            self._transparent_corner_colour
        )
        try:
            self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        except Exception:
            pass
        self._windows_corner_transparency = (
            self._configure_windows_corner_transparency()
        )

        shell = RoundedPanel(
            self,
            background=AUTO_FARMLAND_THEME["surface"],
            border=AUTO_FARMLAND_THEME["border"],
            radius=self._popup_radius,
            clear_background=self._transparent_corner_colour,
        )
        self._shell = shell

        shell_sizer = wx.BoxSizer(wx.VERTICAL)

        self._scroll = ModernScrollViewport(
            shell,
            background=AUTO_FARMLAND_THEME["surface"],
        )
        self._list_content = self._scroll.GetContentWindow()
        self._content = wx.BoxSizer(wx.VERTICAL)
        self._scroll.SetContentSizer(self._content)
        scroll_row = wx.BoxSizer(wx.HORIZONTAL)
        scroll_row.Add(self._scroll, 1, wx.EXPAND)
        self._scrollbar = ModernScrollBar(shell, self._scroll)
        scroll_row.Add(
            self._scrollbar,
            0,
            wx.EXPAND | wx.LEFT,
            _dip(shell, 4),
        )
        shell_sizer.Add(
            scroll_row,
            1,
            wx.EXPAND | wx.ALL,
            _dip(shell, 6),
        )
        shell.SetSizer(shell_sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(shell, 1, wx.EXPAND)
        self.SetSizer(outer)

        self.Bind(wx.EVT_ACTIVATE, self._on_activate)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_down)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self._scroll.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

    def _configure_windows_corner_transparency(self):
        if os.name != "nt":
            return False

        try:
            handle = int(self.GetHandle())
            if not handle:
                return False

            user32 = ctypes.windll.user32
            get_window_long = getattr(
                user32,
                "GetWindowLongPtrW",
                user32.GetWindowLongW,
            )
            set_window_long = getattr(
                user32,
                "SetWindowLongPtrW",
                user32.SetWindowLongW,
            )
            try:
                get_window_long.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_int,
                ]
                get_window_long.restype = ctypes.c_ssize_t
                set_window_long.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.c_ssize_t,
                ]
                set_window_long.restype = ctypes.c_ssize_t
            except Exception:
                pass

            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            LWA_COLORKEY = 0x00000001

            hwnd = ctypes.c_void_p(handle)
            extended_style = int(
                get_window_long(hwnd, GWL_EXSTYLE)
            )
            if not extended_style & WS_EX_LAYERED:
                set_window_long(
                    hwnd,
                    GWL_EXSTYLE,
                    ctypes.c_ssize_t(
                        extended_style | WS_EX_LAYERED
                    ),
                )

                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010
                SWP_FRAMECHANGED = 0x0020
                user32.SetWindowPos(
                    hwnd,
                    None,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOSIZE
                    | SWP_NOMOVE
                    | SWP_NOZORDER
                    | SWP_NOACTIVATE
                    | SWP_FRAMECHANGED,
                )

            colour = self._transparent_corner_colour
            colour_key = (
                int(colour.Red())
                | (int(colour.Green()) << 8)
                | (int(colour.Blue()) << 16)
            )

            set_layered_attributes = (
                user32.SetLayeredWindowAttributes
            )
            set_layered_attributes.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_ubyte,
                ctypes.c_uint32,
            ]
            set_layered_attributes.restype = ctypes.c_int

            return bool(
                set_layered_attributes(
                    hwnd,
                    colour_key,
                    255,
                    LWA_COLORKEY,
                )
            )
        except Exception:
            return False

    def _refresh_rounded_window_boundary(self):
        if os.name == "nt":
            self._windows_corner_transparency = (
                self._configure_windows_corner_transparency()
            )
            if self._windows_corner_transparency:
                return True

        return _apply_rounded_window_shape(
            self,
            self._popup_radius,
        )

    def _on_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        try:
            wx.CallAfter(
                self._refresh_rounded_window_boundary
            )
        except Exception:
            self._refresh_rounded_window_boundary()

    def rebuild(self, owner, choices, selection):
        old_buttons = list(self._buttons)
        self._buttons = []
        try:
            self._content.Clear(delete_windows=False)
        except Exception:
            pass
        for button in old_buttons:
            try:
                button.Destroy()
            except Exception:
                pass

        self._icon_mode = bool(owner.UsesIconPopup())
        if self._icon_mode:
            grid = wx.GridSizer(
                rows=0,
                cols=SLAB_SELECTOR_ICON_COLUMNS,
                vgap=_dip(self._list_content, SLAB_SELECTOR_GRID_GAP),
                hgap=_dip(self._list_content, SLAB_SELECTOR_GRID_GAP),
            )
            self._content.Add(grid, 0, wx.EXPAND)
            for index, label in enumerate(choices):
                button = ModernIconChoiceOption(
                    self._list_content,
                    label,
                    owner.GetIconBitmap(label, SLAB_SELECTOR_ICON_SIZE),
                    selected=(index == selection),
                )
                button.Bind(
                    wx.EVT_BUTTON,
                    lambda _event, item_index=index: self._choose(item_index),
                )
                button.Bind(
                    wx.EVT_LEFT_DCLICK,
                    lambda _event, item_index=index: self._choose(item_index),
                )
                grid.Add(button, 1, wx.EXPAND)
                self._buttons.append(button)
        else:
            for index, label in enumerate(choices):
                button = ModernChoiceOption(
                    self._list_content,
                    label,
                    selected=(index == selection),
                    row_height=32,
                )
                button.Bind(
                    wx.EVT_BUTTON,
                    lambda _event, item_index=index: self._choose(item_index),
                )
                button.Bind(
                    wx.EVT_LEFT_DCLICK,
                    lambda _event, item_index=index: self._choose(item_index),
                )
                self._content.Add(
                    button,
                    0,
                    wx.EXPAND | wx.BOTTOM,
                    _dip(self._list_content, 2),
                )
                self._buttons.append(button)

        self._scroll._modern_sync_layout()
        try:
            self._scrollbar._bind_wheel_tree(self._scroll)
        except Exception:
            pass
        self._scrollbar.sync()
        self.Layout()

    def show_for(self, owner):
        choices = list(owner._choices)
        self.rebuild(owner, choices, owner.GetSelection())

        owner_rect = owner.GetScreenRect()
        owner_center = wx.Point(
            owner_rect.x + owner_rect.width // 2,
            owner_rect.y + owner_rect.height // 2,
        )
        display_index = wx.Display.GetFromPoint(owner_center)
        if display_index == wx.NOT_FOUND:
            display_index = wx.Display.GetFromWindow(owner)
        if display_index == wx.NOT_FOUND:
            display_index = 0
        try:
            work_area = wx.Display(display_index).GetClientArea()
        except Exception:
            work_area = wx.Rect(0, 0, *wx.GetDisplaySize())

        if self._icon_mode:
            width = max(
                owner_rect.width,
                _dip(owner, SLAB_SELECTOR_MIN_WIDTH),
            )
            rows = max(
                1,
                (
                    len(choices)
                    + SLAB_SELECTOR_ICON_COLUMNS
                    - 1
                )
                // SLAB_SELECTOR_ICON_COLUMNS,
            )
            visible_rows = min(rows, SLAB_SELECTOR_VISIBLE_ROWS)
            tile_height = _dip(owner, SLAB_SELECTOR_TILE_HEIGHT)
            grid_gap = _dip(owner, SLAB_SELECTOR_GRID_GAP)
            wanted_height = (
                visible_rows * tile_height
                + max(0, visible_rows - 1) * grid_gap
                + _dip(owner, 14)
            )
            minimum_height = _dip(owner, 180)
            maximum_height = max(_dip(owner, 220), int(work_area.height * 0.65))
        else:
            width = max(owner_rect.width, _dip(owner, 240))
            row_height = _dip(owner, 35)
            wanted_height = len(choices) * row_height + _dip(owner, 14)
            minimum_height = _dip(owner, 90)
            maximum_height = max(_dip(owner, 140), int(work_area.height * 0.55))
        edge_margin = _dip(owner, 8)
        popup_gap = _dip(owner, 4)
        work_left = work_area.x + edge_margin
        work_top = work_area.y + edge_margin
        work_right = work_area.x + work_area.width - edge_margin
        work_bottom = work_area.y + work_area.height - edge_margin
        usable_width = max(1, work_right - work_left)
        usable_height = max(1, work_bottom - work_top)

        width = min(width, usable_width)
        preferred_height = min(
            max(minimum_height, wanted_height),
            maximum_height,
            usable_height,
        )

        below_y = owner_rect.y + owner_rect.height + popup_gap
        above_bottom = owner_rect.y - popup_gap
        available_below = max(0, work_bottom - below_y)
        available_above = max(0, above_bottom - work_top)

        if available_below >= minimum_height:
            open_below = True
        elif available_above >= minimum_height:
            open_below = False
        else:
            open_below = available_below >= available_above

        available_height = available_below if open_below else available_above
        height = max(1, min(preferred_height, available_height or usable_height))

        x = owner_rect.x + int(round((owner_rect.width - width) / 2.0))
        if open_below:
            y = below_y
        else:
            y = above_bottom - height
        x = min(max(x, work_left), max(work_left, work_right - width))
        y = min(max(y, work_top), max(work_top, work_bottom - height))

        self.SetSize((width, height))
        self.SetPosition((x, y))
        self._refresh_rounded_window_boundary()
        self.Layout()
        self._scroll._modern_sync_layout()
        self._scrollbar.sync()
        self._dismiss_notified = False
        self._closing = False
        self.Show(True)
        self.Raise()
        try:
            self._shell.Refresh(False)
            self._shell.Update()
        except Exception:
            pass

        try:
            realized = self.GetScreenRect()
            realized_width = min(realized.width, usable_width)
            realized_height = min(realized.height, usable_height)
            if (
                realized_width != realized.width
                or realized_height != realized.height
            ):
                self.SetSize((realized_width, realized_height))
                realized = self.GetScreenRect()
            realized_x = min(
                max(realized.x, work_left),
                max(work_left, work_right - realized.width),
            )
            realized_y = min(
                max(realized.y, work_top),
                max(work_top, work_bottom - realized.height),
            )
            if realized_x != realized.x or realized_y != realized.y:
                self.SetPosition((realized_x, realized_y))
        except Exception:
            pass

        selection = owner.GetSelection()
        if 0 <= selection < len(self._buttons):
            try:
                self._buttons[selection].SetFocus()
                self._scroll.ScrollChildIntoView(self._buttons[selection])
            except Exception:
                pass
        else:
            try:
                self.SetFocus()
            except Exception:
                pass

    def Dismiss(self, notify_owner=True):
        if self._closing:
            return
        self._closing = True
        try:
            try:
                if self.IsShown():
                    self.Hide()
            except Exception:
                pass

            if notify_owner and not self._dismiss_notified:
                self._dismiss_notified = True
                owner = self._owner_ref()
                if owner is not None:
                    owner._on_popup_dismissed(self)
        finally:
            self._closing = False

    def _choose(self, index):
        owner = self._owner_ref()
        if owner is not None:
            owner._select_from_popup(index)
        self.Dismiss()

    def _on_activate(self, event):
        try:
            active = bool(event.GetActive())
        except Exception:
            active = True
        try:
            event.Skip()
        except Exception:
            pass
        if not active and self.IsShown():

            try:
                wx.CallAfter(self.Dismiss)
            except Exception:
                self.Dismiss()

    def _on_close(self, event):

        if not self._dismiss_notified:
            self._dismiss_notified = True
            owner = self._owner_ref()
            if owner is not None:
                owner._on_popup_dismissed(self)
        try:
            event.Skip()
        except Exception:
            pass

    def _on_key_down(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Dismiss()
            return
        event.Skip()

    def destroy_safely(self):
        try:
            self.Dismiss(notify_owner=False)
        except Exception:
            pass
        self._dismiss_notified = True
        try:
            self.Destroy()
        except Exception:
            pass

class ModernChoice(wx.Panel):

    def __init__(self, parent, choices, icon_provider=None, show_icons=False):
        super().__init__(
            parent,
            style=(
                wx.BORDER_NONE
                | wx.WANTS_CHARS
                | wx.FULL_REPAINT_ON_RESIZE
                | wx.CLIP_CHILDREN
            ),
        )
        _mark_custom_ui_owned(self)
        self._choices = [str(choice) for choice in choices]
        self._selection = 0 if self._choices else wx.NOT_FOUND
        self._hovered = False
        self._pressed = False
        self._fill = AUTO_FARMLAND_THEME["surface_alt"]
        self._radius = 9
        self._popup = None
        self._popup_open = False
        self._suppress_popup_until = 0.0
        self._icon_provider = icon_provider
        self._show_icons = bool(show_icons)

        self.SetBackgroundColour(self._fill)
        self.SetForegroundColour(AUTO_FARMLAND_THEME["text"])
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        self.SetMinSize((-1, _dip(self, 42)))

        initial_label = (
            self._choices[self._selection]
            if self._selection != wx.NOT_FOUND
            else ""
        )
        row = wx.BoxSizer(wx.HORIZONTAL)
        self._selected_icon_bitmap = wx.NullBitmap
        self._selected_icon_visible = False
        self._selected_icon_slot = 34
        self._label_control = wx.StaticText(self, label=initial_label)
        self._chevron_control = wx.StaticText(self, label="\u25be")
        for child in (
            self._label_control,
            self._chevron_control,
        ):
            _mark_custom_ui_owned(child)
            child.SetBackgroundColour(self._fill)
            child.SetForegroundColour(AUTO_FARMLAND_THEME["text"])
            child.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        row.AddSpacer(_dip(self, 12))
        self._icon_spacer_item = row.AddSpacer(
            _dip(self, self._selected_icon_slot + 4)
        )
        row.Add(
            self._label_control,
            1,
            wx.ALIGN_CENTER_VERTICAL,
        )
        row.Add(
            self._chevron_control,
            0,
            wx.RIGHT | wx.ALIGN_CENTER_VERTICAL,
            _dip(self, 12),
        )
        self.SetSizer(row)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda _event: None)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_SET_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        for target in (self, self._label_control, self._chevron_control):
            target.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
            target.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
            target.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
            target.Bind(wx.EVT_LEFT_UP, self._on_left_up)

        self._refresh_selected_icon()
        self._apply_visual_state()

    def SetShowIcons(self, show_icons=True):
        requested = bool(show_icons)
        if requested == self._show_icons:
            self._refresh_selected_icon()
            return
        self._show_icons = requested
        self._dismiss_popup()
        self._refresh_selected_icon()
        self.Layout()
        self.Refresh(False)

    def UsesIconPopup(self):
        provider = self._icon_provider
        if not self._show_icons or provider is None:
            return False
        try:
            return provider.available_count() > 0
        except Exception:
            return False

    def GetIconBitmap(self, choice, size, padding=0):
        provider = self._icon_provider
        if provider is None:
            return wx.NullBitmap
        try:
            return provider.get_bitmap(
                choice,
                _dip(self, size),
                padding=_dip(self, padding),
            )
        except Exception:
            return wx.NullBitmap

    def GetCompactIconBitmap(self, choice, size):
        provider = self._icon_provider
        if provider is None:
            return wx.NullBitmap
        try:
            return provider.get_compact_bitmap(choice, _dip(self, size))
        except Exception:
            return wx.NullBitmap

    def _refresh_selected_icon(self):
        choice = self.GetStringSelection()
        bitmap = wx.NullBitmap
        show = False
        if self._show_icons and choice:

            bitmap = self.GetCompactIconBitmap(choice, 34)
            try:
                show = bool(bitmap.IsOk())
            except Exception:
                show = False
        self._selected_icon_bitmap = bitmap if show else wx.NullBitmap
        self._selected_icon_visible = bool(show)
        try:
            self._icon_spacer_item.Show(bool(show))
        except Exception:
            pass
        try:
            self.Layout()
            self.Refresh(False)
        except Exception:
            pass

    def FindString(self, value):
        try:
            return self._choices.index(str(value))
        except ValueError:
            return wx.NOT_FOUND

    def SetSelection(self, selection):
        selection = int(selection)
        if 0 <= selection < len(self._choices):
            self._selection = selection
            label = self._choices[selection]
        else:
            self._selection = wx.NOT_FOUND
            label = ""
        self._label_control.SetLabel(label)
        self._refresh_selected_icon()
        self.Layout()
        self.Refresh(False)

    def GetSelection(self):
        return self._selection

    def GetStringSelection(self):
        if 0 <= self._selection < len(self._choices):
            return self._choices[self._selection]
        return ""

    def DoGetBestClientSize(self):
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        width = max(
            (dc.GetTextExtent(choice)[0] for choice in self._choices),
            default=120,
        )
        return wx.Size(width + _dip(self, 48), _dip(self, 42))

    def Enable(self, enable=True):
        result = super().Enable(enable)
        self.SetCursor(
            wx.Cursor(wx.CURSOR_HAND if enable else wx.CURSOR_ARROW)
        )
        for child in (self._label_control, self._chevron_control):
            try:
                child.SetCursor(
                    wx.Cursor(
                        wx.CURSOR_HAND if enable else wx.CURSOR_ARROW
                    )
                )
            except Exception:
                pass
        if not enable:
            self._dismiss_popup()
        self._apply_visual_state()
        return result

    def _visual_colors(self):
        if not self.IsEnabled():
            return (
                AUTO_FARMLAND_THEME["surface_alt"],
                AUTO_FARMLAND_THEME["disabled"],
                AUTO_FARMLAND_THEME["border_soft"],
            )
        if self._pressed:
            fill = AUTO_FARMLAND_THEME["surface_pressed"]
        elif self._hovered or self._popup_open:
            fill = AUTO_FARMLAND_THEME["surface_hover"]
        else:
            fill = AUTO_FARMLAND_THEME["surface_alt"]
        border = (
            AUTO_FARMLAND_THEME["accent_hover"]
            if self.HasFocus() or self._popup_open
            else AUTO_FARMLAND_THEME["border"]
        )
        return fill, AUTO_FARMLAND_THEME["text"], border

    def _apply_visual_state(self):
        fill, text_color, _border = self._visual_colors()
        try:
            self.SetBackgroundColour(fill)
        except Exception:
            pass
        try:
            self._chevron_control.SetLabel("\u25b4" if self._popup_open else "\u25be")
        except Exception:
            pass
        for child in (self._label_control, self._chevron_control):
            try:
                child.SetBackgroundColour(fill)
                child.SetForegroundColour(text_color)
                child.Refresh(False)
            except Exception:
                pass
        self.Refresh(False)

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_parent_background(self)))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return
        fill, _text_color, border = self._visual_colors()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(
            0.5,
            0.5,
            max(1, size.width - 1),
            max(1, size.height - 1),
            _dip(self, self._radius),
        )

        bitmap = self._selected_icon_bitmap
        try:
            bitmap_ok = bool(
                self._selected_icon_visible
                and bitmap is not None
                and bitmap.IsOk()
            )
        except Exception:
            bitmap_ok = False
        if bitmap_ok:
            bitmap_width = float(bitmap.GetWidth())
            bitmap_height = float(bitmap.GetHeight())
            slot_width = float(_dip(self, self._selected_icon_slot))
            slot_left = float(_dip(self, 8))
            icon_x = slot_left + max(0.0, (slot_width - bitmap_width) / 2.0)
            icon_y = max(float(_dip(self, 4)), (size.height - bitmap_height) / 2.0)
            gc.DrawBitmap(
                bitmap,
                icon_x,
                icon_y,
                bitmap_width,
                bitmap_height,
            )

    def _on_size(self, event):
        try:
            self.Layout()
            self.Refresh(False)
        except Exception:
            pass
        event.Skip()

    def _on_enter(self, event):
        self._hovered = True
        self._apply_visual_state()
        event.Skip()

    def _on_leave(self, event):
        try:
            wx.CallAfter(self._refresh_hover_from_pointer)
        except Exception:
            self._refresh_hover_from_pointer()
        event.Skip()

    def _refresh_hover_from_pointer(self):
        try:
            mouse = wx.GetMousePosition()
            rect = self.GetScreenRect()
            hovered = bool(rect.Contains(mouse))
        except Exception:
            hovered = False
        if hovered != self._hovered:
            self._hovered = hovered
            if not hovered and not self.HasCapture():
                self._pressed = False
            self._apply_visual_state()

    def _on_left_down(self, event):
        if not self.IsEnabled():
            return
        try:
            self.SetFocus()
        except Exception:
            pass
        self._pressed = True
        self._apply_visual_state()

    def _on_left_up(self, event):
        if not self.IsEnabled():
            return
        was_pressed = self._pressed
        self._pressed = False
        self._apply_visual_state()
        if was_pressed:
            self._toggle_popup()

    def _on_focus_change(self, event):
        self._apply_visual_state()
        event.Skip()

    def _toggle_popup(self):
        if not self.IsEnabled() or not self._choices:
            return
        now = perf_counter()
        if self._popup_open:
            self._dismiss_popup()
            return
        if now < self._suppress_popup_until:
            return

        popup = self._popup
        try:
            popup_alive = popup is not None and not popup.IsBeingDeleted()
        except Exception:
            popup_alive = popup is not None
        if not popup_alive:
            popup = ModernChoicePopup(self)
            self._popup = popup

        self._popup_open = True
        self._apply_visual_state()
        try:
            popup.show_for(self)
        except Exception:
            self._popup_open = False
            self._apply_visual_state()
            raise

    def _dismiss_popup(self):
        popup = self._popup
        if popup is None:
            self._popup_open = False
            self._apply_visual_state()
            return
        try:
            popup.Dismiss()
        except Exception:
            self._popup_open = False
            self._apply_visual_state()

    def _on_popup_dismissed(self, popup):
        if popup is not self._popup:
            return
        self._popup_open = False

        self._suppress_popup_until = perf_counter() + 0.20
        self._pressed = False
        self._apply_visual_state()

    def _select_from_popup(self, index):
        if index == self._selection:
            return
        self.SetSelection(index)
        _emit_command_event(self, wx.EVT_CHOICE)

    def _on_key_down(self, event):
        if not self.IsEnabled():
            event.Skip()
            return
        key = event.GetKeyCode()
        if key in (
            wx.WXK_SPACE,
            wx.WXK_RETURN,
            wx.WXK_NUMPAD_ENTER,
            wx.WXK_DOWN,
        ):
            self._toggle_popup()
            return
        if key == wx.WXK_ESCAPE and self._popup_open:
            self._dismiss_popup()
            return
        if key == wx.WXK_UP and self._choices:
            old = self._selection
            self.SetSelection(max(0, self._selection - 1))
            if self._selection != old:
                _emit_command_event(self, wx.EVT_CHOICE)
            return
        event.Skip()

    def _on_destroy(self, event):
        popup = self._popup
        self._popup = None
        self._popup_open = False
        if popup is not None:
            try:
                destroy_safely = getattr(popup, "destroy_safely", None)
                if destroy_safely is not None:
                    destroy_safely()
                else:
                    popup.Dismiss()
                    popup.Destroy()
            except Exception:
                pass
        event.Skip()

class CropToggleTile(wx.Control):

    def __init__(
        self,
        parent,
        label,
        icon_cache,
        value=False,
        interactive=True,
    ):
        super().__init__(
            parent,
            style=wx.BORDER_NONE | wx.WANTS_CHARS | wx.FULL_REPAINT_ON_RESIZE,
        )
        _mark_custom_ui_owned(self)
        self._label = str(label)
        self._icon_cache = icon_cache
        self._value = bool(value)
        self._interactive = bool(interactive)
        self._hovered = False
        self._pressed = False
        self._show_icons = True
        self._minimum_state = 0
        self._maximum_state = 0
        self._range_mode = False
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((_dip(self, 92), _dip(self, 112)))
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if interactive else wx.CURSOR_ARROW))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_SET_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_KILL_FOCUS, lambda event: (self.Refresh(False), event.Skip()))
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(False), event.Skip()))

    def GetLabel(self):
        return self._label

    def SetLabel(self, label):
        self._label = str(label)
        self.Refresh(False)

    def SetValue(self, value):
        self._value = bool(value)
        self.Refresh(False)

    def GetValue(self):
        return bool(self._value)

    def SetSelected(self, selected):
        self.SetValue(selected)

    def SetShowIcons(self, show=True):
        self._show_icons = bool(show)
        self.Refresh(False)

    def SetPreviewStates(self, minimum, maximum=None, range_mode=False):
        self._minimum_state = max(0, min(7, int(minimum)))
        if maximum is None:
            maximum = minimum
        self._maximum_state = max(0, min(7, int(maximum)))
        self._range_mode = bool(range_mode and self._minimum_state != self._maximum_state)
        self.Refresh(False)

    def Enable(self, enable=True):
        result = super().Enable(enable)
        cursor_kind = wx.CURSOR_HAND if enable and self._interactive else wx.CURSOR_ARROW
        self.SetCursor(wx.Cursor(cursor_kind))
        self.Refresh(False)
        return result

    @staticmethod
    def _bitmap_ok(bitmap):
        try:
            return bool(bitmap is not None and bitmap.IsOk())
        except Exception:
            return False

    def _draw_state_badge(self, gc, text, center_x, y):
        label = str(text)
        gc.SetFont(self.GetFont(), AUTO_FARMLAND_THEME["text"])
        width, height = _graphics_text_size(gc, label)
        pad_x = _dip(self, 5)
        pad_y = _dip(self, 2)
        gc.SetPen(wx.Pen(AUTO_FARMLAND_THEME["border_soft"], 1))
        gc.SetBrush(wx.Brush(AUTO_FARMLAND_THEME["console_bg"]))
        gc.DrawRoundedRectangle(
            center_x - (width + pad_x * 2) / 2,
            y,
            width + pad_x * 2,
            height + pad_y * 2,
            _dip(self, 5),
        )
        gc.DrawText(label, center_x - width / 2, y + pad_y)

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_parent_background(self)))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return
        enabled = self.IsEnabled()
        selected = bool(self._value)
        if not enabled:
            fill = AUTO_FARMLAND_THEME["surface_alt"]
            border = AUTO_FARMLAND_THEME["border_soft"]
            text_color = AUTO_FARMLAND_THEME["disabled"]
        elif self._pressed:
            fill = AUTO_FARMLAND_THEME["accent_pressed"]
            border = AUTO_FARMLAND_THEME["accent_hover"]
            text_color = AUTO_FARMLAND_THEME["text"]
        elif selected:
            fill = AUTO_FARMLAND_THEME["accent_soft"]
            border = AUTO_FARMLAND_THEME["accent"]
            text_color = AUTO_FARMLAND_THEME["text"]
        elif self._hovered:
            fill = AUTO_FARMLAND_THEME["surface_hover"]
            border = AUTO_FARMLAND_THEME["accent_hover"]
            text_color = AUTO_FARMLAND_THEME["text"]
        else:
            fill = AUTO_FARMLAND_THEME["surface_alt"]
            border = AUTO_FARMLAND_THEME["border"]
            text_color = AUTO_FARMLAND_THEME["text"]
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(
            0.5, 0.5, max(1, size.width - 1), max(1, size.height - 1), _dip(self, 10)
        )

        label_height = _dip(self, 26)
        icon_area_height = max(28, size.height - label_height - _dip(self, 8))

        state_badge_y = max(_dip(self, 3), icon_area_height - _dip(self, 14))
        icons_drawn = False
        if self._show_icons and self._icon_cache is not None:
            if self._range_mode:
                bitmap_size = min(_dip(self, 46), max(24, int(size.width * 0.38)))
                left = self._icon_cache.get_bitmap(
                    self._label, self._minimum_state, bitmap_size
                )
                right = self._icon_cache.get_bitmap(
                    self._label, self._maximum_state, bitmap_size
                )
                if self._bitmap_ok(left) and self._bitmap_ok(right):
                    gap = _dip(self, 4)
                    total = bitmap_size * 2 + gap
                    start_x = (size.width - total) / 2.0
                    y = max(_dip(self, 5), (icon_area_height - bitmap_size) / 2.0)
                    gc.DrawBitmap(left, start_x, y, bitmap_size, bitmap_size)
                    gc.DrawBitmap(right, start_x + bitmap_size + gap, y, bitmap_size, bitmap_size)
                    self._draw_state_badge(
                        gc,
                        self._minimum_state,
                        start_x + bitmap_size / 2.0,
                        state_badge_y,
                    )
                    self._draw_state_badge(
                        gc,
                        self._maximum_state,
                        start_x + bitmap_size + gap + bitmap_size / 2.0,
                        state_badge_y,
                    )
                    icons_drawn = True
            else:
                bitmap_size = min(_dip(self, 66), max(30, icon_area_height - _dip(self, 8)))
                bitmap = self._icon_cache.get_bitmap(
                    self._label, self._minimum_state, bitmap_size
                )
                if self._bitmap_ok(bitmap):
                    x = (size.width - bitmap_size) / 2.0
                    y = max(_dip(self, 3), (icon_area_height - bitmap_size) / 2.0)
                    gc.DrawBitmap(bitmap, x, y, bitmap_size, bitmap_size)
                    self._draw_state_badge(
                        gc,
                        self._minimum_state,
                        size.width / 2.0,
                        state_badge_y,
                    )
                    icons_drawn = True

        if not icons_drawn:
            placeholder = self._label[:1].upper() if self._label else "?"
            font = self.GetFont()
            try:
                font.SetPointSize(max(14, font.GetPointSize() + 7))
                font.SetWeight(wx.FONTWEIGHT_BOLD)
            except Exception:
                pass
            gc.SetFont(font, AUTO_FARMLAND_THEME["muted"])
            width, height = _graphics_text_size(gc, placeholder)
            gc.DrawText(
                placeholder,
                (size.width - width) / 2.0,
                max(_dip(self, 8), (icon_area_height - height) / 2.0),
            )

        gc.SetFont(self.GetFont(), text_color)
        text_width, text_height = _graphics_text_size(gc, self._label)
        gc.DrawText(
            self._label,
            (size.width - text_width) / 2.0,
            size.height - text_height - _dip(self, 7),
        )

        if selected and self._interactive:
            check = "✓"
            font = self.GetFont()
            try:
                font.SetWeight(wx.FONTWEIGHT_BOLD)
            except Exception:
                pass
            gc.SetFont(font, AUTO_FARMLAND_THEME["text"])
            width, height = _graphics_text_size(gc, check)
            gc.DrawText(check, size.width - width - _dip(self, 7), _dip(self, 5))
        if self.HasFocus() and enabled and self._interactive:
            gc.SetPen(wx.Pen(AUTO_FARMLAND_THEME["accent_hover"], 1))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawRoundedRectangle(
                2.5, 2.5, max(1, size.width - 5), max(1, size.height - 5), _dip(self, 8)
            )

    def _on_enter(self, event):
        self._hovered = True
        self.Refresh(False)
        event.Skip()

    def _on_leave(self, event):
        self._hovered = False
        if not self.HasCapture():
            self._pressed = False
        self.Refresh(False)
        event.Skip()

    def _on_left_down(self, _event):
        if not self.IsEnabled() or not self._interactive:
            return
        self.SetFocus()
        self._pressed = True
        try:
            self.CaptureMouse()
        except Exception:
            pass
        self.Refresh(False)

    def _on_left_up(self, event):
        if not self.IsEnabled() or not self._interactive:
            return
        was_pressed = self._pressed
        self._pressed = False
        try:
            if self.HasCapture():
                self.ReleaseMouse()
        except Exception:
            pass
        self.Refresh(False)
        if was_pressed and self.GetClientRect().Contains(event.GetPosition()):
            self._value = not self._value
            self.Refresh(False)
            _emit_command_event(self, wx.EVT_CHECKBOX)

    def _on_key_down(self, event):
        if (
            self.IsEnabled()
            and self._interactive
            and event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
        ):
            self._value = not self._value
            self.Refresh(False)
            _emit_command_event(self, wx.EVT_CHECKBOX)
            return
        event.Skip()

class CropExclusiveSelector(wx.Panel):

    def __init__(self, parent, choices, icon_cache):
        super().__init__(parent, style=wx.BORDER_NONE | wx.CLIP_CHILDREN)
        _mark_custom_ui_owned(self)
        self.SetBackgroundColour(parent.GetBackgroundColour())
        self._choices = [str(choice) for choice in choices]
        self._selection = 0 if self._choices else wx.NOT_FOUND
        self._tiles = []
        grid = wx.GridSizer(rows=1, cols=max(1, len(self._choices)), vgap=0, hgap=_dip(self, 6))
        for index, choice in enumerate(self._choices):
            tile = CropToggleTile(
                self,
                choice,
                icon_cache,
                value=(index == self._selection),
                interactive=True,
            )
            tile.Bind(
                wx.EVT_CHECKBOX,
                lambda _event, item_index=index: self._choose(item_index),
            )
            grid.Add(tile, 1, wx.EXPAND)
            self._tiles.append(tile)
        self.SetSizer(grid)
        self.SetMinSize((-1, _dip(self, 112)))

    def FindString(self, value):
        try:
            return self._choices.index(str(value))
        except ValueError:
            return wx.NOT_FOUND

    def SetSelection(self, selection):
        selection = int(selection)
        self._selection = selection if 0 <= selection < len(self._choices) else wx.NOT_FOUND
        for index, tile in enumerate(self._tiles):
            tile.SetValue(index == self._selection)

    def GetSelection(self):
        return self._selection

    def GetStringSelection(self):
        if 0 <= self._selection < len(self._choices):
            return self._choices[self._selection]
        return ""

    def SetPreviewStates(self, minimum, maximum=None, range_mode=False):
        for tile in self._tiles:
            tile.SetPreviewStates(minimum, maximum, range_mode)

    def SetShowIcons(self, show=True):
        for tile in self._tiles:
            tile.SetShowIcons(show)

    def Enable(self, enable=True):
        result = super().Enable(enable)
        for tile in self._tiles:
            tile.Enable(enable)
        return result

    def _choose(self, index):
        if not (0 <= index < len(self._choices)):
            return
        changed = index != self._selection
        self.SetSelection(index)
        if changed:
            _emit_command_event(self, wx.EVT_CHOICE)

class DarkActionPickerDialog(wx.Dialog):

    def __init__(
        self,
        parent,
        actions,
        initial_size=None,
        on_size_changed=None,
    ):
        super().__init__(
            parent,
            title="Manage Auto Farmland Plugin Files",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoFarmlandSettingsDialog",
        )
        self._actions = list(actions)
        self._selection = wx.NOT_FOUND
        self._on_size_changed = on_size_changed
        self.SetBackgroundColour(AUTO_FARMLAND_THEME["window"])
        minimum_size = (
            _dip(self, MANAGE_DIALOG_MIN_SIZE[0]),
            _dip(self, MANAGE_DIALOG_MIN_SIZE[1]),
        )
        self.SetMinSize(minimum_size)

        requested_size = initial_size
        if (
            not isinstance(requested_size, (list, tuple))
            or len(requested_size) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in requested_size
            )
        ):
            requested_size = MANAGE_DIALOG_DEFAULT_SIZE

        width = max(minimum_size[0], int(requested_size[0]))
        height = max(minimum_size[1], int(requested_size[1]))
        try:
            display_index = wx.Display.GetFromWindow(parent)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work_area = wx.Display(display_index).GetClientArea()
            width = min(width, max(minimum_size[0], work_area.width))
            height = min(height, max(minimum_size[1], work_area.height))
        except Exception:
            pass
        self.SetSize((width, height))

        root = wx.Panel(self, style=wx.BORDER_NONE | wx.CLIP_CHILDREN)
        _mark_custom_ui_owned(root)
        root.SetBackgroundColour(AUTO_FARMLAND_THEME["window"])
        outer = wx.BoxSizer(wx.VERTICAL)

        title = _make_text(root, "MANAGE PLUGIN FILES", point_size=14, bold=True)
        outer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP, _dip(root, 18))

        self._description = _make_text(
            root,
            "Choose an Auto Farmland file-management action.",
            muted=True,
        )
        self._description.SetMinSize((-1, _dip(root, 72)))
        self._description.Wrap(_dip(root, 490))
        outer.Add(
            self._description,
            0,
            wx.EXPAND | wx.ALL,
            _dip(root, 18),
        )

        list_card = RoundedPanel(
            root,
            background=AUTO_FARMLAND_THEME["surface"],
            border=AUTO_FARMLAND_THEME["border_soft"],
            radius=10,
        )
        card_sizer = wx.BoxSizer(wx.VERTICAL)

        self._scroll = ModernScrollViewport(
            list_card,
            background=AUTO_FARMLAND_THEME["surface"],
        )
        self._list_content = self._scroll.GetContentWindow()
        self._list_sizer = wx.BoxSizer(wx.VERTICAL)
        self._rows = []
        for index, (label, _description) in enumerate(self._actions):
            row = ModernChoiceOption(
                self._list_content,
                label,
                selected=False,
            )
            row.Bind(
                wx.EVT_BUTTON,
                lambda _event, item_index=index: self._select(item_index),
            )
            row.Bind(
                wx.EVT_LEFT_DCLICK,
                lambda _event, item_index=index: self._open(item_index),
            )
            self._list_sizer.Add(
                row,
                0,
                wx.EXPAND | wx.BOTTOM,
                _dip(self._list_content, 4),
            )
            self._rows.append(row)
        self._scroll.SetContentSizer(self._list_sizer)

        list_row = wx.BoxSizer(wx.HORIZONTAL)
        list_row.Add(self._scroll, 1, wx.EXPAND)
        self._scrollbar = ModernScrollBar(list_card, self._scroll)
        list_row.Add(
            self._scrollbar,
            0,
            wx.EXPAND | wx.LEFT,
            _dip(list_card, 4),
        )
        card_sizer.Add(list_row, 1, wx.EXPAND | wx.ALL, _dip(list_card, 6))
        list_card.SetSizer(card_sizer)
        outer.Add(
            list_card,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT,
            _dip(root, 18),
        )

        button_row = wx.BoxSizer(wx.HORIZONTAL)
        button_row.AddStretchSpacer(1)
        self._open_button = ModernButton(root, "Open", primary=True, compact=True)
        self._open_button.Enable(False)
        self._open_button.SetMinSize((_dip(root, 96), _dip(root, 36)))
        self._open_button.Bind(wx.EVT_BUTTON, lambda _event: self._open(self._selection))
        close_button = ModernButton(root, "Close", compact=True)
        close_button.SetMinSize((_dip(root, 96), _dip(root, 36)))
        close_button.Bind(wx.EVT_BUTTON, lambda _event: self.EndModal(wx.ID_CANCEL))
        button_row.Add(self._open_button, 0, wx.LEFT, _dip(root, 8))
        button_row.Add(close_button, 0, wx.LEFT, _dip(root, 8))
        outer.Add(
            button_row,
            0,
            wx.EXPAND | wx.ALL,
            _dip(root, 18),
        )

        root.SetSizer(outer)
        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(root, 1, wx.EXPAND)
        self.SetSizer(dialog_sizer)
        self.CenterOnParent()
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_SIZE, self._on_size)
        try:
            wx.CallAfter(self._sync_scroll_area)
        except Exception:
            self._sync_scroll_area()

    def _sync_scroll_area(self):
        try:
            self._scroll._modern_sync_layout()
        except Exception:
            pass
        try:
            self._scrollbar.sync()
        except Exception:
            pass

    def _on_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        try:
            wx.CallAfter(self._sync_scroll_area)
        except Exception:
            self._sync_scroll_area()

        callback = self._on_size_changed
        if callback is not None:
            try:
                callback(self)
            except Exception:
                pass

    def GetSelection(self):
        return self._selection

    def _select(self, index):
        if not (0 <= index < len(self._actions)):
            return
        self._selection = index
        for row_index, row in enumerate(self._rows):
            row.SetSelected(row_index == index)
        self._description.SetLabel(self._actions[index][1])
        self._description.Wrap(max(_dip(self, 320), self.GetClientSize().width - _dip(self, 70)))
        self._open_button.Enable(True)
        self.Layout()

    def _open(self, index):
        if 0 <= index < len(self._actions):
            self._selection = index
            self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and self._selection != wx.NOT_FOUND:
            self.EndModal(wx.ID_OK)
            return
        event.Skip()

class ModernTextField(RoundedPanel):

    _FORWARDED_EVENTS = (
        wx.EVT_TEXT,
        wx.EVT_TEXT_ENTER,
        wx.EVT_KILL_FOCUS,
        wx.EVT_SET_FOCUS,
    )

    def __init__(self, parent, value="", width=64):
        super().__init__(
            parent,
            background=AUTO_FARMLAND_THEME["surface_alt"],
            border=AUTO_FARMLAND_THEME["border"],
            radius=8,
        )
        self.SetMinSize((_dip(self, width), _dip(self, 32)))
        sizer = wx.BoxSizer(wx.VERTICAL)
        self._text = wx.TextCtrl(
            self,
            value=str(value),
            style=wx.BORDER_NONE | wx.TE_CENTER | wx.TE_PROCESS_ENTER,
        )
        _mark_custom_ui_owned(self._text)
        self._text.SetBackgroundColour(AUTO_FARMLAND_THEME["surface_alt"])
        self._text.SetForegroundColour(AUTO_FARMLAND_THEME["text"])

        try:
            font = self._text.GetFont()
            base_size = max(1.0, float(font.GetPointSize()))
            target_size = base_size * 1.25
            set_fractional_size = getattr(font, "SetFractionalPointSize", None)
            if callable(set_fractional_size):
                set_fractional_size(target_size)
            else:
                font.SetPointSize(max(1, int(round(target_size))))
            self._text.SetFont(font)
        except Exception:
            pass

        sizer.AddSpacer(_dip(self, 8))
        sizer.Add(
            self._text,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT,
            _dip(self, 4),
        )

        sizer.AddSpacer(_dip(self, 2))
        self.SetSizer(sizer)
        self._text.Bind(wx.EVT_SET_FOCUS, self._on_focus_change)
        self._text.Bind(wx.EVT_KILL_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_LEFT_UP, lambda _event: self._text.SetFocus())

    def Bind(self, event, handler, source=None, id=wx.ID_ANY, id2=wx.ID_ANY):
        if hasattr(self, "_text") and event in self._FORWARDED_EVENTS:
            return self._text.Bind(event, handler, source=source, id=id, id2=id2)
        return super().Bind(event, handler, source=source, id=id, id2=id2)

    def SetValue(self, value):
        self._text.SetValue(str(value))

    def ChangeValue(self, value):
        self._text.ChangeValue(str(value))

    def GetValue(self):
        return self._text.GetValue()

    def Enable(self, enable=True):
        result = super().Enable(enable)
        self._text.Enable(enable)
        return result

    def _on_focus_change(self, event):
        self._border = (
            AUTO_FARMLAND_THEME["accent_hover"]
            if self._text.HasFocus()
            else AUTO_FARMLAND_THEME["border"]
        )
        self.Refresh(False)
        event.Skip()

def _apply_rounded_window_shape(window, radius=10):
    try:
        size = window.GetClientSize()
        width = int(size.GetWidth())
        height = int(size.GetHeight())
    except Exception:
        try:
            width, height = map(int, window.GetClientSize())
        except Exception:
            return False

    if width <= 0 or height <= 0:
        return False

    try:
        radius_px = max(1, int(_dip(window, radius)))
    except Exception:
        radius_px = max(1, int(radius))
    radius_px = min(radius_px, width // 2, height // 2)

    try:
        if radius_px <= 1:
            region = wx.Region(0, 0, width, height)
        else:
            region = None
            for y in range(height):
                inset = _rounded_scanline_inset(
                    width,
                    height,
                    radius_px,
                    y,
                )
                row_width = max(1, width - inset * 2)
                row = wx.Region(inset, y, row_width, 1)
                if region is None:
                    region = row
                else:
                    region.Union(row)

        result = window.SetShape(region)
        return result is not False
    except Exception:
        return False

class _PortableAnchoredConsoleHint(wx.Frame):

    def __init__(self, owner, text):
        style = wx.FRAME_NO_TASKBAR | wx.BORDER_NONE
        style |= getattr(wx, "FRAME_FLOAT_ON_PARENT", 0)
        style |= getattr(wx, "FRAME_SHAPED", 0)
        super().__init__(owner, title="", style=style)
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:PortableConsoleHint",
        )
        self._shape_radius = 10
        self._shape_edge_colour = TOOLTIP_BORDER_COLOUR
        try:
            self.SetBackgroundColour(self._shape_edge_colour)
            self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        except Exception:
            pass

        panel = RoundedPanel(
            self,
            background=AUTO_FARMLAND_THEME["surface"],
            border=TOOLTIP_BORDER_COLOUR,
            radius=self._shape_radius,
            clear_background=self._shape_edge_colour,
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)
        label = _make_text(panel, text, point_size=8, muted=False)
        label.Wrap(_dip(panel, 260))
        sizer.Add(label, 0, wx.ALL | wx.EXPAND, _dip(panel, 10))

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(frame_sizer)
        self.Bind(wx.EVT_SIZE, self._on_shape_size)
        _apply_rounded_window_shape(self, self._shape_radius)

    def _on_shape_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        try:
            wx.CallAfter(
                _apply_rounded_window_shape,
                self,
                self._shape_radius,
            )
        except Exception:
            _apply_rounded_window_shape(self, self._shape_radius)

    def show_for(self, anchor):
        try:
            _apply_rounded_window_shape(self, self._shape_radius)
            anchor_origin = anchor.ClientToScreen((0, 0))
            anchor_size = anchor.GetClientSize()
            hint_size = self.GetSize()
            x = anchor_origin.x + anchor_size.width + _dip(anchor, 10)
            y = (
                anchor_origin.y
                + max(0, (anchor_size.height - hint_size.height) // 2)
            )

            display_index = wx.Display.GetFromPoint(
                wx.Point(anchor_origin.x, anchor_origin.y)
            )
            if display_index == wx.NOT_FOUND:
                display_index = wx.Display.GetFromWindow(anchor)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work_area = wx.Display(display_index).GetClientArea()

            if x + hint_size.width > work_area.GetRight():
                x = anchor_origin.x - hint_size.width - _dip(anchor, 10)
            x = max(
                work_area.x,
                min(x, work_area.GetRight() - hint_size.width),
            )
            y = max(
                work_area.y,
                min(y, work_area.GetBottom() - hint_size.height),
            )
            self.Move((x, y))

            show_without_activating = getattr(
                self,
                "ShowWithoutActivating",
                None,
            )
            if callable(show_without_activating):
                show_without_activating()
            else:
                self.Show(True)
            self.Raise()
            try:
                wx.CallAfter(
                    _apply_rounded_window_shape,
                    self,
                    self._shape_radius,
                )
            except Exception:
                pass
        except Exception:
            pass

    def dismiss(self):
        try:
            self.Hide()
        except Exception:
            pass

class _PortableCursorControlHint(wx.Frame):

    def __init__(self, owner):
        style = wx.FRAME_NO_TASKBAR | wx.BORDER_NONE
        style |= getattr(wx, "FRAME_FLOAT_ON_PARENT", 0)
        style |= getattr(wx, "FRAME_SHAPED", 0)
        super().__init__(owner, title="", style=style)
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:PortableControlHint",
        )
        self._shape_radius = 10
        self._shape_edge_colour = TOOLTIP_BORDER_COLOUR
        try:
            self.SetBackgroundColour(self._shape_edge_colour)
            self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        except Exception:
            pass

        self._panel = RoundedPanel(
            self,
            background=AUTO_FARMLAND_THEME["surface"],
            border=TOOLTIP_BORDER_COLOUR,
            radius=self._shape_radius,
            clear_background=self._shape_edge_colour,
        )
        self._label = _make_text(
            self._panel,
            "",
            point_size=8,
            muted=False,
        )
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        panel_sizer.Add(
            self._label,
            0,
            wx.ALL | wx.EXPAND,
            _dip(self._panel, 10),
        )
        self._panel.SetSizer(panel_sizer)

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(self._panel, 1, wx.EXPAND)
        self.SetSizer(frame_sizer)
        self.Bind(wx.EVT_SIZE, self._on_shape_size)

    def _on_shape_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        try:
            wx.CallAfter(
                _apply_rounded_window_shape,
                self,
                self._shape_radius,
            )
        except Exception:
            _apply_rounded_window_shape(self, self._shape_radius)

    def set_text(self, text):
        try:
            self._label.SetLabel(str(text))
            self._label.Wrap(_dip(self._panel, 300))
            self._panel.Layout()
            self.GetSizer().Fit(self)
            _apply_rounded_window_shape(self, self._shape_radius)
        except Exception:
            pass

    def show_at_pointer(self, anchor):
        try:
            _apply_rounded_window_shape(self, self._shape_radius)
            pointer = wx.GetMousePosition()
            hint_size = self.GetSize()
            offset_x = _dip(anchor, 16)
            offset_y = _dip(anchor, 20)
            x = pointer.x + offset_x
            y = pointer.y + offset_y

            display_index = wx.Display.GetFromPoint(pointer)
            if display_index == wx.NOT_FOUND:
                display_index = wx.Display.GetFromWindow(anchor)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work_area = wx.Display(display_index).GetClientArea()

            if x + hint_size.width > work_area.GetRight():
                x = pointer.x - hint_size.width - offset_x
            if y + hint_size.height > work_area.GetBottom():
                y = pointer.y - hint_size.height - offset_y
            x = max(
                work_area.x,
                min(x, work_area.GetRight() - hint_size.width),
            )
            y = max(
                work_area.y,
                min(y, work_area.GetBottom() - hint_size.height),
            )
            self.Move((x, y))

            show_without_activating = getattr(
                self,
                "ShowWithoutActivating",
                None,
            )
            if callable(show_without_activating):
                show_without_activating()
            else:
                self.Show(True)
            self.Raise()
            try:
                wx.CallAfter(
                    _apply_rounded_window_shape,
                    self,
                    self._shape_radius,
                )
            except Exception:
                pass
        except Exception:
            pass

    def dismiss(self):
        try:
            self.Hide()
        except Exception:
            pass

if os.name == "nt":
    class _WinPoint(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_long),
            ("y", ctypes.c_long),
        ]

    class _WinSize(ctypes.Structure):
        _fields_ = [
            ("cx", ctypes.c_long),
            ("cy", ctypes.c_long),
        ]

    class _WinBlendFunction(ctypes.Structure):
        _fields_ = [
            ("BlendOp", ctypes.c_ubyte),
            ("BlendFlags", ctypes.c_ubyte),
            ("SourceConstantAlpha", ctypes.c_ubyte),
            ("AlphaFormat", ctypes.c_ubyte),
        ]

    class _WinBitmapInfoHeader(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    class _WinBitmapInfo(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", _WinBitmapInfoHeader),
            ("bmiColors", ctypes.c_uint32 * 3),
        ]
else:
    _WinPoint = None
    _WinSize = None
    _WinBlendFunction = None
    _WinBitmapInfoHeader = None
    _WinBitmapInfo = None

def _wx_colour_tuple(colour, alpha=255):
    return (
        int(colour.Red()),
        int(colour.Green()),
        int(colour.Blue()),
        int(alpha),
    )

def _load_layered_tooltip_font(pixel_size):
    if ImageFont is None:
        return None

    candidates = []
    windows_root = os.environ.get("WINDIR", "").strip()
    if windows_root:
        font_root = Path(windows_root) / "Fonts"
        candidates.extend(
            (
                font_root / "segoeui.ttf",
                font_root / "arial.ttf",
                font_root / "tahoma.ttf",
            )
        )

    for candidate in candidates:
        try:
            if candidate.is_file():
                return ImageFont.truetype(
                    str(candidate),
                    max(8, int(pixel_size)),
                )
        except Exception:
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        return None

def _pil_text_width(draw, text, font):
    try:
        return max(
            0,
            int(round(draw.textlength(str(text), font=font))),
        )
    except Exception:
        try:
            box = draw.textbbox((0, 0), str(text), font=font)
            return max(0, int(box[2] - box[0]))
        except Exception:
            return 0

def _wrap_pil_tooltip_text(draw, text, font, max_width):
    lines = []
    paragraphs = str(text).replace("\r\n", "\n").split("\n")

    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if _pil_text_width(draw, candidate, font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)

    return lines or [""]

def _premultiplied_bgra_bytes(image):
    rgba = image.convert("RGBA").tobytes()
    output = bytearray(len(rgba))

    for index in range(0, len(rgba), 4):
        red = rgba[index]
        green = rgba[index + 1]
        blue = rgba[index + 2]
        alpha = rgba[index + 3]
        output[index] = (blue * alpha + 127) // 255
        output[index + 1] = (green * alpha + 127) // 255
        output[index + 2] = (red * alpha + 127) // 255
        output[index + 3] = alpha

    return bytes(output)

class _WindowsLayeredTooltipFrame(wx.Frame):

    _SUPERSAMPLE = 4

    def __init__(self, owner, max_text_width):
        style = wx.FRAME_NO_TASKBAR | wx.BORDER_NONE
        style |= getattr(wx, "FRAME_FLOAT_ON_PARENT", 0)
        super().__init__(owner, title="", size=(1, 1), style=style)
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:LayeredHint",
        )
        self._owner = owner
        self._max_text_width = max(80, int(max_text_width))
        self._text = ""
        self._rendered_image = None
        self._rendered_size = (1, 1)
        self._layered_ready = self._configure_layered_window()
        self._fallback = None
        try:
            self.Hide()
        except Exception:
            pass

    def _configure_layered_window(self):
        if os.name != "nt":
            return False
        try:
            handle = int(self.GetHandle())
            if not handle:
                return False

            user32 = ctypes.windll.user32
            get_window_long = getattr(
                user32,
                "GetWindowLongPtrW",
                user32.GetWindowLongW,
            )
            set_window_long = getattr(
                user32,
                "SetWindowLongPtrW",
                user32.SetWindowLongW,
            )
            try:
                get_window_long.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_int,
                ]
                get_window_long.restype = ctypes.c_ssize_t
                set_window_long.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.c_ssize_t,
                ]
                set_window_long.restype = ctypes.c_ssize_t
            except Exception:
                pass

            GWL_STYLE = -16
            GWL_EXSTYLE = -20

            WS_BORDER = 0x00800000
            WS_DLGFRAME = 0x00400000
            WS_THICKFRAME = 0x00040000
            WS_CAPTION = 0x00C00000

            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_WINDOWEDGE = 0x00000100
            WS_EX_CLIENTEDGE = 0x00000200
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000

            style = int(
                get_window_long(
                    ctypes.c_void_p(handle),
                    GWL_STYLE,
                )
            )
            style &= ~(
                WS_BORDER
                | WS_DLGFRAME
                | WS_THICKFRAME
                | WS_CAPTION
            )
            set_window_long(
                ctypes.c_void_p(handle),
                GWL_STYLE,
                ctypes.c_ssize_t(style),
            )

            ex_style = int(
                get_window_long(
                    ctypes.c_void_p(handle),
                    GWL_EXSTYLE,
                )
            )
            ex_style &= ~(WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE)
            ex_style |= (
                WS_EX_LAYERED
                | WS_EX_TOOLWINDOW
                | WS_EX_NOACTIVATE
                | WS_EX_TRANSPARENT
            )
            set_window_long(
                ctypes.c_void_p(handle),
                GWL_EXSTYLE,
                ctypes.c_ssize_t(ex_style),
            )

            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(
                ctypes.c_void_p(handle),
                None,
                0,
                0,
                0,
                0,
                SWP_NOSIZE
                | SWP_NOMOVE
                | SWP_NOZORDER
                | SWP_NOACTIVATE
                | SWP_FRAMECHANGED,
            )
            return True
        except Exception:
            return False

    def _render_text(self, text):
        if (
            Image is None
            or ImageDraw is None
            or ImageFont is None
        ):
            self._rendered_image = None
            self._rendered_size = (1, 1)
            return False

        try:
            scale = self._SUPERSAMPLE
            padding = max(6, _dip(self, 10))
            radius = max(5, _dip(self, 10))
            border_width = max(
                1,
                _dip(self, TOOLTIP_BORDER_WIDTH),
            )
            font_size = max(9, _dip(self, 11))
            max_text_width = max(
                80,
                _dip(self, self._max_text_width),
            )

            font = _load_layered_tooltip_font(font_size * scale)
            if font is None:
                return False

            measure_image = Image.new(
                "RGBA",
                (max_text_width * scale, 64 * scale),
                (0, 0, 0, 0),
            )
            measure_draw = ImageDraw.Draw(measure_image)
            lines = _wrap_pil_tooltip_text(
                measure_draw,
                text,
                font,
                max_text_width * scale,
            )

            try:
                sample_box = measure_draw.textbbox(
                    (0, 0),
                    "Ag",
                    font=font,
                )
                line_height = max(
                    1,
                    int(sample_box[3] - sample_box[1]),
                )
                baseline_offset = int(sample_box[1])
            except Exception:
                line_height = max(1, font_size * scale)
                baseline_offset = 0

            line_gap = max(1, _dip(self, 2)) * scale
            measured_widths = [
                _pil_text_width(
                    measure_draw,
                    line,
                    font,
                )
                for line in lines
            ]
            text_width = max(measured_widths or [1])
            text_height = (
                line_height * len(lines)
                + line_gap * max(0, len(lines) - 1)
            )

            final_width = max(
                2,
                int(round(text_width / scale))
                + padding * 2,
            )
            final_height = max(
                2,
                int(round(text_height / scale))
                + padding * 2,
            )

            render_width = final_width * scale
            render_height = final_height * scale
            image = Image.new(
                "RGBA",
                (render_width, render_height),
                (0, 0, 0, 0),
            )
            draw = ImageDraw.Draw(image)

            border_rgba = _wx_colour_tuple(
                TOOLTIP_BORDER_COLOUR,
            )
            surface_rgba = _wx_colour_tuple(
                AUTO_FARMLAND_THEME["surface"],
            )
            text_rgba = _wx_colour_tuple(
                AUTO_FARMLAND_THEME["text"],
            )

            outer_radius = radius * scale
            draw.rounded_rectangle(
                (
                    0,
                    0,
                    render_width - 1,
                    render_height - 1,
                ),
                radius=outer_radius,
                fill=border_rgba,
            )

            inset = border_width * scale
            draw.rounded_rectangle(
                (
                    inset,
                    inset,
                    render_width - 1 - inset,
                    render_height - 1 - inset,
                ),
                radius=max(1, outer_radius - inset),
                fill=surface_rgba,
            )

            text_x = padding * scale
            text_y = padding * scale
            for line in lines:
                draw.text(
                    (
                        text_x,
                        text_y - baseline_offset,
                    ),
                    line,
                    font=font,
                    fill=text_rgba,
                )
                text_y += line_height + line_gap

            try:
                resampling = Image.Resampling.LANCZOS
            except Exception:
                resampling = Image.LANCZOS
            image = image.resize(
                (final_width, final_height),
                resampling,
            )

            self._rendered_image = image
            self._rendered_size = (
                final_width,
                final_height,
            )
            try:
                self.SetSize(self._rendered_size)
            except Exception:
                pass
            return True
        except Exception:
            self._rendered_image = None
            self._rendered_size = (1, 1)
            return False

    def _update_layered_window(self, x, y):
        if (
            not self._layered_ready
            or self._rendered_image is None
            or os.name != "nt"
        ):
            return False

        screen_dc = None
        memory_dc = None
        bitmap = None
        old_bitmap = None

        try:
            width, height = self._rendered_size
            if width <= 0 or height <= 0:
                return False

            handle = int(self.GetHandle())
            if not handle:
                return False

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            user32.GetDC.restype = ctypes.c_void_p
            gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
            gdi32.CreateDIBSection.restype = ctypes.c_void_p
            gdi32.SelectObject.restype = ctypes.c_void_p

            screen_dc = user32.GetDC(None)
            if not screen_dc:
                return False

            memory_dc = gdi32.CreateCompatibleDC(
                ctypes.c_void_p(screen_dc)
            )
            if not memory_dc:
                return False

            bitmap_info = _WinBitmapInfo()
            bitmap_info.bmiHeader.biSize = ctypes.sizeof(
                _WinBitmapInfoHeader
            )
            bitmap_info.bmiHeader.biWidth = int(width)
            bitmap_info.bmiHeader.biHeight = -int(height)
            bitmap_info.bmiHeader.biPlanes = 1
            bitmap_info.bmiHeader.biBitCount = 32
            bitmap_info.bmiHeader.biCompression = 0
            bitmap_info.bmiHeader.biSizeImage = (
                int(width) * int(height) * 4
            )

            pixel_pointer = ctypes.c_void_p()
            bitmap = gdi32.CreateDIBSection(
                ctypes.c_void_p(screen_dc),
                ctypes.byref(bitmap_info),
                0,
                ctypes.byref(pixel_pointer),
                None,
                0,
            )
            if not bitmap or not pixel_pointer.value:
                return False

            pixels = _premultiplied_bgra_bytes(
                self._rendered_image
            )
            ctypes.memmove(
                pixel_pointer,
                pixels,
                len(pixels),
            )

            old_bitmap = gdi32.SelectObject(
                ctypes.c_void_p(memory_dc),
                ctypes.c_void_p(bitmap),
            )

            destination = _WinPoint(int(x), int(y))
            source = _WinPoint(0, 0)
            size = _WinSize(int(width), int(height))
            blend = _WinBlendFunction(
                0,
                0,
                255,
                1,
            )

            user32.UpdateLayeredWindow.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(_WinPoint),
                ctypes.POINTER(_WinSize),
                ctypes.c_void_p,
                ctypes.POINTER(_WinPoint),
                ctypes.c_uint32,
                ctypes.POINTER(_WinBlendFunction),
                ctypes.c_uint32,
            ]
            user32.UpdateLayeredWindow.restype = ctypes.c_int

            updated = user32.UpdateLayeredWindow(
                ctypes.c_void_p(handle),
                ctypes.c_void_p(screen_dc),
                ctypes.byref(destination),
                ctypes.byref(size),
                ctypes.c_void_p(memory_dc),
                ctypes.byref(source),
                0,
                ctypes.byref(blend),
                0x00000002,
            )
            if not updated:
                return False

            user32.ShowWindow(
                ctypes.c_void_p(handle),
                4,
            )
            user32.SetWindowPos(
                ctypes.c_void_p(handle),
                None,
                int(x),
                int(y),
                int(width),
                int(height),
                0x0010 | 0x0040,
            )
            return True
        except Exception:
            return False
        finally:
            try:
                if old_bitmap and memory_dc:
                    ctypes.windll.gdi32.SelectObject(
                        ctypes.c_void_p(memory_dc),
                        ctypes.c_void_p(old_bitmap),
                    )
            except Exception:
                pass
            try:
                if bitmap:
                    ctypes.windll.gdi32.DeleteObject(
                        ctypes.c_void_p(bitmap)
                    )
            except Exception:
                pass
            try:
                if memory_dc:
                    ctypes.windll.gdi32.DeleteDC(
                        ctypes.c_void_p(memory_dc)
                    )
            except Exception:
                pass
            try:
                if screen_dc:
                    ctypes.windll.user32.ReleaseDC(
                        None,
                        ctypes.c_void_p(screen_dc),
                    )
            except Exception:
                pass

    def _hide_layered_window(self):
        try:
            handle = int(self.GetHandle())
            if handle and os.name == "nt":
                ctypes.windll.user32.ShowWindow(
                    ctypes.c_void_p(handle),
                    0,
                )
                return
        except Exception:
            pass
        try:
            self.Hide()
        except Exception:
            pass

    def dismiss(self):
        self._hide_layered_window()
        fallback = self._fallback
        if fallback is not None:
            try:
                fallback.dismiss()
            except Exception:
                pass

class _WindowsLayeredAnchoredConsoleHint(
    _WindowsLayeredTooltipFrame
):

    def __init__(self, owner, text):
        super().__init__(owner, max_text_width=260)
        self._text = str(text)
        self._render_text(self._text)

    def show_for(self, anchor):
        try:
            anchor_origin = anchor.ClientToScreen((0, 0))
            anchor_size = anchor.GetClientSize()
            width, height = self._rendered_size
            x = anchor_origin.x + anchor_size.width + _dip(anchor, 10)
            y = anchor_origin.y + max(
                0,
                (anchor_size.height - height) // 2,
            )

            display_index = wx.Display.GetFromPoint(
                wx.Point(anchor_origin.x, anchor_origin.y)
            )
            if display_index == wx.NOT_FOUND:
                display_index = wx.Display.GetFromWindow(anchor)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work_area = wx.Display(display_index).GetClientArea()

            if x + width > work_area.GetRight():
                x = anchor_origin.x - width - _dip(anchor, 10)
            x = max(
                work_area.x,
                min(x, work_area.GetRight() - width),
            )
            y = max(
                work_area.y,
                min(y, work_area.GetBottom() - height),
            )

            if self._update_layered_window(x, y):
                if self._fallback is not None:
                    self._fallback.dismiss()
                return
        except Exception:
            pass

        if self._fallback is None:
            self._fallback = _PortableAnchoredConsoleHint(
                self._owner,
                self._text,
            )
        self._fallback.show_for(anchor)

class _WindowsLayeredCursorControlHint(
    _WindowsLayeredTooltipFrame
):

    def __init__(self, owner):
        super().__init__(owner, max_text_width=300)

    def set_text(self, text):
        self._text = str(text)
        self._render_text(self._text)
        if self._fallback is not None:
            self._fallback.set_text(self._text)

    def show_at_pointer(self, anchor):
        try:
            pointer = wx.GetMousePosition()
            width, height = self._rendered_size
            offset_x = _dip(anchor, 16)
            offset_y = _dip(anchor, 20)
            x = pointer.x + offset_x
            y = pointer.y + offset_y

            display_index = wx.Display.GetFromPoint(pointer)
            if display_index == wx.NOT_FOUND:
                display_index = wx.Display.GetFromWindow(anchor)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work_area = wx.Display(display_index).GetClientArea()

            if x + width > work_area.GetRight():
                x = pointer.x - width - offset_x
            if y + height > work_area.GetBottom():
                y = pointer.y - height - offset_y
            x = max(
                work_area.x,
                min(x, work_area.GetRight() - width),
            )
            y = max(
                work_area.y,
                min(y, work_area.GetBottom() - height),
            )

            if self._update_layered_window(x, y):
                if self._fallback is not None:
                    self._fallback.dismiss()
                return
        except Exception:
            pass

        if self._fallback is None:
            self._fallback = _PortableCursorControlHint(
                self._owner
            )
            self._fallback.set_text(self._text)
        self._fallback.show_at_pointer(anchor)

if (
    os.name == "nt"
    and Image is not None
    and ImageDraw is not None
    and ImageFont is not None
):
    AnchoredConsoleHint = _WindowsLayeredAnchoredConsoleHint
    CursorControlHint = _WindowsLayeredCursorControlHint
else:
    AnchoredConsoleHint = _PortableAnchoredConsoleHint
    CursorControlHint = _PortableCursorControlHint

@dataclass
class SurfaceCandidate:

    farmland_pos: Position
    crop_pos: Position
    clear_positions: Set[Position] = field(default_factory=set)
    originals: Dict[Position, Tuple[Block, object]] = field(default_factory=dict)

@dataclass
class FarmPlan:

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

class AutoFarmlandWindow(wx.Frame):

    def __init__(self, parent, host):
        style = wx.DEFAULT_FRAME_STYLE
        style |= getattr(wx, "FRAME_FLOAT_ON_PARENT", 0)
        super().__init__(
            parent,
            title="Auto Farmland",
            size=FLOATING_DEFAULT_SIZE,
            style=style,
        )
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoFarmlandWindow",
        )
        self._host_ref = weakref.ref(host)
        self._allow_destroy = False
        self.SetBackgroundColour(AUTO_FARMLAND_THEME["passive_window"])
        self.SetMinSize(
            (
                _dip(self, FLOATING_MIN_SIZE[0]),
                _dip(self, FLOATING_MIN_SIZE[1]),
            )
        )
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def destroy_for_host(self):
        self._allow_destroy = True
        try:
            self.Destroy()
        except Exception:
            pass

    def _on_close(self, event):
        if self._allow_destroy:
            event.Skip()
            return
        try:
            event.Veto()
        except Exception:
            pass
        self.Hide()
        host = self._host_ref()
        if host is not None:
            host._update_launcher_status()

    def _on_show(self, event):
        host = self._host_ref()
        if host is not None:
            host._update_launcher_status()
        event.Skip()

class AutoFarmland(wx.Panel, DefaultOperationUI):

    SETTINGS_CONFIG_FILENAME = "Auto Farmland.config"
    SETTINGS_CONFIG_FORMAT_VERSION = 5
    SETTINGS_SAVE_DELAY_MS = 500
    MAX_SETTINGS_CONFIG_BYTES = 1024 * 1024
    CONSOLE_SEMANTIC_NAME = "AmuletPluginConsole:AutoFarmland"
    CONSOLE_TOOLTIP_DELAY_MS = 650
    CONTROL_TOOLTIP_DELAY_MS = 550

    SETTINGS_VIEWPORT_HEIGHT = 280
    SETTINGS_GROW_PROPORTION = 4
    CONSOLE_GROW_PROPORTION = 1
    CONSOLE_MIN_TEXT_HEIGHT = 150
    CONSOLE_MIN_CARD_HEIGHT = 194
    FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT = 720

    def __init__(self, parent, canvas, world, options_path):
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)

        self._selection = BlockSelectionBehaviour(self.canvas)
        self._settings_config_save_call = None
        self._settings_config_applying = False
        self._settings_ready = False
        self._settings_defaults: Dict[str, object] = {}
        self._settings_config_unknown_data: Dict[str, object] = {}
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._report_lines: List[str] = []
        self._last_report_text = ""
        self._plugin_window = None
        self._window_has_been_shown = False
        self._destroying = False
        self._manage_dialog_size = MANAGE_DIALOG_DEFAULT_SIZE
        self._console_visible = True
        self._operation_running = False
        self._operation_button_restore_call = None
        self._control_help_window = None
        self._control_help_call = None
        self._control_help_anchor_ref = None
        self._control_help_text = ""
        self._console_help_window = None
        self._console_help_call = None
        self._console_help_hovered = False
        self._console_help_text = (
            "Shows the current operation report. Click or focus the console to "
            "read, select, and copy text without the help bubble remaining open."
        )
        self._crop_icon_cache = AmuletCropIconCache()
        self._slab_icon_cache = AmuletSlabIconCache()

        wx.ToolTip.SetAutoPop(28000)
        self._build_launcher_ui()
        self._build_floating_ui()
        self._initialize_settings_persistence()
        self._update_ui_visibility()
        self._update_growth_description()
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_host_destroy)
        try:
            wx.CallAfter(self._show_plugin_window)
        except Exception:
            self._show_plugin_window()

    def _build_launcher_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)
        margin = 6
        title = wx.StaticText(self, label="Auto Farmland")
        try:
            font = title.GetFont()
            font.SetPointSize(max(font.GetPointSize(), 10))
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            title.SetFont(font)
        except Exception:
            pass
        outer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, margin)
        description = wx.StaticText(self, label="Floating interface.")
        outer.Add(description, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, margin)
        self.open_window_button = ModernButton(
            self,
            "Open Window",
            primary=True,
            compact=True,
        )
        self.open_window_button.Bind(wx.EVT_BUTTON, self._show_plugin_window)
        outer.Add(
            self.open_window_button,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            margin,
        )
        self.launcher_status = wx.StaticText(self, label="Opens automatically.")
        outer.Add(self.launcher_status, 0, wx.ALL | wx.EXPAND, margin)
        self.SetMinSize((150, 130))
        self.SetSize((150, 130))

    def _create_card(self, parent, title, subtitle=None):
        card = RoundedPanel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        card.SetSizer(sizer)
        heading = _make_text(card, title.upper(), point_size=9, bold=True)
        sizer.Add(
            heading,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            UI_CARD_PADDING,
        )
        if subtitle:
            subtitle_control = _make_wrapped_text(
                card,
                subtitle,
                point_size=8,
                muted=True,
            )
            sizer.Add(
                subtitle_control,
                0,
                wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
                UI_CARD_PADDING,
            )
        sizer.AddSpacer(_dip(card, 6))
        return card, sizer

    def _build_labeled_choice(
        self,
        card,
        sizer,
        label,
        choices,
        tooltip,
        *,
        icon_provider=None,
        show_icons=False,
    ):
        label_control = _make_text(card, label, point_size=9, bold=True)
        sizer.Add(
            label_control,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        choice = ModernChoice(
            card,
            choices,
            icon_provider=icon_provider,
            show_icons=show_icons,
        )
        self._set_control_tooltip(choice, tooltip)
        sizer.Add(
            choice,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        return label_control, choice

    def _build_slider_row(self, parent, value, minimum, maximum, box_width=56):
        row = wx.BoxSizer(wx.HORIZONTAL)
        slider = ModernSlider(parent, value=value, minValue=minimum, maxValue=maximum)
        text_box = ModernTextField(parent, value=str(value), width=box_width)
        row.Add(slider, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, _dip(parent, 8))
        row.Add(text_box, 0, wx.ALIGN_CENTER_VERTICAL)
        return row, slider, text_box

    def _sync_main_content_width(self):
        root = getattr(self, "_main_content_root", None)
        panel = getattr(self, "_main_content_panel", None)
        item = getattr(self, "_main_content_sizer_item", None)
        if root is None or panel is None or item is None:
            return

        try:
            available_width = int(root.GetClientSize().width)
        except Exception:
            return
        if available_width <= 0:
            return

        target_width = min(
            available_width,
            _dip(root, UI_MAIN_CONTENT_MAX_WIDTH),
        )
        if target_width == getattr(self, "_main_content_width", None):
            return

        self._main_content_width = target_width
        try:
            panel.SetMinSize((target_width, -1))
        except Exception:
            pass
        try:
            item.SetMinSize((target_width, -1))
        except Exception:
            pass
        try:
            panel.InvalidateBestSize()
        except Exception:
            pass
        try:
            root.Layout()
        except Exception:
            pass

    def _on_main_content_root_size(self, event):
        self._sync_main_content_width()
        event.Skip()

    def _build_floating_ui(self):
        owner = wx.GetTopLevelParent(self) or self
        self._plugin_window = AutoFarmlandWindow(owner, self)
        root = wx.Panel(
            self._plugin_window,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(
            root,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoFarmlandRoot",
        )
        root.SetBackgroundColour(AUTO_FARMLAND_THEME["passive_window"])
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        root.SetSizer(root_sizer)

        self._main_content_root = root
        self._main_content_panel = wx.Panel(
            root,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(
            self._main_content_panel,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoFarmlandMainContent",
        )
        self._main_content_panel.SetBackgroundColour(
            AUTO_FARMLAND_THEME["passive_window"]
        )
        main_content_sizer = wx.BoxSizer(wx.VERTICAL)
        self._main_content_panel.SetSizer(main_content_sizer)

        root_sizer.AddStretchSpacer(1)
        self._main_content_sizer_item = root_sizer.Add(
            self._main_content_panel,
            0,
            wx.EXPAND,
        )
        root_sizer.AddStretchSpacer(1)

        initial_content_width = _dip(
            root,
            min(FLOATING_DEFAULT_SIZE[0], UI_MAIN_CONTENT_MAX_WIDTH),
        )
        self._main_content_width = initial_content_width
        self._main_content_panel.SetMinSize((initial_content_width, -1))
        self._main_content_sizer_item.SetMinSize((initial_content_width, -1))
        root.Bind(wx.EVT_SIZE, self._on_main_content_root_size)

        header = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(header)
        header.SetBackgroundColour(AUTO_FARMLAND_THEME["passive_window"])
        header_sizer = wx.BoxSizer(wx.VERTICAL)
        header.SetSizer(header_sizer)
        title = _make_text(header, "AUTO FARMLAND", point_size=18, bold=True)
        subtitle = _make_wrapped_text(
            header,
            "Surface-aware crop layouts, hydration planning, and reporting",
            point_size=9,
            muted=True,
        )
        header_sizer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 16)
        header_sizer.Add(
            subtitle,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM | wx.EXPAND,
            16,
        )
        main_content_sizer.Add(header, 0, wx.EXPAND)

        settings_host = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(settings_host)
        settings_host.SetBackgroundColour(AUTO_FARMLAND_THEME["passive_window"])
        settings_row = wx.BoxSizer(wx.HORIZONTAL)
        settings_host.SetSizer(settings_row)
        self.scroll = ModernScrollViewport(
            settings_host,
            background=AUTO_FARMLAND_THEME["passive_window"],
        )
        _mark_custom_ui_owned(
            self.scroll,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoFarmlandSettings",
        )

        self.scroll.SetMinSize((-1, self.SETTINGS_VIEWPORT_HEIGHT))
        self.settings_content_panel = self.scroll.GetContentWindow()
        content = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetContentSizer(content)
        content.AddSpacer(_dip(self.scroll, 4))

        placement_card, placement_sizer = self._create_card(
            self.settings_content_panel,
            "Farmland Placement",
            "Choose whether Auto Farmland replaces grass or builds above safe surfaces.",
        )
        self.replace_grass_cb = ModernCheckBox(
            placement_card,
            "Replace grass blocks with farmland",
            True,
        )
        self._set_control_tooltip(
            self.replace_grass_cb,
            "Enabled: eligible exposed grass blocks become farmland at their "
            "current level. Disabled: the original support remains and farmland "
            "is placed one block above safe exposed surfaces.",
        )
        _tighten_gap_before_checkbox(placement_sizer)
        placement_sizer.Add(
            self.replace_grass_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        placement_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(placement_sizer)
        placement_sizer.AddSpacer(UI_CHECKBOX_GROUP_TRANSITION_GAP)
        self.placement_explanation = _make_wrapped_text(
            placement_card,
            "Eligible grass blocks are replaced with farmland at their current position.",
            point_size=8,
            muted=True,
        )
        placement_sizer.Add(
            self.placement_explanation,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.raised_support_label, self.raised_support_choice = self._build_labeled_choice(
            placement_card,
            placement_sizer,
            "Raised farmland support",
            ("Natural terrain only", "Any safe full block"),
            "Controls which retained surface blocks may support farmland in raised "
            "mode. Partial, fluid, interactive, and block-entity supports are always rejected.",
        )
        self.replace_plants_cb = ModernCheckBox(
            placement_card,
            "Replace decorative plants above targets",
            True,
        )
        self._set_control_tooltip(
            self.replace_plants_cb,
            "Allows a narrow safe list of grass, ferns, flowers, and similar "
            "decoration to be removed. Existing crops and productive plants are protected.",
        )
        _tighten_gap_before_checkbox(placement_sizer)
        placement_sizer.Add(
            self.replace_plants_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        placement_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        self.skip_isolated_raised_cb = ModernCheckBox(
            placement_card,
            "Skip isolated raised farmland",
            True,
        )
        self._set_control_tooltip(
            self.skip_isolated_raised_cb,
            "Prevents raised mode from scattering single farmland blocks across "
            "rough terrain. A selection containing only one valid column remains allowed.",
        )
        _tighten_gap_before_checkbox(placement_sizer)
        placement_sizer.Add(
            self.skip_isolated_raised_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        placement_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(placement_sizer)
        content.Add(
            placement_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        crop_card, crop_sizer = self._create_card(
            self.settings_content_panel,
            "Crop Layout",
            "Choose a layout and preview the exact visual growth state before writing.",
        )
        _, self.crop_layout_choice = self._build_labeled_choice(
            crop_card,
            crop_sizer,
            "Layout",
            CROP_LAYOUT_CHOICES,
            "Choose farmland only, one standard crop, alternating crop rows, "
            "deterministically assorted crops, or a melon / pumpkin stem layout.",
        )

        self.crop_layout_choice.SetSelection(1)
        self.single_crop_label = _make_text(
            crop_card,
            "Single crop",
            point_size=9,
            bold=True,
        )
        crop_sizer.Add(
            self.single_crop_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.single_crop_choice = CropExclusiveSelector(
            crop_card,
            STANDARD_CROPS,
            self._crop_icon_cache,
        )
        self._set_control_tooltip(
            self.single_crop_choice,
            "Choose the standard crop used by the Single Crop layout. Preview "
            "artwork follows the active fixed state or random growth range.",
        )
        crop_sizer.Add(
            self.single_crop_choice,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )

        self.selected_crops_label = _make_text(
            crop_card,
            "Crops included in the layout",
            point_size=9,
            bold=True,
        )
        crop_sizer.Add(
            self.selected_crops_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.selected_crops_panel = wx.Panel(
            crop_card,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(self.selected_crops_panel)
        self.selected_crops_panel.SetBackgroundColour(crop_card.GetBackgroundColour())
        selected_grid = wx.GridSizer(rows=1, cols=4, vgap=0, hgap=_dip(crop_card, 6))
        self.crop_wheat_cb = CropToggleTile(
            self.selected_crops_panel, "Wheat", self._crop_icon_cache, True
        )
        self.crop_carrots_cb = CropToggleTile(
            self.selected_crops_panel, "Carrots", self._crop_icon_cache, True
        )
        self.crop_potatoes_cb = CropToggleTile(
            self.selected_crops_panel, "Potatoes", self._crop_icon_cache, True
        )
        self.crop_beetroot_cb = CropToggleTile(
            self.selected_crops_panel, "Beetroot", self._crop_icon_cache, True
        )
        for crop_control in (
            self.crop_wheat_cb,
            self.crop_carrots_cb,
            self.crop_potatoes_cb,
            self.crop_beetroot_cb,
        ):
            selected_grid.Add(crop_control, 1, wx.EXPAND)
            self._set_control_tooltip(
                crop_control,
                "Include this crop in Alternating Crop Rows and Assorted Crops. "
                "The artwork updates with the selected growth state or range.",
            )
        self.selected_crops_panel.SetSizer(selected_grid)
        self.selected_crops_panel.SetMinSize((-1, _dip(crop_card, 112)))
        crop_sizer.Add(
            self.selected_crops_panel,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )

        self.stem_preview_label = _make_text(
            crop_card,
            "Stem preview",
            point_size=9,
            bold=True,
        )
        crop_sizer.Add(
            self.stem_preview_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.stem_preview = CropToggleTile(
            crop_card,
            "Melon Stem",
            self._crop_icon_cache,
            value=False,
            interactive=False,
        )
        self.stem_preview.SetMinSize((-1, _dip(crop_card, 112)))
        crop_sizer.Add(
            self.stem_preview,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )

        self.row_direction_label, self.row_direction_choice = self._build_labeled_choice(
            crop_card,
            crop_sizer,
            "Row direction",
            ("Automatic", "Along X", "Along Z"),
            "Alternating crops change across rows perpendicular to this axis. "
            "Automatic chooses the longer horizontal axis separately for each "
            "selection box. Stem rows use the same direction setting.",
        )
        self.show_crop_icons_cb = ModernCheckBox(
            crop_card,
            "Show live crop previews",
            True,
        )
        self._set_control_tooltip(
            self.show_crop_icons_cb,
            "Uses crop textures from Amulet's local vanilla resource cache. "
            "The selectors remain available as labeled text tiles when artwork is missing.",
        )
        _tighten_gap_before_checkbox(crop_sizer)
        crop_sizer.Add(
            self.show_crop_icons_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        crop_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(crop_sizer)
        content.Add(
            crop_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        growth_card, growth_sizer = self._create_card(
            self.settings_content_panel,
            "Growth",
            "Set one exact state or a deterministic random range from state 0 through 7.",
        )
        self.growth_mode_label, self.growth_mode_choice = self._build_labeled_choice(
            growth_card,
            growth_sizer,
            "Growth mode",
            GROWTH_MODE_CHOICES,
            "Use one fixed growth state or a deterministic random state between "
            "the selected minimum and maximum.",
        )
        self.growth_label = _make_text(
            growth_card,
            "Fixed growth state",
            point_size=9,
            bold=True,
        )
        growth_sizer.Add(
            self.growth_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.growth_row, self.growth_slider, self.growth_box = self._build_slider_row(
            growth_card, 0, 0, 7
        )
        self.growth_row_item = growth_sizer.Add(
            self.growth_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.growth_description = _make_text(
            growth_card,
            "State 0 of 7 - Just planted",
            point_size=8,
            muted=True,
        )
        growth_sizer.Add(
            self.growth_description,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )

        self.random_growth_min_label = _make_text(
            growth_card,
            "Minimum random growth",
            point_size=9,
            bold=True,
        )
        growth_sizer.Add(
            self.random_growth_min_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        (
            self.random_growth_min_row,
            self.random_growth_min_slider,
            self.random_growth_min_box,
        ) = self._build_slider_row(growth_card, 0, 0, 7)
        self.random_growth_min_row_item = growth_sizer.Add(
            self.random_growth_min_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.random_growth_max_label = _make_text(
            growth_card,
            "Maximum random growth",
            point_size=9,
            bold=True,
        )
        growth_sizer.Add(
            self.random_growth_max_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        (
            self.random_growth_max_row,
            self.random_growth_max_slider,
            self.random_growth_max_box,
        ) = self._build_slider_row(growth_card, 7, 0, 7)
        self.random_growth_max_row_item = growth_sizer.Add(
            self.random_growth_max_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.growth_range_description = _make_text(
            growth_card,
            "Random range: state 0 through state 7",
            point_size=8,
            muted=True,
        )
        growth_sizer.Add(
            self.growth_range_description,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )

        self.pattern_seed_label = _make_text(
            growth_card,
            "Pattern seed",
            point_size=9,
            bold=True,
        )
        growth_sizer.Add(
            self.pattern_seed_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.pattern_seed_row = wx.BoxSizer(wx.HORIZONTAL)
        self.pattern_seed_slider = ModernSlider(
            growth_card,
            value=0,
            minValue=0,
            maxValue=PATTERN_SEED_MAX,
        )
        self.pattern_seed_box = ModernTextField(growth_card, value="0", width=84)
        self.randomize_seed_button = ModernButton(
            growth_card,
            "Randomize",
            compact=True,
        )
        self.pattern_seed_row.Add(
            self.pattern_seed_slider,
            1,
            wx.RIGHT | wx.ALIGN_CENTER_VERTICAL,
            _dip(growth_card, 8),
        )
        self.pattern_seed_row.Add(
            self.pattern_seed_box,
            0,
            wx.RIGHT | wx.ALIGN_CENTER_VERTICAL,
            _dip(growth_card, 8),
        )
        self.pattern_seed_row.Add(
            self.randomize_seed_button,
            0,
            wx.ALIGN_CENTER_VERTICAL,
        )
        self.pattern_seed_row_item = growth_sizer.Add(
            self.pattern_seed_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self._set_control_tooltip(
            self.randomize_seed_button,
            "Choose another saved seed. The same seed and coordinates produce "
            "the same assorted crops and random growth states.",
        )

        self.stem_spacing_label = _make_text(
            growth_card,
            "Blocks skipped between stems",
            point_size=9,
            bold=True,
        )
        growth_sizer.Add(
            self.stem_spacing_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        (
            self.stem_spacing_row,
            self.stem_spacing_slider,
            self.stem_spacing_box,
        ) = self._build_slider_row(growth_card, 1, 0, 2)
        self.stem_spacing_row_item = growth_sizer.Add(
            self.stem_spacing_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        content.Add(
            growth_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        water_card, water_sizer = self._create_card(
            self.settings_content_panel,
            "Irrigation",
            "Reuse existing water and add efficient sources only where safely needed.",
        )
        self.add_water_cb = ModernCheckBox(
            water_card,
            "Add water sources where safely needed",
            True,
        )
        self._set_control_tooltip(
            self.add_water_cb,
            "Detects existing hydration first, then places safe source blocks "
            "that cover the most remaining farmland. Water is never forced into "
            "an invalid or poorly surrounded position.",
        )
        _tighten_gap_before_checkbox(water_sizer)
        water_sizer.Add(
            self.add_water_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        water_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(water_sizer)
        self._water_options_transition_spacing = water_sizer.AddSpacer(
            UI_CHECKBOX_GROUP_TRANSITION_GAP
        )
        self.moisture_label, self.moisture_choice = self._build_labeled_choice(
            water_card,
            water_sizer,
            "Initial farmland moisture",
            (
                "Match planned irrigation",
                "Force dry",
                "Force fully hydrated",
            ),
            "Match planned irrigation writes moisture 7 only where existing or "
            "planned water covers the farmland. Forced moisture may later change normally in-game.",
        )
        self.water_cover_label, self.water_cover_choice = self._build_labeled_choice(
            water_card,
            water_sizer,
            "Water cover",
            ("Open Water", "Waterlogged Upper Slab"),
            "Choose open source water or cover each new source with a waterlogged upper slab.",
        )
        self.slab_type_label, self.slab_type_choice = self._build_labeled_choice(
            water_card,
            water_sizer,
            "Slab type",
            SLAB_CHOICES,
            "Select the upper slab placed over each new water source. The slab "
            "stores source water as an Amulet extra block layer.",
            icon_provider=self._slab_icon_cache,
            show_icons=True,
        )
        oak_index = self.slab_type_choice.FindString("Oak Slab")
        self.slab_type_choice.SetSelection(oak_index if oak_index != wx.NOT_FOUND else 0)
        self.show_slab_icons_cb = ModernCheckBox(
            water_card,
            "Show slab icons",
            True,
        )
        self._set_control_tooltip(
            self.show_slab_icons_cb,
            "Uses slab item textures from Amulet's local vanilla resource cache. "
            "Disable this option to use a compact text-only slab list.",
        )
        _tighten_gap_before_checkbox(water_sizer)
        water_sizer.Add(
            self.show_slab_icons_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        water_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        self._slab_icon_group_bottom_spacing = (
            _add_checkbox_group_bottom_spacing(water_sizer)
        )
        content.Add(
            water_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        files_card, files_sizer = self._create_card(
            self.settings_content_panel,
            "Plugin Files",
            "Manage local settings without affecting worlds or unrelated files.",
        )
        self.manage_plugin_files_button = ModernButton(
            files_card,
            "Manage Plugin Files...",
        )
        self._set_control_tooltip(
            self.manage_plugin_files_button,
            "Open folders, reset, repair, import, export, or delete the files "
            "owned by Auto Farmland.",
        )
        files_sizer.Add(
            self.manage_plugin_files_button,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        content.Add(
            files_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )
        content.AddSpacer(_dip(self.scroll, 2))

        settings_row.Add(self.scroll, 1, wx.EXPAND)
        self.settings_scrollbar = ModernScrollBar(
            settings_host,
            self.scroll,
            on_scrolled=self._on_settings_scroll,
        )
        settings_row.Add(
            self.settings_scrollbar,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT,
            _dip(settings_host, 4),
        )
        main_content_sizer.Add(settings_host, self.SETTINGS_GROW_PROPORTION, wx.EXPAND)

        footer = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(footer)
        footer.SetBackgroundColour(AUTO_FARMLAND_THEME["passive_window"])
        footer_sizer = wx.BoxSizer(wx.VERTICAL)
        footer.SetSizer(footer_sizer)

        status_card = RoundedPanel(
            footer,
            background=AUTO_FARMLAND_THEME["passive_surface_alt"],
        )
        status_sizer = wx.BoxSizer(wx.HORIZONTAL)
        status_card.SetSizer(status_sizer)
        status_caption = _make_text(
            status_card,
            "STATUS",
            point_size=8,
            bold=True,
            muted=True,
        )
        self.status = _make_text(status_card, "Ready", point_size=9)
        self._set_control_tooltip(
            self.status,
            "Shows the current operation state and the most recent result.",
        )
        status_sizer.Add(
            status_caption,
            0,
            wx.ALL | wx.ALIGN_CENTER_VERTICAL,
            _dip(status_card, 12),
        )
        status_sizer.Add(
            self.status,
            1,
            wx.TOP | wx.RIGHT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL,
            _dip(status_card, 12),
        )
        footer_sizer.Add(
            status_card,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            UI_FOOTER_MARGIN,
        )

        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.create_button = ModernButton(
            footer,
            "Create Farm",
            primary=True,
        )
        self.create_button.ProtectFromExternalDisable(True)
        action_row.Add(
            self.create_button,
            2,
            wx.RIGHT | wx.EXPAND,
            _dip(footer, 8),
        )

        self.save_report_button = ModernButton(footer, "Save Report")
        self.save_report_button.ProtectFromExternalDisable(True)
        self.save_report_button.SetAvailable(False)
        action_row.Add(
            self.save_report_button,
            1,
            wx.RIGHT | wx.EXPAND,
            _dip(footer, 8),
        )

        self.console_toggle_button = ModernButton(
            footer,
            "Hide Console",
            compact=True,
        )
        self.console_toggle_button.Bind(wx.EVT_BUTTON, self._toggle_console)
        action_row.Add(self.console_toggle_button, 1, wx.EXPAND)
        footer_sizer.Add(
            action_row,
            0,
            wx.ALL | wx.EXPAND,
            UI_FOOTER_MARGIN,
        )
        main_content_sizer.Add(footer, 0, wx.EXPAND)

        self.console_card = RoundedPanel(
            self._main_content_panel,
            background=AUTO_FARMLAND_THEME["console_bg"],
            border=AUTO_FARMLAND_THEME["border"],
            radius=12,
        )
        console_sizer = wx.BoxSizer(wx.VERTICAL)
        self.console_card.SetSizer(console_sizer)
        console_title = _make_text(
            self.console_card,
            "REPORT CONSOLE",
            point_size=8,
            bold=True,
            muted=True,
        )
        console_sizer.Add(
            console_title,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            _dip(self.console_card, 12),
        )
        self.text = wx.TextCtrl(
            self.console_card,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.BORDER_NONE,
            size=(-1, self.CONSOLE_MIN_TEXT_HEIGHT),
        )
        _mark_custom_ui_owned(self.text, self.CONSOLE_SEMANTIC_NAME)
        self.text.SetForegroundColour(AUTO_FARMLAND_THEME["console_text"])
        self.text.SetBackgroundColour(AUTO_FARMLAND_THEME["console_bg"])
        try:
            wx.CallAfter(_try_apply_dark_native_theme, self.text)
        except Exception:
            pass
        try:
            font = wx.Font(
                9,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
            self.text.SetFont(font)
        except Exception:
            pass
        self.text.SetMinSize(
            (
                _dip(self.console_card, 340),
                _dip(self.console_card, self.CONSOLE_MIN_TEXT_HEIGHT),
            )
        )
        self.console_card.SetMinSize(
            (-1, _dip(root, self.CONSOLE_MIN_CARD_HEIGHT))
        )
        console_sizer.Add(
            self.text,
            1,
            wx.ALL | wx.EXPAND,
            _dip(self.console_card, 12),
        )
        main_content_sizer.Add(
            self.console_card,
            self.CONSOLE_GROW_PROPORTION,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_FOOTER_MARGIN,
        )

        self._bind_slider_and_text(self.growth_slider, self.growth_box, 0, 7)

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

        for control in (
            self.replace_grass_cb,
            self.replace_plants_cb,
            self.skip_isolated_raised_cb,
            self.add_water_cb,
            self.show_crop_icons_cb,
            self.show_slab_icons_cb,
        ):
            control.Bind(wx.EVT_CHECKBOX, self._on_ui_setting_changed)
        for control in (
            self.raised_support_choice,
            self.crop_layout_choice,
            self.single_crop_choice,
            self.growth_mode_choice,
            self.row_direction_choice,
            self.moisture_choice,
            self.water_cover_choice,
            self.slab_type_choice,
        ):
            control.Bind(wx.EVT_CHOICE, self._on_ui_setting_changed)
        for crop_control in self._selected_crop_controls():
            crop_control[1].Bind(wx.EVT_CHECKBOX, self._on_ui_setting_changed)

        self.growth_slider.Bind(wx.EVT_SLIDER, self._on_growth_changed)
        self.growth_box.Bind(wx.EVT_TEXT, self._on_growth_text_changed)
        self.random_growth_min_slider.Bind(wx.EVT_SLIDER, self._on_random_growth_changed)
        self.random_growth_min_box.Bind(wx.EVT_TEXT, self._on_random_growth_changed)
        self.random_growth_max_slider.Bind(wx.EVT_SLIDER, self._on_random_growth_changed)
        self.random_growth_max_box.Bind(wx.EVT_TEXT, self._on_random_growth_changed)
        self.randomize_seed_button.Bind(wx.EVT_BUTTON, self._randomize_pattern_seed)
        self.create_button.Bind(wx.EVT_BUTTON, self._run_operation)
        self.manage_plugin_files_button.Bind(wx.EVT_BUTTON, self._manage_plugin_files)
        self.save_report_button.Bind(wx.EVT_BUTTON, self._save_last_report)

        for target in (console_title, self.console_card, self.text):
            target.Bind(wx.EVT_ENTER_WINDOW, self._on_console_help_enter)
            target.Bind(wx.EVT_LEAVE_WINDOW, self._on_console_help_leave)
        for event_binder in (
            wx.EVT_LEFT_DOWN,
            wx.EVT_SET_FOCUS,
            wx.EVT_KEY_DOWN,
        ):
            self.text.Bind(event_binder, self._on_console_text_interaction)

        self._update_floating_minimum_size(resize_if_needed=True)

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(root, 1, wx.EXPAND)
        self._plugin_window.SetSizer(frame_sizer)
        self._plugin_window.Layout()
        self._sync_main_content_width()
        self._bind_floating_window_geometry_events()
        self._sync_settings_viewport()

    def _show_plugin_window(self, _event=None):
        window = self._plugin_window
        if window is None or self._destroying:
            return
        try:
            if window.IsIconized():
                window.Iconize(False)
            if not self._window_has_been_shown:
                self._position_plugin_window_at_amulet_edge()
                self._window_has_been_shown = True
            if not window.IsShown():
                window.Show(True)
            window.Raise()
            window.SetFocus()
            self._update_launcher_status()
            try:
                window.Layout()
                window.Refresh(False)
                window.Update()
            except Exception:
                pass
            try:
                wx.CallAfter(self._refresh_scrolled_custom_controls)
                wx.CallLater(75, self._refresh_scrolled_custom_controls)
            except Exception:
                pass
        except Exception:
            pass

    def _position_plugin_window_at_amulet_edge(self):
        window = self._plugin_window
        if window is None:
            return
        try:
            owner = wx.GetTopLevelParent(self)
            owner_rect = owner.GetScreenRect()
            size = window.GetSize()
            display_index = wx.Display.GetFromWindow(owner)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work = wx.Display(display_index).GetClientArea()
            x = owner_rect.x - int(round(size.width / 2.0))
            y = owner_rect.y + int(round((owner_rect.height - size.height) / 2.0))
            x = min(max(x, work.x), max(work.x, work.right - size.width))
            y = min(max(y, work.y), max(work.y, work.bottom - size.height))
            window.SetPosition((x, y))
        except Exception:
            try:
                window.CenterOnParent()
            except Exception:
                pass

    def _update_launcher_status(self):
        window = self._plugin_window
        shown = bool(window is not None and window.IsShown())
        self.launcher_status.SetLabel("Status: Open" if shown else "Status: Closed")
        self.open_window_button.SetLabel("Focus Window" if shown else "Open Window")
        try:
            self.Layout()
        except Exception:
            pass

    def _bind_floating_window_geometry_events(self):
        self._plugin_window.Bind(wx.EVT_SIZE, self._on_plugin_window_size)

    def _on_plugin_window_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        self._sync_settings_viewport()
        if not self._settings_ready:
            return
        try:
            if self._plugin_window.IsMaximized() or self._plugin_window.IsIconized():
                return
        except Exception:
            pass
        self._schedule_settings_save()

    def _current_window_size_config(self):
        try:
            if self._plugin_window.IsMaximized() or self._plugin_window.IsIconized():
                return list(FLOATING_DEFAULT_SIZE)
            size = self._plugin_window.GetSize()
            return [int(size.width), int(size.height)]
        except Exception:
            return list(FLOATING_DEFAULT_SIZE)

    def _current_manage_dialog_size_config(self):
        return [int(self._manage_dialog_size[0]), int(self._manage_dialog_size[1])]

    def _remember_manage_dialog_size(self, dialog):
        try:
            size = dialog.GetSize()
            self._manage_dialog_size = (int(size.width), int(size.height))
            if self._settings_ready:
                self._schedule_settings_save()
        except Exception:
            pass

    def _apply_saved_ui_data(self, data):
        ui = data.get("ui", {}) if isinstance(data, Mapping) else {}
        if not isinstance(ui, Mapping):
            ui = {}

        console_visible = ui.get("console_visible")
        if isinstance(console_visible, bool):
            self._console_visible = console_visible
        self.console_card.Show(self._console_visible)
        self.console_toggle_button.SetLabel(
            "Hide Console" if self._console_visible else "Show Console"
        )
        self._update_floating_minimum_size(
            resize_if_needed=self._console_visible
        )

        size = ui.get("window_size")
        if (
            isinstance(size, (list, tuple))
            and len(size) == 2
            and all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in size
            )
        ):
            minimum_width, minimum_height = (
                self._current_floating_minimum_size()
            )
            width = max(minimum_width, int(size[0]))
            height = max(minimum_height, int(size[1]))
            try:
                display_index = wx.Display.GetFromWindow(self._plugin_window)
                if display_index == wx.NOT_FOUND:
                    display_index = 0
                work = wx.Display(display_index).GetClientArea()
                width = min(width, max(minimum_width, work.width))
                height = min(height, max(minimum_height, work.height))
            except Exception:
                pass
            self._plugin_window.SetSize((width, height))

        manage_size = ui.get("manage_window_size")
        if (
            isinstance(manage_size, (list, tuple))
            and len(manage_size) == 2
            and all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in manage_size
            )
        ):
            self._manage_dialog_size = (
                max(MANAGE_DIALOG_MIN_SIZE[0], int(manage_size[0])),
                max(MANAGE_DIALOG_MIN_SIZE[1], int(manage_size[1])),
            )

        self._refresh_floating_layout()

    def _toggle_console(self, _event=None):
        self._console_visible = not self._console_visible
        self.console_card.Show(self._console_visible)
        self.console_toggle_button.SetLabel(
            "Hide Console" if self._console_visible else "Show Console"
        )
        self._hide_console_help()
        self._update_floating_minimum_size(resize_if_needed=self._console_visible)
        self._refresh_floating_layout()
        self._schedule_settings_save()

    def _current_floating_minimum_size(self):
        minimum_height = (
            self.FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT
            if self._console_visible
            else FLOATING_MIN_SIZE[1]
        )
        return FLOATING_MIN_SIZE[0], minimum_height

    def _update_floating_minimum_size(self, resize_if_needed=False):
        window = self._plugin_window
        if window is None:
            return
        minimum_width, minimum_height = self._current_floating_minimum_size()
        try:
            window.SetMinSize(
                (_dip(window, minimum_width), _dip(window, minimum_height))
            )
        except Exception:
            return
        if not resize_if_needed:
            return
        try:
            if window.IsIconized() or window.IsMaximized():
                return
            size = window.GetSize()
            width = max(int(size.width), _dip(window, minimum_width))
            height = max(int(size.height), _dip(window, minimum_height))
            if width != size.width or height != size.height:
                window.SetSize((width, height))
        except Exception:
            pass

    def _on_settings_scroll(self):
        self._refresh_scrolled_custom_controls()

    def _refresh_scrolled_custom_controls(self):
        try:
            self.settings_content_panel.Refresh(False)
        except Exception:
            pass

    def _sync_settings_viewport(self):
        try:
            self.scroll._modern_sync_layout()
        except Exception:
            pass
        try:
            self.settings_scrollbar._bind_wheel_tree(self.scroll)
            self.settings_scrollbar.sync()
        except Exception:
            pass

    def _refresh_floating_layout(self):
        self._sync_settings_viewport()
        try:
            self._plugin_window.Layout()
            self._plugin_window.Refresh(False)
        except Exception:
            pass

    def _tooltip_targets(self, control):
        targets = [control]
        try:
            targets.extend(control.GetChildren())
        except Exception:
            pass
        return targets

    def _set_control_tooltip(self, control, text):
        if control is None or not text:
            return
        anchor_ref = weakref.ref(control)
        for target in self._tooltip_targets(control):
            try:
                target.Bind(
                    wx.EVT_ENTER_WINDOW,
                    lambda event, ref=anchor_ref, help_text=str(text): self._on_control_help_enter(
                        event, ref, help_text
                    ),
                )
                target.Bind(
                    wx.EVT_LEAVE_WINDOW,
                    lambda event, ref=anchor_ref: self._on_control_help_leave(event, ref),
                )
                target.Bind(wx.EVT_LEFT_DOWN, self._hide_control_help_event)
                target.Bind(wx.EVT_SET_FOCUS, self._hide_control_help_event)
            except Exception:
                pass

    def _hide_control_help_event(self, event):
        self._hide_control_help()
        try:
            event.Skip()
        except Exception:
            pass

    def _cancel_control_help(self):
        pending = self._control_help_call
        self._control_help_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _hide_control_help(self, clear_anchor=True):
        self._cancel_control_help()
        window = self._control_help_window
        if window is not None:
            try:
                window.dismiss()
            except Exception:
                pass
        if clear_anchor:
            self._control_help_anchor_ref = None
            self._control_help_text = ""

    def _on_control_help_enter(self, event, anchor_ref, text):
        try:
            event.Skip()
        except Exception:
            pass

        if (
            getattr(self, "_tooltips_suspended", False)
            or getattr(self, "_operation_running", False)
            or getattr(self, "_destroying", False)
        ):
            self._hide_control_help()
            return

        try:
            anchor = anchor_ref()
        except Exception:
            anchor = None
        if anchor is None:
            return

        try:
            current_anchor = (
                self._control_help_anchor_ref()
                if self._control_help_anchor_ref is not None
                else None
            )
        except Exception:
            current_anchor = None

        same_tip = (
            current_anchor is anchor
            and self._control_help_text == str(text)
        )
        if same_tip:
            try:
                if self._control_help_call is not None or (
                    self._control_help_window is not None
                    and self._control_help_window.IsShown()
                ):
                    return
            except Exception:
                pass

        self._hide_control_help()
        self._control_help_anchor_ref = anchor_ref
        self._control_help_text = str(text)
        try:
            self._control_help_call = wx.CallLater(
                self.CONTROL_TOOLTIP_DELAY_MS,
                self._show_control_help,
            )
        except Exception:
            self._control_help_call = None

    def _on_control_help_leave(self, event, anchor_ref):
        try:
            event.Skip()
        except Exception:
            pass

        try:
            wx.CallAfter(
                self._hide_control_help_if_pointer_left,
                anchor_ref,
            )
        except Exception:
            self._hide_control_help_if_pointer_left(anchor_ref)

    def _hide_control_help_if_pointer_left(self, anchor_ref):
        try:
            current_anchor = (
                self._control_help_anchor_ref()
                if self._control_help_anchor_ref is not None
                else None
            )
        except Exception:
            current_anchor = None
        try:
            leaving_anchor = anchor_ref()
        except Exception:
            leaving_anchor = None

        if current_anchor is not leaving_anchor:
            return

        try:
            if (
                leaving_anchor is not None
                and leaving_anchor.IsShownOnScreen()
                and leaving_anchor.GetScreenRect().Contains(
                    wx.GetMousePosition()
                )
            ):
                return
        except Exception:
            pass

        self._hide_control_help()

    def _show_control_help(self):
        self._control_help_call = None
        if (
            getattr(self, "_tooltips_suspended", False)
            or getattr(self, "_operation_running", False)
            or getattr(self, "_destroying", False)
        ):
            self._hide_control_help()
            return

        try:
            anchor = (
                self._control_help_anchor_ref()
                if self._control_help_anchor_ref is not None
                else None
            )
        except Exception:
            anchor = None
        if anchor is None or not self._control_help_text:
            return

        try:
            if not anchor.IsShownOnScreen():
                return
            if not anchor.GetScreenRect().Contains(wx.GetMousePosition()):
                return
            if wx.GetMouseState().LeftIsDown():

                self._control_help_call = wx.CallLater(
                    120,
                    self._show_control_help,
                )
                return
        except Exception:
            return

        if self._control_help_window is None:
            try:
                owner = getattr(self, "_plugin_window", None)
                if owner is None:
                    owner = self.GetTopLevelParent()
                self._control_help_window = CursorControlHint(owner)
            except Exception:
                self._control_help_window = None
                return

        try:
            self._control_help_window.set_text(self._control_help_text)
            self._control_help_window.show_at_pointer(anchor)
        except Exception:
            pass

    def _cancel_console_help(self):
        pending = self._console_help_call
        self._console_help_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _hide_console_help(self):
        self._cancel_console_help()
        if self._console_help_window is not None:
            try:
                self._console_help_window.dismiss()
            except Exception:
                pass

    def _on_console_help_enter(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        if (
            getattr(self, "_tooltips_suspended", False)
            or getattr(self, "_operation_running", False)
            or getattr(self, "_destroying", False)
        ):
            self._console_help_hovered = False
            self._hide_console_help()
            return
        self._console_help_hovered = True
        self._cancel_console_help()
        try:
            self._console_help_call = wx.CallLater(
                self.CONSOLE_TOOLTIP_DELAY_MS,
                self._show_console_help,
            )
        except Exception:
            self._console_help_call = None

    def _on_console_help_leave(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        try:
            if self.console_card.GetScreenRect().Contains(wx.GetMousePosition()):
                return
        except Exception:
            pass
        self._console_help_hovered = False
        self._hide_console_help()

    def _on_console_text_interaction(self, event):
        self._console_help_hovered = False
        self._hide_console_help()
        try:
            event.Skip()
        except Exception:
            pass

    def _show_console_help(self):
        self._console_help_call = None
        if (
            getattr(self, "_tooltips_suspended", False)
            or getattr(self, "_operation_running", False)
            or getattr(self, "_destroying", False)
            or not self._console_help_hovered
            or not self._console_visible
        ):
            self._hide_console_help()
            return
        try:
            if self.text.HasFocus() or wx.GetMouseState().LeftIsDown():
                return
        except Exception:
            pass
        if self._console_help_window is None:
            try:
                self._console_help_window = AnchoredConsoleHint(
                    self._plugin_window,
                    self._console_help_text,
                )
            except Exception:
                self._console_help_window = None
                return
        try:
            self._console_help_window.show_for(self.console_card)
        except Exception:
            pass

    def _begin_operation_ui(self):
        self._console_help_hovered = False
        self._hide_control_help()
        self._hide_console_help()
        self._operation_running = True
        self.create_button.SetBusy(True)
        self.create_button.SetLabel("Creating Farm...")

    def _finish_operation_ui(self):
        self._operation_running = False
        self.create_button.SetBusy(False)
        self.create_button.SetAvailable(True)
        self.create_button.SetLabel("Create Farm")
        self._schedule_operation_button_restore()

    def _schedule_operation_button_restore(self):
        pending = self._operation_button_restore_call
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass
        self._operation_button_restore_call = wx.CallLater(
            120,
            self._settle_operation_buttons,
            0,
        )

    def _settle_operation_buttons(self, pass_index=0):
        self._operation_button_restore_call = None
        if self._operation_running or self._destroying:
            return
        self.create_button.SetBusy(False)
        self.create_button.SetAvailable(True)
        self.create_button.SetLabel("Create Farm")
        if pass_index < 4:
            self._operation_button_restore_call = wx.CallLater(
                120,
                self._settle_operation_buttons,
                pass_index + 1,
            )

    def _on_host_destroy(self, event):
        try:
            if event.GetEventObject() is not self:
                event.Skip()
                return
        except Exception:
            pass
        self._destroying = True
        self._stop_pending_settings_save()
        self._hide_control_help()
        self._hide_console_help()
        for pending_name in ("_operation_button_restore_call",):
            pending = getattr(self, pending_name, None)
            setattr(self, pending_name, None)
            if pending is not None:
                try:
                    pending.Stop()
                except Exception:
                    pass
        try:
            self._write_settings_config(create_if_missing=True)
        except Exception:
            pass
        for help_name in ("_control_help_window", "_console_help_window"):
            window = getattr(self, help_name, None)
            setattr(self, help_name, None)
            if window is not None:
                try:
                    window.Destroy()
                except Exception:
                    pass
        window = self._plugin_window
        self._plugin_window = None
        if window is not None:
            window.destroy_for_host()
        event.Skip()

    def bind_events(self):
        super().bind_events()
        self._selection.bind_events()
        self._selection.enable()

    def enable(self):
        self._selection.enable()

    def _settings_registry(self) -> Mapping[str, wx.Window]:
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
            "show_crop_previews": self.show_crop_icons_cb,
            "show_slab_icons": self.show_slab_icons_cb,
        }

    @staticmethod
    def _control_value(control):
        if isinstance(control, (ModernCheckBox, CropToggleTile, wx.CheckBox)):
            return bool(control.GetValue())
        if isinstance(control, (ModernChoice, CropExclusiveSelector, wx.Choice)):
            return str(control.GetStringSelection())
        if isinstance(control, (ModernSlider, wx.Slider)):
            return int(control.GetValue())
        raise TypeError(f"Unsupported settings control: {type(control).__name__}")

    @staticmethod
    def _setting_value_is_valid(control, value) -> bool:
        if isinstance(control, (ModernCheckBox, CropToggleTile, wx.CheckBox)):
            return isinstance(value, bool)
        if isinstance(control, (ModernChoice, CropExclusiveSelector, wx.Choice)):
            return isinstance(value, str) and control.FindString(value) != wx.NOT_FOUND
        if isinstance(control, (ModernSlider, wx.Slider)):
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and control.GetMin() <= value <= control.GetMax()
            )
        return False

    @classmethod
    def _set_control_value(cls, control, value) -> bool:
        if not cls._setting_value_is_valid(control, value):
            return False
        try:
            if isinstance(control, (ModernCheckBox, CropToggleTile, wx.CheckBox)):
                control.SetValue(value)
                return True
            if isinstance(control, (ModernChoice, CropExclusiveSelector, wx.Choice)):
                control.SetSelection(control.FindString(value))
                return True
            if isinstance(control, (ModernSlider, wx.Slider)):
                control.SetValue(value)
                return True
        except Exception:
            return False
        return False

    def _capture_settings(self) -> Dict[str, object]:
        data = {
            key: self._control_value(control)
            for key, control in self._settings_registry().items()
        }
        data["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        data["plugin"] = "Auto Farmland"
        data["ui"] = {
            "window_size": self._current_window_size_config(),
            "manage_window_size": self._current_manage_dialog_size_config(),
            "console_visible": bool(self._console_visible),
        }
        return data

    def _apply_settings_data(self, data: Mapping[str, object]) -> None:
        if not isinstance(data, Mapping):
            return
        data = self._migrate_legacy_settings_data(data)
        self._settings_config_applying = True
        try:
            for key, control in self._settings_registry().items():
                if key in data:
                    self._set_control_value(control, data[key])
            self.growth_box.ChangeValue(str(self.growth_slider.GetValue()))
            self.random_growth_min_box.ChangeValue(str(self.random_growth_min_slider.GetValue()))
            self.random_growth_max_box.ChangeValue(str(self.random_growth_max_slider.GetValue()))
            self.pattern_seed_box.ChangeValue(str(self.pattern_seed_slider.GetValue()))
            self.stem_spacing_box.ChangeValue(str(self.stem_spacing_slider.GetValue()))
            self._apply_saved_ui_data(data)
        finally:
            self._settings_config_applying = False
        self._update_ui_visibility()
        self._update_growth_description()
        self._refresh_floating_layout()

    def _normalize_settings_config_data(
        self,
        data: Optional[Mapping[str, object]],
        *,
        add_missing_defaults: bool,
    ) -> Dict[str, object]:
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

        ui = normalized.get("ui")
        ui = dict(ui) if isinstance(ui, Mapping) else {}
        default_ui = defaults.get("ui", {}) if isinstance(defaults, Mapping) else {}
        for size_key, minimum, fallback in (
            ("window_size", FLOATING_MIN_SIZE, FLOATING_DEFAULT_SIZE),
            ("manage_window_size", MANAGE_DIALOG_MIN_SIZE, MANAGE_DIALOG_DEFAULT_SIZE),
        ):
            value = ui.get(size_key)
            valid = (
                isinstance(value, (list, tuple))
                and len(value) == 2
                and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
                and value[0] >= minimum[0]
                and value[1] >= minimum[1]
            )
            if not valid:
                default_value = (
                    default_ui.get(size_key)
                    if isinstance(default_ui, Mapping)
                    else None
                )
                if (
                    isinstance(default_value, (list, tuple))
                    and len(default_value) == 2
                ):
                    ui[size_key] = list(default_value)
                elif add_missing_defaults:
                    ui[size_key] = list(fallback)
                else:
                    ui.pop(size_key, None)
        if not isinstance(ui.get("console_visible"), bool):
            if add_missing_defaults:
                ui["console_visible"] = bool(
                    default_ui.get("console_visible", True)
                    if isinstance(default_ui, Mapping)
                    else True
                )
            else:
                ui.pop("console_visible", None)
        normalized["ui"] = ui
        normalized["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        normalized["plugin"] = "Auto Farmland"
        return normalized

    def _initialize_settings_persistence(self) -> None:
        self._settings_defaults = self._capture_settings()
        path = self._settings_config_path()
        if not path.is_file():
            self._settings_config_unknown_data = {}
            self._settings_ready = True
            self._write_settings_config(create_if_missing=True)
            return
        loaded = self._load_settings_config_data(path)
        if loaded is None:
            self._log(
                "Settings warning: Auto Farmland.config could not be loaded; "
                "current defaults are active. Reason: "
                f"{self._settings_config_load_error or 'Unknown error'}"
            )
            self._settings_ready = True
            return
        normalized = self._normalize_settings_config_data(
            loaded,
            add_missing_defaults=True,
        )
        self._settings_config_unknown_data = dict(normalized)
        self._apply_settings_data(normalized)
        self._settings_ready = True
        self._write_settings_config(create_if_missing=False)

    def _schedule_settings_save(self, event=None) -> None:
        try:
            if event is not None:
                event.Skip()
        except Exception:
            pass
        if self._settings_config_applying or not self._settings_ready:
            return
        self._stop_pending_settings_save()
        self._settings_config_save_call = wx.CallLater(
            self.SETTINGS_SAVE_DELAY_MS,
            self._write_settings_config,
        )

    def _show_plugin_file_action_dialog(
        self,
        actions: Sequence[Tuple[str, str]],
    ) -> Optional[int]:
        parent = self._plugin_window or wx.GetTopLevelParent(self) or self
        dialog = DarkActionPickerDialog(
            parent,
            actions,
            initial_size=self._current_manage_dialog_size_config(),
            on_size_changed=self._remember_manage_dialog_size,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            selection = dialog.GetSelection()
            return selection if selection != wx.NOT_FOUND else None
        finally:
            self._remember_manage_dialog_size(dialog)
            dialog.Destroy()
    def _settings_config_path(self) -> Path:
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
        return Path(__file__).resolve().parent

    @staticmethod
    def _migrate_legacy_settings_data(
        data: Mapping[str, object],
    ) -> Dict[str, object]:
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

    def _load_settings_config_data(
        self,
        path: Optional[Path] = None,
    ) -> Optional[Dict[str, object]]:
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

    def _merge_settings_config_data(
        self,
        existing: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
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

    def _write_settings_config(self, create_if_missing: bool = True) -> bool:
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
        try:
            if self._settings_config_save_call is not None:
                self._settings_config_save_call.Stop()
        except Exception:
            pass
        self._settings_config_save_call = None

    def _reset_settings_to_defaults(self) -> bool:
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
        return self._normalize_settings_config_data(
            recovered,
            add_missing_defaults=True,
        )

    def _repair_existing_settings_config(self) -> None:
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

    def _manage_plugin_files(self, _event) -> None:
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

    def _bind_slider_and_text(self, slider, text_box, minimum, maximum) -> None:
        def on_slider(event):
            text_box.ChangeValue(str(slider.GetValue()))
            self._schedule_settings_save(event)

        def on_text(event):
            try:
                value = int(text_box.GetValue())
                slider.SetValue(max(minimum, min(maximum, value)))
            except (TypeError, ValueError):
                pass
            self._schedule_settings_save(event)

        slider.Bind(wx.EVT_SLIDER, on_slider)
        text_box.Bind(wx.EVT_TEXT, on_text)

    def _on_ui_setting_changed(self, event) -> None:
        self._update_ui_visibility()
        self._update_growth_description()
        self._schedule_settings_save(event)

    def _on_growth_changed(self, event) -> None:
        self.growth_box.ChangeValue(str(self.growth_slider.GetValue()))
        self._update_growth_description()
        self._schedule_settings_save(event)

    def _on_growth_text_changed(self, event) -> None:
        try:
            value = int(self.growth_box.GetValue())
            self.growth_slider.SetValue(max(0, min(7, value)))
        except (TypeError, ValueError):
            pass
        self._update_growth_description()
        self._schedule_settings_save(event)

    def _on_random_growth_changed(self, event) -> None:
        try:
            source = event.GetEventObject()
        except Exception:
            source = None

        pairs = (
            (self.random_growth_min_slider, self.random_growth_min_box),
            (self.random_growth_max_slider, self.random_growth_max_box),
        )
        for slider, text_box in pairs:
            if source is slider:
                text_box.ChangeValue(str(slider.GetValue()))
                break
            if source is text_box or source is getattr(text_box, "_text", None):
                try:
                    value = int(text_box.GetValue())
                    slider.SetValue(max(0, min(7, value)))
                except (TypeError, ValueError):
                    pass
                break

        self._update_growth_description()
        self._schedule_settings_save(event)

    def _randomize_pattern_seed(self, event) -> None:
        seed = int(datetime.now().timestamp() * 1_000_000) % (PATTERN_SEED_MAX + 1)
        self.pattern_seed_slider.SetValue(seed)
        self.pattern_seed_box.ChangeValue(str(seed))
        self._schedule_settings_save(event)

    def _update_crop_previews(self) -> None:
        layout = self.crop_layout_choice.GetStringSelection()
        growth_mode = self.growth_mode_choice.GetStringSelection()
        standard_layout = layout in {
            "Single Crop",
            "Alternating Crop Rows",
            "Assorted Crops",
        }
        random_mode = standard_layout and growth_mode == "Random growth range"
        if random_mode:
            low, high = sorted(
                (
                    int(self.random_growth_min_slider.GetValue()),
                    int(self.random_growth_max_slider.GetValue()),
                )
            )
        else:
            low = high = int(self.growth_slider.GetValue())
        show_icons = bool(self.show_crop_icons_cb.GetValue())
        self.single_crop_choice.SetPreviewStates(low, high, random_mode)
        self.single_crop_choice.SetShowIcons(show_icons)
        for _crop, control in self._selected_crop_controls():
            control.SetPreviewStates(low, high, random_mode)
            control.SetShowIcons(show_icons)
        stem_crop = layout if layout in STEM_CROPS else "Melon Stem"
        self.stem_preview.SetLabel(stem_crop)
        self.stem_preview.SetPreviewStates(low, high, False)
        self.stem_preview.SetShowIcons(show_icons)

    def _update_growth_description(self) -> None:
        value = int(self.growth_slider.GetValue())
        description = GROWTH_DESCRIPTIONS.get(value, "Unknown")
        self.growth_description.SetLabel(f"State {value} of 7 - {description}")
        minimum = int(self.random_growth_min_slider.GetValue())
        maximum = int(self.random_growth_max_slider.GetValue())
        low, high = sorted((minimum, maximum))
        self.growth_range_description.SetLabel(
            f"Random range: state {low} through state {high}"
        )
        self._update_crop_previews()

    def _selected_crop_controls(self) -> Tuple[Tuple[str, CropToggleTile], ...]:
        return (
            ("Wheat", self.crop_wheat_cb),
            ("Carrots", self.crop_carrots_cb),
            ("Potatoes", self.crop_potatoes_cb),
            ("Beetroot", self.crop_beetroot_cb),
        )

    def _update_ui_visibility(self) -> None:
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
        random_growth = standard_layout and growth_mode == "Random growth range"
        fixed_growth = stem_mode or (standard_layout and not random_growth)
        seed_needed = layout == "Assorted Crops" or random_growth
        add_water = bool(self.add_water_cb.GetValue())

        _set_wrapped_text(
            self.placement_explanation,
            "Eligible grass blocks are replaced with farmland at their current position."
            if replace_mode
            else (
                "Farmland is placed one block above safe exposed surfaces. "
                "Existing support blocks remain unchanged."
            ),
        )
        _set_window_sizer_item_visible(
            self.raised_support_label,
            not replace_mode,
        )
        _set_window_sizer_item_visible(
            self.raised_support_choice,
            not replace_mode,
        )
        _set_window_sizer_item_visible(
            self.skip_isolated_raised_cb,
            not replace_mode,
        )

        _set_window_sizer_item_visible(
            self.single_crop_label,
            layout == "Single Crop",
        )
        _set_window_sizer_item_visible(
            self.single_crop_choice,
            layout == "Single Crop",
        )
        _set_window_sizer_item_visible(
            self.selected_crops_label,
            multi_crop_layout,
        )
        _set_window_sizer_item_visible(
            self.selected_crops_panel,
            multi_crop_layout,
        )
        _set_window_sizer_item_visible(
            self.stem_preview_label,
            stem_mode,
        )
        _set_window_sizer_item_visible(
            self.stem_preview,
            stem_mode,
        )
        _set_window_sizer_item_visible(
            self.row_direction_label,
            row_mode,
        )
        _set_window_sizer_item_visible(
            self.row_direction_choice,
            row_mode,
        )

        _set_window_sizer_item_visible(
            self.growth_mode_label,
            standard_layout,
        )
        _set_window_sizer_item_visible(
            self.growth_mode_choice,
            standard_layout,
        )
        _set_window_sizer_item_visible(
            self.growth_label,
            fixed_growth,
        )
        _set_window_sizer_item_visible(
            self.growth_slider,
            fixed_growth,
        )
        _set_window_sizer_item_visible(
            self.growth_box,
            fixed_growth,
        )
        _set_window_sizer_item_visible(
            self.growth_description,
            fixed_growth,
        )
        _set_sizer_item_visible(self.growth_row_item, fixed_growth)

        _set_window_sizer_item_visible(
            self.random_growth_min_label,
            random_growth,
        )
        _set_window_sizer_item_visible(
            self.random_growth_min_slider,
            random_growth,
        )
        _set_window_sizer_item_visible(
            self.random_growth_min_box,
            random_growth,
        )
        _set_sizer_item_visible(
            self.random_growth_min_row_item,
            random_growth,
        )
        _set_window_sizer_item_visible(
            self.random_growth_max_label,
            random_growth,
        )
        _set_window_sizer_item_visible(
            self.random_growth_max_slider,
            random_growth,
        )
        _set_window_sizer_item_visible(
            self.random_growth_max_box,
            random_growth,
        )
        _set_sizer_item_visible(
            self.random_growth_max_row_item,
            random_growth,
        )
        _set_window_sizer_item_visible(
            self.growth_range_description,
            random_growth,
        )

        _set_window_sizer_item_visible(
            self.pattern_seed_label,
            seed_needed,
        )
        _set_window_sizer_item_visible(
            self.pattern_seed_slider,
            seed_needed,
        )
        _set_window_sizer_item_visible(
            self.pattern_seed_box,
            seed_needed,
        )
        _set_window_sizer_item_visible(
            self.randomize_seed_button,
            seed_needed,
        )
        _set_sizer_item_visible(
            self.pattern_seed_row_item,
            seed_needed,
        )
        _set_window_sizer_item_visible(
            self.stem_spacing_label,
            stem_mode,
        )
        _set_window_sizer_item_visible(
            self.stem_spacing_slider,
            stem_mode,
        )
        _set_window_sizer_item_visible(
            self.stem_spacing_box,
            stem_mode,
        )
        _set_sizer_item_visible(
            self.stem_spacing_row_item,
            stem_mode,
        )

        slab_cover = (
            add_water
            and self.water_cover_choice.GetStringSelection()
            == "Waterlogged Upper Slab"
        )
        _set_sizer_item_visible(
            self._water_options_transition_spacing,
            add_water,
        )
        _set_window_sizer_item_visible(self.moisture_label, add_water)
        _set_window_sizer_item_visible(self.moisture_choice, add_water)
        _set_window_sizer_item_visible(self.water_cover_label, add_water)
        _set_window_sizer_item_visible(self.water_cover_choice, add_water)
        _set_window_sizer_item_visible(self.slab_type_label, slab_cover)
        _set_window_sizer_item_visible(self.slab_type_choice, slab_cover)
        _set_window_sizer_item_visible(self.show_slab_icons_cb, slab_cover)
        _set_checkbox_group_bottom_spacing_visible(
            self._slab_icon_group_bottom_spacing,
            slab_cover,
        )
        try:
            self.slab_type_choice.SetShowIcons(
                self.show_slab_icons_cb.GetValue()
            )
        except Exception:
            pass
        self._update_crop_previews()
        self._refresh_floating_layout()

    def _clear_log(self) -> None:
        self._report_lines = []
        self._last_report_text = ""
        self.save_report_button.Enable(False)
        try:
            self.text.SetValue("")
        except Exception:
            pass

    def _append_log_text(self, message: str) -> None:
        try:
            self.text.AppendText(str(message) + "\n")
        except Exception:
            pass

    def _log(self, message: object = "") -> None:
        text = str(message)
        print(text)
        self._report_lines.append(text)
        try:
            wx.CallAfter(self._append_log_text, text)
        except Exception:
            self._append_log_text(text)

    def _log_section(self, title: str, rows: Iterable[Tuple[str, object]]) -> None:
        self._log("")
        self._log(title)
        for label, value in rows:
            self._log(f"{label}: {value}")

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.2f} seconds"
        minutes = int(seconds // 60)
        remaining = seconds - minutes * 60
        return f"{minutes} minute(s), {remaining:.2f} seconds"

    def _finalize_report(self) -> None:
        self._last_report_text = "\n".join(self._report_lines).strip()
        self.save_report_button.Enable(bool(self._last_report_text))

    def _save_last_report(self, _event) -> None:
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

    @staticmethod
    def _normalize_box_tuple(box) -> BoxTuple:
        if isinstance(box, tuple) and len(box) == 6:
            return tuple(int(value) for value in box)
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
        return sum((box[1] - box[0]) * (box[5] - box[4]) for box in boxes)

    @staticmethod
    def _merge_intervals(intervals: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
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
        for min_y, max_y in sorted(intervals, reverse=True):
            for y in range(max_y - 1, min_y - 1, -1):
                yield y

    @staticmethod
    def _tag_value(value):
        for attribute in ("py_data", "value"):
            try:
                return getattr(value, attribute)
            except Exception:
                pass
        return value

    @classmethod
    def _state_bool(cls, value) -> Optional[bool]:
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
        return block.base_name in AIR_NAMES

    @staticmethod
    def _block_layers(block: Block):
        yield block
        for extra in getattr(block, "extra_blocks", ()) or ():
            yield extra

    def _block_contains_water(self, block: Block) -> bool:
        return any(layer.base_name in WATER_NAMES for layer in self._block_layers(block))

    def _is_replaceable_plant(self, block: Block) -> bool:
        return block.base_name in REPLACEABLE_DECORATIVE_PLANTS

    @staticmethod
    def _is_missing_chunk_error(exc: Exception) -> bool:
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

    @staticmethod
    def _farmland_block(moisture: int) -> Block:
        return Block(
            "minecraft",
            "farmland",
            {"moisturized_amount": TAG_Int(int(moisture))},
        )

    @staticmethod
    def _crop_block(crop: str, growth: int) -> Block:
        base_name = CROP_BLOCK_NAMES[crop]
        properties = {"growth": TAG_Int(int(growth))}
        if crop in STEM_CROPS:
            properties["facing_direction"] = TAG_Int(0)
        return Block("minecraft", base_name, properties)

    @staticmethod
    def _source_water_block() -> Block:
        return Block(
            "minecraft",
            "water",
            {"liquid_depth": TAG_Int(0)},
        )

    def _planned_water_block(self, water_cover: str, slab_type: str) -> Block:
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

    @staticmethod
    def _combined_selection_bounds(boxes: Sequence[BoxTuple]) -> Tuple[int, int, int, int]:
        return (
            min(box[0] for box in boxes),
            max(box[1] for box in boxes),
            min(box[4] for box in boxes),
            max(box[5] for box in boxes),
        )

    def _row_axis(self, boxes: Sequence[BoxTuple], direction_setting: str) -> str:
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
        x, y, z = pos
        for index, box in enumerate(boxes):
            min_x, max_x, min_y, max_y, min_z, max_z = box
            if (
                min_x <= x < max_x
                and min_y <= y < max_y
                and min_z <= z < max_z
            ):
                return index

        return 0

    @staticmethod
    def _selected_standard_crops(
        settings: Mapping[str, object],
    ) -> Tuple[str, ...]:
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
                        fruit_candidate = (
                            (x, farmland_y, z + delta)
                            if row_axis == "x"
                            else (x + delta, farmland_y, z)
                        )
                        if fruit_candidate in reserved_fruit or (
                            fruit_candidate in terrace_positions
                            and (
                                (
                                    (
                                        fruit_candidate[2]
                                        if row_axis == "x"
                                        else fruit_candidate[0]
                                    )
                                    - cross_origin
                                )
                                % 2
                                == 1
                            )
                        ):
                            fruit_pos = fruit_candidate
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

    @staticmethod
    def _positions_hydrated_by_water(
        water_pos: Position,
        farmland_positions: Set[Position],
    ) -> Set[Position]:
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

    def _build_plan(
        self,
        boxes: Sequence[BoxTuple],
        settings: Mapping[str, object],
        dim,
        plat,
        ver,
    ) -> FarmPlan:
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

        for water_pos in water_positions:
            farmland_positions.discard(water_pos)
            candidate = candidates.get(water_pos)
            if candidate is not None:
                crop_positions.pop(candidate.crop_pos, None)

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

    def _moisture_for_position(self, pos: Position, plan: FarmPlan) -> int:
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

        return writes, expected

    def _validate_plan_unchanged(
        self,
        expected: Mapping[Position, Tuple[Block, object]],
        dim,
        plat,
        ver,
    ) -> Tuple[bool, Optional[Position], str]:
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

    def _report_plan(
        self,
        plan: FarmPlan,
        planning_time: float,
        write_time: float,
        writes_applied: int,
        changed_chunks: int,
    ) -> None:
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

    def _snapshot_ui_settings(self) -> Dict[str, object]:
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
        self._clear_log()
        self._begin_operation_ui()

        selection_group = self.canvas.selection.selection_group
        if not selection_group:
            self._log("Auto Farmland Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log("Operation not started: no selection was found.")
            self._finalize_report()
            wx.MessageBox(
                "No selection was found.",
                "Auto Farmland",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            self._finish_operation_ui()
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
            self._finish_operation_ui()
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
                self._finish_operation_ui()
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
            self._finish_operation_ui()
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
                wx.CallAfter(
                    self.status.SetLabel,
                    "Auto Farmland failed. Review the report.",
                )
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
        finally:
            self._finish_operation_ui()

export = dict(name="Auto Farmland", operation=AutoFarmland)
