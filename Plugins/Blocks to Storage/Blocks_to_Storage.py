import ast
import collections
import ctypes
import inspect
import json
import os
import re
import stat
import tempfile
import time
from time import perf_counter
import weakref
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, Set

import wx

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
from amulet_map_editor.programs.edit.api.behaviour import BlockSelectionBehaviour
from amulet_map_editor.programs.edit.api.operations import DefaultOperationUI

from amulet.api.block import Block
from amulet.api.block_entity import BlockEntity

try:
    from amulet.api.item import Item
except Exception:
    Item = None

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

CUSTOM_UI_NAME_PREFIX = "AmuletUtilityCustomUI"
CUSTOM_UI_THEME_OWNED_ATTR = "_amulet_utility_theme_owned"

FLOATING_DEFAULT_SIZE = (560, 780)
FLOATING_MIN_SIZE = (440, 580)
MANAGE_DIALOG_DEFAULT_SIZE = (560, 460)
MANAGE_DIALOG_MIN_SIZE = (554, 410)

BLOCKS_TO_STORAGE_THEME = {
    "passive_window": wx.Colour(20, 15, 25),
    "passive_surface": wx.Colour(31, 23, 38),
    "passive_surface_alt": wx.Colour(27, 20, 33),
    "passive_border": wx.Colour(72, 52, 86),
    "window": wx.Colour(16, 13, 20),
    "surface": wx.Colour(26, 21, 31),
    "surface_alt": wx.Colour(23, 18, 28),
    "surface_hover": wx.Colour(42, 31, 51),
    "surface_pressed": wx.Colour(69, 36, 103),
    "border": wx.Colour(78, 60, 91),
    "border_soft": wx.Colour(57, 44, 67),
    "text": wx.Colour(239, 235, 244),
    "muted": wx.Colour(174, 161, 185),
    "accent": wx.Colour(128, 61, 196),
    "accent_hover": wx.Colour(151, 79, 224),
    "accent_pressed": wx.Colour(99, 43, 157),
    "accent_soft": wx.Colour(72, 39, 105),
    "disabled": wx.Colour(88, 78, 96),
    "console_bg": wx.Colour(7, 5, 9),
    "console_text": wx.Colour(91, 224, 125),
    "warning": wx.Colour(220, 181, 79),
}

TOOLTIP_BORDER_COLOUR = BLOCKS_TO_STORAGE_THEME["accent_hover"]
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

UI_FINAL_CHECKBOX_BOTTOM_EXTRA = 4

UI_COLLAPSIBLE_CONTENT_INSET = 2
UI_COLLAPSIBLE_CONTENT_RADIUS = 10

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

STORAGE_SELECTOR_ICON_COLUMNS = 3
SHULKER_SELECTOR_ICON_COLUMNS = 4
SHULKER_SELECTOR_VISIBLE_ROWS = 4
STORAGE_SELECTOR_TILE_HEIGHT = 104
STORAGE_SELECTOR_ICON_SIZE = 72
STORAGE_SELECTOR_ICON_OFFSET = 7
STORAGE_SELECTOR_ICON_BOTTOM_PADDING = 4
STORAGE_SELECTOR_MIN_WIDTH = 520
STORAGE_SELECTOR_GRID_GAP = 5
STORAGE_SELECTOR_POPUP_RADIUS = 12

STORAGE_ICON_ITEM_IDS = {
    "Chest": "chest",
    "Barrel": "barrel",
    "Shulker Box": "shulker_box",
    "default": "shulker_box",
    "white": "white_shulker_box",
    "orange": "orange_shulker_box",
    "magenta": "magenta_shulker_box",
    "light_blue": "light_blue_shulker_box",
    "yellow": "yellow_shulker_box",
    "lime": "lime_shulker_box",
    "pink": "pink_shulker_box",
    "gray": "gray_shulker_box",
    "light_gray": "light_gray_shulker_box",
    "cyan": "cyan_shulker_box",
    "purple": "purple_shulker_box",
    "blue": "blue_shulker_box",
    "brown": "brown_shulker_box",
    "green": "green_shulker_box",
    "red": "red_shulker_box",
    "black": "black_shulker_box",
}

STORAGE_ICON_FALLBACK_SPECS = {

    "Chest": ("chest_entity", "minecraft:entity/chest/normal"),
    "Barrel": ("barrel_block", "minecraft:block/barrel_side"),
    "Shulker Box": ("shulker_entity", "minecraft:entity/shulker/shulker"),
    "default": ("shulker_entity", "minecraft:entity/shulker/shulker"),
    "white": ("shulker_entity", "minecraft:entity/shulker/shulker_white"),
    "orange": ("shulker_entity", "minecraft:entity/shulker/shulker_orange"),
    "magenta": ("shulker_entity", "minecraft:entity/shulker/shulker_magenta"),
    "light_blue": ("shulker_entity", "minecraft:entity/shulker/shulker_light_blue"),
    "yellow": ("shulker_entity", "minecraft:entity/shulker/shulker_yellow"),
    "lime": ("shulker_entity", "minecraft:entity/shulker/shulker_lime"),
    "pink": ("shulker_entity", "minecraft:entity/shulker/shulker_pink"),
    "gray": ("shulker_entity", "minecraft:entity/shulker/shulker_gray"),
    "light_gray": ("shulker_entity", "minecraft:entity/shulker/shulker_light_gray"),
    "cyan": ("shulker_entity", "minecraft:entity/shulker/shulker_cyan"),
    "purple": ("shulker_entity", "minecraft:entity/shulker/shulker_purple"),
    "blue": ("shulker_entity", "minecraft:entity/shulker/shulker_blue"),
    "brown": ("shulker_entity", "minecraft:entity/shulker/shulker_brown"),
    "green": ("shulker_entity", "minecraft:entity/shulker/shulker_green"),
    "red": ("shulker_entity", "minecraft:entity/shulker/shulker_red"),
    "black": ("shulker_entity", "minecraft:entity/shulker/shulker_black"),
}

SHULKER_COLOR_RGB = {
    "default": (116, 81, 132),
    "white": (222, 222, 214),
    "orange": (216, 127, 51),
    "magenta": (178, 76, 216),
    "light_blue": (102, 153, 216),
    "yellow": (229, 229, 51),
    "lime": (127, 204, 25),
    "pink": (242, 127, 165),
    "gray": (76, 76, 76),
    "light_gray": (153, 153, 153),
    "cyan": (76, 127, 153),
    "purple": (127, 63, 178),
    "blue": (51, 76, 178),
    "brown": (102, 76, 51),
    "green": (102, 127, 51),
    "red": (153, 51, 51),
    "black": (37, 37, 37),
}

SHULKER_COLOR_LABELS = {
    "default": "Default",
    "white": "White",
    "orange": "Orange",
    "magenta": "Magenta",
    "light_blue": "Light Blue",
    "yellow": "Yellow",
    "lime": "Lime",
    "pink": "Pink",
    "gray": "Gray",
    "light_gray": "Light Gray",
    "cyan": "Cyan",
    "purple": "Purple",
    "blue": "Blue",
    "brown": "Brown",
    "green": "Green",
    "red": "Red",
    "black": "Black",
}
SHULKER_COLOR_VALUES_BY_LABEL = {
    label: value
    for value, label in SHULKER_COLOR_LABELS.items()
}
SHULKER_COLOR_CHOICES = tuple(SHULKER_COLOR_LABELS.values())

def _shulker_color_value(value):
    text = str(value or "").strip()
    if text in SHULKER_COLOR_RGB:
        return text

    mapped = SHULKER_COLOR_VALUES_BY_LABEL.get(text)
    if mapped is not None:
        return mapped

    normalized = text.lower().replace(" ", "_")
    if normalized in SHULKER_COLOR_RGB:
        return normalized
    return "default"

def _shulker_color_label(value):
    return SHULKER_COLOR_LABELS[_shulker_color_value(value)]

def _storage_icon_choice_key(choice):
    text = str(choice)
    return SHULKER_COLOR_VALUES_BY_LABEL.get(text, text)

def _mark_custom_ui_owned(window, semantic_name=None):
    try:
        setattr(window, CUSTOM_UI_THEME_OWNED_ATTR, True)
    except Exception:
        pass
    try:
        window.SetName(semantic_name or f"{CUSTOM_UI_NAME_PREFIX}:Control")
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
        result = set_window_theme(ctypes.c_void_p(handle), "DarkMode_Explorer", None)
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
    return BLOCKS_TO_STORAGE_THEME["window"]

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
            BLOCKS_TO_STORAGE_THEME["muted"] if muted else BLOCKS_TO_STORAGE_THEME["text"]
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

class AmuletStorageIconCache:

    ATLAS_JSON_LIMIT = 16 * 1024 * 1024
    MODEL_JSON_LIMIT = 2 * 1024 * 1024
    BASE_ICON_SIZE = 64

    def __init__(self):
        self._loaded = False
        self._resource_roots = []
        self._base_icons = {}

        self._icon_sources = {}
        self._bitmap_cache = {}
        self._compact_bitmap_cache = {}

    @staticmethod
    def _local_app_data_root():
        value = os.environ.get("LOCALAPPDATA", "").strip()
        if value:
            return Path(value)
        return Path.home() / "AppData" / "Local"

    @classmethod
    def _cache_root(cls):
        return (
            cls._local_app_data_root()
            / "AmuletTeam"
            / "AmuletMapEditor"
            / "Cache"
            / "resource_packs"
        )

    @staticmethod
    def _normalize_path(value):
        return str(value).replace("\\", "/").lower()

    @staticmethod
    def _texture_suffix(texture_reference):
        reference = str(texture_reference or "").strip()
        if not reference:
            return ""
        if ":" in reference:
            _namespace, reference = reference.split(":", 1)
        reference = reference.strip("/").replace("\\", "/")
        return f"/textures/{reference}.png".lower()

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
        java_root = self._cache_root() / "java"
        roots = []
        try:
            children = [child for child in java_root.iterdir() if child.is_dir()]
        except Exception:
            children = []

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
        try:
            return float(Path(path).stat().st_mtime)
        except Exception:
            return 0.0

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

    def _resolve_model_spec(self, item_id):
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
        elif any(
            value.endswith((
                "block/cube_all",
                "block/cube_bottom_top",
                "block/cube_column",
                "block/cube_column_horizontal",
            ))
            for value in model_values
        ):
            render_kind = "cube_all"
            texture_value = (
                textures.get("all")
                or textures.get("side")
                or textures.get("end")
                or textures.get("top")
            )
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
        specs = {}
        special_kinds = {"chest_entity", "barrel_block", "shulker_entity"}
        for choice, item_id in STORAGE_ICON_ITEM_IDS.items():

            special_spec = STORAGE_ICON_FALLBACK_SPECS.get(choice)
            if special_spec is not None and special_spec[0] in special_kinds:
                specs[choice] = special_spec
                continue
            spec = self._resolve_model_spec(item_id)
            if spec is None:
                spec = special_spec
            if spec is not None:
                specs[choice] = spec
        return specs

    def _select_atlas(self, specs):
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

    @classmethod
    def _render_flat_icon(cls, texture):
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
        red, green, blue, alpha = pixel
        return (
            max(0, min(255, int(round(red * factor)))),
            max(0, min(255, int(round(green * factor)))),
            max(0, min(255, int(round(blue * factor)))),
            alpha,
        )

    @classmethod
    def _render_prism_icon(
        cls,
        top_texture,
        left_texture,
        right_texture,
        *,
        top_shade=1.08,
        left_shade=0.84,
        right_shade=0.68,
        face_scale=1.0,
        side_height_scale=1.0,
    ):
        render_size = cls.BASE_ICON_SIZE * 4
        geometry_scale = render_size / 128.0

        top_texture = cls._first_animation_frame(top_texture)
        left_texture = cls._first_animation_frame(left_texture)
        right_texture = cls._first_animation_frame(right_texture)
        canvas = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas, "RGBA")
        center_x = render_size / 2.0
        top_y = 6.0 * geometry_scale
        face_width = 66.0 * face_scale * geometry_scale
        face_height = 32.0 * face_scale * geometry_scale
        side_height = 46.0 * face_scale * side_height_scale * geometry_scale

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

        def draw_face(texture, origin, basis_x, basis_y, shade):
            source_width = max(1, int(texture.width))
            source_height = max(1, int(texture.height))
            for source_y in range(source_height):
                for source_x in range(source_width):
                    pixel = texture.getpixel((source_x, source_y))
                    if pixel[3] <= 0:
                        continue
                    u0 = source_x / float(source_width)
                    v0 = source_y / float(source_height)
                    u1 = (source_x + 1) / float(source_width)
                    v1 = (source_y + 1) / float(source_height)
                    polygon = [
                        point(origin, basis_x, basis_y, u0, v0),
                        point(origin, basis_x, basis_y, u1, v0),
                        point(origin, basis_x, basis_y, u1, v1),
                        point(origin, basis_x, basis_y, u0, v1),
                    ]
                    draw.polygon(polygon, fill=cls._shade_pixel(pixel, shade))

        draw_face(left_texture, left_origin, left_x, left_y, left_shade)
        draw_face(right_texture, right_origin, right_x, right_y, right_shade)
        draw_face(top_texture, top_origin, top_x, top_y_basis, top_shade)
        return canvas.resize(
            (cls.BASE_ICON_SIZE, cls.BASE_ICON_SIZE),
            cls._smooth_filter(),
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
        return cls._render_prism_icon(
            texture,
            texture,
            texture,
            top_shade=top_shade,
            left_shade=left_shade,
            right_shade=right_shade,
            face_scale=face_scale,
        )

    @classmethod
    def _render_chest_icon(cls, texture):
        texture = texture.convert("RGBA")
        if texture.width < 56 or texture.height < 43:
            return cls._render_flat_icon(texture)

        lid_top = texture.crop((28, 0, 42, 14))
        lid_west = texture.crop((0, 14, 14, 19))
        lid_front = texture.crop((14, 14, 28, 19))

        base_west = texture.crop((0, 33, 14, 43))
        base_front = texture.crop((14, 33, 28, 43))

        latch_front = texture.crop((1, 1, 3, 5))

        front = Image.new("RGBA", (14, 15), (0, 0, 0, 0))
        front.alpha_composite(lid_front, (0, 0))
        front.alpha_composite(base_front, (0, 5))
        front.alpha_composite(latch_front, (6, 3))

        west = Image.new("RGBA", (14, 15), (0, 0, 0, 0))
        west.alpha_composite(lid_west, (0, 0))
        west.alpha_composite(base_west, (0, 5))

        return cls._render_prism_icon(
            lid_top,
            west,
            front,
            top_shade=1.04,
            left_shade=0.86,
            right_shade=0.74,
            face_scale=0.92,
            side_height_scale=15.0 / 14.0,
        )

    @classmethod
    def _render_barrel_icon(cls, side_texture, top_texture):
        return cls._render_prism_icon(
            cls._first_animation_frame(top_texture),
            cls._first_animation_frame(side_texture),
            cls._first_animation_frame(side_texture),
            top_shade=1.04,
            left_shade=0.86,
            right_shade=0.72,
            face_scale=0.94,
        )

    @classmethod
    def _render_shulker_icon(cls, texture):
        texture = texture.convert("RGBA")
        if texture.width < 64 or texture.height < 52:
            return cls._render_flat_icon(texture)

        lid_top = texture.crop((16, 0, 32, 16))
        lid_left = texture.crop((0, 16, 16, 28))
        lid_front = texture.crop((16, 16, 32, 28))
        base_left = texture.crop((0, 44, 16, 52))
        base_front = texture.crop((16, 44, 32, 52))

        left = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        left.alpha_composite(base_left, (0, 8))
        left.alpha_composite(lid_left, (0, 0))

        front = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        front.alpha_composite(base_front, (0, 8))
        front.alpha_composite(lid_front, (0, 0))

        return cls._render_prism_icon(
            lid_top,
            left,
            front,
            top_shade=1.04,
            left_shade=0.88,
            right_shade=0.76,
            face_scale=0.94,
        )

    @staticmethod
    def _content_bbox(image):
        try:
            return image.convert("RGBA").getchannel("A").getbbox()
        except Exception:
            return None

    @classmethod
    def _fit_icon_to_size(cls, image, size, padding=0, smooth=False):
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
        specs = self._model_specs()

        unresolved = {}
        three_dimensional_kinds = {
            "cube_all",
            "chest_entity",
            "barrel_block",
            "shulker_entity",
        }
        for choice, (render_kind, texture_reference) in specs.items():
            texture = self._direct_texture(texture_reference)
            top_texture = None
            if render_kind == "barrel_block":
                top_texture = self._direct_texture("minecraft:block/barrel_top")
            if texture is None or (render_kind == "barrel_block" and top_texture is None):
                unresolved[choice] = (render_kind, texture_reference)
                continue
            try:
                if render_kind == "chest_entity":
                    icon = self._render_chest_icon(texture)
                elif render_kind == "barrel_block":
                    icon = self._render_barrel_icon(texture, top_texture)
                elif render_kind == "shulker_entity":
                    icon = self._render_shulker_icon(texture)
                elif render_kind == "cube_all":
                    icon = self._render_cube_icon(texture)
                else:
                    icon = self._render_flat_icon(texture)
                self._base_icons[choice] = icon
                self._icon_sources[choice] = (
                    "cube" if render_kind in three_dimensional_kinds else "flat",
                    icon.copy()
                    if render_kind in three_dimensional_kinds
                    else texture.copy(),
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
                    top_texture = None
                    if render_kind == "barrel_block":
                        top_texture = self._atlas_texture(
                            atlas_image,
                            atlas_mapping,
                            "minecraft:block/barrel_top",
                        )
                    if texture is None or (render_kind == "barrel_block" and top_texture is None):
                        continue
                    try:
                        if render_kind == "chest_entity":
                            icon = self._render_chest_icon(texture)
                        elif render_kind == "barrel_block":
                            icon = self._render_barrel_icon(texture, top_texture)
                        elif render_kind == "shulker_entity":
                            icon = self._render_shulker_icon(texture)
                        elif render_kind == "cube_all":
                            icon = self._render_cube_icon(texture)
                        else:
                            icon = self._render_flat_icon(texture)
                        self._base_icons[choice] = icon
                        self._icon_sources[choice] = (
                            "cube" if render_kind in three_dimensional_kinds else "flat",
                            icon.copy()
                            if render_kind in three_dimensional_kinds
                            else texture.copy(),
                        )
                    except Exception:
                        continue
        finally:
            try:
                if atlas_image is not None:
                    atlas_image.close()
            except Exception:
                pass

        self._add_shulker_color_swatches()
        return bool(self._base_icons)

    def _add_shulker_color_swatches(self):
        if Image is None or ImageDraw is None:
            return
        for choice, rgb in SHULKER_COLOR_RGB.items():
            if choice in self._base_icons:
                continue
            try:
                base = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                draw = ImageDraw.Draw(base)
                red, green, blue = rgb
                top = (
                    min(255, int(red * 1.18)),
                    min(255, int(green * 1.18)),
                    min(255, int(blue * 1.18)),
                    255,
                )
                left = (max(0, int(red * 0.82)), max(0, int(green * 0.82)), max(0, int(blue * 0.82)), 255)
                right = (max(0, int(red * 0.66)), max(0, int(green * 0.66)), max(0, int(blue * 0.66)), 255)
                outline = (31, 24, 37, 255)
                draw.polygon(((32, 7), (55, 19), (32, 31), (9, 19)), fill=top, outline=outline)
                draw.polygon(((9, 19), (32, 31), (32, 56), (9, 44)), fill=left, outline=outline)
                draw.polygon(((32, 31), (55, 19), (55, 44), (32, 56)), fill=right, outline=outline)
                draw.line(((10, 31), (32, 43), (54, 31)), fill=outline, width=2)
                self._base_icons[choice] = base
                self._icon_sources[choice] = ("cube", base.copy())
            except Exception:
                continue

        default_icon = self._base_icons.get("default")
        if default_icon is not None and "Shulker Box" not in self._base_icons:
            self._base_icons["Shulker Box"] = default_icon.copy()
            self._icon_sources["Shulker Box"] = ("cube", default_icon.copy())

    def available_count(self):
        self.ensure_loaded()
        return len(self._base_icons)

    def get_bitmap(self, choice, size, padding=0):
        self.ensure_loaded()
        choice = _storage_icon_choice_key(choice)
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
        self.ensure_loaded()
        choice = _storage_icon_choice_key(choice)
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
        self._fill = background or BLOCKS_TO_STORAGE_THEME["surface"]
        self._border = border or BLOCKS_TO_STORAGE_THEME["border_soft"]
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

            border_width = max(1, int(TOOLTIP_BORDER_WIDTH))
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
            return BLOCKS_TO_STORAGE_THEME["surface_alt"], BLOCKS_TO_STORAGE_THEME["disabled"], BLOCKS_TO_STORAGE_THEME["border_soft"]
        if self._primary:
            if self._pressed:
                fill = BLOCKS_TO_STORAGE_THEME["accent_pressed"]
            elif self._hovered:
                fill = BLOCKS_TO_STORAGE_THEME["accent_hover"]
            else:
                fill = BLOCKS_TO_STORAGE_THEME["accent"]
            return fill, BLOCKS_TO_STORAGE_THEME["text"], fill
        if self._pressed:
            fill = BLOCKS_TO_STORAGE_THEME["surface_pressed"]
        elif self._hovered:
            fill = BLOCKS_TO_STORAGE_THEME["surface_hover"]
        else:
            fill = BLOCKS_TO_STORAGE_THEME["surface_alt"]
        return fill, BLOCKS_TO_STORAGE_THEME["text"], BLOCKS_TO_STORAGE_THEME["border"]

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
            gc.SetPen(wx.Pen(BLOCKS_TO_STORAGE_THEME["accent_hover"], 1))
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
        fill = BLOCKS_TO_STORAGE_THEME["accent"] if self._value and enabled else BLOCKS_TO_STORAGE_THEME["surface_alt"]
        if self._hovered and enabled and not self._value:
            fill = BLOCKS_TO_STORAGE_THEME["surface_hover"]
        border = BLOCKS_TO_STORAGE_THEME["accent_hover"] if self.HasFocus() and enabled else BLOCKS_TO_STORAGE_THEME["border"]
        text_color = BLOCKS_TO_STORAGE_THEME["text"] if enabled else BLOCKS_TO_STORAGE_THEME["disabled"]
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(box_x + 0.5, box_y + 0.5, box_size - 1, box_size - 1, _dip(self, 4))
        if self._value:
            gc.SetPen(wx.Pen(BLOCKS_TO_STORAGE_THEME["text"], max(2, _dip(self, 2))))
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
        gc.SetBrush(wx.Brush(BLOCKS_TO_STORAGE_THEME["border_soft"]))
        gc.DrawRoundedRectangle(start, center_y - track_height / 2, max(1, end - start), track_height, track_height / 2)
        gc.SetBrush(wx.Brush(BLOCKS_TO_STORAGE_THEME["accent"] if self.IsEnabled() else BLOCKS_TO_STORAGE_THEME["disabled"]))
        gc.DrawRoundedRectangle(start, center_y - track_height / 2, max(1, knob_x - start), track_height, track_height / 2)
        gc.SetPen(wx.Pen(BLOCKS_TO_STORAGE_THEME["accent_hover"] if self.HasFocus() else BLOCKS_TO_STORAGE_THEME["border"], 1))
        gc.SetBrush(wx.Brush(BLOCKS_TO_STORAGE_THEME["accent_hover"] if self._hovered and self.IsEnabled() else BLOCKS_TO_STORAGE_THEME["accent"]))
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
        self._background = background or BLOCKS_TO_STORAGE_THEME["window"]
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
        gc.SetBrush(wx.Brush(BLOCKS_TO_STORAGE_THEME["surface_alt"]))
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
            BLOCKS_TO_STORAGE_THEME["accent_hover"]
            if self._dragging
            else BLOCKS_TO_STORAGE_THEME["accent"]
            if self._hovered
            else BLOCKS_TO_STORAGE_THEME["border"]
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
                BLOCKS_TO_STORAGE_THEME["surface_alt"],
                BLOCKS_TO_STORAGE_THEME["disabled"],
                BLOCKS_TO_STORAGE_THEME["border_soft"],
            )
        if self._pressed:
            return (
                BLOCKS_TO_STORAGE_THEME["accent_pressed"],
                BLOCKS_TO_STORAGE_THEME["text"],
                BLOCKS_TO_STORAGE_THEME["accent_pressed"],
            )
        if self._hovered:
            return (
                BLOCKS_TO_STORAGE_THEME["surface_hover"],
                BLOCKS_TO_STORAGE_THEME["text"],
                BLOCKS_TO_STORAGE_THEME["accent_hover"],
            )
        if self._selected:
            return (
                BLOCKS_TO_STORAGE_THEME["surface_pressed"],
                BLOCKS_TO_STORAGE_THEME["text"],
                BLOCKS_TO_STORAGE_THEME["accent"],
            )
        return (
            BLOCKS_TO_STORAGE_THEME["surface_alt"],
            BLOCKS_TO_STORAGE_THEME["text"],
            BLOCKS_TO_STORAGE_THEME["border_soft"],
        )

class ModernIconChoiceOption(ModernChoiceOption):

    def __init__(self, parent, label, bitmap, selected=False):
        super().__init__(
            parent,
            label,
            selected=selected,
            row_height=STORAGE_SELECTOR_TILE_HEIGHT,
        )
        self._bitmap = bitmap
        self._icon_y_offset = STORAGE_SELECTOR_ICON_OFFSET
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
                + _dip(self, self._icon_y_offset)
            )

            maximum_icon_y = max(
                0.0,
                float(
                    size.height
                    - bitmap_height
                    - _dip(
                        self,
                        STORAGE_SELECTOR_ICON_BOTTOM_PADDING,
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
                gc.SetFont(placeholder_font, BLOCKS_TO_STORAGE_THEME["muted"])
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
        shadow_color = BLOCKS_TO_STORAGE_THEME["console_bg"]
        for line in lines:
            text_width, text_height = _graphics_text_size(gc, line)
            text_x = (size.width - text_width) / 2.0

            gc.SetFont(self.GetFont(), shadow_color)
            gc.DrawText(line, text_x + 1, line_y + 1)
            gc.SetFont(self.GetFont(), text_color)
            gc.DrawText(line, text_x, line_y)
            line_y += text_height + _dip(self, 1)

        if self.HasFocus() and self.IsAvailable() and not self.IsBusy():
            gc.SetPen(wx.Pen(BLOCKS_TO_STORAGE_THEME["accent_hover"], 1))
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
            f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorageChoicePopup",
        )
        self._owner_ref = weakref.ref(owner)
        self._buttons = []
        self._dismiss_notified = True
        self._closing = False
        self._popup_radius = STORAGE_SELECTOR_POPUP_RADIUS
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
            background=BLOCKS_TO_STORAGE_THEME["surface"],
            border=BLOCKS_TO_STORAGE_THEME["border"],
            radius=self._popup_radius,
            clear_background=self._transparent_corner_colour,
        )
        self._shell = shell

        shell_sizer = wx.BoxSizer(wx.VERTICAL)

        self._scroll = ModernScrollViewport(
            shell,
            background=BLOCKS_TO_STORAGE_THEME["surface"],
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
            icon_columns = owner.GetIconPopupColumns()
            grid = wx.GridSizer(
                rows=0,
                cols=icon_columns,
                vgap=_dip(self._list_content, STORAGE_SELECTOR_GRID_GAP),
                hgap=_dip(self._list_content, STORAGE_SELECTOR_GRID_GAP),
            )
            self._content.Add(grid, 0, wx.EXPAND)
            for index, label in enumerate(choices):
                button = ModernIconChoiceOption(
                    self._list_content,
                    label,
                    owner.GetIconBitmap(label, STORAGE_SELECTOR_ICON_SIZE),
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
        display_index = wx.Display.GetFromWindow(owner)
        if display_index == wx.NOT_FOUND:
            display_index = 0
        try:
            work_area = wx.Display(display_index).GetClientArea()
        except Exception:
            work_area = wx.Rect(0, 0, *wx.GetDisplaySize())

        if self._icon_mode:
            icon_columns = owner.GetIconPopupColumns()
            visible_rows = owner.GetIconPopupVisibleRows()
            width = max(
                owner_rect.width,
                _dip(owner, STORAGE_SELECTOR_MIN_WIDTH),
            )
            rows = max(
                1,
                (len(choices) + icon_columns - 1) // icon_columns,
            )
            tile_height = _dip(owner, STORAGE_SELECTOR_TILE_HEIGHT)
            grid_gap = _dip(owner, STORAGE_SELECTOR_GRID_GAP)
            wanted_height = (
                rows * tile_height
                + max(0, rows - 1) * grid_gap
                + _dip(owner, 14)
            )
            minimum_height = _dip(owner, 180)
            work_area_limit = max(
                _dip(owner, 220),
                int(work_area.height * 0.65),
            )
            if visible_rows is None:
                maximum_height = work_area_limit
            else:
                bounded_rows = max(1, min(rows, int(visible_rows)))
                visible_height = (
                    bounded_rows * tile_height
                    + max(0, bounded_rows - 1) * grid_gap
                    + _dip(owner, 14)
                )
                maximum_height = min(work_area_limit, visible_height)
        else:
            width = max(owner_rect.width, _dip(owner, 240))
            row_height = _dip(owner, 35)
            wanted_height = len(choices) * row_height + _dip(owner, 14)
            minimum_height = _dip(owner, 90)
            maximum_height = max(_dip(owner, 140), int(work_area.height * 0.55))
        width = min(width, max(_dip(owner, 260), work_area.width))
        height = min(max(minimum_height, wanted_height), maximum_height)

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

    def __init__(
        self,
        parent,
        choices,
        icon_provider=None,
        show_icons=False,
        icon_columns=STORAGE_SELECTOR_ICON_COLUMNS,
        icon_visible_rows=None,
    ):
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
        self._fill = BLOCKS_TO_STORAGE_THEME["surface_alt"]
        self._radius = 9
        self._popup = None
        self._popup_open = False
        self._suppress_popup_until = 0.0
        self._icon_provider = icon_provider
        self._show_icons = bool(show_icons)
        try:
            self._icon_columns = max(1, int(icon_columns))
        except Exception:
            self._icon_columns = STORAGE_SELECTOR_ICON_COLUMNS
        try:
            self._icon_visible_rows = (
                None
                if icon_visible_rows is None
                else max(1, int(icon_visible_rows))
            )
        except Exception:
            self._icon_visible_rows = None

        self.SetBackgroundColour(self._fill)
        self.SetForegroundColour(BLOCKS_TO_STORAGE_THEME["text"])
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
            child.SetForegroundColour(BLOCKS_TO_STORAGE_THEME["text"])
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

    def GetIconPopupColumns(self):
        return max(1, int(self._icon_columns))

    def GetIconPopupVisibleRows(self):
        return self._icon_visible_rows

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
        if not self._show_icons or provider is None or not self._choices:
            return False
        try:
            if provider.available_count() <= 0:
                return False
            for choice in self._choices:
                bitmap = provider.get_bitmap(choice, _dip(self, 24), padding=1)
                if bitmap is None or not bitmap.IsOk():
                    return False
            return True
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
                BLOCKS_TO_STORAGE_THEME["surface_alt"],
                BLOCKS_TO_STORAGE_THEME["disabled"],
                BLOCKS_TO_STORAGE_THEME["border_soft"],
            )
        if self._pressed:
            fill = BLOCKS_TO_STORAGE_THEME["surface_pressed"]
        elif self._hovered or self._popup_open:
            fill = BLOCKS_TO_STORAGE_THEME["surface_hover"]
        else:
            fill = BLOCKS_TO_STORAGE_THEME["surface_alt"]
        border = (
            BLOCKS_TO_STORAGE_THEME["accent_hover"]
            if self.HasFocus() or self._popup_open
            else BLOCKS_TO_STORAGE_THEME["border"]
        )
        return fill, BLOCKS_TO_STORAGE_THEME["text"], border

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

class DarkMessageDialog(wx.Dialog):

    def __init__(self, parent, message, caption, style=wx.OK | wx.CENTRE):
        dialog_style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        super().__init__(parent, title=str(caption), style=dialog_style)
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorageDialog",
        )
        self._message_style = int(style)
        self.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["window"])
        self.SetMinSize((_dip(self, 390), _dip(self, 190)))

        root = wx.Panel(self, style=wx.BORDER_NONE | wx.CLIP_CHILDREN)
        _mark_custom_ui_owned(root)
        root.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["window"])
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
    dialog = DarkMessageDialog(parent, message, caption, style)
    try:
        return dialog.ShowModal()
    finally:
        dialog.Destroy()

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
            title="Manage Blocks to Storage files",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorageSettingsDialog",
        )
        self._actions = list(actions)
        self._selection = wx.NOT_FOUND
        self._on_size_changed = on_size_changed
        self.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["window"])
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
        root.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["window"])
        outer = wx.BoxSizer(wx.VERTICAL)

        title = _make_text(root, "MANAGE PLUGIN FILES", point_size=14, bold=True)
        outer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP, _dip(root, 18))

        self._description = _make_text(
            root,
            "Choose what to do with Blocks to Storage managed files.",
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
            background=BLOCKS_TO_STORAGE_THEME["surface"],
            border=BLOCKS_TO_STORAGE_THEME["border_soft"],
            radius=10,
        )
        card_sizer = wx.BoxSizer(wx.VERTICAL)

        self._scroll = ModernScrollViewport(
            list_card,
            background=BLOCKS_TO_STORAGE_THEME["surface"],
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

    _FORWARDED_EVENTS = (wx.EVT_TEXT, wx.EVT_TEXT_ENTER, wx.EVT_KILL_FOCUS, wx.EVT_SET_FOCUS)

    def __init__(self, parent, value="", width=64, center=True, large=True):
        super().__init__(parent, background=BLOCKS_TO_STORAGE_THEME["surface_alt"], border=BLOCKS_TO_STORAGE_THEME["border"], radius=8)
        self.SetMinSize((_dip(self, width), _dip(self, 32)))
        sizer = wx.BoxSizer(wx.VERTICAL)
        self._text = wx.TextCtrl(
            self,
            value=str(value),
            style=(wx.BORDER_NONE | wx.TE_PROCESS_ENTER | (wx.TE_CENTER if center else 0)),
        )
        _mark_custom_ui_owned(self._text)
        self._text.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["surface_alt"])
        self._text.SetForegroundColour(BLOCKS_TO_STORAGE_THEME["text"])

        try:
            font = self._text.GetFont()
            base_size = max(1.0, float(font.GetPointSize()))
            target_size = base_size * (1.25 if large else 1.0)
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
        self._border = BLOCKS_TO_STORAGE_THEME["accent_hover"] if self._text.HasFocus() else BLOCKS_TO_STORAGE_THEME["border"]
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

