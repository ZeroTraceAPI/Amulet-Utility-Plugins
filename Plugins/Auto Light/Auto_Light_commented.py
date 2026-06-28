"""Auto Light v2.0.0.0 plugin for Amulet Map Editor.

Purpose:
- Scan selected Minecraft Bedrock Edition areas for valid lighting positions.
- Respect existing light, placement support, spacing and replacement rules.
- Place the selected light source through Amulet's undoable operation system.
- Present the complete control set in a self-themed floating window.

Navigation:
1. Light-source reference data and state rules
2. Placement block groups and replacement rules
3. Blue custom UI theme and shared helpers
4. Local Amulet resource-pack icon loading
5. Painted controls, scrolling, selectors and dialogs
6. Layered Windows dropdowns and tooltips with portable fallbacks
7. Floating window, launcher and window lifecycle
8. Settings persistence and plugin-file management
9. Console, report and selection preparation
10. Light detection, spacing and placement rules
11. Block construction, main operation and Amulet export
"""

import ast
import ctypes
import json
import os
import re
import tempfile
import weakref
from datetime import datetime
from pathlib import Path
from time import perf_counter

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
from amulet_nbt import TAG_String, TAG_Byte


# =========================
# LIGHT SOURCE REFERENCE
# =========================
# This section is intentionally data-heavy. Keeping light values in one place
# makes it easier to update for newer Minecraft Bedrock versions.
# Strength values are used for nearby-light detection and match Bedrock
# Edition block-light output. Variable sources are refined from their saved
# block states below. Only blocks that can emit light should be listed here.
# Conditional sources may be inactive in the saved world state and are handled
# separately below.
LIGHT_STRENGTH = {
    "torch": 14,
    "soul_torch": 10,
    "copper_torch": 14,

    "lantern": 15,
    "copper_lantern": 15,
    "exposed_copper_lantern": 15,
    "weathered_copper_lantern": 15,
    "oxidized_copper_lantern": 15,
    "waxed_copper_lantern": 15,
    "waxed_exposed_copper_lantern": 15,
    "waxed_weathered_copper_lantern": 15,
    "waxed_oxidized_copper_lantern": 15,

    "soul_lantern": 10,

    "sea_lantern": 15,
    "glowstone": 15,
    "shroomlight": 15,
    "jack_o_lantern": 15,
    "lit_pumpkin": 15,
    "redstone_lamp": 15,
    "lit_redstone_lamp": 15,
    "beacon": 15,
    "lava": 15,

    "campfire": 15,
    "soul_campfire": 10,

    "end_rod": 14,

    "candle": 12,
    "white_candle": 12,
    "orange_candle": 12,
    "magenta_candle": 12,
    "light_blue_candle": 12,
    "yellow_candle": 12,
    "lime_candle": 12,
    "pink_candle": 12,
    "gray_candle": 12,
    "light_gray_candle": 12,
    "cyan_candle": 12,
    "purple_candle": 12,
    "blue_candle": 12,
    "brown_candle": 12,
    "green_candle": 12,
    "red_candle": 12,
    "black_candle": 12,

    "candle_cake": 3,
    "white_candle_cake": 3,
    "orange_candle_cake": 3,
    "magenta_candle_cake": 3,
    "light_blue_candle_cake": 3,
    "yellow_candle_cake": 3,
    "lime_candle_cake": 3,
    "pink_candle_cake": 3,
    "gray_candle_cake": 3,
    "light_gray_candle_cake": 3,
    "cyan_candle_cake": 3,
    "purple_candle_cake": 3,
    "blue_candle_cake": 3,
    "brown_candle_cake": 3,
    "green_candle_cake": 3,
    "red_candle_cake": 3,
    "black_candle_cake": 3,

    "froglight": 15,
    "pearlescent_froglight": 15,
    "verdant_froglight": 15,
    "ochre_froglight": 15,

    "crying_obsidian": 10,

    "enchanting_table": 7,
    "ender_chest": 7,
    "magma": 3,
    "magma_block": 3,

    "conduit": 15,
    "respawn_anchor": 15,

    "blast_furnace": 13,
    "lit_blast_furnace": 13,
    "furnace": 13,
    "lit_furnace": 13,
    "smoker": 13,
    "lit_smoker": 13,

    "sea_pickle": 15,
    "glow_lichen": 7,
    "redstone_torch": 7,
    "unlit_redstone_torch": 7,

    "amethyst_cluster": 5,
    "large_amethyst_bud": 4,
    "medium_amethyst_bud": 2,
    "small_amethyst_bud": 1,

    "brewing_stand": 1,
    "brown_mushroom": 1,
    "dragon_egg": 1,
    "end_portal_frame": 1,

    "sculk_sensor": 1,
    "calibrated_sculk_sensor": 1,
    "sculk_catalyst": 6,

    "copper_bulb": 15,
    "exposed_copper_bulb": 12,
    "weathered_copper_bulb": 8,
    "oxidized_copper_bulb": 4,
    "waxed_copper_bulb": 15,
    "waxed_exposed_copper_bulb": 12,
    "waxed_weathered_copper_bulb": 8,
    "waxed_oxidized_copper_bulb": 4,

    "firefly_bush": 2,
}

LIGHT_SOURCES = set(LIGHT_STRENGTH.keys())

# Smart Coverage uses Minecraft-style light decay without adding overlapping
# source values together. A level-15 source can contribute positive light for
# at most 14 blocks of taxicab distance in unobstructed space.
SMART_LIGHT_MAX_DISTANCE = max(LIGHT_STRENGTH.values()) - 1
SMART_LIGHT_BUCKET_SIZE = 16

# Copper bulbs need special handling because their light output depends on state.
COPPER_BULB_BASES = {
    "copper_bulb",
    "exposed_copper_bulb",
    "weathered_copper_bulb",
    "oxidized_copper_bulb",
}
COPPER_BULB_NAMES = COPPER_BULB_BASES | {f"waxed_{name}" for name in COPPER_BULB_BASES}

# These blocks can exist in an inactive state. The default UI behavior treats
# them as potentially lit so Auto Light does not add permanent lighting around
# sources that may activate later. Users can disable that behavior to use the
# current supported block state instead.
CONDITIONAL_LIGHT_SOURCES = {
    "redstone_lamp",
    "blast_furnace",
    "furnace",
    "smoker",
    "campfire",
    "soul_campfire",
    "candle",
    "white_candle",
    "orange_candle",
    "magenta_candle",
    "light_blue_candle",
    "yellow_candle",
    "lime_candle",
    "pink_candle",
    "gray_candle",
    "light_gray_candle",
    "cyan_candle",
    "purple_candle",
    "blue_candle",
    "brown_candle",
    "green_candle",
    "red_candle",
    "black_candle",
    "candle_cake",
    "white_candle_cake",
    "orange_candle_cake",
    "magenta_candle_cake",
    "light_blue_candle_cake",
    "yellow_candle_cake",
    "lime_candle_cake",
    "pink_candle_cake",
    "gray_candle_cake",
    "light_gray_candle_cake",
    "cyan_candle_cake",
    "purple_candle_cake",
    "blue_candle_cake",
    "brown_candle_cake",
    "green_candle_cake",
    "red_candle_cake",
    "black_candle_cake",
    "sea_pickle",
    "respawn_anchor",
    "sculk_sensor",
    "calibrated_sculk_sensor",
    "copper_bulb",
    "exposed_copper_bulb",
    "weathered_copper_bulb",
    "oxidized_copper_bulb",
    "waxed_copper_bulb",
    "waxed_exposed_copper_bulb",
    "waxed_weathered_copper_bulb",
    "waxed_oxidized_copper_bulb",
    "unlit_redstone_torch",
}

# Legacy Bedrock identities encode the active state directly in the block name.
LEGACY_ACTIVE_LIGHT_NAMES = {
    "lit_redstone_lamp",
    "lit_blast_furnace",
    "lit_furnace",
    "lit_smoker",
}

CANDLE_LIGHT_NAMES = {
    "candle",
    "white_candle",
    "orange_candle",
    "magenta_candle",
    "light_blue_candle",
    "yellow_candle",
    "lime_candle",
    "pink_candle",
    "gray_candle",
    "light_gray_candle",
    "cyan_candle",
    "purple_candle",
    "blue_candle",
    "brown_candle",
    "green_candle",
    "red_candle",
    "black_candle",
    "candle_cake",
    "white_candle_cake",
    "orange_candle_cake",
    "magenta_candle_cake",
    "light_blue_candle_cake",
    "yellow_candle_cake",
    "lime_candle_cake",
    "pink_candle_cake",
    "gray_candle_cake",
    "light_gray_candle_cake",
    "cyan_candle_cake",
    "purple_candle_cake",
    "blue_candle_cake",
    "brown_candle_cake",
    "green_candle_cake",
    "red_candle_cake",
    "black_candle_cake",
}

# These are used for stacking prevention and are treated as recognized
# light-source bases even when a conditional source is currently inactive.
UNSTACKABLE_LIGHT_BASES = set(LIGHT_SOURCES)

# =========================
# BASIC BLOCK GROUPS
# =========================
# These groups drive placement decisions without repeating long string checks
# throughout the hot scan path.
AIR = ("air", "cave_air", "void_air")

TORCH_CHOICES = {
    "Torch",
    "Soul Torch",
    "Copper Torch",
}

LANTERN_CHOICES = {
    "Lantern",
    "Soul Lantern",
    "Copper Lantern",
    "Exposed Copper Lantern",
    "Weathered Copper Lantern",
    "Oxidized Copper Lantern",
}

COPPER_LANTERN_MAP = {
    "Copper Lantern": "copper_lantern",
    "Exposed Copper Lantern": "exposed_copper_lantern",
    "Weathered Copper Lantern": "weathered_copper_lantern",
    "Oxidized Copper Lantern": "oxidized_copper_lantern",
}

COPPER_BULB_MAP = {
    "Copper Bulb": "copper_bulb",
    "Exposed Copper Bulb": "exposed_copper_bulb",
    "Weathered Copper Bulb": "weathered_copper_bulb",
    "Oxidized Copper Bulb": "oxidized_copper_bulb",
}

COPPER_LANTERN_CHOICES = set(COPPER_LANTERN_MAP.keys())
COPPER_BULB_CHOICES = set(COPPER_BULB_MAP.keys())
COPPER_VARIANT_CHOICES = COPPER_LANTERN_CHOICES | COPPER_BULB_CHOICES

FULL_BLOCK_CHOICES = {
    "Sea Lantern",
    *COPPER_BULB_CHOICES,
}

# Firefly bush only makes sense on plant-like, solid ground.
FIREFLY_SUPPORT_KEYWORDS = (
    "grass_block",
    "dirt",
    "coarse_dirt",
    "rooted_dirt",
    "podzol",
    "mycelium",
    "moss_block",
    "mud",
    "packed_mud",
    "grass_path",
)

# Blocks that should not be treated as valid support for floor / wall / ceiling placement.
NON_SOLID_KEYWORDS = (
    # Generic plant and attachment families not fully represented by the exact
    # replacement set. Exact approved targets are rejected separately below.
    "reeds", "leaves", "sapling", "flower",
    "ladder", "vine", "rail", "powered_rail", "detector_rail", "activator_rail",
    "carpet", "button", "lever", "pressure_plate",
    "comparator", "repeater", "observer", "redstone", "wire", "dust",
    "sign", "banner",
    "door", "trapdoor",
    "slab", "stairs",
    "fence", "pane", "glass",
    "scaffolding",
    "chest", "barrel",
    "water", "lava",
    "bell",
    "torch", "lantern",
    "candle",
    "froglight", "glowstone", "sea_pickle", "shroomlight",
    "jack_o_lantern", "lit_pumpkin", "redstone_lamp",
    "beacon", "campfire",
    "blast_furnace", "furnace", "smoker", "brewing_stand",
    "amethyst_cluster", "amethyst_bud",
    "end_rod", "end_portal_frame", "dragon_egg",
    "sculk_sensor", "sculk_catalyst",
    "copper_bulb",
)

# Blocks that the replace-plants option may safely overwrite. The set includes
# current Bedrock names plus a few older Amulet-translated aliases that may
# still appear in existing worlds. Productive chain plants not already handled
# by Auto Light remain outside this list unless their replacement behavior has
# been explicitly reviewed.
REPLACEABLE_TARGET_BLOCKS = {
    # Grass, ferns and dry vegetation
    "short_grass", "tall_grass",
    "short_dry_grass", "tall_dry_grass",
    "fern", "large_fern",

    # Small flowers
    "dandelion", "golden_dandelion",
    "poppy", "blue_orchid", "allium", "azure_bluet",
    "red_tulip", "orange_tulip", "white_tulip", "pink_tulip",
    "oxeye_daisy", "cornflower", "lily_of_the_valley",
    "wither_rose", "closed_eyeblossom", "open_eyeblossom",
    "cactus_flower",

    # Double-height flowers
    "sunflower", "lilac", "rose_bush", "peony",

    # Bushes and shrubs
    "bush", "firefly_bush", "sweet_berry_bush",
    "azalea", "flowering_azalea",

    # Nether fungi and roots
    "crimson_fungus", "warped_fungus",
    "crimson_roots", "warped_roots", "nether_sprouts",

    # Mushrooms and dead vegetation
    "dead_bush", "deadbush",
    "brown_mushroom", "red_mushroom",

    # Aquatic and column plants already supported by Auto Light
    "seagrass", "kelp", "waterlily",
    "bamboo", "cactus",

    # Attached decoration
    "vine", "glow_lichen", "hanging_roots",

    # Dripleaf and propagules
    "small_dripleaf", "small_dripleaf_block",
    "big_dripleaf", "mangrove_propagule",

    # Ancient plants and crops already supported by Auto Light
    "pitcher_crop", "pitcher_plant",
    "torchflower", "torchflower_crop",

    # Ground cover and hanging decoration
    "pink_petals", "spore_blossom",
    "moss_carpet", "pale_moss_carpet",
    "leaf_litter", "wildflowers",
}

# Paired plants need both selected halves cleared so nothing remains floating.
# Torchflower crops are intentionally excluded because they use a growth state,
# not an upper / lower pair.
DOUBLE_HEIGHT_PLANTS = {
    "tall_grass",
    "large_fern",
    "sunflower",
    "lilac",
    "rose_bush",
    "peony",
    "small_dripleaf",
    "small_dripleaf_block",
    "pitcher_crop",
    "pitcher_plant",
    "pale_moss_carpet",
}

# A replaceable source at the candidate coordinate may ignore only its own
# existing light contribution. Other nearby sources remain fully respected.
REPLACEABLE_LIGHT_SOURCES = REPLACEABLE_TARGET_BLOCKS & LIGHT_SOURCES


# =========================
# CUSTOM UI FOUNDATION
# =========================
# These controls remain wxPython controls so they share Amulet's event loop,
# focus handling and window ownership. They draw their own appearance and opt
# out of Dark Mode UI through a shared semantic contract.
CUSTOM_UI_NAME_PREFIX = "AmuletUtilityCustomUI"
CUSTOM_UI_THEME_OWNED_ATTR = "_amulet_utility_theme_owned"

# The default size is intentionally compact. Auto Light.config stores the last
# normal size and restores it on the next load. Position is not persisted, so
# each session opens against the left edge of the Amulet window.
FLOATING_DEFAULT_SIZE = (480, 720)
FLOATING_MIN_SIZE = (440, 580)
MANAGE_DIALOG_DEFAULT_SIZE = (560, 460)
MANAGE_DIALOG_MIN_SIZE = (554, 410)

AUTO_LIGHT_THEME = {
    "window": wx.Colour(18, 21, 27),
    "surface": wx.Colour(27, 31, 39),
    "surface_alt": wx.Colour(22, 26, 33),
    "surface_hover": wx.Colour(35, 41, 51),
    "surface_pressed": wx.Colour(20, 63, 112),
    "border": wx.Colour(55, 63, 76),
    "border_soft": wx.Colour(43, 50, 61),
    "text": wx.Colour(231, 235, 242),
    "muted": wx.Colour(153, 163, 180),
    "accent": wx.Colour(22, 112, 219),
    "accent_hover": wx.Colour(35, 129, 239),
    "accent_pressed": wx.Colour(18, 91, 177),
    "disabled": wx.Colour(78, 85, 98),
    "console_bg": wx.Colour(5, 8, 11),
    "console_text": wx.Colour(83, 224, 126),
}

# Tooltips use the same active / open control outline as this plugin.
# The two-pixel border is shared by the Windows layered renderer and
# the portable wx fallback so both paths retain the plugin identity.
TOOLTIP_BORDER_COLOUR = AUTO_LIGHT_THEME["accent_hover"]
TOOLTIP_BORDER_WIDTH = 2

# Expanded dropdown windows reserve one near-black colour for the pixels
# outside their rounded shell. Windows makes that exact colour transparent
# through a layered-window colour key, while other platforms clip the same
# integer scanline outline with wx.Region.
CHOICE_POPUP_TRANSPARENT_COLOUR = wx.Colour(1, 2, 3)

# Shared spacing values keep the interface compact without crowding controls.
UI_CARD_MARGIN = 10
UI_CARD_PADDING = 12
UI_CONTROL_GAP = 7
UI_SECTION_GAP = 10
UI_FOOTER_MARGIN = 12
UI_SCROLLBAR_WIDTH = 12

# The floating frame may grow freely, but its complete interface column stops
# widening at this DPI-aware width. Additional horizontal frame space remains
# as centered themed background instead of stretching cards and controls.
UI_MAIN_CONTENT_MAX_WIDTH = 588

# Compact checkbox geometry keeps labels readable without making cards tall.
# The 18-pixel box leaves three pixels of vertical breathing room, and
# the label begins eight pixels after the box.
UI_CHECKBOX_HEIGHT = 24
UI_CHECKBOX_BOX_SIZE = 18
UI_CHECKBOX_LEFT_PADDING = 2
UI_CHECKBOX_LABEL_GAP = 8
UI_CHECKBOX_RIGHT_PADDING = 12
UI_CHECKBOX_TEXT_VERTICAL_PADDING = 6

# A five-pixel reduction is applied to the vertical space around each row
# without changing its horizontal alignment.
UI_CHECKBOX_GAP_REDUCTION = 5
UI_CHECKBOX_CONTROL_GAP = max(
    0,
    UI_CONTROL_GAP - UI_CHECKBOX_GAP_REDUCTION,
)
UI_CHECKBOX_CARD_GAP = max(
    0,
    UI_CARD_PADDING - UI_CHECKBOX_GAP_REDUCTION,
)

# A checkbox group followed by another section receives a separate transition
# gap so the larger separation is not retained at the bottom of the card.
UI_CHECKBOX_GROUP_TRANSITION_GAP = max(
    0,
    UI_CHECKBOX_CARD_GAP - UI_CHECKBOX_CONTROL_GAP,
)

# Explicit checkbox-group end spacers provide a small final separation
# between the last checkbox and its card or section boundary.
UI_FINAL_CHECKBOX_BOTTOM_EXTRA = 4


_CHECKBOX_SPACING_SIZERS = {}
_CHECKBOX_SPACING_BASELINES = {}
_CHECKBOX_SPACING_REFRESH_PENDING = set()
_CHECKBOX_GROUP_END_SPACERS = {}


def _register_checkbox_spacing_sizer(sizer):
    """Retain one sizer whose checkbox spacing needs responsive maintenance."""
    try:
        _CHECKBOX_SPACING_SIZERS[id(sizer)] = sizer
    except Exception:
        pass


def _sizer_item_window(item):
    """Return the window owned by one sizer item, if any."""
    try:
        return item.GetWindow()
    except Exception:
        return None


def _sizer_item_is_shown(item):
    """Return whether a sizer item contains any currently visible content."""
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
    """Return one spacer's width and height as ordinary integers."""
    spacer = item.GetSpacer()
    try:
        return int(spacer.width), int(spacer.height)
    except Exception:
        return int(spacer[0]), int(spacer[1])


def _capture_checkbox_spacing_baseline(sizer):
    """Capture the original sizer geometry used to recompute visible gaps."""
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
    """Restore one sizer before applying its current visible checkbox gaps."""
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
    """Return whether a zero-height spacer marks the next checkbox row."""
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
    """Return whether a spacer follows a checkbox that is currently hidden."""
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
    """Recompute upper checkbox gaps from the currently visible controls.

    Each checkbox receives a private zero-height marker spacer during UI
    construction. When optional controls are shown or hidden, this function
    restores the original sizer geometry, finds the nearest visible predecessor,
    moves that predecessor's vertical gap into the marker, and applies the
    configured reduction exactly once. Horizontal borders are preserved.
    """
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

    # Standalone spacers after hidden checkboxes must collapse with the
    # checkbox. Leaving those spacers visible makes dynamic cards retain
    # empty height even though the checkbox windows themselves are hidden.
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
                # Explicit group-end spacers belong to the preceding
                # checkbox group and must not become an upper gap.
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
                    # The spacer already represents the compact lower gap of the
                    # previous visible checkbox. Move it to this marker without
                    # applying the reduction a second time.
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
    """Coalesce checkbox-spacing refreshes on the wx event queue."""
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

            # One deferred viewport synchronization runs after the complete
            # batch of checkbox sizers has updated. This lets cards shrink to
            # their visible content without issuing one full scroll-layout pass
            # for every checkbox group.
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
    """Insert and maintain the upper-gap marker for the next checkbox row."""
    _register_checkbox_spacing_sizer(sizer)

    # The marker is inserted immediately before the checkbox by every existing
    # call site. Its height is calculated after the checkbox and the rest of the
    # card have been added to the sizer.
    try:
        sizer.AddSpacer(0)
    except Exception:
        return

    _schedule_checkbox_spacing_refresh(sizer)


def _add_checkbox_group_bottom_spacing(sizer):
    """Add one explicit spacer at a known checkbox-group boundary."""
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


def _invalidate_layout_best_size_chain(window):
    """Invalidate cached best sizes after a dynamic visibility change."""
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
    """Show or hide a window through its complete sizer item.

    Calling ``window.Show`` alone can leave the sizer item's border in the
    calculated minimum size. Toggling the item itself collapses both the window
    and that border, which is required for exact card-bottom spacing.
    """
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
    """Collapse or restore one nested sizer item and its border."""
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


def _set_sizer_group_visible(item, visible):
    """Show or hide one nested-sizer group and all of its child windows.

    Source-specific option groups use sizers instead of child panels so the
    parent rounded card remains fully visible at its lower corners. Recursively
    toggling the group items also prevents hidden controls from painting at
    their previous positions while the containing sizer item is collapsed.
    """
    if item is None:
        return

    show = bool(visible)

    try:
        child_sizer = item.GetSizer()
    except Exception:
        child_sizer = None

    def set_children_visible(sizer):
        try:
            children = list(sizer.GetChildren())
        except Exception:
            return

        for child in children:
            try:
                nested_sizer = child.GetSizer()
            except Exception:
                nested_sizer = None
            if nested_sizer is not None:
                set_children_visible(nested_sizer)

            try:
                child_window = child.GetWindow()
            except Exception:
                child_window = None
            if child_window is not None:
                try:
                    child_window.Show(show)
                except Exception:
                    pass

            try:
                child.Show(show)
            except Exception:
                pass

    if child_sizer is not None:
        set_children_visible(child_sizer)

    try:
        item.Show(show)
    except Exception:
        pass

    containing_window = None
    if child_sizer is not None:
        try:
            containing_window = child_sizer.GetContainingWindow()
        except Exception:
            containing_window = None
    _invalidate_layout_best_size_chain(containing_window)



# The visual light-source picker uses four evenly sized tiles per row.
# Labels remain overlaid so every tile keeps the same compact square-like
# footprint. Wrapped labels move upward and use a slightly tighter line advance.
LIGHT_SELECTOR_ICON_COLUMNS = 4
LIGHT_SELECTOR_TILE_HEIGHT = 104
LIGHT_SELECTOR_ICON_SIZE = 72
LIGHT_SELECTOR_TWO_LINE_LABEL_OFFSET = 3
LIGHT_SELECTOR_TWO_LINE_SPACING_REDUCTION = 2

# Category-specific vertical offsets move artwork away from the label without
# changing tile dimensions. The bottom clamp prevents large icons from touching
# or crossing the lower rounded border.
LIGHT_SELECTOR_TORCH_ICON_OFFSET = 7
LIGHT_SELECTOR_TALL_ICON_OFFSET = 11
LIGHT_SELECTOR_FULL_BLOCK_ICON_OFFSET = 14
LIGHT_SELECTOR_ICON_BOTTOM_PADDING = 4

LIGHT_SELECTOR_MIN_WIDTH = 520
LIGHT_SELECTOR_GRID_GAP = 5
LIGHT_SELECTOR_POPUP_RADIUS = 12

# Display names remain the persisted settings values. These identifiers are
# used only to resolve optional item / block artwork from Amulet's local cache.
LIGHT_ICON_ITEM_IDS = {
    "Torch": "torch",
    "Soul Torch": "soul_torch",
    "Copper Torch": "copper_torch",
    "Lantern": "lantern",
    "Soul Lantern": "soul_lantern",
    "Copper Lantern": "copper_lantern",
    "Exposed Copper Lantern": "exposed_copper_lantern",
    "Weathered Copper Lantern": "weathered_copper_lantern",
    "Oxidized Copper Lantern": "oxidized_copper_lantern",
    "Copper Bulb": "copper_bulb",
    "Exposed Copper Bulb": "exposed_copper_bulb",
    "Weathered Copper Bulb": "weathered_copper_bulb",
    "Oxidized Copper Bulb": "oxidized_copper_bulb",
    "Sea Lantern": "sea_lantern",
    "Firefly Bush": "firefly_bush",
}

