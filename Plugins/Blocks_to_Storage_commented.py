"""Blocks to Storage plugin for Amulet Map Editor.

Purpose:
- Scan the selected Bedrock world area.
- Count exportable non-air blocks.
- Clear the selected blocks while preserving protected blocks such as bedrock.
- Place the collected blocks into chests, double chests, barrels or shulker boxes.

Navigation:
1. Constants and block exclusion lists
2. UI setup and tooltips
3. Warning, logging and report helpers
4. Selection and direction helpers
5. Block, inventory and NBT helpers
6. Item packing
7. Chunk read/write helpers
8. Scan, clear, layout and placement logic
9. Main Amulet operation wrapper"""

import collections
import math
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
        TAG_List,
        TAG_Short,
        TAG_String,
        StringTag,
    )
except Exception:  # pragma: no cover
    NBTFile = None
    TAG_Byte = None
    TAG_Compound = None
    TAG_Int = None
    TAG_List = None
    TAG_Short = None
    TAG_String = None
    StringTag = None

if TYPE_CHECKING:
    from amulet.api.level import BaseLevel
    from amulet_map_editor.programs.edit.api.canvas import EditCanvas


class PluginClassName(wx.Panel, DefaultOperationUI):
    """
    Main UI and operation class for converting selected blocks into storage containers.
    """
    # Minecraft inventory sizing used by the packer.
    SINGLE_CONTAINER_SLOT_COUNT = 27
    DOUBLE_CHEST_SLOT_COUNT = 54
    ITEM_STACK_LIMIT = 64
    DEFAULT_STACK_HEIGHT = 8
    MAX_STACK_HEIGHT = 40
    # Progress updates are intentionally spaced out to avoid slowing large operations.
    PROGRESS_INTERVAL = 500000
    LARGE_SELECTION_WARNING_THRESHOLD = 500000

    # User-facing storage choices shown in the dropdown.
    CONTAINER_CHEST = "Chest"
    CONTAINER_BARREL = "Barrel"
    CONTAINER_SHULKER = "Shulker Box"

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

    # Air-like blocks are ignored completely because there is nothing to collect.
    AIR_BLOCKS = {
        "minecraft:air",
        "minecraft:cave_air",
        "minecraft:void_air",
    }

    # Technical or normally unobtainable blocks are skipped unless Include unusual blocks is enabled.
    DEFAULT_EXCLUDED_BLOCKS = {
        "minecraft:air",
        "minecraft:cave_air",
        "minecraft:void_air",
        "minecraft:bedrock",
        "minecraft:water",
        "minecraft:flowing_water",
        "minecraft:lava",
        "minecraft:flowing_lava",
        "minecraft:bubble_column",
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
        "minecraft:structure_block",
        "minecraft:jigsaw",
    }

    def __init__(
        self,
        parent: wx.Window,
        canvas: "EditCanvas",
        world: "BaseLevel",
        options_path: str,
    ):
        """
        Builds the plugin UI, stores world metadata and configures default options.
        """
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

        self._configure_tooltips()

        self._sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(self, label="Block To Storage Exporter")
        self._sizer.Add(title, 0, wx.ALL, 6)

        container_row = wx.BoxSizer(wx.HORIZONTAL)
        container_label = wx.StaticText(self, label="Storage container")
        self.storage_choice = wx.Choice(
            self,
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
        self._sizer.Add(container_row, 0, wx.ALL | wx.EXPAND, 6)

        self.shulker_color_row = wx.BoxSizer(wx.HORIZONTAL)
        shulker_color_label = wx.StaticText(self, label="Shulker color")
        self.shulker_color_choice = wx.Choice(self, choices=self.SHULKER_COLORS)
        self.shulker_color_choice.SetSelection(0)

        self.shulker_color_row.Add(shulker_color_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.shulker_color_row.Add(self.shulker_color_choice, 1)
        self._sizer.Add(self.shulker_color_row, 0, wx.ALL | wx.EXPAND, 6)

        stack_row = wx.BoxSizer(wx.HORIZONTAL)
        stack_label = wx.StaticText(self, label="Vertical stack height")
        self.stack_height = wx.SpinCtrl(
            self,
            min=1,
            max=self.MAX_STACK_HEIGHT,
            initial=self.DEFAULT_STACK_HEIGHT,
            size=(80, -1),
        )
        stack_row.Add(stack_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        stack_row.Add(self.stack_height, 0)
        self._sizer.Add(stack_row, 0, wx.ALL, 6)

        self.include_unusual = wx.CheckBox(self, label="Include unusual blocks")
        self.include_unusual.SetValue(False)
        self._sizer.Add(self.include_unusual, 0, wx.ALL, 6)

        self.preserve_bedrock = wx.CheckBox(self, label="Preserve bedrock")
        self.preserve_bedrock.SetValue(True)
        self._sizer.Add(self.preserve_bedrock, 0, wx.ALL, 6)

        self.fast_direct_scan = wx.CheckBox(self, label="Fast direct chunk scan")
        self.fast_direct_scan.SetValue(True)
        self._sizer.Add(self.fast_direct_scan, 0, wx.ALL, 6)

        self.fast_direct_clear = wx.CheckBox(self, label="Fast direct chunk clear")
        self.fast_direct_clear.SetValue(True)
        self._sizer.Add(self.fast_direct_clear, 0, wx.ALL, 6)

        self.show_large_selection_warning = wx.CheckBox(self, label="Show large selection warning")
        self.show_large_selection_warning.SetValue(True)
        self._sizer.Add(self.show_large_selection_warning, 0, wx.ALL, 6)

        self.separate_types = wx.CheckBox(self, label="One block type per storage group")
        self.separate_types.SetValue(False)
        self._sizer.Add(self.separate_types, 0, wx.ALL, 6)

        self.alphabetical_order = wx.CheckBox(self, label="ABC item order")
        self.alphabetical_order.SetValue(True)
        self._sizer.Add(self.alphabetical_order, 0, wx.ALL, 6)

        self.use_double_chests = wx.CheckBox(self, label="Use double chests")
        self.use_double_chests.SetValue(False)
        self._sizer.Add(self.use_double_chests, 0, wx.ALL, 6)

        self.test = wx.Button(self, label="Delete Blocks to Storage")
        self.test.Bind(wx.EVT_BUTTON, self._run_export)
        self._sizer.Add(self.test, 0, wx.ALL | wx.EXPAND, 6)

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
        self.SetMinSize((380, 580))

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
            "Includes normally skipped blocks such as water, lava, bubble columns, barrier, light, portal blocks, command blocks, and other technical blocks.",
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
            self.separate_types,
            "Keeps each block type in its own storage group. Example: stone goes into its own containers, dirt goes into its own containers, and so on.",
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
            self.test,
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
        """
        Connects Amulet selection events when the operation becomes active.
        """
        super().bind_events()
        self._selection.bind_events()
        self._selection.enable()

    def enable(self):
        """
        Enables block selection behavior for this operation.
        """
        self._selection = BlockSelectionBehaviour(self.canvas)
        self._selection.enable()

    # ---------------------------------------------------------------------
    # UI helpers
    # ---------------------------------------------------------------------
    def _configure_tooltips(self) -> None:
        """
        Sets tooltip timing so option descriptions remain readable.
        """
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
        """
        Applies a tooltip using the safest API available in the current wxPython build.
        """
        try:
            window.SetToolTip(wx.ToolTip(text))
        except Exception:
            try:
                window.SetToolTip(text)
            except Exception:
                pass

    def _get_selected_container(self) -> str:
        """
        Returns the selected storage container type, defaulting to chest if the UI has no value.
        """
        value = self.storage_choice.GetStringSelection()
        if not value:
            return self.CONTAINER_CHEST
        return value

    def _on_storage_choice_changed(self, _):
        """
        Refreshes option visibility when the storage container type changes.
        """
        self._update_option_visibility()

    def _update_option_visibility(self) -> None:
        """
        Shows only options that apply to the selected storage container.
        """
        container = self._get_selected_container()

        is_chest = container == self.CONTAINER_CHEST
        is_shulker = container == self.CONTAINER_SHULKER

        self.use_double_chests.Show(is_chest)

        for child in self.shulker_color_row.GetChildren():
            window = child.GetWindow()
            if window is not None:
                window.Show(is_shulker)

        if not is_chest:
            self.use_double_chests.SetValue(False)

        try:
            self.Layout()
            self.GetParent().Layout()
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # Warning helpers
    # ---------------------------------------------------------------------
    def _estimate_selection_volume(self) -> Optional[int]:
        """
        Estimates selected block count before the heavy operation starts.
        """
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
        """
        Shows a confirmation popup for large selections when that warning is enabled.
        """
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

    # ---------------------------------------------------------------------
    # Logging / report helpers
    # ---------------------------------------------------------------------
    def _format_seconds(self, seconds: float) -> str:
        """
        Formats elapsed time into seconds, minutes or hours for readable reports.
        """
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
        """
        Formats an operation speed value for the report.
        """
        seconds = float(seconds)
        if seconds <= 0:
            return f"{amount:,} {label}/second"

        rate = amount / seconds
        return f"{rate:,.2f} {label}/second"

    def _clear_log(self) -> None:
        """
        Clears the visible report log.
        """
        try:
            wx.CallAfter(self.text.SetValue, "")
        except Exception:
            try:
                self.text.SetValue("")
            except Exception:
                pass

    def _append_log_text(self, message: str) -> None:
        """
        Appends one line to the visible report log.
        """
        try:
            self.text.AppendText(message + "\n")
        except Exception:
            pass

    def _log(self, message: str) -> None:
        """
        Writes a message to the console, visible log and saved report buffer.
        """
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
        """
        Clears the saved report buffer before a new run.
        """
        self._report_lines = []
        self._last_report_text = ""
        try:
            self.save_report_button.Enable(False)
        except Exception:
            pass

    def _finalize_report(self) -> None:
        """
        Stores the final report text and enables the save-report button.
        """
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
        """
        Lets the user choose where to save the latest report text file.
        """
        if not self._last_report_text:
            wx.MessageBox(
                "No report is available yet. Run the exporter first.",
                "No Report",
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        default_name = "Block to storage export report; " + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"

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

    # ---------------------------------------------------------------------
    # Selection helpers
    # ---------------------------------------------------------------------
    def _iter_selected_positions(self):
        """
        Yields every selected block coordinate from Amulet selection boxes.
        """
        selection = list(self.canvas.selection.selection_group.selection_boxes)

        for box in selection:
            for pos in box:
                yield int(pos[0]), int(pos[1]), int(pos[2])

    # ---------------------------------------------------------------------
    # Direction helpers
    # ---------------------------------------------------------------------
    def _get_inward_facing(
        self,
        x: int,
        z: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> str:
        """
        Chooses a single-container facing direction that points toward the inside of the selection.
        """
        min_x, min_y, min_z, max_x, max_y, max_z = bounds

        center_x = (min_x + max_x) / 2.0
        center_z = (min_z + max_z) / 2.0

        dx = center_x - x
        dz = center_z - z

        if abs(dx) >= abs(dz):
            if dx >= 0:
                return "east"
            return "west"

        if dz >= 0:
            return "south"
        return "north"

    def _get_double_chest_facing(
        self,
        pair_axis: str,
        x1: int,
        z1: int,
        x2: int,
        z2: int,
        bounds: Tuple[int, int, int, int, int, int],
    ) -> str:
        """
        Chooses a double-chest facing direction based on the pair position and selection center.
        """
        min_x, min_y, min_z, max_x, max_y, max_z = bounds

        center_x = (min_x + max_x) / 2.0
        center_z = (min_z + max_z) / 2.0

        pair_center_x = (x1 + x2) / 2.0
        pair_center_z = (z1 + z2) / 2.0

        if pair_axis == "x":
            if center_z >= pair_center_z:
                return "south"
            return "north"

        if center_x >= pair_center_x:
            return "east"
        return "west"

    def _get_double_chest_connections(
        self,
        pair_axis: str,
        facing: str,
    ) -> Tuple[str, str]:
        """
        Returns left/right connection states so paired chests connect correctly.
        """
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

    # ---------------------------------------------------------------------
    # Block / NBT helpers
    # ---------------------------------------------------------------------
    def _normalize_name(self, value) -> str:
        """
        Normalizes block names into a minecraft-style namespaced form.
        """
        text = str(value) if value is not None else ""
        if not text:
            return ""
        if text.startswith("universal_minecraft:"):
            text = text.replace("universal_minecraft:", "minecraft:", 1)
        if ":" in text:
            return text
        return f"minecraft:{text}"

    def _get_namespaced_block_name(self, block) -> Optional[str]:
        """
        Extracts a stable namespaced block name from an Amulet block object.
        """
        namespace = getattr(block, "namespace", "minecraft") or "minecraft"
        base_name = getattr(block, "base_name", None) or getattr(block, "namespaced_name", None)

        if base_name is None:
            return None

        namespace = self._normalize_name(namespace)
        if namespace.startswith("minecraft:"):
            namespace = "minecraft"

        return self._normalize_name(f"{namespace}:{str(base_name)}")

    def _classify_block(self, block) -> Tuple[Optional[str], Optional[str]]:
        """
        Decides whether a block should be exported, skipped or treated as air.
        """
        key = self._get_namespaced_block_name(block)

        if key is None:
            return None, "unknown_block"

        if key in self.AIR_BLOCKS or key.endswith(":air"):
            return None, None

        if key == "minecraft:bedrock":
            return None, key

        if not self.include_unusual.GetValue() and key in self.DEFAULT_EXCLUDED_BLOCKS:
            return None, key

        return key, None

    def _universal_string(self, value: str):
        """
        Creates the correct string tag type for universal block state properties.
        """
        if StringTag is not None:
            return StringTag(value)
        if TAG_String is not None:
            return TAG_String(value)
        return value

    def _make_universal_air(self) -> Block:
        """
        Builds the universal air block used during clearing.
        """
        return Block("universal_minecraft", "air")

    def _make_universal_chest(self, facing: str = "north", connection: str = "none") -> Block:
        """
        Builds a universal chest block with facing and connection properties.
        """
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
        """
        Builds a universal barrel block with facing and closed-state properties.
        """
        return Block(
            "universal_minecraft",
            "barrel",
            {
                "facing": self._universal_string(facing),
                "open": self._universal_string("false"),
            },
        )

    def _make_universal_shulker_box(self, facing: str = "east") -> Block:
        """
        Builds a universal shulker box block using the selected color and facing.
        """
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
        """
        Builds the selected storage block type for single-container placement.
        """
        container = self._get_selected_container()

        if container == self.CONTAINER_BARREL:
            return self._make_universal_barrel(facing=facing)

        if container == self.CONTAINER_SHULKER:
            return self._make_universal_shulker_box(facing=facing)

        return self._make_universal_chest(facing=facing, connection="none")

    def _get_storage_entity_name(self) -> str:
        """
        Returns the block entity name matching the selected storage container.
        """
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
    ):
        """
        Builds the inventory NBT payload for one storage container.
        """
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

        for slot, (item_name, count) in enumerate(stacks):
            item = TAG_Compound()
            item["Slot"] = TAG_Byte(int(slot))
            item["Name"] = TAG_String(item_name)
            item["Count"] = TAG_Byte(int(count))
            item["Damage"] = TAG_Short(0)
            items.append(item)

        return NBTFile(the_nbt)

    # ---------------------------------------------------------------------
    # Item packing
    # ---------------------------------------------------------------------
    def _get_ordered_item_names(self, counts: Dict[str, int]) -> List[str]:
        """
        Returns block item names in ABC order or first-seen scan order.
        """
        if self.alphabetical_order.GetValue():
            return sorted(counts.keys())

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
        """
        Returns 27 slots for single containers or 54 slots for double chests.
        """
        if self._get_selected_container() == self.CONTAINER_CHEST and self.use_double_chests.GetValue():
            return self.DOUBLE_CHEST_SLOT_COUNT
        return self.SINGLE_CONTAINER_SLOT_COUNT

    def _split_into_stacks(self, item_name: str, total_count: int) -> List[Tuple[str, int]]:
        """
        Splits a counted block type into Minecraft-sized 64-item stacks.
        """
        stacks: List[Tuple[str, int]] = []
        remaining = int(total_count)

        while remaining > 0:
            take = self.ITEM_STACK_LIMIT if remaining >= self.ITEM_STACK_LIMIT else remaining
            stacks.append((item_name, take))
            remaining -= take

        return stacks

    def _pack_stacks_into_containers(
        self,
        stacks: Sequence[Tuple[str, int]],
        slot_count: int,
    ) -> List[List[Tuple[str, int]]]:
        """
        Packs item stacks into storage-container slot lists.
        """
        containers: List[List[Tuple[str, int]]] = []
        current: List[Tuple[str, int]] = []

        for stack in stacks:
            current.append(stack)
            if len(current) >= slot_count:
                containers.append(current)
                current = []

        if current:
            containers.append(current)

        return containers

    def _build_container_payloads(self, counts: Dict[str, int]) -> List[List[Tuple[str, int]]]:
        """
        Builds all storage inventories from the scanned block counts.
        """
        payloads: List[List[Tuple[str, int]]] = []
        slot_count = self._get_container_slot_count()
        item_names = self._get_ordered_item_names(counts)

        if self.separate_types.GetValue():
            for item_name in item_names:
                payloads.extend(
                    self._pack_stacks_into_containers(
                        self._split_into_stacks(item_name, counts[item_name]),
                        slot_count,
                    )
                )
        else:
            all_stacks: List[Tuple[str, int]] = []
            for item_name in item_names:
                all_stacks.extend(self._split_into_stacks(item_name, counts[item_name]))
            payloads = self._pack_stacks_into_containers(all_stacks, slot_count)

        return payloads

    # ---------------------------------------------------------------------
    # Chunk helpers
    # ---------------------------------------------------------------------
    def _get_chunk(self, cx: int, cz: int):
        """
        Loads a chunk using several known Amulet API signatures for compatibility.
        """
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
        """
        Converts world x/z coordinates to chunk coordinates.
        """
        return x // 16, z // 16

    def _local_coords(self, x: int, z: int) -> Tuple[int, int]:
        """
        Converts world x/z coordinates to local chunk coordinates.
        """
        return x % 16, z % 16

    def _try_get_palette_block(self, palette, block_id):
        """
        Reads a block from a chunk palette using compatible palette APIs.
        """
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
        """
        Reads a block directly from chunk block arrays for faster scanning.
        """
        dx, dz = self._local_coords(x, z)
        block_id = chunk.blocks[dx, y, dz]
        return self._try_get_palette_block(chunk.block_palette, block_id)

    def _get_block_for_scan(self, x: int, y: int, z: int, chunk_cache: Dict[Tuple[int, int], object]):
        """
        Returns the block at a position using fast direct scan or safe Amulet fallback.
        """
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

        block, ent = self.world.get_version_block(
            x,
            y,
            z,
            self.canvas.dimension,
            (self._world_platform, self._world_version),
        )
        return block

    def _write_universal_block_to_chunk(
        self,
        chunk,
        x: int,
        y: int,
        z: int,
        universal_block: Block,
        universal_block_entity: Optional[BlockEntity] = None,
    ) -> None:
        """
        Writes a universal block and optional block entity into chunk data.
        """
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
        """
        Writes cached air directly into chunk data during fast clear.
        """
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

    # ---------------------------------------------------------------------
    # Scan / layout / edit
    # ---------------------------------------------------------------------
    def _scan_selection(self):
        """
        Scans the selection, counts exportable blocks and records protected positions.
        """
        counts: Dict[str, int] = collections.defaultdict(int)
        skipped_counts: Dict[str, int] = collections.defaultdict(int)
        protected_positions: Set[Tuple[int, int, int]] = set()

        self._scan_order = []
        self._fast_scan_failed = False
        self._fast_scan_fail_reason = ""

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
            export_key, skipped_key = self._classify_block(block)

            if skipped_key == "minecraft:bedrock" and self.preserve_bedrock.GetValue():
                protected_positions.add((x, y, z))

            if skipped_key is not None:
                skipped_counts[skipped_key] += 1
                continue

            if export_key is None:
                continue

            if counts[export_key] == 0:
                self._scan_order.append(export_key)

            counts[export_key] += 1

        if min_x is None:
            return counts, skipped_counts, protected_positions, None, scanned_positions

        return counts, skipped_counts, protected_positions, (min_x, min_y, min_z, max_x, max_y, max_z), scanned_positions

    def _is_protected_position(
        self,
        x: int,
        y: int,
        z: int,
        protected_positions: Set[Tuple[int, int, int]],
    ) -> bool:
        """
        Checks whether a coordinate should be preserved during clear and placement.
        """
        return (x, y, z) in protected_positions

    def _plan_single_storage_positions(
        self,
        container_count: int,
        bounds: Tuple[int, int, int, int, int, int],
        protected_positions: Set[Tuple[int, int, int]],
    ) -> List[Tuple[int, int, int]]:
        """
        Plans single-container positions inside the selection while avoiding protected blocks.
        """
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
            for primary_offset in range(primary_len):
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

    def _plan_double_chest_positions(
        self,
        container_count: int,
        bounds: Tuple[int, int, int, int, int, int],
        protected_positions: Set[Tuple[int, int, int]],
    ) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int], str]]:
        """
        Plans paired double-chest positions while avoiding protected blocks.
        """
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

        if x_len >= 2:
            pair_axis = "x"
            primary_len = x_len // 2
            secondary_len = z_len
        elif z_len >= 2:
            pair_axis = "z"
            primary_len = z_len // 2
            secondary_len = x_len
        else:
            raise RuntimeError("Not enough horizontal room for double chests.")

        for line_index in range(secondary_len):
            for primary_offset in range(primary_len):
                for vertical_offset in range(stack_height):
                    y = min_y + vertical_offset

                    if pair_axis == "x":
                        x1 = min_x + (primary_offset * 2)
                        z1 = min_z + line_index
                        x2 = x1 + 1
                        z2 = z1
                    else:
                        x1 = min_x + line_index
                        z1 = min_z + (primary_offset * 2)
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

    def _clear_selection_safe(
        self,
        protected_positions: Set[Tuple[int, int, int]],
    ) -> Tuple[int, int]:
        """
        Clears selected blocks using the safer generic write helper.
        """
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
        """
        Clears selected blocks using cached direct chunk writes.
        """
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
        """
        Chooses fast or safe clearing and reports the result.
        """
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

    # ---------------------------------------------------------------------
    # Storage placement
    # ---------------------------------------------------------------------
    def _place_single_storage_in_chunks(
        self,
        positions: Sequence[Tuple[int, int, int]],
        inventories: Sequence[Sequence[Tuple[str, int]]],
        bounds: Tuple[int, int, int, int, int, int],
    ) -> None:
        """
        Places single storage containers and their inventories into chunks.
        """
        entity_name = self._get_storage_entity_name()
        chunk_cache = {}

        for (x, y, z), stacks in zip(positions, inventories):
            facing = self._get_inward_facing(x, z, bounds)
            universal_block = self._make_universal_storage_block(facing=facing)

            nbt = self._make_inventory_nbt(stacks)
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
        """
        Places connected double chests and splits inventory across both halves.
        """
        chunk_cache = {}

        for ((x1, y1, z1), (x2, y2, z2), pair_axis), stacks in zip(chest_pairs, chest_inventories):
            facing = self._get_double_chest_facing(pair_axis, x1, z1, x2, z2, bounds)
            connection_1, connection_2 = self._get_double_chest_connections(pair_axis, facing)

            first_half = list(stacks[:self.SINGLE_CONTAINER_SLOT_COUNT])
            second_half = list(stacks[self.SINGLE_CONTAINER_SLOT_COUNT:])

            nbt_1 = self._make_inventory_nbt(first_half, pair_position=(x2, z2))
            nbt_2 = self._make_inventory_nbt(second_half, pair_position=(x1, z1))

            entity_1 = BlockEntity("universal_minecraft", "chest", x1, y1, z1, nbt_1)
            entity_2 = BlockEntity("universal_minecraft", "chest", x2, y2, z2, nbt_2)

            chest_1 = self._make_universal_chest(facing=facing, connection=connection_1)
            chest_2 = self._make_universal_chest(facing=facing, connection=connection_2)

            for x, y, z, chest_block, chest_entity in (
                (x1, y1, z1, chest_1, entity_1),
                (x2, y2, z2, chest_2, entity_2),
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

    # ---------------------------------------------------------------------
    # Button / Amulet operation wrapper
    # ---------------------------------------------------------------------
    def _run_export(self, _):
        """
        Validates warnings and starts the Amulet operation wrapper.
        """
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
                title="Block To Storage Exporter",
                msg="Moving selected blocks into storage...",
                throw_exceptions=False,
            )
        except TypeError:
            try:
                self.canvas.run_operation(
                    self._run_export_operation,
                    "Block To Storage Exporter",
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
        """
        Main workflow: scan, plan, clear, place storage and write the report.
        """
        total_start = time.perf_counter()

        try:
            self._log("Block To Storage Export Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")
            self._log("Starting block scan...")
            self._log(f"World wrapper: {self._world_platform} / {self._world_version}")
            self._log(f"Fast direct chunk scan: {self.fast_direct_scan.GetValue()}")
            self._log(f"Fast direct chunk clear: {self.fast_direct_clear.GetValue()}")
            self._log(f"Large selection warning enabled: {self.show_large_selection_warning.GetValue()}")

            container = self._get_selected_container()
            use_double_chests = container == self.CONTAINER_CHEST and self.use_double_chests.GetValue()

            self._log(f"Storage container: {container}")

            if container == self.CONTAINER_SHULKER:
                self._log(f"Shulker color: {self.shulker_color_choice.GetStringSelection()}")
                self._log("Shulker facing: sideways/inward")

            scan_start = time.perf_counter()
            counts, skipped_counts, protected_positions, bounds, scanned_positions = self._scan_selection()
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

            if not counts:
                self._log("No exportable blocks found.")

                if skipped_counts:
                    self._log("")
                    self._log("Skipped blocks:")
                    for item_name in sorted(skipped_counts.keys()):
                        self._log(f"{item_name} -> {skipped_counts[item_name]}")

                self._log("")
                self._log(f"Total operation time: {self._format_seconds(time.perf_counter() - total_start)}")
                return

            planning_start = time.perf_counter()

            total_blocks = sum(counts.values())
            total_skipped = sum(skipped_counts.values())

            inventories = self._build_container_payloads(counts)
            container_count = len(inventories)

            if use_double_chests:
                storage_positions = self._plan_double_chest_positions(container_count, bounds, protected_positions)
                planned_physical_blocks = len(storage_positions) * 2
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

            self._log(f"Vertical stack height: {self.stack_height.GetValue()}")
            self._log(f"ABC item order: {self.alphabetical_order.GetValue()}")
            self._log(f"One block type per storage group: {self.separate_types.GetValue()}")
            self._log(f"Include unusual blocks: {self.include_unusual.GetValue()}")
            self._log(f"Preserve bedrock: {self.preserve_bedrock.GetValue()}")
            self._log(f"Protected bedrock positions: {len(protected_positions):,}")
            self._log(f"Planning time: {self._format_seconds(planning_time)}")

            self._log("")
            self._log("Exported blocks:")
            for item_name in self._get_ordered_item_names(counts):
                self._log(f"{item_name} -> {counts[item_name]:,}")

            self._log("")
            if skipped_counts:
                self._log("Skipped blocks:")
                for item_name in sorted(skipped_counts.keys()):
                    self._log(f"{item_name} -> {skipped_counts[item_name]:,}")
            else:
                self._log("Skipped blocks: none")

            clear_start = time.perf_counter()
            preserved_bedrock, cleared_blocks, fast_clear_result = self._clear_selection_in_chunks(protected_positions)
            clear_time = time.perf_counter() - clear_start

            place_start = time.perf_counter()
            if use_double_chests:
                self._place_double_chests_in_chunks(storage_positions, inventories, bounds)
            else:
                self._place_single_storage_in_chunks(storage_positions, inventories, bounds)
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


export = dict(name="Block To Storage", operation=PluginClassName)