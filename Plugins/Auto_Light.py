import wx
from time import perf_counter

from amulet.api.block import Block
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

    "froglight": 15,
    "pearlescent_froglight": 15,
    "verdant_froglight": 15,
    "ochre_froglight": 15,

    "crying_obsidian": 10,

    "conduit": 15,
    "respawn_anchor": 15,

    "blast_furnace": 13,
    "furnace": 13,
    "smoker": 13,

    "sea_pickle": 15,
    "glow_lichen": 7,
    "redstone_torch": 7,

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

COPPER_BULB_BASES = {
    "copper_bulb",
    "exposed_copper_bulb",
    "weathered_copper_bulb",
    "oxidized_copper_bulb",
}
COPPER_BULB_NAMES = COPPER_BULB_BASES | {f"waxed_{name}" for name in COPPER_BULB_BASES}

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
    "short_grass", "tall_grass", "reeds", "leaves", "pink_petals", "leaf_litter", "wildflowers", "flower",
    "torch", "soul_torch", "copper_torch", "lantern", "copper_lantern", "soul_lantern",
    "firefly_bush", "sea_lantern",
    "copper_bulb", "exposed_copper_bulb", "weathered_copper_bulb", "oxidized_copper_bulb",
    "waxed_copper_bulb", "waxed_exposed_copper_bulb", "waxed_weathered_copper_bulb", "waxed_oxidized_copper_bulb",
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
    "candle", "white_candle", "orange_candle", "magenta_candle", "light_blue_candle",
    "yellow_candle", "lime_candle", "pink_candle", "gray_candle", "light_gray_candle",
    "cyan_candle", "purple_candle", "blue_candle", "brown_candle", "green_candle",
    "red_candle", "black_candle",
    "froglight", "pearlescent_froglight", "verdant_froglight", "ochre_froglight",
    "glowstone", "sea_pickle", "shroomlight",
    "jack_o_lantern", "lit_pumpkin", "redstone_lamp", "redstone_torch",
    "beacon", "campfire", "soul_campfire",
    "blast_furnace", "furnace", "smoker", "brewing_stand",
    "amethyst_cluster", "large_amethyst_bud", "medium_amethyst_bud", "small_amethyst_bud",
    "end_rod", "end_portal_frame", "dragon_egg",
    "glow_lichen", "sculk_sensor", "calibrated_sculk_sensor", "sculk_catalyst",
    "firefly_bush",
)

REPLACEABLE_TARGET_BLOCKS = {
    "short_grass", "tall_grass",
    "dandelion", "poppy", "blue_orchid", "allium", "azure_bluet",
    "red_tulip", "orange_tulip", "white_tulip", "pink_tulip",
    "oxeye_daisy", "cornflower", "lily_of_the_valley",
    "wither_rose", "sunflower", "lilac", "rose_bush", "peony",
    "crimson_fungus", "warped_fungus",
    "crimson_roots", "warped_roots",
    "nether_sprouts", "dead_bush",
    "seagrass", "kelp",
    "bamboo", "cactus",
    "sweet_berry_bush",
    "vine", "fern", "large_fern",
    "brown_mushroom", "red_mushroom",
    "small_dripleaf", "big_dripleaf",
    "mangrove_propagule", "pitcher_crop",
    "torchflower", "torchflower_crop",
    "pink_petals", "spore_blossom",
    "azalea", "flowering_azalea",
    "leaf_litter", "wildflowers",
}

DOUBLE_HEIGHT_PLANTS = {
    "tall_grass",
    "sunflower",
    "lilac",
    "rose_bush",
    "peony",
    "large_fern",
    "pitcher_crop",
    "torchflower_crop",
}