# These model-aware fallbacks keep icon loading functional if Amulet changes or
# temporarily omits the Java item-model cache. ``generated`` uses a flat sprite;
# ``cube_all`` creates a small isometric inventory-style block render.
LIGHT_ICON_FALLBACK_SPECS = {
    "Torch": ("generated", "minecraft:block/torch"),
    "Soul Torch": ("generated", "minecraft:block/soul_torch"),
    "Copper Torch": ("generated", "minecraft:block/copper_torch"),
    "Lantern": ("generated", "minecraft:item/lantern"),
    "Soul Lantern": ("generated", "minecraft:item/soul_lantern"),
    "Copper Lantern": ("generated", "minecraft:item/copper_lantern"),
    "Exposed Copper Lantern": ("generated", "minecraft:item/exposed_copper_lantern"),
    "Weathered Copper Lantern": ("generated", "minecraft:item/weathered_copper_lantern"),
    "Oxidized Copper Lantern": ("generated", "minecraft:item/oxidized_copper_lantern"),
    "Copper Bulb": ("cube_all", "minecraft:block/copper_bulb"),
    "Exposed Copper Bulb": ("cube_all", "minecraft:block/exposed_copper_bulb"),
    "Weathered Copper Bulb": ("cube_all", "minecraft:block/weathered_copper_bulb"),
    "Oxidized Copper Bulb": ("cube_all", "minecraft:block/oxidized_copper_bulb"),
    "Sea Lantern": ("cube_all", "minecraft:block/sea_lantern"),
    "Firefly Bush": ("generated", "minecraft:item/firefly_bush"),
}


def _light_selector_icon_offset(choice):
    """Return the configured downward artwork offset for one selector tile."""
    choice = str(choice)

    # Sea Lantern is a full cube despite its display name, so full-block
    # classification intentionally takes priority over the lantern family.
    if choice in FULL_BLOCK_CHOICES:
        return LIGHT_SELECTOR_FULL_BLOCK_ICON_OFFSET
    if choice in TORCH_CHOICES:
        return LIGHT_SELECTOR_TORCH_ICON_OFFSET
    if choice in LANTERN_CHOICES or choice == "Firefly Bush":
        return LIGHT_SELECTOR_TALL_ICON_OFFSET
    return 0


def _mark_custom_ui_owned(window, semantic_name=None):
    """Mark a wx window as self-themed so Dark Mode UI skips its subtree."""
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
    """Best-effort dark styling for native Windows child scrollbars.

    Custom scroll areas use ModernScrollBar. Native editors such as wx.TextCtrl
    still own their platform scrollbars, so this asks Windows to use its dark
    Explorer theme without changing the global application theme. Failure is
    intentionally ignored for older Windows / wx builds.
    """
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
    """Return a DPI-scaled integer while supporting older wxPython builds."""
    try:
        return int(window.FromDIP(value))
    except Exception:
        return int(value)


def _parent_background(window):
    """Return a valid parent background for clearing a custom-painted control."""
    try:
        parent = window.GetParent()
        color = parent.GetBackgroundColour() if parent is not None else None
        if color is not None and color.IsOk():
            return color
    except Exception:
        pass
    return AUTO_LIGHT_THEME["window"]


def _graphics_text_size(graphics_context, text):
    """Return width and height from either 2-value or 4-value wx extents."""
    try:
        extent = graphics_context.GetTextExtent(str(text))
        return float(extent[0]), float(extent[1])
    except Exception:
        return 0.0, 0.0


def _emit_command_event(window, event_binder):
    """Emit a standard wx command event from a custom control."""
    try:
        event = wx.CommandEvent(event_binder.typeId, window.GetId())
        event.SetEventObject(window)
        window.GetEventHandler().ProcessEvent(event)
    except Exception:
        pass


def _make_text(parent, label, point_size=None, bold=False, muted=False):
    """Create a theme-owned text label with optional size and emphasis."""
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
            AUTO_LIGHT_THEME["muted"] if muted else AUTO_LIGHT_THEME["text"]
        )
        control.SetBackgroundColour(parent.GetBackgroundColour())
    except Exception:
        pass
    return control


def _wrap_static_text_lines(device_context, text, maximum_width):
    """Wrap plain descriptive text to the measured width of its control."""
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
    """Relayout changed content and synchronize its containing viewport.

    Dynamic visibility and spacer changes can leave wxPython's cached best size
    larger than the currently visible controls. Invalidating the complete parent
    chain before recalculating prevents rounded cards from retaining blank space.
    """
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
    """Create responsive descriptive text with a tightly measured height.

    The label reflows only after wx assigns a meaningful width. Height changes
    are applied once per distinct layout, and parent relayout requests are
    coalesced so a group of cards cannot flood the wx event queue.
    """
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

        # EVT_SIZE performs the wrap when the control has not received a
        # usable width.
        # Do not reschedule here, because repeated CallAfter retries can starve
        # the UI thread while a large settings window is being constructed.
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

        # Record the signature before changing sizes. SetMinSize and Layout may
        # synchronously produce another size event on some wxPython builds.
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

    # Store the live text state and callback so dynamic descriptions can update
    # without falling back to fixed-width wx.StaticText.Wrap calls.
    container._responsive_text_state = text_state
    container._responsive_text_control = text_control
    container._responsive_layout_state = layout_state
    container._responsive_wrap_callback = apply_wrap

    # One deferred pass handles controls that already have a usable width.
    # Otherwise, the later EVT_SIZE event performs the wrap.
    try:
        wx.CallAfter(apply_wrap)
    except Exception:
        pass

    return container


# =========================
# AMULET RESOURCE-PACK ICONS
# =========================
class AmuletLightIconCache:
    """Resolve optional light-source artwork from Amulet's local caches.

    Java item and model JSON files determine whether an item uses a flat
    ``item/generated`` sprite or a ``block/cube_all`` model. Small direct Java
    texture files are preferred for normal loading, with Amulet's packed atlas
    used as a fallback. Resource failures are nonfatal, and the selector falls
    back to its text-only mode.
    """

    ATLAS_JSON_LIMIT = 16 * 1024 * 1024
    MODEL_JSON_LIMIT = 2 * 1024 * 1024
    BASE_ICON_SIZE = 64

    def __init__(self):
        """Initialize lazy resource discovery and bounded bitmap caches."""
        self._loaded = False
        self._resource_roots = []
        self._base_icons = {}
        # Keep the resolved source texture for compact selected-item icons.
        # Rendering those icons directly from the original pixels avoids the
        # double-resampling that can damage one-pixel outlines on thin sprites.
        self._icon_sources = {}
        self._bitmap_cache = {}
        self._compact_bitmap_cache = {}

    # Resource discovery and safe file access

    @staticmethod
    def _local_app_data_root():
        """Return the per-user local application-data root."""
        value = os.environ.get("LOCALAPPDATA", "").strip()
        if value:
            return Path(value)
        return Path.home() / "AppData" / "Local"

    @classmethod
    def _cache_root(cls):
        """Return Amulet's materialized resource-pack cache root."""
        return (
            cls._local_app_data_root()
            / "AmuletTeam"
            / "AmuletMapEditor"
            / "Cache"
            / "resource_packs"
        )

    @staticmethod
    def _normalize_path(value):
        """Normalize a resource path for case-insensitive suffix matching."""
        return str(value).replace("\\", "/").lower()

    @staticmethod
    def _texture_suffix(texture_reference):
        """Convert a namespaced texture reference to its cache-path suffix."""
        reference = str(texture_reference or "").strip()
        if not reference:
            return ""
        if ":" in reference:
            _namespace, reference = reference.split(":", 1)
        reference = reference.strip("/").replace("\\", "/")
        return f"/textures/{reference}.png".lower()

    @staticmethod
    def _safe_json(path, size_limit):
        """Read a bounded JSON file, returning None for unavailable data."""
        try:
            path = Path(path)
            if not path.is_file() or path.stat().st_size > int(size_limit):
                return None
            with path.open("r", encoding="utf-8-sig") as handle:
                return json.load(handle)
        except Exception:
            return None

    def _discover_resource_roots(self):
        """Discover ordered Minecraft Java resource roots in Amulet's local cache."""
        java_root = self._cache_root() / "java"
        roots = []
        try:
            children = [child for child in java_root.iterdir() if child.is_dir()]
        except Exception:
            children = []

        # Non-vanilla folders are considered first so a model / texture override
        # can be used when Amulet has materialized it as a complete resource root.
        children.sort(
            key=lambda child: (
                child.name.lower() == "vanilla",
                -self._safe_mtime(child),
                child.name.lower(),
            )
        )
        for child in children:
            candidate = child / "assets" / "minecraft"
            if candidate.is_dir():
                roots.append(candidate)

        vanilla = java_root / "vanilla" / "assets" / "minecraft"
        if vanilla.is_dir() and vanilla not in roots:
            roots.append(vanilla)
        self._resource_roots = roots

    @staticmethod
    def _safe_mtime(path):
        """Return a sortable modification time without propagating I / O errors."""
        try:
            return float(Path(path).stat().st_mtime)
        except Exception:
            return 0.0

    def _find_resource_file(self, relative_path):
        """Return the first matching file from the ordered resource roots."""
        relative_path = Path(relative_path)
        for root in self._resource_roots:
            candidate = root / relative_path
            try:
                if candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    # Item-model and atlas resolution

    @staticmethod
    def _model_relative_path(model_reference):
        """Convert a namespaced model reference to a relative JSON path."""
        reference = str(model_reference or "").strip()
        if not reference:
            return None
        if ":" in reference:
            _namespace, reference = reference.split(":", 1)
        reference = reference.strip("/").replace("\\", "/")
        return Path("models") / f"{reference}.json"

    def _resolve_model_spec(self, item_id):
        """Resolve an item model to a supported flat or cube render spec."""
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
                # Built-in abstract parents such as item/generated and cube_all
                # normally have no physical JSON file in the materialized cache.
                chain.append({"parent": current, "textures": {}})
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

        parent_values = [str(model.get("parent", "")).lower() for model in chain]
        model_values = [str(model_reference).lower(), *parent_values]
        if any(value.endswith("item/generated") for value in model_values):
            render_kind = "generated"
            texture_value = textures.get("layer0")
        elif any(value.endswith("block/cube_all") for value in model_values):
            render_kind = "cube_all"
            texture_value = textures.get("all")
        else:
            return None

        for _ in range(12):
            if not isinstance(texture_value, str) or not texture_value.startswith("#"):
                break
            texture_value = textures.get(texture_value[1:])
        if not isinstance(texture_value, str) or not texture_value:
            return None
        return render_kind, texture_value

    def _model_specs(self):
        """Build render specifications for all configured light choices."""
        specs = {}
        for choice, item_id in LIGHT_ICON_ITEM_IDS.items():
            spec = self._resolve_model_spec(item_id)
            if spec is None:
                spec = LIGHT_ICON_FALLBACK_SPECS.get(choice)
            if spec is not None:
                specs[choice] = spec
        return specs

    def _select_atlas(self, specs):
        """Select the cached atlas that covers the greatest number of required textures."""
        atlas_root = self._cache_root() / "atlas"
        try:
            json_files = list(atlas_root.glob("*.json"))
        except Exception:
            json_files = []

        required_suffixes = {
            self._texture_suffix(texture_reference)
            for _kind, texture_reference in specs.values()
        }
        required_suffixes.discard("")
        candidates = []
        for json_path in json_files:
            png_path = json_path.with_suffix(".png")
            if not png_path.is_file():
                continue
            data = self._safe_json(json_path, self.ATLAS_JSON_LIMIT)
            if (
                not isinstance(data, list)
                or len(data) < 2
                or not isinstance(data[1], dict)
            ):
                continue
            mapping = data[1]
            normalized_paths = [self._normalize_path(path) for path in mapping.keys()]
            score = sum(
                1
                for suffix in required_suffixes
                if any(path.endswith(suffix) for path in normalized_paths)
            )
            try:
                declared_time = float(data[0])
            except Exception:
                declared_time = 0.0
            candidates.append(
                (
                    score,
                    declared_time,
                    self._safe_mtime(json_path),
                    json_path,
                    png_path,
                    mapping,
                )
            )

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        _score, _declared, _mtime, json_path, png_path, mapping = candidates[0]
        return json_path, png_path, mapping

    def _atlas_texture(self, atlas_image, atlas_mapping, texture_reference):
        """Extract one texture region from an Amulet atlas mapping."""
        suffix = self._texture_suffix(texture_reference)
        if not suffix:
            return None
        matches = []
        for raw_path, raw_uv in atlas_mapping.items():
            normalized = self._normalize_path(raw_path)
            if normalized.endswith(suffix):
                matches.append((raw_path, raw_uv))
        if not matches:
            return None

        # Preserve JSON order and prefer the last matching entry. This is a
        # best-effort approximation of the override order used while Amulet
        # assembled the atlas, while vanilla-only atlases remain unambiguous.
        _path, uv = matches[-1]
        if not isinstance(uv, (list, tuple)) or len(uv) != 4:
            return None
        try:
            width, height = atlas_image.size
            left = int(round(float(uv[0]) * width))
            top = int(round(float(uv[1]) * height))
            right = int(round(float(uv[2]) * width))
            bottom = int(round(float(uv[3]) * height))
        except Exception:
            return None
        left = max(0, min(left, width - 1))
        top = max(0, min(top, height - 1))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))
        try:
            return atlas_image.crop((left, top, right, bottom)).convert("RGBA")
        except Exception:
            return None

    def _direct_texture(self, texture_reference):
        """Load one texture directly from the ordered resource roots."""
        suffix = self._texture_suffix(texture_reference)
        if not suffix:
            return None
        relative = suffix.lstrip("/")
        texture_path = self._find_resource_file(relative)
        if texture_path is None:
            return None
        try:
            with Image.open(texture_path) as image:
                return image.convert("RGBA")
        except Exception:
            return None

    # Pixel-art rendering

    @staticmethod
    def _nearest_filter():
        """Return Pillow's nearest-neighbor filter across supported versions."""
        try:
            return Image.Resampling.NEAREST
        except Exception:
            return Image.NEAREST

    @staticmethod
    def _smooth_filter():
        """Return a high-quality filter for reducing rendered 3D geometry."""
        try:
            return Image.Resampling.LANCZOS
        except Exception:
            return Image.LANCZOS

    @staticmethod
    def _first_animation_frame(texture):
        """Return the first square frame from a vertically or horizontally packed texture."""
        texture = texture.convert("RGBA")
        width, height = texture.size
        if width > 0 and height > width and height % width == 0:
            return texture.crop((0, 0, width, width))
        if height > 0 and width > height and width % height == 0:
            return texture.crop((0, 0, height, height))
        return texture

    @classmethod
    def _render_flat_icon(cls, texture):
        """Render a flat item sprite onto the shared transparent icon canvas."""
        canvas_size = cls.BASE_ICON_SIZE
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        texture = cls._first_animation_frame(texture)
        target = 54
        scale = min(target / max(1, texture.width), target / max(1, texture.height))
        width = max(1, int(round(texture.width * scale)))
        height = max(1, int(round(texture.height * scale)))
        resized = texture.resize((width, height), cls._nearest_filter())
        canvas.alpha_composite(
            resized,
            ((canvas_size - width) // 2, (canvas_size - height) // 2),
        )
        return canvas

    @staticmethod
    def _shade_pixel(pixel, factor):
        """Apply one brightness multiplier while preserving source alpha."""
        red, green, blue, alpha = pixel
        return (
            max(0, min(255, int(round(red * factor)))),
            max(0, min(255, int(round(green * factor)))),
            max(0, min(255, int(round(blue * factor)))),
            alpha,
        )

    @classmethod
    def _render_cube_icon(
        cls,
        texture,
        *,
        top_shade=1.08,
        left_shade=0.84,
        right_shade=0.68,
        face_scale=1.0,
    ):
        """Render an anti-aliased isometric full-block item.

        Source textures remain at their native 16-pixel resolution. The cube is
        drawn on a four-times supersampled canvas and reduced once with Lanczos
        filtering. This smooths the diagonal model edges without softening the
        original flat-item artwork used by torches, lanterns and Firefly Bush.
        """
        render_size = cls.BASE_ICON_SIZE * 4
        geometry_scale = render_size / 128.0
        texture = cls._first_animation_frame(texture).resize(
            (16, 16),
            cls._nearest_filter(),
        )
        canvas = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas, "RGBA")
        center_x = render_size / 2.0
        top_y = 6.0 * geometry_scale
        face_width = 66.0 * face_scale * geometry_scale
        face_height = 32.0 * face_scale * geometry_scale
        side_height = 46.0 * face_scale * geometry_scale

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

        def draw_face(origin, basis_x, basis_y, shade):
            for source_y in range(16):
                for source_x in range(16):
                    pixel = texture.getpixel((source_x, source_y))
                    if pixel[3] <= 0:
                        continue
                    u0 = source_x / 16.0
                    v0 = source_y / 16.0
                    u1 = (source_x + 1) / 16.0
                    v1 = (source_y + 1) / 16.0
                    polygon = [
                        point(origin, basis_x, basis_y, u0, v0),
                        point(origin, basis_x, basis_y, u1, v0),
                        point(origin, basis_x, basis_y, u1, v1),
                        point(origin, basis_x, basis_y, u0, v1),
                    ]
                    draw.polygon(polygon, fill=cls._shade_pixel(pixel, shade))

        draw_face(left_origin, left_x, left_y, left_shade)
        draw_face(right_origin, right_x, right_y, right_shade)
        draw_face(top_origin, top_x, top_y_basis, top_shade)
        return canvas.resize(
            (cls.BASE_ICON_SIZE, cls.BASE_ICON_SIZE),
            cls._smooth_filter(),
        )

    @classmethod
    def _render_sea_lantern_icon(cls, texture):
        """Render the first Sea Lantern animation frame as an isometric cube."""
        # Sea Lantern is an animated 16 x 64 texture strip. Rendering the whole
        # strip as one 16 x 16 image creates false horizontal bands, so use only
        # the first 16 x 16 animation frame and preserve nearest-neighbor pixels.
        frame = cls._first_animation_frame(texture)
        return cls._render_cube_icon(
            frame,
            top_shade=1.06,
            left_shade=0.92,
            right_shade=0.82,
            face_scale=0.94,
        )

    @staticmethod
    def _content_bbox(image):
        """Return the visible alpha bounds for one rendered icon."""
        try:
            return image.convert("RGBA").getchannel("A").getbbox()
        except Exception:
            return None

    @classmethod
    def _fit_icon_to_size(cls, image, size, padding=0, smooth=False):
        """Scale visible icon content into a square with optional smoothing."""
        image = image.convert("RGBA")
        try:
            size = max(8, int(size))
        except Exception:
            size = 32
        padding = max(0, int(padding))

        bounds = cls._content_bbox(image)
        if bounds is not None:
            image = image.crop(bounds)

        available = max(1, size - (padding * 2))
        source_width = max(1, image.width)
        source_height = max(1, image.height)
        scale = min(
            available / float(source_width),
            available / float(source_height),
        )
        width = max(1, int(round(source_width * scale)))
        height = max(1, int(round(source_height * scale)))
        resize_filter = cls._smooth_filter() if smooth else cls._nearest_filter()
        image = image.resize((width, height), resize_filter)

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(
            image,
            ((size - width) // 2, (size - height) // 2),
        )
        return canvas

    @classmethod
    def _render_compact_icon(cls, source, render_kind, size):
        """Render a compact selector icon directly from original artwork.

        Flat item sprites use a whole-number nearest-neighbor scale so every
        source pixel, including one-pixel colored outlines, remains complete.
        Cube items reuse the already rendered model icon and fit it normally.
        """
        try:
            size = max(12, int(size))
        except Exception:
            size = 34

        source = source.convert("RGBA")
        if render_kind == "flat":
            source = cls._first_animation_frame(source)
            bounds = cls._content_bbox(source)
            if bounds is not None:
                source = source.crop(bounds)

            margin = max(2, int(round(size * 0.06)))
            available = max(1, size - (margin * 2))
            width = max(1, source.width)
            height = max(1, source.height)
            integer_scale = max(1, int(min(available / width, available / height)))
            rendered_width = max(1, width * integer_scale)
            rendered_height = max(1, height * integer_scale)
            rendered = source.resize(
                (rendered_width, rendered_height),
                cls._nearest_filter(),
            )
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.alpha_composite(
                rendered,
                (
                    (size - rendered_width) // 2,
                    (size - rendered_height) // 2,
                ),
            )
            return canvas

        return cls._fit_icon_to_size(
            source,
            size,
            padding=max(2, int(round(size * 0.08))),
            smooth=True,
        )

    @staticmethod
    def _pil_to_bitmap(image):
        """Convert a Pillow RGBA image to a wx bitmap with alpha intact."""
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

    # Public bitmap access

    def ensure_loaded(self):
        """Load available local icon resources once and report success."""
        if self._loaded:
            return bool(self._base_icons)
        self._loaded = True
        if Image is None or ImageDraw is None:
            return False
        self._discover_resource_roots()
        specs = self._model_specs()
        if not specs:
            return False

        # Direct Java textures are tiny and avoid decoding a complete 4096-pixel
        # atlas during normal startup. The atlas remains the fallback for packs
        # whose resolved texture exists only in Amulet's packed cache.
        unresolved = {}
        for choice, (render_kind, texture_reference) in specs.items():
            texture = self._direct_texture(texture_reference)
            if texture is None:
                unresolved[choice] = (render_kind, texture_reference)
                continue
            try:
                if choice == "Sea Lantern":
                    icon = self._render_sea_lantern_icon(texture)
                elif render_kind == "cube_all":
                    icon = self._render_cube_icon(texture)
                else:
                    icon = self._render_flat_icon(texture)
                self._base_icons[choice] = icon
                self._icon_sources[choice] = (
                    "flat" if render_kind != "cube_all" else "cube",
                    texture.copy() if render_kind != "cube_all" else icon.copy(),
                )
            except Exception:
                unresolved[choice] = (render_kind, texture_reference)

        atlas_image = None
        atlas_mapping = {}
        if unresolved:
            atlas = self._select_atlas(unresolved)
            if atlas is not None:
                _json_path, png_path, atlas_mapping = atlas
                try:
                    with Image.open(png_path) as source:
                        atlas_image = source.convert("RGBA")
                except Exception:
                    atlas_image = None
                    atlas_mapping = {}

        try:
            if atlas_image is not None:
                for choice, (render_kind, texture_reference) in unresolved.items():
                    texture = self._atlas_texture(
                        atlas_image,
                        atlas_mapping,
                        texture_reference,
                    )
                    if texture is None:
                        continue
                    try:
                        if choice == "Sea Lantern":
                            icon = self._render_sea_lantern_icon(texture)
                        elif render_kind == "cube_all":
                            icon = self._render_cube_icon(texture)
                        else:
                            icon = self._render_flat_icon(texture)
                        self._base_icons[choice] = icon
                        self._icon_sources[choice] = (
                            "flat" if render_kind != "cube_all" else "cube",
                            texture.copy() if render_kind != "cube_all" else icon.copy(),
                        )
                    except Exception:
                        continue
        finally:
            try:
                if atlas_image is not None:
                    atlas_image.close()
            except Exception:
                pass

        return bool(self._base_icons)

    def available_count(self):
        """Return the number of light-source icons currently available."""
        self.ensure_loaded()
        return len(self._base_icons)

    def get_bitmap(self, choice, size, padding=0):
        """Return a square popup bitmap for one light-source choice."""
        self.ensure_loaded()
        choice = str(choice)
        try:
            size = max(8, int(size))
        except Exception:
            size = 32
        try:
            padding = max(0, int(padding))
        except Exception:
            padding = 0
        key = (choice, size, padding)
        if key in self._bitmap_cache:
            return self._bitmap_cache[key]
        image = self._base_icons.get(choice)
        if image is None:
            return wx.NullBitmap
        source_entry = self._icon_sources.get(choice)
        smooth = bool(source_entry and source_entry[0] == "cube")
        image = self._fit_icon_to_size(
            image,
            size,
            padding=padding,
            smooth=smooth,
        )
        bitmap = self._pil_to_bitmap(image)
        self._bitmap_cache[key] = bitmap
        return bitmap

    def get_compact_bitmap(self, choice, size):
        """Render the closed-selector icon directly from its stored source."""
        self.ensure_loaded()
        choice = str(choice)
        try:
            size = max(12, int(size))
        except Exception:
            size = 34
        key = (choice, size)
        if key in self._compact_bitmap_cache:
            return self._compact_bitmap_cache[key]

        source_entry = self._icon_sources.get(choice)
        if source_entry is None:
            return self.get_bitmap(choice, size, padding=2)
        render_kind, source = source_entry
        try:
            image = self._render_compact_icon(source, render_kind, size)
            bitmap = self._pil_to_bitmap(image)
        except Exception:
            return self.get_bitmap(choice, size, padding=2)
        self._compact_bitmap_cache[key] = bitmap
        return bitmap


# -------------------------
# CORE PAINTED CONTROLS
# -------------------------
def _rounded_scanline_inset(width, height, radius, y):
    """Return the opaque left inset for one rounded-rectangle scanline.

    Portable dropdown and tooltip shapes share this integer mask with their
    painted surfaces. Matching both paths prevents the top-level window from
    exposing pixels that its rounded child panel did not cover.
    """
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
    """A softly rounded self-painted container used for cards and status rows."""

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
        self._fill = background or AUTO_LIGHT_THEME["surface"]
        self._border = border or AUTO_LIGHT_THEME["border_soft"]
        self._radius = radius
        # Dropdown and tooltip windows pass an explicit clear colour here.
        # Their scanline painter then assigns every visible edge pixel directly
        # instead of anti-aliasing against an unintended backing surface.
        self._clear_background = clear_background
        self.SetBackgroundColour(self._fill)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(False), event.Skip()))

    def _on_paint(self, _event):
        """Paint the card using the normal or portable-tooltip rendering path."""
        dc = wx.AutoBufferedPaintDC(self)
        clear_colour = self._clear_background or _parent_background(self)
        dc.SetBackground(wx.Brush(clear_colour))
        dc.Clear()
        size = self.GetClientSize()
        if size.width <= 1 or size.height <= 1:
            return

        radius = max(1, _dip(self, self._radius))
        if self._clear_background is not None:
            # Portable tooltip cards use the same integer scanline mask for their
            # window shape and painted surface. Every visible pixel is assigned
            # the themed border or fill color without translucent edge pixels.
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

        # In-window cards use an anti-aliased stroked border so they blend
        # naturally with the parent surface.
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
    """Rounded push button that emits the ordinary wx.EVT_BUTTON event."""

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
        # Busy is a visual and interaction state that deliberately does not
        # disable the native wx control. Some Amulet operation cleanup paths
        # can reapply a disabled wx state after a worker finishes, leaving a
        # custom primary button permanently painted as disabled. Keeping busy
        # separate makes the final blue state fully owned by this control.
        self._busy = False
        # Availability is owned by the custom control instead of wx's native
        # enabled flag. Amulet may temporarily disable the event source around
        # canvas.run_operation and reapply that state after the worker returns.
        # Keeping the native window enabled lets the custom button reliably
        # restore its own visual and interaction state afterward.
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
        """Return the label through the standard wx control API."""
        return self._label

    def DoGetBestClientSize(self):
        """Provide wxPython's virtual best-size calculation for this control."""
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(self._label)
        return wx.Size(width + _dip(self, 34), max(height + _dip(self, 16), _dip(self, 34 if self._compact else 40)))

    def ProtectFromExternalDisable(self, protect=True):
        """Ignore later native Disable calls for framework-owned action buttons."""
        self._protect_from_external_disable = bool(protect)
        try:
            wx.Control.Enable(self, True)
        except Exception:
            pass
        self._update_cursor()
        self.Refresh(False)

    def SetAvailable(self, available=True):
        """Set the button's logical enabled state while keeping wx enabled."""
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
        """Return the plugin-owned logical enabled state."""
        return bool(self._available)

    def Enable(self, enable=True):
        """Route wx enable requests through the plugin-owned availability state."""
        # Amulet may call Disable on the button that started an operation. The
        # primary action buttons opt out of that framework-side state because
        # Auto Light already manages their availability and busy state itself.
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
        """Set a non-native busy state without disabling the wx control."""
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
        """Return whether the control is displaying its busy state."""
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
            return AUTO_LIGHT_THEME["surface_alt"], AUTO_LIGHT_THEME["disabled"], AUTO_LIGHT_THEME["border_soft"]
        if self._primary:
            if self._pressed:
                fill = AUTO_LIGHT_THEME["accent_pressed"]
            elif self._hovered:
                fill = AUTO_LIGHT_THEME["accent_hover"]
            else:
                fill = AUTO_LIGHT_THEME["accent"]
            return fill, AUTO_LIGHT_THEME["text"], fill
        if self._pressed:
            fill = AUTO_LIGHT_THEME["surface_pressed"]
        elif self._hovered:
            fill = AUTO_LIGHT_THEME["surface_hover"]
        else:
            fill = AUTO_LIGHT_THEME["surface_alt"]
        return fill, AUTO_LIGHT_THEME["text"], AUTO_LIGHT_THEME["border"]

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
            gc.SetPen(wx.Pen(AUTO_LIGHT_THEME["accent_hover"], 1))
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
    """Self-painted check box with the standard wx.CheckBox value API."""

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
        """Return the label through the standard wx control API."""
        return self._label

    def GetValue(self):
        """Return the current checked state."""
        return bool(self._value)

    def SetValue(self, value):
        """Set the checked state without emitting an event."""
        self._value = bool(value)
        self.Refresh(False)

    def DoGetBestClientSize(self):
        """Provide wxPython's virtual best-size calculation for this control."""
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
        """Update native enabled state, cursor, and custom painting together."""
        result = super().Enable(enable)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if enable else wx.CURSOR_ARROW))
        self.Refresh(False)
        return result

    def Show(self, show=True):
        """Show or hide the checkbox and refresh visible spacing."""
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
        fill = AUTO_LIGHT_THEME["accent"] if self._value and enabled else AUTO_LIGHT_THEME["surface_alt"]
        if self._hovered and enabled and not self._value:
            fill = AUTO_LIGHT_THEME["surface_hover"]
        border = AUTO_LIGHT_THEME["accent_hover"] if self.HasFocus() and enabled else AUTO_LIGHT_THEME["border"]
        text_color = AUTO_LIGHT_THEME["text"] if enabled else AUTO_LIGHT_THEME["disabled"]
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(box_x + 0.5, box_y + 0.5, box_size - 1, box_size - 1, _dip(self, 4))
        if self._value:
            gc.SetPen(wx.Pen(AUTO_LIGHT_THEME["text"], max(2, _dip(self, 2))))
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
    """Rounded horizontal slider that emits the standard wx.EVT_SLIDER event."""

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
        gc.SetBrush(wx.Brush(AUTO_LIGHT_THEME["border_soft"]))
        gc.DrawRoundedRectangle(start, center_y - track_height / 2, max(1, end - start), track_height, track_height / 2)
        gc.SetBrush(wx.Brush(AUTO_LIGHT_THEME["accent"] if self.IsEnabled() else AUTO_LIGHT_THEME["disabled"]))
        gc.DrawRoundedRectangle(start, center_y - track_height / 2, max(1, knob_x - start), track_height, track_height / 2)
        gc.SetPen(wx.Pen(AUTO_LIGHT_THEME["accent_hover"] if self.HasFocus() else AUTO_LIGHT_THEME["border"], 1))
        gc.SetBrush(wx.Brush(AUTO_LIGHT_THEME["accent_hover"] if self._hovered and self.IsEnabled() else AUTO_LIGHT_THEME["accent"]))
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
    """Manual clipped viewport for custom Auto Light scrolling areas.

    It owns one content panel and scrolls by moving that panel vertically inside
    a clipped parent. This avoids native wx virtual-range and repaint mismatches
    in the main settings panel, popup lists, and plugin-management dialogs.
    """

    def __init__(self, parent, background=None):
        super().__init__(
            parent,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN | wx.FULL_REPAINT_ON_RESIZE,
        )
        _mark_custom_ui_owned(self)
        self._background = background or AUTO_LIGHT_THEME["window"]
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
        """Lay out the complete content panel and clamp the current offset."""
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
                # Give expanding controls their final width before calculating
                # the total vertical minimum.
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
            # Moving the child window is handled natively and is much cheaper
            # than repainting the complete clipped viewport for every drag tick.
            self._content.SetPosition((0, -int(round(offset))))
        except Exception:
            return
        if refresh:
            try:
                self.Refresh(False)
            except Exception:
                pass

    def ScrollChildIntoView(self, child, margin=4):
        """Move just enough to reveal one descendant of the content panel."""
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
    """Self-painted vertical scrollbar for :class:`ModernScrollViewport`.

    The viewport owns the content position. This control supplies the visible
    track and thumb, routes wheel input from descendants and keeps rapid thumb
    dragging responsive without repeatedly repainting the complete content tree.
    """

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
        """Route wheel input from the viewport and all current descendants."""
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

        # Repaint only the thumb during continuous movement. The complete
        # viewport is refreshed after a wheel action or when dragging ends.
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
        """Synchronize content layout, wheel routing and thumb geometry."""
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
        gc.SetBrush(wx.Brush(AUTO_LIGHT_THEME["surface_alt"]))
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
            AUTO_LIGHT_THEME["accent_hover"]
            if self._dragging
            else AUTO_LIGHT_THEME["accent"]
            if self._hovered
            else AUTO_LIGHT_THEME["border"]
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
            # Windows may combine rapid motion events. Polling the pointer at a
            # stable cadence keeps the thumb responsive during fast dragging.
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

        # Repaint the complete viewport once after dragging rather than during
        # every intermediate pointer sample.
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


