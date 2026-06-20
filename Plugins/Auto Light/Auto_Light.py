import ast
import json
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime
from time import perf_counter

import wx

from amulet.api.block import Block
from amulet_map_editor.programs.edit.api.behaviour import BlockSelectionBehaviour
from amulet_map_editor.programs.edit.api.operations import DefaultOperationUI
from amulet.utils import block_coords_to_chunk_coords
from amulet_nbt import TAG_String, TAG_Byte

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

SMART_LIGHT_MAX_DISTANCE = max(LIGHT_STRENGTH.values()) - 1
SMART_LIGHT_BUCKET_SIZE = 16

COPPER_BULB_BASES = {
    "copper_bulb",
    "exposed_copper_bulb",
    "weathered_copper_bulb",
    "oxidized_copper_bulb",
}
COPPER_BULB_NAMES = COPPER_BULB_BASES | {f"waxed_{name}" for name in COPPER_BULB_BASES}

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

UNSTACKABLE_LIGHT_BASES = set(LIGHT_SOURCES)

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

FULL_BLOCK_LIGHTS = {
    "sea_lantern",
    "copper_bulb",
    "exposed_copper_bulb",
    "weathered_copper_bulb",
    "oxidized_copper_bulb",
    "waxed_copper_bulb",
    "waxed_exposed_copper_bulb",
    "waxed_weathered_copper_bulb",
    "waxed_oxidized_copper_bulb",
}

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