class AutoLighting(wx.Panel, DefaultOperationUI):
    def __init__(self, parent, canvas, world, options_path):
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)

        wx.ToolTip.SetAutoPop(15000)

        s = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(s)

        self.scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.scroll.SetScrollRate(0, 15)
        s.Add(self.scroll, 1, wx.EXPAND)

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
        self.radius_slider.SetToolTip("Distance to search for nearby light sources.")

        self.radius_box = wx.TextCtrl(self.scroll, value="4", size=(50, -1))
        self.radius_box.SetToolTip("Manual radius input.")

        self._bind(self.radius_slider, self.radius_box, 0, 15)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self.radius_slider, 1, wx.RIGHT, 5)
        row.Add(self.radius_box)

        lbl = wx.StaticText(self.scroll, label="Light Radius")
        lbl.SetToolTip("Higher = fewer lights but slower.")
        content.Add(lbl, 0, wx.ALL, 5)
        content.Add(row, 0, wx.EXPAND | wx.ALL, 5)

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
        self.air_only.SetToolTip("Prevents replacing blocks unless replacement is allowed for small plants and grass.")
        content.Add(self.air_only, 0, wx.ALL, 5)

        btn = wx.Button(self.scroll, label="Place Lights")
        btn.SetToolTip("Run auto-lighting.")
        btn.Bind(wx.EVT_BUTTON, self._run_operation)
        content.Add(btn, 0, wx.EXPAND | wx.ALL, 10)

        self.status = wx.StaticText(self.scroll, label="Idle")
        self.status.SetToolTip("Shows operation status.")
        content.Add(self.status, 0, wx.ALL, 5)

        self.runtime = wx.StaticText(self.scroll, label="Run time: --")
        self.runtime.SetToolTip("Shows how long the last lighting operation took.")
        content.Add(self.runtime, 0, wx.ALL, 5)

        content.AddSpacer(10)

        self.Layout()
        self.scroll.FitInside()
        self.SetMinSize((275, 460))

        self._update_ui_visibility()

    def _is_emitting_light(self, block):
        name = block.base_name

        if name in COPPER_BULB_NAMES:
            props = getattr(block, "properties", {}) or {}
            lit = props.get("lit")
            if lit is not None and str(lit).lower() != "true":
                return False

        return name in LIGHT_SOURCES

    def _estimate_light_strength(self, block):
        return LIGHT_STRENGTH.get(block.base_name, 15)

    def _build_light_index(self, selection_boxes, dim, plat, ver, radius):
        light_index = {}

        min_x = min(box.min_x for box in selection_boxes) - radius
        max_x = max(box.max_x for box in selection_boxes) + radius
        min_y = min(box.min_y for box in selection_boxes) - 1
        max_y = max(box.max_y for box in selection_boxes) + 1
        min_z = min(box.min_z for box in selection_boxes) - radius
        max_z = max(box.max_z for box in selection_boxes) + radius

        min_cx = min_x // 16
        max_cx = (max_x - 1) // 16
        min_cz = min_z // 16
        max_cz = (max_z - 1) // 16

        for cx in range(min_cx, max_cx + 1):
            for cz in range(min_cz, max_cz + 1):
                if not self.world.has_chunk(cx, cz, dim):
                    continue

                chunk_min_x = max(min_x, cx * 16)
                chunk_max_x = min(max_x, cx * 16 + 16)
                chunk_min_z = max(min_z, cz * 16)
                chunk_max_z = min(max_z, cz * 16 + 16)

                for x in range(chunk_min_x, chunk_max_x):
                    for y in range(min_y, max_y):
                        for z in range(chunk_min_z, chunk_max_z):
                            block, _ = self.world.get_version_block(
                                x, y, z, dim, (plat, ver)
                            )

                            if self._is_emitting_light(block):
                                light_index[(x, y, z)] = self._estimate_light_strength(block)

        return light_index

    def _get_nearby_light_strength(self, x, y, z, light_index, radius):
        max_effective_strength = 0

        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                if dx * dx + dz * dz > radius * radius:
                    continue

                for dy in (-1, 0, 1):
                    source_strength = light_index.get((x + dx, y + dy, z + dz))
                    if source_strength is None:
                        continue

                    distance = max(abs(dx), abs(dy), abs(dz))
                    effective_strength = source_strength - distance

                    if effective_strength > max_effective_strength:
                        max_effective_strength = effective_strength
                        if max_effective_strength >= 15:
                            return 15

        return max_effective_strength

    def _is_valid_support(self, block, cache=None):
        name = block.base_name

        if cache is not None and name in cache:
            return cache[name]

        if name in AIR:
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

    def _clear_connected_plant_half(self, x, y, z, dim, plat, ver, block):
        cleared = []

        if block.base_name not in DOUBLE_HEIGHT_PLANTS:
            return cleared

        candidates = [(x, y + 1, z), (x, y - 1, z)]

        props = getattr(block, "properties", {}) or {}
        upper_bit = props.get("upper_block_bit")
        half = props.get("half")

        if upper_bit is not None:
            upper_value = str(upper_bit).lower() in ("true", "1", "yes")
            partner = (x, y - 1, z) if upper_value else (x, y + 1, z)
            candidates = [partner]
        elif half is not None:
            half_value = str(half).lower()
            if half_value == "upper":
                candidates = [(x, y - 1, z)]
            elif half_value == "lower":
                candidates = [(x, y + 1, z)]

        air = Block("minecraft", "air")

        for px, py, pz in candidates:
            if not self.world.has_chunk(*block_coords_to_chunk_coords(px, pz), dim):
                continue

            partner_block, _ = self.world.get_version_block(
                px, py, pz, dim, (plat, ver)
            )

            if partner_block.base_name == block.base_name:
                self.world.set_version_block(
                    px, py, pz, dim, (plat, ver), air, None
                )
                cleared.append((px, py, pz))

        return cleared

    def _on_light_change(self, event):
        self._update_ui_visibility()

    def _update_ui_visibility(self):
        choice = self.light_choice.GetStringSelection()

        is_torch = choice in TORCH_CHOICES
        is_lantern = choice in LANTERN_CHOICES
        is_copper_variants = choice in COPPER_VARIANT_CHOICES
        is_copper_bulb = choice in COPPER_BULB_CHOICES

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

        def on_text(event):
            try:
                v = int(box.GetValue())
                v = max(min_v, min(max_v, v))
                slider.SetValue(v)
            except:
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

        return Block("minecraft", "lantern")

    def _get_selection_kind(self, choice):
        if choice == "Firefly Bush":
            return "firefly"
        if choice in FULL_BLOCK_CHOICES:
            return "full"
        if choice in TORCH_CHOICES:
            return "torch"
        if choice in LANTERN_CHOICES:
            return "lantern"
        return "lantern"

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
        support_cache=None,
        replace_cache=None
    ):
        below, _ = self.world.get_version_block(x, y - 1, z, dim, (plat, ver))

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

        if placement_kind == "full":
            return base_block

        if self._is_valid_support(below, support_cache):
            if placement_kind == "torch" and self.allow_floor_torches.GetValue():
                return self._torch_block("top", base_block.base_name)

            if placement_kind == "lantern" and self.allow_floor_lanterns.GetValue():
                return Block("minecraft", base_block.base_name, {"hanging": TAG_Byte(0)})

        if placement_kind == "torch" and self.allow_walls.GetValue():
            directions = {
                (1, 0): "east",
                (-1, 0): "west",
                (0, 1): "south",
                (0, -1): "north",
            }

            for (dx, dz), facing in directions.items():
                side_block, _ = self.world.get_version_block(
                    x + dx, y, z + dz, dim, (plat, ver)
                )

                if self._is_valid_support(side_block, support_cache):
                    return self._torch_block(facing, base_block.base_name)

        if placement_kind == "lantern" and self.allow_lanterns.GetValue():
            above, _ = self.world.get_version_block(x, y + 1, z, dim, (plat, ver))

            if self._is_valid_support(above, support_cache):
                return Block("minecraft", base_block.base_name, {"hanging": TAG_Byte(1)})

        return None

    def _build_row_candidates(self, selection_boxes, grid_step, grid_origin_x, grid_origin_z):
        allowed_x = set()
        allowed_z = set()

        for box in selection_boxes:
            for x in range(box.min_x, box.max_x):
                if (x - grid_origin_x) % grid_step == 0:
                    allowed_x.add(x)

            for z in range(box.min_z, box.max_z):
                if (z - grid_origin_z) % grid_step == 0:
                    allowed_z.add(z)

        return allowed_x, allowed_z

    def _run_operation(self, _):
        sel = self.canvas.selection.selection_group
        if not sel:
            wx.MessageBox("No selection!", "Error", wx.OK)
            return

        dim = self.canvas.dimension
        plat = self.world.level_wrapper.platform
        ver = self.world.level_wrapper.version

        raw_spacing_value = self.spacing_slider.GetValue()
        radius = self.radius_slider.GetValue()
        use_row_spacing = self.row_spacing_cb.GetValue()
        row_grid_step = raw_spacing_value + 1
        spacing_value = raw_spacing_value if use_row_spacing else max(1, raw_spacing_value)
        replace_plants = self.replace_plants_cb.GetValue()

        choice = self.light_choice.GetStringSelection()
        base_block = self._get_selected_block()
        placement_kind = self._get_selection_kind(choice)

        self.status.SetLabel("Processing...")
        self.runtime.SetLabel("Run time: Running...")

        def operation():
            start_time = perf_counter()
            placed = 0
            blocked = set()

            try:
                light_index = self._build_light_index(sel.selection_boxes, dim, plat, ver, radius)

                grid_origin_x = min(box.min_x for box in sel.selection_boxes)
                grid_origin_z = min(box.min_z for box in sel.selection_boxes)

                allowed_x = allowed_z = None
                if use_row_spacing:
                    allowed_x, allowed_z = self._build_row_candidates(
                        sel.selection_boxes,
                        row_grid_step,
                        grid_origin_x,
                        grid_origin_z,
                    )

                support_cache = {}
                replace_cache = {}

                for box in sel.selection_boxes:
                    min_cx = box.min_x // 16
                    max_cx = (box.max_x - 1) // 16
                    min_cz = box.min_z // 16
                    max_cz = (box.max_z - 1) // 16

                    for cx in range(min_cx, max_cx + 1):
                        chunk_min_x = max(box.min_x, cx * 16)
                        chunk_max_x = min(box.max_x, cx * 16 + 16)

                        if use_row_spacing:
                            chunk_xs = [x for x in range(chunk_min_x, chunk_max_x) if x in allowed_x]
                            if not chunk_xs:
                                continue
                        else:
                            chunk_xs = range(chunk_min_x, chunk_max_x)

                        for cz in range(min_cz, max_cz + 1):
                            if not self.world.has_chunk(cx, cz, dim):
                                continue

                            chunk_min_z = max(box.min_z, cz * 16)
                            chunk_max_z = min(box.max_z, cz * 16 + 16)

                            if use_row_spacing:
                                chunk_zs = [z for z in range(chunk_min_z, chunk_max_z) if z in allowed_z]
                                if not chunk_zs:
                                    continue
                            else:
                                chunk_zs = range(chunk_min_z, chunk_max_z)

                            for x in chunk_xs:
                                for z in chunk_zs:
                                    for y in range(box.min_y, box.max_y):
                                        if (x, y, z) in blocked:
                                            continue

                                        current_block, _ = self.world.get_version_block(
                                            x, y, z, dim, (plat, ver)
                                        )

                                        if self.air_only.GetValue():
                                            if current_block.base_name not in AIR:
                                                if not (
                                                    replace_plants
                                                    and self._is_replaceable_target(current_block, replace_cache)
                                                ):
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
                                            support_cache,
                                            replace_cache,
                                        )
                                        if not place:
                                            continue

                                        if self._get_nearby_light_strength(x, y, z, light_index, radius) > 0:
                                            continue

                                        if replace_plants and current_block.base_name not in AIR:
                                            self._clear_connected_plant_half(
                                                x, y, z, dim, plat, ver, current_block
                                            )

                                        self.world.set_version_block(
                                            x, y, z, dim, (plat, ver), place, None
                                        )

                                        placed += 1

                                        if use_row_spacing:
                                            for dy in range(-2, 3):
                                                blocked.add((x, y + dy, z))
                                        else:
                                            for dx in range(-spacing_value, spacing_value + 1):
                                                for dz in range(-spacing_value, spacing_value + 1):
                                                    if dx * dx + dz * dz <= spacing_value * spacing_value:
                                                        for dy in range(-2, 3):
                                                            blocked.add((x + dx, y + dy, z + dz))

                                        chunk = self.world.get_chunk(cx, cz, dim)
                                        chunk.changed = True

            finally:
                elapsed = perf_counter() - start_time
                wx.CallAfter(self.runtime.SetLabel, f"Run time: {elapsed:.2f} seconds")
                wx.CallAfter(self.status.SetLabel, f"Done. Placed {placed} lights.")

        self.canvas.run_operation(operation)

export = dict(name="Auto Light", operation=AutoLighting)