# -------------------------
# DROPDOWNS AND DIALOGS
# -------------------------
class ModernChoiceOption(ModernButton):
    """One dark popup row used by ModernChoice and other picker dialogs."""

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
                AUTO_LIGHT_THEME["surface_alt"],
                AUTO_LIGHT_THEME["disabled"],
                AUTO_LIGHT_THEME["border_soft"],
            )
        if self._pressed:
            return (
                AUTO_LIGHT_THEME["accent_pressed"],
                AUTO_LIGHT_THEME["text"],
                AUTO_LIGHT_THEME["accent_pressed"],
            )
        if self._hovered:
            return (
                AUTO_LIGHT_THEME["surface_hover"],
                AUTO_LIGHT_THEME["text"],
                AUTO_LIGHT_THEME["accent_hover"],
            )
        if self._selected:
            return (
                AUTO_LIGHT_THEME["surface_pressed"],
                AUTO_LIGHT_THEME["text"],
                AUTO_LIGHT_THEME["accent"],
            )
        return (
            AUTO_LIGHT_THEME["surface_alt"],
            AUTO_LIGHT_THEME["text"],
            AUTO_LIGHT_THEME["border_soft"],
        )


class ModernIconChoiceOption(ModernChoiceOption):
    """One selectable tile with centered artwork and an overlaid label."""

    def __init__(self, parent, label, bitmap, selected=False):
        super().__init__(
            parent,
            label,
            selected=selected,
            row_height=LIGHT_SELECTOR_TILE_HEIGHT,
        )
        self._bitmap = bitmap
        self._icon_y_offset = _light_selector_icon_offset(label)
        try:
            font = self.GetFont()
            font.SetPointSize(max(7, font.GetPointSize() - 1))
            self.SetFont(font)
        except Exception:
            pass

    @staticmethod
    def _wrapped_lines(graphics_context, text, maximum_width):
        """Wrap a tile label to at most two centered lines with an ellipsis."""
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

        # Center the complete icon canvas in the tile. Labels are drawn over the
        # artwork afterward so the tile keeps the compact original proportions.
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
                + _dip(self, self._icon_y_offset)
            )

            # Keep the requested category offset, but always retain a small
            # opaque margin above the tile's lower border.
            maximum_icon_y = max(
                0.0,
                float(
                    size.height
                    - bitmap_height
                    - _dip(
                        self,
                        LIGHT_SELECTOR_ICON_BOTTOM_PADDING,
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
                gc.SetFont(
                    placeholder_font,
                    AUTO_LIGHT_THEME["muted"],
                )
            except Exception:
                pass
            text_width, text_height = _graphics_text_size(
                gc,
                placeholder,
            )
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

        # Preserve the original position for one-line labels. Only wrapped
        # two-line labels move upward by three DPI-scaled pixels so their lower
        # line has more separation from the centered icon.
        label_offset = (
            LIGHT_SELECTOR_TWO_LINE_LABEL_OFFSET
            if len(lines) > 1
            else 0
        )
        line_y = float(
            _dip(self, 6)
            - _dip(self, label_offset)
        )

        shadow_color = AUTO_LIGHT_THEME["console_bg"]
        for line in lines:
            text_width, text_height = _graphics_text_size(gc, line)
            text_x = (size.width - text_width) / 2.0

            # A one-pixel dark shadow keeps the light text readable over bright
            # icon pixels without changing the icon position.
            gc.SetFont(self.GetFont(), shadow_color)
            gc.DrawText(line, text_x + 1, line_y + 1)
            gc.SetFont(self.GetFont(), text_color)
            gc.DrawText(line, text_x, line_y)
            # The default one-pixel gap looks wider with this font's line
            # metrics. Reduce the wrapped-line advance by two pixels while
            # leaving single-line labels visually unchanged.
            line_y += max(
                1.0,
                text_height
                + _dip(self, 1)
                - _dip(
                    self,
                    LIGHT_SELECTOR_TWO_LINE_SPACING_REDUCTION,
                ),
            )

        if self.HasFocus() and self.IsAvailable() and not self.IsBusy():
            gc.SetPen(wx.Pen(AUTO_LIGHT_THEME["accent_hover"], 1))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawRoundedRectangle(
                2.5,
                2.5,
                max(1, size.width - 5),
                max(1, size.height - 5),
                _dip(self, 7),
            )


class ModernChoicePopup(wx.Frame):
    """Dark, modeless dropdown window with transparent rounded corners.

    The borderless frame retains ordinary wx child controls, keyboard focus,
    outside-click dismissal and Escape handling. Windows uses a layered colour
    key for the reserved corner pixels; other platforms use a matching region.
    """

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
            f"{CUSTOM_UI_NAME_PREFIX}:AutoLightChoicePopup",
        )
        self._owner_ref = weakref.ref(owner)
        self._buttons = []
        self._dismiss_notified = True
        self._closing = False
        self._popup_radius = LIGHT_SELECTOR_POPUP_RADIUS
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
            background=AUTO_LIGHT_THEME["surface"],
            border=AUTO_LIGHT_THEME["border"],
            radius=self._popup_radius,
            clear_background=self._transparent_corner_colour,
        )
        self._shell = shell
        # Keep the shell's reported background on the normal popup surface.
        # Custom-painted children clear against their parent's background, so
        # assigning the transparent corner key here would also make the empty
        # space around controls such as the scrollbar transparent.
        shell_sizer = wx.BoxSizer(wx.VERTICAL)
        # Use the shared clipped viewport so every option remains reachable
        # without relying on a platform-owned scrollbar or virtual layout.
        self._scroll = ModernScrollViewport(
            shell,
            background=AUTO_LIGHT_THEME["surface"],
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
        """Make the reserved popup-corner colour transparent on Windows.

        A colour-keyed layered frame keeps the dropdown's ordinary interactive
        child controls while removing the rectangular top-level window corners.
        Unlike a shaped native region, this does not composite rounded edge
        pixels against a temporary white backing surface.
        """
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
        """Refresh the platform-appropriate rounded popup boundary."""
        if os.name == "nt":
            self._windows_corner_transparency = (
                self._configure_windows_corner_transparency()
            )
            if self._windows_corner_transparency:
                return True

        # Linux, macOS and a failed Windows colour-key setup use the same
        # one-bit scanline region as the portable tooltip fallback.
        return _apply_rounded_window_shape(
            self,
            self._popup_radius,
        )

    def _on_size(self, event):
        """Refresh the rounded boundary whenever the popup is resized."""
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
        """Rebuild text rows or the optional four-column icon grid."""
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
                cols=LIGHT_SELECTOR_ICON_COLUMNS,
                vgap=_dip(self._list_content, LIGHT_SELECTOR_GRID_GAP),
                hgap=_dip(self._list_content, LIGHT_SELECTOR_GRID_GAP),
            )
            self._content.Add(grid, 0, wx.EXPAND)
            for index, label in enumerate(choices):
                button = ModernIconChoiceOption(
                    self._list_content,
                    label,
                    owner.GetIconBitmap(label, LIGHT_SELECTOR_ICON_SIZE),
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
        """Size, position, populate, and show the popup for one choice field."""
        choices = list(owner._choices)
        self.rebuild(owner, choices, owner.GetSelection())

        owner_rect = owner.GetScreenRect()
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
                _dip(owner, LIGHT_SELECTOR_MIN_WIDTH),
            )
            rows = max(
                1,
                (
                    len(choices)
                    + LIGHT_SELECTOR_ICON_COLUMNS
                    - 1
                )
                // LIGHT_SELECTOR_ICON_COLUMNS,
            )
            tile_height = _dip(owner, LIGHT_SELECTOR_TILE_HEIGHT)
            grid_gap = _dip(owner, LIGHT_SELECTOR_GRID_GAP)
            wanted_height = (
                rows * tile_height
                + max(0, rows - 1) * grid_gap
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
        width = min(width, max(_dip(owner, 260), work_area.width))
        height = min(max(minimum_height, wanted_height), maximum_height)

        # Center the popup on the owning selector instead of aligning the
        # popup's left edge with the field. The wider four-column icon window
        # therefore expands evenly to both sides whenever the display allows.
        x = owner_rect.x + int(round((owner_rect.width - width) / 2.0))
        y = owner_rect.bottom + _dip(owner, 4)
        if y + height > work_area.bottom:
            y = owner_rect.y - height - _dip(owner, 4)
        x = min(max(x, work_area.x), max(work_area.x, work_area.right - width))
        y = min(max(y, work_area.y), max(work_area.y, work_area.bottom - height))

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
        """Hide the dropdown once and synchronize the owning field."""
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
        """Apply one popup selection and return focus to the owning field."""
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
            # Defer hiding until wx has finished delivering the activation
            # change. This avoids changing top-level lifetime during the native
            # event that caused the deactivation.
            try:
                wx.CallAfter(self.Dismiss)
            except Exception:
                self.Dismiss()

    def _on_close(self, event):
        # Allow native destruction, including application shutdown and Alt+F4,
        # while keeping the owning field's open state synchronized.
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
        """Destroy the reusable frame without notifying an owner being deleted."""
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
    """Rounded composite choice field with a dark toggleable popup."""

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
        self._fill = AUTO_LIGHT_THEME["surface_alt"]
        self._radius = 9
        self._popup = None
        self._popup_open = False
        self._suppress_popup_until = 0.0
        self._icon_provider = icon_provider
        self._show_icons = bool(show_icons)

        self.SetBackgroundColour(self._fill)
        self.SetForegroundColour(AUTO_LIGHT_THEME["text"])
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # Keep the closed field compact while retaining comfortable hit space.
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
            child.SetForegroundColour(AUTO_LIGHT_THEME["text"])
            child.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # Keep a small left inset even when icons are disabled so the text never
        # touches the rounded outline. When icons are enabled, the conditional
        # spacer reserves the remainder of the icon slot without changing the
        # label's established alignment.
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
        """Switch between the icon grid and the compact text-only list."""
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
        """Return whether this field can display the visual icon grid."""
        provider = self._icon_provider
        if not self._show_icons or provider is None:
            return False
        try:
            return provider.available_count() > 0
        except Exception:
            return False

    def GetIconBitmap(self, choice, size, padding=0):
        """Return a popup icon bitmap or wx.NullBitmap when unavailable."""
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
        """Return a compact field icon or wx.NullBitmap when unavailable."""
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
            # Render directly from the original item texture. Thin sprites
            # such as torches contain one-pixel colored outlines that can be
            # damaged if an already scaled icon is resized a second time.
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
        """Return the index of a displayed value or wx.NOT_FOUND."""
        try:
            return self._choices.index(str(value))
        except ValueError:
            return wx.NOT_FOUND

    def SetSelection(self, selection):
        """Select one item by index without emitting a choice event."""
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
        """Return the current item index or wx.NOT_FOUND."""
        return self._selection

    def GetStringSelection(self):
        """Return the selected display name or an empty string."""
        if 0 <= self._selection < len(self._choices):
            return self._choices[self._selection]
        return ""

    def DoGetBestClientSize(self):
        """Provide wxPython's virtual best-size calculation for the selector."""
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        width = max(
            (dc.GetTextExtent(choice)[0] for choice in self._choices),
            default=120,
        )
        return wx.Size(width + _dip(self, 48), _dip(self, 42))

    def Enable(self, enable=True):
        """Synchronize enabled state across the selector and painted children."""
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
                AUTO_LIGHT_THEME["surface_alt"],
                AUTO_LIGHT_THEME["disabled"],
                AUTO_LIGHT_THEME["border_soft"],
            )
        if self._pressed:
            fill = AUTO_LIGHT_THEME["surface_pressed"]
        elif self._hovered or self._popup_open:
            fill = AUTO_LIGHT_THEME["surface_hover"]
        else:
            fill = AUTO_LIGHT_THEME["surface_alt"]
        border = (
            AUTO_LIGHT_THEME["accent_hover"]
            if self.HasFocus() or self._popup_open
            else AUTO_LIGHT_THEME["border"]
        )
        return fill, AUTO_LIGHT_THEME["text"], border

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

        # Paint the selected artwork directly in the choice field. Keeping the
        # icon inside the field's own paint pass preserves clearance from the
        # rounded focus border around thin sprites such as Soul Torch.
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
        # A top-level dropdown can deactivate before the click is delivered to
        # the underlying field. Suppress that same click from immediately
        # reopening the popup.
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


class DarkMessageDialog(wx.Dialog):
    """Self-themed replacement for wx.MessageDialog."""

    def __init__(self, parent, message, caption, style=wx.OK | wx.CENTRE):
        dialog_style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        super().__init__(parent, title=str(caption), style=dialog_style)
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoLightDialog",
        )
        self._message_style = int(style)
        self.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        self.SetMinSize((_dip(self, 390), _dip(self, 190)))

        root = wx.Panel(self, style=wx.BORDER_NONE | wx.CLIP_CHILDREN)
        _mark_custom_ui_owned(root)
        root.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        outer = wx.BoxSizer(wx.VERTICAL)

        title = _make_text(root, str(caption), point_size=13, bold=True)
        outer.Add(title, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _dip(root, 18))

        message_text = _make_text(root, str(message), muted=False)
        message_text.Wrap(_dip(root, 470))
        outer.Add(
            message_text,
            1,
            wx.EXPAND | wx.ALL,
            _dip(root, 18),
        )

        button_row = wx.BoxSizer(wx.HORIZONTAL)
        button_row.AddStretchSpacer(1)

        buttons = []
        if style & wx.YES_NO:
            buttons = [
                ("Yes", wx.ID_YES, not bool(style & wx.NO_DEFAULT)),
                ("No", wx.ID_NO, bool(style & wx.NO_DEFAULT)),
            ]
        elif style & wx.OK and style & wx.CANCEL:
            buttons = [
                ("OK", wx.ID_OK, True),
                ("Cancel", wx.ID_CANCEL, False),
            ]
        elif style & wx.CANCEL and not style & wx.OK:
            buttons = [("Cancel", wx.ID_CANCEL, True)]
        else:
            buttons = [("OK", wx.ID_OK, True)]

        default_button = None
        for label, result_id, is_default in buttons:
            button = ModernButton(
                root,
                label,
                primary=is_default,
                compact=True,
            )
            button.SetMinSize((_dip(root, 92), _dip(root, 36)))
            button.Bind(
                wx.EVT_BUTTON,
                lambda _event, modal_id=result_id: self.EndModal(modal_id),
            )
            button_row.Add(button, 0, wx.LEFT, _dip(root, 8))
            if is_default:
                default_button = button

        outer.Add(
            button_row,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            _dip(root, 18),
        )
        root.SetSizer(outer)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(root, 1, wx.EXPAND)
        self.SetSizer(dialog_sizer)
        self.Fit()
        size = self.GetSize()
        self.SetSize((max(size.width, _dip(self, 420)), max(size.height, _dip(self, 210))))
        self.CenterOnParent()

        if default_button is not None:
            try:
                default_button.SetFocus()
            except Exception:
                pass

        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            if self._message_style & wx.YES_NO:
                self.EndModal(wx.ID_NO)
            elif self._message_style & wx.CANCEL:
                self.EndModal(wx.ID_CANCEL)
            else:
                self.EndModal(wx.ID_OK)
            return
        event.Skip()


def _show_dark_message(
    message,
    caption="Message",
    style=wx.OK | wx.CENTRE,
    parent=None,
    *unused_position,
):
    """wx.MessageBox-compatible wrapper using the Auto Light palette."""
    dialog = DarkMessageDialog(parent, message, caption, style)
    try:
        return dialog.ShowModal()
    finally:
        dialog.Destroy()