NON_SOLID_KEYWORDS = (

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

REPLACEABLE_TARGET_BLOCKS = {

    "short_grass", "tall_grass",
    "short_dry_grass", "tall_dry_grass",
    "fern", "large_fern",

    "dandelion", "golden_dandelion",
    "poppy", "blue_orchid", "allium", "azure_bluet",
    "red_tulip", "orange_tulip", "white_tulip", "pink_tulip",
    "oxeye_daisy", "cornflower", "lily_of_the_valley",
    "wither_rose", "closed_eyeblossom", "open_eyeblossom",
    "cactus_flower",

    "sunflower", "lilac", "rose_bush", "peony",

    "bush", "firefly_bush", "sweet_berry_bush",
    "azalea", "flowering_azalea",

    "crimson_fungus", "warped_fungus",
    "crimson_roots", "warped_roots", "nether_sprouts",

    "dead_bush", "deadbush",
    "brown_mushroom", "red_mushroom",

    "seagrass", "kelp", "waterlily",
    "bamboo", "cactus",

    "vine", "glow_lichen", "hanging_roots",

    "small_dripleaf", "small_dripleaf_block",
    "big_dripleaf", "mangrove_propagule",

    "pitcher_crop", "pitcher_plant",
    "torchflower", "torchflower_crop",

    "pink_petals", "spore_blossom",
    "moss_carpet", "pale_moss_carpet",
    "leaf_litter", "wildflowers",
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
    "pitcher_crop",
    "pitcher_plant",
    "pale_moss_carpet",
}

REPLACEABLE_LIGHT_SOURCES = REPLACEABLE_TARGET_BLOCKS & LIGHT_SOURCES

class AutoLighting(wx.Panel, DefaultOperationUI):

    SETTINGS_CONFIG_FILENAME = "Auto Light.config"
    SETTINGS_CONFIG_FORMAT_VERSION = 1
    SETTINGS_SAVE_DELAY_MS = 500
    MAX_SETTINGS_CONFIG_BYTES = 1024 * 1024

    SETTINGS_VIEWPORT_HEIGHT = 340
    CONSOLE_PREFERRED_HEIGHT = 240
    CONSOLE_MIN_HEIGHT = 240

    CONSOLE_SEMANTIC_NAME = "AmuletPluginConsole:AutoLight"

    def __init__(self, parent, canvas, world, options_path):
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)

        self._settings_config_save_call = None
        self._settings_config_applying = False
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._settings_config_unknown_data = {}
        self._settings_defaults = {}

        self._report_lines = []
        self._last_report_text = ""

        wx.ToolTip.SetAutoPop(28000)

        s = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(s)

        self.scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.scroll.SetScrollRate(0, 15)
        self.scroll.SetMinSize((-1, self.SETTINGS_VIEWPORT_HEIGHT))
        s.Add(self.scroll, 0, wx.EXPAND)

        content = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetSizer(content)

        content.AddSpacer(10)

        title = wx.StaticText(self.scroll, label="Auto Light")
        title.SetToolTip("Automatically places lights in dark areas.")
        content.Add(title, 0, wx.ALL, 5)

        label = wx.StaticText(self.scroll, label="Light Type")
        label.SetToolTip("Select which light source will be placed.")
        content.Add(label, 0, wx.ALL, 5)

        self.light_choice = wx.Choice(self.scroll, choices=[
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
            "Firefly Bush"
        ])
        self.light_choice.SetSelection(0)
        self.light_choice.Bind(wx.EVT_CHOICE, self._on_light_change)
        self.light_choice.SetToolTip("Choose the light type.")
        content.Add(self.light_choice, 0, wx.EXPAND | wx.ALL, 5)

        self.radius_slider = wx.Slider(self.scroll, value=4, minValue=0, maxValue=15)
        self.radius_slider.SetToolTip(
            "Legacy detection distance for light sources that already exist before "
            "the operation starts. Source brightness is ignored in this mode."
        )

        self.radius_box = wx.TextCtrl(self.scroll, value="4", size=(50, -1))
        self.radius_box.SetToolTip("Manual legacy light-radius input.")

        self._bind(self.radius_slider, self.radius_box, 0, 15)

        self.radius_row = wx.BoxSizer(wx.HORIZONTAL)
        self.radius_row.Add(self.radius_slider, 1, wx.RIGHT, 5)
        self.radius_row.Add(self.radius_box)

        self.radius_label = wx.StaticText(self.scroll, label="Light Radius")
        self.radius_label.SetToolTip(
            "Legacy mode uses this exact radius around pre-existing light-source "
            "blocks, regardless of how strong or weak they are. Newly placed "
            "lights remain controlled by Light Spacing."
        )
        content.Add(self.radius_label, 0, wx.ALL, 5)
        content.Add(self.radius_row, 0, wx.EXPAND | wx.ALL, 5)

        self.smart_coverage_cb = wx.CheckBox(
            self.scroll,
            label="Use calculated light coverage",
        )
        self.smart_coverage_cb.SetValue(False)
        self.smart_coverage_cb.SetToolTip(
            "Uses estimated open-space block-light decay instead of the fixed "
            "Light Radius. The strongest nearby source wins; light levels are "
            "not added together. Newly placed lights join the calculation during "
            "this operation, while Light Spacing remains the minimum placement gap."
        )
        self.smart_coverage_cb.Bind(
            wx.EVT_CHECKBOX,
            self._on_detection_mode_change,
        )
        content.Add(self.smart_coverage_cb, 0, wx.ALL, 5)

        self.treat_inactive_lights_as_lit_cb = wx.CheckBox(
            self.scroll,
            label="Treat inactive light sources as lit",
        )
        self.treat_inactive_lights_as_lit_cb.SetValue(True)
        self.treat_inactive_lights_as_lit_cb.SetToolTip(
            "Counts supported light-emitting blocks as active even when their "
            "current block state is unlit or inactive. This helps avoid placing "
            "permanent lights near lamps, bulbs, campfires, furnaces, candles, "
            "and other sources that may activate later. Disable this to use "
            "their current supported in-world state."
        )
        content.Add(self.treat_inactive_lights_as_lit_cb, 0, wx.ALL, 5)

        self.spacing_slider = wx.Slider(self.scroll, value=7, minValue=0, maxValue=15)
        self.spacing_slider.SetToolTip("Row / grid mode: number of blocks skipped between lights. Spread mode still uses this as the older spread distance.")

        self.spacing_box = wx.TextCtrl(self.scroll, value="7", size=(50, -1))
        self.spacing_box.SetToolTip("Manual spacing input.")

        self._bind(self.spacing_slider, self.spacing_box, 0, 15)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self.spacing_slider, 1, wx.RIGHT, 5)
        row.Add(self.spacing_box)

        self.spacing_label = wx.StaticText(self.scroll, label="Light Spacing")
        self.spacing_label.SetToolTip("Row / grid mode uses this as skipped blocks between lights. Example: 5 skips five blocks, then places on the sixth block.")
        content.Add(self.spacing_label, 0, wx.ALL, 5)
        content.Add(row, 0, wx.EXPAND | wx.ALL, 5)

        self.row_spacing_cb = wx.CheckBox(self.scroll, label="Use row / grid spacing")
        self.row_spacing_cb.SetValue(False)
        self.row_spacing_cb.SetToolTip("Places lights in neat rows and columns instead of the older spread pattern.")
        content.Add(self.row_spacing_cb, 0, wx.ALL, 5)

        self.replace_plants_cb = wx.CheckBox(self.scroll, label="Replace plants / grass with lights")
        self.replace_plants_cb.SetValue(False)
        self.replace_plants_cb.SetToolTip("Allows plants, grass, flowers, and similar small blocks to be removed when a light is placed there. Connected halves of tall plants are removed too.")
        content.Add(self.replace_plants_cb, 0, wx.ALL, 5)

        self.torch_group_label = wx.StaticText(self.scroll, label="Torch options")
        self.torch_group_label.SetToolTip("Controls how torches are placed.")
        content.Add(self.torch_group_label, 0, wx.TOP | wx.LEFT, 8)

        self.allow_floor_torches = wx.CheckBox(self.scroll, label="Allow floor torches")
        self.allow_floor_torches.SetValue(True)
        self.allow_floor_torches.SetToolTip("Allows torches to be placed on solid floors.")
        content.Add(self.allow_floor_torches, 0, wx.ALL, 5)

        self.allow_walls = wx.CheckBox(self.scroll, label="Allow wall torches")
        self.allow_walls.SetValue(True)
        self.allow_walls.SetToolTip("Allows torches on walls.")
        content.Add(self.allow_walls, 0, wx.ALL, 5)

        self.lantern_group_label = wx.StaticText(self.scroll, label="Lantern options")
        self.lantern_group_label.SetToolTip("Controls how lanterns are placed.")
        content.Add(self.lantern_group_label, 0, wx.TOP | wx.LEFT, 8)

        self.allow_floor_lanterns = wx.CheckBox(self.scroll, label="Allow floor lanterns")
        self.allow_floor_lanterns.SetValue(True)
        self.allow_floor_lanterns.SetToolTip("Allows lanterns to be placed on solid floors.")
        content.Add(self.allow_floor_lanterns, 0, wx.ALL, 5)

        self.allow_lanterns = wx.CheckBox(self.scroll, label="Allow ceiling lanterns")
        self.allow_lanterns.SetValue(True)
        self.allow_lanterns.SetToolTip("Allows lanterns to hang.")
        content.Add(self.allow_lanterns, 0, wx.ALL, 5)

        self.copper_group_label = wx.StaticText(self.scroll, label="Copper options")
        self.copper_group_label.SetToolTip("Controls waxed copper variants and copper bulb brightness.")
        content.Add(self.copper_group_label, 0, wx.TOP | wx.LEFT, 8)

        self.copper_waxed_cb = wx.CheckBox(self.scroll, label="Waxed copper variants")
        self.copper_waxed_cb.SetValue(False)
        self.copper_waxed_cb.SetToolTip("Uses waxed copper lantern or copper bulb variants when available.")
        content.Add(self.copper_waxed_cb, 0, wx.ALL, 5)

        self.copper_bulb_lit_cb = wx.CheckBox(self.scroll, label="Lit copper bulbs")
        self.copper_bulb_lit_cb.SetValue(True)
        self.copper_bulb_lit_cb.SetToolTip("Places copper bulbs in their lit state.")
        content.Add(self.copper_bulb_lit_cb, 0, wx.ALL, 5)

        self.air_only = wx.CheckBox(self.scroll, label="Only place on air")
        self.air_only.SetValue(True)
        self.air_only.SetToolTip(
            "When enabled, lights are placed only in air, except approved plants "
            "when plant replacement is enabled. When disabled, eligible light "
            "types may replace other blocks."
        )
        content.Add(self.air_only, 0, wx.ALL, 5)

        self.manage_settings_button = wx.Button(
            self.scroll,
            label="Manage Plugin Files...",
        )
        self.manage_settings_button.SetToolTip(
            "Save, reset, repair, import, export, delete, or open the folder "
            "for Auto Light.config."
        )
        self.manage_settings_button.Bind(
            wx.EVT_BUTTON,
            self._manage_settings,
        )
        content.Add(
            self.manage_settings_button,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            10,
        )

        self.status = wx.StaticText(self.scroll, label="Idle")
        self.status.SetToolTip(
            "Shows the current operation state and the last run's total time."
        )
        content.Add(self.status, 0, wx.ALL, 5)

        content.AddSpacer(4)

        btn = wx.Button(self, label="Place Lights")
        btn.SetToolTip("Run auto-lighting.")
        btn.Bind(wx.EVT_BUTTON, self._run_operation)
        s.Add(btn, 0, wx.ALL | wx.EXPAND, 6)

        self.save_report_button = wx.Button(
            self,
            label="Save Last Report...",
        )
        self.save_report_button.Bind(
            wx.EVT_BUTTON,
            self._save_last_report,
        )
        self.save_report_button.Enable(False)
        self.save_report_button.SetToolTip(
            "Saves the latest Auto Light console report as a text file."
        )
        s.Add(
            self.save_report_button,
            0,
            wx.ALL | wx.EXPAND,
            6,
        )

        self.text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, self.CONSOLE_PREFERRED_HEIGHT),
        )
        self.text.SetName(self.CONSOLE_SEMANTIC_NAME)
        self.text.SetMinSize((320, self.CONSOLE_MIN_HEIGHT))
        self.text.SetForegroundColour(wx.Colour(0, 255, 0))
        self.text.SetBackgroundColour(wx.Colour(0, 0, 0))
        self.text.SetToolTip(
            "Shows the settings, selection, light detection, placement results, "
            "warnings, timing, and performance information for the latest run."
        )
        s.Add(self.text, 0, wx.ALL | wx.EXPAND, 4)

        self.Layout()
        self.scroll.FitInside()
        self.SetMinSize((380, 700))

        self._initialize_settings_persistence()

    def bind_events(self):
        super().bind_events()
        self._selection.bind_events()
        self._selection.enable()

    def enable(self):
        self._selection = BlockSelectionBehaviour(self.canvas)
        self._selection.enable()

    def _get_settings_config_path(self):
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
        control_names = (
            "light_choice",
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
        if isinstance(control, wx.CheckBox):
            return bool(control.GetValue())
        if isinstance(control, wx.Choice):
            return str(control.GetStringSelection())
        if isinstance(control, wx.Slider):
            return int(control.GetValue())
        raise TypeError(f"Unsupported settings control: {type(control)!r}")

    def _apply_settings_control_value(self, control, value):
        try:
            if isinstance(control, wx.CheckBox):
                if not isinstance(value, bool):
                    return False
                control.SetValue(value)
                return True

            if isinstance(control, wx.Choice):
                if not isinstance(value, str):
                    return False
                index = control.FindString(value)
                if index == wx.NOT_FOUND:
                    return False
                control.SetSelection(index)
                return True

            if isinstance(control, wx.Slider):
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
        }

    def _capture_settings_defaults(self):
        self._settings_defaults = self._collect_current_settings_config()

    def _load_settings_config_data(self, path):
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
        self._settings_config_applying = True
        try:
            saved_settings = data.get("settings", {})
            for key, control in self._settings_control_registry().items():
                if key in saved_settings:
                    self._apply_settings_control_value(
                        control,
                        saved_settings[key],
                    )

            self.radius_box.ChangeValue(str(self.radius_slider.GetValue()))
            self.spacing_box.ChangeValue(str(self.spacing_slider.GetValue()))

            self._settings_config_unknown_data = dict(data)
            self._update_ui_visibility()
        finally:
            self._settings_config_applying = False

    def _merge_settings_config_data(self, existing):
        merged = dict(existing) if isinstance(existing, dict) else {}
        current = self._collect_current_settings_config()

        merged["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        merged["plugin"] = "Auto Light"

        existing_settings = merged.get("settings")
        if not isinstance(existing_settings, dict):
            existing_settings = {}
        existing_settings.update(current["settings"])
        merged["settings"] = existing_settings
        return merged

    def _write_text_atomically(self, destination, content):
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
            self._settings_config_unknown_data = merged
            self._settings_config_load_error = ""
            self._settings_config_write_error = ""
            return True
        except Exception as exc:
            self._settings_config_write_error = str(exc)
            return False

    def _schedule_settings_config_save(self, event=None):
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
        self._settings_config_save_call = None
        self._write_settings_config(create_if_missing=True)

    def _bind_settings_persistence_events(self):
        custom_controls = (
            self.light_choice,
            self.smart_coverage_cb,
            self.radius_slider,
            self.spacing_slider,
        )

        for control in self._settings_control_registry().values():
            if any(control is custom for custom in custom_controls):
                continue
            try:
                if isinstance(control, wx.CheckBox):
                    control.Bind(
                        wx.EVT_CHECKBOX,
                        self._schedule_settings_config_save,
                    )
                elif isinstance(control, wx.Choice):
                    control.Bind(
                        wx.EVT_CHOICE,
                        self._schedule_settings_config_save,
                    )
            except Exception:
                continue

    def _initialize_settings_persistence(self):
        self._capture_settings_defaults()
        path = self._get_settings_config_path()
        self._settings_config_load_error = ""
        data = self._load_settings_config_data(path)

        if data is not None:
            self._apply_settings_config_data(data)

            self._write_settings_config(create_if_missing=False)
        else:
            self._update_ui_visibility()
            if path.is_file() and self._settings_config_load_error:
                self.status.SetLabel(
                    "Settings file needs repair. Use Manage settings."
                )

        self._bind_settings_persistence_events()

    def _stop_pending_settings_save(self):
        pending = self._settings_config_save_call
        self._settings_config_save_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _reset_settings_to_defaults(self):
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
        self._settings_config_unknown_data = dict(defaults)
        self._apply_settings_config_data(defaults)
        return True

    def _repair_json_missing_line_commas(self, content):
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

        try:
            literal_data = ast.literal_eval(with_line_commas)
            if isinstance(literal_data, dict):
                repairs.append("normalized Python-style JSON values")
                return literal_data, repairs
        except Exception:
            pass

        return None, repairs

    def _validate_repaired_settings_config(self, data):
        if not isinstance(data, dict):
            return False, "The top-level value is not an object."
        if not isinstance(data.get("settings", {}), dict):
            return False, "The settings entry is not an object."
        return True, ""

    def _merge_recovered_settings_config_data(self, recovered):
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
        return merged

    def _repair_existing_settings_config(self):
        path = self._get_settings_config_path()
        if not path.is_file():
            wx.MessageBox(
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
            wx.MessageBox(
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
            wx.MessageBox(
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
            wx.MessageBox(
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
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._settings_config_unknown_data = merged
        self._apply_settings_config_data(merged)

        wx.MessageBox(
            "The settings file was repaired and reloaded successfully.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _import_settings_config(self):
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
            wx.MessageBox(
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
            wx.MessageBox(
                "The selected settings were valid, but the active settings "
                "file could not be written.\n\n"
                f"Reason: {exc}",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._settings_config_unknown_data = merged
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_config_data(merged)
        wx.MessageBox(
            "Settings imported successfully.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _export_settings_config(self):
        active_path = self._get_settings_config_path()
        existing = None
        if active_path.is_file():
            self._settings_config_load_error = ""
            existing = self._load_settings_config_data(active_path)
            if existing is None:
                wx.MessageBox(
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
            wx.MessageBox(
                f"Could not export the settings file.\n\nReason: {exc}",
                "Auto Light",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        wx.MessageBox(
            "Settings exported successfully.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _show_settings_action_dialog(self, actions):
        parent = wx.GetTopLevelParent(self) or self
        dialog = wx.Dialog(
            parent,
            title="Manage Auto Light settings",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        dialog.SetMinSize((470, 350))
        dialog.SetSize((520, 380))

        outer = wx.BoxSizer(wx.VERTICAL)
        description = wx.StaticText(
            dialog,
            label="Choose what to do with Auto Light.config.",
        )
        description.SetMinSize((-1, 78))
        description.Wrap(440)
        outer.Add(description, 0, wx.EXPAND | wx.ALL, 12)

        choices = wx.ListBox(
            dialog,
            choices=[label for label, _ in actions],
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
            description.Wrap(440)
            open_button.Enable(True)
            dialog.Layout()

        def open_selected(event):
            if choices.GetSelection() != wx.NOT_FOUND:
                dialog.EndModal(wx.ID_OK)

        choices.Bind(wx.EVT_LISTBOX, update_description)
        choices.Bind(wx.EVT_LISTBOX_DCLICK, open_selected)
        dialog.CenterOnParent()

        try:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            selection = choices.GetSelection()
            return selection if selection != wx.NOT_FOUND else None
        finally:
            dialog.Destroy()

    def _manage_settings(self, _):
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
                wx.MessageBox(
                    "Current settings were saved successfully.",
                    "Auto Light",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                wx.MessageBox(
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
                wx.MessageBox(
                    f"Could not open the settings folder.\n\nReason: {exc}",
                    "Auto Light",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            return

        if action == 2:
            confirmation = wx.MessageDialog(
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
                wx.MessageBox(
                    "Auto Light settings were reset successfully.",
                    "Auto Light",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                wx.MessageBox(
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

        confirmation = wx.MessageDialog(
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
            wx.MessageBox(
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
        self._settings_config_unknown_data = {}

        wx.MessageBox(
            "Auto Light.config was deleted and visible settings were restored "
            "to defaults.",
            "Auto Light",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _clear_log(self):
        try:
            wx.CallAfter(self.text.SetValue, "")
        except Exception:
            try:
                self.text.SetValue("")
            except Exception:
                pass

    def _append_log_text(self, message):
        try:
            self.text.AppendText(str(message) + "\n")
        except Exception:
            pass

    def _log(self, message):
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
        self._report_lines = []
        self._last_report_text = ""
        try:
            self.save_report_button.Enable(False)
        except Exception:
            pass

    def _finalize_report(self):
        self._last_report_text = "\n".join(self._report_lines).strip()
        if not self._last_report_text:
            return

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
            wx.MessageBox(
                f"Report saved:\n{path}",
                "Report Saved",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        except Exception as exc:
            wx.MessageBox(
                f"Could not save report:\n{exc}",
                "Save Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    @staticmethod
    def _format_seconds(seconds):
        try:
            seconds = max(0.0, float(seconds))
        except (TypeError, ValueError):
            seconds = 0.0
        return f"{seconds:.3f} seconds"

    @staticmethod
    def _format_rate(amount, seconds, unit="positions"):
        try:
            seconds = float(seconds)
            amount = int(amount)
        except (TypeError, ValueError):
            return f"0 {unit}/second"
        if seconds <= 0.0:
            return f"{amount:,} {unit}/second"
        return f"{amount / seconds:,.0f} {unit}/second"

    @staticmethod
    def _box_volume(box):
        min_x, max_x, min_y, max_y, min_z, max_z = box
        return max(0, max_x - min_x) * max(0, max_y - min_y) * max(0, max_z - min_z)

    @staticmethod
    def _selection_bounds(boxes):
        return (
            min(box[0] for box in boxes),
            max(box[1] for box in boxes),
            min(box[2] for box in boxes),
            max(box[3] for box in boxes),
            min(box[4] for box in boxes),
            max(box[5] for box in boxes),
        )

    def _log_section(self, title, rows):
        self._log("")
        self._log(title)
        for label, value in rows:
            self._log(f"{label}: {value}")

    @staticmethod
    def _tag_to_python_value(value):
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

        vanilla_count = self._state_int(
            self._get_block_property(block, ("candles",))
        )
        if vanilla_count is not None:
            if 0 <= vanilla_count <= 3:
                return vanilla_count + 1
            return 1

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
        x, y, z = pos
        return any(
            min_x <= x < max_x
            and min_y <= y < max_y
            and min_z <= z < max_z
            for min_x, max_x, min_y, max_y, min_z, max_z in boxes
        )

    @staticmethod
    def _subtract_box_tuple(box, cutter):
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
        size = SMART_LIGHT_BUCKET_SIZE
        return x // size, y // size, z // size

    def _build_light_buckets(self, light_index):
        buckets = {}
        for (x, y, z), strength in light_index.items():
            key = self._light_bucket_key(x, y, z)
            buckets.setdefault(key, []).append(
                (x, y, z, strength, False)
            )
        return buckets

    def _add_light_to_buckets(self, light_buckets, x, y, z, strength):
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

    def _get_calculated_light_level(self, x, y, z, light_buckets):
        level, _is_placed = self._get_calculated_light_details(
            x, y, z, light_buckets
        )
        return level

    @staticmethod
    def _is_missing_chunk_error(exc):
        return exc.__class__.__name__ == "ChunkDoesNotExist"

    def _get_block_if_available(self, x, y, z, dim, plat, ver):
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
        name = block.base_name
        if name in AIR:
            return False

        for key in FIREFLY_SUPPORT_KEYWORDS:
            if key in name:
                return True

        return False

    def _is_replaceable_target(self, block, cache=None):
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

        return True, None

    def _clear_connected_plant_half(
        self,
        partner_pos,
        dim,
        plat,
        ver,
        expected_name,
    ):
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

    def _on_light_change(self, event):
        self._update_ui_visibility()
        self._schedule_settings_config_save(event)

    def _on_detection_mode_change(self, event):
        self._update_ui_visibility()
        self._schedule_settings_config_save(event)

    def _update_ui_visibility(self):
        choice = self.light_choice.GetStringSelection()

        is_torch = choice in TORCH_CHOICES
        is_lantern = choice in LANTERN_CHOICES
        is_copper_variants = choice in COPPER_VARIANT_CHOICES
        is_copper_bulb = choice in COPPER_BULB_CHOICES
        use_smart_coverage = self.smart_coverage_cb.GetValue()

        self.radius_label.Show(not use_smart_coverage)
        self.radius_slider.Show(not use_smart_coverage)
        self.radius_box.Show(not use_smart_coverage)

        if is_torch:
            self.torch_group_label.Show()
            self.allow_floor_torches.Show()
            self.allow_walls.Show()
        else:
            self.torch_group_label.Hide()
            self.allow_floor_torches.Hide()
            self.allow_walls.Hide()

        if is_lantern:
            self.lantern_group_label.Show()
            self.allow_floor_lanterns.Show()
            self.allow_lanterns.Show()
        else:
            self.lantern_group_label.Hide()
            self.allow_floor_lanterns.Hide()
            self.allow_lanterns.Hide()

        if is_copper_variants:
            self.copper_group_label.Show()
            self.copper_waxed_cb.Show()
        else:
            self.copper_group_label.Hide()
            self.copper_waxed_cb.Hide()

        if is_copper_bulb:
            self.copper_bulb_lit_cb.Show()
        else:
            self.copper_bulb_lit_cb.Hide()

        self.Layout()
        self.scroll.FitInside()

    def _bind(self, slider, box, min_v, max_v):
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

    def _torch_block(self, direction, base_name):
        return Block(
            "minecraft",
            base_name,
            {"torch_facing_direction": TAG_String(direction)}
        )

    def _get_selected_block(self):
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

        if placement_kind == "full":
            return base_block

        below = self._get_block_if_available(
            x, y - 1, z, dim, plat, ver
        )
        if below is None:
            return None

        if below.base_name in UNSTACKABLE_LIGHT_BASES:
            return None

        if placement_kind == "firefly":
            if not self._is_firefly_support(below):
                return None

            if current_block.base_name in AIR:
                return base_block

            if replace_plants and self._is_replaceable_target(current_block, replace_cache):
                return base_block

            return None

        if self._is_valid_support(below, support_cache):
            if placement_kind == "torch" and allow_floor_torches:
                return self._torch_block("top", base_block.base_name)

            if placement_kind == "lantern" and allow_floor_lanterns:
                return Block("minecraft", base_block.base_name, {"hanging": TAG_Byte(0)})

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

        if placement_kind == "lantern" and allow_ceiling_lanterns:
            above = self._get_block_if_available(
                x, y + 1, z, dim, plat, ver
            )

            if above is not None and self._is_valid_support(above, support_cache):
                return Block("minecraft", base_block.base_name, {"hanging": TAG_Byte(1)})

        return None

    def _build_row_candidates(self, selection_boxes, grid_step, grid_origin_x, grid_origin_z):
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
        if use_row_spacing:
            placed_columns.setdefault((x, z), []).append(y)
            return

        key = self._spacing_bucket_key(x, z, spacing_bucket_size)
        placed_spacing_buckets.setdefault(key, []).append((x, y, z))

    def _run_operation(self, _):
        self._clear_log()
        self._reset_report()

        sel = self.canvas.selection.selection_group
        if not sel:
            self._log("Auto Light Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log("Operation not started: no selection was found.")
            self._finalize_report()
            wx.MessageBox("No selection!", "Error", wx.OK, self)
            return

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
            wx.MessageBox("No selection!", "Error", wx.OK, self)
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

        allow_floor_torches = bool(self.allow_floor_torches.GetValue())
        allow_wall_torches = bool(self.allow_walls.GetValue())
        allow_floor_lanterns = bool(self.allow_floor_lanterns.GetValue())
        allow_ceiling_lanterns = bool(self.allow_lanterns.GetValue())
        use_waxed_copper = bool(self.copper_waxed_cb.GetValue())
        place_lit_copper_bulbs = bool(self.copper_bulb_lit_cb.GetValue())

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
            wx.MessageBox(
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

                wx.CallAfter(self.status.SetLabel, status_label)
                self._finalize_report()

        try:
            self.canvas.run_operation(operation)
        except Exception as exc:

            if not self._report_lines:
                self._log("Auto Light Report")
                self._log(
                    f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                self._log("")
                self._log(f"Operation failed to start: {exc}")
                self._finalize_report()
            raise

export = dict(name="Auto Light", operation=AutoLighting)