def _apply_rounded_child_shape(window, radius=10):
    try:
        size = window.GetClientSize()
        width = int(size.GetWidth())
        height = int(size.GetHeight())
    except Exception:
        try:
            width, height = map(int, window.GetClientSize())
        except Exception:
            return False

    if width <= 1 or height <= 1:
        return False

    try:
        radius_px = max(1, int(_dip(window, radius)))
    except Exception:
        radius_px = max(1, int(radius))
    radius_px = min(radius_px, width // 2, height // 2)

    if os.name == "nt":
        region_handle = None
        try:
            window_handle = int(window.GetHandle())
            if not window_handle:
                return False

            gdi32 = ctypes.windll.gdi32
            user32 = ctypes.windll.user32

            create_round_region = gdi32.CreateRoundRectRgn
            create_round_region.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            create_round_region.restype = ctypes.c_void_p

            set_window_region = user32.SetWindowRgn
            set_window_region.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_bool,
            ]
            set_window_region.restype = ctypes.c_int

            delete_object = gdi32.DeleteObject
            delete_object.argtypes = [ctypes.c_void_p]
            delete_object.restype = ctypes.c_int

            diameter = max(2, radius_px * 2)
            region_handle = create_round_region(
                0,
                0,
                width + 1,
                height + 1,
                diameter,
                diameter,
            )
            if not region_handle:
                return False

            result = set_window_region(
                ctypes.c_void_p(window_handle),
                ctypes.c_void_p(region_handle),
                True,
            )
            if result:

                region_handle = None
                return True
        except Exception:
            pass
        finally:
            if region_handle:
                try:
                    ctypes.windll.gdi32.DeleteObject(
                        ctypes.c_void_p(region_handle)
                    )
                except Exception:
                    pass

    return _apply_rounded_window_shape(window, radius)

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
            background=BLOCKS_TO_STORAGE_THEME["surface"],
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
            background=BLOCKS_TO_STORAGE_THEME["surface"],
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
                BLOCKS_TO_STORAGE_THEME["surface"],
            )
            text_rgba = _wx_colour_tuple(
                BLOCKS_TO_STORAGE_THEME["text"],
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

class ModernSectionButton(ModernButton):

    def __init__(self, parent, label, value=True):
        self._section_label = str(label)
        self._value = bool(value)
        super().__init__(
            parent,
            "",
            primary=False,
            compact=True,
            content_alignment="left",
        )
        self.Bind(wx.EVT_BUTTON, self._toggle_from_button)
        self._sync_label()

    def _sync_label(self):
        marker = "▼" if self._value else "▶"
        ModernButton.SetLabel(self, f"{marker} {self._section_label}")

    def SetSectionLabel(self, label):
        self._section_label = str(label)
        self._sync_label()

    def GetValue(self):
        return bool(self._value)

    def SetValue(self, value):
        self._value = bool(value)
        self._sync_label()

    def _toggle_from_button(self, _event):
        self._value = not self._value
        self._sync_label()
        _emit_command_event(self, wx.EVT_TOGGLEBUTTON)

class ModernFileCheckRow(RoundedPanel):

    def __init__(self, parent, label, value=False):
        super().__init__(
            parent,
            background=BLOCKS_TO_STORAGE_THEME["surface"],
            border=BLOCKS_TO_STORAGE_THEME["border_soft"],
            radius=9,
        )
        text = str(label)
        parts = [part.strip() for part in text.split(" | ") if part.strip()]
        title = parts[0] if parts else text
        details = " • ".join(parts[1:])

        self._check = ModernCheckBox(self, title, value)
        self._details = _make_text(self, details, point_size=8, muted=True)
        self._details.Wrap(_dip(self, 430))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(
            _dip(
                self,
                max(
                    0,
                    9 - UI_CHECKBOX_GAP_REDUCTION,
                ),
            )
        )
        sizer.Add(
            self._check,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            _dip(self, 9),
        )
        if details:
            sizer.Add(
                self._details,
                0,
                wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
                _dip(self, 10),
            )
        else:
            sizer.AddSpacer(_dip(self, 7))
        self.SetSizer(sizer)

        self.Bind(wx.EVT_SIZE, self._on_size)
        for target in (self, self._details):
            target.SetCursor(wx.Cursor(wx.CURSOR_HAND))
            target.Bind(wx.EVT_LEFT_UP, self._on_activate)

    def GetValue(self):
        return self._check.GetValue()

    def SetValue(self, value):
        self._check.SetValue(value)

    def _on_activate(self, _event):
        self._check.SetValue(not self._check.GetValue())
        _emit_command_event(self._check, wx.EVT_CHECKBOX)

    def _on_size(self, event):
        try:
            width = max(_dip(self, 220), self.GetClientSize().width - _dip(self, 24))
            self._details.Wrap(width)
            self.Layout()
        except Exception:
            pass
        event.Skip()

class DarkMultiChoiceDialog(wx.Dialog):

    def __init__(self, parent, title, message, choices):
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        _mark_custom_ui_owned(self, f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorageFileSelection")
        self.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["passive_window"])
        self._checks = []

        outer = wx.BoxSizer(wx.VERTICAL)
        heading = _make_text(self, title.upper(), point_size=13, bold=True)
        outer.Add(heading, 0, wx.ALL | wx.EXPAND, _dip(self, 14))
        description = _make_text(self, message, point_size=9, muted=True)
        description.Wrap(500)
        outer.Add(
            description,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            _dip(self, 14),
        )

        viewport = ModernScrollViewport(
            self,
            background=BLOCKS_TO_STORAGE_THEME["passive_window"],
        )
        viewport.SetMinSize((-1, _dip(self, 260)))
        content = viewport.GetContentWindow()
        content_sizer = wx.BoxSizer(wx.VERTICAL)
        viewport.SetContentSizer(content_sizer)
        for label in choices:
            check = ModernFileCheckRow(content, str(label), False)
            self._checks.append(check)
            content_sizer.Add(
                check,
                0,
                wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
                _dip(self, 10),
            )
        content_sizer.AddSpacer(_dip(self, 4))

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(viewport, 1, wx.EXPAND)
        scrollbar = ModernScrollBar(self, viewport)
        row.Add(scrollbar, 0, wx.LEFT | wx.EXPAND, _dip(self, 6))
        outer.Add(
            row,
            1,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            _dip(self, 14),
        )

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        back = ModernButton(self, "Back")
        accept = ModernButton(self, "Continue", primary=True)
        back.Bind(wx.EVT_BUTTON, lambda _event: self.EndModal(wx.ID_CANCEL))
        accept.Bind(wx.EVT_BUTTON, lambda _event: self.EndModal(wx.ID_OK))
        buttons.Add(back, 1, wx.RIGHT | wx.EXPAND, _dip(self, 8))
        buttons.Add(accept, 1, wx.EXPAND)
        outer.Add(
            buttons,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            _dip(self, 14),
        )

        self.SetSizer(outer)
        self.SetMinSize((_dip(self, 500), _dip(self, 410)))
        self.SetSize((_dip(self, 560), _dip(self, 500)))
        try:
            self.CentreOnParent()
        except Exception:
            self.Centre()
        wx.CallAfter(viewport._modern_sync_layout)
        wx.CallAfter(scrollbar.sync)

    def GetSelections(self):
        return tuple(
            index
            for index, check in enumerate(self._checks)
            if check.GetValue()
        )

class BlocksToStorageWindow(wx.Frame):

    def __init__(self, owner, host):
        style = wx.DEFAULT_FRAME_STYLE
        style |= getattr(wx, "FRAME_FLOAT_ON_PARENT", 0)
        super().__init__(owner, title="Blocks to Storage", size=FLOATING_DEFAULT_SIZE, style=style)
        _mark_custom_ui_owned(self, f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorage")
        self._host_ref = weakref.ref(host)
        self.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["window"])
        self.SetMinSize((_dip(self, FLOATING_MIN_SIZE[0]), _dip(self, FLOATING_MIN_SIZE[1])))
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def _on_close(self, event):
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
        host = self._host_ref()
        if host is not None:
            host._update_launcher_status(bool(event.IsShown()))
        event.Skip()

class PluginClassName(wx.Panel, DefaultOperationUI):
    SETTINGS_VIEWPORT_HEIGHT = 310
    SETTINGS_GROW_PROPORTION = 4
    CONSOLE_GROW_PROPORTION = 1
    CONSOLE_MIN_TEXT_HEIGHT = 150
    CONSOLE_MIN_CARD_HEIGHT = 194
    FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT = 720
    CONSOLE_TOOLTIP_DELAY_MS = 650
    CONTROL_TOOLTIP_DELAY_MS = 550

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

    FOUND_ENTRIES_FILENAME = "Found Entries.BTSP"
    CONVERSION_ENTRIES_FILENAME = "Conversion Entries.BTSP"
    CONVERSION_CANDIDATES_FILENAME = "Conversion Candidates.BTSP"
    BUILT_IN_INTEGRATED_SOURCE_LABEL = "Built-in integrated entry"
    INSTALLED_LANGUAGE_SOURCE_LABEL = "Installed en_US.lang"
    SETTINGS_CONFIG_FILENAME = "Blocks to Storage.config"
    SETTINGS_CONFIG_FORMAT_VERSION = 2
    SETTINGS_SAVE_DELAY_MS = 500
    MAX_SETTINGS_CONFIG_BYTES = 1024 * 1024

    CONSOLE_SEMANTIC_NAME = "AmuletPluginConsole:BlocksToStorage"
    MAX_CONVERSION_CANDIDATES_FILE_BYTES = 1024 * 1024
    MAX_CONVERSION_CANDIDATES = 5000
    MAX_CONVERSION_ENTRIES_FILE_BYTES = 1024 * 1024
    MAX_CONVERSION_ENTRIES = 5000
    MAX_CONVERSION_DIAGNOSTIC_DETAILS = 20
    MAX_CONVERSION_DIAGNOSTIC_TEXT_LENGTH = 160
    MAX_AMULET_CONVERSION_AUDIT_ENTRIES = 100
    MAX_AMULET_CONVERSION_AUDIT_OMITTED_IDENTITIES = 5000
    MAX_FOUND_ENTRY_SCAN_IDENTITY_DETAILS = 20

    REVIEWED_AMULET_NORMALIZATIONS = {
        "minecraft:plant": "minecraft:short_grass",
    }

    BUILT_IN_RESOLVED_CANDIDATE_SOURCES = {
        "minecraft:coral",
        "minecraft:coral_fan",
        "minecraft:coral_fan_dead",
        "minecraft:coral_fan_hang",
        "minecraft:coral_fan_hang2",
        "minecraft:coral_fan_hang3",
        "minecraft:door",
        "minecraft:double_plant",
        "minecraft:fence",
        "minecraft:glazed_terracotta",
        "minecraft:leaves",
        "minecraft:leaves2",
        "minecraft:log",
        "minecraft:log2",
        "minecraft:planks",
        "minecraft:sapling",
        "minecraft:slab",
        "minecraft:stained_terracotta",
        "minecraft:stairs",
        "minecraft:wall",
        "minecraft:wood",
    }

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

    SHULKER_COLORS = SHULKER_COLOR_CHOICES

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
        "minecraft:sapling",
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
        "minecraft:coral",
        "minecraft:coral_fan",
        "minecraft:coral_fan_dead",
        "minecraft:coral_fan_hang",
        "minecraft:coral_fan_hang2",
        "minecraft:coral_fan_hang3",
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
        "minecraft:magma",
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
        "minecraft:coral",
        "minecraft:coral_fan",
        "minecraft:coral_fan_dead",
        "minecraft:coral_fan_hang",
        "minecraft:coral_fan_hang2",
        "minecraft:coral_fan_hang3",
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
        "minecraft:plant",
        "minecraft:sapling",
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
        "minecraft:coral",
        "minecraft:coral_fan",
        "minecraft:coral_fan_dead",
        "minecraft:coral_fan_hang",
        "minecraft:coral_fan_hang2",
        "minecraft:coral_fan_hang3",
    }

    ITEM_NAME_OVERRIDES = {
        "minecraft:fire_fly_bush": "minecraft:firefly_bush",
        "minecraft:small_dripleaf": "minecraft:small_dripleaf_block",
        "minecraft:bamboo_sapling": "minecraft:bamboo",
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

    CORAL_TYPE_ALIASES = {
        "blue": "tube",
        "pink": "brain",
        "purple": "bubble",
        "red": "fire",
        "yellow": "horn",
        "tube": "tube",
        "brain": "brain",
        "bubble": "bubble",
        "fire": "fire",
        "horn": "horn",
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

    SAPLING_ITEM_BY_TYPE = {
        "oak": "minecraft:oak_sapling",
        "spruce": "minecraft:spruce_sapling",
        "birch": "minecraft:birch_sapling",
        "jungle": "minecraft:jungle_sapling",
        "acacia": "minecraft:acacia_sapling",
        "dark_oak": "minecraft:dark_oak_sapling",
        "big_oak": "minecraft:dark_oak_sapling",
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

    LEGACY_DISPLAY_NAME_ALIASES = {
        "acacia_slab": ("wooden_slab_acacia",),
        "andesite_slab": ("stone_slab3_andesite",),
        "birch_slab": ("wooden_slab_birch",),
        "brick_slab": ("stone_slab_brick",),
        "cobblestone_slab": ("stone_slab_cobble",),
        "cut_red_sandstone_slab": ("stone_slab4_cut_red_sandstone",),
        "cut_sandstone_slab": ("stone_slab4_cut_sandstone",),
        "dark_oak_slab": ("wooden_slab_big_oak",),
        "dark_prismarine_slab": ("stone_slab2_prismarine_dark",),
        "diorite_slab": ("stone_slab3_diorite",),
        "end_stone_brick_slab": ("stone_slab3_end_brick",),
        "granite_slab": ("stone_slab3_granite",),
        "jungle_slab": ("wooden_slab_jungle",),
        "mossy_cobblestone_slab": ("stone_slab2_mossy_cobblestone",),
        "mossy_stone_brick_slab": ("stone_slab4_mossy_stone_brick",),
        "nether_brick_slab": ("stone_slab_nether_brick",),
        "oak_slab": ("wooden_slab_oak",),
        "polished_andesite_slab": ("stone_slab3_andesite_smooth",),
        "polished_diorite_slab": ("stone_slab3_diorite_smooth",),
        "polished_granite_slab": ("stone_slab3_granite_smooth",),
        "prismarine_brick_slab": ("stone_slab2_prismarine_bricks",),
        "prismarine_slab": ("stone_slab2_prismarine_rough",),
        "purpur_slab": ("stone_slab2_purpur",),
        "quartz_slab": ("stone_slab_quartz",),
        "red_nether_brick_slab": ("stone_slab2_red_nether_brick",),
        "red_sandstone_slab": ("stone_slab2_red_sandstone",),
        "sandstone_slab": ("stone_slab_sand",),
        "smooth_quartz_slab": ("stone_slab4_smooth_quartz",),
        "smooth_red_sandstone_slab": ("stone_slab3_red_sandstone_smooth",),
        "smooth_sandstone_slab": ("stone_slab2_sandstone_smooth",),
        "smooth_stone_slab": ("stone_slab_stone",),
        "spruce_slab": ("wooden_slab_spruce",),
        "stone_brick_slab": ("stone_slab_smooth_stone_brick",),
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

    INTEGRATED_SCAN_IDENTITY_DISPLAY_NAMES = {
        "chiseled_cinnabar": (
            "tile.chiseled_cinnabar.name",
            "Chiseled Cinnabar",
        ),
        "chiseled_sulfur": (
            "tile.chiseled_sulfur.name",
            "Chiseled Sulfur",
        ),
        "cinnabar": (
            "tile.cinnabar.name",
            "Cinnabar",
        ),
        "cinnabar_brick_double_slab": (
            "tile.cinnabar_brick_double_slab.name",
            "Cinnabar Brick Double Slab",
        ),
        "cinnabar_brick_slab": (
            "tile.cinnabar_brick_slab.name",
            "Cinnabar Brick Slab",
        ),
        "cinnabar_brick_stairs": (
            "tile.cinnabar_brick_stairs.name",
            "Cinnabar Brick Stairs",
        ),
        "cinnabar_brick_wall": (
            "tile.cinnabar_brick_wall.name",
            "Cinnabar Brick Wall",
        ),
        "cinnabar_bricks": (
            "tile.cinnabar_bricks.name",
            "Cinnabar Bricks",
        ),
        "cinnabar_double_slab": (
            "tile.cinnabar_double_slab.name",
            "Cinnabar Double Slab",
        ),
        "cinnabar_slab": (
            "tile.cinnabar_slab.name",
            "Cinnabar Slab",
        ),
        "cinnabar_stairs": (
            "tile.cinnabar_stairs.name",
            "Cinnabar Stairs",
        ),
        "cinnabar_wall": (
            "tile.cinnabar_wall.name",
            "Cinnabar Wall",
        ),
        "polished_cinnabar": (
            "tile.polished_cinnabar.name",
            "Polished Cinnabar",
        ),
        "polished_cinnabar_double_slab": (
            "tile.polished_cinnabar_double_slab.name",
            "Polished Cinnabar Double Slab",
        ),
        "polished_cinnabar_slab": (
            "tile.polished_cinnabar_slab.name",
            "Polished Cinnabar Slab",
        ),
        "polished_cinnabar_stairs": (
            "tile.polished_cinnabar_stairs.name",
            "Polished Cinnabar Stairs",
        ),
        "polished_cinnabar_wall": (
            "tile.polished_cinnabar_wall.name",
            "Polished Cinnabar Wall",
        ),
        "polished_sulfur": (
            "tile.polished_sulfur.name",
            "Polished Sulfur",
        ),
        "polished_sulfur_double_slab": (
            "tile.polished_sulfur_double_slab.name",
            "Polished Sulfur Double Slab",
        ),
        "polished_sulfur_slab": (
            "tile.polished_sulfur_slab.name",
            "Polished Sulfur Slab",
        ),
        "polished_sulfur_stairs": (
            "tile.polished_sulfur_stairs.name",
            "Polished Sulfur Stairs",
        ),
        "polished_sulfur_wall": (
            "tile.polished_sulfur_wall.name",
            "Polished Sulfur Wall",
        ),
        "potent_sulfur": (
            "tile.potent_sulfur.name",
            "Potent Sulfur",
        ),
        "sulfur": (
            "tile.sulfur.name",
            "Sulfur",
        ),
        "sulfur_brick_double_slab": (
            "tile.sulfur_brick_double_slab.name",
            "Sulfur Brick Double Slab",
        ),
        "sulfur_brick_slab": (
            "tile.sulfur_brick_slab.name",
            "Sulfur Brick Slab",
        ),
        "sulfur_brick_stairs": (
            "tile.sulfur_brick_stairs.name",
            "Sulfur Brick Stairs",
        ),
        "sulfur_brick_wall": (
            "tile.sulfur_brick_wall.name",
            "Sulfur Brick Wall",
        ),
        "sulfur_bricks": (
            "tile.sulfur_bricks.name",
            "Sulfur Bricks",
        ),
        "sulfur_double_slab": (
            "tile.sulfur_double_slab.name",
            "Sulfur Double Slab",
        ),
        "sulfur_slab": (
            "tile.sulfur_slab.name",
            "Sulfur Slab",
        ),
        "sulfur_spike": (
            "tile.sulfur_spike.name",
            "Sulfur Spike",
        ),
        "sulfur_stairs": (
            "tile.sulfur_stairs.name",
            "Sulfur Stairs",
        ),
        "sulfur_wall": (
            "tile.sulfur_wall.name",
            "Sulfur Wall",
        ),
    }

    BEDROCK_EN_US_DISPLAY_NAMES.update(
        INTEGRATED_SCAN_IDENTITY_DISPLAY_NAMES
    )

    INTEGRATED_SCAN_IDENTITY_BLOCK_ALIASES = frozenset(
        INTEGRATED_SCAN_IDENTITY_DISPLAY_NAMES
    )

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

        self._selection = BlockSelectionBehaviour(self.canvas)
        self._world_platform = getattr(world.level_wrapper, "platform", "universal")
        self._world_version = getattr(world.level_wrapper, "version", None)
        self._scan_order: List[str] = []
        self._report_lines: List[str] = []
        self._last_report_text = ""

        self._plugin_window = None
        self._window_has_been_shown = False
        self._destroying = False
        self._console_visible = True
        self._scroll_refresh_pending = False
        self._scroll_refresh_call = None
        self._window_geometry_events_ready = False
        self._last_normal_window_size = list(FLOATING_DEFAULT_SIZE)
        self._last_manage_dialog_size = list(MANAGE_DIALOG_DEFAULT_SIZE)
        self._operation_running = False
        self._operation_ui_generation = 0
        self._active_operation_ui_generation = 0
        self._operation_button_restore_call = None
        self._control_help_window = None
        self._control_help_call = None
        self._control_help_anchor_ref = None
        self._control_help_text = ""

        self._tooltips_suspended = False
        self._console_help_window = None
        self._console_help_call = None
        self._console_help_hovered = False
        self._console_help_text = (
            "Shows the current Blocks to Storage report. Click or focus the "
            "console to read, select, and copy text without the help bubble remaining open."
        )
        self._storage_icon_cache = AmuletStorageIconCache()

        self._fast_scan_failed = False
        self._fast_scan_fail_reason = ""
        self._fast_clear_failed = False
        self._fast_clear_fail_reason = ""
        self._ambiguous_fast_scan_fallbacks = 0
        self._missing_scan_chunks: Set[Tuple[int, int]] = set()
        self._unresolved_write_attempt_counts = collections.defaultdict(int)

        self._external_language_aliases: Dict[str, Tuple[str, str]] = {}
        self._found_entries_aliases: Dict[str, Tuple[str, str]] = {}
        self._found_entries_raw_entries: Dict[str, str] = {}
        self._external_language_loaded_path = ""
        self._external_language_load_error = ""
        self._external_language_loaded_count = 0
        self._external_language_used: Dict[str, Tuple[str, str, str]] = {}
        self._found_entries_used: Dict[str, Tuple[str, str, str]] = {}
        self._pending_found_entries: Dict[str, str] = {}
        self._found_entries_write_error = ""
        self._found_entries_written_count = 0
        self._found_entries_sync_queued_count = 0
        self._external_language_prepared = False
        self._display_name_resolution_cache: Dict[
            str,
            Optional[Tuple[str, str, str]],
        ] = {}

        self._conversion_entries: Dict[str, str] = {}
        self._conversion_entries_used: Dict[str, str] = {}
        self._conversion_entries_skipped: Dict[str, str] = {}
        self._conversion_entries_skip_reason_counts: Dict[str, int] = {}
        self._conversion_entries_skip_details: List[str] = []
        self._conversion_entries_skip_detail_overflow = 0
        self._conversion_entries_load_error = ""
        self._conversion_entries_loaded_count = 0
        self._conversion_entries_prepared = False
        self._pending_conversion_candidates = collections.defaultdict(int)
        self._conversion_candidates_new_record_count = 0
        self._conversion_candidates_updated_record_count = 0
        self._conversion_candidate_observations_added_count = 0
        self._conversion_candidates_existing_record_count = 0
        self._conversion_candidates_total_record_count = 0
        self._conversion_candidates_write_error = ""

        self._settings_config_save_call = None
        self._settings_config_applying = False
        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._settings_defaults = {}

        self._amulet_translator_capabilities: Dict[str, Tuple[bool, str]] = {}
        self._amulet_translator_version_object = None
        self._amulet_translator_version_source = ""
        self._amulet_translator_capabilities_prepared = False
        self._amulet_conversion_audit_entries: Dict[
            Tuple[str, str], Tuple[str, str, str, str, str, str]
        ] = {}
        self._amulet_conversion_audit_buckets: Dict[
            int, Set[Tuple[str, str]]
        ] = collections.defaultdict(set)
        self._amulet_conversion_audit_omitted_identities: Set[
            Tuple[str, str]
        ] = set()
        self._amulet_conversion_audit_omitted_overflow = 0
        self._reviewed_amulet_normalizations_used = collections.Counter()
        self._reviewed_amulet_normalization_failures = collections.Counter()
        self._reviewed_amulet_normalization_cache: Dict[
            Tuple[str, Tuple[Tuple[str, str], ...]], Optional[str]
        ] = {}

        self._configure_tooltips()
        self._build_launcher_ui()
        self._build_floating_ui()
        self._initialize_settings_persistence()
        self._update_option_visibility()
        self._bind_floating_window_geometry_events()
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_host_destroy)
        try:
            wx.CallAfter(self._show_plugin_window)
        except Exception:
            self._show_plugin_window()

    def _build_launcher_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)
        margin = 6
        title = wx.StaticText(self, label="Blocks to Storage")
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
        card = RoundedPanel(
            parent,
            background=BLOCKS_TO_STORAGE_THEME["passive_surface"],
            border=BLOCKS_TO_STORAGE_THEME["passive_border"],
            radius=12,
        )
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

    def _create_collapsible_card(self, parent, label, subtitle=None, expanded=True, parent_sizer=None):
        card = RoundedPanel(
            parent,
            background=BLOCKS_TO_STORAGE_THEME["passive_surface"],
            border=BLOCKS_TO_STORAGE_THEME["passive_border"],
            radius=12,
        )
        card_sizer = wx.BoxSizer(wx.VERTICAL)
        card.SetSizer(card_sizer)
        header = ModernSectionButton(card, label, expanded)
        card_sizer.Add(
            header,
            0,
            wx.ALL | wx.EXPAND,
            _dip(card, UI_CARD_PADDING),
        )
        if subtitle:
            subtitle_control = _make_wrapped_text(
                card,
                subtitle,
                point_size=8,
                muted=True,
            )
            card_sizer.Add(
                subtitle_control,
                0,
                wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
                _dip(card, UI_CARD_PADDING),
            )

        content_fill = card.GetBackgroundColour()
        content_panel = RoundedPanel(
            card,
            background=content_fill,
            border=content_fill,
            radius=UI_COLLAPSIBLE_CONTENT_RADIUS,
        )

        def reshape_content_panel(event=None):
            _apply_rounded_child_shape(
                content_panel,
                UI_COLLAPSIBLE_CONTENT_RADIUS,
            )
            if event is not None:
                event.Skip()

        content_panel.Bind(
            wx.EVT_SIZE,
            reshape_content_panel,
        )
        try:
            wx.CallAfter(reshape_content_panel)
        except Exception:
            pass

        content_sizer = wx.BoxSizer(wx.VERTICAL)
        content_panel.SetSizer(content_sizer)

        card_sizer.Add(
            content_panel,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            _dip(card, UI_COLLAPSIBLE_CONTENT_INSET),
        )
        self._collapsible_settings_sections[label] = (
            header,
            content_sizer,
            content_panel,
        )
        header.Bind(
            wx.EVT_TOGGLEBUTTON,
            lambda event, section_label=label: self._on_collapsible_settings_section_toggled(
                event,
                section_label,
            ),
        )
        target_sizer = (
            parent_sizer
            if parent_sizer is not None
            else self.settings_sizer
        )
        target_sizer.Add(
            card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )
        self._update_collapsible_settings_section(label)
        return card, content_sizer

    def _build_labeled_choice(self, parent, sizer, label, choices, tooltip, icon_provider=None, show_icons=False):
        label_control = _make_text(parent, label, point_size=9, bold=True)
        self._set_control_tooltip(label_control, tooltip)
        sizer.Add(
            label_control,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        choice = ModernChoice(
            parent,
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

    def _build_slider_row(self, parent, value, minimum, maximum, box_width=58):
        row = wx.BoxSizer(wx.HORIZONTAL)
        slider = ModernSlider(parent, value=value, minValue=minimum, maxValue=maximum)
        text_box = ModernTextField(parent, value=str(value), width=box_width)
        row.Add(slider, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, _dip(parent, 8))
        row.Add(text_box, 0, wx.ALIGN_CENTER_VERTICAL)
        return row, slider, text_box

    def _add_checkbox(self, parent, sizer, attribute, label, value, tooltip):
        control = ModernCheckBox(parent, label, value)
        setattr(self, attribute, control)
        self._set_control_tooltip(control, tooltip)

        _tighten_gap_before_checkbox(sizer)
        sizer.Add(
            control,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        return control

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
        self._plugin_window = BlocksToStorageWindow(owner, self)
        root = wx.Panel(
            self._plugin_window,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(root, f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorageRoot")
        root.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["passive_window"])
        root_sizer = wx.BoxSizer(wx.HORIZONTAL)
        root.SetSizer(root_sizer)

        self._main_content_root = root
        self._main_content_panel = wx.Panel(
            root,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(
            self._main_content_panel,
            f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorageMainContent",
        )
        self._main_content_panel.SetBackgroundColour(
            BLOCKS_TO_STORAGE_THEME["passive_window"]
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
        header.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["passive_window"])
        header_sizer = wx.BoxSizer(wx.VERTICAL)
        header.SetSizer(header_sizer)
        title = _make_text(header, "BLOCKS TO STORAGE", point_size=18, bold=True)
        subtitle = _make_wrapped_text(
            header,
            "Organized storage, grouping, labeling, packing, and reporting",
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
        settings_host.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["passive_window"])
        settings_row = wx.BoxSizer(wx.HORIZONTAL)
        settings_host.SetSizer(settings_row)
        self.scroll = ModernScrollViewport(
            settings_host,
            background=BLOCKS_TO_STORAGE_THEME["passive_window"],
        )
        _mark_custom_ui_owned(
            self.scroll,
            f"{CUSTOM_UI_NAME_PREFIX}:BlocksToStorageSettings",
        )
        self.scroll.SetMinSize((-1, self.SETTINGS_VIEWPORT_HEIGHT))
        self.settings_content_panel = self.scroll.GetContentWindow()
        self.settings_panel = self.settings_content_panel
        self.settings_sizer = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetContentSizer(self.settings_sizer)
        self._collapsible_settings_sections = {}
        self.settings_sizer.AddSpacer(_dip(self.scroll, 4))

        storage_card, storage_sizer = self._create_card(
            self.settings_content_panel,
            "Storage Settings",
            "Choose the outer storage type, capacity and vertical arrangement.",
        )
        container_tip = (
            "Choose which storage block will hold the collected blocks. Chests "
            "support the double chest option. Barrels and shulker boxes use normal 27-slot storage."
        )
        self.storage_container_label, self.storage_choice = self._build_labeled_choice(
            storage_card,
            storage_sizer,
            "Storage container",
            (self.CONTAINER_CHEST, self.CONTAINER_BARREL, self.CONTAINER_SHULKER),
            container_tip,
            icon_provider=self._storage_icon_cache,
            show_icons=True,
        )
        self.show_storage_icons_cb = ModernCheckBox(
            storage_card,
            "Show visual storage selectors",
            True,
        )
        self._set_control_tooltip(
            self.show_storage_icons_cb,
            "Shows locally available storage artwork and shulker color swatches. "
            "Text-only selection remains available when disabled or when artwork is unavailable.",
        )
        _tighten_gap_before_checkbox(storage_sizer)
        storage_sizer.Add(
            self.show_storage_icons_cb,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        storage_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(storage_sizer)
        self.shulker_color_row = wx.BoxSizer(wx.VERTICAL)
        self.shulker_color_label = _make_text(
            storage_card,
            "Shulker color",
            point_size=9,
            bold=True,
        )
        self.shulker_color_choice = ModernChoice(
            storage_card,
            self.SHULKER_COLORS,
            icon_provider=self._storage_icon_cache,
            show_icons=True,
            icon_columns=SHULKER_SELECTOR_ICON_COLUMNS,
            icon_visible_rows=SHULKER_SELECTOR_VISIBLE_ROWS,
        )
        shulker_tip = "Choose the shulker box color. Default creates the normal undyed shulker box."
        self._set_control_tooltip(self.shulker_color_label, shulker_tip)
        self._set_control_tooltip(self.shulker_color_choice, shulker_tip)
        self.shulker_color_row.Add(
            self.shulker_color_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.shulker_color_row.Add(
            self.shulker_color_choice,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.shulker_color_row_item = storage_sizer.Add(
            self.shulker_color_row,
            0,
            wx.EXPAND,
        )
        self._add_checkbox(
            storage_card,
            storage_sizer,
            "use_double_chests",
            "Use double chests",
            False,
            "Only applies when Storage container is set to Chest. Uses connected double chests with 54 slots instead of single chests with 27 slots.",
        )
        self._double_chest_group_bottom_spacing = (
            _add_checkbox_group_bottom_spacing(storage_sizer)
        )
        self.stack_height_label = _make_text(
            storage_card,
            "Vertical stack height",
            point_size=9,
            bold=True,
        )
        stack_tip = "Controls how many storage blocks can stack vertically before the plugin starts a new line. Default is 8. Maximum is 40."
        self._set_control_tooltip(self.stack_height_label, stack_tip)
        storage_sizer.Add(
            self.stack_height_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.stack_height_row, self.stack_height, self.stack_height_box = self._build_slider_row(
            storage_card,
            self.DEFAULT_STACK_HEIGHT,
            1,
            self.MAX_STACK_HEIGHT,
        )
        self._set_control_tooltip(self.stack_height, stack_tip)
        self._set_control_tooltip(self.stack_height_box, stack_tip)
        storage_sizer.Add(
            self.stack_height_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.settings_sizer.Add(
            storage_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        export_card, export_sizer = self._create_card(
            self.settings_content_panel,
            "Export Behavior",
            "Control the order used when block groups are packed into storage.",
        )
        self._add_checkbox(
            export_card,
            export_sizer,
            "alphabetical_order",
            "ABC item order",
            True,
            "Sorts block types by their Minecraft Bedrock Edition display names before packing them into storage. Turning this off keeps first-seen scan order.",
        )
        _add_checkbox_group_bottom_spacing(export_sizer)
        self.settings_sizer.Add(
            export_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        groups_card, groups_sizer = self._create_card(
            self.settings_content_panel,
            "Separated Groups",
            "Keep block types in independent storage groups with optional labels and spacing.",
        )
        self._add_checkbox(
            groups_card,
            groups_sizer,
            "separate_types",
            "One block type per storage group",
            False,
            "Keeps each block type in its own storage group. Example: stone goes into its own containers, dirt goes into its own containers, and so on.",
        )
        self._add_checkbox(
            groups_card,
            groups_sizer,
            "add_group_item_frames",
            "Add item frames for separated groups",
            False,
            "Only works when One block type per storage group is enabled. Adds one regular item frame or glow item frame to the first storage container for each block type group.",
        )
        _add_checkbox_group_bottom_spacing(groups_sizer)
        self.group_spacing_label = _make_text(
            groups_card,
            "Spacing between separated groups",
            point_size=9,
            bold=True,
        )
        group_tip = "Controls the empty side space between separated block groups. Range is 0 to 8. Default is 1. Item frames reserve front space separately."
        self._set_control_tooltip(self.group_spacing_label, group_tip)
        groups_sizer.Add(
            self.group_spacing_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.group_spacing_row, self.group_spacing, self.group_spacing_box = self._build_slider_row(
            groups_card,
            self.DEFAULT_GROUP_SPACING,
            0,
            self.MAX_GROUP_SPACING,
        )
        self._set_control_tooltip(self.group_spacing, group_tip)
        self._set_control_tooltip(self.group_spacing_box, group_tip)
        self.group_spacing_row_item = groups_sizer.Add(
            self.group_spacing_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.settings_sizer.Add(
            groups_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        nested_card, nested_sizer = self._create_card(
            self.settings_content_panel,
            "Nested Shulker Storage",
            "Pack collected items into shulker-box items before placing them in outer storage.",
        )
        self._add_checkbox(
            nested_card,
            nested_sizer,
            "use_nested_shulker_storage",
            "Pack into shulker boxes inside storage",
            False,
            "Advanced. Puts collected blocks into shulker boxes, then puts those shulker boxes inside the generated storage containers.",
        )
        self._nested_shulker_group_bottom_spacing = (
            _add_checkbox_group_bottom_spacing(nested_sizer)
        )
        self.nested_shulker_mode_row = wx.BoxSizer(wx.VERTICAL)
        self.nested_shulker_mode_label = _make_text(
            nested_card,
            "Nested shulker mode",
            point_size=9,
            bold=True,
        )
        nested_mode_tip = "Balanced mode leaves small groups directly in storage and uses shulker boxes for large groups. Compact mode uses shulker boxes for almost every group."
        self.nested_shulker_mode_choice = ModernChoice(
            nested_card,
            (self.NESTED_SHULKER_MODE_PRACTICAL, self.NESTED_SHULKER_MODE_COMPACT),
        )
        self._set_control_tooltip(self.nested_shulker_mode_label, nested_mode_tip)
        self._set_control_tooltip(self.nested_shulker_mode_choice, nested_mode_tip)
        self.nested_shulker_mode_row.Add(
            self.nested_shulker_mode_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.nested_shulker_mode_row.Add(
            self.nested_shulker_mode_choice,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.nested_shulker_mode_row_item = nested_sizer.Add(
            self.nested_shulker_mode_row,
            0,
            wx.EXPAND,
        )
        self.nested_shulker_color_row = wx.BoxSizer(wx.VERTICAL)
        self.nested_shulker_color_label = _make_text(
            nested_card,
            "Nested shulker color",
            point_size=9,
            bold=True,
        )
        nested_color_tip = "Choose the color of the generated shulker boxes used inside storage containers. Default creates normal undyed shulker boxes."
        self.nested_shulker_color_choice = ModernChoice(
            nested_card,
            self.SHULKER_COLORS,
            icon_provider=self._storage_icon_cache,
            show_icons=True,
            icon_columns=SHULKER_SELECTOR_ICON_COLUMNS,
            icon_visible_rows=SHULKER_SELECTOR_VISIBLE_ROWS,
        )
        self._set_control_tooltip(self.nested_shulker_color_label, nested_color_tip)
        self._set_control_tooltip(self.nested_shulker_color_choice, nested_color_tip)
        self.nested_shulker_color_row.Add(
            self.nested_shulker_color_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.nested_shulker_color_row.Add(
            self.nested_shulker_color_choice,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.nested_shulker_color_row_item = nested_sizer.Add(
            self.nested_shulker_color_row,
            0,
            wx.EXPAND,
        )
        self.settings_sizer.Add(
            nested_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        _performance_card, performance_sizer = self._create_collapsible_card(
            self.settings_content_panel,
            "Performance",
            "Fast chunk paths remain enabled by default and safely fall back when needed.",
            expanded=True,
        )
        self._add_checkbox(
            self._collapsible_settings_sections["Performance"][2],
            performance_sizer,
            "fast_direct_scan",
            "Fast direct chunk scan",
            True,
            "Scans directly from chunk data instead of calling get_version_block for every selected block. This is much faster on large selections.",
        )
        self._add_checkbox(
            self._collapsible_settings_sections["Performance"][2],
            performance_sizer,
            "fast_direct_clear",
            "Fast direct chunk clear",
            True,
            "Clears directly in chunk data using one cached air block ID per chunk. If it fails, the plugin falls back to the safer clear method.",
        )
        _add_checkbox_group_bottom_spacing(performance_sizer)

        _safety_card, safety_sizer = self._create_collapsible_card(
            self.settings_content_panel,
            "Safety",
            "Keep survival-friendly defaults and protect large or bedrock-heavy selections.",
            expanded=True,
        )
        safety_parent = self._collapsible_settings_sections["Safety"][2]
        self._add_checkbox(
            safety_parent,
            safety_sizer,
            "include_unusual",
            "Include unusual blocks",
            False,
            "Includes technical or normally unobtainable block forms when they have a supported item representation. Leave disabled for normal survival-friendly exports.",
        )
        self._add_checkbox(
            safety_parent,
            safety_sizer,
            "preserve_bedrock",
            "Preserve bedrock",
            True,
            "Keeps bedrock blocks in the selected area instead of replacing them with air.",
        )
        self._add_checkbox(
            safety_parent,
            safety_sizer,
            "show_large_selection_warning",
            "Show large selection warning",
            True,
            "Shows a confirmation before running on selections estimated at 500,000 blocks or more.",
        )
        _add_checkbox_group_bottom_spacing(safety_sizer)

        display_card, display_sizer = self._create_card(
            self.settings_content_panel,
            "Display-Name Data",
            "Use local plugin and Minecraft language data for unresolved names and ABC ordering.",
        )
        self._add_checkbox(
            display_card,
            display_sizer,
            "use_found_entries_cache",
            f"Use plugin-created {self.FOUND_ENTRIES_FILENAME} cache",
            True,
            f"Uses previously saved entries from {self.FOUND_ENTRIES_FILENAME} independently of the installed language fallback.",
        )
        self._add_checkbox(
            display_card,
            display_sizer,
            "use_installed_language_data",
            "Use installed Minecraft en_US.lang as fallback",
            False,
            "Allows unresolved ABC display names and conservative scan-identity recovery to use a local Minecraft Bedrock Edition en_US.lang file during an operation.",
        )
        self._add_checkbox(
            display_card,
            display_sizer,
            "auto_detect_language_file",
            "Automatically detect the Minecraft language file",
            False,
            "Checks only known Minecraft for Windows installation locations on available drive letters. It does not recursively search drives.",
        )

        self._language_source_group_bottom_spacing = (
            _add_checkbox_group_bottom_spacing(display_sizer)
        )
        self.language_file_row = wx.BoxSizer(wx.VERTICAL)
        self.language_file_label = _make_text(
            display_card,
            "Language file",
            point_size=9,
            bold=True,
        )
        language_tip = "Path to the Minecraft Bedrock Edition en_US.lang file used for unresolved display names."
        self._set_control_tooltip(self.language_file_label, language_tip)
        self.language_file_row.Add(
            self.language_file_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        path_row = wx.BoxSizer(wx.HORIZONTAL)
        self.language_file_path = ModernTextField(
            display_card,
            value=str(Path("C:/") / self.DEFAULT_MINECRAFT_LANGUAGE_RELATIVE_PATH),
            width=260,
            center=False,
            large=False,
        )
        self.browse_language_file_button = ModernButton(
            display_card,
            "Browse...",
            compact=True,
        )
        self._set_control_tooltip(self.language_file_path, language_tip)
        self._set_control_tooltip(
            self.browse_language_file_button,
            "Select the Minecraft Bedrock Edition en_US.lang file manually.",
        )
        path_row.Add(self.language_file_path, 1, wx.RIGHT | wx.EXPAND, _dip(display_card, 8))
        path_row.Add(self.browse_language_file_button, 0, wx.EXPAND)
        self.language_file_row.Add(
            path_row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.language_file_row_item = display_sizer.Add(
            self.language_file_row,
            0,
            wx.EXPAND,
        )
        self._add_checkbox(
            display_card,
            display_sizer,
            "save_found_language_entries",
            f"Keep {self.FOUND_ENTRIES_FILENAME} updated from en_US.lang",
            False,
            f"Scans the configured language file before each operation and atomically adds safe missing display-name entries to {self.FOUND_ENTRIES_FILENAME}.",
        )
        self._add_checkbox(
            display_card,
            display_sizer,
            "simulate_missing_display_name",
            "Simulate missing embedded display-name entry",
            False,
            "Diagnostic simulation. Makes one item behave as though its embedded display-name entry is missing.",
        )
        _add_checkbox_group_bottom_spacing(display_sizer)
        self.simulated_missing_alias_row = wx.BoxSizer(wx.VERTICAL)
        self.simulated_missing_alias_label = _make_text(
            display_card,
            "Entry alias to ignore",
            point_size=9,
            bold=True,
        )
        alias_tip = (
            "Internal item alias omitted by the diagnostic simulation, for example "
            "oak_log. Only one alias is supported."
        )
        self.simulated_missing_alias = ModernTextField(
            display_card,
            value="oak_log",
            width=180,
            center=False,
            large=False,
        )
        self._set_control_tooltip(self.simulated_missing_alias_label, alias_tip)
        self._set_control_tooltip(self.simulated_missing_alias, alias_tip)
        self.simulated_missing_alias_row.Add(
            self.simulated_missing_alias_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        self.simulated_missing_alias_row.Add(
            self.simulated_missing_alias,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.simulated_missing_alias_row_item = display_sizer.Add(
            self.simulated_missing_alias_row,
            0,
            wx.EXPAND,
        )
        self.settings_sizer.Add(
            display_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        conversion_card, conversion_sizer = self._create_card(
            self.settings_content_panel,
            "Conversion Data",
            "Optional reviewed local rules run after built-in state-aware conversion logic.",
        )
        self._add_checkbox(
            conversion_card,
            conversion_sizer,
            "use_conversion_entries",
            f"Use plugin-created {self.CONVERSION_ENTRIES_FILENAME} rules",
            True,
            f"Reads reviewed local block-to-item rules from {self.CONVERSION_ENTRIES_FILENAME}. Built-in verified conversions keep priority.",
        )
        _add_checkbox_group_bottom_spacing(conversion_sizer)
        self.settings_sizer.Add(
            conversion_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        _diagnostics_card, diagnostics_sizer = self._create_collapsible_card(
            self.settings_content_panel,
            "Diagnostics",
            "Optional local report detail and controlled conversion simulations.",
            expanded=False,
        )
        diagnostics_parent = self._collapsible_settings_sections["Diagnostics"][2]
        self._add_checkbox(
            diagnostics_parent,
            diagnostics_sizer,
            "include_item_frame_audit",
            "Include item frame label audit in report",
            False,
            "Adds detailed item-frame label diagnostics to the export report. Leave disabled during normal use.",
        )
        self._add_checkbox(
            diagnostics_parent,
            diagnostics_sizer,
            "include_display_name_audit",
            "Include display-name ABC audit in report",
            False,
            "Adds display-name and ABC sorting diagnostics without changing conversion or placement.",
        )
        self._add_checkbox(
            diagnostics_parent,
            diagnostics_sizer,
            "use_reviewed_amulet_normalization",
            "Use plugin-reviewed conversion fallback",
            True,
            "Lets the plugin use only built-in conversion fallbacks individually "
            "reviewed against Amulet conversion behavior.",
        )
        self._add_checkbox(
            diagnostics_parent,
            diagnostics_sizer,
            "record_conversion_candidates",
            f"Record inactive candidates to {self.CONVERSION_CANDIDATES_FILENAME}",
            False,
            "Records inactive conversion observations in a local candidate file. Candidates never change exports or active conversion rules.",
        )
        self._add_checkbox(
            diagnostics_parent,
            diagnostics_sizer,
            "attempt_unresolved_item_writes",
            "Attempt unresolved item writes",
            False,
            "Diagnostic simulation. Allows unresolved generic identifiers to be written so ghost or empty results can be located in-game.",
        )
        _add_checkbox_group_bottom_spacing(diagnostics_sizer)
        _advanced_card, advanced_sizer = self._create_collapsible_card(
            diagnostics_parent,
            "Advanced Diagnostics",
            "Bounded read-only Amulet capability and comparison reports.",
            expanded=False,
            parent_sizer=diagnostics_sizer,
        )
        advanced_parent = self._collapsible_settings_sections["Advanced Diagnostics"][2]
        self._add_checkbox(
            advanced_parent,
            advanced_sizer,
            "include_amulet_conversion_diagnostic",
            "Include Amulet conversion capability diagnostic in report",
            False,
            "Adds a local read-only report section showing whether Amulet can translate known block identities into item-capable forms.",
        )
        self._add_checkbox(
            advanced_parent,
            advanced_sizer,
            "include_amulet_translator_probe",
            "Include Amulet translator validation probe in report",
            False,
            "Runs a local read-only validation probe against Amulet's block and item translators.",
        )
        self._add_checkbox(
            advanced_parent,
            advanced_sizer,
            "include_amulet_conversion_audit",
            "Include Amulet conversion comparison audit in report",
            False,
            "Reports which resolver layer chose each final item and compares generic identifiers with Amulet normalization candidates.",
        )
        self._add_checkbox(
            advanced_parent,
            advanced_sizer,
            "record_all_conversion_observations",
            "Record all resolved conversion observations",
            False,
            "Advanced diagnostic recording. Records state-aware observations even "
            "when a verified built-in resolver already handles the source family.",
        )
        _add_checkbox_group_bottom_spacing(advanced_sizer)
        files_card, files_sizer = self._create_card(
            self.settings_content_panel,
            "Plugin Files",
            "Manage settings and optional Blocks to Storage data files without affecting worlds or unrelated files.",
        )
        self.manage_plugin_files_button = ModernButton(
            files_card,
            "Manage Plugin Files...",
        )
        self._set_control_tooltip(
            self.manage_plugin_files_button,
            "Create, delete, open, reset, repair, import, export, or update the files owned by Blocks to Storage.",
        )
        files_sizer.Add(
            self.manage_plugin_files_button,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        self.settings_sizer.Add(
            files_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )
        self.settings_sizer.AddSpacer(_dip(self.scroll, 4))

        settings_row.Add(self.scroll, 1, wx.EXPAND)
        self.settings_scrollbar = ModernScrollBar(settings_host, self.scroll)
        settings_row.Add(
            self.settings_scrollbar,
            0,
            wx.RIGHT | wx.TOP | wx.BOTTOM | wx.EXPAND,
            _dip(settings_host, 6),
        )
        main_content_sizer.Add(
            settings_host,
            self.SETTINGS_GROW_PROPORTION,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            _dip(root, 4),
        )
        self.scroll.Bind(wx.EVT_SCROLLWIN, self._on_settings_scroll)
        self.scroll.Bind(wx.EVT_MOUSEWHEEL, self._on_settings_scroll)

        footer = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(footer)
        footer.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["passive_window"])
        footer_sizer = wx.BoxSizer(wx.VERTICAL)
        footer.SetSizer(footer_sizer)

        status_card = RoundedPanel(
            footer,
            background=BLOCKS_TO_STORAGE_THEME["passive_surface_alt"],
            border=BLOCKS_TO_STORAGE_THEME["passive_border"],
            radius=10,
        )
        status_sizer = wx.BoxSizer(wx.HORIZONTAL)
        status_card.SetSizer(status_sizer)
        status_caption = _make_text(status_card, "STATUS", point_size=8, bold=True, muted=True)
        self.status = _make_text(status_card, "Ready", point_size=9)
        self._set_control_tooltip(
            self.status,
            "Shows the current operation state and most recent result.",
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
        self.run_export_button = ModernButton(footer, "Scan & Store", primary=True)
        self.run_export_button.ProtectFromExternalDisable(True)
        self._set_control_tooltip(
            self.run_export_button,
            "Scans the selected area, counts exportable blocks and resulting items, clears the selected blocks, and places the collected items into the chosen storage type.",
        )
        action_row.Add(
            self.run_export_button,
            2,
            wx.RIGHT | wx.EXPAND,
            _dip(footer, 8),
        )
        self.save_report_button = ModernButton(footer, "Save Report")
        self.save_report_button.ProtectFromExternalDisable(True)
        self.save_report_button.SetAvailable(False)
        self._set_control_tooltip(
            self.save_report_button,
            "Saves the latest export report as a UTF-8 text file.",
        )
        action_row.Add(
            self.save_report_button,
            1,
            wx.RIGHT | wx.EXPAND,
            _dip(footer, 8),
        )
        self.console_toggle_button = ModernButton(footer, "Hide Console", compact=True)
        self._set_control_tooltip(
            self.console_toggle_button,
            "Hide or show the report console without clearing its content.",
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
            background=BLOCKS_TO_STORAGE_THEME["console_bg"],
            border=BLOCKS_TO_STORAGE_THEME["border"],
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
        self.text.SetForegroundColour(BLOCKS_TO_STORAGE_THEME["console_text"])
        self.text.SetBackgroundColour(BLOCKS_TO_STORAGE_THEME["console_bg"])
        try:
            wx.CallAfter(_try_apply_dark_native_theme, self.text)
        except Exception:
            pass
        try:
            self.text.SetFont(
                wx.Font(
                    9,
                    wx.FONTFAMILY_TELETYPE,
                    wx.FONTSTYLE_NORMAL,
                    wx.FONTWEIGHT_NORMAL,
                )
            )
        except Exception:
            pass
        self.text.SetMinSize(
            (_dip(self.console_card, 340), _dip(self.console_card, self.CONSOLE_MIN_TEXT_HEIGHT))
        )
        self.console_card.SetMinSize((-1, _dip(root, self.CONSOLE_MIN_CARD_HEIGHT)))
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

        self._bind_integer_slider_and_text(
            self.stack_height,
            self.stack_height_box,
            1,
            self.MAX_STACK_HEIGHT,
        )
        self._bind_integer_slider_and_text(
            self.group_spacing,
            self.group_spacing_box,
            0,
            self.MAX_GROUP_SPACING,
        )
        self.storage_choice.Bind(wx.EVT_CHOICE, self._on_storage_choice_changed)
        self.separate_types.Bind(wx.EVT_CHECKBOX, self._on_separate_types_changed)
        self.use_nested_shulker_storage.Bind(
            wx.EVT_CHECKBOX,
            self._on_nested_shulker_storage_changed,
        )
        self.use_found_entries_cache.Bind(
            wx.EVT_CHECKBOX,
            self._on_display_name_dependency_changed,
        )
        self.use_installed_language_data.Bind(
            wx.EVT_CHECKBOX,
            self._on_installed_language_data_changed,
        )
        self.auto_detect_language_file.Bind(
            wx.EVT_CHECKBOX,
            self._on_auto_detect_language_file_changed,
        )
        self.save_found_language_entries.Bind(
            wx.EVT_CHECKBOX,
            self._on_display_name_dependency_changed,
        )
        self.simulate_missing_display_name.Bind(
            wx.EVT_CHECKBOX,
            self._on_simulate_missing_display_name_changed,
        )
        self.show_storage_icons_cb.Bind(
            wx.EVT_CHECKBOX,
            self._on_storage_icon_visibility_changed,
        )
        self.browse_language_file_button.Bind(wx.EVT_BUTTON, self._browse_for_language_file)
        self.run_export_button.Bind(wx.EVT_BUTTON, self._run_export)
        self.manage_plugin_files_button.Bind(wx.EVT_BUTTON, self._manage_plugin_files)
        self.save_report_button.Bind(wx.EVT_BUTTON, self._save_last_report)

        for target in (console_title, self.console_card, self.text):
            target.Bind(wx.EVT_ENTER_WINDOW, self._on_console_help_enter)
            target.Bind(wx.EVT_LEAVE_WINDOW, self._on_console_help_leave)
        for event_binder in (wx.EVT_LEFT_DOWN, wx.EVT_SET_FOCUS, wx.EVT_KEY_DOWN):
            self.text.Bind(event_binder, self._on_console_text_interaction)

        self._update_floating_minimum_size(resize_if_needed=True)
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(root, 1, wx.EXPAND)
        self._plugin_window.SetSizer(frame_sizer)
        self._plugin_window.Layout()
        self._sync_main_content_width()
        self._sync_settings_viewport()

    def _bind_integer_slider_and_text(self, slider, text_box, minimum, maximum):
        def from_slider(event=None):
            text_box.ChangeValue(str(slider.GetValue()))
            self._schedule_settings_config_save(event)

        def from_text(event=None):
            try:
                value = int(text_box.GetValue().strip())
            except Exception:
                try:
                    if event is not None:
                        event.Skip()
                except Exception:
                    pass
                return
            value = max(int(minimum), min(int(maximum), value))
            slider.SetValue(value)
            self._schedule_settings_config_save(event)

        def settle(_event=None):
            try:
                value = int(text_box.GetValue().strip())
            except Exception:
                value = slider.GetValue()
            value = max(int(minimum), min(int(maximum), value))
            slider.SetValue(value)
            text_box.ChangeValue(str(value))
            self._schedule_settings_config_save()

        slider.Bind(wx.EVT_SLIDER, from_slider)
        text_box.Bind(wx.EVT_TEXT, from_text)
        text_box.Bind(wx.EVT_TEXT_ENTER, settle)
        text_box.Bind(wx.EVT_KILL_FOCUS, settle)

    def _show_plugin_window(self, _event=None):
        window = self._plugin_window
        if window is None or self._destroying:
            return
        try:
            if window.IsIconized():
                window.Iconize(False)
            if not window.IsShown():
                window.Show()
                if not self._window_has_been_shown:
                    self._position_plugin_window_at_amulet_edge()
                    self._window_has_been_shown = True
            window.Raise()
            window.SetFocus()
            self._update_launcher_status(True)
            self._refresh_floating_layout()
        except Exception:
            pass

    def _position_plugin_window_at_amulet_edge(self):
        window = self._plugin_window
        if window is None:
            return
        try:
            owner = window.GetParent() or wx.GetTopLevelParent(self) or self
            owner_rect = owner.GetScreenRect()
            window_size = window.GetSize()
            desired_x = int(owner_rect.x - window_size.width / 2)
            desired_y = int(owner_rect.y + (owner_rect.height - window_size.height) / 2)
        except Exception:
            try:
                window.CentreOnParent()
            except Exception:
                window.CentreOnScreen()
            return
        try:
            display_index = wx.Display.GetFromWindow(owner)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            work_area = wx.Display(display_index).GetClientArea()
            max_x = work_area.x + max(0, work_area.width - window_size.width)
            max_y = work_area.y + max(0, work_area.height - window_size.height)
            desired_x = max(work_area.x, min(desired_x, max_x))
            desired_y = max(work_area.y, min(desired_y, max_y))
        except Exception:
            pass
        try:
            window.SetPosition((desired_x, desired_y))
        except Exception:
            pass

    def _update_launcher_status(self, is_open):
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

    def _bind_floating_window_geometry_events(self):
        window = self._plugin_window
        if window is None or self._window_geometry_events_ready:
            return
        try:
            window.Bind(wx.EVT_SIZE, self._on_plugin_window_size)
            self._window_geometry_events_ready = True
        except Exception:
            self._window_geometry_events_ready = False

    def _on_plugin_window_size(self, event):
        try:
            event.Skip()
        except Exception:
            pass
        window = self._plugin_window
        if window is None:
            return
        try:
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
        window = self._plugin_window
        if window is None:
            return list(self._last_normal_window_size)
        try:
            if window.IsIconized() or window.IsMaximized():
                return list(self._last_normal_window_size)
            size = window.GetSize()
            minimum_width, minimum_height = self._current_floating_minimum_size()
            self._last_normal_window_size = [
                max(minimum_width, int(size.width)),
                max(minimum_height, int(size.height)),
            ]
        except Exception:
            pass
        return list(self._last_normal_window_size)

    def _apply_saved_window_size(self, data):
        window = self._plugin_window
        if window is None or not isinstance(data, dict):
            return
        ui_data = data.get("ui", {})
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
        try:
            width = max(MANAGE_DIALOG_MIN_SIZE[0], int(self._last_manage_dialog_size[0]))
            height = max(MANAGE_DIALOG_MIN_SIZE[1], int(self._last_manage_dialog_size[1]))
            self._last_manage_dialog_size = [width, height]
        except Exception:
            self._last_manage_dialog_size = list(MANAGE_DIALOG_DEFAULT_SIZE)
        return list(self._last_manage_dialog_size)

    def _remember_manage_dialog_size(self, dialog):
        if dialog is None or self._settings_config_applying:
            return
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
        if not isinstance(data, dict):
            return
        ui_data = data.get("ui", {})
        if not isinstance(ui_data, dict):
            return
        saved_size = ui_data.get("manage_window_size")
        if (
            not isinstance(saved_size, (list, tuple))
            or len(saved_size) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in saved_size)
        ):
            return
        self._last_manage_dialog_size = [
            max(MANAGE_DIALOG_MIN_SIZE[0], int(saved_size[0])),
            max(MANAGE_DIALOG_MIN_SIZE[1], int(saved_size[1])),
        ]

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
            window.SetMinSize((_dip(window, minimum_width), _dip(window, minimum_height)))
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

    def _apply_saved_console_visibility(self, data):
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
        self._console_visible = not self._console_visible
        self.console_card.Show(self._console_visible)
        self.console_toggle_button.SetLabel(
            "Hide Console" if self._console_visible else "Show Console"
        )
        self._hide_console_help()
        self._update_floating_minimum_size(resize_if_needed=self._console_visible)
        self._refresh_floating_layout()
        self._schedule_settings_config_save()

    def _on_storage_icon_visibility_changed(self, event=None):
        show_icons = bool(self.show_storage_icons_cb.GetValue())
        for choice in (
            self.storage_choice,
            self.shulker_color_choice,
            self.nested_shulker_color_choice,
        ):
            try:
                choice.SetShowIcons(show_icons)
            except Exception:
                pass
        self._refresh_floating_layout()
        self._schedule_settings_config_save(event)

    def _on_settings_scroll(self, event):
        try:
            event.Skip()
        except Exception:
            pass
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
                    pass
        try:
            scroll.Update()
        except Exception:
            pass

    def _sync_settings_viewport(self):
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
        try:
            self._sync_settings_viewport()
        except Exception:
            pass
        try:
            self._plugin_window.Layout()
            self._plugin_window.Refresh(False)
        except Exception:
            pass

    def _begin_operation_ui(self):
        if self._operation_running:
            return self._operation_ui_generation
        self._set_tooltips_suspended(True)
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
            self.run_export_button.SetAvailable(True)
            self.run_export_button.SetLabel("Processing...")
            self.run_export_button.SetBusy(True)
            self.status.SetLabel("Scanning and preparing storage...")
        except Exception:
            pass
        return generation

    def _restore_operation_buttons(self, generation):
        if self._destroying or generation != self._operation_ui_generation or self._operation_running:
            return
        try:
            self.run_export_button.SetAvailable(True)
            self.run_export_button.SetBusy(False)
            self.run_export_button.SetLabel("Scan & Store")
            self.run_export_button.Refresh(False)
            self.run_export_button.Update()
        except Exception:
            pass
        try:
            self.save_report_button.SetAvailable(bool(self._last_report_text))
        except Exception:
            pass

    def _finish_operation_ui(self, status_label, generation):
        if self._destroying or generation != self._operation_ui_generation:
            return
        self._operation_running = False

        self._set_tooltips_suspended(True)
        try:
            self.status.SetLabel(status_label)
        except Exception:
            pass
        self._restore_operation_buttons(generation)
        self._schedule_operation_button_restore(generation, 0)
        self._set_tooltips_suspended(False)

    def _schedule_operation_button_restore(self, generation, attempt):
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
        self._operation_button_restore_call = None
        if self._destroying or generation != self._operation_ui_generation or self._operation_running:
            return
        self._restore_operation_buttons(generation)
        self._schedule_operation_button_restore(generation, attempt + 1)

    def _on_host_destroy(self, event):
        try:
            if event.GetEventObject() is not self:
                event.Skip()
                return
        except Exception:
            pass
        self._destroying = True
        pending = self._operation_button_restore_call
        self._operation_button_restore_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass
        pending = self._scroll_refresh_call
        self._scroll_refresh_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass
        try:
            pending_save = self._settings_config_save_call
            self._settings_config_save_call = None
            if pending_save is not None:
                pending_save.Stop()
        except Exception:
            pass
        self._hide_control_help()
        if self._control_help_window is not None:
            try:
                self._control_help_window.Destroy()
            except Exception:
                pass
            self._control_help_window = None
        self._hide_console_help()
        if self._console_help_window is not None:
            try:
                self._console_help_window.Destroy()
            except Exception:
                pass
            self._console_help_window = None
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

    def _tooltip_targets(self, window):
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
        if window is None or not str(text).strip():
            return
        tooltip_text = str(text)
        root_ref = weakref.ref(window)
        for target in self._tooltip_targets(window):
            try:
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

    def _set_tooltips_suspended(self, suspended):
        self._tooltips_suspended = bool(suspended)
        if self._tooltips_suspended:
            self._console_help_hovered = False
            self._hide_control_help()
            self._hide_console_help()

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
                self._console_help_window.Hide()
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
            wx.ToolTip.SetAutoPop(28000)
            wx.ToolTip.SetReshow(250)
        except Exception:
            pass

    def _on_collapsible_settings_section_toggled(self, event, label: str) -> None:
        self._update_collapsible_settings_section(label)
        if label == "Diagnostics":
            self._update_collapsible_settings_section("Advanced Diagnostics")
        self._schedule_settings_config_save()
        try:
            event.Skip()
        except Exception:
            pass

    def _update_collapsible_settings_section(self, label: str) -> None:
        section = self._collapsible_settings_sections.get(label)
        if section is None:
            return
        header = section[0]
        content_sizer = section[1]
        content_panel = section[2] if len(section) > 2 else None
        expanded = bool(header.GetValue())
        try:
            header.SetSectionLabel(label)
        except Exception:
            header.SetLabel(("▼ " if expanded else "▶ ") + label)
        try:
            content_sizer.ShowItems(expanded)
            if content_panel is not None:
                _set_window_sizer_item_visible(content_panel, expanded)
            if label == "Diagnostics" and expanded:
                child = self._collapsible_settings_sections.get("Advanced Diagnostics")
                if child is not None:
                    child_panel = child[2] if len(child) > 2 else None
                    if child_panel is not None:
                        _set_window_sizer_item_visible(
                            child_panel,
                            bool(child[0].GetValue()),
                        )
        except Exception:
            pass
        self._refresh_floating_layout()

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

    def _get_scan_identity_property_values(self, block) -> List[str]:
        properties = getattr(block, "properties", None) or {}
        ignored_values = {
            "", "0", "1", "2", "3", "4", "5", "6", "7",
            "8", "9", "10", "11", "12", "13", "14", "15",
            "true", "false", "top", "bottom", "upper", "lower",
            "north", "south", "east", "west", "none", "single",
            "double", "normal", "open", "closed",
        }

        values: List[str] = []
        seen = set()
        try:
            property_items = properties.items()
        except Exception:
            property_items = []

        for _property_name, raw_value in property_items:
            value = self._normalize_state_text(raw_value)
            value = self._normalize_language_alias(value)
            if not value or value in ignored_values or value in seen:
                continue
            if not re.fullmatch(r"[a-z0-9_]+", value):
                continue
            seen.add(value)
            values.append(value)

        return values

    def _is_double_slab_state(
        self,
        block,
        block_key: Optional[str] = None,
    ) -> bool:
        normalized_key = self._normalize_conversion_identifier(
            block_key or self._get_namespaced_block_name(block) or ""
        )
        if normalized_key is not None:
            base_name = normalized_key.split(":", 1)[1]
            if "double" in base_name and "slab" in base_name:
                return True

        properties = getattr(block, "properties", None) or {}
        try:
            property_items = properties.items()
        except Exception:
            property_items = []

        for raw_property_name, raw_property_value in property_items:
            property_name = self._normalize_language_alias(
                self._normalize_state_text(raw_property_name)
            )
            property_value = self._normalize_language_alias(
                self._normalize_state_text(raw_property_value)
            )
            if (
                property_name in {"type", "slab_type", "minecraft:slab_type"}
                and property_value == "double"
            ):
                return True

        return False

    def _get_scan_identity_family_suffixes(
        self,
        raw_block,
        raw_scan_key: Optional[str],
        safe_item_key: Optional[str],
    ) -> List[str]:
        base_names = []
        for value in (raw_scan_key, safe_item_key):
            if not value:
                continue
            base_name = str(value).split(":", 1)[-1]
            if base_name not in base_names:
                base_names.append(base_name)

        slab_family_present = any("slab" in base_name for base_name in base_names)
        if slab_family_present and self._is_double_slab_state(
            raw_block,
            raw_scan_key,
        ):
            return ["double_slab"]

        suffixes: List[str] = []
        for base_name in base_names:
            if "double" in base_name and "slab" in base_name:
                if "double_slab" not in suffixes:
                    suffixes.append("double_slab")
                continue
            if "slab" in base_name and "slab" not in suffixes:
                suffixes.append("slab")
            if "stairs" in base_name and "stairs" not in suffixes:
                suffixes.append("stairs")
            if (
                base_name == "wall"
                or base_name.endswith("_wall")
                or "wall_block" in base_name
            ) and "wall" not in suffixes:
                suffixes.append("wall")

        return suffixes

    def _get_scan_identity_source(self, alias: str) -> str:
        alias = self._normalize_language_alias(alias)
        if not alias:
            return ""

        if alias in self.INTEGRATED_SCAN_IDENTITY_BLOCK_ALIASES:
            result = self.BEDROCK_EN_US_DISPLAY_NAMES.get(alias)
            if result is not None:
                language_key, _display_name = result
                if str(language_key).startswith(("tile.", "block.")):
                    return self.BUILT_IN_INTEGRATED_SOURCE_LABEL

        if self.use_found_entries_cache.GetValue():
            result = self._found_entries_aliases.get(alias)
            if result is not None:
                language_key, _display_name = result
                if str(language_key).startswith(("tile.", "block.")):
                    return self.FOUND_ENTRIES_FILENAME

        if self.use_installed_language_data.GetValue():
            result = self._external_language_aliases.get(alias)
            if result is not None:
                language_key, _display_name = result
                if str(language_key).startswith(("tile.", "block.")):
                    return self.INSTALLED_LANGUAGE_SOURCE_LABEL

        return ""

    def _get_scan_identity_material_variants(self, raw_block) -> Set[str]:
        variants: Set[str] = set()

        for material_value in self._get_scan_identity_property_values(raw_block):
            variants.add(material_value)

            if material_value.endswith("_bricks"):
                variants.add(
                    material_value[:-len("_bricks")] + "_brick"
                )

        return variants

    def _scan_identity_item_matches_material(
        self,
        item_key: Optional[str],
        material_variants: Set[str],
    ) -> bool:
        normalized_key = self._normalize_conversion_identifier(
            item_key or ""
        )
        if normalized_key is None or not material_variants:
            return False

        item_alias = normalized_key.split(":", 1)[1]
        item_material = item_alias

        for suffix in ("double_slab", "slab", "stairs", "wall"):
            suffix_text = "_" + suffix
            if item_material.endswith(suffix_text):
                item_material = item_material[:-len(suffix_text)]
                break

        item_tokens = {
            token
            for token in item_material.split("_")
            if token
        }

        for material_variant in material_variants:
            material_variant = self._normalize_language_alias(
                material_variant
            )
            if not material_variant:
                continue

            if (
                item_material == material_variant
                or item_material.endswith("_" + material_variant)
                or item_material.startswith(material_variant + "_")
            ):
                return True

            material_tokens = {
                token
                for token in material_variant.split("_")
                if token
            }
            if material_tokens and material_tokens.issubset(item_tokens):
                return True

        return False

    def _should_apply_scan_identity(
        self,
        raw_block,
        safe_item_key: Optional[str],
        candidate_item_key: Optional[str],
        *,
        direct_identity: bool = False,
    ) -> bool:
        candidate_key = self._normalize_conversion_identifier(
            candidate_item_key or ""
        )
        if candidate_key is None:
            return False

        safe_key = self._normalize_conversion_identifier(
            safe_item_key or ""
        )
        if safe_key is None:
            return True

        if candidate_key == safe_key:
            return False

        candidate_alias = candidate_key.split(":", 1)[1]
        safe_alias = safe_key.split(":", 1)[1]

        if (
            self._is_double_slab_state(raw_block)
            and candidate_alias.endswith("_double_slab")
            and not safe_alias.endswith("_double_slab")
        ):
            return True

        if direct_identity:
            return True

        if (
            safe_key in self.GENERIC_UNSAFE_ITEM_BLOCKS
            or not self._is_safe_item_key(safe_key)
        ):
            return True

        material_variants = self._get_scan_identity_material_variants(
            raw_block
        )
        if not material_variants:
            return False

        if self._scan_identity_item_matches_material(
            safe_key,
            material_variants,
        ):
            return False

        return True

    def _resolve_scan_identity(
        self,
        raw_block,
        raw_scan_key: Optional[str],
        safe_item_key: Optional[str],
    ) -> Tuple[Optional[str], str]:
        external_sources_enabled = getattr(
            self,
            "_operation_external_scan_identity_enabled",
            None,
        )
        if external_sources_enabled is None:
            external_sources_enabled = (
                self.use_found_entries_cache.GetValue()
                or self.use_installed_language_data.GetValue()
            )
        if external_sources_enabled:
            self._ensure_external_language_data_loaded()

        if (
            not self.INTEGRATED_SCAN_IDENTITY_BLOCK_ALIASES
            and not self._found_entries_aliases
            and not self._external_language_aliases
        ):
            return None, ""

        raw_key = self._normalize_conversion_identifier(raw_scan_key or "")
        if raw_key is not None:
            raw_alias = raw_key.split(":", 1)[1]
            source = self._get_scan_identity_source(raw_alias)
            if (
                source
                and self._is_safe_conversion_source_key(raw_key)
                and self._is_safe_item_key(raw_key)
                and self._should_apply_scan_identity(
                    raw_block,
                    safe_item_key,
                    raw_key,
                    direct_identity=True,
                )
            ):
                return raw_key, source

        suffixes = self._get_scan_identity_family_suffixes(
            raw_block,
            raw_scan_key,
            safe_item_key,
        )
        if not suffixes:
            return None, ""

        candidate_aliases = set()
        for material_value in self._get_scan_identity_property_values(raw_block):
            material_variants = {material_value}
            if material_value.endswith("_bricks"):
                material_variants.add(
                    material_value[:-len("_bricks")] + "_brick"
                )

            for material_variant in material_variants:
                for suffix in suffixes:
                    if material_variant.endswith("_" + suffix):
                        candidate_aliases.add(material_variant)
                    else:
                        candidate_aliases.add(
                            f"{material_variant}_{suffix}"
                        )

        matched_items: Dict[str, str] = {}
        for alias in sorted(candidate_aliases):
            source = self._get_scan_identity_source(alias)
            if not source:
                continue

            item_key = self._normalize_conversion_identifier(
                f"minecraft:{alias}"
            )
            if item_key is None or not self._is_safe_item_key(item_key):
                continue

            matched_items.setdefault(item_key, source)

        if len(matched_items) == 1:
            item_key, source = next(iter(matched_items.items()))
            if self._should_apply_scan_identity(
                raw_block,
                safe_item_key,
                item_key,
            ):
                return item_key, source
        return None, ""

    def _format_scan_identity_properties(self, block) -> str:
        try:
            properties = getattr(block, "properties", None) or {}
            parts = []
            for property_name in sorted(properties, key=lambda value: str(value)):
                property_value = self._tag_to_python_value(
                    properties[property_name]
                )
                parts.append(f"{property_name}={property_value}")
            text = "; ".join(parts) or "(none)"
        except Exception:
            text = "(unavailable)"
        return self._safe_conversion_diagnostic_text(text, 300)

    def _record_scan_identity_result(
        self,
        raw_block,
        raw_scan_key: Optional[str],
        safe_block,
        safe_item_key: Optional[str],
        recovered_item_key: Optional[str],
        recovery_source: str = "",
    ) -> None:
        raw_name = str(raw_scan_key or "<unknown>")
        safe_name = str(safe_item_key or "<none>")
        recovered_name = str(recovered_item_key or "<none>")

        if recovered_item_key:
            recovery_key = (raw_name, safe_name, recovered_name)
            if recovery_source == self.BUILT_IN_INTEGRATED_SOURCE_LABEL:
                self._built_in_scan_identity_recoveries[recovery_key] += 1
            elif recovery_source == self.INSTALLED_LANGUAGE_SOURCE_LABEL:
                self._installed_language_scan_identity_recoveries[
                    recovery_key
                ] += 1
            else:
                self._found_entry_scan_identity_recoveries[
                    recovery_key
                ] += 1

        if raw_name == safe_name and not recovered_item_key:
            return

        signature = (
            raw_name,
            self._format_scan_identity_properties(raw_block),
            safe_name,
            self._format_scan_identity_properties(safe_block),
            recovery_source or "<none>",
            recovered_name,
        )
        if (
            signature not in self._scan_identity_diagnostics
            and len(self._scan_identity_diagnostics)
            >= self.MAX_FOUND_ENTRY_SCAN_IDENTITY_DETAILS
        ):
            self._scan_identity_diagnostic_overflow += 1
            return
        self._scan_identity_diagnostics[signature] += 1

    def _log_scan_identity_summary(self) -> None:
        built_in_total = sum(
            self._built_in_scan_identity_recoveries.values()
        )
        found_entries_total = sum(
            self._found_entry_scan_identity_recoveries.values()
        )
        installed_language_total = sum(
            self._installed_language_scan_identity_recoveries.values()
        )
        external_total = found_entries_total + installed_language_total
        recovered_total = built_in_total + external_total

        self._log(f"Scan identities recovered: {recovered_total:,}")
        self._log(
            f"Built-in integrated identities recovered: {built_in_total:,}"
        )
        self._log(
            f"External language scan identities recovered: {external_total:,}"
        )
        self._log(
            f"Found Entries-assisted identities recovered: "
            f"{found_entries_total:,}"
        )
        self._log(
            f"Installed language-assisted identities recovered: "
            f"{installed_language_total:,}"
        )

        if recovered_total:
            self._log("Recovered scan identities:")
            for source_label, recoveries in (
                (
                    self.BUILT_IN_INTEGRATED_SOURCE_LABEL,
                    self._built_in_scan_identity_recoveries,
                ),
                (
                    self.FOUND_ENTRIES_FILENAME,
                    self._found_entry_scan_identity_recoveries,
                ),
                (
                    self.INSTALLED_LANGUAGE_SOURCE_LABEL,
                    self._installed_language_scan_identity_recoveries,
                ),
            ):
                for (raw_name, safe_name, recovered_name), count in sorted(
                    recoveries.items()
                ):
                    self._log(
                        f"  [{source_label}] {raw_name} -> {recovered_name} "
                        f"(Amulet translated: {safe_name}; {count:,} block"
                        f"{'s' if count != 1 else ''})"
                    )

        if self._scan_identity_diagnostics:
            self._log("Ambiguous scan identity details:")
            for (
                raw_name,
                raw_properties,
                safe_name,
                safe_properties,
                recovery_source,
                recovered_name,
            ), count in sorted(self._scan_identity_diagnostics.items()):
                recovery_text = (
                    f"{recovery_source} {recovered_name}"
                    if recovered_name != "<none>"
                    else "no identity recovery"
                )
                self._log(
                    f"  Direct {raw_name} [{raw_properties}] -> Amulet "
                    f"{safe_name} [{safe_properties}] -> {recovery_text} "
                    f"({count:,} block{'s' if count != 1 else ''})"
                )

        if self._scan_identity_diagnostic_overflow:
            self._log(
                "  Additional identity details omitted: "
                f"{self._scan_identity_diagnostic_overflow:,}"
            )

    def _get_selected_container(self) -> str:
        value = self.storage_choice.GetStringSelection()
        if not value:
            return self.CONTAINER_CHEST
        return value

    def _on_storage_choice_changed(self, _):
        self._update_option_visibility()
        self._schedule_settings_config_save()

    def _on_separate_types_changed(self, _):
        self._update_option_visibility()
        self._schedule_settings_config_save()

    def _on_nested_shulker_storage_changed(self, _):
        self._update_option_visibility()
        self._schedule_settings_config_save()

    def _on_display_name_dependency_changed(self, _) -> None:
        self._update_option_visibility()
        self._schedule_settings_config_save()

    def _on_installed_language_data_changed(self, _) -> None:
        self._update_option_visibility()
        self._schedule_settings_config_save()

    def _on_auto_detect_language_file_changed(self, _) -> None:
        self._update_option_visibility()
        self._schedule_settings_config_save()

    def _on_simulate_missing_display_name_changed(self, _) -> None:
        self._update_option_visibility()
        self._schedule_settings_config_save()

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

    def _update_option_visibility(self) -> None:
        container = self._get_selected_container()
        is_chest = container == self.CONTAINER_CHEST
        is_shulker = container == self.CONTAINER_SHULKER
        separate_groups_enabled = bool(self.separate_types.GetValue())
        nested_shulker_allowed = not is_shulker
        nested_shulker_enabled = (
            nested_shulker_allowed
            and bool(self.use_nested_shulker_storage.GetValue())
        )

        _set_window_sizer_item_visible(self.use_double_chests, is_chest)
        _set_checkbox_group_bottom_spacing_visible(
            self._double_chest_group_bottom_spacing,
            is_chest,
        )
        _set_window_sizer_item_visible(
            self.add_group_item_frames,
            separate_groups_enabled,
        )
        _set_window_sizer_item_visible(
            self.group_spacing_label,
            separate_groups_enabled,
        )
        self._show_sizer_windows(
            self.group_spacing_row,
            separate_groups_enabled,
        )
        _set_sizer_item_visible(
            self.group_spacing_row_item,
            separate_groups_enabled,
        )
        _set_window_sizer_item_visible(
            self.use_nested_shulker_storage,
            nested_shulker_allowed,
        )
        _set_checkbox_group_bottom_spacing_visible(
            self._nested_shulker_group_bottom_spacing,
            nested_shulker_allowed,
        )
        self._show_sizer_windows(
            self.nested_shulker_mode_row,
            nested_shulker_enabled,
        )
        _set_sizer_item_visible(
            self.nested_shulker_mode_row_item,
            nested_shulker_enabled,
        )
        self._show_sizer_windows(
            self.nested_shulker_color_row,
            nested_shulker_enabled,
        )
        _set_sizer_item_visible(
            self.nested_shulker_color_row_item,
            nested_shulker_enabled,
        )
        self._show_sizer_windows(self.shulker_color_row, is_shulker)
        _set_sizer_item_visible(
            self.shulker_color_row_item,
            is_shulker,
        )

        external_language_enabled = bool(
            self.use_installed_language_data.GetValue()
        )
        btsp_cache_enabled = bool(self.use_found_entries_cache.GetValue())
        automatic_detection_checked = bool(
            self.auto_detect_language_file.GetValue()
        )
        save_entries_checked = bool(
            self.save_found_language_entries.GetValue()
        )
        simulation_checked = bool(
            self.simulate_missing_display_name.GetValue()
        )
        language_file_access_enabled = (
            external_language_enabled or save_entries_checked
        )

        language_source_options_visible = (
            language_file_access_enabled or automatic_detection_checked
        )
        _set_window_sizer_item_visible(
            self.auto_detect_language_file,
            language_source_options_visible,
        )
        _set_checkbox_group_bottom_spacing_visible(
            self._language_source_group_bottom_spacing,
            language_source_options_visible,
        )
        language_file_row_visible = (
            language_file_access_enabled
            and not automatic_detection_checked
        )
        self._show_sizer_windows(
            self.language_file_row,
            language_file_row_visible,
        )
        _set_sizer_item_visible(
            self.language_file_row_item,
            language_file_row_visible,
        )
        _set_window_sizer_item_visible(
            self.save_found_language_entries,
            True,
        )
        _set_window_sizer_item_visible(
            self.simulate_missing_display_name,
            btsp_cache_enabled
            or external_language_enabled
            or simulation_checked,
        )
        self._show_sizer_windows(
            self.simulated_missing_alias_row,
            simulation_checked,
        )
        _set_sizer_item_visible(
            self.simulated_missing_alias_row_item,
            simulation_checked,
        )

        if not separate_groups_enabled:
            self.add_group_item_frames.SetValue(False)
        if not is_chest:
            self.use_double_chests.SetValue(False)
        if is_shulker:
            self.use_nested_shulker_storage.SetValue(False)

        for label in self._collapsible_settings_sections:
            self._update_collapsible_settings_section(label)
        self._refresh_floating_layout()

    @staticmethod
    def _show_sizer_windows(sizer, show):
        try:
            for child in sizer.GetChildren():
                window = child.GetWindow()
                nested = child.GetSizer()
                if window is not None:
                    _set_window_sizer_item_visible(window, show)
                elif nested is not None:
                    PluginClassName._show_sizer_windows(nested, show)
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
            "The plugin will scan the selection, clear exportable source blocks, preserve protected bedrock if enabled, "
            "and place the resulting items into storage containers.\n\n"
            "Continue?"
        )

        dialog = DarkMessageDialog(
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
            return f"{amount:,} {label} / second"

        rate = amount / seconds
        return f"{rate:,.2f} {label} / second"

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
            self.save_report_button.SetAvailable(False)
        except Exception:
            pass

    def _finalize_report(self) -> None:
        self._last_report_text = "\n".join(self._report_lines).strip()

        if self._last_report_text:
            try:
                wx.CallAfter(self.save_report_button.SetAvailable, True)
            except Exception:
                try:
                    self.save_report_button.SetAvailable(True)
                except Exception:
                    pass

    def _write_text_atomically(
        self,
        destination: Path,
        content: str,
        replace_existing: bool = True,
    ) -> None:
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

            if replace_existing:
                os.replace(str(temporary_path), str(destination))
                temporary_path = None
                return

            os.link(str(temporary_path), str(destination))
            temporary_path.unlink()
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except Exception:
                    pass

    def _save_last_report(self, _):
        if not self._last_report_text:
            _show_dark_message(
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
            self._write_text_atomically(
                Path(path),
                self._last_report_text + "\n",
                replace_existing=True,
            )
            _show_dark_message(
                f"Report saved:\n{path}",
                "Report Saved",
                wx.OK | wx.ICON_INFORMATION,
            )
        except Exception as exc:
            _show_dark_message(
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

    def _get_coral_type_and_dead_state(
        self,
        block,
        key: str,
    ) -> Tuple[Optional[str], bool]:
        key_text = str(key or "").strip().lower()
        if key_text.startswith("minecraft:"):
            key_text = key_text.split(":", 1)[1]
        key_text = key_text.replace(" ", "_").replace("-", "_")

        is_dead = (
            key_text.startswith("dead_")
            or "_dead" in key_text
            or key_text.endswith("_dead")
        )
        coral_type = None

        for alias, canonical_type in self.CORAL_TYPE_ALIASES.items():
            if alias in key_text:
                coral_type = canonical_type
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
            type_text = self._normalize_state_text(raw_type)
            if type_text:
                type_text = type_text.removesuffix("_fan")
                type_text = type_text.removesuffix("_coral")
                type_text = type_text.removesuffix("_block")
                type_text = type_text.removeprefix("dead_")
                type_text = type_text.removesuffix("_dead")
                coral_type = self.CORAL_TYPE_ALIASES.get(type_text)

                if coral_type is None:
                    for alias, canonical_type in self.CORAL_TYPE_ALIASES.items():
                        if alias in type_text:
                            coral_type = canonical_type
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

        return coral_type, is_dead

    def _get_coral_item_name(self, block, key: str) -> Optional[str]:
        key_text = str(key or "").strip().lower()
        if key_text.startswith("minecraft:"):
            key_text = key_text.split(":", 1)[1]
        key_text = key_text.replace(" ", "_").replace("-", "_")

        coral_type, is_dead = self._get_coral_type_and_dead_state(block, key)
        if coral_type is None:
            return None

        is_fan = "fan" in key_text
        prefix = "dead_" if is_dead else ""
        suffix = "_coral_fan" if is_fan else "_coral"
        return f"minecraft:{prefix}{coral_type}{suffix}"

    def _get_coral_block_item_name(self, block, key: str) -> Optional[str]:
        coral_type, is_dead = self._get_coral_type_and_dead_state(
            block,
            key,
        )
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

        banner_type = self._get_block_entity_nbt_value(block_entity, "Type")
        if banner_type is None:
            banner_type = 0

        try:
            base_color_value = int(base_color)
        except Exception:
            base_color_value = 0

        try:
            banner_type_value = int(banner_type)
        except Exception:
            banner_type_value = 0

        base_color_value = max(0, min(15, base_color_value))
        banner_type_value = max(0, banner_type_value)
        return (
            f"{self.BANNER_ITEM_PREFIX}{base_color_value}"
            f"__type_{banner_type_value}"
        )

    def _get_banner_item_parts(self, item_name: str) -> Tuple[int, int]:
        value = str(item_name)
        if not value.startswith(self.BANNER_ITEM_PREFIX):
            return 0, 0

        payload = value[len(self.BANNER_ITEM_PREFIX):]
        damage_text, separator, type_text = payload.partition("__type_")

        try:
            damage_value = int(damage_text)
        except Exception:
            damage_value = 0

        try:
            type_value = int(type_text) if separator else 0
        except Exception:
            type_value = 0

        return max(0, min(15, damage_value)), max(0, type_value)

    def _is_banner_item_key(self, item_name: str) -> bool:
        return str(item_name).startswith(self.BANNER_ITEM_PREFIX)

    def _make_item_extra_tag(self, item_name: str):
        if not self._is_banner_item_key(item_name):
            return None

        if TAG_Compound is None or TAG_Int is None:
            return None

        _damage_value, banner_type = self._get_banner_item_parts(item_name)
        tag = TAG_Compound()
        tag["Type"] = TAG_Int(int(banner_type))
        return tag

    def _get_item_nbt_name_damage(self, item_name: str) -> Tuple[str, int]:
        item_name = self.ITEM_NAME_OVERRIDES.get(str(item_name), str(item_name))

        if self._is_banner_item_key(item_name):
            banner_damage, _banner_type = self._get_banner_item_parts(item_name)
            return "minecraft:banner", banner_damage

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

    def _get_sapling_item_name(self, block) -> Optional[str]:
        sapling_type = self._get_block_property(
            block,
            (
                "sapling_type",
                "minecraft:sapling_type",
                "wood_type",
                "tree_type",
            ),
        )
        if sapling_type is None:
            return None

        normalized_type = self._normalize_name(str(sapling_type))
        normalized_type = normalized_type.replace("darkoak", "dark_oak")
        normalized_type = normalized_type.replace("big oak", "big_oak")
        normalized_type = normalized_type.replace("-", "_")
        normalized_type = normalized_type.replace(" ", "_")

        return self.SAPLING_ITEM_BY_TYPE.get(normalized_type)

    def _classify_block(
        self,
        block,
        block_entity=None,
        source_key: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        key = (
            source_key
            if source_key is not None
            else self._get_namespaced_block_name(block)
        )
        source_key = key

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
        elif key == "minecraft:sapling":
            sapling_item = self._get_sapling_item_name(block)
            if sapling_item:
                key = sapling_item
        elif (
            key == "minecraft:coral"
            or key == "minecraft:coral_fan"
            or key == "minecraft:coral_fan_dead"
            or key.startswith("minecraft:coral_fan_hang")
            or key.endswith("_coral")
            or key.endswith("_coral_fan")
            or key.endswith("_coral_wall_fan")
        ):
            coral_item = self._get_coral_item_name(block, key)
            if coral_item:
                key = coral_item
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

        conversion_entry_item = None
        conversion_entries = getattr(self, "_conversion_entries", None)
        if (
            source_key == key
            and conversion_entries
            and source_key in conversion_entries
        ):

            conversion_entry_item = self._resolve_conversion_entry_item(
                source_key,
                key,
            )
            if conversion_entry_item:
                key = conversion_entry_item

        reviewed_normalization_item = None
        reviewed_enabled = getattr(
            self,
            "_operation_use_reviewed_amulet_normalization",
            None,
        )
        if (
            source_key == key
            and source_key in self.REVIEWED_AMULET_NORMALIZATIONS
            and reviewed_enabled is not False
        ):
            reviewed_normalization_item = (
                self._resolve_reviewed_amulet_normalization(
                    block,
                    source_key,
                    key,
                )
            )
            if reviewed_normalization_item:
                key = reviewed_normalization_item

        conversion_tracking_enabled = getattr(
            self,
            "_operation_conversion_tracking_enabled",
            None,
        )
        if conversion_tracking_enabled is not False:
            self._record_amulet_conversion_comparison(
                block,
                source_key,
                key,
                conversion_entry_item,
                reviewed_normalization_item,
            )

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
            try:
                return bool(self.attempt_unresolved_item_writes.GetValue())
            except Exception:
                return False

        return True

    def _get_extra_export_items_for_block(
        self,
        block,
        block_key: Optional[str] = None,
    ) -> List[Tuple[str, int]]:
        include_unusual = getattr(
            self,
            "_operation_include_unusual",
            None,
        )
        if include_unusual is None:
            include_unusual = bool(self.include_unusual.GetValue())
        if include_unusual:
            return []

        key = (
            block_key
            if block_key is not None
            else self._get_namespaced_block_name(block)
        )

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

    def _get_raw_double_slab_export_multiplier(
        self,
        raw_block,
        raw_scan_key: Optional[str],
        export_key: Optional[str],
    ) -> int:
        raw_scan_key_text = str(raw_scan_key or "")
        if "slab" not in raw_scan_key_text:
            return 1

        include_unusual = getattr(
            self,
            "_operation_include_unusual",
            None,
        )
        if include_unusual is None:
            include_unusual = bool(self.include_unusual.GetValue())
        if include_unusual:
            return 1

        if not self._is_double_slab_state(raw_block, raw_scan_key_text):
            return 1

        normalized_export_key = self._normalize_conversion_identifier(
            export_key or ""
        )
        if normalized_export_key is None:
            return 1

        if self._get_double_slab_export_item(normalized_export_key):
            return 1

        if normalized_export_key.endswith("_slab"):
            return 2

        return 1

    def _record_export_count(self, counts: Dict[str, int], item_name: str, amount: int = 1) -> None:
        item_name = str(item_name)
        item_name = self.ITEM_NAME_OVERRIDES.get(item_name, item_name)
        amount = int(amount)

        include_unusual = getattr(
            self,
            "_operation_include_unusual",
            None,
        )
        if include_unusual is None:
            include_unusual = bool(self.include_unusual.GetValue())

        if not include_unusual and "slab" in item_name:
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
        self._found_entries_sync_queued_count = 0
        self._external_language_prepared = False
        self._display_name_resolution_cache = {}

    def _release_operation_display_name_caches(self) -> None:
        self._external_language_used = {}
        self._found_entries_used = {}
        self._pending_found_entries = {}
        self._display_name_resolution_cache = {}

    def _reset_conversion_operation_state(self) -> None:
        self._conversion_entries = {}
        self._conversion_entries_used = {}
        self._conversion_entries_skipped = {}
        self._conversion_entries_skip_reason_counts = {}
        self._conversion_entries_skip_details = []
        self._conversion_entries_skip_detail_overflow = 0
        self._conversion_entries_load_error = ""
        self._conversion_entries_loaded_count = 0
        self._conversion_entries_prepared = False
        self._pending_conversion_candidates = collections.defaultdict(int)
        self._conversion_candidates_new_record_count = 0
        self._conversion_candidates_updated_record_count = 0
        self._conversion_candidate_observations_added_count = 0
        self._conversion_candidates_existing_record_count = 0
        self._conversion_candidates_total_record_count = 0
        self._conversion_candidates_write_error = ""

    def _release_operation_conversion_caches(self) -> None:
        self._conversion_entries = {}
        self._conversion_entries_used = {}
        self._conversion_entries_skipped = {}
        self._conversion_entries_skip_reason_counts = {}
        self._conversion_entries_skip_details = []
        self._conversion_entries_skip_detail_overflow = 0
        self._pending_conversion_candidates = collections.defaultdict(int)

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

    def _clear_loaded_display_name_data(self) -> None:
        self._external_language_aliases = {}
        self._found_entries_aliases = {}
        self._found_entries_raw_entries = {}
        self._external_language_loaded_path = ""
        self._external_language_load_error = ""
        self._external_language_loaded_count = 0
        self._external_language_used = {}
        self._found_entries_used = {}
        self._pending_found_entries = {}
        self._found_entries_write_error = ""
        self._found_entries_written_count = 0
        self._found_entries_sync_queued_count = 0
        self._external_language_prepared = False
        self._display_name_resolution_cache = {}

    def _get_settings_config_path(self) -> Path:
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
            "storage_choice",
            "show_storage_icons_cb",
            "shulker_color_choice",
            "use_double_chests",
            "stack_height",
            "include_unusual",
            "preserve_bedrock",
            "alphabetical_order",
            "separate_types",
            "add_group_item_frames",
            "group_spacing",
            "use_nested_shulker_storage",
            "nested_shulker_mode_choice",
            "nested_shulker_color_choice",
            "fast_direct_scan",
            "fast_direct_clear",
            "show_large_selection_warning",
            "use_found_entries_cache",
            "use_installed_language_data",
            "auto_detect_language_file",
            "language_file_path",
            "save_found_language_entries",
            "simulate_missing_display_name",
            "simulated_missing_alias",
            "use_conversion_entries",
            "include_item_frame_audit",
            "include_display_name_audit",
            "include_amulet_conversion_diagnostic",
            "include_amulet_translator_probe",
            "use_reviewed_amulet_normalization",
            "record_conversion_candidates",
            "attempt_unresolved_item_writes",
            "include_amulet_conversion_audit",
            "record_all_conversion_observations",
        )
        return {
            name: getattr(self, name)
            for name in control_names
            if getattr(self, name, None) is not None
        }

    def _read_settings_control_value(self, control):
        if isinstance(control, (wx.CheckBox, ModernCheckBox)):
            return bool(control.GetValue())
        if isinstance(control, (wx.Choice, ModernChoice)):
            selected = str(control.GetStringSelection())
            if control in (
                getattr(self, "shulker_color_choice", None),
                getattr(self, "nested_shulker_color_choice", None),
            ):
                return _shulker_color_value(selected)
            return selected
        if isinstance(control, (wx.SpinCtrl, wx.Slider, ModernSlider)):
            return int(control.GetValue())
        if isinstance(control, (wx.TextCtrl, ModernTextField)):
            return str(control.GetValue())
        raise TypeError(f"Unsupported settings control: {type(control)!r}")

    def _apply_settings_control_value(self, control, value) -> bool:
        try:
            if isinstance(control, (wx.CheckBox, ModernCheckBox)):
                if not isinstance(value, bool):
                    return False
                control.SetValue(value)
                return True
            if isinstance(control, (wx.Choice, ModernChoice)):
                if not isinstance(value, str):
                    return False
                display_value = value
                if control in (
                    getattr(self, "shulker_color_choice", None),
                    getattr(self, "nested_shulker_color_choice", None),
                ):
                    display_value = _shulker_color_label(value)
                index = control.FindString(display_value)
                if index == wx.NOT_FOUND:
                    return False
                control.SetSelection(index)
                return True
            if isinstance(control, (wx.SpinCtrl, wx.Slider, ModernSlider)):
                if isinstance(value, bool) or not isinstance(value, int):
                    return False
                if value < control.GetMin() or value > control.GetMax():
                    return False
                control.SetValue(value)
                return True
            if isinstance(control, (wx.TextCtrl, ModernTextField)):
                if not isinstance(value, str):
                    return False
                control.SetValue(value)
                return True
        except Exception:
            return False
        return False

    def _collect_current_settings_config(self) -> dict:
        settings = {}
        for key, control in self._settings_control_registry().items():
            try:
                settings[key] = self._read_settings_control_value(control)
            except Exception:
                continue
        ui_state = {}
        for label, section in self._collapsible_settings_sections.items():
            try:
                ui_state[label] = bool(section[0].GetValue())
            except Exception:
                continue
        return {
            "format_version": self.SETTINGS_CONFIG_FORMAT_VERSION,
            "plugin": "Blocks to Storage",
            "settings": settings,
            "ui_state": ui_state,
            "ui": {
                "window_size": self._current_window_size_config(),
                "manage_window_size": self._current_manage_dialog_size_config(),
                "console_visible": bool(self._console_visible),
            },
        }

    def _capture_settings_defaults(self) -> None:
        self._settings_defaults = self._collect_current_settings_config()

    def _load_settings_config_data(self, path: Path) -> Optional[dict]:
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
            plugin_name = data.get("plugin")
            if plugin_name is not None and plugin_name != "Blocks to Storage":
                raise ValueError("the selected file belongs to another plugin")
            settings = data.get("settings", {})
            ui_state = data.get("ui_state", {})
            ui = data.get("ui", {})
            if not isinstance(settings, dict):
                raise ValueError("'settings' must be a JSON object")
            if not isinstance(ui_state, dict):
                raise ValueError("'ui_state' must be a JSON object")
            if not isinstance(ui, dict):
                raise ValueError("'ui' must be a JSON object")
            if plugin_name is None:
                recognized = set(settings).intersection(self._settings_control_registry())
                if not recognized and not set(ui_state).intersection(self._collapsible_settings_sections):
                    raise ValueError("the selected file does not contain recognizable Blocks to Storage settings")
            return data
        except Exception as exc:
            self._settings_config_load_error = str(exc)
            return None

    def _apply_settings_config_data(self, data: dict) -> None:
        self._settings_config_applying = True
        try:
            saved_settings = data.get("settings", {})
            for key, control in self._settings_control_registry().items():
                if key in saved_settings:
                    self._apply_settings_control_value(control, saved_settings[key])
            self.stack_height_box.ChangeValue(str(self.stack_height.GetValue()))
            self.group_spacing_box.ChangeValue(str(self.group_spacing.GetValue()))
            try:
                show_icons = bool(self.show_storage_icons_cb.GetValue())
                for choice in (
                    self.storage_choice,
                    self.shulker_color_choice,
                    self.nested_shulker_color_choice,
                ):
                    choice.SetShowIcons(show_icons)
            except Exception:
                pass
            saved_ui_state = data.get("ui_state", {})
            for label, expanded in saved_ui_state.items():
                section = self._collapsible_settings_sections.get(label)
                if section is not None and isinstance(expanded, bool):
                    section[0].SetValue(expanded)

            self._apply_saved_console_visibility(data)
            self._apply_saved_window_size(data)
            self._apply_saved_manage_dialog_size(data)
            self._update_option_visibility()
        finally:
            self._settings_config_applying = False

    def _merge_settings_config_data(self, existing: Optional[dict]) -> dict:
        merged = dict(existing) if isinstance(existing, dict) else {}
        current = self._collect_current_settings_config()
        merged["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        merged["plugin"] = "Blocks to Storage"
        existing_settings = merged.get("settings")
        if not isinstance(existing_settings, dict):
            existing_settings = {}
        existing_settings.update(current["settings"])
        merged["settings"] = existing_settings
        existing_ui_state = merged.get("ui_state")
        if not isinstance(existing_ui_state, dict):
            existing_ui_state = {}
        existing_ui_state.update(current["ui_state"])
        merged["ui_state"] = existing_ui_state
        existing_ui = merged.get("ui")
        if not isinstance(existing_ui, dict):
            existing_ui = {}
        existing_ui.update(current["ui"])
        merged["ui"] = existing_ui
        return merged

    def _write_settings_config(
        self,
        create_if_missing: bool = True,
    ) -> bool:
        if self._settings_config_applying:
            return False

        path = self._get_settings_config_path()
        if not create_if_missing and not path.is_file():
            return False

        existing = None
        if path.is_file():
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
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_text_atomically(
                path,
                content,
                replace_existing=True,
            )
            self._settings_config_load_error = ""
            self._settings_config_write_error = ""
            return True
        except Exception as exc:
            self._settings_config_write_error = str(exc)
            return False

    def _schedule_settings_config_save(self, event=None) -> None:
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

    def _save_settings_config_after_delay(self) -> None:
        self._settings_config_save_call = None
        self._write_settings_config(create_if_missing=True)

    def _bind_settings_persistence_events(self) -> None:
        custom_handled = {
            id(self.storage_choice),
            id(self.show_storage_icons_cb),
            id(self.separate_types),
            id(self.use_nested_shulker_storage),
            id(self.use_found_entries_cache),
            id(self.use_installed_language_data),
            id(self.auto_detect_language_file),
            id(self.save_found_language_entries),
            id(self.simulate_missing_display_name),
            id(self.stack_height),
            id(self.group_spacing),
        }
        for control in self._settings_control_registry().values():
            if id(control) in custom_handled:
                continue
            try:
                if isinstance(control, (wx.CheckBox, ModernCheckBox)):
                    control.Bind(wx.EVT_CHECKBOX, self._schedule_settings_config_save)
                elif isinstance(control, (wx.Choice, ModernChoice)):
                    control.Bind(wx.EVT_CHOICE, self._schedule_settings_config_save)
                elif isinstance(control, (wx.SpinCtrl, wx.Slider, ModernSlider)):
                    control.Bind(wx.EVT_SLIDER, self._schedule_settings_config_save)
                elif isinstance(control, (wx.TextCtrl, ModernTextField)):
                    control.Bind(wx.EVT_TEXT, self._schedule_settings_config_save)
            except Exception:
                continue

    def _initialize_settings_persistence(self) -> None:
        self._capture_settings_defaults()
        path = self._get_settings_config_path()
        self._settings_config_load_error = ""
        data = self._load_settings_config_data(path)
        if data is not None:
            self._apply_settings_config_data(data)
            self._write_settings_config(create_if_missing=False)
        else:
            self._update_option_visibility()
            if path.is_file() and self._settings_config_load_error:
                try:
                    self.status.SetLabel("Settings file needs repair. Use Manage Files.")
                except Exception:
                    pass
        self._bind_settings_persistence_events()

    def _stop_pending_settings_save(self) -> None:
        pending = self._settings_config_save_call
        self._settings_config_save_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _reset_settings_to_defaults(self) -> bool:
        defaults = self._settings_defaults
        if not isinstance(defaults, dict):
            return False

        normalized = json.dumps(
            defaults,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        self._stop_pending_settings_save()
        try:
            path = self._get_settings_config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_text_atomically(
                path,
                normalized,
                replace_existing=True,
            )
        except Exception as exc:
            self._settings_config_write_error = str(exc)
            return False

        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_config_data(defaults)
        return True

    def _repair_json_missing_line_commas(self, content: str) -> str:
        lines = content.splitlines()
        repaired = list(lines)

        for index, line in enumerate(lines[:-1]):
            current = line.rstrip()
            stripped = current.strip()
            if not stripped:
                continue
            if stripped.endswith((",", "{", "[", ":")):
                continue

            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index >= len(lines):
                continue

            next_stripped = lines[next_index].lstrip()
            if not next_stripped.startswith('"'):
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
    ) -> Tuple[Optional[dict], List[str]]:
        attempts = []

        def try_json(candidate: str, repair_name: str):
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    if repair_name:
                        attempts.append(repair_name)
                    return data, candidate
            except Exception:
                pass
            return None, candidate

        normalized = content.lstrip("\ufeff")

        data, normalized = try_json(normalized, "")
        if data is not None:
            return data, attempts

        without_trailing_commas = re.sub(
            r",(\s*[}\]])",
            r"\1",
            normalized,
        )
        data, without_trailing_commas = try_json(
            without_trailing_commas,
            "removed trailing commas",
        )
        if data is not None:
            return data, attempts

        with_line_commas = self._repair_json_missing_line_commas(
            without_trailing_commas
        )
        data, with_line_commas = try_json(
            with_line_commas,
            "restored missing entry commas",
        )
        if data is not None:
            return data, attempts

        try:
            literal_data = ast.literal_eval(with_line_commas)
            if isinstance(literal_data, dict):
                attempts.append("normalized Python-style JSON values")
                return literal_data, attempts
        except Exception:
            pass

        return None, attempts

    def _validate_repaired_settings_config(self, data: dict) -> Tuple[bool, str]:
        if not isinstance(data, dict):
            return False, "The top-level value is not an object."

        plugin_name = data.get("plugin")
        if plugin_name is not None and plugin_name != "Blocks to Storage":
            return False, "The file identifies another plugin."

        settings = data.get("settings", {})
        ui_state = data.get("ui_state", {})
        ui = data.get("ui", {})
        if not isinstance(settings, dict):
            return False, "The settings entry is not an object."
        if not isinstance(ui_state, dict):
            return False, "The ui_state entry is not an object."
        if not isinstance(ui, dict):
            return False, "The ui entry is not an object."

        if plugin_name is None:
            recognized = set(settings).intersection(self._settings_control_registry())
            if not recognized and not set(ui_state).intersection(self._collapsible_settings_sections):
                return False, "The file does not contain recognizable Blocks to Storage settings."

        return True, ""

    def _merge_recovered_settings_config_data(
        self,
        recovered: dict,
    ) -> dict:
        merged = dict(recovered) if isinstance(recovered, dict) else {}
        defaults = (
            self._settings_defaults
            if isinstance(self._settings_defaults, dict)
            else self._collect_current_settings_config()
        )

        merged["format_version"] = self.SETTINGS_CONFIG_FORMAT_VERSION
        merged["plugin"] = "Blocks to Storage"

        recovered_settings = merged.get("settings")
        if not isinstance(recovered_settings, dict):
            recovered_settings = {}

        default_settings = defaults.get("settings", {})
        if isinstance(default_settings, dict):
            for key, value in default_settings.items():
                recovered_settings.setdefault(key, value)
        merged["settings"] = recovered_settings

        recovered_ui_state = merged.get("ui_state")
        if not isinstance(recovered_ui_state, dict):
            recovered_ui_state = {}

        default_ui_state = defaults.get("ui_state", {})
        if isinstance(default_ui_state, dict):
            for key, value in default_ui_state.items():
                recovered_ui_state.setdefault(key, value)
        merged["ui_state"] = recovered_ui_state

        recovered_ui = merged.get("ui")
        if not isinstance(recovered_ui, dict):
            recovered_ui = {}
        default_ui = defaults.get("ui", {})
        if isinstance(default_ui, dict):
            for key, value in default_ui.items():
                recovered_ui.setdefault(key, value)
        merged["ui"] = recovered_ui

        return merged

    def _repair_existing_settings_config(self) -> None:
        path = self._get_settings_config_path()
        if not path.is_file():
            _show_dark_message(
                "No active Blocks to Storage settings file was found.",
                "Blocks to Storage",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        try:
            if path.stat().st_size > self.MAX_SETTINGS_CONFIG_BYTES:
                raise ValueError("The settings file exceeds the 1 MiB safety limit.")
            content = path.read_text(
                encoding="utf-8-sig",
                errors="strict",
            )
        except Exception as exc:
            _show_dark_message(
                f"The settings file could not be read.\n\nReason: {exc}",
                "Blocks to Storage",
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
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        valid, reason = self._validate_repaired_settings_config(repaired_data)
        if not valid:
            _show_dark_message(
                "The settings file could not be repaired safely.\n\n"
                f"Reason: {reason}\n\nNo changes were made.",
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        confirmation_lines = [
            "Repair and normalize the active settings file?",
            "",
            "Recognized settings will be validated.",
            "Unknown entries will be preserved.",
            "Missing current settings will be added with their defaults.",
            "The repaired file will atomically replace the existing file.",
        ]
        if repairs:
            confirmation_lines.extend(
                [
                    "",
                    "Detected repairs:",
                    *[f"• {repair}" for repair in repairs],
                ]
            )
        else:
            confirmation_lines.extend(
                [
                    "",
                    "The JSON is readable. The file will be normalized and "
                    "merged with the current setting structure.",
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
            self._write_text_atomically(
                path,
                normalized_content,
                replace_existing=True,
            )
        except Exception as exc:
            _show_dark_message(
                f"The repaired settings file could not be written.\n\nReason: {exc}",
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._settings_config_load_error = ""
        self._settings_config_write_error = ""
        self._apply_settings_config_data(merged)

        _show_dark_message(
            "The settings file was repaired and reloaded successfully.",
            "Blocks to Storage",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _import_settings_config(self) -> None:
        dialog = wx.FileDialog(
            self,
            "Import Blocks to Storage settings",
            wildcard="Blocks to Storage config (*.config)|*.config|All files (*.*)|*.*",
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
            _show_dark_message(
                "The selected settings file could not be imported.\n\n"
                f"Reason: {self._settings_config_load_error or 'Invalid file'}",
                "Blocks to Storage",
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
            active_path = self._get_settings_config_path()
            active_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_text_atomically(
                active_path,
                content,
                replace_existing=True,
            )
            self._settings_config_load_error = ""
            self._settings_config_write_error = ""
        except Exception as exc:
            self._settings_config_write_error = str(exc)
            _show_dark_message(
                "The selected settings were valid, but the active settings file "
                "could not be written. The visible settings were not changed.\n\n"
                f"Reason: {self._settings_config_write_error}",
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._apply_settings_config_data(merged)
        _show_dark_message(
            "Settings imported successfully.",
            "Blocks to Storage",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _export_settings_config(self) -> None:
        dialog = wx.FileDialog(
            self,
            "Export Blocks to Storage settings",
            defaultFile=self.SETTINGS_CONFIG_FILENAME,
            wildcard="Blocks to Storage config (*.config)|*.config|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            destination = Path(dialog.GetPath())
        finally:
            dialog.Destroy()

        existing = self._load_settings_config_data(
            self._get_settings_config_path()
        )
        merged = self._merge_settings_config_data(existing)
        content = json.dumps(
            merged,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"

        try:
            self._write_text_atomically(
                destination,
                content,
                replace_existing=True,
            )
        except Exception as exc:
            _show_dark_message(
                f"Could not export the settings file.\n\nReason: {exc}",
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        _show_dark_message(
            "Settings exported successfully.",
            "Blocks to Storage",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _plugin_managed_file_definitions(self):
        return [
            (
                self.SETTINGS_CONFIG_FILENAME,
                "Saved plugin settings",
            ),
            (
                self.FOUND_ENTRIES_FILENAME,
                "Discovered display-name entries",
            ),
            (
                self.CONVERSION_ENTRIES_FILENAME,
                "Reviewed active conversion rules",
            ),
            (
                self.CONVERSION_CANDIDATES_FILENAME,
                "Inactive conversion observations",
            ),
        ]

    def _get_managed_file_candidates(self, filename: str) -> List[Path]:
        if filename == self.SETTINGS_CONFIG_FILENAME:
            return [self._get_settings_config_path()]

        return [
            self._get_plugin_directory() / filename,
            Path.home() / ".blocks_to_storage" / filename,
        ]

    def _choose_writable_managed_file_path(
        self,
        filename: str,
    ) -> Optional[Path]:
        if filename == self.SETTINGS_CONFIG_FILENAME:
            try:
                path = self._get_settings_config_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                return path
            except Exception:
                return None

        for directory in (
            self._get_plugin_directory(),
            Path.home() / ".blocks_to_storage",
        ):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                probe = directory / ".btsp_write_probe.tmp"
                probe.write_text("probe", encoding="utf-8")
                probe.unlink()
                return directory / filename
            except Exception:
                continue
        return None

    def _managed_file_template(self, filename: str) -> str:
        if filename == self.SETTINGS_CONFIG_FILENAME:
            return json.dumps(
                self._merge_settings_config_data(None),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ) + "\n"
        if filename == self.CONVERSION_ENTRIES_FILENAME:
            return (
                "# Blocks to Storage reviewed conversion rules\n"
                "# Rules in this file affect exported items.\n"
                "# The plugin reads this file but never writes active rules to it.\n"
                "# Add only mappings that have been reviewed and verified.\n"
                "# Format: minecraft:source=minecraft:target\n"
            )
        if filename == self.CONVERSION_CANDIDATES_FILENAME:
            return (
                "# Blocks to Storage inactive conversion candidates\n"
                "# These observations never affect exports.\n"
                "# Existing observations are read only so counts can be merged.\n"
                "# Built-in resolved families are omitted unless advanced recording is enabled\n"
                "# or an external language-assisted identity recovery is recorded.\n"
                "# Format version: 1\n"
                "# source<TAB>target<TAB>source properties<TAB>observations\n"
            )
        return (
            "# Blocks to Storage discovered display-name entries\n"
            "# Format: language_key=Display Name\n"
        )

    def _managed_file_authority(self, filename: str) -> str:
        if filename == self.SETTINGS_CONFIG_FILENAME:
            return "User preferences"
        if filename == self.CONVERSION_ENTRIES_FILENAME:
            return "Active rules"
        if filename == self.CONVERSION_CANDIDATES_FILENAME:
            return "Inactive observations"
        return "Display-name cache"

    def _managed_file_entry_status(
        self,
        filename: str,
        path: Path,
    ) -> Tuple[str, str]:
        try:
            content = path.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )
        except Exception as exc:
            return "Unknown", f"Read error: {exc}"

        if filename == self.SETTINGS_CONFIG_FILENAME:
            try:
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("top-level value is not an object")
                settings = data.get("settings", {})
                ui_state = data.get("ui_state", {})
                ui = data.get("ui", {})
                if (
                    not isinstance(settings, dict)
                    or not isinstance(ui_state, dict)
                    or not isinstance(ui, dict)
                ):
                    raise ValueError("settings, ui_state or ui is not an object")
                count = len(settings) + len(ui_state) + len(ui)
                return f"{count:,}", "Valid"
            except Exception as exc:
                return "Unknown", f"Malformed: {exc}"

        entries = 0
        malformed = 0
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            entries += 1
            if filename == self.CONVERSION_CANDIDATES_FILENAME:
                if len(line.split("\t")) != 4:
                    malformed += 1
            elif filename == self.CONVERSION_ENTRIES_FILENAME:
                if "=" not in line and "->" not in line and "\t" not in line:
                    malformed += 1

        status = "Valid" if malformed == 0 else f"Malformed: {malformed}"
        return f"{entries:,}", status

    def _managed_file_access_status(self, path: Path) -> str:
        try:
            mode = path.stat().st_mode
            read_only = not bool(mode & stat.S_IWRITE)
            readable = os.access(str(path), os.R_OK)
            writable = os.access(str(path), os.W_OK) and not read_only
        except Exception:
            return "Unknown"

        if readable and writable:
            return "Read & Write"
        if readable:
            return "Read Only"
        if writable:
            return "Write Only"
        return "No Access"

    def _managed_file_status_label(
        self,
        filename: str,
        description: str,
    ) -> str:
        existing_paths = [
            path
            for path in self._get_managed_file_candidates(filename)
            if path.is_file()
        ]
        authority = self._managed_file_authority(filename)

        if not existing_paths:
            return (
                f"{filename} | Not found | Access: Not applicable | Entries: 0 | "
                f"Authority: {authority} | {description}"
            )

        path = existing_paths[0]
        try:
            size_text = f"{path.stat().st_size:,} bytes"
        except Exception:
            size_text = "Unknown"

        entry_count, structure_status = self._managed_file_entry_status(
            filename,
            path,
        )
        access_status = self._managed_file_access_status(path)
        return (
            f"{filename} | Exists | Size: {size_text} | "
            f"Entries: {entry_count} | Access: {access_status} | "
            f"Status: {structure_status} | Authority: {authority}"
        )

    def _show_plugin_file_action_dialog(
        self,
        actions: Sequence[Tuple[str, str]],
    ) -> Optional[int]:
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
            return int(selection) if selection != wx.NOT_FOUND else None
        finally:
            dialog.Destroy()

    def _manage_plugin_files(self, _) -> None:
        while True:
            definitions = self._plugin_managed_file_definitions()
            labels = [
                self._managed_file_status_label(filename, description)
                for filename, description in definitions
            ]

            actions = [
                (
                    "Create selected files",
                    "Create missing plugin-managed files without replacing existing ones. "
                    "These local files can support display-name sorting, approved "
                    "conversion rules, diagnostic candidates and saved settings.",
                ),
                (
                    "Delete selected files",
                    "Remove selected plugin-managed files from local plugin or settings "
                    "storage. This can clear cached names, conversion data, candidates "
                    "or saved settings, but it never deletes worlds or the plugin file.",
                ),
                (
                    "Open plugin folder",
                    "Open the local plugin folder used for optional BTSP data files, "
                    "including found display-name entries, approved conversions and "
                    "recorded conversion candidates.",
                ),
                (
                    "Open settings folder",
                    "Open the folder that stores the active Blocks to Storage settings "
                    "config. This is separate from the optional BTSP data files.",
                ),
                (
                    "Reset saved settings to defaults",
                    "Replace the active settings config with current default settings "
                    "and default collapsible UI states. Local BTSP data files are not "
                    "deleted.",
                ),
                (
                    "Attempt to repair existing settings config",
                    "Try a conservative manual repair of the active settings config when "
                    "simple editable JSON mistakes prevent it from loading.",
                ),
                (
                    "Import settings...",
                    "Copy a selected settings backup into the active config location. "
                    "This updates saved settings only and does not change the active "
                    "config path.",
                ),
                (
                    "Export settings...",
                    "Save a copy of the active settings config to a location you choose. "
                    "This creates a backup for later import and does not move the "
                    "active config.",
                ),
                (
                    f"Update {self.FOUND_ENTRIES_FILENAME} from en_US.lang",
                    "Scan the configured Minecraft en_US.lang file now and merge every "
                    "safe tile, item and block display-name entry that is missing from "
                    "the embedded table and the existing Found Entries cache.",
                ),
            ]
            action = self._show_plugin_file_action_dialog(actions)
            if action is None:
                return

            if action == 2:
                try:
                    wx.LaunchDefaultApplication(
                        str(self._get_plugin_directory())
                    )
                except Exception as exc:
                    _show_dark_message(
                        f"Could not open the plugin folder.\n\nReason: {exc}",
                        "Blocks to Storage",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )
                continue

            if action == 3:
                try:
                    settings_directory = self._get_settings_config_path().parent
                    settings_directory.mkdir(parents=True, exist_ok=True)
                    wx.LaunchDefaultApplication(str(settings_directory))
                except Exception as exc:
                    _show_dark_message(
                        f"Could not open the settings folder.\n\nReason: {exc}",
                        "Blocks to Storage",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )
                continue

            if action == 4:
                confirmation = DarkMessageDialog(
                    self,
                    "Reset all Blocks to Storage settings to their current "
                    "defaults?\n\nThe settings file will remain and will be "
                    "rewritten with default values.",
                    "Reset saved settings?",
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                )
                try:
                    confirmed = confirmation.ShowModal() == wx.ID_YES
                finally:
                    confirmation.Destroy()
                if confirmed:
                    if self._reset_settings_to_defaults():
                        _show_dark_message(
                            "Blocks to Storage settings were reset successfully.",
                            "Blocks to Storage",
                            wx.OK | wx.ICON_INFORMATION,
                            self,
                        )
                    else:
                        _show_dark_message(
                            "The settings could not be reset.\n\n"
                            f"Reason: {self._settings_config_write_error or 'Unknown error'}",
                            "Blocks to Storage",
                            wx.OK | wx.ICON_WARNING,
                            self,
                        )
                continue

            if action == 5:
                self._repair_existing_settings_config()
                continue

            if action == 6:
                self._import_settings_config()
                continue

            if action == 7:
                self._export_settings_config()
                continue

            if action == 8:
                self._synchronize_found_entries_from_language_file()
                continue

            selection_dialog = DarkMultiChoiceDialog(
                wx.GetTopLevelParent(self) or self,
                "Select plugin files",
                "Select the plugin-managed files to create or delete. Back returns "
                "to the main file-management menu.",
                labels,
            )
            try:
                if selection_dialog.ShowModal() != wx.ID_OK:
                    continue
                selections = list(selection_dialog.GetSelections())
            finally:
                selection_dialog.Destroy()

            if not selections:
                _show_dark_message(
                    "No files were selected.",
                    "Blocks to Storage",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
                continue

            selected_names = [definitions[index][0] for index in selections]

            if action == 0:
                created = []
                unchanged = []
                failed = []

                for filename in selected_names:
                    existing = any(
                        path.is_file()
                        for path in self._get_managed_file_candidates(filename)
                    )
                    if existing:
                        unchanged.append((filename, "already exists"))
                        continue

                    destination = self._choose_writable_managed_file_path(
                        filename
                    )
                    if destination is None:
                        failed.append(
                            (filename, "no writable data directory")
                        )
                        continue

                    try:
                        self._write_text_atomically(
                            destination,
                            self._managed_file_template(filename),
                            replace_existing=False,
                        )
                        created.append(destination)
                    except Exception as exc:
                        failed.append((filename, str(exc)))

                lines = []
                if created:
                    lines.append("Created:")
                    lines.extend(f"• {path}" for path in created)
                if unchanged:
                    if lines:
                        lines.append("")
                    lines.append("Not changed:")
                    lines.extend(
                        f"• {name}: {reason}"
                        for name, reason in unchanged
                    )
                if failed:
                    if lines:
                        lines.append("")
                    lines.append("Could not create:")
                    lines.extend(
                        f"• {name}: {reason}"
                        for name, reason in failed
                    )

                _show_dark_message(
                    "\n".join(lines) if lines else "No files were created.",
                    "Blocks to Storage",
                    wx.OK | (
                        wx.ICON_WARNING
                        if failed
                        else wx.ICON_INFORMATION
                    ),
                    self,
                )
                continue

            confirmation = DarkMessageDialog(
                self,
                "Delete the selected plugin-managed files?\n\n"
                + "\n".join(f"• {name}" for name in selected_names)
                + "\n\nWorlds, reports, Minecraft files and the plugin itself "
                "will not be deleted.",
                "Delete selected plugin files?",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            )
            try:
                if confirmation.ShowModal() != wx.ID_YES:
                    continue
            finally:
                confirmation.Destroy()

            if self.SETTINGS_CONFIG_FILENAME in selected_names:
                self._stop_pending_settings_save()

            deleted = []
            failed = []
            for filename in selected_names:
                for path in self._get_managed_file_candidates(filename):
                    try:
                        if path.is_file():
                            path.unlink()
                            deleted.append(path)
                    except Exception as exc:
                        failed.append((path, str(exc)))

            fallback_directory = Path.home() / ".blocks_to_storage"
            try:
                if (
                    fallback_directory.is_dir()
                    and not any(fallback_directory.iterdir())
                ):
                    fallback_directory.rmdir()
            except Exception:
                pass

            self._clear_loaded_display_name_data()
            self._clear_loaded_conversion_data()

            if self.SETTINGS_CONFIG_FILENAME in selected_names:
                config_still_exists = any(
                    path.is_file()
                    for path in self._get_managed_file_candidates(
                        self.SETTINGS_CONFIG_FILENAME
                    )
                )
                if not config_still_exists:
                    self._apply_settings_config_data(self._settings_defaults)
                    self._settings_config_load_error = ""
                    self._settings_config_write_error = ""

            lines = []
            if deleted:
                lines.append("Deleted:")
                lines.extend(f"• {path}" for path in deleted)
            if failed:
                if lines:
                    lines.append("")
                lines.append("Could not delete:")
                lines.extend(
                    f"• {path}: {reason}"
                    for path, reason in failed
                )

            _show_dark_message(
                "\n".join(lines) if lines else "No selected files were found.",
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
                probe_path = directory / ".btsp_write_probe.tmp"
                with probe_path.open("w", encoding="utf-8") as handle:
                    handle.write("probe")
                probe_path.unlink()
                return directory / self.FOUND_ENTRIES_FILENAME
            except Exception:
                continue

        return None

    def _normalize_conversion_identifier(self, value: str) -> Optional[str]:
        value = str(value).strip().lower()
        if not value or "\0" in value:
            return None
        if value.count(":") != 1:
            return None
        namespace, base_name = value.split(":", 1)
        if not namespace or not base_name:
            return None
        if not re.fullmatch(r"[a-z0-9_.-]+", namespace):
            return None
        if not re.fullmatch(r"[a-z0-9_./-]+", base_name):
            return None
        return f"{namespace}:{base_name}"

    def _is_safe_conversion_source_key(self, source_key: str) -> bool:
        source_key = self.ITEM_NAME_OVERRIDES.get(str(source_key), str(source_key))
        if source_key in self.GENERIC_UNSAFE_ITEM_BLOCKS:
            return False
        if source_key in self.STATE_SENSITIVE_SCAN_BLOCKS:
            return False
        return True

    def _is_safe_conversion_target_key(self, item_key: str) -> bool:
        item_key = self.ITEM_NAME_OVERRIDES.get(str(item_key), str(item_key))
        if item_key in self.DEFAULT_EXCLUDED_BLOCKS:
            return False
        return self._is_safe_item_key(item_key)

    def _get_existing_conversion_entries_path(self) -> Optional[Path]:
        candidates = [
            self._get_plugin_directory() / self.CONVERSION_ENTRIES_FILENAME,
            Path.home() / ".blocks_to_storage" / self.CONVERSION_ENTRIES_FILENAME,
        ]

        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except Exception:
                continue

        return None

    def _clear_loaded_conversion_data(self) -> None:
        self._reset_conversion_operation_state()

    def _get_conversion_candidates_path(self) -> Optional[Path]:
        return self._choose_writable_managed_file_path(
            self.CONVERSION_CANDIDATES_FILENAME
        )

    def _conversion_candidate_state_text(self, block) -> str:
        try:
            properties = getattr(block, "properties", {}) or {}
            parts = [
                f"{key}={properties[key]}"
                for key in sorted(properties)
            ]
            value = ";".join(parts)
        except Exception:
            value = ""
        return self._safe_conversion_diagnostic_text(value, 240)

    def _queue_conversion_candidate(
        self,
        block,
        source_key: str,
        target_key: str,
        allow_resolved_family: bool = False,
    ) -> None:
        candidate_recording = getattr(
            self,
            "_operation_record_conversion_candidates",
            None,
        )
        if candidate_recording is None:
            candidate_recording = bool(
                self.record_conversion_candidates.GetValue()
            )
        if not candidate_recording:
            return

        source_key = self._normalize_conversion_identifier(source_key)
        target_key = self._normalize_conversion_identifier(target_key)
        if not source_key or not target_key or source_key == target_key:
            return

        if (
            target_key == "minecraft:bedrock"
            or target_key in self.DEFAULT_EXCLUDED_BLOCKS
            or target_key in self.KNOWN_UNSAFE_ITEM_BLOCKS
        ):
            return

        record_all = False
        try:
            record_all = bool(
                self.record_all_conversion_observations.GetValue()
            )
        except Exception:
            pass

        if (
            not allow_resolved_family
            and not record_all
            and source_key in self.BUILT_IN_RESOLVED_CANDIDATE_SOURCES
        ):
            return

        state_text = self._conversion_candidate_state_text(block)
        self._pending_conversion_candidates[
            (source_key, target_key, state_text)
        ] += 1

    def _write_pending_conversion_candidates(self) -> None:
        self._conversion_candidates_new_record_count = 0
        self._conversion_candidates_updated_record_count = 0
        self._conversion_candidate_observations_added_count = 0
        self._conversion_candidates_existing_record_count = 0
        self._conversion_candidates_total_record_count = 0
        self._conversion_candidates_write_error = ""

        if (
            not self.record_conversion_candidates.GetValue()
            or not self._pending_conversion_candidates
        ):
            return

        destination = self._get_conversion_candidates_path()
        if destination is None:
            self._conversion_candidates_write_error = (
                "No writable data directory was available."
            )
            return

        existing = {}
        if destination.is_file():
            try:
                if (
                    destination.stat().st_size
                    > self.MAX_CONVERSION_CANDIDATES_FILE_BYTES
                ):
                    self._conversion_candidates_write_error = (
                        "Candidate file exceeds the configured size limit."
                    )
                    return

                content = destination.read_text(
                    encoding="utf-8-sig",
                    errors="replace",
                )
                malformed_lines = []
                for line_number, line in enumerate(
                    content.splitlines(),
                    start=1,
                ):
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split("\t")
                    if len(parts) != 4:
                        malformed_lines.append(line_number)
                        continue

                    source_key, target_key, state_text, count_text = parts
                    normalized_source = self._normalize_conversion_identifier(
                        source_key
                    )
                    normalized_target = self._normalize_conversion_identifier(
                        target_key
                    )

                    try:
                        count = int(count_text)
                    except Exception:
                        malformed_lines.append(line_number)
                        continue

                    if (
                        not normalized_source
                        or not normalized_target
                        or normalized_source == normalized_target
                        or count < 0
                    ):
                        malformed_lines.append(line_number)
                        continue

                    existing[
                        (
                            normalized_source,
                            normalized_target,
                            state_text,
                        )
                    ] = count

                if malformed_lines:
                    line_preview = ", ".join(
                        str(line_number)
                        for line_number in malformed_lines[:10]
                    )
                    if len(malformed_lines) > 10:
                        line_preview += ", ..."

                    self._conversion_candidates_write_error = (
                        "Candidate file contains malformed data on line(s) "
                        f"{line_preview}. The existing file was preserved and "
                        "no candidates were written."
                    )
                    return
            except Exception as exc:
                self._conversion_candidates_write_error = str(exc)
                return

        self._conversion_candidates_existing_record_count = len(existing)

        for key, count in self._pending_conversion_candidates.items():
            count = int(count)
            if key in existing:
                self._conversion_candidates_updated_record_count += 1
            else:
                self._conversion_candidates_new_record_count += 1
            existing[key] = existing.get(key, 0) + count
            self._conversion_candidate_observations_added_count += count

        if len(existing) > self.MAX_CONVERSION_CANDIDATES:
            self._conversion_candidates_write_error = (
                "Candidate entry limit reached; no changes were written."
            )
            return

        lines = [
            "# Blocks to Storage inactive conversion candidates",
            "# These observations never affect exports.",
            "# Intentionally excluded and unsafe export targets are not recorded.",
            "# Existing observations are read only so counts can be merged.",
            "# Built-in resolved families are omitted unless advanced recording is enabled",
            "# or an external language-assisted identity recovery is recorded.",
            "# Format version: 1",
            "# source<TAB>target<TAB>source properties<TAB>observations",
            "",
        ]
        for (
            source_key,
            target_key,
            state_text,
        ), count in sorted(existing.items()):
            lines.append(
                f"{source_key}\t{target_key}\t{state_text}\t{count}"
            )

        temporary_path = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=destination.name + ".",
                suffix=".tmp",
                dir=str(destination.parent),
                delete=False,
            ) as handle:
                handle.write("\n".join(lines).rstrip() + "\n")
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except Exception:
                    pass
                temporary_path = Path(handle.name)

            os.replace(str(temporary_path), str(destination))
            self._conversion_candidates_total_record_count = len(existing)
            self._conversion_candidates_write_error = ""
        except Exception as exc:
            self._conversion_candidates_write_error = str(exc)
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except Exception:
                    pass

    def _record_conversion_entry_skip(
        self,
        reason: str,
        line_number: int,
        line_text: str,
        source_key: Optional[str] = None,
    ) -> None:
        self._conversion_entries_skip_reason_counts[reason] = (
            self._conversion_entries_skip_reason_counts.get(reason, 0) + 1
        )

        if source_key is not None:
            self._conversion_entries_skipped[source_key] = reason

        clean_text = " ".join(str(line_text).strip().split())
        if len(clean_text) > self.MAX_CONVERSION_DIAGNOSTIC_TEXT_LENGTH:
            clean_text = (
                clean_text[: self.MAX_CONVERSION_DIAGNOSTIC_TEXT_LENGTH - 3]
                + "..."
            )

        detail = f"Line {line_number}: {reason}"
        if clean_text:
            detail += f" [{clean_text}]"

        if len(self._conversion_entries_skip_details) < self.MAX_CONVERSION_DIAGNOSTIC_DETAILS:
            self._conversion_entries_skip_details.append(detail)
        else:
            self._conversion_entries_skip_detail_overflow += 1

    def _parse_conversion_entries_file(self, path: Path) -> Dict[str, str]:
        try:
            file_size = path.stat().st_size
        except Exception:
            file_size = 0

        if file_size > self.MAX_CONVERSION_ENTRIES_FILE_BYTES:
            raise ValueError(
                f"{self.CONVERSION_ENTRIES_FILENAME} is larger than the allowed 1 MiB limit."
            )

        entries: Dict[str, str] = {}
        content = path.read_text(encoding="utf-8-sig", errors="replace")

        for line_number, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                continue
            if "=" not in line:
                self._record_conversion_entry_skip(
                    "Missing '=' separator.",
                    line_number,
                    line,
                )
                continue

            source_text, item_text = line.split("=", 1)
            source_key = self._normalize_conversion_identifier(source_text)
            item_key = self._normalize_conversion_identifier(item_text)

            if source_key is None:
                self._record_conversion_entry_skip(
                    "Invalid source identifier.",
                    line_number,
                    line,
                )
                continue
            if item_key is None:
                self._record_conversion_entry_skip(
                    "Invalid target identifier.",
                    line_number,
                    line,
                    source_key,
                )
                continue
            if not self._is_safe_conversion_source_key(source_key):
                self._record_conversion_entry_skip(
                    "State-sensitive or generic source requires built-in logic.",
                    line_number,
                    line,
                    source_key,
                )
                continue
            if not self._is_safe_conversion_target_key(item_key):
                self._record_conversion_entry_skip(
                    "Unsafe or excluded target item.",
                    line_number,
                    line,
                    source_key,
                )
                continue

            existing_item = entries.get(source_key)
            if existing_item is not None:
                if existing_item != item_key:
                    self._record_conversion_entry_skip(
                        "Conflicting duplicate source rule.",
                        line_number,
                        line,
                        source_key,
                    )
                continue

            entries[source_key] = item_key
            if len(entries) >= self.MAX_CONVERSION_ENTRIES:
                raise ValueError(
                    f"{self.CONVERSION_ENTRIES_FILENAME} has more than {self.MAX_CONVERSION_ENTRIES:,} usable entries."
                )

        return entries

    def _ensure_conversion_entries_loaded(self) -> bool:
        if self._conversion_entries_prepared:
            return bool(self._conversion_entries)

        self._conversion_entries_prepared = True
        self._conversion_entries = {}
        self._conversion_entries_used = {}
        self._conversion_entries_skipped = {}
        self._conversion_entries_skip_reason_counts = {}
        self._conversion_entries_skip_details = []
        self._conversion_entries_skip_detail_overflow = 0
        self._conversion_entries_load_error = ""
        self._conversion_entries_loaded_count = 0

        if not self.use_conversion_entries.GetValue():
            return False

        conversion_path = self._get_existing_conversion_entries_path()
        if conversion_path is None:
            return False

        try:
            self._conversion_entries = self._parse_conversion_entries_file(conversion_path)
            self._conversion_entries_loaded_count = len(self._conversion_entries)
        except Exception as exc:
            self._conversion_entries = {}
            self._conversion_entries_load_error = str(exc)
            self._conversion_entries_loaded_count = 0

        return bool(self._conversion_entries)

    def _resolve_conversion_entry_item(
        self,
        source_key: Optional[str],
        current_key: Optional[str],
    ) -> Optional[str]:
        if source_key is None or current_key is None:
            return None

        if source_key != current_key:
            return None

        use_conversion_entries = getattr(
            self,
            "_operation_use_conversion_entries",
            None,
        )
        if use_conversion_entries is None:
            use_conversion_entries = bool(
                self.use_conversion_entries.GetValue()
            )
        if not use_conversion_entries:
            return None

        if not self._conversion_entries_prepared:
            self._ensure_conversion_entries_loaded()

        item_key = self._conversion_entries.get(source_key)
        if item_key is None:
            return None
        if not self._is_safe_conversion_target_key(item_key):
            self._record_conversion_entry_skip(
                "Unsafe or excluded target item during resolution.",
                0,
                f"{source_key}={item_key}",
                source_key,
            )
            return None

        self._conversion_entries_used[source_key] = item_key
        return item_key

    def _safe_conversion_diagnostic_text(self, value, max_length: Optional[int] = None) -> str:
        if max_length is None:
            max_length = self.MAX_CONVERSION_DIAGNOSTIC_TEXT_LENGTH

        text_value = str(value)
        text_value = text_value.replace("\r", " ").replace("\n", " ")
        text_value = re.sub(r"[A-Za-z]:\\[^\s,\]\)]+", "[local-path]", text_value)
        text_value = re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s,\]\)]+", "[local-path]", text_value)
        text_value = " ".join(text_value.split())

        if len(text_value) > max_length:
            text_value = text_value[: max_length - 3] + "..."
        return text_value

    def _diagnostic_type_name(self, obj) -> str:
        if obj is None:
            return "None"
        obj_type = type(obj)
        module_name = getattr(obj_type, "__module__", "")
        class_name = getattr(obj_type, "__name__", obj_type.__class__.__name__)
        if module_name and module_name not in ("builtins", "__builtin__"):
            return self._safe_conversion_diagnostic_text(f"{module_name}.{class_name}")
        return self._safe_conversion_diagnostic_text(class_name)

    def _diagnostic_signature_text(self, obj) -> str:
        try:
            signature = inspect.signature(obj)
        except Exception:
            return "signature unavailable"
        return self._safe_conversion_diagnostic_text(signature, 120)

    def _diagnostic_get_attribute(self, obj, attribute_name: str):
        try:
            return True, getattr(obj, attribute_name), ""
        except Exception as exc:
            return False, None, type(exc).__name__

    def _diagnostic_attribute_status(self, obj, attribute_name: str) -> str:
        ok, value, error_name = self._diagnostic_get_attribute(obj, attribute_name)
        if not ok:
            return f"{attribute_name}: unavailable ({error_name})"
        if value is None:
            return f"{attribute_name}: None"
        if callable(value):
            return (
                f"{attribute_name}: callable "
                f"{self._diagnostic_signature_text(value)}"
            )
        return f"{attribute_name}: {self._diagnostic_type_name(value)}"

    def _diagnostic_log_attributes(
        self,
        label: str,
        obj,
        attribute_names: Sequence[str],
    ) -> None:
        self._log(f"  {label} type: {self._diagnostic_type_name(obj)}")
        if obj is None:
            return

        for attribute_name in attribute_names:
            self._log(f"    {self._diagnostic_attribute_status(obj, attribute_name)}")

    def _diagnostic_collect_translation_managers(self) -> List[Tuple[str, object]]:
        candidates: List[Tuple[str, object]] = []
        seen_ids: Set[int] = set()

        roots = [
            ("world", getattr(self, "world", None)),
            ("level_wrapper", getattr(getattr(self, "world", None), "level_wrapper", None)),
            ("canvas", getattr(self, "canvas", None)),
        ]

        manager_attribute_names = (
            "translation_manager",
            "_translation_manager",
            "translator",
            "_translator",
        )

        for root_label, root_obj in roots:
            if root_obj is None:
                continue
            for attribute_name in manager_attribute_names:
                ok, value, _error_name = self._diagnostic_get_attribute(root_obj, attribute_name)
                if not ok or value is None:
                    continue
                object_id = id(value)
                if object_id in seen_ids:
                    continue
                seen_ids.add(object_id)
                candidates.append((f"{root_label}.{attribute_name}", value))

        return candidates

    def _diagnostic_lookup_version_object(self, manager_label: str, manager_obj):
        lookup_attempts = (
            ("get_version", (self._world_platform, self._world_version)),
            ("get_version_container", (self._world_platform, self._world_version)),
            ("get_version", ((self._world_platform, self._world_version),)),
            ("get_version_container", ((self._world_platform, self._world_version),)),
        )

        last_error = "not available"
        for method_name, args in lookup_attempts:
            ok, method_obj, _error_name = self._diagnostic_get_attribute(
                manager_obj,
                method_name,
            )
            if not ok or not callable(method_obj):
                continue
            try:
                return (
                    True,
                    method_obj(*args),
                    f"{manager_label}.{method_name}",
                    "",
                )
            except Exception as exc:
                last_error = type(exc).__name__

        return False, None, manager_label, last_error

    def _log_amulet_conversion_capability_diagnostic(self) -> None:
        self._log("Amulet conversion capability diagnostic:")
        self._log("  Purpose: reports local API capabilities only; no paths or world block data are included.")
        self._log(f"  World platform: {self._safe_conversion_diagnostic_text(self._world_platform)}")
        self._log(f"  World version: {self._safe_conversion_diagnostic_text(self._world_version)}")
        self._log(f"  Canvas dimension: {self._safe_conversion_diagnostic_text(getattr(self.canvas, 'dimension', '(unknown)'))}")

        world_obj = getattr(self, "world", None)
        wrapper_obj = getattr(world_obj, "level_wrapper", None)

        self._diagnostic_log_attributes(
            "world",
            world_obj,
            (
                "get_version_block",
                "get_block",
                "get_chunk",
                "translation_manager",
                "level_wrapper",
            ),
        )
        self._diagnostic_log_attributes(
            "level_wrapper",
            wrapper_obj,
            (
                "platform",
                "version",
                "translation_manager",
                "get_version_block",
                "get_raw_chunk",
                "get_chunk",
            ),
        )

        translation_managers = self._diagnostic_collect_translation_managers()
        if not translation_managers:
            self._log("  Translation manager candidates: none found")
            return

        self._log(f"  Translation manager candidates: {len(translation_managers):,}")
        version_obj = None
        version_source = ""

        for manager_label, manager_obj in translation_managers:
            self._diagnostic_log_attributes(
                manager_label,
                manager_obj,
                (
                    "get_version",
                    "get_version_container",
                    "get_platforms",
                    "get_version_numbers",
                    "platforms",
                    "versions",
                ),
            )
            if version_obj is None:
                ok, candidate_version, source_label, error_name = (
                    self._diagnostic_lookup_version_object(manager_label, manager_obj)
                )
                if ok and candidate_version is not None:
                    version_obj = candidate_version
                    version_source = source_label
                elif error_name:
                    self._log(
                        f"    Version lookup through {source_label}: failed ({error_name})"
                    )

        if version_obj is None:
            self._log("  Version object lookup: unavailable")
            return

        self._log(f"  Version object lookup: success through {version_source}")
        self._diagnostic_log_attributes(
            "version object",
            version_obj,
            (
                "platform",
                "version_number",
                "data_version",
                "block",
                "item",
                "entity",
                "biome",
                "get_item",
                "get_block",
            ),
        )

        for translator_label in ("block", "item", "entity"):
            ok, translator_obj, error_name = self._diagnostic_get_attribute(
                version_obj,
                translator_label,
            )
            if not ok or translator_obj is None:
                self._log(
                    f"  version.{translator_label}: unavailable "
                    f"({error_name or 'missing'})"
                )
                continue

            self._diagnostic_log_attributes(
                f"version.{translator_label}",
                translator_obj,
                (
                    "get_specification",
                    "to_universal",
                    "from_universal",
                    "get_mapping",
                    "has_mapping",
                    "specification",
                ),
            )

    def _diagnostic_get_version_object(self):
        last_error = "not available"
        for manager_label, manager_obj in self._diagnostic_collect_translation_managers():
            ok, version_obj, source_label, error_name = (
                self._diagnostic_lookup_version_object(manager_label, manager_obj)
            )
            if ok and version_obj is not None:
                return version_obj, source_label, ""
            if error_name:
                last_error = error_name
        return None, "", last_error

    def _diagnostic_result_identity(self, value) -> str:
        if value is None:
            return "None"
        namespace = getattr(value, "namespace", None)
        base_name = getattr(value, "base_name", None)
        if namespace and base_name:
            return self._safe_conversion_diagnostic_text(
                f"{namespace}:{base_name}",
                120,
            )
        return self._diagnostic_type_name(value)

    def _diagnostic_call_summary(self, callable_obj, *args) -> Tuple[bool, str]:
        try:
            result = callable_obj(*args)
        except Exception as exc:
            return False, type(exc).__name__
        return True, self._diagnostic_result_identity(result)

    def _reset_amulet_translator_capability_state(self) -> None:
        self._amulet_translator_capabilities = {}
        self._amulet_translator_version_object = None
        self._amulet_translator_version_source = ""
        self._amulet_translator_capabilities_prepared = False
        self._amulet_conversion_audit_entries = {}
        self._amulet_conversion_audit_buckets = collections.defaultdict(set)
        self._amulet_conversion_audit_omitted_identities = set()
        self._amulet_conversion_audit_omitted_overflow = 0
        self._reviewed_amulet_normalizations_used = collections.Counter()
        self._reviewed_amulet_normalization_failures = collections.Counter()
        self._reviewed_amulet_normalization_cache = {}

    def _release_amulet_translator_capability_state(self) -> None:
        self._amulet_translator_capabilities.clear()
        self._amulet_translator_version_object = None
        self._amulet_translator_version_source = ""
        self._amulet_translator_capabilities_prepared = False
        self._amulet_conversion_audit_entries.clear()
        self._amulet_conversion_audit_buckets.clear()
        self._amulet_conversion_audit_omitted_identities.clear()
        self._amulet_conversion_audit_omitted_overflow = 0
        self._reviewed_amulet_normalizations_used.clear()
        self._reviewed_amulet_normalization_failures.clear()
        self._reviewed_amulet_normalization_cache.clear()

    def _prepare_amulet_translator_capabilities(self) -> None:
        if self._amulet_translator_capabilities_prepared:
            return

        self._amulet_translator_capabilities_prepared = True
        version_obj, version_source, error_name = self._diagnostic_get_version_object()
        if version_obj is None:
            self._amulet_translator_capabilities["version"] = (
                False,
                error_name or "not available",
            )
            return

        self._amulet_translator_version_object = version_obj
        self._amulet_translator_version_source = version_source
        self._amulet_translator_capabilities["version"] = (True, version_source)

        block_translator = getattr(version_obj, "block", None)
        item_translator = getattr(version_obj, "item", None)

        block_get_specification = getattr(block_translator, "get_specification", None)
        block_to_universal = getattr(block_translator, "to_universal", None)
        block_from_universal = getattr(block_translator, "from_universal", None)

        self._amulet_translator_capabilities["block.get_specification"] = (
            callable(block_get_specification),
            "callable" if callable(block_get_specification) else "unavailable",
        )
        self._amulet_translator_capabilities["block.to_universal"] = (
            callable(block_to_universal),
            "callable" if callable(block_to_universal) else "unavailable",
        )
        self._amulet_translator_capabilities["block.from_universal"] = (
            callable(block_from_universal),
            "callable" if callable(block_from_universal) else "unavailable",
        )

        item_get_specification = getattr(item_translator, "get_specification", None)
        item_to_universal = getattr(item_translator, "to_universal", None)
        item_from_universal = getattr(item_translator, "from_universal", None)

        if not callable(item_get_specification) or not callable(item_to_universal):
            self._amulet_translator_capabilities["item"] = (
                False,
                "required methods unavailable",
            )
            return

        try:
            item_get_specification("minecraft", "stone")
            if Item is None:
                self._amulet_translator_capabilities["item"] = (
                    False,
                    "item object construction unavailable",
                )
                return
            universal_item = item_to_universal(Item("minecraft", "stone"))
            if callable(item_from_universal) and universal_item is not None:
                item_from_universal(universal_item)
        except Exception as exc:
            self._amulet_translator_capabilities["item"] = (
                False,
                type(exc).__name__,
            )
            return

        self._amulet_translator_capabilities["item"] = (True, "usable")

    def _reviewed_normalization_cache_key(
        self,
        block,
        source_key: str,
    ) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
        properties = getattr(block, "properties", None)
        normalized_properties: List[Tuple[str, str]] = []

        if properties:
            try:
                for property_name, property_value in properties.items():
                    normalized_properties.append(
                        (str(property_name), str(property_value))
                    )
            except Exception:
                normalized_properties = []

        normalized_properties.sort()
        return source_key, tuple(normalized_properties)

    def _resolve_reviewed_amulet_normalization(
        self,
        block,
        source_key: str,
        current_item_key: str,
    ) -> Optional[str]:
        expected_item = self.REVIEWED_AMULET_NORMALIZATIONS.get(source_key)
        if not expected_item or current_item_key != source_key:
            return None

        reviewed_enabled = getattr(
            self,
            "_operation_use_reviewed_amulet_normalization",
            None,
        )
        if reviewed_enabled is None:
            reviewed_enabled = bool(
                self.use_reviewed_amulet_normalization.GetValue()
            )
        if not reviewed_enabled:
            return None

        if source_key not in self.GENERIC_UNSAFE_ITEM_BLOCKS:
            self._reviewed_amulet_normalization_failures[
                "reviewed source is not an unresolved generic identity"
            ] += 1
            return None

        if expected_item == source_key:
            self._reviewed_amulet_normalization_failures[
                "reviewed target does not resolve the generic identity"
            ] += 1
            return None

        if not self._is_safe_conversion_target_key(expected_item):
            self._reviewed_amulet_normalization_failures[
                "reviewed target failed safety validation"
            ] += 1
            return None

        cache_key = self._reviewed_normalization_cache_key(block, source_key)
        if cache_key in self._reviewed_amulet_normalization_cache:
            cached_result = self._reviewed_amulet_normalization_cache[cache_key]
            if cached_result:
                self._reviewed_amulet_normalizations_used[
                    (source_key, cached_result)
                ] += 1
            return cached_result

        self._prepare_amulet_translator_capabilities()
        version_ok, _version_detail = self._amulet_translator_capabilities.get(
            "version",
            (False, "not available"),
        )
        block_supported, block_detail = self._amulet_translator_capabilities.get(
            "block.to_universal",
            (False, "not checked"),
        )

        if (
            not version_ok
            or not block_supported
            or self._amulet_translator_version_object is None
        ):
            reason = block_detail if not block_supported else "version unavailable"
            self._reviewed_amulet_normalization_failures[reason] += 1
            self._reviewed_amulet_normalization_cache[cache_key] = None
            return None

        translator = getattr(
            self._amulet_translator_version_object,
            "block",
            None,
        )
        to_universal = getattr(translator, "to_universal", None)
        from_universal = getattr(translator, "from_universal", None)

        if not callable(to_universal) or not callable(from_universal):
            self._reviewed_amulet_normalization_failures[
                "required block translator methods unavailable"
            ] += 1
            self._reviewed_amulet_normalization_cache[cache_key] = None
            return None

        try:
            translated = to_universal(block)
            universal_block = (
                translated[0]
                if isinstance(translated, tuple) and translated
                else translated
            )
            translated_back = from_universal(universal_block)
            round_trip_block = (
                translated_back[0]
                if isinstance(translated_back, tuple) and translated_back
                else translated_back
            )
            round_trip_identity = self._diagnostic_result_identity(
                round_trip_block
            )
        except Exception as exc:
            self._reviewed_amulet_normalization_failures[
                type(exc).__name__
            ] += 1
            self._reviewed_amulet_normalization_cache[cache_key] = None
            return None

        if round_trip_identity != expected_item:
            self._reviewed_amulet_normalization_failures[
                f"unexpected candidate {round_trip_identity}"
            ] += 1
            self._reviewed_amulet_normalization_cache[cache_key] = None
            return None

        self._reviewed_amulet_normalization_cache[cache_key] = expected_item
        self._reviewed_amulet_normalizations_used[
            (source_key, expected_item)
        ] += 1
        return expected_item

    def _classify_conversion_audit_source(
        self,
        source_key: str,
        item_key: Optional[str],
        conversion_entry_item: Optional[str],
        reviewed_normalization_item: Optional[str] = None,
    ) -> str:
        item_text = str(item_key) if item_key is not None else "(not exported)"

        if reviewed_normalization_item:
            return "reviewed Amulet normalization"

        if conversion_entry_item:
            return "Conversion Entries.BTSP"

        if source_key in self.ITEM_NAME_OVERRIDES:
            return "built-in override"

        if source_key in self.DEFAULT_EXCLUDED_BLOCKS:
            return "excluded block"

        if source_key in self.KNOWN_UNSAFE_ITEM_BLOCKS:
            return "unsafe technical block"

        if source_key in self.GENERIC_UNSAFE_ITEM_BLOCKS and source_key == item_text:
            return "unresolved generic identity"

        if source_key == item_text:
            return "safe identity"

        return "built-in family or state conversion"

    def _track_omitted_amulet_conversion_audit_key(
        self,
        audit_key: Tuple[str, str],
    ) -> None:
        if audit_key in self._amulet_conversion_audit_omitted_identities:
            return

        if (
            len(self._amulet_conversion_audit_omitted_identities)
            < self.MAX_AMULET_CONVERSION_AUDIT_OMITTED_IDENTITIES
        ):
            self._amulet_conversion_audit_omitted_identities.add(audit_key)
        else:
            self._amulet_conversion_audit_omitted_overflow += 1

    def _amulet_conversion_audit_worst_entry_key(
        self,
    ) -> Optional[Tuple[str, str]]:
        for priority in range(7, -1, -1):
            bucket = self._amulet_conversion_audit_buckets.get(priority)
            if bucket:
                return next(iter(bucket))
        return None

    def _store_amulet_conversion_audit_entry(
        self,
        audit_key: Tuple[str, str],
        audit_entry: Tuple[str, str, str, str, str, str],
    ) -> None:
        self._amulet_conversion_audit_entries[audit_key] = audit_entry
        priority = self._amulet_conversion_audit_priority(
            audit_entry[1],
            audit_entry[4],
            audit_entry[5],
        )
        self._amulet_conversion_audit_buckets[priority].add(audit_key)

    def _remove_amulet_conversion_audit_entry(
        self,
        audit_key: Tuple[str, str],
    ) -> None:
        old_entry = self._amulet_conversion_audit_entries.pop(audit_key, None)
        if old_entry is None:
            return

        old_priority = self._amulet_conversion_audit_priority(
            old_entry[1],
            old_entry[4],
            old_entry[5],
        )
        bucket = self._amulet_conversion_audit_buckets.get(old_priority)
        if bucket is not None:
            bucket.discard(audit_key)
            if not bucket:
                self._amulet_conversion_audit_buckets.pop(old_priority, None)

    def _record_amulet_conversion_comparison(
        self,
        block,
        source_key: str,
        item_key: Optional[str],
        conversion_entry_item: Optional[str] = None,
        reviewed_normalization_item: Optional[str] = None,
    ) -> None:
        audit_enabled = getattr(
            self,
            "_operation_conversion_audit_enabled",
            None,
        )
        if audit_enabled is None:
            audit_enabled = bool(
                self.include_amulet_conversion_audit.GetValue()
            )

        candidate_recording = getattr(
            self,
            "_operation_record_conversion_candidates",
            None,
        )
        if candidate_recording is None:
            candidate_recording = bool(
                self.record_conversion_candidates.GetValue()
            )

        if not audit_enabled and not candidate_recording:
            return

        source_key = str(source_key or "")

        if source_key == "minecraft:sapling" and item_key == source_key:
            audit_sapling_item = self._get_sapling_item_name(block)
            if audit_sapling_item:
                item_key = audit_sapling_item

        item_text = str(item_key) if item_key is not None else "(not exported)"
        audit_key = (source_key, item_text)

        if audit_key in self._amulet_conversion_audit_entries:
            return

        resolver_source = self._classify_conversion_audit_source(
            source_key,
            item_key,
            conversion_entry_item,
            reviewed_normalization_item,
        )
        preliminary_priority = self._amulet_conversion_audit_priority(
            resolver_source,
            "(none)",
            "",
        )

        replacement_key = None
        if (
            len(self._amulet_conversion_audit_entries)
            >= self.MAX_AMULET_CONVERSION_AUDIT_ENTRIES
        ):
            worst_key = self._amulet_conversion_audit_worst_entry_key()
            if worst_key is None:
                self._track_omitted_amulet_conversion_audit_key(audit_key)
                return

            worst_entry = self._amulet_conversion_audit_entries[worst_key]
            worst_priority = self._amulet_conversion_audit_priority(
                worst_entry[1],
                worst_entry[4],
                worst_entry[5],
            )
            if preliminary_priority >= worst_priority:
                self._track_omitted_amulet_conversion_audit_key(audit_key)
                return
            replacement_key = worst_key

        self._prepare_amulet_translator_capabilities()
        version_ok, _version_detail = self._amulet_translator_capabilities.get(
            "version",
            (False, "not available"),
        )
        block_supported, block_detail = self._amulet_translator_capabilities.get(
            "block.to_universal",
            (False, "not checked"),
        )

        universal_identity = "(unavailable)"
        round_trip_identity = "(not run)"
        normalization_candidate = "(none)"

        if (
            version_ok
            and block_supported
            and self._amulet_translator_version_object is not None
        ):
            translator = getattr(
                self._amulet_translator_version_object,
                "block",
                None,
            )
            to_universal = getattr(translator, "to_universal", None)
            from_universal = getattr(translator, "from_universal", None)

            try:
                translated = to_universal(block)
                universal_block = (
                    translated[0]
                    if isinstance(translated, tuple) and translated
                    else translated
                )
                universal_identity = self._diagnostic_result_identity(
                    universal_block
                )

                if callable(from_universal) and universal_block is not None:
                    translated_back = from_universal(universal_block)
                    round_trip_block = (
                        translated_back[0]
                        if isinstance(translated_back, tuple) and translated_back
                        else translated_back
                    )
                    round_trip_identity = self._diagnostic_result_identity(
                        round_trip_block
                    )
                    if (
                        source_key in self.GENERIC_UNSAFE_ITEM_BLOCKS
                        and round_trip_identity not in {
                            source_key,
                            "(unavailable)",
                            "(not run)",
                        }
                    ):
                        normalization_candidate = round_trip_identity
            except Exception as exc:
                universal_identity = f"(failed: {type(exc).__name__})"
                round_trip_identity = "(not run)"
        elif not block_supported:
            universal_identity = f"(unusable: {block_detail})"

        if (
            candidate_recording
            and normalization_candidate not in {"(none)", source_key}
            and normalization_candidate.startswith("minecraft:")
        ):
            self._queue_conversion_candidate(
                block,
                source_key,
                normalization_candidate,
            )

        if not audit_enabled:
            return

        generic_family_suffixes = {
            "minecraft:sapling": "_sapling",
            "minecraft:button": "_button",
            "minecraft:pressure_plate": "_pressure_plate",
            "minecraft:trapdoor": "_trapdoor",
        }
        expected_suffix = generic_family_suffixes.get(source_key)

        if (
            expected_suffix
            and item_text == source_key
            and round_trip_identity.startswith("minecraft:")
            and round_trip_identity.endswith(expected_suffix)
            and round_trip_identity != source_key
        ):
            item_text = round_trip_identity
            item_key = round_trip_identity
            audit_key = (source_key, item_text)
            resolver_source = "built-in family or state conversion"
            normalization_candidate = "(none)"

            if audit_key in self._amulet_conversion_audit_entries:
                return

        audit_outcome = self._amulet_conversion_audit_outcome(
            source_key,
            item_text,
            resolver_source,
            round_trip_identity,
            normalization_candidate,
        )
        audit_entry = (
            item_text,
            resolver_source,
            universal_identity,
            round_trip_identity,
            normalization_candidate,
            audit_outcome,
        )
        final_priority = self._amulet_conversion_audit_priority(
            resolver_source,
            normalization_candidate,
            audit_outcome,
        )

        if (
            replacement_key is None
            and len(self._amulet_conversion_audit_entries)
            >= self.MAX_AMULET_CONVERSION_AUDIT_ENTRIES
        ):
            worst_key = self._amulet_conversion_audit_worst_entry_key()
            if worst_key is None:
                self._track_omitted_amulet_conversion_audit_key(audit_key)
                return

            worst_entry = self._amulet_conversion_audit_entries[worst_key]
            worst_priority = self._amulet_conversion_audit_priority(
                worst_entry[1],
                worst_entry[4],
                worst_entry[5],
            )
            if final_priority >= worst_priority:
                self._track_omitted_amulet_conversion_audit_key(audit_key)
                return
            replacement_key = worst_key

        if replacement_key is not None:
            self._remove_amulet_conversion_audit_entry(replacement_key)
            self._track_omitted_amulet_conversion_audit_key(replacement_key)

        self._store_amulet_conversion_audit_entry(audit_key, audit_entry)

    def _log_reviewed_amulet_normalization_summary(self) -> None:
        enabled = self.use_reviewed_amulet_normalization.GetValue()
        self._log("Conversion authority: plugin-controlled")
        self._log(
            "Conversion priority: built-in state / integrated identity / override "
            "-> unresolved external entry -> plugin-reviewed Amulet fallback -> safe skip"
        )
        self._log(f"Plugin-reviewed conversion fallback enabled: {enabled}")
        self._log(
            f"Reviewed Amulet normalizations used: "
            f"{sum(self._reviewed_amulet_normalizations_used.values()):,}"
        )

        for (source_key, item_key), count in sorted(
            self._reviewed_amulet_normalizations_used.items()
        ):
            self._log(
                f"  {source_key} -> {item_key}: {count:,}"
            )

        failure_count = sum(
            self._reviewed_amulet_normalization_failures.values()
        )
        self._log(
            f"Reviewed Amulet normalization fallbacks: {failure_count:,}"
        )
        for reason, count in sorted(
            self._reviewed_amulet_normalization_failures.items()
        ):
            self._log(f"  {reason}: {count:,}")

    def _conversion_audit_sign_item_key(
        self,
        block_key: str,
    ) -> Optional[str]:
        if not block_key or ":" not in block_key:
            return None

        namespace, base_name = block_key.split(":", 1)
        if namespace != "minecraft":
            return None

        normalized_name = base_name.replace("darkoak", "dark_oak")

        if normalized_name in {"sign", "standing_sign", "wall_sign"}:
            return "minecraft:oak_sign"

        suffixes = (
            "_standing_sign",
            "_wall_sign",
        )
        for suffix in suffixes:
            if normalized_name.endswith(suffix):
                wood_type = normalized_name[:-len(suffix)]
                if wood_type == "oak":
                    return "minecraft:oak_sign"
                candidate = self.SIGN_ITEM_BY_TYPE.get(wood_type)
                if candidate:
                    return candidate

        return None

    def _conversion_audit_coral_fan_item_key(
        self,
        block_key: str,
    ) -> Optional[str]:
        if not block_key or ":" not in block_key:
            return None

        namespace, base_name = block_key.split(":", 1)
        if namespace != "minecraft":
            return None

        normalized_name = base_name.strip().lower()

        if normalized_name.endswith("_coral_wall_fan"):
            normalized_name = normalized_name.replace(
                "_coral_wall_fan",
                "_coral_fan",
            )
            return f"minecraft:{normalized_name}"

        return None

    def _conversion_audit_alias_equivalent(
        self,
        first_key: str,
        second_key: str,
    ) -> bool:
        if first_key == second_key:
            return True

        first_coral_fan_item = self._conversion_audit_coral_fan_item_key(
            first_key
        )
        second_coral_fan_item = self._conversion_audit_coral_fan_item_key(
            second_key
        )
        if first_coral_fan_item and first_coral_fan_item == second_key:
            return True
        if second_coral_fan_item and second_coral_fan_item == first_key:
            return True
        if (
            first_coral_fan_item
            and second_coral_fan_item
            and first_coral_fan_item == second_coral_fan_item
        ):
            return True

        first_sign_item = self._conversion_audit_sign_item_key(first_key)
        second_sign_item = self._conversion_audit_sign_item_key(second_key)
        if first_sign_item and first_sign_item == second_key:
            return True
        if second_sign_item and second_sign_item == first_key:
            return True
        if (
            first_sign_item
            and second_sign_item
            and first_sign_item == second_sign_item
        ):
            return True

        first_target = self.ITEM_NAME_OVERRIDES.get(first_key)
        second_target = self.ITEM_NAME_OVERRIDES.get(second_key)

        if first_target == second_key or second_target == first_key:
            return True

        if first_target and second_target and first_target == second_target:
            return True

        return False

    def _conversion_audit_expected_inventory_conversion(
        self,
        source_key: str,
        item_text: str,
        round_trip_identity: str,
        resolver_source: str,
    ) -> bool:
        if resolver_source not in {
            "built-in override",
            "built-in family or state conversion",
            "Conversion Entries.BTSP",
        }:
            return False

        if round_trip_identity == source_key and item_text != source_key:
            return True

        if self.ITEM_NAME_OVERRIDES.get(source_key) == item_text:
            return True

        return False

    def _amulet_conversion_audit_outcome(
        self,
        source_key: str,
        item_text: str,
        resolver_source: str,
        round_trip_identity: str,
        normalization_candidate: str,
    ) -> str:
        if resolver_source == "reviewed Amulet normalization":
            return "reviewed normalization used"

        if resolver_source == "unresolved generic identity":
            if normalization_candidate != "(none)":
                return "unresolved candidate"
            return "unresolved without candidate"

        if resolver_source in {
            "built-in override",
            "built-in family or state conversion",
            "Conversion Entries.BTSP",
        }:
            if round_trip_identity == item_text:
                return "Amulet confirms plugin result"

            if self._conversion_audit_alias_equivalent(
                item_text,
                round_trip_identity,
            ):
                return "alias-aware confirmation"

            if self._conversion_audit_expected_inventory_conversion(
                source_key,
                item_text,
                round_trip_identity,
                resolver_source,
            ):
                return "expected inventory conversion"

            return "Amulet differs from plugin result"

        if resolver_source in {
            "excluded block",
            "unsafe technical block",
        }:
            return "not exportable"

        if round_trip_identity == item_text:
            return "identity confirmed"

        if self._conversion_audit_alias_equivalent(
            item_text,
            round_trip_identity,
        ):
            return "alias-aware identity confirmation"

        return "identity differs after translation"

    def _amulet_conversion_audit_priority(
        self,
        resolver_source: str,
        normalization_candidate: str,
        audit_outcome: str = "",
    ) -> int:
        if resolver_source == "reviewed Amulet normalization":
            return 0
        if resolver_source == "unresolved generic identity":
            return 1
        if audit_outcome == "Amulet differs from plugin result":
            return 2
        if normalization_candidate != "(none)":
            return 3
        if resolver_source == "Conversion Entries.BTSP":
            return 4
        if audit_outcome in {
            "alias-aware confirmation",
            "expected inventory conversion",
            "Amulet confirms plugin result",
        }:
            return 5
        if resolver_source in {
            "excluded block",
            "unsafe technical block",
        }:
            return 6
        return 7

    def _amulet_conversion_audit_sort_key(self, entry):
        (source_key, item_key), (
            _item_text,
            resolver_source,
            _universal_identity,
            _round_trip_identity,
            normalization_candidate,
            audit_outcome,
        ) = entry
        return (
            self._amulet_conversion_audit_priority(
                resolver_source,
                normalization_candidate,
                audit_outcome,
            ),
            str(source_key),
            str(item_key),
        )

    def _log_amulet_conversion_decision_summary(self) -> None:
        outcome_counts = collections.Counter(
            entry[5]
            for entry in self._amulet_conversion_audit_entries.values()
        )

        reviewed_used = outcome_counts.get(
            "reviewed normalization used",
            0,
        )
        unresolved_candidates = outcome_counts.get(
            "unresolved candidate",
            0,
        )
        unresolved_without_candidate = outcome_counts.get(
            "unresolved without candidate",
            0,
        )
        plugin_confirmations = (
            outcome_counts.get("Amulet confirms plugin result", 0)
            + outcome_counts.get("alias-aware confirmation", 0)
            + outcome_counts.get("expected inventory conversion", 0)
        )
        true_differences = outcome_counts.get(
            "Amulet differs from plugin result",
            0,
        )
        identity_confirmations = (
            outcome_counts.get("identity confirmed", 0)
            + outcome_counts.get("alias-aware identity confirmation", 0)
        )
        identity_differences = outcome_counts.get(
            "identity differs after translation",
            0,
        )
        not_exportable = outcome_counts.get(
            "not exportable",
            0,
        )

        self._log("Conversion decision summary:")
        self._log(f"  Reviewed normalizations used: {reviewed_used:,}")
        self._log(
            f"  Unresolved candidates: {unresolved_candidates:,}"
        )
        self._log(
            "  Unresolved without candidate: "
            f"{unresolved_without_candidate:,}"
        )
        self._log(
            f"  Confirmed plugin conversions: {plugin_confirmations:,}"
        )
        self._log(f"  True plugin / Amulet differences: {true_differences:,}")
        self._log(
            f"  Confirmed safe identities: {identity_confirmations:,}"
        )
        self._log(
            f"  Identity differences after translation: "
            f"{identity_differences:,}"
        )
        self._log(f"  Not exportable: {not_exportable:,}")

    def _log_amulet_conversion_comparison_audit(self) -> None:
        self._log("Amulet conversion comparison audit:")
        self._log(
            "  Purpose: report-only comparison of unique scanned conversions; "
            "exported items are not changed."
        )
        self._log_amulet_conversion_decision_summary()
        self._log("")
        self._log(
            f"  Highest-priority unique comparisons retained: "
            f"{len(self._amulet_conversion_audit_entries):,}"
        )
        active_bucket_count = sum(
            1 for bucket in self._amulet_conversion_audit_buckets.values()
            if bucket
        )
        self._log(
            f"  Active audit priority buckets: {active_bucket_count:,}"
        )

        normalization_candidates = 0

        prioritized_entries = sorted(
            self._amulet_conversion_audit_entries.items(),
            key=self._amulet_conversion_audit_sort_key,
        )

        for (source_key, _item_key), (
            item_text,
            resolver_source,
            universal_identity,
            round_trip_identity,
            normalization_candidate,
            audit_outcome,
        ) in prioritized_entries:
            self._log(
                f"  {source_key} -> {item_text} [{resolver_source}]"
            )
            self._log(
                f"    Amulet universal block: {universal_identity}"
            )
            self._log(
                f"    Amulet round-trip block: {round_trip_identity}"
            )
            self._log(
                f"    Audit outcome: {audit_outcome}"
            )

            if normalization_candidate != "(none)":
                normalization_candidates += 1
                if resolver_source in {
                    "reviewed Amulet normalization",
                    "unresolved generic identity",
                }:
                    self._log(
                        f"    Normalization candidate: {normalization_candidate}"
                    )
                    if resolver_source == "reviewed Amulet normalization":
                        self._log(
                            "    Candidate status: reviewed and used for export"
                        )
                    else:
                        self._log(
                            "    Candidate status: review only; not used for export"
                        )

        self._log(
            f"  Normalization candidates found: {normalization_candidates:,}"
        )

        omitted_unique = len(
            self._amulet_conversion_audit_omitted_identities
        )
        if omitted_unique:
            self._log(
                f"  Additional unique comparisons omitted by limit: "
                f"{omitted_unique:,}"
            )
        if self._amulet_conversion_audit_omitted_overflow:
            self._log(
                "  Additional omitted identities beyond tracking limit: "
                f"{self._amulet_conversion_audit_omitted_overflow:,}"
            )

    def _log_amulet_translator_validation_probe(self) -> None:
        self._log("Amulet translator validation probe:")
        self._log(
            "  Purpose: read-only local translator checks; conversion behavior "
            "is not changed."
        )

        self._prepare_amulet_translator_capabilities()
        version_ok, version_detail = self._amulet_translator_capabilities.get(
            "version",
            (False, "not available"),
        )
        if not version_ok or self._amulet_translator_version_object is None:
            self._log(f"  Version object: unavailable ({version_detail})")
            return

        self._log(
            f"  Version object source: "
            f"{self._amulet_translator_version_source}"
        )

        for capability_name in (
            "block.get_specification",
            "block.to_universal",
            "block.from_universal",
            "item",
        ):
            supported, detail = self._amulet_translator_capabilities.get(
                capability_name,
                (False, "not checked"),
            )
            self._log(
                f"  Cached capability {capability_name}: "
                f"{'usable' if supported else 'unusable'} ({detail})"
            )

        version_obj = self._amulet_translator_version_object
        block_translator = getattr(version_obj, "block", None)
        block_get_specification = getattr(
            block_translator,
            "get_specification",
            None,
        )
        block_to_universal = getattr(block_translator, "to_universal", None)
        block_from_universal = getattr(block_translator, "from_universal", None)

        probe_blocks = (
            "minecraft:stone",
            "minecraft:grass_block",
            "minecraft:melon",
            "minecraft:redstone_wire",
            "minecraft:oak_standing_sign",
        )

        for block_identifier in probe_blocks:
            block_namespace, block_base_name = block_identifier.split(":", 1)
            self._log(f"  Probe {block_identifier}:")

            if callable(block_get_specification):
                ok, detail = self._diagnostic_call_summary(
                    block_get_specification,
                    block_namespace,
                    block_base_name,
                )
                self._log(
                    f"    block.get_specification: "
                    f"{'success' if ok else 'failed'} ({detail})"
                )
            else:
                self._log("    block.get_specification: unavailable")

            universal_block = None
            if callable(block_to_universal):
                try:
                    translated = block_to_universal(
                        Block(block_namespace, block_base_name)
                    )
                    universal_block = (
                        translated[0]
                        if isinstance(translated, tuple) and translated
                        else translated
                    )
                    self._log(
                        "    block.to_universal: success "
                        f"({self._diagnostic_result_identity(universal_block)})"
                    )
                except Exception as exc:
                    self._log(
                        f"    block.to_universal: failed "
                        f"({type(exc).__name__})"
                    )
            else:
                self._log("    block.to_universal: unavailable")

            if universal_block is not None and callable(block_from_universal):
                try:
                    translated = block_from_universal(universal_block)
                    round_trip_block = (
                        translated[0]
                        if isinstance(translated, tuple) and translated
                        else translated
                    )
                    self._log(
                        "    block.from_universal: success "
                        f"({self._diagnostic_result_identity(round_trip_block)})"
                    )
                except Exception as exc:
                    self._log(
                        f"    block.from_universal: failed "
                        f"({type(exc).__name__})"
                    )
            elif not callable(block_from_universal):
                self._log("    block.from_universal: unavailable")
            else:
                self._log("    block.from_universal: not run")

        item_supported, item_detail = self._amulet_translator_capabilities.get(
            "item",
            (False, "not checked"),
        )
        if not item_supported:
            self._log(
                "  Item translator checks skipped after the cached probe marked "
                f"the translator unusable ({item_detail})."
            )

    def _log_conversion_entries_summary(self) -> None:
        enabled = self.use_conversion_entries.GetValue()
        self._log(f"Conversion Entries rules enabled: {enabled}")
        if not enabled:
            return

        self._log(
            f"Conversion Entries file found: "
            f"{self._get_existing_conversion_entries_path() is not None}"
        )
        self._log("Conversion Entries file modified by plugin: False")
        self._log(
            f"Conversion Entries rules loaded: "
            f"{self._conversion_entries_loaded_count:,}"
        )
        self._log(
            f"Conversion Entries rules used: "
            f"{len(self._conversion_entries_used):,}"
        )

        if self._unresolved_write_attempt_counts:
            self._log("")
            self._log("Unresolved item write attempts:")
            for unresolved_name in sorted(
                self._unresolved_write_attempt_counts.keys()
            ):
                unresolved_count = self._unresolved_write_attempt_counts[
                    unresolved_name
                ]
                self._log(
                    f"  {unresolved_name} -> {unresolved_count:,} "
                    "(in-game verification required)"
                )

        if self._conversion_entries_load_error:
            self._log(
                f"Conversion Entries load issue: "
                f"{self._conversion_entries_load_error}"
            )

        skipped_count = sum(self._conversion_entries_skip_reason_counts.values())
        if skipped_count:
            self._log(
                f"Conversion Entries rules skipped: "
                f"{skipped_count:,}"
            )
            self._log("Conversion Entries skipped rules by reason:")
            for reason in sorted(self._conversion_entries_skip_reason_counts):
                count = self._conversion_entries_skip_reason_counts[reason]
                self._log(f"  {reason}: {count:,}")

            if self._conversion_entries_skip_details:
                self._log("Conversion Entries skipped rule details:")
                for detail in self._conversion_entries_skip_details:
                    self._log(f"  {detail}")

            if self._conversion_entries_skip_detail_overflow:
                self._log(
                    "  Additional rejected rule details omitted: "
                    f"{self._conversion_entries_skip_detail_overflow:,}"
                )

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

    def _get_selected_language_file(
        self,
        require_enabled: bool = True,
    ) -> Optional[Path]:
        if require_enabled and not (
            self.use_installed_language_data.GetValue()
            or self.save_found_language_entries.GetValue()
        ):
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
        self._external_language_loaded_path = ""
        self._external_language_load_error = ""
        self._external_language_loaded_count = 0

        self._load_found_entries_file()

        installed_language_requested = (
            self.use_installed_language_data.GetValue()
            or self.save_found_language_entries.GetValue()
        )
        if not installed_language_requested:
            return bool(self._found_entries_aliases)

        language_path = self._get_selected_language_file(
            require_enabled=False,
        )
        if language_path is None:
            self._external_language_load_error = "Language file not found."
            return bool(self._found_entries_aliases)

        try:

            (
                self._external_language_aliases,
                _,
            ) = self._parse_display_name_file(language_path)
            self._external_language_loaded_path = str(language_path)
            self._external_language_loaded_count = len(
                self._external_language_aliases
            )
        except Exception as exc:
            self._external_language_aliases = {}
            self._external_language_loaded_path = ""
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

    def _queue_missing_installed_language_entries(
        self,
        require_save_setting: bool = True,
    ) -> int:
        self._found_entries_sync_queued_count = 0

        if (
            require_save_setting
            and not self.save_found_language_entries.GetValue()
        ):
            return 0

        if not self._external_language_aliases:
            return 0

        existing_aliases = dict(self._found_entries_aliases)
        existing_raw_entries = dict(self._found_entries_raw_entries)

        existing_path = self._get_existing_found_entries_path()
        if existing_path is not None:
            try:
                file_aliases, file_raw_entries = self._parse_display_name_file(
                    existing_path
                )
                for alias, value in file_aliases.items():
                    existing_aliases.setdefault(alias, value)
                for language_key, display_name in file_raw_entries.items():
                    existing_raw_entries.setdefault(language_key, display_name)
            except Exception:

                pass

        queued_count = 0
        for alias, (
            language_key,
            display_name,
        ) in sorted(self._external_language_aliases.items()):
            if alias in self.BEDROCK_EN_US_DISPLAY_NAMES:
                continue
            if alias in existing_aliases:
                continue
            if language_key in existing_raw_entries:
                continue
            if language_key in self._pending_found_entries:
                continue
            if not self._is_safe_language_value(display_name):
                continue

            self._pending_found_entries[str(language_key)] = str(display_name)
            queued_count += 1

        self._found_entries_sync_queued_count = queued_count
        return queued_count

    def _synchronize_found_entries_from_language_file(self) -> None:
        self._clear_loaded_display_name_data()
        language_path = self._get_selected_language_file(
            require_enabled=False,
        )

        if language_path is None:
            _show_dark_message(
                "No readable Minecraft en_US.lang file was found.\n\n"
                "Choose the file in Display-name data or enable automatic "
                "detection, then try again.",
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        try:

            (
                self._external_language_aliases,
                _,
            ) = self._parse_display_name_file(language_path)
            self._external_language_loaded_path = str(language_path)
            self._external_language_loaded_count = len(
                self._external_language_aliases
            )
            self._external_language_prepared = True
        except Exception as exc:
            self._external_language_load_error = str(exc)
            _show_dark_message(
                f"Could not read the selected Minecraft language file.\n\n"
                f"Reason: {exc}",
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        queued_count = self._queue_missing_installed_language_entries(
            require_save_setting=False,
        )
        self._write_pending_found_entries()

        if self._found_entries_write_error:
            _show_dark_message(
                f"The language file was scanned, but "
                f"{self.FOUND_ENTRIES_FILENAME} could not be updated.\n\n"
                f"Reason: {self._found_entries_write_error}",
                "Blocks to Storage",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        added_count = self._found_entries_written_count
        if queued_count == 0:
            result_text = (
                f"{self.FOUND_ENTRIES_FILENAME} is already up to date."
            )
        else:
            result_text = (
                f"Added {added_count:,} new display-name "
                f"entr{'y' if added_count == 1 else 'ies'} to "
                f"{self.FOUND_ENTRIES_FILENAME}."
            )

        _show_dark_message(
            f"Scanned {self._external_language_loaded_count:,} relevant "
            f"language aliases from:\n{language_path}\n\n{result_text}",
            "Blocks to Storage",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

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
                f"Installed language entries queued for cache sync: "
                f"{self._found_entries_sync_queued_count:,}"
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

        item_alias = self._normalize_display_name_for_audit(item_name)
        actual_alias = self._normalize_display_name_for_audit(actual_name)
        for legacy_lookup_alias in (item_alias, actual_alias):
            raw_candidates.extend(
                self.LEGACY_DISPLAY_NAME_ALIASES.get(
                    legacy_lookup_alias,
                    (),
                )
            )

        if self._is_banner_item_key(item_name):
            banner_damage, banner_type = self._get_banner_item_parts(item_name)

            if banner_type == 1:
                raw_candidates.extend(
                    (
                        "banner_illager_captain",
                        "ominous_banner",
                    )
                )
            else:
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
            banner_damage, banner_type = self._get_banner_item_parts(item_name)

            if banner_type == 1:
                return self._normalize_abc_sort_text("ominous_banner")

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
            color = _shulker_color_value(
                self.nested_shulker_color_choice.GetStringSelection()
            )
        except Exception:
            pass

        if color == "default":
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

    def _make_scan_air(self) -> Block:
        return Block("minecraft", "air")

    def _get_block_for_scan(
        self,
        x: int,
        y: int,
        z: int,
        chunk_cache: Dict[Tuple[int, int], object],
    ):
        if self.fast_direct_scan.GetValue() and not self._fast_scan_failed:
            cx, cz = self._chunk_coords(x, z)
            key = (cx, cz)

            if key in self._missing_scan_chunks:
                return self._make_scan_air()

            try:
                if key not in chunk_cache:
                    chunk_cache[key] = self._get_chunk(cx, cz)

                chunk = chunk_cache[key]
                return self._get_block_direct_from_chunk(chunk, x, y, z)
            except Exception as exc:
                error_text = str(exc)

                if error_text.startswith("Could not load chunk"):
                    self._missing_scan_chunks.add(key)
                    chunk_cache.pop(key, None)
                    return self._make_scan_air()

                self._fast_scan_failed = True
                self._fast_scan_fail_reason = error_text
                self._log(
                    "Fast direct chunk scan failed. Falling back to safe scan. "
                    f"Reason: {exc}"
                )

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
        self._missing_scan_chunks = set()
        self._unresolved_write_attempt_counts = collections.defaultdict(int)
        self._built_in_scan_identity_recoveries = collections.defaultdict(int)
        self._installed_language_scan_identity_recoveries = collections.defaultdict(int)
        self._found_entry_scan_identity_recoveries = collections.defaultdict(int)
        self._scan_identity_diagnostics = collections.defaultdict(int)
        self._scan_identity_diagnostic_overflow = 0

        min_x = min_y = min_z = None
        max_x = max_y = max_z = None

        scanned_positions = 0
        exportable_source_blocks = 0
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
            scan_block_key = raw_scan_key
            export_key, skipped_key = self._classify_block(
                block,
                source_key=raw_scan_key,
            )

            raw_scan_needs_safe_lookup = self._needs_safe_block_lookup(
                raw_scan_key
            )
            ambiguous_lookup_needed = (
                export_key in self.AMBIGUOUS_FAST_SCAN_BLOCKS
                or raw_scan_key in self.AMBIGUOUS_FAST_SCAN_BLOCKS
            )

            export_needs_safe_lookup = (
                raw_scan_needs_safe_lookup
                if export_key == raw_scan_key
                else self._needs_safe_block_lookup(export_key)
            )
            skipped_needs_safe_lookup = (
                False
                if skipped_key is None
                else (
                    raw_scan_needs_safe_lookup
                    if skipped_key == raw_scan_key
                    else self._needs_safe_block_lookup(skipped_key)
                )
            )
            needs_safe_lookup = (
                raw_scan_needs_safe_lookup
                or ambiguous_lookup_needed
                or export_needs_safe_lookup
                or skipped_needs_safe_lookup
            )

            if needs_safe_lookup:
                try:
                    safe_block, safe_block_entity = (
                        self._get_block_and_entity_safe_for_scan(x, y, z)
                    )
                    safe_scan_key = self._get_namespaced_block_name(safe_block)
                    safe_export_key, safe_skipped_key = self._classify_block(
                        safe_block,
                        safe_block_entity,
                        source_key=safe_scan_key,
                    )
                    (
                        recovered_item_key,
                        recovery_source,
                    ) = self._resolve_scan_identity(
                        block,
                        raw_scan_key,
                        safe_export_key or safe_skipped_key,
                    )

                    self._record_scan_identity_result(
                        block,
                        raw_scan_key,
                        safe_block,
                        safe_export_key or safe_skipped_key,
                        recovered_item_key,
                        recovery_source,
                    )

                    if recovered_item_key is not None:

                        if recovery_source in (
                            self.FOUND_ENTRIES_FILENAME,
                            self.INSTALLED_LANGUAGE_SOURCE_LABEL,
                        ):
                            self._queue_conversion_candidate(
                                block,
                                raw_scan_key,
                                recovered_item_key,
                                allow_resolved_family=True,
                            )
                        scan_block = block
                        export_key = recovered_item_key
                        skipped_key = None
                        if ambiguous_lookup_needed:
                            self._ambiguous_fast_scan_fallbacks += 1
                    elif safe_export_key is not None or safe_skipped_key is not None:
                        scan_block = safe_block
                        scan_block_key = safe_scan_key
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

            extra_export_items = []
            if (
                scan_block_key == "minecraft:candle_cake"
                or str(scan_block_key or "").endswith("_candle_cake")
            ):
                extra_export_items = self._get_extra_export_items_for_block(
                    scan_block,
                    scan_block_key,
                )

            if (
                skipped_key == "minecraft:bedrock"
                and self._operation_preserve_bedrock
            ):
                protected_positions.add((x, y, z))

            if skipped_key is not None:
                skipped_reason = self._get_skipped_block_reason(skipped_key)
                skipped_counts[skipped_key] += 1
                skipped_by_reason[skipped_reason][skipped_key] += 1
                if extra_export_items:
                    exportable_source_blocks += 1
                for extra_item_name, extra_amount in extra_export_items:
                    self._record_export_count(counts, extra_item_name, extra_amount)
                continue

            if export_key is not None:
                exportable_source_blocks += 1
                export_amount = (
                    self._get_candle_export_amount(scan_block, export_key)
                    if export_key in self.CANDLE_ITEM_BLOCKS
                    else 1
                )
                if "slab" in str(raw_scan_key or ""):
                    export_amount *= (
                        self._get_raw_double_slab_export_multiplier(
                            block,
                            raw_scan_key,
                            export_key,
                        )
                    )
                self._record_export_count(counts, export_key, export_amount)

                if (
                    export_key in self.GENERIC_UNSAFE_ITEM_BLOCKS
                    and self._operation_attempt_unresolved_item_writes
                ):
                    self._unresolved_write_attempt_counts[export_key] += export_amount

            for extra_item_name, extra_amount in extra_export_items:
                self._record_export_count(counts, extra_item_name, extra_amount)

        if min_x is None:
            return (
                counts,
                skipped_counts,
                skipped_by_reason,
                protected_positions,
                None,
                scanned_positions,
                exportable_source_blocks,
            )

        return (
            counts,
            skipped_counts,
            skipped_by_reason,
            protected_positions,
            (min_x, min_y, min_z, max_x, max_y, max_z),
            scanned_positions,
            exportable_source_blocks,
        )

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
            shulker_color = _shulker_color_value(
                self.shulker_color_choice.GetStringSelection()
            )
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
        if self._operation_running:
            return

        self._set_tooltips_suspended(True)
        self._clear_log()
        self._reset_report()
        self._update_option_visibility()
        if not self._confirm_large_selection():
            self._log("Operation cancelled before start by large selection warning.")
            self._finalize_report()
            try:
                self.status.SetLabel("Cancelled before start.")
            except Exception:
                pass
            self._set_tooltips_suspended(False)
            return

        generation = self._begin_operation_ui()
        self._active_operation_ui_generation = generation
        try:
            self.canvas.run_operation(
                self._run_export_operation_guarded,
                title="Blocks to Storage",
                msg="Moving selected blocks into storage...",
                throw_exceptions=False,
            )
        except TypeError:
            try:
                self.canvas.run_operation(
                    self._run_export_operation_guarded,
                    "Blocks to Storage",
                    "Moving selected blocks into storage...",
                    False,
                )
            except Exception as exc:
                self._log(f"Operation failed to start: {exc}")
                self._finalize_report()
                self._operation_running = False
                self._finish_operation_ui("Failed to start. Review the report.", generation)
        except Exception as exc:
            self._log(f"Operation failed to start: {exc}")
            self._finalize_report()
            self._operation_running = False
            self._finish_operation_ui("Failed to start. Review the report.", generation)

    def _run_export_operation_guarded(self):
        try:
            self._run_export_operation()
        except Exception as exc:
            self._log("")
            self._log(f"Operation failed during preparation: {exc}")
            try:
                self._finalize_report()
            finally:
                self._release_operation_display_name_caches()
                self._release_operation_conversion_caches()
                self._release_amulet_translator_capability_state()
                try:
                    wx.CallAfter(
                        self._finish_operation_ui,
                        "Operation failed. Review the report.",
                        self._active_operation_ui_generation,
                    )
                except Exception:
                    self._finish_operation_ui(
                        "Operation failed. Review the report.",
                        self._active_operation_ui_generation,
                    )

    def _run_export_operation(self):
        total_start = time.perf_counter()
        operation_failed = False
        self._reset_external_language_operation_state()
        self._reset_conversion_operation_state()
        self._reset_amulet_translator_capability_state()

        self._operation_include_unusual = bool(
            self.include_unusual.GetValue()
        )
        self._operation_use_conversion_entries = bool(
            self.use_conversion_entries.GetValue()
        )
        self._operation_use_reviewed_amulet_normalization = bool(
            self.use_reviewed_amulet_normalization.GetValue()
        )
        self._operation_conversion_audit_enabled = bool(
            self.include_amulet_conversion_audit.GetValue()
        )
        self._operation_record_conversion_candidates = bool(
            self.record_conversion_candidates.GetValue()
        )
        self._operation_conversion_tracking_enabled = (
            self._operation_conversion_audit_enabled
            or self._operation_record_conversion_candidates
        )
        self._operation_external_scan_identity_enabled = bool(
            self.use_found_entries_cache.GetValue()
            or self.use_installed_language_data.GetValue()
        )
        self._operation_attempt_unresolved_item_writes = bool(
            self.attempt_unresolved_item_writes.GetValue()
        )
        self._operation_preserve_bedrock = bool(
            self.preserve_bedrock.GetValue()
        )
        if (
            self._operation_external_scan_identity_enabled
            or self.save_found_language_entries.GetValue()
        ):
            self._ensure_external_language_data_loaded()

        if self.save_found_language_entries.GetValue():
            self._queue_missing_installed_language_entries()
            self._write_pending_found_entries()

        if self._operation_use_conversion_entries:
            self._ensure_conversion_entries_loaded()

        try:
            self._log("Blocks to Storage Export Report")
            self._log(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("")

            if (
                self.use_installed_language_data.GetValue()
                or self.save_found_language_entries.GetValue()
            ):
                self._log(
                    f"Installed language aliases prepared before scan: "
                    f"{self._external_language_loaded_count:,}"
                )
                if self.save_found_language_entries.GetValue():
                    self._log(
                        f"Found Entries pre-scan update: "
                        f"{self._found_entries_written_count:,} new entr"
                        f"{'y' if self._found_entries_written_count == 1 else 'ies'}"
                    )
                if self._external_language_load_error:
                    self._log(
                        f"Installed language preparation issue: "
                        f"{self._external_language_load_error}"
                    )
                if self._found_entries_write_error:
                    self._log(
                        f"{self.FOUND_ENTRIES_FILENAME} pre-scan write issue: "
                        f"{self._found_entries_write_error}"
                    )
                self._log("")

            self._log("Starting block scan...")
            self._log(f"World wrapper: {self._world_platform} / {self._world_version}")
            self._log(f"Fast direct chunk scan: {self.fast_direct_scan.GetValue()}")
            self._log(f"Fast direct chunk clear: {self.fast_direct_clear.GetValue()}")
            self._log(f"Large selection warning enabled: {self.show_large_selection_warning.GetValue()}")
            self._log(f"Item frame label audit enabled: {self.include_item_frame_audit.GetValue()}")
            self._log(f"Display-name ABC audit enabled: {self.include_display_name_audit.GetValue()}")
            self._log(f"Amulet conversion capability diagnostic enabled: {self.include_amulet_conversion_diagnostic.GetValue()}")
            self._log(f"Amulet translator validation probe enabled: {self.include_amulet_translator_probe.GetValue()}")
            self._log(f"Reviewed Amulet normalization enabled: {self.use_reviewed_amulet_normalization.GetValue()}")
            self._log(
                "Attempt unresolved item writes: "
                f"{self.attempt_unresolved_item_writes.GetValue()}"
            )
            self._log(f"Amulet conversion comparison audit enabled: {self.include_amulet_conversion_audit.GetValue()}")
            self._log(f"Found Entries cache enabled: {self.use_found_entries_cache.GetValue()}")
            self._log(f"Installed language fallback enabled: {self.use_installed_language_data.GetValue()}")
            self._log(
                f"Keep Found Entries updated from installed language file: "
                f"{self.save_found_language_entries.GetValue()}"
            )
            self._log(f"Simulate missing display-name entry: {self.simulate_missing_display_name.GetValue()}")
            self._log(f"Conversion Entries rules enabled: {self.use_conversion_entries.GetValue()}")
            self._log(
                f"Record conversion candidates: "
                f"{self.record_conversion_candidates.GetValue()}"
            )
            self._log(
                "Record all resolved conversion observations: "
                f"{self.record_all_conversion_observations.GetValue()}"
            )
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
                self._log("Shulker facing: sideways / inward")

            scan_start = time.perf_counter()
            (
                counts,
                skipped_counts,
                skipped_by_reason,
                protected_positions,
                bounds,
                scanned_positions,
                exportable_source_blocks,
            ) = self._scan_selection()
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

            if self._missing_scan_chunks:
                self._log(
                    f"Missing chunks treated as air: "
                    f"{len(self._missing_scan_chunks):,}"
                )

            if self._ambiguous_fast_scan_fallbacks:
                self._log(f"Ambiguous fast scan block fallbacks: {self._ambiguous_fast_scan_fallbacks:,}")

            if (
                self._built_in_scan_identity_recoveries
                or self._found_entry_scan_identity_recoveries
                or self._installed_language_scan_identity_recoveries
                or self._scan_identity_diagnostics
                or self._scan_identity_diagnostic_overflow
            ):
                self._log_scan_identity_summary()

            if not counts:
                self._log("No exportable items found.")

                self._log("")
                self._log_skipped_block_report(skipped_counts, skipped_by_reason)

                self._log("")
                self._log(f"Total operation time: {self._format_seconds(time.perf_counter() - total_start)}")
                return

            planning_start = time.perf_counter()

            total_items = sum(counts.values())
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
            self._log(
                f"Exportable source blocks found: {exportable_source_blocks:,}"
            )
            self._log(f"Exportable items produced: {total_items:,}")
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
            self._log("Exported items:")
            for item_name in self._get_ordered_item_names(counts):
                self._log(f"{item_name} -> {counts[item_name]:,}")

            if self.include_display_name_audit.GetValue():
                self._log("")
                self._log_display_name_audit(counts)

            self._write_pending_found_entries()
            self._write_pending_conversion_candidates()
            self._log("")
            self._log_external_language_summary()
            self._log_conversion_entries_summary()
            self._log(
                f"Conversion candidate recording enabled: "
                f"{self.record_conversion_candidates.GetValue()}"
            )
            if self.record_conversion_candidates.GetValue():
                self._log(
                    f"Conversion candidate records collected this operation: "
                    f"{len(self._pending_conversion_candidates):,}"
                )
                self._log(
                    f"Conversion candidate observations collected this operation: "
                    f"{sum(self._pending_conversion_candidates.values()):,}"
                )
                self._log(
                    f"Conversion candidate records already in file: "
                    f"{self._conversion_candidates_existing_record_count:,}"
                )
                self._log(
                    f"Conversion candidate new records added: "
                    f"{self._conversion_candidates_new_record_count:,}"
                )
                self._log(
                    f"Conversion candidate existing records updated: "
                    f"{self._conversion_candidates_updated_record_count:,}"
                )
                self._log(
                    f"Conversion candidate observations added: "
                    f"{self._conversion_candidate_observations_added_count:,}"
                )
                self._log(
                    f"Conversion candidate total records after write: "
                    f"{self._conversion_candidates_total_record_count:,}"
                )
                if self._conversion_candidates_write_error:
                    self._log(
                        f"Conversion candidate write issue: "
                        f"{self._conversion_candidates_write_error}"
                    )
            if self.include_amulet_conversion_diagnostic.GetValue():
                self._log("")
                self._log_amulet_conversion_capability_diagnostic()

            if self.include_amulet_translator_probe.GetValue():
                self._log("")
                self._log_amulet_translator_validation_probe()

            if self.use_reviewed_amulet_normalization.GetValue():
                self._log("")
                self._log_reviewed_amulet_normalization_summary()

            if self.include_amulet_conversion_audit.GetValue():
                self._log("")
                self._log_amulet_conversion_comparison_audit()

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

            self._log(f"Selected positions cleared: {cleared_blocks:,}")
            self._log(f"Clear time: {self._format_seconds(clear_time)}")
            self._log(f"Clear speed: {self._format_rate(cleared_blocks, clear_time, 'positions')}")
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
            operation_failed = True
            self._log("")
            self._log(f"Operation failed: {exc}")
            self._log(f"Total operation time before failure: {self._format_seconds(time.perf_counter() - total_start)}")
        finally:
            try:
                self._finalize_report()
            finally:
                self._release_operation_display_name_caches()
                self._release_operation_conversion_caches()
                self._release_amulet_translator_capability_state()
                status_label = (
                    "Operation failed. Review the report."
                    if operation_failed
                    else "Done. Selected blocks were moved into storage."
                )
                try:
                    wx.CallAfter(
                        self._finish_operation_ui,
                        status_label,
                        self._active_operation_ui_generation,
                    )
                except Exception:
                    self._finish_operation_ui(
                        status_label,
                        self._active_operation_ui_generation,
                    )

export = dict(name="Blocks to Storage", operation=PluginClassName)