class DarkActionPickerDialog(wx.Dialog):
    """Dark action picker used by Manage Plugin Files."""

    def __init__(
        self,
        parent,
        actions,
        initial_size=None,
        on_size_changed=None,
    ):
        super().__init__(
            parent,
            title="Manage Auto Light settings",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoLightSettingsDialog",
        )
        self._actions = list(actions)
        self._selection = wx.NOT_FOUND
        self._on_size_changed = on_size_changed
        self.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
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
        root.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        outer = wx.BoxSizer(wx.VERTICAL)

        title = _make_text(root, "MANAGE PLUGIN FILES", point_size=14, bold=True)
        outer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP, _dip(root, 18))

        self._description = _make_text(
            root,
            "Choose what to do with Auto Light.config.",
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
            background=AUTO_LIGHT_THEME["surface"],
            border=AUTO_LIGHT_THEME["border_soft"],
            radius=10,
        )
        card_sizer = wx.BoxSizer(wx.VERTICAL)

        # Use the shared clipped viewport so every action row remains visible
        # and scrollable at the dialog's default size.
        self._scroll = ModernScrollViewport(
            list_card,
            background=AUTO_LIGHT_THEME["surface"],
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
        """Synchronize the action-list content height and custom thumb."""
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
        """Return the selected action index or wx.NOT_FOUND."""
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
    """Rounded wrapper around a native text editor for reliable keyboard input."""

    _FORWARDED_EVENTS = (
        wx.EVT_TEXT,
        wx.EVT_TEXT_ENTER,
        wx.EVT_KILL_FOCUS,
        wx.EVT_SET_FOCUS,
    )

    def __init__(self, parent, value="", width=64):
        super().__init__(
            parent,
            background=AUTO_LIGHT_THEME["surface_alt"],
            border=AUTO_LIGHT_THEME["border"],
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
        self._text.SetBackgroundColour(AUTO_LIGHT_THEME["surface_alt"])
        self._text.SetForegroundColour(AUTO_LIGHT_THEME["text"])
        # Numeric values are intentionally larger than surrounding helper text
        # so they remain easy to read without increasing the field dimensions.
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
        # Native Windows text controls paint their baseline slightly above the
        # visual center. Keep the enlarged number one DPI-scaled pixel higher
        # while preserving the outer field size.
        sizer.AddSpacer(_dip(self, 8))
        sizer.Add(
            self._text,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT,
            _dip(self, 4),
        )
        # Leave the native editor clear of the painted lower border. Without
        # this small gap, wx.CLIP_CHILDREN lets the child cover the center of
        # the rounded outline even though the outer field itself is tall enough.
        sizer.AddSpacer(_dip(self, 2))
        self.SetSizer(sizer)
        self._text.Bind(wx.EVT_SET_FOCUS, self._on_focus_change)
        self._text.Bind(wx.EVT_KILL_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_LEFT_UP, lambda _event: self._text.SetFocus())

    def Bind(self, event, handler, source=None, id=wx.ID_ANY, id2=wx.ID_ANY):
        """Forward text and focus events to the native editor child."""
        if hasattr(self, "_text") and event in self._FORWARDED_EVENTS:
            return self._text.Bind(event, handler, source=source, id=id, id2=id2)
        return super().Bind(event, handler, source=source, id=id, id2=id2)

    def SetValue(self, value):
        """Set text and emit the native wx text-change behavior."""
        self._text.SetValue(str(value))

    def ChangeValue(self, value):
        """Set text without emitting a wx text event."""
        self._text.ChangeValue(str(value))

    def GetValue(self):
        """Return the native editor's current string value."""
        return self._text.GetValue()

    def Enable(self, enable=True):
        """Synchronize enabled state across the wrapper and native editor."""
        result = super().Enable(enable)
        self._text.Enable(enable)
        return result

    def _on_focus_change(self, event):
        self._border = (
            AUTO_LIGHT_THEME["accent_hover"]
            if self._text.HasFocus()
            else AUTO_LIGHT_THEME["border"]
        )
        self.Refresh(False)
        event.Skip()


# ---------------------------
# TOOLTIPS AND WINDOW SUPPORT
# ---------------------------

def _apply_rounded_window_shape(window, radius=10):
    """Clip a portable top-level window to the shared rounded scanline mask.

    Dropdown popups use this on Linux and macOS, while tooltips use it whenever
    their Windows per-pixel-alpha renderer is unavailable.
    """
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
    """Portable shaped help bubble used when layered windows are unavailable."""

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
            background=AUTO_LIGHT_THEME["surface"],
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
        """Show beside the anchor without stealing keyboard focus."""
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
    """Portable shaped tooltip displayed near the current pointer."""

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
            background=AUTO_LIGHT_THEME["surface"],
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
        """Update the bubble text and fit it to a bounded readable width."""
        try:
            self._label.SetLabel(str(text))
            self._label.Wrap(_dip(self._panel, 300))
            self._panel.Layout()
            self.GetSizer().Fit(self)
            _apply_rounded_window_shape(self, self._shape_radius)
        except Exception:
            pass

    def show_at_pointer(self, anchor):
        """Show beside the current pointer without taking keyboard focus."""
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
    """Return one wx colour as an RGBA tuple."""
    return (
        int(colour.Red()),
        int(colour.Green()),
        int(colour.Blue()),
        int(alpha),
    )


def _load_layered_tooltip_font(pixel_size):
    """Load a normal Windows UI font for the layered tooltip bitmap."""
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
    """Measure one Pillow text line while supporting older Pillow builds."""
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
    """Wrap tooltip text to a bounded pixel width."""
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
    """Return a Pillow RGBA image as premultiplied BGRA bytes for GDI."""
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
    """Per-pixel-alpha tooltip that bypasses wx shaped-window composition.

    The complete bubble is rendered into a transparent 32-bit bitmap and sent
    directly to UpdateLayeredWindow. Curved edge pixels therefore blend with
    the real Amulet interface underneath rather than a temporary white wx
    backing surface.
    """

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
        """Add the native layered, no-activate, click-through styles."""
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
        """Render a supersampled transparent tooltip bitmap."""
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
                AUTO_LIGHT_THEME["surface"],
            )
            text_rgba = _wx_colour_tuple(
                AUTO_LIGHT_THEME["text"],
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
        """Upload the current RGBA bitmap with per-pixel alpha."""
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
    """Layered console help bubble positioned beside its anchor."""

    def __init__(self, owner, text):
        super().__init__(owner, max_text_width=260)
        self._text = str(text)
        self._render_text(self._text)

    def show_for(self, anchor):
        """Position and display the layered console hint beside its anchor."""
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
    """Layered control tooltip positioned beside the current pointer."""

    def __init__(self, owner):
        super().__init__(owner, max_text_width=300)

    def set_text(self, text):
        self._text = str(text)
        self._render_text(self._text)
        if self._fallback is not None:
            self._fallback.set_text(self._text)

    def show_at_pointer(self, anchor):
        """Position and display the layered control hint beside the pointer."""
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

# -------------------------
# FLOATING WINDOW AND HOST
# -------------------------

class AutoLightWindow(wx.Frame):
    """Single modeless floating window owned by the Amulet top-level frame."""

    def __init__(self, owner, host):
        style = wx.DEFAULT_FRAME_STYLE
        style |= getattr(wx, "FRAME_FLOAT_ON_PARENT", 0)
        super().__init__(
            owner,
            title="Auto Light",
            size=FLOATING_DEFAULT_SIZE,
            style=style,
        )
        _mark_custom_ui_owned(self, f"{CUSTOM_UI_NAME_PREFIX}:AutoLight")
        self._host_ref = weakref.ref(host)
        self.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        self.SetMinSize(
            (
                _dip(self, FLOATING_MIN_SIZE[0]),
                _dip(self, FLOATING_MIN_SIZE[1]),
            )
        )
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def _on_close(self, event):
        """Persist window state and close the floating interface safely."""
        host = self._host_ref()
        owner_closing = False
        try:
            owner = self.GetParent()
            owner_closing = bool(owner is not None and owner.IsBeingDeleted())
        except Exception:
            owner_closing = False
        if (
            host is not None
            and not getattr(host, "_destroying", False)
            and not owner_closing
            and event.CanVeto()
        ):
            self.Hide()
            host._update_launcher_status(False)
            event.Veto()
            return
        event.Skip()

    def _on_show(self, event):
        """Keep the compact launcher synchronized with window visibility."""
        host = self._host_ref()
        if host is not None:
            host._update_launcher_status(bool(event.IsShown()))
        event.Skip()


class AutoLighting(wx.Panel, DefaultOperationUI):
    """Auto Light operation host and controller.

    Major behaviors:
    - Supports exact legacy-radius detection and calculated light coverage.
    - Places every light source exposed by the floating interface.
    - Supports row / grid spacing and spread spacing.
    - Optionally replaces approved plants / grass at placement positions.
    - Preserves Amulet selection, operation, undo and world communication.
    """

    SETTINGS_CONFIG_FILENAME = "Auto Light.config"
    SETTINGS_CONFIG_FORMAT_VERSION = 1
    SETTINGS_SAVE_DELAY_MS = 500
    MAX_SETTINGS_CONFIG_BYTES = 1024 * 1024

    # The settings viewport receives most vertical growth while the report
    # console receives a smaller share. This lets the console grow and shrink
    # slightly with the window without overtaking the settings area.
    SETTINGS_VIEWPORT_HEIGHT = 280
    SETTINGS_GROW_PROPORTION = 4
    CONSOLE_GROW_PROPORTION = 1
    # Keep a comfortable console height as the hard minimum. Extra vertical
    # space may still enlarge it slightly through the smaller grow proportion,
    # while shrinking the window never collapses the console below that limit.
    CONSOLE_MIN_TEXT_HEIGHT = 150
    CONSOLE_MIN_CARD_HEIGHT = 194
    FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT = 720
    CONSOLE_TOOLTIP_DELAY_MS = 700
    CONTROL_TOOLTIP_DELAY_MS = 700

    # Dark Mode UI recognizes this shared semantic name and preserves the
    # report console's intended black background and green text palette.
    CONSOLE_SEMANTIC_NAME = "AmuletPluginConsole:AutoLight"

    def __init__(self, parent, canvas, world, options_path):
        """Build the Amulet launcher host and the separate Auto Light window."""
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)

        self._destroying = False
        self._plugin_window = None
        self._window_has_been_shown = False
        self._console_visible = True
        self._scroll_refresh_pending = False
        self._scroll_refresh_call = None
        self._window_geometry_events_ready = False
        self._last_normal_window_size = list(FLOATING_DEFAULT_SIZE)
        self._last_manage_dialog_size = list(MANAGE_DIALOG_DEFAULT_SIZE)
        self._operation_running = False
        self._operation_ui_generation = 0
        self._operation_button_restore_call = None
        self._light_icon_cache = AmuletLightIconCache()
        self._console_help_window = None
        self._console_help_call = None
        self._console_help_hovered = False
        self._control_help_window = None
        self._control_help_call = None
        self._control_help_anchor_ref = None
        self._control_help_text = ""

        # Settings are persisted to one local JSON-backed config file. A short
        # debounce prevents rapid slider and text changes from causing excessive
        # disk writes. Malformed configs are preserved until manually repaired,
        # reset, imported over, or deleted by the user.
        self._settings_config_save_call = None
        self._settings_config_applying = False
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._settings_defaults = {}

        # The report remains owned by the operation host. Closing the floating
        # window only hides it, so worker callbacks can safely keep updating the
        # status and console while the operation continues.
        self._report_lines = []
        self._last_report_text = ""

        self._build_launcher_ui()
        self._build_floating_ui()
        self._initialize_settings_persistence()
        self._bind_floating_window_geometry_events()

        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_host_destroy)
        wx.CallAfter(self._show_plugin_window)

    def _build_launcher_ui(self):
        """Build the compact compatibility panel shown in Amulet's Operations tab."""
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)
        margin = 6

        title = wx.StaticText(self, label="Auto Light")
        try:
            font = title.GetFont()
            font.SetPointSize(max(font.GetPointSize(), 11))
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            title.SetFont(font)
        except Exception:
            pass
        outer.Add(
            title,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            margin,
        )

        description = wx.StaticText(
            self,
            label="Floating interface.",
        )
        outer.Add(
            description,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            margin,
        )

        self.open_window_button = ModernButton(
            self,
            "Open Window",
            primary=True,
            compact=True,
        )
        self.open_window_button.Bind(wx.EVT_BUTTON, self._show_plugin_window)
        self._set_control_tooltip(
            self.open_window_button,
            "Show, restore, and focus the existing Auto Light window.",
        )
        outer.Add(
            self.open_window_button,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            margin,
        )

        self.launcher_status = wx.StaticText(
            self,
            label="Opens automatically.",
        )
        outer.Add(
            self.launcher_status,
            0,
            wx.ALL | wx.EXPAND,
            margin,
        )
        self.SetMinSize((150, 130))
        self.SetSize((150, 130))

    def _create_card(self, parent, title, subtitle=None):
        """Create one rounded settings card and return its content sizer."""
        card = RoundedPanel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        card.SetSizer(sizer)
        heading = _make_text(card, title.upper(), point_size=9, bold=True)
        sizer.Add(heading, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, UI_CARD_PADDING)
        if subtitle:
            subtitle_control = _make_wrapped_text(
                card,
                subtitle,
                point_size=8,
                muted=True,
            )
            sizer.Add(subtitle_control, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, UI_CARD_PADDING)
        sizer.AddSpacer(_dip(card, 6))
        return card, sizer

    def _sync_main_content_width(self):
        """Center the responsive interface inside its configured width cap.

        The frame itself remains unrestricted. Below the cap, the content column
        follows the available client width. Above the cap, the horizontal root
        sizer gives the remaining space equally to its two stretch spacers.
        """
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
        """Update the centered content width when the frame client area changes."""
        self._sync_main_content_width()
        event.Skip()

    def _build_floating_ui(self):
        """Build the complete modern modeless Auto Light interface."""
        owner = wx.GetTopLevelParent(self) or self
        self._plugin_window = AutoLightWindow(owner, self)

        root = wx.Panel(
            self._plugin_window,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(root, f"{CUSTOM_UI_NAME_PREFIX}:AutoLightRoot")
        root.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        root.SetSizer(root_sizer)

        # Keep the complete interface centered inside a comfortable width while
        # allowing the outer frame to remain freely resizable.
        self._main_content_root = root
        self._main_content_panel = wx.Panel(
            root,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(
            self._main_content_panel,
            f"{CUSTOM_UI_NAME_PREFIX}:AutoLightMainContent",
        )
        self._main_content_panel.SetBackgroundColour(
            AUTO_LIGHT_THEME["window"]
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

        # Header
        header = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(header)
        header.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        header_sizer = wx.BoxSizer(wx.VERTICAL)
        header.SetSizer(header_sizer)
        title = _make_text(header, "AUTO LIGHT", point_size=18, bold=True)
        subtitle = _make_wrapped_text(
            header,
            "Automatic lighting with selection-aware placement and reporting",
            point_size=9,
            muted=True,
        )
        header_sizer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 16)
        header_sizer.Add(subtitle, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM | wx.EXPAND, 16)
        main_content_sizer.Add(header, 0, wx.EXPAND)

        # Scrollable settings area
        settings_host = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(settings_host)
        settings_host.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        settings_row = wx.BoxSizer(wx.HORIZONTAL)
        settings_host.SetSizer(settings_row)

        self.scroll = ModernScrollViewport(
            settings_host,
            background=AUTO_LIGHT_THEME["window"],
        )
        _mark_custom_ui_owned(self.scroll, f"{CUSTOM_UI_NAME_PREFIX}:AutoLightSettings")
        self.scroll.SetMinSize((-1, self.SETTINGS_VIEWPORT_HEIGHT))
        self.settings_content_panel = self.scroll.GetContentWindow()
        content = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetContentSizer(content)
        content.AddSpacer(_dip(self.scroll, 4))

        # Light source card
        light_card, light_sizer = self._create_card(
            self.settings_content_panel,
            "Light Source",
            "Choose the block Auto Light should place. Relevant placement "
            "options appear below.",
        )
        self.light_choice = ModernChoice(
            light_card,
            choices=[
                "Torch",
                "Soul Torch",
                "Copper Torch",
                "Lantern",
                "Soul Lantern",
                "Copper Lantern",
                "Exposed Copper Lantern",
                "Weathered Copper Lantern",
                "Oxidized Copper Lantern",
                "Copper Bulb",
                "Exposed Copper Bulb",
                "Weathered Copper Bulb",
                "Oxidized Copper Bulb",
                "Sea Lantern",
                "Firefly Bush",
            ],
            icon_provider=self._light_icon_cache,
            show_icons=False,
        )
        self.light_choice.SetSelection(0)
        self.light_choice.Bind(wx.EVT_CHOICE, self._on_light_change)
        self._set_control_tooltip(
            self.light_choice,
            "Choose the light type.",
        )
        light_sizer.Add(
            self.light_choice,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.show_light_icons_cb = ModernCheckBox(
            light_card,
            "Show light source icons",
            True,
        )
        self._set_control_tooltip(
            self.show_light_icons_cb,
            "Shows model-aware item / block artwork from Amulet's local "
            "resource-pack cache. If artwork is unavailable, Auto Light safely "
            "uses the normal text-only list.",
        )
        self.show_light_icons_cb.Bind(
            wx.EVT_CHECKBOX,
            self._on_light_icon_mode_change,
        )
        _tighten_gap_before_checkbox(light_sizer)
        light_sizer.Add(
            self.show_light_icons_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        # The ordinary compact checkbox gap remains part of this group. A
        # separate transition spacer is shown only when a source-specific group
        # follows, so source types such as Sea Lantern do not retain that larger
        # inter-section gap at the bottom of the card.
        light_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(light_sizer)
        self._source_options_transition_spacing = light_sizer.AddSpacer(
            UI_CHECKBOX_GROUP_TRANSITION_GAP
        )

        # Each source-specific section owns one nested sizer item. Controls stay
        # parented directly to the rounded card, so no rectangular child panel
        # can cover or flatten the card's painted lower border and corners.
        self.torch_group_sizer = wx.BoxSizer(wx.VERTICAL)
        self.torch_group_item = light_sizer.Add(
            self.torch_group_sizer,
            0,
            wx.EXPAND,
        )

        self.torch_group_label = _make_text(
            light_card,
            "Torch placement",
            point_size=9,
            bold=True,
        )
        self._set_control_tooltip(
            self.torch_group_label,
            "Controls how torches are placed.",
        )
        self.torch_group_sizer.Add(
            self.torch_group_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.allow_floor_torches = ModernCheckBox(
            light_card,
            "Allow floor torches",
            True,
        )
        self._set_control_tooltip(
            self.allow_floor_torches,
            "Allows torches to be placed on solid floors.",
        )
        _tighten_gap_before_checkbox(self.torch_group_sizer)
        self.torch_group_sizer.Add(
            self.allow_floor_torches,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.torch_group_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        self.allow_walls = ModernCheckBox(
            light_card,
            "Allow wall torches",
            True,
        )
        self._set_control_tooltip(
            self.allow_walls,
            "Allows torches on walls.",
        )
        _tighten_gap_before_checkbox(self.torch_group_sizer)
        self.torch_group_sizer.Add(
            self.allow_walls,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.torch_group_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(self.torch_group_sizer)

        self.lantern_group_sizer = wx.BoxSizer(wx.VERTICAL)
        self.lantern_group_item = light_sizer.Add(
            self.lantern_group_sizer,
            0,
            wx.EXPAND,
        )

        self.lantern_group_label = _make_text(
            light_card,
            "Lantern placement",
            point_size=9,
            bold=True,
        )
        self._set_control_tooltip(
            self.lantern_group_label,
            "Controls how lanterns are placed.",
        )
        self.lantern_group_sizer.Add(
            self.lantern_group_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.allow_floor_lanterns = ModernCheckBox(
            light_card,
            "Allow floor lanterns",
            True,
        )
        self._set_control_tooltip(
            self.allow_floor_lanterns,
            "Allows lanterns to be placed on solid floors.",
        )
        _tighten_gap_before_checkbox(self.lantern_group_sizer)
        self.lantern_group_sizer.Add(
            self.allow_floor_lanterns,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.lantern_group_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        self.allow_lanterns = ModernCheckBox(
            light_card,
            "Allow ceiling lanterns",
            True,
        )
        self._set_control_tooltip(
            self.allow_lanterns,
            "Allows lanterns to hang.",
        )
        _tighten_gap_before_checkbox(self.lantern_group_sizer)
        self.lantern_group_sizer.Add(
            self.allow_lanterns,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.lantern_group_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(self.lantern_group_sizer)

        self.copper_group_sizer = wx.BoxSizer(wx.VERTICAL)
        self.copper_group_item = light_sizer.Add(
            self.copper_group_sizer,
            0,
            wx.EXPAND,
        )

        self.copper_group_label = _make_text(
            light_card,
            "Copper options",
            point_size=9,
            bold=True,
        )
        self._set_control_tooltip(
            self.copper_group_label,
            "Controls waxed copper variants and copper bulb brightness.",
        )
        self.copper_group_sizer.Add(
            self.copper_group_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.copper_waxed_cb = ModernCheckBox(
            light_card,
            "Waxed copper variants",
            False,
        )
        self._set_control_tooltip(
            self.copper_waxed_cb,
            "Uses waxed copper lantern or copper bulb variants when available.",
        )
        _tighten_gap_before_checkbox(self.copper_group_sizer)
        self.copper_group_sizer.Add(
            self.copper_waxed_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.copper_group_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        self.copper_bulb_lit_cb = ModernCheckBox(
            light_card,
            "Lit copper bulbs",
            True,
        )
        self._set_control_tooltip(
            self.copper_bulb_lit_cb,
            "Places copper bulbs in their lit state.",
        )
        _tighten_gap_before_checkbox(self.copper_group_sizer)
        self.copper_group_sizer.Add(
            self.copper_bulb_lit_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.copper_group_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(self.copper_group_sizer)
        content.Add(light_card, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_CARD_MARGIN)

        # Detection card
        detection_card, detection_sizer = self._create_card(
            self.settings_content_panel,
            "Light Detection",
            "Use a fixed legacy radius or estimated Minecraft-style light decay.",
        )
        self.smart_coverage_cb = ModernCheckBox(
            detection_card,
            "Use calculated light coverage",
            False,
        )
        self._set_control_tooltip(
            self.smart_coverage_cb,
            "Uses estimated open-space block-light decay instead of the fixed "
            "Light Radius. The strongest nearby source wins; light levels are "
            "not added together. Newly placed lights join the calculation during "
            "this operation, while Light Spacing remains the minimum placement gap.",
        )
        self.smart_coverage_cb.Bind(wx.EVT_CHECKBOX, self._on_detection_mode_change)
        _tighten_gap_before_checkbox(detection_sizer)
        detection_sizer.Add(
            self.smart_coverage_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        detection_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(detection_sizer)

        self.radius_label = _make_text(detection_card, "Legacy light radius", point_size=9, bold=True)
        self._set_control_tooltip(
            self.radius_label,
            "Legacy mode uses this exact radius around pre-existing light-source "
            "blocks, regardless of how strong or weak they are.",
        )
        detection_sizer.Add(self.radius_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_CONTROL_GAP)

        self.radius_slider = ModernSlider(detection_card, value=4, minValue=0, maxValue=15)
        self._set_control_tooltip(
            self.radius_slider,
            "Legacy detection distance for light sources that already exist before "
            "the operation starts. Source brightness is ignored in this mode.",
        )
        self.radius_box = ModernTextField(detection_card, value="4", width=58)
        self._set_control_tooltip(
            self.radius_box,
            "Manual legacy light-radius input.",
        )
        self._bind(self.radius_slider, self.radius_box, 0, 15)
        self.radius_row = wx.BoxSizer(wx.HORIZONTAL)
        self.radius_row.Add(self.radius_slider, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.radius_row.Add(self.radius_box, 0, wx.ALIGN_CENTER_VERTICAL)
        self.radius_row_item = detection_sizer.Add(
            self.radius_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_SECTION_GAP,
        )

        self.treat_inactive_lights_as_lit_cb = ModernCheckBox(
            detection_card,
            "Treat inactive light sources as lit",
            True,
        )
        self._set_control_tooltip(
            self.treat_inactive_lights_as_lit_cb,
            "Counts supported light-emitting blocks as active even when their "
            "current block state is unlit or inactive.",
        )
        _tighten_gap_before_checkbox(detection_sizer)
        detection_sizer.Add(
            self.treat_inactive_lights_as_lit_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        detection_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(detection_sizer)
        content.Add(detection_card, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_CARD_MARGIN)

        # Placement card
        placement_card, placement_sizer = self._create_card(
            self.settings_content_panel,
            "Placement",
            "Control spacing, target restrictions, and optional plant replacement.",
        )
        self.spacing_label = _make_text(placement_card, "Light spacing", point_size=9, bold=True)
        self._set_control_tooltip(
            self.spacing_label,
            "Row / grid mode uses this as skipped blocks between lights. Example: "
            "5 skips five blocks, then places on the sixth block.",
        )
        placement_sizer.Add(self.spacing_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_CONTROL_GAP)
        self.spacing_slider = ModernSlider(placement_card, value=7, minValue=0, maxValue=15)
        self._set_control_tooltip(
            self.spacing_slider,
            "Row / grid mode: number of blocks skipped between lights. Spread "
            "mode uses this as the minimum placement distance.",
        )
        self.spacing_box = ModernTextField(placement_card, value="7", width=58)
        self._set_control_tooltip(
            self.spacing_box,
            "Manual spacing input.",
        )
        self._bind(self.spacing_slider, self.spacing_box, 0, 15)
        spacing_row = wx.BoxSizer(wx.HORIZONTAL)
        spacing_row.Add(self.spacing_slider, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        spacing_row.Add(self.spacing_box, 0, wx.ALIGN_CENTER_VERTICAL)
        placement_sizer.Add(spacing_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_SECTION_GAP)

        self.row_spacing_cb = ModernCheckBox(placement_card, "Use row / grid spacing", False)
        self._set_control_tooltip(
            self.row_spacing_cb,
            "Places lights in neat rows and columns instead of distributing them by minimum spacing.",
        )
        _tighten_gap_before_checkbox(placement_sizer)
        placement_sizer.Add(
            self.row_spacing_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        placement_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        self.replace_plants_cb = ModernCheckBox(placement_card, "Replace plants / grass with lights", False)
        self._set_control_tooltip(
            self.replace_plants_cb,
            "Allows plants, grass, flowers, and similar small blocks to be removed "
            "when a light is placed there.",
        )
        _tighten_gap_before_checkbox(placement_sizer)
        placement_sizer.Add(
            self.replace_plants_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        placement_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        self.air_only = ModernCheckBox(placement_card, "Only place on air", True)
        self._set_control_tooltip(
            self.air_only,
            "When enabled, lights are placed only in air, except approved plants "
            "when plant replacement is enabled.",
        )
        _tighten_gap_before_checkbox(placement_sizer)
        placement_sizer.Add(
            self.air_only,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        placement_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(placement_sizer)
        content.Add(placement_card, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_CARD_MARGIN)

        # Plugin files card
        files_card, files_sizer = self._create_card(
            self.settings_content_panel,
            "Plugin Files",
            "Save, import, export, repair, reset, or delete Auto Light.config.",
        )
        self.manage_settings_button = ModernButton(files_card, "Manage Plugin Files...", primary=False)
        self._set_control_tooltip(
            self.manage_settings_button,
            "Save, reset, repair, import, export, delete, or open the folder for Auto Light.config.",
        )
        self.manage_settings_button.Bind(wx.EVT_BUTTON, self._manage_settings)
        files_sizer.Add(self.manage_settings_button, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_CARD_PADDING)
        content.Add(files_card, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, UI_CARD_MARGIN)
        content.AddSpacer(_dip(self.scroll, 4))
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
        main_content_sizer.Add(
            settings_host,
            self.SETTINGS_GROW_PROPORTION,
            wx.EXPAND,
        )

        # Status and action area
        footer = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(footer)
        footer.SetBackgroundColour(AUTO_LIGHT_THEME["window"])
        footer_sizer = wx.BoxSizer(wx.VERTICAL)
        footer.SetSizer(footer_sizer)

        status_card = RoundedPanel(footer, background=AUTO_LIGHT_THEME["surface_alt"])
        status_sizer = wx.BoxSizer(wx.HORIZONTAL)
        status_card.SetSizer(status_sizer)
        status_caption = _make_text(status_card, "STATUS", point_size=8, bold=True, muted=True)
        self.status = _make_text(status_card, "Idle", point_size=9)
        self._set_control_tooltip(
            self.status,
            "Shows the current operation state and the last run's total time.",
        )
        status_sizer.Add(status_caption, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 12)
        status_sizer.Add(self.status, 1, wx.TOP | wx.RIGHT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL, 12)
        footer_sizer.Add(status_card, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, UI_FOOTER_MARGIN)

        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.place_lights_button = ModernButton(footer, "Place Lights", primary=True)
        self.place_lights_button.ProtectFromExternalDisable(True)
        self._set_control_tooltip(
            self.place_lights_button,
            "Run auto-lighting.",
        )
        self.place_lights_button.Bind(wx.EVT_BUTTON, self._run_operation)
        action_row.Add(self.place_lights_button, 2, wx.RIGHT | wx.EXPAND, 8)
        self.save_report_button = ModernButton(footer, "Save Report", primary=False)
        self.save_report_button.ProtectFromExternalDisable(True)
        self.save_report_button.Bind(wx.EVT_BUTTON, self._save_last_report)
        self.save_report_button.SetAvailable(False)
        self._set_control_tooltip(
            self.save_report_button,
            "Saves the latest Auto Light console report as a text file.",
        )
        action_row.Add(self.save_report_button, 1, wx.RIGHT | wx.EXPAND, 8)
        self.console_toggle_button = ModernButton(footer, "Hide Console", compact=True)
        self.console_toggle_button.Bind(wx.EVT_BUTTON, self._toggle_console)
        action_row.Add(self.console_toggle_button, 1, wx.EXPAND)
        footer_sizer.Add(action_row, 0, wx.ALL | wx.EXPAND, UI_FOOTER_MARGIN)
        main_content_sizer.Add(footer, 0, wx.EXPAND)

        # Report console
        self.console_card = RoundedPanel(
            self._main_content_panel,
            background=AUTO_LIGHT_THEME["console_bg"],
            border=AUTO_LIGHT_THEME["border"],
        )
        console_sizer = wx.BoxSizer(wx.VERTICAL)
        self.console_card.SetSizer(console_sizer)
        console_title = _make_text(self.console_card, "REPORT CONSOLE", point_size=8, bold=True, muted=True)
        console_sizer.Add(console_title, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 12)
        self.text = wx.TextCtrl(
            self.console_card,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.BORDER_NONE,
            size=(-1, self.CONSOLE_MIN_TEXT_HEIGHT),
        )
        _mark_custom_ui_owned(self.text, self.CONSOLE_SEMANTIC_NAME)
        self.text.SetForegroundColour(AUTO_LIGHT_THEME["console_text"])
        self.text.SetBackgroundColour(AUTO_LIGHT_THEME["console_bg"])
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
        self.text.SetMinSize((340, self.CONSOLE_MIN_TEXT_HEIGHT))
        self.console_card.SetMinSize((-1, self.CONSOLE_MIN_CARD_HEIGHT))
        self._console_help_text = (
            "Shows the settings, selection, light detection, placement results, "
            "warnings, timing, and performance information for the latest run."
        )
        for target in (console_title, self.console_card, self.text):
            target.Bind(wx.EVT_ENTER_WINDOW, self._on_console_help_enter)
            target.Bind(wx.EVT_LEAVE_WINDOW, self._on_console_help_leave)
        self.text.Bind(wx.EVT_LEFT_DOWN, self._on_console_text_interaction)
        self.text.Bind(wx.EVT_SET_FOCUS, self._on_console_text_interaction)
        console_sizer.Add(self.text, 1, wx.ALL | wx.EXPAND, 12)
        main_content_sizer.Add(
            self.console_card,
            self.CONSOLE_GROW_PROPORTION,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_FOOTER_MARGIN,
        )
        self._update_floating_minimum_size(resize_if_needed=True)

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(root, 1, wx.EXPAND)
        self._plugin_window.SetSizer(frame_sizer)
        self._plugin_window.Layout()
        self._sync_main_content_width()
        self._sync_settings_viewport()

        # The frame is still hidden while this method runs. Queue repaint passes
        # after wx has created and exposed every native child window so the first
        # visible frame uses the completed custom appearance.
        try:
            wx.CallAfter(self._refresh_scrolled_custom_controls)
            wx.CallLater(90, self._refresh_scrolled_custom_controls)
        except Exception:
            pass

    def _show_plugin_window(self, _event=None):
        """Show, restore, and focus the single Auto Light floating window."""
        window = self._plugin_window
        if window is None:
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
            self._update_launcher_status(True)
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
        """Center the floating window across Amulet's left frame border.

        When Amulet is restored and there is room on the monitor, the Auto Light
        window sits half outside and half inside the editor's left edge. If
        Amulet is maximized or too close to the screen edge, normal work-area
        clamping keeps the complete plugin window reachable.
        """
        window = self._plugin_window
        if window is None:
            return

        try:
            owner = window.GetParent()
        except Exception:
            owner = None
        if owner is None:
            try:
                owner = wx.GetTopLevelParent(self) or self
            except Exception:
                owner = self

        try:
            owner_rect = owner.GetScreenRect()
            window_size = window.GetSize()

            # Align the plugin window's center with the middle of Amulet's left
            # border. This intentionally places half of the plugin on either
            # side of that border whenever the monitor provides enough room.
            desired_x = int(owner_rect.x - (window_size.width / 2))
            desired_y = int(
                owner_rect.y
                + (owner_rect.height - window_size.height) / 2
            )
        except Exception:
            try:
                window.CentreOnParent()
            except Exception:
                window.CentreOnScreen()
            return

        try:
            display_index = wx.Display.GetFromWindow(owner)
            if display_index == wx.NOT_FOUND:
                owner_center = wx.Point(
                    int(owner_rect.x + owner_rect.width / 2),
                    int(owner_rect.y + owner_rect.height / 2),
                )
                display_index = wx.Display.GetFromPoint(owner_center)
            if display_index == wx.NOT_FOUND:
                display_index = 0

            work_area = wx.Display(display_index).GetClientArea()
            size = window.GetSize()
            max_x = work_area.x + max(0, work_area.width - size.width)
            max_y = work_area.y + max(0, work_area.height - size.height)
            desired_x = max(work_area.x, min(int(desired_x), max_x))
            desired_y = max(work_area.y, min(int(desired_y), max_y))
        except Exception:
            pass

        try:
            window.SetPosition((int(desired_x), int(desired_y)))
        except Exception:
            pass

    def _on_settings_scroll(self, event):
        """Repaint after the manual settings viewport finishes moving."""
        try:
            event.Skip()
        except Exception:
            pass

        # Repaint once immediately and again after the final wheel / thumb event.
        # Restarting the delayed call avoids painting only an intermediate scroll
        # position during a rapid sequence of wheel events.
        if not self._scroll_refresh_pending:
            self._scroll_refresh_pending = True
            try:
                wx.CallAfter(self._refresh_scrolled_custom_controls)
            except Exception:
                self._refresh_scrolled_custom_controls()

        pending = self._scroll_refresh_call
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass
        try:
            self._scroll_refresh_call = wx.CallLater(45, self._refresh_scrolled_custom_controls)
        except Exception:
            self._scroll_refresh_call = None

    def _refresh_scrolled_custom_controls(self):
        """Invalidate and synchronously repaint the visible settings subtree."""
        self._scroll_refresh_pending = False
        self._scroll_refresh_call = None
        scroll = getattr(self, "scroll", None)
        if scroll is None:
            return

        try:
            scroll.Refresh(True)
        except Exception:
            pass

        pending = [scroll]
        seen = set()
        while pending:
            parent = pending.pop()
            marker = id(parent)
            if marker in seen:
                continue
            seen.add(marker)
            try:
                children = list(parent.GetChildren())
            except Exception:
                children = []
            for child in children:
                pending.append(child)
                try:
                    if child.IsShownOnScreen():
                        child.Refresh(True)
                except Exception:
                    try:
                        child.Refresh(True)
                    except Exception:
                        pass

        try:
            scroll.Update()
        except Exception:
            pass

        # Paint the choice after the complete viewport has finished updating.
        # Raising it keeps the field above its rounded card after rapid movement.
        choice = getattr(self, "light_choice", None)
        if choice is not None:
            try:
                choice.Raise()
            except Exception:
                pass
            try:
                choice.Refresh(False)
                choice.Update()
            except Exception:
                pass

    def _bind_floating_window_geometry_events(self):
        """Start saving user-resized window dimensions after config loading."""
        window = self._plugin_window
        if window is None:
            return
        try:
            window.Bind(wx.EVT_SIZE, self._on_plugin_window_size)
            self._window_geometry_events_ready = True
        except Exception:
            self._window_geometry_events_ready = False

    def _on_plugin_window_size(self, event):
        """Repaint resized custom controls and debounce persistence of the size."""
        try:
            event.Skip()
        except Exception:
            pass

        window = self._plugin_window
        if window is None:
            return
        try:
            window.Refresh(False)
            wx.CallAfter(self._refresh_floating_layout)
        except Exception:
            pass

        if not self._window_geometry_events_ready or self._settings_config_applying:
            return
        try:
            if window.IsIconized() or window.IsMaximized():
                return
            size = window.GetSize()
            minimum_width, minimum_height = self._current_floating_minimum_size()
            self._last_normal_window_size = [
                max(minimum_width, int(size.width)),
                max(minimum_height, int(size.height)),
            ]
        except Exception:
            pass
        self._schedule_settings_config_save()

    def _current_window_size_config(self):
        """Return the current normal floating-frame size as JSON-safe data."""
        window = self._plugin_window
        if window is None:
            return list(self._last_normal_window_size)
        try:
            if window.IsIconized() or window.IsMaximized():
                return list(self._last_normal_window_size)
            size = window.GetSize()
            minimum_width, minimum_height = self._current_floating_minimum_size()
            width = max(minimum_width, int(size.width))
            height = max(minimum_height, int(size.height))
            self._last_normal_window_size = [width, height]
            return [width, height]
        except Exception:
            return list(self._last_normal_window_size)

    def _apply_saved_window_size(self, data):
        """Restore a validated saved floating-frame size without restoring position."""
        window = self._plugin_window
        if window is None or not isinstance(data, dict):
            return
        ui_data = data.get("ui")
        if not isinstance(ui_data, dict):
            return
        saved_size = ui_data.get("window_size")
        if (
            not isinstance(saved_size, (list, tuple))
            or len(saved_size) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in saved_size)
        ):
            return

        minimum_width, minimum_height = self._current_floating_minimum_size()
        width = max(minimum_width, int(saved_size[0]))
        height = max(minimum_height, int(saved_size[1]))
        try:
            display_index = wx.Display.GetFromWindow(self.open_window_button)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work_area = wx.Display(display_index).GetClientArea()
            width = min(width, max(minimum_width, work_area.width))
            height = min(height, max(minimum_height, work_area.height))
        except Exception:
            pass
        self._last_normal_window_size = [width, height]
        try:
            window.SetSize((width, height))
            window.Layout()
        except Exception:
            pass

    def _current_manage_dialog_size_config(self):
        """Return the last normal Manage Plugin Files size as JSON-safe data."""
        try:
            width = max(
                MANAGE_DIALOG_MIN_SIZE[0],
                int(self._last_manage_dialog_size[0]),
            )
            height = max(
                MANAGE_DIALOG_MIN_SIZE[1],
                int(self._last_manage_dialog_size[1]),
            )
            self._last_manage_dialog_size = [width, height]
        except Exception:
            self._last_manage_dialog_size = list(MANAGE_DIALOG_DEFAULT_SIZE)
        return list(self._last_manage_dialog_size)

    def _remember_manage_dialog_size(self, dialog):
        """Remember a resized Manage Plugin Files dialog and queue a save."""
        if dialog is None or self._settings_config_applying:
            return
        try:
            if dialog.IsIconized() or dialog.IsMaximized():
                return
        except Exception:
            pass
        try:
            size = dialog.GetSize()
            self._last_manage_dialog_size = [
                max(MANAGE_DIALOG_MIN_SIZE[0], int(size.width)),
                max(MANAGE_DIALOG_MIN_SIZE[1], int(size.height)),
            ]
        except Exception:
            return
        self._schedule_settings_config_save()

    def _apply_saved_manage_dialog_size(self, data):
        """Restore a validated Manage Plugin Files size for its next opening."""
        if not isinstance(data, dict):
            return
        ui_data = data.get("ui")
        if not isinstance(ui_data, dict):
            return
        saved_size = ui_data.get("manage_window_size")
        if (
            not isinstance(saved_size, (list, tuple))
            or len(saved_size) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in saved_size
            )
        ):
            return
        self._last_manage_dialog_size = [
            max(MANAGE_DIALOG_MIN_SIZE[0], int(saved_size[0])),
            max(MANAGE_DIALOG_MIN_SIZE[1], int(saved_size[1])),
        ]

    def _update_launcher_status(self, is_open):
        """Reflect the floating window state in the Amulet launcher panel."""
        try:
            if is_open:
                self.launcher_status.SetLabel("Status: Open")
                self.open_window_button.SetLabel("Focus Window")
            else:
                self.launcher_status.SetLabel("Status: Closed")
                self.open_window_button.SetLabel("Open Window")
            self.Layout()
        except Exception:
            pass

    def _begin_operation_ui(self):
        """Enter a deliberate busy state before Auto Light starts processing."""
        self._console_help_hovered = False
        self._hide_control_help()
        self._hide_console_help()
        self._operation_ui_generation += 1
        generation = self._operation_ui_generation
        self._operation_running = True

        pending = self._operation_button_restore_call
        self._operation_button_restore_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

        try:
            # Keep the native wx control enabled. Busy state blocks activation
            # and supplies the disabled-looking palette without relying on
            # Amulet / wx to restore Enable(True) after the operation.
            self.place_lights_button.SetAvailable(True)
            self.place_lights_button.SetLabel("Processing...")
            self.place_lights_button.SetBusy(True)
            self.place_lights_button.Refresh(False)
        except Exception:
            pass
        return generation

    def _restore_operation_buttons(self, generation):
        """Restore button state after Amulet has finished its operation cleanup."""
        if self._destroying or generation != self._operation_ui_generation:
            return
        if self._operation_running:
            return

        try:
            self.place_lights_button.SetAvailable(True)
            self.place_lights_button.SetBusy(False)
            self.place_lights_button.SetLabel("Place Lights")
            self.place_lights_button.Refresh(False)
            self.place_lights_button.Update()
        except Exception:
            pass

        try:
            self.save_report_button.SetAvailable(bool(self._last_report_text))
            self.save_report_button.Refresh(False)
        except Exception:
            pass

    def _finish_operation_ui(self, status_label, generation):
        """Apply the completed status and reliably restore the action buttons."""
        if self._destroying or generation != self._operation_ui_generation:
            return

        self._operation_running = False
        try:
            self.status.SetLabel(status_label)
        except Exception:
            pass

        self._restore_operation_buttons(generation)

        # Amulet may update the source button more than once while unwinding
        # canvas.run_operation. Reassert the intended custom state across a
        # short bounded settle window instead of relying on one exact delay.
        self._schedule_operation_button_restore(generation, 0)

    def _schedule_operation_button_restore(self, generation, attempt):
        """Reassert final action-button state while Amulet cleanup settles."""
        delays = (80, 180, 320, 520, 800)
        if (
            self._destroying
            or generation != self._operation_ui_generation
            or self._operation_running
            or attempt >= len(delays)
        ):
            return
        try:
            self._operation_button_restore_call = wx.CallLater(
                delays[attempt],
                self._settle_operation_buttons,
                generation,
                attempt,
            )
        except Exception:
            self._operation_button_restore_call = None

    def _settle_operation_buttons(self, generation, attempt):
        """Run one bounded post-operation button-state correction pass."""
        self._operation_button_restore_call = None
        if (
            self._destroying
            or generation != self._operation_ui_generation
            or self._operation_running
        ):
            return
        self._restore_operation_buttons(generation)
        self._schedule_operation_button_restore(generation, attempt + 1)

    def _current_floating_minimum_size(self):
        """Return the active minimum frame size for the current console state."""
        minimum_height = (
            self.FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT
            if self._console_visible
            else FLOATING_MIN_SIZE[1]
        )
        return FLOATING_MIN_SIZE[0], minimum_height

    def _update_floating_minimum_size(self, resize_if_needed=False):
        """Keep the visible console from being clipped below its usable height."""
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

    def _tooltip_targets(self, window):
        """Return one control and its current child windows without duplicates."""
        result = []
        stack = [window]
        seen = set()
        while stack:
            current = stack.pop()
            if current is None or id(current) in seen:
                continue
            seen.add(id(current))
            result.append(current)
            try:
                stack.extend(list(current.GetChildren()))
            except Exception:
                pass
        return result

    def _set_control_tooltip(self, window, text):
        """Attach one custom dark pointer tooltip to a control subtree."""
        if window is None or not str(text).strip():
            return
        tooltip_text = str(text)
        root_ref = weakref.ref(window)
        for target in self._tooltip_targets(window):
            try:
                unset_tooltip = getattr(target, "UnsetToolTip", None)
                if callable(unset_tooltip):
                    unset_tooltip()
                else:
                    target.SetToolTip(None)
            except Exception:
                pass

            def on_enter(event, anchor_ref=root_ref, value=tooltip_text):
                self._on_control_help_enter(event, anchor_ref, value)

            def on_leave(event, anchor_ref=root_ref):
                self._on_control_help_leave(event, anchor_ref)

            def on_interaction(event):
                self._hide_control_help()
                try:
                    event.Skip()
                except Exception:
                    pass

            try:
                target.Bind(wx.EVT_ENTER_WINDOW, on_enter)
                target.Bind(wx.EVT_LEAVE_WINDOW, on_leave)
                target.Bind(wx.EVT_LEFT_DOWN, on_interaction)
                target.Bind(wx.EVT_RIGHT_DOWN, on_interaction)
                target.Bind(wx.EVT_MIDDLE_DOWN, on_interaction)
                target.Bind(wx.EVT_SET_FOCUS, on_interaction)
            except Exception:
                pass

    def _cancel_control_help(self):
        """Cancel a pending normal-control tooltip display."""
        pending = self._control_help_call
        self._control_help_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _hide_control_help(self, clear_anchor=True):
        """Dismiss the current control tooltip and cancel delayed callbacks."""
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
        """Schedule one reliable tooltip for a control and its child windows."""
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
        """Hide only after the pointer has left the complete control tree."""
        try:
            event.Skip()
        except Exception:
            pass

        # Composite custom controls emit leave / enter pairs while the pointer
        # moves between their child windows. Defer the decision until wx has
        # updated the pointer position so those internal transitions do not
        # randomly cancel the pending tooltip.
        try:
            wx.CallAfter(
                self._hide_control_help_if_pointer_left,
                anchor_ref,
            )
        except Exception:
            self._hide_control_help_if_pointer_left(anchor_ref)

    def _hide_control_help_if_pointer_left(self, anchor_ref):
        """Dismiss a tooltip only when its original root is no longer hovered."""
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
        """Show a pending tooltip only while its complete control is hovered."""
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
                # A click can overlap the delayed callback. Retry briefly while
                # the pointer remains over the same control instead of silently
                # consuming that hover for the rest of the visit.
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
        """Cancel a pending report-console tooltip display."""
        pending = self._console_help_call
        self._console_help_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _hide_console_help(self):
        """Dismiss the report-console tooltip without changing console state."""
        self._cancel_console_help()
        window = self._console_help_window
        if window is not None:
            try:
                window.dismiss()
            except Exception:
                pass

    def _on_console_help_enter(self, event):
        """Schedule the console tooltip only while the plugin is idle."""
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
        """Hide the console tooltip after the pointer leaves its card."""
        try:
            event.Skip()
        except Exception:
            pass
        try:
            screen_point = wx.GetMousePosition()
            console_rect = self.console_card.GetScreenRect()
            if console_rect.Contains(screen_point):
                return
        except Exception:
            pass
        self._console_help_hovered = False
        self._hide_console_help()

    def _on_console_text_interaction(self, event):
        """Never allow the help bubble to interfere with text selection / copying."""
        self._console_help_hovered = False
        self._hide_console_help()
        try:
            event.Skip()
        except Exception:
            pass

    def _show_console_help(self):
        """Show the console hint only while it remains safe and unobtrusive."""
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

    def _apply_saved_console_visibility(self, data):
        """Restore the persisted console visibility without emitting events."""
        visible = True
        try:
            ui_data = data.get("ui", {}) if isinstance(data, dict) else {}
            saved = ui_data.get("console_visible", True)
            if isinstance(saved, bool):
                visible = saved
        except Exception:
            visible = True
        self._console_visible = bool(visible)
        try:
            self.console_card.Show(self._console_visible)
            self.console_toggle_button.SetLabel(
                "Hide Console" if self._console_visible else "Show Console"
            )
            self._hide_console_help()
            self._update_floating_minimum_size(resize_if_needed=self._console_visible)
            self._refresh_floating_layout()
        except Exception:
            pass

    def _toggle_console(self, _event=None):
        """Collapse or restore the report console without destroying its content."""
        self._console_visible = not self._console_visible
        self.console_card.Show(self._console_visible)
        self.console_toggle_button.SetLabel(
            "Hide Console" if self._console_visible else "Show Console"
        )
        self._hide_console_help()
        self._update_floating_minimum_size(resize_if_needed=self._console_visible)
        self._refresh_floating_layout()
        self._schedule_settings_config_save()

    def _sync_settings_viewport(self):
        """Lay out the complete settings viewport and update its scrollbar."""
        scroll = getattr(self, "scroll", None)
        if scroll is None:
            return
        try:
            scroll._modern_sync_layout()
        except Exception:
            pass
        try:
            self.settings_scrollbar.sync()
        except Exception:
            pass

    def _refresh_floating_layout(self):
        """Recalculate the floating window after dynamic visibility changes."""
        try:
            self._sync_settings_viewport()
        except Exception:
            pass
        try:
            self._plugin_window.Layout()
            self._plugin_window.Refresh(False)
        except Exception:
            pass

    def _on_host_destroy(self, event):
        """Destroy the floating window when Amulet unloads this operation host."""
        try:
            if event.GetEventObject() is not self:
                event.Skip()
                return
        except Exception:
            pass
        self._destroying = True
        pending_restore = self._operation_button_restore_call
        self._operation_button_restore_call = None
        if pending_restore is not None:
            try:
                pending_restore.Stop()
            except Exception:
                pass
        self._stop_pending_settings_save()
        self._hide_control_help()
        control_help_window = self._control_help_window
        self._control_help_window = None
        if control_help_window is not None:
            try:
                control_help_window.Destroy()
            except Exception:
                pass
        self._hide_console_help()
        help_window = self._console_help_window
        self._console_help_window = None
        if help_window is not None:
            try:
                help_window.Destroy()
            except Exception:
                pass
        try:
            self._write_settings_config(create_if_missing=True)
        except Exception:
            pass
        window = self._plugin_window
        self._plugin_window = None
        if window is not None:
            try:
                window.Destroy()
            except Exception:
                pass
        event.Skip()

    # Amulet calls these lifecycle methods outside this module. They are
    # intentionally retained even though ordinary static call searches do not
    # show an in-file caller.
    def bind_events(self):
        """Connect selection handlers when Amulet activates the operation."""
        super().bind_events()
        self._selection.bind_events()
        self._selection.enable()

    def enable(self):
        """Enable block selection while the operation panel remains open."""
        self._selection = BlockSelectionBehaviour(self.canvas)
        self._selection.enable()

    # =========================
    # SETTINGS PERSISTENCE
    # =========================
    def _get_settings_config_path(self):
        """Return the stable local path used for Auto Light.config."""
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            root = Path(local_app_data)
        else:
            root = Path.home() / "AppData" / "Local"

        return (
            root
            / "AmuletTeam"
            / "AmuletMapEditor"
            / "Config"
            / "plugins"
            / "edit_plugins"
            / self.SETTINGS_CONFIG_FILENAME
        )

    def _settings_control_registry(self):
        """Maps stable config keys to every persistent user setting."""
        control_names = (
            "light_choice",
            "show_light_icons_cb",
            "radius_slider",
            "smart_coverage_cb",
            "treat_inactive_lights_as_lit_cb",
            "spacing_slider",
            "row_spacing_cb",
            "replace_plants_cb",
            "allow_floor_torches",
            "allow_walls",
            "allow_floor_lanterns",
            "allow_lanterns",
            "copper_waxed_cb",
            "copper_bulb_lit_cb",
            "air_only",
        )

        registry = {}
        for name in control_names:
            control = getattr(self, name, None)
            if control is not None:
                registry[name] = control
        return registry

    def _read_settings_control_value(self, control):
        """Converts one supported wx control into JSON-safe data."""
        if isinstance(control, (wx.CheckBox, ModernCheckBox)):
            return bool(control.GetValue())
        if isinstance(control, (wx.Choice, ModernChoice)):
            return str(control.GetStringSelection())
        if isinstance(control, (wx.Slider, ModernSlider)):
            return int(control.GetValue())
        raise TypeError(f"Unsupported settings control: {type(control)!r}")

    def _apply_settings_control_value(self, control, value):
        """Applies one validated saved value to a supported wx control."""
        try:
            if isinstance(control, (wx.CheckBox, ModernCheckBox)):
                if not isinstance(value, bool):
                    return False
                control.SetValue(value)
                return True

            if isinstance(control, (wx.Choice, ModernChoice)):
                if not isinstance(value, str):
                    return False
                index = control.FindString(value)
                if index == wx.NOT_FOUND:
                    return False
                control.SetSelection(index)
                return True

            if isinstance(control, (wx.Slider, ModernSlider)):
                if isinstance(value, bool) or not isinstance(value, int):
                    return False
                minimum = control.GetMin()
                maximum = control.GetMax()
                if value < minimum or value > maximum:
                    return False
                control.SetValue(value)
                return True
        except Exception:
            return False

        return False

    def _collect_current_settings_config(self):
        """Collects the current persistent settings in the config format."""
        settings = {}
        for key, control in self._settings_control_registry().items():
            try:
                settings[key] = self._read_settings_control_value(control)
            except Exception:
                continue

        return {
            "format_version": self.SETTINGS_CONFIG_FORMAT_VERSION,
            "plugin": "Auto Light",
            "settings": settings,
            "ui": {
                "window_size": self._current_window_size_config(),
                "manage_window_size": self._current_manage_dialog_size_config(),
                "console_visible": bool(self._console_visible),
            },
        }

    def _capture_settings_defaults(self):
        """Captures plugin-defined defaults before saved values are loaded."""
        self._settings_defaults = self._collect_current_settings_config()

    def _load_settings_config_data(self, path):
        """Loads and validates a JSON config without modifying the file."""
        try:
            path = Path(path)
            if not path.is_file():
                return None
            if path.stat().st_size > self.MAX_SETTINGS_CONFIG_BYTES:
                raise ValueError("settings file exceeds the 1 MiB safety limit")

            with path.open("r", encoding="utf-8-sig") as handle:
                data = json.load(handle)

            if not isinstance(data, dict):
                raise ValueError("top-level JSON value must be an object")
            if not isinstance(data.get("settings", {}), dict):
                raise ValueError("'settings' must be a JSON object")
            return data
        except Exception as exc:
            self._settings_config_load_error = str(exc)
            return None

    def _apply_settings_config_data(self, data):
        """Apply recognized values while retaining unknown data for compatibility."""
        self._settings_config_applying = True
        try:
            saved_settings = data.get("settings", {})
            for key, control in self._settings_control_registry().items():
                if key in saved_settings:
                    self._apply_settings_control_value(
                        control,
                        saved_settings[key],
                    )

            # Text boxes mirror their sliders and are intentionally not stored
            # as duplicate settings.
            self.radius_box.ChangeValue(str(self.radius_slider.GetValue()))
            self.spacing_box.ChangeValue(str(self.spacing_slider.GetValue()))

            try:
                self.light_choice.SetShowIcons(
                    self.show_light_icons_cb.GetValue()
                )
            except Exception:
                pass
            # Restore console visibility before window dimensions so a saved
            # hidden-console height of 580 pixels is not clamped to the
            # visible-console minimum of 720 pixels during startup.
            self._apply_saved_console_visibility(data)
            self._apply_saved_window_size(data)
            self._apply_saved_manage_dialog_size(data)
            self._update_ui_visibility()
        finally:
            self._settings_config_applying = False

    def _merge_settings_config_data(self, existing):
        """Preserves unknown keys while updating recognized current values."""
        merged = dict(existing) if isinstance(existing, dict) else {}
        current = self._collect_current_settings_config()

        merged["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        merged["plugin"] = "Auto Light"

        existing_settings = merged.get("settings")
        if not isinstance(existing_settings, dict):
            existing_settings = {}
        existing_settings.update(current["settings"])
        merged["settings"] = existing_settings

        existing_ui = merged.get("ui")
        if not isinstance(existing_ui, dict):
            existing_ui = {}
        current_ui = current.get("ui", {})
        if isinstance(current_ui, dict):
            existing_ui.update(current_ui)
        merged["ui"] = existing_ui
        return merged

    def _write_text_atomically(self, destination, content):
        """Atomically replaces a UTF-8 text file after a complete flush."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
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
                handle.write(content)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except Exception:
                    pass
                temporary_path = Path(handle.name)

            os.replace(str(temporary_path), str(destination))
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except Exception:
                    pass

    def _write_settings_config(self, create_if_missing=True):
        """Writes current settings while preserving a malformed existing file."""
        if self._settings_config_applying:
            return False

        path = self._get_settings_config_path()
        if not create_if_missing and not path.is_file():
            return False

        existing = None
        if path.is_file():
            self._settings_config_load_error = ""
            existing = self._load_settings_config_data(path)
            if existing is None and self._settings_config_load_error:
                self._settings_config_write_error = (
                    "The existing settings file is malformed or unreadable. "
                    "It was preserved and was not overwritten."
                )
                return False

        merged = self._merge_settings_config_data(existing)
        content = json.dumps(
            merged,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        try:
            self._write_text_atomically(path, content)
            self._settings_config_load_error = ""
            self._settings_config_write_error = ""
            return True
        except Exception as exc:
            self._settings_config_write_error = str(exc)
            return False

    def _schedule_settings_config_save(self, event=None):
        """Restarts the 500 ms save delay after a user setting changes."""
        if self._settings_config_applying:
            try:
                if event is not None:
                    event.Skip()
            except Exception:
                pass
            return

        pending = self._settings_config_save_call
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

        try:
            self._settings_config_save_call = wx.CallLater(
                self.SETTINGS_SAVE_DELAY_MS,
                self._save_settings_config_after_delay,
            )
        except Exception:
            self._write_settings_config(create_if_missing=True)

        try:
            if event is not None:
                event.Skip()
        except Exception:
            pass

    def _save_settings_config_after_delay(self):
        """Writes settings after the debounce delay expires."""
        self._settings_config_save_call = None
        self._write_settings_config(create_if_missing=True)

    def _bind_settings_persistence_events(self):
        """Binds persistence to controls without duplicating custom handlers."""
        custom_controls = (
            self.light_choice,
            self.show_light_icons_cb,
            self.smart_coverage_cb,
            self.radius_slider,
            self.spacing_slider,
        )

        for control in self._settings_control_registry().values():
            if any(control is custom for custom in custom_controls):
                continue
            try:
                if isinstance(control, (wx.CheckBox, ModernCheckBox)):
                    control.Bind(
                        wx.EVT_CHECKBOX,
                        self._schedule_settings_config_save,
                    )
                elif isinstance(control, (wx.Choice, ModernChoice)):
                    control.Bind(
                        wx.EVT_CHOICE,
                        self._schedule_settings_config_save,
                    )
            except Exception:
                continue

    def _initialize_settings_persistence(self):
        """Captures defaults, loads saved settings, and enables auto-saving."""
        self._capture_settings_defaults()
        path = self._get_settings_config_path()
        self._settings_config_load_error = ""
        data = self._load_settings_config_data(path)

        if data is not None:
            self._apply_settings_config_data(data)
            # Add defaults introduced by a newer version while preserving all
            # unknown keys from the existing file.
            self._write_settings_config(create_if_missing=False)
        else:
            self._update_ui_visibility()
            if path.is_file() and self._settings_config_load_error:
                self.status.SetLabel(
                    "Settings file needs repair. Use Manage settings."
                )

        try:
            self.light_choice.SetShowIcons(
                self.show_light_icons_cb.GetValue()
            )
        except Exception:
            pass
        self._bind_settings_persistence_events()

    def _stop_pending_settings_save(self):
        """Stops a queued save before an explicit file-management action."""
        pending = self._settings_config_save_call
        self._settings_config_save_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _reset_settings_to_defaults(self):
        """Applies defaults and intentionally rewrites the active config."""
        defaults = self._settings_defaults
        if not isinstance(defaults, dict):
            return False

        self._stop_pending_settings_save()
        normalized = json.dumps(
            defaults,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        try:
            self._write_text_atomically(
                self._get_settings_config_path(),
                normalized,
            )
        except Exception as exc:
            self._settings_config_write_error = str(exc)
            return False

        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_config_data(defaults)
        return True

    def _repair_json_missing_line_commas(self, content):
        """Adds only clearly missing commas between adjacent object entries."""
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
                or re.search(
                    r"(?:true|false|null|-?\d+(?:\.\d+)?)$",
                    stripped,
                )
            ):
                repaired[index] = current + ","

        return "\n".join(repaired)

    def _attempt_parse_repaired_settings_config(self, content):
        """Attempts bounded, data-only repairs and reports what succeeded."""
        repairs = []

        def try_json(candidate, repair_name):
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    if repair_name:
                        repairs.append(repair_name)
                    return data
            except Exception:
                pass
            return None

        normalized = content.lstrip("\ufeff")
        data = try_json(normalized, "")
        if data is not None:
            return data, repairs

        without_trailing_commas = re.sub(
            r",(\s*[}\]])",
            r"\1",
            normalized,
        )
        data = try_json(without_trailing_commas, "removed trailing commas")
        if data is not None:
            return data, repairs

        with_line_commas = self._repair_json_missing_line_commas(
            without_trailing_commas
        )
        data = try_json(with_line_commas, "restored missing entry commas")
        if data is not None:
            return data, repairs

        # ast.literal_eval is data-only. It can recover single quotes and
        # Python-style True / False / None without executing code.
        try:
            literal_data = ast.literal_eval(with_line_commas)
            if isinstance(literal_data, dict):
                repairs.append("normalized Python-style JSON values")
                return literal_data, repairs
        except Exception:
            pass

        return None, repairs

    def _validate_repaired_settings_config(self, data):
        """Validates the minimum structure required for a safe repair."""
        if not isinstance(data, dict):
            return False, "The top-level value is not an object."
        if not isinstance(data.get("settings", {}), dict):
            return False, "The settings entry is not an object."
        return True, ""

    def _merge_recovered_settings_config_data(self, recovered):
        """Preserves recovered values and adds only missing current defaults."""
        merged = dict(recovered) if isinstance(recovered, dict) else {}
        defaults = (
            self._settings_defaults
            if isinstance(self._settings_defaults, dict)
            else self._collect_current_settings_config()
        )

        merged["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        merged["plugin"] = "Auto Light"

        recovered_settings = merged.get("settings")
        if not isinstance(recovered_settings, dict):
            recovered_settings = {}

        default_settings = defaults.get("settings", {})
        if isinstance(default_settings, dict):
            for key, value in default_settings.items():
                recovered_settings.setdefault(key, value)
        merged["settings"] = recovered_settings

        recovered_ui = merged.get("ui")
        if not isinstance(recovered_ui, dict):
            recovered_ui = {}
        default_ui = defaults.get("ui", {})
        if isinstance(default_ui, dict):
            for key, value in default_ui.items():
                recovered_ui.setdefault(key, value)
        merged["ui"] = recovered_ui
        return merged

    def _repair_existing_settings_config(self):
        """Conservatively repairs and atomically replaces the active config."""
        path = self._get_settings_config_path()
        if not path.is_file():
            _show_dark_message(
                "No active Auto Light settings file was found.",
                "Auto Light",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        try:
            if path.stat().st_size > self.MAX_SETTINGS_CONFIG_BYTES:
                raise ValueError(
                    "The settings file exceeds the 1 MiB safety limit."
                )
            content = path.read_text(
                encoding="utf-8-sig",
                errors="strict",
            )
        except Exception as exc:
            _show_dark_message(
                f"The settings file could not be read.\n\nReason: {exc}",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        repaired_data, repairs = self._attempt_parse_repaired_settings_config(
            content
        )
        if repaired_data is None:
            _show_dark_message(
                "The settings file could not be repaired safely.\n\n"
                "No changes were made. Correct the JSON manually or import a "
                "known-good settings file.",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        valid, reason = self._validate_repaired_settings_config(repaired_data)
        if not valid:
            _show_dark_message(
                "The settings file could not be repaired safely.\n\n"
                f"Reason: {reason}\n\nNo changes were made.",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        confirmation_lines = [
            "Repair and normalize the active Auto Light settings file?",
            "",
            "Recognized settings will be validated before being applied.",
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

        confirmation = DarkMessageDialog(
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
            _show_dark_message(
                "The repaired settings file could not be written.\n\n"
                f"Reason: {exc}",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_config_data(merged)

        _show_dark_message(
            "The settings file was repaired and reloaded successfully.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _import_settings_config(self):
        """Imports a valid config into the stable active config location."""
        dialog = wx.FileDialog(
            self,
            "Import Auto Light settings",
            wildcard=(
                "Auto Light config (*.config)|*.config|All files (*.*)|*.*"
            ),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            source_path = Path(dialog.GetPath())
        finally:
            dialog.Destroy()

        self._settings_config_load_error = ""
        data = self._load_settings_config_data(source_path)
        if data is None:
            _show_dark_message(
                "The selected settings file could not be imported.\n\n"
                f"Reason: {self._settings_config_load_error or 'Invalid file'}",
                "Auto Light",
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
            self._write_text_atomically(
                self._get_settings_config_path(),
                content,
            )
        except Exception as exc:
            _show_dark_message(
                "The selected settings were valid, but the active settings "
                "file could not be written.\n\n"
                f"Reason: {exc}",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_config_data(merged)
        _show_dark_message(
            "Settings imported successfully.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _export_settings_config(self):
        """Exports a backup without changing the active config location."""
        active_path = self._get_settings_config_path()
        existing = None
        if active_path.is_file():
            self._settings_config_load_error = ""
            existing = self._load_settings_config_data(active_path)
            if existing is None:
                _show_dark_message(
                    "The active settings file is malformed or unreadable.\n\n"
                    "Repair it before exporting so unknown saved entries are not "
                    "silently lost.",
                    "Auto Light",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
                return

        dialog = wx.FileDialog(
            self,
            "Export Auto Light settings",
            defaultFile=self.SETTINGS_CONFIG_FILENAME,
            wildcard=(
                "Auto Light config (*.config)|*.config|All files (*.*)|*.*"
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
            _show_dark_message(
                f"Could not export the settings file.\n\nReason: {exc}",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        _show_dark_message(
            "Settings exported successfully.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _show_settings_action_dialog(self, actions):
        """Shows the dark Manage Plugin Files action picker."""
        parent = wx.GetTopLevelParent(self) or self
        dialog = DarkActionPickerDialog(
            parent,
            actions,
            initial_size=self._current_manage_dialog_size_config(),
            on_size_changed=self._remember_manage_dialog_size,
        )
        try:
            result = dialog.ShowModal()
            self._remember_manage_dialog_size(dialog)
            if result != wx.ID_OK:
                return None
            selection = dialog.GetSelection()
            return selection if selection != wx.NOT_FOUND else None
        finally:
            dialog.Destroy()

    def _manage_settings(self, _):
        """Provides explicit local management for Auto Light.config."""
        actions = [
            (
                "Save current settings now",
                "Create or update Auto Light.config with the settings currently "
                "shown in the plugin. Normal setting changes are also saved "
                "automatically after a short delay.",
            ),
            (
                "Open settings folder",
                "Open the local Amulet edit-plugins settings folder containing "
                "Auto Light.config and other plugin config files.",
            ),
            (
                "Reset saved settings to defaults",
                "Restore every Auto Light option to the current plugin defaults "
                "and rewrite the active settings file.",
            ),
            (
                "Attempt to repair existing settings config",
                "Try a conservative manual repair when simple JSON damage prevents "
                "Auto Light.config from loading. Unknown and recovered values are "
                "preserved where possible.",
            ),
            (
                "Import settings...",
                "Copy a selected Auto Light settings backup into the stable active "
                "config location and load its recognized values.",
            ),
            (
                "Export settings...",
                "Save a backup copy of the current Auto Light settings without "
                "moving or changing the active config path.",
            ),
            (
                "Delete settings config",
                "Delete only Auto Light.config and restore the visible controls to "
                "plugin defaults. Worlds, the plugin, and other config files are "
                "not changed.",
            ),
        ]

        action = self._show_settings_action_dialog(actions)
        if action is None:
            return

        if action == 0:
            self._stop_pending_settings_save()
            if self._write_settings_config(create_if_missing=True):
                _show_dark_message(
                    "Current settings were saved successfully.",
                    "Auto Light",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                _show_dark_message(
                    "The settings file could not be saved.\n\n"
                    f"Reason: {self._settings_config_write_error or 'Unknown error'}",
                    "Auto Light",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            return

        if action == 1:
            try:
                directory = self._get_settings_config_path().parent
                directory.mkdir(parents=True, exist_ok=True)
                wx.LaunchDefaultApplication(str(directory))
            except Exception as exc:
                _show_dark_message(
                    f"Could not open the settings folder.\n\nReason: {exc}",
                    "Auto Light",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            return

        if action == 2:
            confirmation = DarkMessageDialog(
                self,
                "Reset all Auto Light settings to their current defaults?\n\n"
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
                _show_dark_message(
                    "Auto Light settings were reset successfully.",
                    "Auto Light",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                _show_dark_message(
                    "The settings could not be reset.\n\n"
                    f"Reason: {self._settings_config_write_error or 'Unknown error'}",
                    "Auto Light",
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

        confirmation = DarkMessageDialog(
            self,
            "Delete Auto Light.config?\n\n"
            "The visible settings will return to defaults. Worlds, the plugin, "
            "and other config files will not be changed.",
            "Delete Auto Light settings?",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        try:
            confirmed = confirmation.ShowModal() == wx.ID_YES
        finally:
            confirmation.Destroy()
        if not confirmed:
            return

        self._stop_pending_settings_save()
        path = self._get_settings_config_path()
        try:
            if path.is_file():
                path.unlink()
        except Exception as exc:
            _show_dark_message(
                f"The settings file could not be deleted.\n\nReason: {exc}",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        defaults = self._settings_defaults
        if isinstance(defaults, dict):
            self._apply_settings_config_data(defaults)
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""

        _show_dark_message(
            "Auto Light.config was deleted and visible settings were restored "
            "to defaults.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # =========================
    # BUILT-IN CONSOLE AND REPORT
    # =========================
    def _clear_log(self):
        """Clears the visible report console."""
        try:
            wx.CallAfter(self.text.SetValue, "")
        except Exception:
            try:
                self.text.SetValue("")
            except Exception:
                pass

    def _append_log_text(self, message):
        """Appends one line to the visible report console."""
        try:
            self.text.AppendText(str(message) + "\n")
        except Exception:
            pass

    def _log(self, message):
        """Writes one line to stdout, the console, and the saved report."""
        message = str(message)
        print(message)

        try:
            self._report_lines.append(message)
        except Exception:
            pass

        try:
            wx.CallAfter(self._append_log_text, message)
        except Exception:
            self._append_log_text(message)

    def _reset_report(self):
        """Clears the in-memory report before a new run."""
        self._report_lines = []
        self._last_report_text = ""
        try:
            self.save_report_button.SetAvailable(False)
        except Exception:
            pass

    def _finalize_report(self):
        """Stores the completed report and enables explicit report saving."""
        self._last_report_text = "\n".join(self._report_lines).strip()
        if not self._last_report_text:
            return

        try:
            wx.CallAfter(self.save_report_button.SetAvailable, True)
        except Exception:
            try:
                self.save_report_button.SetAvailable(True)
            except Exception:
                pass

    def _save_last_report(self, _):
        """Lets the user save the latest console report atomically."""
        if not self._last_report_text:
            _show_dark_message(
                "No report is available yet. Run Auto Light first.",
                "No Report",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        default_name = (
            "Auto Light report; "
            + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".txt"
        )
        dialog = wx.FileDialog(
            self,
            message="Save Auto Light report",
            defaultFile=default_name,
            wildcard="Text files (*.txt)|*.txt|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = Path(dialog.GetPath())
        finally:
            dialog.Destroy()

        try:
            self._write_text_atomically(
                path,
                self._last_report_text + "\n",
            )
            _show_dark_message(
                f"Report saved:\n{path}",
                "Report Saved",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:
            _show_dark_message(
                f"Could not save report:\n{exc}",
                "Save Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    @staticmethod
    def _format_seconds(seconds):
        """Formats a timing value consistently for console reports."""
        try:
            seconds = max(0.0, float(seconds))
        except (TypeError, ValueError):
            seconds = 0.0
        return f"{seconds:.3f} seconds"

    @staticmethod
    def _format_rate(amount, seconds, unit="positions"):
        """Formats a safe per-second processing rate."""
        try:
            seconds = float(seconds)
            amount = int(amount)
        except (TypeError, ValueError):
            return f"0 {unit} / second"
        if seconds <= 0.0:
            return f"{amount:,} {unit} / second"
        return f"{amount / seconds:,.0f} {unit} / second"

    @staticmethod
    def _box_volume(box):
        """Returns the block volume of one half-open cuboid tuple."""
        min_x, max_x, min_y, max_y, min_z, max_z = box
        return max(0, max_x - min_x) * max(0, max_y - min_y) * max(0, max_z - min_z)

    @staticmethod
    def _selection_bounds(boxes):
        """Returns the overall half-open bounds for a non-empty box sequence."""
        return (
            min(box[0] for box in boxes),
            max(box[1] for box in boxes),
            min(box[2] for box in boxes),
            max(box[3] for box in boxes),
            min(box[4] for box in boxes),
            max(box[5] for box in boxes),
        )

    def _log_section(self, title, rows):
        """Writes a compact titled section to the current report."""
        self._log("")
        self._log(title)
        for label, value in rows:
            self._log(f"{label}: {value}")

    # =========================
    # LIGHT DETECTION
    # =========================
    @staticmethod
    def _tag_to_python_value(value):
        """Converts common Amulet property tags into plain Python values."""
        for attribute_name in ("py_data", "value"):
            try:
                return getattr(value, attribute_name)
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

    def _get_block_property(self, block, names):
        """Reads the first available block property from common key forms."""
        properties = getattr(block, "properties", None)
        if not properties:
            return None

        requested_names = []
        for name in names:
            name_text = str(name)
            requested_names.append(name_text)
            if ":" not in name_text:
                requested_names.append(f"minecraft:{name_text}")

        for name in requested_names:
            try:
                if name in properties:
                    return self._tag_to_python_value(properties.get(name))
            except Exception:
                pass

        # Some Amulet versions expose property keys as tag-like or namespaced
        # objects rather than plain strings. Compare their normalized local
        # names without changing the stored property values.
        requested_local_names = {
            name.split(":", 1)[-1].strip().lower()
            for name in requested_names
        }
        try:
            property_items = properties.items()
        except Exception:
            return None

        for raw_key, raw_value in property_items:
            key_text = str(self._tag_to_python_value(raw_key)).strip()
            key_text = key_text.strip('"').strip("'").lower()
            local_name = key_text.split(":", 1)[-1]
            if local_name in requested_local_names:
                return self._tag_to_python_value(raw_value)

        return None

    def _state_bool(self, value):
        """Interprets common Bedrock and Amulet boolean state values."""
        if value is None:
            return None

        value = self._tag_to_python_value(value)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0

        text = str(value).strip().lower().strip('"').strip("'")
        if text in ("1", "1b", "true", "yes", "on", "active", "lit"):
            return True
        if text in ("0", "0b", "false", "no", "off", "inactive", "unlit"):
            return False
        return None

    def _state_int(self, value):
        """Returns an integer block-state value when it can be read safely."""
        if value is None:
            return None

        value = self._tag_to_python_value(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            text = str(value).strip().lower().rstrip("bslf")
            try:
                return int(text)
            except (TypeError, ValueError):
                return None

    def _get_candle_count(self, block):
        """Returns the physical candle count represented by a candle block."""
        # Bedrock's vanilla ``candles`` state stores the number of extra
        # candles, so 0 through 3 represents one through four candles.
        vanilla_count = self._state_int(
            self._get_block_property(block, ("candles",))
        )
        if vanilla_count is not None:
            if 0 <= vanilla_count <= 3:
                return vanilla_count + 1
            return 1

        # Compatibility aliases may expose the physical count directly.
        direct_count = self._state_int(
            self._get_block_property(
                block,
                ("candle_count", "cluster_count", "count"),
            )
        )
        if direct_count is None:
            return 1
        if 1 <= direct_count <= 4:
            return direct_count
        if direct_count == 0:
            return 1
        return 1

    def _get_sea_pickle_count(self, block):
        """Returns the physical sea-pickle count represented by the block."""
        # Bedrock's vanilla ``cluster_count`` state stores extra pickles, so
        # 0 through 3 represents one through four sea pickles.
        vanilla_count = self._state_int(
            self._get_block_property(block, ("cluster_count",))
        )
        if vanilla_count is not None:
            if 0 <= vanilla_count <= 3:
                return vanilla_count + 1
            return 1

        direct_count = self._state_int(
            self._get_block_property(
                block,
                ("pickle_count", "sea_pickle_count", "count"),
            )
        )
        if direct_count is None:
            return 1
        if 1 <= direct_count <= 4:
            return direct_count
        if direct_count == 0:
            return 1
        return 1

    def _is_conditional_source_active(self, block):
        """
        Returns the supported current active state for a conditional source.

        False is used when a source is known to be inactive or when its active
        state cannot be determined from the saved block data. The default UI
        option can instead treat these blocks as potentially lit.
        """
        name = block.base_name

        if name in LEGACY_ACTIVE_LIGHT_NAMES:
            return True
        if name == "unlit_redstone_torch":
            return False
        if name == "redstone_torch":
            return True

        if name in COPPER_BULB_NAMES or name == "redstone_lamp":
            return self._state_bool(
                self._get_block_property(block, ("lit", "lit_bit", "is_lit"))
            ) is True

        if name in {"blast_furnace", "furnace", "smoker"}:
            return self._state_bool(
                self._get_block_property(
                    block,
                    ("lit", "lit_bit", "is_lit", "burning", "burning_bit"),
                )
            ) is True

        if name in {"campfire", "soul_campfire"}:
            extinguished = self._state_bool(
                self._get_block_property(
                    block,
                    ("extinguished", "extinguished_bit", "is_extinguished"),
                )
            )
            if extinguished is not None:
                return not extinguished
            return self._state_bool(
                self._get_block_property(block, ("lit", "lit_bit", "is_lit"))
            ) is True

        if name in CANDLE_LIGHT_NAMES:
            return self._state_bool(
                self._get_block_property(block, ("lit", "lit_bit", "is_lit"))
            ) is True

        if name == "sea_pickle":
            dead = self._state_bool(
                self._get_block_property(block, ("dead_bit", "dead", "is_dead"))
            )
            if dead is not None:
                return not dead
            return self._state_bool(
                self._get_block_property(
                    block,
                    ("waterlogged", "waterlogged_bit", "is_waterlogged"),
                )
            ) is True

        if name == "respawn_anchor":
            charge = self._state_int(
                self._get_block_property(
                    block,
                    ("respawn_anchor_charge", "charge", "charges"),
                )
            )
            return charge is not None and charge > 0

        if name in {"sculk_sensor", "calibrated_sculk_sensor"}:
            phase = self._get_block_property(
                block,
                ("sculk_sensor_phase", "phase", "sensor_phase"),
            )
            if phase is None:
                return False
            phase_text = str(self._tag_to_python_value(phase)).strip().lower()
            return "active" in phase_text and "inactive" not in phase_text

        return name not in CONDITIONAL_LIGHT_SOURCES

    def _estimate_light_strength(self, block, treat_inactive_as_lit=True):
        """
        Returns the effective light strength for detection.

        When treat_inactive_as_lit is enabled, conditional sources use their
        potential strength. Otherwise, supported current block states determine
        whether the source contributes light.
        """
        name = block.base_name
        strength = LIGHT_STRENGTH.get(name, 0)
        if strength <= 0:
            return 0

        if name in CANDLE_LIGHT_NAMES:
            strength = min(15, self._get_candle_count(block) * 3)
        elif name == "sea_pickle":
            strength = min(15, 3 + self._get_sea_pickle_count(block) * 3)
        elif name == "respawn_anchor" and not treat_inactive_as_lit:
            charge = self._state_int(
                self._get_block_property(
                    block,
                    ("respawn_anchor_charge", "charge", "charges"),
                )
            )
            strength = {1: 3, 2: 7, 3: 11, 4: 15}.get(charge, 0)

        if treat_inactive_as_lit:
            return strength

        if name in CONDITIONAL_LIGHT_SOURCES and not self._is_conditional_source_active(block):
            return 0

        return strength

    @staticmethod
    def _normalize_box_tuple(box):
        """Returns one selection box as a plain half-open coordinate tuple."""
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
    def _position_in_boxes(pos, boxes):
        """Returns True when a coordinate is inside any half-open selection box."""
        x, y, z = pos
        return any(
            min_x <= x < max_x
            and min_y <= y < max_y
            and min_z <= z < max_z
            for min_x, max_x, min_y, max_y, min_z, max_z in boxes
        )

    @staticmethod
    def _subtract_box_tuple(box, cutter):
        """Subtracts one half-open cuboid and returns non-overlapping fragments."""
        min_x, max_x, min_y, max_y, min_z, max_z = box
        cut_min_x, cut_max_x, cut_min_y, cut_max_y, cut_min_z, cut_max_z = cutter

        overlap_min_x = max(min_x, cut_min_x)
        overlap_max_x = min(max_x, cut_max_x)
        overlap_min_y = max(min_y, cut_min_y)
        overlap_max_y = min(max_y, cut_max_y)
        overlap_min_z = max(min_z, cut_min_z)
        overlap_max_z = min(max_z, cut_max_z)

        if (
            overlap_min_x >= overlap_max_x
            or overlap_min_y >= overlap_max_y
            or overlap_min_z >= overlap_max_z
        ):
            return [box]

        fragments = []

        if min_x < overlap_min_x:
            fragments.append(
                (min_x, overlap_min_x, min_y, max_y, min_z, max_z)
            )
        if overlap_max_x < max_x:
            fragments.append(
                (overlap_max_x, max_x, min_y, max_y, min_z, max_z)
            )

        middle_min_x = overlap_min_x
        middle_max_x = overlap_max_x

        if min_y < overlap_min_y:
            fragments.append(
                (
                    middle_min_x,
                    middle_max_x,
                    min_y,
                    overlap_min_y,
                    min_z,
                    max_z,
                )
            )
        if overlap_max_y < max_y:
            fragments.append(
                (
                    middle_min_x,
                    middle_max_x,
                    overlap_max_y,
                    max_y,
                    min_z,
                    max_z,
                )
            )

        middle_min_y = overlap_min_y
        middle_max_y = overlap_max_y

        if min_z < overlap_min_z:
            fragments.append(
                (
                    middle_min_x,
                    middle_max_x,
                    middle_min_y,
                    middle_max_y,
                    min_z,
                    overlap_min_z,
                )
            )
        if overlap_max_z < max_z:
            fragments.append(
                (
                    middle_min_x,
                    middle_max_x,
                    middle_min_y,
                    middle_max_y,
                    overlap_max_z,
                    max_z,
                )
            )

        return fragments

    def _deduplicate_box_tuples(self, boxes):
        """
        Converts overlapping cuboids into a deterministic non-overlapping union.

        Memory use scales with the number of resulting cuboids rather than the
        number of selected blocks, so large solid selections do not require a
        coordinate-sized deduplication set.
        """
        unique_boxes = []

        for raw_box in boxes:
            box = self._normalize_box_tuple(raw_box)
            if (
                box[0] >= box[1]
                or box[2] >= box[3]
                or box[4] >= box[5]
            ):
                continue

            fragments = [box]
            for existing in unique_boxes:
                next_fragments = []
                for fragment in fragments:
                    next_fragments.extend(
                        self._subtract_box_tuple(fragment, existing)
                    )
                fragments = next_fragments
                if not fragments:
                    break

            unique_boxes.extend(fragments)

        return unique_boxes

    def _build_chunk_regions(self, boxes):
        """Clips non-overlapping selection cuboids into chunk-local regions."""
        regions = []

        for order, raw_box in enumerate(boxes):
            min_x, max_x, min_y, max_y, min_z, max_z = (
                self._normalize_box_tuple(raw_box)
            )
            min_cx = min_x // 16
            max_cx = (max_x - 1) // 16
            min_cz = min_z // 16
            max_cz = (max_z - 1) // 16

            for cx in range(min_cx, max_cx + 1):
                chunk_min_x = max(min_x, cx * 16)
                chunk_max_x = min(max_x, cx * 16 + 16)

                for cz in range(min_cz, max_cz + 1):
                    chunk_min_z = max(min_z, cz * 16)
                    chunk_max_z = min(max_z, cz * 16 + 16)
                    regions.append(
                        (
                            order,
                            cx,
                            cz,
                            chunk_min_x,
                            chunk_max_x,
                            min_y,
                            max_y,
                            chunk_min_z,
                            chunk_max_z,
                        )
                    )

        return regions

    @staticmethod
    def _selection_center_doubled(boxes):
        """Returns the doubled center coordinate of the combined selection."""
        min_x = min(box[0] for box in boxes)
        max_x = max(box[1] for box in boxes)
        min_y = min(box[2] for box in boxes)
        max_y = max(box[3] for box in boxes)
        min_z = min(box[4] for box in boxes)
        max_z = max(box[5] for box in boxes)
        return (
            min_x + max_x - 1,
            min_y + max_y - 1,
            min_z + max_z - 1,
        )

    @staticmethod
    def _region_center_distance_key(region, center_x2, center_y2, center_z2):
        """Returns a deterministic center-outward ordering key for one region."""
        (
            order,
            cx,
            cz,
            min_x,
            max_x,
            min_y,
            max_y,
            min_z,
            max_z,
        ) = region
        region_x2 = min_x + max_x - 1
        region_y2 = min_y + max_y - 1
        region_z2 = min_z + max_z - 1
        distance = (
            (region_x2 - center_x2) ** 2
            + (region_y2 - center_y2) ** 2
            + (region_z2 - center_z2) ** 2
        )
        return distance, order, cx, cz, min_y, min_x, min_z

    @staticmethod
    def _ordered_region_columns(
        min_x,
        max_x,
        min_z,
        max_z,
        center_x2,
        center_z2,
        center_outward,
    ):
        """Returns chunk-local x / z columns in legacy or center-outward order."""
        columns = [
            (x, z)
            for x in range(min_x, max_x)
            for z in range(min_z, max_z)
        ]
        if center_outward:
            columns.sort(
                key=lambda position: (
                    (position[0] * 2 - center_x2) ** 2
                    + (position[1] * 2 - center_z2) ** 2,
                    position[0],
                    position[1],
                )
            )
        return columns

    def _build_light_index(
        self,
        selection_boxes,
        dim,
        plat,
        ver,
        horizontal_radius,
        vertical_radius,
        treat_inactive_as_lit,
    ):
        """
        Builds the cached existing-light map and bounded report statistics.

        Expanded selection regions are deduplicated before scanning. This keeps
        distant selections independent while preventing overlapping selections
        and overlapping radius margins from reading the same coordinates twice.
        """
        expanded_boxes = []
        for raw_box in selection_boxes:
            min_x, max_x, min_y, max_y, min_z, max_z = (
                self._normalize_box_tuple(raw_box)
            )
            expanded_boxes.append(
                (
                    min_x - horizontal_radius,
                    max_x + horizontal_radius,
                    min_y - vertical_radius,
                    max_y + vertical_radius,
                    min_z - horizontal_radius,
                    max_z + horizontal_radius,
                )
            )

        unique_expanded_boxes = self._deduplicate_box_tuples(expanded_boxes)
        expanded_chunk_regions = self._build_chunk_regions(
            unique_expanded_boxes
        )
        light_index = {}
        chunk_availability = {}
        stats = {
            "expanded_regions": len(unique_expanded_boxes),
            "chunk_regions": len(expanded_chunk_regions),
            "chunks_checked": 0,
            "available_chunks": 0,
            "missing_chunks": 0,
            "positions_scanned": 0,
            "light_capable_sources_found": 0,
            "active_sources_found": 0,
            "inactive_sources_ignored": 0,
            "inactive_sources_treated_as_lit": 0,
        }

        for region in expanded_chunk_regions:
            (
                _order,
                cx,
                cz,
                min_x,
                max_x,
                min_y,
                max_y,
                min_z,
                max_z,
            ) = region

            available = chunk_availability.get((cx, cz))
            if available is None:
                available = bool(self.world.has_chunk(cx, cz, dim))
                chunk_availability[(cx, cz)] = available
            if not available:
                continue

            for x in range(min_x, max_x):
                for y in range(min_y, max_y):
                    for z in range(min_z, max_z):
                        stats["positions_scanned"] += 1
                        block, _ = self.world.get_version_block(
                            x, y, z, dim, (plat, ver)
                        )
                        name = block.base_name
                        if name not in LIGHT_SOURCES:
                            continue

                        potential_strength = self._estimate_light_strength(
                            block,
                            True,
                        )
                        if potential_strength <= 0:
                            continue

                        stats["light_capable_sources_found"] += 1
                        is_conditional = name in CONDITIONAL_LIGHT_SOURCES
                        actual_strength = (
                            self._estimate_light_strength(block, False)
                            if is_conditional
                            else potential_strength
                        )
                        if actual_strength > 0:
                            stats["active_sources_found"] += 1

                        if treat_inactive_as_lit:
                            strength = potential_strength
                            if is_conditional and actual_strength <= 0:
                                stats["inactive_sources_treated_as_lit"] += 1
                        else:
                            strength = actual_strength
                            if is_conditional and actual_strength <= 0:
                                stats["inactive_sources_ignored"] += 1

                        if strength > 0:
                            light_index[(x, y, z)] = strength

        stats["chunks_checked"] = len(chunk_availability)
        stats["available_chunks"] = sum(
            1 for available in chunk_availability.values() if available
        )
        stats["missing_chunks"] = (
            stats["chunks_checked"] - stats["available_chunks"]
        )
        stats["sources_included"] = len(light_index)
        return light_index, stats

    @staticmethod
    def _has_legacy_nearby_light(
        x,
        y,
        z,
        light_index,
        radius,
        ignored_existing_source=None,
    ):
        """
        Returns True when a recognized pre-existing source is within the
        configured legacy radius.

        A replaceable light-emitting plant at the candidate coordinate may be
        ignored so it does not prevent its own replacement. Every other source
        remains active in the check.
        """
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                if dx * dx + dz * dz > radius * radius:
                    continue

                for dy in (-1, 0, 1):
                    source_pos = (x + dx, y + dy, z + dz)
                    if source_pos == ignored_existing_source:
                        continue
                    if source_pos in light_index:
                        return True

        return False

    @staticmethod
    def _light_bucket_key(x, y, z):
        """Returns the compact three-dimensional bucket for a light source."""
        size = SMART_LIGHT_BUCKET_SIZE
        return x // size, y // size, z // size

    def _build_light_buckets(self, light_index):
        """Builds spatial buckets for fast Smart Coverage source queries."""
        buckets = {}
        for (x, y, z), strength in light_index.items():
            key = self._light_bucket_key(x, y, z)
            buckets.setdefault(key, []).append(
                (x, y, z, strength, False)
            )
        return buckets

    def _add_light_to_buckets(self, light_buckets, x, y, z, strength):
        """Adds one newly placed source to the Smart Coverage index."""
        if strength <= 0:
            return False
        key = self._light_bucket_key(x, y, z)
        light_buckets.setdefault(key, []).append(
            (x, y, z, strength, True)
        )
        return True

    def _get_calculated_light_details(
        self,
        x,
        y,
        z,
        light_buckets,
        ignored_existing_source=None,
    ):
        """
        Returns the strongest estimated level and whether its source was placed
        during the current operation. Existing sources win equal-strength ties.
        """
        bucket_x, bucket_y, bucket_z = self._light_bucket_key(x, y, z)
        bucket_radius = (
            SMART_LIGHT_MAX_DISTANCE + SMART_LIGHT_BUCKET_SIZE - 1
        ) // SMART_LIGHT_BUCKET_SIZE
        strongest = 0
        strongest_is_placed = False

        for offset_x in range(-bucket_radius, bucket_radius + 1):
            for offset_y in range(-bucket_radius, bucket_radius + 1):
                for offset_z in range(-bucket_radius, bucket_radius + 1):
                    sources = light_buckets.get(
                        (
                            bucket_x + offset_x,
                            bucket_y + offset_y,
                            bucket_z + offset_z,
                        ),
                        (),
                    )
                    for source in sources:
                        source_x, source_y, source_z, strength = source[:4]
                        is_placed = bool(source[4]) if len(source) > 4 else False
                        if (
                            ignored_existing_source is not None
                            and not is_placed
                            and (source_x, source_y, source_z)
                            == ignored_existing_source
                        ):
                            continue
                        distance = (
                            abs(source_x - x)
                            + abs(source_y - y)
                            + abs(source_z - z)
                        )
                        if distance >= strength:
                            continue

                        effective = strength - distance
                        if (
                            effective > strongest
                            or (
                                effective == strongest
                                and strongest_is_placed
                                and not is_placed
                            )
                        ):
                            strongest = effective
                            strongest_is_placed = is_placed
                            if strongest >= 15:
                                return 15, strongest_is_placed

        return strongest, strongest_is_placed

    # =========================
    # PLACEMENT RULES
    # =========================
    @staticmethod
    def _is_missing_chunk_error(exc):
        """Returns True when an Amulet read failed because a chunk is unavailable."""
        return exc.__class__.__name__ == "ChunkDoesNotExist"

    def _get_block_if_available(self, x, y, z, dim, plat, ver):
        """
        Reads a block only when its chunk exists.

        Placement checks can cross a chunk boundary while checking floors,
        walls or ceilings. An unavailable neighboring chunk is treated as
        missing support instead of aborting the full operation.
        """
        cx, cz = block_coords_to_chunk_coords(x, z)
        if not self.world.has_chunk(cx, cz, dim):
            return None

        try:
            block, _ = self.world.get_version_block(
                x, y, z, dim, (plat, ver)
            )
            return block
        except Exception as exc:
            if self._is_missing_chunk_error(exc):
                return None
            raise

    def _is_valid_support(self, block, cache=None):
        """
        Returns True when a block is solid enough to support a floor or wall light.
        Uses an optional cache so repeated block names are only classified once.
        """
        name = block.base_name

        if cache is not None and name in cache:
            return cache[name]

        if name in AIR or name in REPLACEABLE_TARGET_BLOCKS:
            result = False
        else:
            result = True
            for bad in NON_SOLID_KEYWORDS:
                if bad in name:
                    result = False
                    break

        if cache is not None:
            cache[name] = result
        return result

    def _is_firefly_support(self, block):
        """
        Firefly bush only makes sense on full ground-like blocks.
        """
        name = block.base_name
        if name in AIR:
            return False

        for key in FIREFLY_SUPPORT_KEYWORDS:
            if key in name:
                return True

        return False

    def _is_replaceable_target(self, block, cache=None):
        """
        Returns True if the current block is a safe plant-like block
        that may be replaced when the option is enabled.
        """
        name = block.base_name

        if cache is not None and name in cache:
            return cache[name]

        if name in AIR:
            result = True
        else:
            result = name in REPLACEABLE_TARGET_BLOCKS

        if cache is not None:
            cache[name] = result
        return result

    def _connected_plant_partner(
        self,
        x,
        y,
        z,
        dim,
        plat,
        ver,
        block,
        selection_boxes,
    ):
        """Return (safe, partner_position) for a paired replaceable plant.

        A paired plant is rejected when its required partner lies outside the
        selection. This prevents plant replacement from modifying unselected
        blocks or leaving a selected half floating beside an unselected half.
        """
        if block.base_name not in DOUBLE_HEIGHT_PLANTS:
            return True, None

        candidates = [(x, y + 1, z), (x, y - 1, z)]
        upper_value = self._state_bool(
            self._get_block_property(block, ("upper_block_bit",))
        )
        half = self._get_block_property(block, ("half",))

        if upper_value is not None:
            candidates = [
                (x, y - 1, z) if upper_value else (x, y + 1, z)
            ]
        elif half is not None:
            half_text = str(self._tag_to_python_value(half)).strip().lower()
            if half_text in ("upper", "top"):
                candidates = [(x, y - 1, z)]
            elif half_text in ("lower", "bottom"):
                candidates = [(x, y + 1, z)]

        for partner_pos in candidates:
            px, py, pz = partner_pos
            partner_block = self._get_block_if_available(
                px,
                py,
                pz,
                dim,
                plat,
                ver,
            )
            if partner_block is None:
                continue
            if partner_block.base_name != block.base_name:
                continue
            if not self._position_in_boxes(partner_pos, selection_boxes):
                return False, None
            return True, partner_pos

        # An already-orphaned half is safe to replace because no connected
        # selected or unselected partner remains to clean up.
        return True, None

    def _clear_connected_plant_half(
        self,
        partner_pos,
        dim,
        plat,
        ver,
        expected_name,
    ):
        """Remove one already-validated selected partner half, if still present."""
        if partner_pos is None:
            return []

        px, py, pz = partner_pos
        partner_block = self._get_block_if_available(
            px,
            py,
            pz,
            dim,
            plat,
            ver,
        )
        if partner_block is None or partner_block.base_name != expected_name:
            return []

        self.world.set_version_block(
            px,
            py,
            pz,
            dim,
            (plat, ver),
            Block("minecraft", "air"),
            None,
        )
        return [partner_pos]

    # =========================
    # UI VISIBILITY LOGIC
    # =========================
    def _on_light_change(self, event):
        """
        Refreshes visible options when the selected light type changes.
        """
        self._update_ui_visibility()
        self._schedule_settings_config_save(event)

    def _on_light_icon_mode_change(self, event):
        """Apply and persist the optional model-aware light-source selector."""
        try:
            self.light_choice.SetShowIcons(
                self.show_light_icons_cb.GetValue()
            )
        except Exception:
            pass
        self._refresh_floating_layout()
        self._schedule_settings_config_save(event)

    def _on_detection_mode_change(self, event):
        """Refreshes radius controls when Smart Coverage is toggled."""
        self._update_ui_visibility()
        self._schedule_settings_config_save(event)

    def _update_ui_visibility(self):
        """Show only controls that apply to the selected light source."""
        choice = self.light_choice.GetStringSelection()

        is_torch = choice in TORCH_CHOICES
        is_lantern = choice in LANTERN_CHOICES
        is_copper_variants = choice in COPPER_VARIANT_CHOICES
        is_copper_bulb = choice in COPPER_BULB_CHOICES
        use_smart_coverage = self.smart_coverage_cb.GetValue()

        _set_window_sizer_item_visible(
            self.radius_label,
            not use_smart_coverage,
        )
        _set_window_sizer_item_visible(
            self.radius_slider,
            not use_smart_coverage,
        )
        _set_window_sizer_item_visible(
            self.radius_box,
            not use_smart_coverage,
        )
        _set_sizer_item_visible(
            self.radius_row_item,
            not use_smart_coverage,
        )

        has_source_options = bool(
            is_torch
            or is_lantern
            or is_copper_variants
        )
        _set_sizer_item_visible(
            self._source_options_transition_spacing,
            has_source_options,
        )
        _set_sizer_group_visible(
            self.torch_group_item,
            is_torch,
        )
        _set_sizer_group_visible(
            self.lantern_group_item,
            is_lantern,
        )
        _set_sizer_group_visible(
            self.copper_group_item,
            is_copper_variants,
        )
        _set_window_sizer_item_visible(
            self.copper_bulb_lit_cb,
            is_copper_bulb,
        )

        self._refresh_floating_layout()

    # =========================
    # VALUE BINDING HELPERS
    # =========================
    def _bind(self, slider, box, min_v, max_v):
        """
        Keeps slider and text box in sync.
        """
        def on_slider(event):
            box.ChangeValue(str(slider.GetValue()))
            self._schedule_settings_config_save(event)

        def on_text(event):
            changed = False
            try:
                v = int(box.GetValue())
                v = max(min_v, min(max_v, v))
                slider.SetValue(v)
                changed = True
            except (TypeError, ValueError):
                pass

            if changed:
                self._schedule_settings_config_save()
            try:
                event.Skip()
            except Exception:
                pass

        slider.Bind(wx.EVT_SLIDER, on_slider)
        box.Bind(wx.EVT_TEXT, on_text)

    # =========================
    # BLOCK CONSTRUCTION HELPERS
    # =========================
    def _torch_block(self, direction, base_name):
        """
        Creates a torch block with the correct facing direction property.
        """
        return Block(
            "minecraft",
            base_name,
            {"torch_facing_direction": TAG_String(direction)}
        )

    def _get_selected_block(self):
        """
        Converts the UI selection into the actual block object to place.
        """
        choice = self.light_choice.GetStringSelection()

        simple_map = {
            "Torch": ("minecraft", "torch"),
            "Soul Torch": ("minecraft", "soul_torch"),
            "Copper Torch": ("minecraft", "copper_torch"),
            "Lantern": ("minecraft", "lantern"),
            "Soul Lantern": ("minecraft", "soul_lantern"),
            "Sea Lantern": ("minecraft", "sea_lantern"),
        }

        if choice in simple_map:
            namespace, base_name = simple_map[choice]
            return Block(namespace, base_name)

        if choice in COPPER_LANTERN_MAP:
            base_name = COPPER_LANTERN_MAP[choice]
            if self.copper_waxed_cb.GetValue():
                base_name = f"waxed_{base_name}"
            return Block("minecraft", base_name)

        if choice == "Firefly Bush":
            return Block(
                "minecraft",
                "firefly_bush",
                {"plant_type": TAG_String("firefly_bush")}
            )

        if choice in COPPER_BULB_MAP:
            base_name = COPPER_BULB_MAP[choice]
            if self.copper_waxed_cb.GetValue():
                base_name = f"waxed_{base_name}"

            # Amulet expects the bulb state to be expressed with lit + powered_bit.
            lit = self.copper_bulb_lit_cb.GetValue()
            return Block(
                "minecraft",
                base_name,
                {
                    "lit": TAG_Byte(1 if lit else 0),
                    "powered_bit": TAG_Byte(0),
                }
            )

        selection_name = choice or "<no selection>"
        raise ValueError(f"Unsupported light type: {selection_name}")

    def _get_selection_kind(self, choice):
        """
        Returns a simple placement kind so the hot path does less string checking.
        """
        if choice == "Firefly Bush":
            return "firefly"
        if choice in FULL_BLOCK_CHOICES:
            return "full"
        if choice in TORCH_CHOICES:
            return "torch"
        if choice in LANTERN_CHOICES:
            return "lantern"
        selection_name = choice or "<no selection>"
        raise ValueError(f"Unsupported light placement type: {selection_name}")

    # =========================
    # PLACEMENT LOGIC
    # =========================
    def _try_place(
        self,
        x,
        y,
        z,
        dim,
        plat,
        ver,
        base_block,
        current_block,
        replace_plants,
        placement_kind,
        allow_floor_torches,
        allow_wall_torches,
        allow_floor_lanterns,
        allow_ceiling_lanterns,
        support_cache=None,
        replace_cache=None
    ):
        """
        Returns the exact block that should be placed at x, y, z,
        or None if the position should be skipped.
        """
        # Full-block lights replace the target directly and do not need
        # neighboring support reads.
        if placement_kind == "full":
            return base_block

        below = self._get_block_if_available(
            x, y - 1, z, dim, plat, ver
        )
        if below is None:
            return None

        # Do not place on top of an existing light source.
        if below.base_name in UNSTACKABLE_LIGHT_BASES:
            return None

        # Firefly bush is handled as a special ground-plant style light.
        if placement_kind == "firefly":
            if not self._is_firefly_support(below):
                return None

            if current_block.base_name in AIR:
                return base_block

            if replace_plants and self._is_replaceable_target(current_block, replace_cache):
                return base_block

            return None

        # Floor placement for torch-like or lantern-like blocks.
        if self._is_valid_support(below, support_cache):
            if placement_kind == "torch" and allow_floor_torches:
                return self._torch_block("top", base_block.base_name)

            if placement_kind == "lantern" and allow_floor_lanterns:
                return Block("minecraft", base_block.base_name, {"hanging": TAG_Byte(0)})

        # Wall torches only.
        if placement_kind == "torch" and allow_wall_torches:
            directions = {
                (1, 0): "east",
                (-1, 0): "west",
                (0, 1): "south",
                (0, -1): "north",
            }

            for (dx, dz), facing in directions.items():
                side_block = self._get_block_if_available(
                    x + dx, y, z + dz, dim, plat, ver
                )
                if side_block is None:
                    continue

                if self._is_valid_support(side_block, support_cache):
                    return self._torch_block(facing, base_block.base_name)

        # Ceiling lanterns only.
        if placement_kind == "lantern" and allow_ceiling_lanterns:
            above = self._get_block_if_available(
                x, y + 1, z, dim, plat, ver
            )

            if above is not None and self._is_valid_support(above, support_cache):
                return Block("minecraft", base_block.base_name, {"hanging": TAG_Byte(1)})

        return None

    # =========================
    # MAIN OPERATION
    # =========================
    def _build_row_candidates(self, selection_boxes, grid_step, grid_origin_x, grid_origin_z):
        """
        Precomputes the x and z positions that are valid in row / grid mode.

        The UI spacing value means skipped blocks between lights. The selection
        boxes are already non-overlapping, so each coordinate is considered only
        once even when the original Amulet selection boxes overlap.
        """
        allowed_x = set()
        allowed_z = set()

        for raw_box in selection_boxes:
            min_x, max_x, _min_y, _max_y, min_z, max_z = (
                self._normalize_box_tuple(raw_box)
            )
            for x in range(min_x, max_x):
                if (x - grid_origin_x) % grid_step == 0:
                    allowed_x.add(x)

            for z in range(min_z, max_z):
                if (z - grid_origin_z) % grid_step == 0:
                    allowed_z.add(z)

        return allowed_x, allowed_z

    @staticmethod
    def _spacing_bucket_key(x, z, bucket_size):
        """Returns the horizontal bucket used for compact spread spacing."""
        return x // bucket_size, z // bucket_size

    def _has_placed_spacing_conflict(
        self,
        x,
        y,
        z,
        use_row_spacing,
        spacing_value,
        placed_columns,
        placed_spacing_buckets,
        spacing_bucket_size,
    ):
        """Checks spacing against previously placed lights without volume sets."""
        if use_row_spacing:
            return any(
                abs(y - placed_y) <= 2
                for placed_y in placed_columns.get((x, z), ())
            )

        bucket_x, bucket_z = self._spacing_bucket_key(
            x,
            z,
            spacing_bucket_size,
        )
        bucket_radius = (
            spacing_value + spacing_bucket_size - 1
        ) // spacing_bucket_size
        spacing_squared = spacing_value * spacing_value

        for offset_x in range(-bucket_radius, bucket_radius + 1):
            for offset_z in range(-bucket_radius, bucket_radius + 1):
                for placed_x, placed_y, placed_z in placed_spacing_buckets.get(
                    (bucket_x + offset_x, bucket_z + offset_z),
                    (),
                ):
                    if abs(y - placed_y) > 2:
                        continue
                    delta_x = x - placed_x
                    delta_z = z - placed_z
                    if delta_x * delta_x + delta_z * delta_z <= spacing_squared:
                        return True

        return False

    def _record_placed_spacing_position(
        self,
        x,
        y,
        z,
        use_row_spacing,
        placed_columns,
        placed_spacing_buckets,
        spacing_bucket_size,
    ):
        """Stores one placed light in the compact spacing index."""
        if use_row_spacing:
            placed_columns.setdefault((x, z), []).append(y)
            return

        key = self._spacing_bucket_key(x, z, spacing_bucket_size)
        placed_spacing_buckets.setdefault(key, []).append((x, y, z))

    def _run_operation(self, _):
        """
        Snapshots settings, runs Auto Light, and writes the built-in report.
        """
        # The custom busy state intentionally leaves the native control enabled,
        # so guard the operation entry point as well as the button event itself.
        if self._operation_running:
            return

        self._clear_log()
        self._reset_report()

        sel = self.canvas.selection.selection_group
        if not sel:
            self._log("Auto Light Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log("Operation not started: no selection was found.")
            self._finalize_report()
            _show_dark_message("No selection!", "Error", wx.OK, self)
            return

        # Snapshot the selection itself so changing it while the worker is
        # running cannot alter this operation midway through.
        selection_box_tuples = tuple(
            self._normalize_box_tuple(box)
            for box in sel.selection_boxes
        )
        if not selection_box_tuples:
            self._log("Auto Light Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log("Operation not started: no selection boxes were found.")
            self._finalize_report()
            _show_dark_message("No selection!", "Error", wx.OK, self)
            return

        dim = self.canvas.dimension
        plat = self.world.level_wrapper.platform
        ver = self.world.level_wrapper.version

        raw_spacing_value = int(self.spacing_slider.GetValue())
        radius = int(self.radius_slider.GetValue())
        use_smart_coverage = bool(self.smart_coverage_cb.GetValue())
        use_row_spacing = bool(self.row_spacing_cb.GetValue())
        treat_inactive_as_lit = bool(
            self.treat_inactive_lights_as_lit_cb.GetValue()
        )
        restrict_to_air = bool(self.air_only.GetValue())
        replace_plants = bool(self.replace_plants_cb.GetValue())

        # Snapshot every placement option before the worker operation begins.
        allow_floor_torches = bool(self.allow_floor_torches.GetValue())
        allow_wall_torches = bool(self.allow_walls.GetValue())
        allow_floor_lanterns = bool(self.allow_floor_lanterns.GetValue())
        allow_ceiling_lanterns = bool(self.allow_lanterns.GetValue())
        use_waxed_copper = bool(self.copper_waxed_cb.GetValue())
        place_lit_copper_bulbs = bool(self.copper_bulb_lit_cb.GetValue())

        # Row / grid spacing means skipped blocks between grid candidates.
        # Spread mode enforces a minimum circular placement distance of 1.
        row_grid_step = raw_spacing_value + 1
        spacing_value = (
            raw_spacing_value
            if use_row_spacing
            else max(1, raw_spacing_value)
        )

        choice = self.light_choice.GetStringSelection()
        try:
            base_block = self._get_selected_block()
            placement_kind = self._get_selection_kind(choice)
        except ValueError as exc:
            self._log("Auto Light Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log(f"Operation not started: {exc}")
            self._finalize_report()
            _show_dark_message(
                str(exc),
                "Auto Light",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        placed_block_name = (
            f"{base_block.namespace}:{base_block.base_name}"
            if getattr(base_block, "namespace", None)
            else str(base_block.base_name)
        )
        no_attachment_method = (
            placement_kind == "torch"
            and not allow_floor_torches
            and not allow_wall_torches
        ) or (
            placement_kind == "lantern"
            and not allow_floor_lanterns
            and not allow_ceiling_lanterns
        )

        self.status.SetLabel("Processing...")
        operation_ui_generation = self._begin_operation_ui()

        def operation():
            total_start = perf_counter()
            placed = 0
            changed_chunks = set()
            operation_error = None
            completed = False

            selection_time = 0.0
            light_scan_time = 0.0
            placement_time = 0.0
            chunk_finalize_time = 0.0

            counters = {
                "candidate_positions_checked": 0,
                "row_grid_positions_excluded": 0,
                "spacing_skips": 0,
                "target_restriction_skips": 0,
                "no_valid_placement": 0,
                "valid_placement_candidates": 0,
                "existing_coverage_skips": 0,
                "placed_coverage_skips": 0,
                "plants_replaced": 0,
                "connected_plant_halves_removed": 0,
                "connected_plant_boundary_skips": 0,
                "unavailable_selection_chunks": 0,
                "unavailable_selected_positions": 0,
                "placed_sources_added": 0,
            }

            self._log("Auto Light Report")
            self._log(
                f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self._log_section(
                "Settings",
                [
                    ("Light type", choice),
                    ("Placed block", placed_block_name),
                    (
                        "Detection mode",
                        "Calculated light coverage"
                        if use_smart_coverage
                        else "Legacy radius",
                    ),
                    *(
                        [("Placement order", "Center outward")]
                        if use_smart_coverage
                        else [("Light radius", radius)]
                    ),
                    (
                        "Treat inactive light sources as lit",
                        "On" if treat_inactive_as_lit else "Off",
                    ),
                    ("Light spacing", raw_spacing_value),
                    (
                        "Spacing mode",
                        "Row / grid" if use_row_spacing else "Spread",
                    ),
                    ("Only place on air", "On" if restrict_to_air else "Off"),
                    (
                        "Replace plants / grass",
                        "On" if replace_plants else "Off",
                    ),
                ],
            )

            if placement_kind == "torch":
                self._log(f"Allow floor torches: {'On' if allow_floor_torches else 'Off'}")
                self._log(f"Allow wall torches: {'On' if allow_wall_torches else 'Off'}")
            elif placement_kind == "lantern":
                self._log(f"Allow floor lanterns: {'On' if allow_floor_lanterns else 'Off'}")
                self._log(f"Allow ceiling lanterns: {'On' if allow_ceiling_lanterns else 'Off'}")
            if choice in COPPER_VARIANT_CHOICES:
                self._log(f"Waxed copper variant: {'On' if use_waxed_copper else 'Off'}")
            if choice in COPPER_BULB_CHOICES:
                self._log(f"Place lit copper bulb: {'On' if place_lit_copper_bulbs else 'Off'}")

            try:
                selection_start = perf_counter()
                raw_selected_volume = sum(
                    self._box_volume(box) for box in selection_box_tuples
                )
                unique_selection_boxes = self._deduplicate_box_tuples(
                    selection_box_tuples
                )
                if not unique_selection_boxes:
                    self._log_section(
                        "Selection",
                        [
                            ("Original selection boxes", len(selection_box_tuples)),
                            ("Result", "No non-empty selected volume remained"),
                        ],
                    )
                    completed = True
                    return

                unique_selected_volume = sum(
                    self._box_volume(box) for box in unique_selection_boxes
                )
                overlap_removed = max(
                    0,
                    raw_selected_volume - unique_selected_volume,
                )
                bounds = self._selection_bounds(unique_selection_boxes)
                chunk_regions = self._build_chunk_regions(
                    unique_selection_boxes
                )
                selection_chunks = {
                    (region[1], region[2]) for region in chunk_regions
                }
                center_x2, center_y2, center_z2 = (
                    self._selection_center_doubled(unique_selection_boxes)
                )
                if use_smart_coverage:
                    chunk_regions.sort(
                        key=lambda region: self._region_center_distance_key(
                            region,
                            center_x2,
                            center_y2,
                            center_z2,
                        )
                    )
                selection_time = perf_counter() - selection_start

                self._log_section(
                    "Selection",
                    [
                        ("Original selection boxes", len(selection_box_tuples)),
                        ("Raw selected volume", f"{raw_selected_volume:,} blocks"),
                        ("Unique selected volume", f"{unique_selected_volume:,} blocks"),
                        ("Overlapping volume removed", f"{overlap_removed:,} blocks"),
                        ("Non-overlapping regions", len(unique_selection_boxes)),
                        ("Chunk-local regions", len(chunk_regions)),
                        ("Selection chunks", len(selection_chunks)),
                        (
                            "Selection bounds",
                            f"X {bounds[0]} to {bounds[1] - 1}, "
                            f"Y {bounds[2]} to {bounds[3] - 1}, "
                            f"Z {bounds[4]} to {bounds[5] - 1}",
                        ),
                    ],
                )

                light_scan_start = perf_counter()
                detection_radius = (
                    SMART_LIGHT_MAX_DISTANCE
                    if use_smart_coverage
                    else radius
                )
                vertical_detection_radius = (
                    SMART_LIGHT_MAX_DISTANCE
                    if use_smart_coverage
                    else 1
                )
                light_index, light_stats = self._build_light_index(
                    unique_selection_boxes,
                    dim,
                    plat,
                    ver,
                    detection_radius,
                    vertical_detection_radius,
                    treat_inactive_as_lit,
                )
                light_buckets = (
                    self._build_light_buckets(light_index)
                    if use_smart_coverage
                    else None
                )
                initial_light_bucket_count = (
                    len(light_buckets) if light_buckets is not None else 0
                )
                light_scan_time = perf_counter() - light_scan_start

                detection_rows = [
                    (
                        "Existing sources included",
                        f"{light_stats['sources_included']:,}",
                    ),
                    (
                        "Light-capable sources found",
                        f"{light_stats['light_capable_sources_found']:,}",
                    ),
                    (
                        "Active sources found",
                        f"{light_stats['active_sources_found']:,}",
                    ),
                    (
                        "Source scan positions",
                        f"{light_stats['positions_scanned']:,}",
                    ),
                    (
                        "Source scan chunks checked",
                        f"{light_stats['chunks_checked']:,}",
                    ),
                    (
                        "Unavailable source-scan chunks",
                        f"{light_stats['missing_chunks']:,}",
                    ),
                ]
                if treat_inactive_as_lit:
                    detection_rows.append(
                        (
                            "Inactive sources treated as potentially lit",
                            f"{light_stats['inactive_sources_treated_as_lit']:,}",
                        )
                    )
                else:
                    detection_rows.append(
                        (
                            "Inactive sources ignored",
                            f"{light_stats['inactive_sources_ignored']:,}",
                        )
                    )
                if use_smart_coverage:
                    detection_rows.extend(
                        [
                            ("Initial Smart Coverage buckets", initial_light_bucket_count),
                            ("Maximum source scan distance", SMART_LIGHT_MAX_DISTANCE),
                        ]
                    )
                self._log_section("Light detection", detection_rows)

                grid_origin_x = min(
                    box[0] for box in unique_selection_boxes
                )
                grid_origin_z = min(
                    box[4] for box in unique_selection_boxes
                )

                allowed_x = allowed_z = None
                if use_row_spacing:
                    allowed_x, allowed_z = self._build_row_candidates(
                        unique_selection_boxes,
                        row_grid_step,
                        grid_origin_x,
                        grid_origin_z,
                    )

                support_cache = {}
                replace_cache = {}
                chunk_availability = {}

                # Spacing stores only placed lights. Memory therefore grows
                # with placements instead of excluded coordinate volume.
                placed_columns = {}
                placed_spacing_buckets = {}
                spacing_bucket_size = max(1, spacing_value)

                placement_start = perf_counter()
                for region in chunk_regions:
                    (
                        _order,
                        cx,
                        cz,
                        min_x,
                        max_x,
                        min_y,
                        max_y,
                        min_z,
                        max_z,
                    ) = region

                    available = chunk_availability.get((cx, cz))
                    if available is None:
                        available = bool(self.world.has_chunk(cx, cz, dim))
                        chunk_availability[(cx, cz)] = available
                    if not available:
                        counters["unavailable_selected_positions"] += (
                            (max_x - min_x)
                            * (max_y - min_y)
                            * (max_z - min_z)
                        )
                        continue

                    columns = self._ordered_region_columns(
                        min_x,
                        max_x,
                        min_z,
                        max_z,
                        center_x2,
                        center_z2,
                        use_smart_coverage,
                    )

                    for x, z in columns:
                        if use_row_spacing and (
                            x not in allowed_x or z not in allowed_z
                        ):
                            counters["row_grid_positions_excluded"] += (
                                max_y - min_y
                            )
                            continue

                        for y in range(min_y, max_y):
                            counters["candidate_positions_checked"] += 1

                            if self._has_placed_spacing_conflict(
                                x,
                                y,
                                z,
                                use_row_spacing,
                                spacing_value,
                                placed_columns,
                                placed_spacing_buckets,
                                spacing_bucket_size,
                            ):
                                counters["spacing_skips"] += 1
                                continue

                            current_block, _ = self.world.get_version_block(
                                x, y, z, dim, (plat, ver)
                            )

                            replaceable_current = (
                                replace_plants
                                and current_block.base_name not in AIR
                                and self._is_replaceable_target(
                                    current_block,
                                    replace_cache,
                                )
                            )
                            connected_partner = None
                            if replaceable_current:
                                (
                                    connected_replacement_safe,
                                    connected_partner,
                                ) = self._connected_plant_partner(
                                    x,
                                    y,
                                    z,
                                    dim,
                                    plat,
                                    ver,
                                    current_block,
                                    unique_selection_boxes,
                                )
                                if not connected_replacement_safe:
                                    counters[
                                        "connected_plant_boundary_skips"
                                    ] += 1
                                    continue

                            if restrict_to_air:
                                if (
                                    current_block.base_name not in AIR
                                    and not replaceable_current
                                ):
                                    counters["target_restriction_skips"] += 1
                                    continue

                            place = self._try_place(
                                x,
                                y,
                                z,
                                dim,
                                plat,
                                ver,
                                base_block,
                                current_block,
                                replace_plants,
                                placement_kind,
                                allow_floor_torches,
                                allow_wall_torches,
                                allow_floor_lanterns,
                                allow_ceiling_lanterns,
                                support_cache,
                                replace_cache,
                            )
                            if not place:
                                counters["no_valid_placement"] += 1
                                continue

                            counters["valid_placement_candidates"] += 1

                            ignored_existing_source = (
                                (x, y, z)
                                if (
                                    replaceable_current
                                    and current_block.base_name
                                    in REPLACEABLE_LIGHT_SOURCES
                                )
                                else None
                            )

                            if use_smart_coverage:
                                (
                                    calculated_level,
                                    source_is_placed,
                                ) = self._get_calculated_light_details(
                                    x,
                                    y,
                                    z,
                                    light_buckets,
                                    ignored_existing_source,
                                )
                                if calculated_level > 0:
                                    if source_is_placed:
                                        counters["placed_coverage_skips"] += 1
                                    else:
                                        counters["existing_coverage_skips"] += 1
                                    continue
                            elif self._has_legacy_nearby_light(
                                x,
                                y,
                                z,
                                light_index,
                                radius,
                                ignored_existing_source,
                            ):
                                counters["existing_coverage_skips"] += 1
                                continue

                            if replaceable_current:
                                counters["plants_replaced"] += 1
                                cleared_positions = (
                                    self._clear_connected_plant_half(
                                        connected_partner,
                                        dim,
                                        plat,
                                        ver,
                                        current_block.base_name,
                                    )
                                )
                                counters[
                                    "connected_plant_halves_removed"
                                ] += len(cleared_positions)
                                for (
                                    cleared_x,
                                    _cleared_y,
                                    cleared_z,
                                ) in cleared_positions:
                                    changed_chunks.add(
                                        block_coords_to_chunk_coords(
                                            cleared_x,
                                            cleared_z,
                                        )
                                    )

                            self.world.set_version_block(
                                x,
                                y,
                                z,
                                dim,
                                (plat, ver),
                                place,
                                None,
                            )
                            placed += 1

                            if use_smart_coverage:
                                placed_strength = self._estimate_light_strength(
                                    place,
                                    treat_inactive_as_lit,
                                )
                                if self._add_light_to_buckets(
                                    light_buckets,
                                    x,
                                    y,
                                    z,
                                    placed_strength,
                                ):
                                    counters["placed_sources_added"] += 1

                            self._record_placed_spacing_position(
                                x,
                                y,
                                z,
                                use_row_spacing,
                                placed_columns,
                                placed_spacing_buckets,
                                spacing_bucket_size,
                            )
                            changed_chunks.add((cx, cz))

                placement_time = perf_counter() - placement_start
                counters["unavailable_selection_chunks"] = sum(
                    1
                    for available in chunk_availability.values()
                    if not available
                )

                chunk_finalize_start = perf_counter()
                for changed_cx, changed_cz in changed_chunks:
                    try:
                        chunk = self.world.get_chunk(
                            changed_cx,
                            changed_cz,
                            dim,
                        )
                        chunk.changed = True
                    except Exception as exc:
                        if not self._is_missing_chunk_error(exc):
                            raise
                chunk_finalize_time = (
                    perf_counter() - chunk_finalize_start
                )

                spacing_records = (
                    sum(len(values) for values in placed_columns.values())
                    if use_row_spacing
                    else sum(
                        len(values)
                        for values in placed_spacing_buckets.values()
                    )
                )
                final_light_bucket_count = (
                    len(light_buckets) if light_buckets is not None else 0
                )

                result_rows = [
                    (
                        "Candidate positions checked",
                        f"{counters['candidate_positions_checked']:,}",
                    ),
                ]
                if use_row_spacing:
                    result_rows.append(
                        (
                            "Positions excluded by row / grid alignment",
                            f"{counters['row_grid_positions_excluded']:,}",
                        )
                    )
                result_rows.extend(
                    [
                        (
                            "Skipped by Light Spacing",
                            f"{counters['spacing_skips']:,}",
                        ),
                        (
                            "Skipped by target restriction",
                            f"{counters['target_restriction_skips']:,}",
                        ),
                        (
                            "No valid support or placement method",
                            f"{counters['no_valid_placement']:,}",
                        ),
                        (
                            "Valid placement candidates",
                            f"{counters['valid_placement_candidates']:,}",
                        ),
                        (
                            "Skipped by existing light coverage",
                            f"{counters['existing_coverage_skips']:,}",
                        ),
                    ]
                )
                if use_smart_coverage:
                    result_rows.append(
                        (
                            "Skipped by newly placed light coverage",
                            f"{counters['placed_coverage_skips']:,}",
                        )
                    )
                result_rows.extend(
                    [
                        ("Lights placed", f"{placed:,}"),
                        (
                            "Plants replaced",
                            f"{counters['plants_replaced']:,}",
                        ),
                        (
                            "Connected plant halves removed",
                            f"{counters['connected_plant_halves_removed']:,}",
                        ),
                        (
                            "Connected plants crossing selection skipped",
                            f"{counters['connected_plant_boundary_skips']:,}",
                        ),
                        ("Changed chunks", f"{len(changed_chunks):,}"),
                        (
                            "Unavailable selection chunks",
                            f"{counters['unavailable_selection_chunks']:,}",
                        ),
                        (
                            "Selected positions in unavailable chunks",
                            f"{counters['unavailable_selected_positions']:,}",
                        ),
                        ("Spacing records retained", f"{spacing_records:,}"),
                    ]
                )
                if use_smart_coverage:
                    result_rows.extend(
                        [
                            (
                                "New placement sources added to coverage",
                                f"{counters['placed_sources_added']:,}",
                            ),
                            (
                                "Final Smart Coverage buckets",
                                f"{final_light_bucket_count:,}",
                            ),
                        ]
                    )
                self._log_section("Placement results", result_rows)

                if placed == 0:
                    if counters["valid_placement_candidates"] == 0:
                        outcome = (
                            "No position had both an eligible target and a valid "
                            "placement arrangement."
                        )
                    elif (
                        counters["existing_coverage_skips"]
                        + counters["placed_coverage_skips"]
                        >= counters["valid_placement_candidates"]
                    ):
                        outcome = (
                            "Every valid placement candidate was already covered "
                            "by existing or calculated light."
                        )
                    else:
                        outcome = (
                            "No light was placed after applying coverage and "
                            "spacing rules."
                        )
                else:
                    outcome = f"Placed {placed:,} light(s) successfully."
                self._log(f"Outcome: {outcome}")
                completed = True

            except Exception as exc:
                operation_error = exc
                self._log_section(
                    "Operation failure",
                    [
                        ("Error type", exc.__class__.__name__),
                        ("Error", str(exc) or "No error message was provided"),
                        ("Lights placed before failure", f"{placed:,}"),
                    ],
                )
                raise

            finally:
                total_time = perf_counter() - total_start
                performance_rows = [
                    ("Selection preparation", self._format_seconds(selection_time)),
                    ("Existing-light scan", self._format_seconds(light_scan_time)),
                    ("Candidate scan and placement", self._format_seconds(placement_time)),
                    ("Changed-chunk finalization", self._format_seconds(chunk_finalize_time)),
                    ("Total operation time", self._format_seconds(total_time)),
                ]
                if light_scan_time > 0.0 and 'light_stats' in locals():
                    performance_rows.append(
                        (
                            "Existing-light scan speed",
                            self._format_rate(
                                light_stats["positions_scanned"],
                                light_scan_time,
                                "blocks",
                            ),
                        )
                    )
                if placement_time > 0.0:
                    performance_rows.append(
                        (
                            "Candidate processing speed",
                            self._format_rate(
                                counters["candidate_positions_checked"],
                                placement_time,
                                "positions",
                            ),
                        )
                    )
                self._log_section("Performance", performance_rows)

                warnings = []
                if use_smart_coverage:
                    warnings.append(
                        "Smart Coverage estimates open-space block light and "
                        "does not currently model walls or block opacity."
                    )
                if no_attachment_method:
                    warnings.append(
                        "The selected light type had no enabled placement method."
                    )
                if counters["unavailable_selection_chunks"]:
                    warnings.append(
                        f"{counters['unavailable_selection_chunks']:,} unavailable "
                        "selection chunk(s) were skipped."
                    )
                if (
                    'light_stats' in locals()
                    and light_stats["missing_chunks"]
                ):
                    warnings.append(
                        f"{light_stats['missing_chunks']:,} unavailable source-scan "
                        "chunk(s) were skipped."
                    )
                if (
                    use_smart_coverage
                    and placed > 0
                    and counters["placed_sources_added"] < placed
                ):
                    warnings.append(
                        "One or more placed lights contributed no calculated "
                        "coverage in their saved state."
                    )
                if operation_error is not None:
                    warnings.append(
                        "The operation ended with an exception. Partial world "
                        "changes may require review before saving."
                    )

                if warnings:
                    self._log("")
                    self._log("Warnings")
                    for warning in warnings:
                        self._log(f"• {warning}")

                if operation_error is not None:
                    status_label = (
                        f"Failed after placing {placed} lights in "
                        f"{total_time:.2f} seconds."
                    )
                elif completed:
                    status_label = (
                        f"Done. Placed {placed} lights in "
                        f"{total_time:.2f} seconds."
                    )
                else:
                    status_label = (
                        "Done. No selected volume was processed "
                        f"({total_time:.2f} seconds)."
                    )

                self._finalize_report()
                wx.CallAfter(
                    self._finish_operation_ui,
                    status_label,
                    operation_ui_generation,
                )

        try:
            self.canvas.run_operation(operation)
        except Exception as exc:
            # If the operation could not be scheduled, no worker report was
            # produced. Preserve a useful visible explanation instead.
            if not self._report_lines:
                self._log("Auto Light Report")
                self._log(
                    f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                self._log("")
                self._log(f"Operation failed to start: {exc}")
                self._finalize_report()
            self._operation_running = False
            self._restore_operation_buttons(operation_ui_generation)
            raise


# Amulet discovers this module-level registration directly.
export = dict(name="Auto Light", operation=AutoLighting)
