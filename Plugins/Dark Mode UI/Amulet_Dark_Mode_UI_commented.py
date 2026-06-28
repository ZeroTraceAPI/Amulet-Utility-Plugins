r"""Dark Mode UI v2.0.0.0 plugin for Amulet Map Editor.

Purpose:
- Apply a reversible dark theme to Amulet's wxPython interface.
- Keep the theme active through a persistent top-level controller.
- Exclude self-themed Amulet Utility Plugin windows from recoloring.
- Provide local settings, diagnostics, UI scans and log export.

Settings are saved to:
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\Config\plugins\edit_plugins\Dark Mode UI.config

This plugin does not edit the world.

Navigation:
1. Configuration, file management and editor-load startup
2. Persistent theme controller and reversible state capture
3. Incremental event watchers and secondary-dialog handling
4. Matte-black custom UI foundation and painted controls
5. Layered Windows dropdowns and tooltips with portable fallbacks
6. Floating window, compact launcher and settings layout
7. Console, diagnostics, report export and Amulet registration
"""

import ast
import collections
import ctypes
import json
import os
import tempfile
import weakref
from time import monotonic, perf_counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import wx

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
from amulet_map_editor.programs.edit.api.operations import DefaultOperationUI

try:
    import wx.lib.agw.flatnotebook as flatnotebook
except Exception:
    flatnotebook = None


# =========================
# CONFIGURATION AND STARTUP
# =========================
CONFIG_FORMAT_VERSION = 3
# Settings are stored in Amulet's normal per-user plugin config folder.
CONFIG_FILE_NAME = "Dark Mode UI.config"
CONTROLLER_ATTR_NAME = "_amulet_dark_mode_ui_controller"
EDITOR_LOAD_ATTEMPT_COUNT = 0
EDITOR_LOAD_MAX_ATTEMPTS = 40
EDITOR_LOAD_DELAY_MS = 250
# Newly created or shown controls are collected briefly so one UI action causes
# one small incremental theme pass instead of several full-window passes.
EVENT_RETHEME_DELAY_MS = 120
# Amulet can assemble an operation panel in stages. The first show / create
# event may occur before all labels, buttons, and choices are attached. A bounded
# follow-up pass themes the affected top-level window after construction settles.
EVENT_SETTLE_DELAY_MS = 320
# Child-focus is watched only on target top-level windows as a compatibility
# fallback for operation hosts that do not propagate create / show events.
ROOT_ACTIVITY_COOLDOWN_MS = 250
# Secondary dialogs may finish native sizing after their controls receive dark
# colors. A root-only size watcher and one background-erasing repaint keep the
# complete dialog client area consistent without per-control size monitoring.
SECONDARY_DIALOG_SIZE_COOLDOWN_MS = 120

# Plugin consoles can opt into the black background and green text palette by
# assigning a shared semantic name. The legacy name remains recognized for
# compatibility with existing plugin consoles.
PLUGIN_CONSOLE_NAME_PREFIX = "AmuletPluginConsole"
LEGACY_CONSOLE_NAME = "DarkModeUIConsole"


# Custom utility-plugin windows can own their complete visual theme. When a
# window uses this attribute or semantic name prefix, Dark Mode UI must neither
# recolor it nor descend into its children. This protects custom-painted plugin
# controls while allowing the surrounding Amulet operation host to remain
# normally themed.
CUSTOM_UI_THEME_OWNED_ATTR = "_amulet_utility_theme_owned"
CUSTOM_UI_NAME_PREFIX = "AmuletUtilityCustomUI"


def _config_path() -> Path:
    """Return the local per-user Dark Mode UI configuration path."""
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "AmuletTeam" / "AmuletMapEditor" / "Config" / "plugins" / "edit_plugins" / CONFIG_FILE_NAME


def _display_path(path: Path) -> str:
    """Return a privacy-conscious path using environment aliases when possible."""
    try:
        raw = str(Path(path).resolve())
        for key in ("LOCALAPPDATA", "USERPROFILE"):
            value = os.environ.get(key)
            if value:
                root = str(Path(value).resolve())
                if raw.lower().startswith(root.lower()):
                    return f"%{key}%" + raw[len(root):]
        home = str(Path.home().resolve())
        if raw.lower().startswith(home.lower()):
            return "~" + raw[len(home):]
    except Exception:
        pass
    return str(path)


def _default_config() -> Dict[str, object]:
    """Return default user settings for Dark Mode UI."""
    return {
        "format_version": CONFIG_FORMAT_VERSION,
        "enabled_on_editor_load": False,
        "enabled_on_startup": False,
        "scope_mode": "top",
        "skip_canvas": True,
        "try_flatnotebook": True,
        "button_hover_safe": True,
        "preserve_selection_colors": True,
        "color_coordinate_labels": False,
        "watch_new_controls": True,
        "max_depth": 18,
        "max_controls": 1500,
        "window_size": [520, 760],
        "manage_window_size": [560, 460],
        "console_visible": True,
    }


def _validated_size_pair(
    value,
    minimum,
    fallback,
    maximum=(2400, 1600),
):
    """Return a bounded two-integer size pair."""
    try:
        width, height = value
        if any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in (width, height)
        ):
            raise ValueError
        return [
            max(minimum[0], min(int(width), maximum[0])),
            max(minimum[1], min(int(height), maximum[1])),
        ]
    except Exception:
        return [int(fallback[0]), int(fallback[1])]


def _normalize_config_data(data: Dict[str, object]) -> Dict[str, object]:
    """Normalize recognized settings while preserving unknown entries."""
    source = dict(data) if isinstance(data, dict) else {}
    defaults = _default_config()
    normalized = dict(source)

    if "preserve_selection_colours" in source:
        source["preserve_selection_colors"] = source.get(
            "preserve_selection_colours"
        )
    if "colour_coordinate_labels" in source:
        source["color_coordinate_labels"] = source.get(
            "colour_coordinate_labels"
        )
    if (
        "enabled_on_editor_load" not in source
        and "enabled_on_startup" in source
    ):
        source["enabled_on_editor_load"] = source.get("enabled_on_startup")

    bool_keys = (
        "enabled_on_editor_load",
        "skip_canvas",
        "try_flatnotebook",
        "button_hover_safe",
        "preserve_selection_colors",
        "color_coordinate_labels",
        "watch_new_controls",
        "console_visible",
    )
    for key in bool_keys:
        value = source.get(key)
        normalized[key] = (
            value if isinstance(value, bool) else bool(defaults[key])
        )

    scope_mode = source.get("scope_mode")
    normalized["scope_mode"] = (
        scope_mode if scope_mode in {"top", "all"} else defaults["scope_mode"]
    )

    max_depth = source.get("max_depth")
    if isinstance(max_depth, int) and not isinstance(max_depth, bool):
        normalized["max_depth"] = max(1, min(max_depth, 40))
    else:
        normalized["max_depth"] = defaults["max_depth"]

    max_controls = source.get("max_controls")
    if isinstance(max_controls, int) and not isinstance(max_controls, bool):
        normalized["max_controls"] = max(100, min(max_controls, 5000))
    else:
        normalized["max_controls"] = defaults["max_controls"]

    normalized["window_size"] = _validated_size_pair(
        source.get("window_size"),
        (440, 580),
        defaults["window_size"],
    )
    normalized["manage_window_size"] = _validated_size_pair(
        source.get("manage_window_size"),
        (554, 410),
        defaults["manage_window_size"],
    )

    normalized["format_version"] = CONFIG_FORMAT_VERSION
    normalized["enabled_on_startup"] = False
    normalized.pop("preserve_selection_colours", None)
    normalized.pop("colour_coordinate_labels", None)
    return normalized


def _write_text_atomically(path: Path, content: str) -> None:
    """Write text through a temporary sibling and atomically replace the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_name = temporary.name
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except Exception:
                pass


def _load_config() -> Dict[str, object]:
    """Load, validate, and migrate the active Dark Mode UI configuration."""
    path = _config_path()
    try:
        if path.exists() and path.is_file():
            if path.stat().st_size > 1024 * 1024:
                return _default_config()
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                return _normalize_config_data(loaded)
    except Exception:
        pass
    return _default_config()


def _save_config(config: Dict[str, object]) -> Tuple[bool, str]:
    """Atomically write normalized settings and return a display-safe path."""
    path = _config_path()
    try:
        data = _normalize_config_data(config)
        _write_text_atomically(
            path,
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ) + "\n",
        )
        return True, _display_path(path)
    except Exception as exc:
        return False, str(exc)


def _find_top_window() -> Optional[wx.Window]:
    """Locate the current Amulet top-level window for editor-load theming."""
    try:
        windows = list(wx.GetTopLevelWindows())
    except Exception:
        return None
    for window in windows:
        try:
            title = str(window.GetTitle()) if hasattr(window, "GetTitle") else ""
            cls = window.__class__.__module__ + "." + window.__class__.__name__
            if "amulet" in title.lower() or "amulet" in cls.lower():
                return window
        except Exception:
            pass
    return windows[0] if windows else None


def _deactivate_replaced_controller(controller) -> None:
    """Deactivate handlers retained by a replaced controller instance.

    wx event bindings keep bound-method owners alive. When Amulet reloads the
    plugin without restarting, the replaced controller can otherwise continue
    receiving events after the top-level attribute changes.
    """
    if controller is None:
        return
    try:
        controller._theme_active = False
    except Exception:
        pass
    try:
        controller.watch_new_controls = False
    except Exception:
        pass
    for pending_name in ("_event_retheme_call", "_settle_retheme_call"):
        try:
            pending = getattr(controller, pending_name, None)
            if pending is not None:
                pending.Stop()
        except Exception:
            pass


def _get_controller(top: wx.Window):
    """Return the persistent controller attached to one Amulet window."""
    existing = None
    try:
        existing = getattr(top, CONTROLLER_ATTR_NAME, None)
        if isinstance(existing, DarkModeController):
            return existing
    except Exception:
        existing = None
    _deactivate_replaced_controller(existing)
    controller = DarkModeController(top)
    try:
        setattr(top, CONTROLLER_ATTR_NAME, controller)
    except Exception:
        pass
    return controller


def _configure_controller(controller, config: Dict[str, object]) -> None:
    """Apply normalized configuration values to a controller instance."""
    controller.configure(
        scope_mode=str(config.get("scope_mode", "top")),
        skip_canvas=bool(config.get("skip_canvas", True)),
        try_flatnotebook=bool(config.get("try_flatnotebook", True)),
        button_hover_safe=bool(config.get("button_hover_safe", True)),
        preserve_selection_colors=bool(config.get("preserve_selection_colors", True)),
        color_coordinate_labels=bool(config.get("color_coordinate_labels", False)),
        watch_new_controls=bool(config.get("watch_new_controls", True)),
        max_depth=int(config.get("max_depth", 18)),
        max_controls=int(config.get("max_controls", 1500)),
    )


def _try_apply_on_editor_load() -> None:
    """Apply dark mode once Amulet has loaded enough wx UI to theme."""
    global EDITOR_LOAD_ATTEMPT_COUNT
    EDITOR_LOAD_ATTEMPT_COUNT += 1
    config = _load_config()
    if not bool(config.get("enabled_on_editor_load", False)):
        return
    top = _find_top_window()
    if top is None:
        if EDITOR_LOAD_ATTEMPT_COUNT < EDITOR_LOAD_MAX_ATTEMPTS:
            try:
                wx.CallLater(EDITOR_LOAD_DELAY_MS, _try_apply_on_editor_load)
            except Exception:
                pass
        return
    try:
        controller = _get_controller(top)
        _configure_controller(controller, config)
        controller.apply(quiet=True)
    except Exception:
        if EDITOR_LOAD_ATTEMPT_COUNT < EDITOR_LOAD_MAX_ATTEMPTS:
            try:
                wx.CallLater(EDITOR_LOAD_DELAY_MS, _try_apply_on_editor_load)
            except Exception:
                pass


def _schedule_editor_load_apply() -> None:
    """Schedule the bounded editor-load dark-mode check."""
    try:
        wx.CallLater(EDITOR_LOAD_DELAY_MS, _try_apply_on_editor_load)
    except Exception:
        try:
            wx.CallAfter(_try_apply_on_editor_load)
        except Exception:
            pass


# =========================
# PERSISTENT THEME CONTROLLER
# =========================
class DarkModeController:
    """Apply, maintain, inspect, and reverse the Amulet dark theme."""
    DARK_WINDOW_BG = wx.Colour(30, 30, 30)
    DARK_PANEL_BG = wx.Colour(37, 37, 38)
    DARK_TEXT = wx.Colour(225, 225, 225)
    DARK_MUTED_TEXT = wx.Colour(185, 185, 185)
    DARK_INPUT_BG = wx.Colour(25, 25, 25)
    DARK_CONSOLE_BG = wx.Colour(0, 0, 0)
    DARK_CONSOLE_TEXT = wx.Colour(0, 255, 0)
    DARK_BUTTON_BG = wx.Colour(50, 50, 50)
    DARK_BUTTON_FORCED_LIGHT_HOVER_TEXT = wx.Colour(24, 24, 24)
    DARK_BUTTON_NORMAL_TEXT = wx.Colour(225, 225, 225)
    DARK_DISABLED_BUTTON_BG = wx.Colour(42, 42, 42)
    DARK_DISABLED_BUTTON_TEXT = wx.Colour(150, 150, 150)
    DARK_DISABLED_INPUT_BG = wx.Colour(32, 32, 32)
    DARK_DISABLED_INPUT_TEXT = wx.Colour(145, 145, 145)
    DARK_BITMAP_BUTTON_BG = wx.Colour(43, 43, 43)
    DARK_BORDER = wx.Colour(70, 70, 70)
    DARK_POINT_1_BG = wx.Colour(54, 126, 70)
    DARK_POINT_2_BG = wx.Colour(84, 76, 150)
    DARK_SELECTION_BOX_BG = wx.Colour(82, 82, 82)
    MAX_SAFE_DEPTH = 40
    MAX_SAFE_CONTROLS = 5000

    def __init__(self, owner: wx.Window):
        """Initialize reversible theme state for one Amulet top-level window."""
        self.owner_ref = weakref.ref(owner)
        self._log_callbacks: List[weakref.ReferenceType] = []
        self._original_colors: "weakref.WeakKeyDictionary[wx.Window, Tuple[wx.Colour, wx.Colour]]" = weakref.WeakKeyDictionary()
        self._original_extra_state: "weakref.WeakKeyDictionary[wx.Window, Dict[str, object]]" = weakref.WeakKeyDictionary()
        self._semantic_roles: "weakref.WeakKeyDictionary[wx.Window, str]" = weakref.WeakKeyDictionary()
        self._hover_bound_windows = weakref.WeakSet()
        self._currently_hovered_buttons = weakref.WeakSet()
        self._watch_bound_windows = weakref.WeakSet()
        self._root_activity_bound_windows = weakref.WeakSet()
        self._pending_theme_windows = weakref.WeakSet()
        self._pending_settle_roots = weakref.WeakSet()
        self._known_target_roots = weakref.WeakSet()
        self._root_activity_last_queued = {}
        self._event_retheme_call = None
        self._settle_retheme_call = None
        self._event_retheme_pending = False
        self._event_batch_count = 0
        self._event_window_count = 0
        self._settle_batch_count = 0
        self._last_event_report = ""
        self._theme_active = False
        self.scope_mode = "top"
        self.skip_canvas = True
        self.try_flatnotebook = True
        self.button_hover_safe = True
        self.preserve_selection_colors = True
        self.color_coordinate_labels = False
        self.watch_new_controls = True
        self.max_depth = 18
        self.max_controls = 1500

    # ------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------

    def add_logger(self, logger) -> None:
        """Register a weakly held callback for controller log messages."""
        try:
            self._log_callbacks.append(weakref.WeakMethod(logger))
        except TypeError:
            try:
                self._log_callbacks.append(weakref.ref(logger))
            except Exception:
                pass

    def log(self, message: str = "") -> None:
        """Write to stdout and forward the message to live UI loggers."""
        print(message)
        live = []
        for callback_ref in list(self._log_callbacks):
            try:
                callback = callback_ref()
            except Exception:
                callback = None
            if callback is None:
                continue
            live.append(callback_ref)
            try:
                wx.CallAfter(callback, message)
            except Exception:
                try:
                    callback(message)
                except Exception:
                    pass
        self._log_callbacks = live

    def configure(self, *, scope_mode: str, skip_canvas: bool, try_flatnotebook: bool, button_hover_safe: bool, preserve_selection_colors: bool, color_coordinate_labels: bool, watch_new_controls: bool, max_depth: int, max_controls: int) -> None:
        """Apply bounded user settings to this persistent controller."""
        self.scope_mode = scope_mode
        self.skip_canvas = skip_canvas
        self.try_flatnotebook = try_flatnotebook
        self.button_hover_safe = button_hover_safe
        self.preserve_selection_colors = preserve_selection_colors
        self.color_coordinate_labels = color_coordinate_labels
        self.watch_new_controls = watch_new_controls
        self.max_depth = max(1, min(int(max_depth), self.MAX_SAFE_DEPTH))
        self.max_controls = max(100, min(int(max_controls), self.MAX_SAFE_CONTROLS))

    # ------------------------------------------------------------
    # Safe wx helpers
    # ------------------------------------------------------------

    def _safe_class_name(self, window: wx.Window) -> str:
        """Return a diagnostic class name without propagating wx errors."""
        try:
            return window.__class__.__module__ + "." + window.__class__.__name__
        except Exception:
            return type(window).__name__

    def _safe_label(self, window: wx.Window) -> str:
        """Return the first useful display label exposed by a wx window."""
        for method_name in ("GetLabelText", "GetLabel", "GetTitle", "GetName"):
            try:
                method = getattr(window, method_name, None)
                value = method() if method else ""
                if value:
                    return str(value).replace("\n", "\\n")
            except Exception:
                pass
        return ""

    def _safe_color_text(self, color) -> str:
        """Return a display-safe RGB string for diagnostics."""
        try:
            if not color or not color.IsOk():
                return "invalid"
            return "#{:02X}{:02X}{:02X}".format(color.Red(), color.Green(), color.Blue())
        except Exception:
            return "unknown"

    def _safe_get_bg(self, window: wx.Window):
        """Read a background colour without propagating wx errors."""
        try:
            return window.GetBackgroundColour()
        except Exception:
            return None

    def _safe_get_fg(self, window: wx.Window):
        """Read a foreground colour without propagating wx errors."""
        try:
            return window.GetForegroundColour()
        except Exception:
            return None

    def _safe_is_shown(self, window: wx.Window) -> bool:
        """Return visibility, defaulting to visible on wx failure."""
        try:
            return bool(window.IsShown())
        except Exception:
            return True

    def _safe_is_enabled(self, window: wx.Window) -> bool:
        """Return enabled state, defaulting to enabled on wx failure."""
        try:
            return bool(window.IsEnabled())
        except Exception:
            return True

    def _safe_children(self, window: wx.Window) -> List[wx.Window]:
        """Return child windows or an empty list when wx access fails."""
        try:
            return list(window.GetChildren())
        except Exception:
            return []


    def _is_theme_owned(self, window: wx.Window) -> bool:
        """Return True when a control explicitly owns its complete visual theme."""
        if window is None:
            return False
        try:
            if bool(getattr(window, CUSTOM_UI_THEME_OWNED_ATTR, False)):
                return True
        except Exception:
            pass
        try:
            name = str(window.GetName() or "")
            # Any semantic name beginning with the shared prefix owns its
            # complete visual theme. This intentionally accepts both the normal
            # ``Prefix:Role`` form and compatible suffix conventions.
            return name.startswith(CUSTOM_UI_NAME_PREFIX)
        except Exception:
            return False

    def _is_within_theme_owned(self, window: wx.Window) -> bool:
        """Return True for a theme-owned root or any descendant of one."""
        current = window
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if self._is_theme_owned(current):
                return True
            current = self._safe_parent(current)
        return False

    def _safe_size(self, window: wx.Window) -> str:
        """Return a compact diagnostic size string."""
        try:
            size = window.GetSize()
            return f"{size.width}x{size.height}"
        except Exception:
            return "unknown"

    def _color_close(self, color, target: wx.Colour, tolerance: int = 10) -> bool:
        """Return whether two RGB colours are within one tolerance."""
        try:
            return bool(color and color.IsOk() and abs(color.Red() - target.Red()) <= tolerance and abs(color.Green() - target.Green()) <= tolerance and abs(color.Blue() - target.Blue()) <= tolerance)
        except Exception:
            return False

    def _looks_like_canvas(self, window: wx.Window) -> bool:
        """Identify canvas-like windows that should remain unthemed."""
        try:
            words = f"{type(window).__module__}.{self._safe_class_name(window)}".lower()
        except Exception:
            words = type(window).__name__.lower()
        return any(token in words for token in ("glcanvas", "opengl", "canvas", "renderer", "viewport"))

    def _is_button_like(self, window: wx.Window) -> bool:
        """Identify native and custom button-like controls."""
        try:
            if isinstance(window, (wx.Button, wx.ToggleButton, wx.BitmapButton)):
                return True
        except Exception:
            pass
        class_name = self._safe_class_name(window).lower()
        return "button" in class_name or "movebutton" in class_name

    def _is_transient_top_level(self, window: wx.Window) -> bool:
        """Return True for short-lived popup / tooltip windows.

        These windows are recreated by native controls and are not stable theme
        roots. Treating them as full application windows can cause unnecessary
        repainting while choices, menus, or tips open and close.
        """
        transient_types = []
        for type_name in ("PopupWindow", "PopupTransientWindow", "TipWindow"):
            window_type = getattr(wx, type_name, None)
            if window_type is not None:
                transient_types.append(window_type)
        try:
            if transient_types and isinstance(window, tuple(transient_types)):
                return True
        except Exception:
            pass
        class_name = self._safe_class_name(window).lower()
        return any(
            token in class_name
            for token in ("popupwindow", "popuptransient", "tooltip", "tipwindow")
        )

    def _is_owned_by_window(
        self,
        window: wx.Window,
        owner: wx.Window,
    ) -> bool:
        """Return whether a window belongs to the owner's parent chain.

        Amulet may retain one World Select window for the normal Main Menu path
        but create a different top-level instance after Close World. Owned
        top-level windows still belong to the selected Amulet window even though
        they are not ordinary child panels.
        """
        current = window
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if current is owner:
                return True
            current = self._safe_parent(current)
        return False

    def get_targets(self) -> List[wx.Window]:
        """Return current top-level roots included by the selected scope.

        ``This Amulet window`` includes top-level dialogs owned by the main
        window. ``All top-level wx windows`` continues to include every stable
        non-transient top-level window.
        """
        owner = self.owner_ref()
        try:
            top_levels = [
                window
                for window in wx.GetTopLevelWindows()
                if (
                    window is not None
                    and not self._is_transient_top_level(window)
                    and not self._is_theme_owned(window)
                )
            ]
        except Exception:
            top_levels = []

        if self.scope_mode == "all":
            if top_levels:
                return top_levels
            return [owner] if owner is not None else []

        if owner is None:
            return []

        targets = [owner]
        seen = {id(owner)}
        for window in top_levels:
            if id(window) in seen:
                continue
            if self._is_owned_by_window(window, owner):
                targets.append(window)
                seen.add(id(window))
        return targets

    def walk_windows(self, roots: Iterable[wx.Window], include_hidden: bool, max_depth: Optional[int] = None, max_controls: Optional[int] = None) -> Tuple[List[Tuple[int, wx.Window]], bool]:
        """Return the bounded window tree used by theme and restore passes."""
        result: List[Tuple[int, wx.Window]] = []
        truncated = False
        seen = set()
        max_depth = self.max_depth if max_depth is None else int(max_depth)
        max_controls = self.max_controls if max_controls is None else int(max_controls)

        def walk(window: wx.Window, depth: int) -> None:
            nonlocal truncated
            if window is None or truncated:
                return
            if self._is_theme_owned(window):
                return
            marker = id(window)
            if marker in seen:
                return
            seen.add(marker)
            if len(result) >= max_controls:
                truncated = True
                return
            if include_hidden or self._safe_is_shown(window):
                result.append((depth, window))
            if depth >= max_depth:
                return
            for child in self._safe_children(window):
                walk(child, depth + 1)

        for root in roots:
            walk(root, 0)
        return result, truncated

    # ------------------------------------------------------------
    # Theme color selection and application
    # ------------------------------------------------------------

    def _colors_equal(self, first, second) -> bool:
        """Return True when two wx colors have the same RGBA components."""
        try:
            if not first or not second or not first.IsOk() or not second.IsOk():
                return False
            return (
                first.Red(),
                first.Green(),
                first.Blue(),
                first.Alpha(),
            ) == (
                second.Red(),
                second.Green(),
                second.Blue(),
                second.Alpha(),
            )
        except Exception:
            return False

    def _safe_parent(self, window: wx.Window) -> Optional[wx.Window]:
        """Return a wx parent without allowing destroyed wrappers to abort a pass."""
        try:
            return window.GetParent()
        except Exception:
            return None

    def _top_level_for_window(self, window: wx.Window) -> Optional[wx.Window]:
        """Return the nearest top-level parent for one themed control."""
        current = window
        last = window
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            last = current
            try:
                if isinstance(current, wx.TopLevelWindow):
                    return current
            except Exception:
                pass
            current = self._safe_parent(current)
        return last

    def _is_secondary_top_level(self, window: wx.Window) -> bool:
        """Return whether a stable top-level root is separate from the owner."""
        owner = self.owner_ref()
        try:
            return (
                isinstance(window, wx.TopLevelWindow)
                and window is not owner
                and not self._is_transient_top_level(window)
            )
        except Exception:
            return False

    def _repaint_secondary_dialog(self, root: wx.Window) -> None:
        """Repaint one secondary-dialog root after native sizing completes.

        The repaint is limited to the dialog root so blank client regions receive
        the dark background without forcing synchronous updates on every child.
        """
        if not self._is_secondary_top_level(root):
            return

        try:
            self._remember_original_state(root)
            bg, fg = self._choose_dark_colors(root)
            # Reapply the root colors even when wx reports that they already
            # match. Native dialog resizing can visually expose the system
            # background while GetBackgroundColour still returns the dark value.
            root.SetBackgroundColour(bg)
            root.SetForegroundColour(fg)
        except Exception:
            pass

        try:
            root.Layout()
        except Exception:
            pass
        try:
            # eraseBackground=True is required for unoccupied client regions.
            root.Refresh(True)
        except Exception:
            try:
                root.Refresh()
            except Exception:
                pass
        try:
            # One synchronous update is limited to the secondary-dialog root.
            root.Update()
        except Exception:
            pass

    def _event_theme_target(self, window: wx.Window) -> wx.Window:
        """Promote secondary-dialog events to the complete dialog root.

        Ordinary events inside the main Amulet window remain subtree-scoped so
        operation switches do not trigger a full-window repaint. Events inside
        a separate stable dialog use that dialog as the bounded root, ensuring
        its frame, background panels and controls receive one consistent pass.
        """
        root = self._top_level_for_window(window)
        owner = self.owner_ref()
        if (
            root is not None
            and root is not owner
            and not self._is_transient_top_level(root)
        ):
            return root
        return window

    def _deduplicate_theme_roots(self, windows: Iterable[wx.Window]) -> List[wx.Window]:
        """Remove duplicate targets and descendants of another queued target."""
        unique = []
        seen = set()
        for window in windows:
            if window is None or id(window) in seen:
                continue
            try:
                if window.IsBeingDeleted():
                    continue
            except Exception:
                pass
            seen.add(id(window))
            unique.append(window)

        unique_ids = {id(window) for window in unique}
        roots = []
        for window in unique:
            # Keep each top-level window as an independent theme root even when
            # wx reports another top-level window as its owner / parent. Owned
            # dialogs are not guaranteed to appear in the owner's GetChildren
            # traversal, so collapsing them could skip a new World Select frame.
            try:
                if isinstance(window, wx.TopLevelWindow):
                    roots.append(window)
                    continue
            except Exception:
                pass

            parent = self._safe_parent(window)
            has_queued_ancestor = False
            visited = set()
            while parent is not None and id(parent) not in visited:
                visited.add(id(parent))
                if id(parent) in unique_ids:
                    has_queued_ancestor = True
                    break
                parent = self._safe_parent(parent)
            if not has_queued_ancestor:
                roots.append(window)
        return roots

    def _remember_original_state(self, window: wx.Window) -> None:
        """Capture a control's original visual state before its first modification."""
        try:
            if window not in self._original_colors:
                self._original_colors[window] = (wx.Colour(self._safe_get_bg(window)), wx.Colour(self._safe_get_fg(window)))
        except Exception:
            pass
        try:
            if window not in self._original_extra_state:
                state = {}
                if flatnotebook is not None and isinstance(window, flatnotebook.FlatNotebook):
                    for getter_name in ("GetActiveTabColour", "GetActiveTabTextColour", "GetNonActiveTabTextColour", "GetTabAreaColour"):
                        getter = getattr(window, getter_name, None)
                        if getter:
                            try:
                                state[getter_name] = getter()
                            except Exception:
                                pass
                self._original_extra_state[window] = state
        except Exception:
            pass

    def _set_window_colors(
        self,
        window: wx.Window,
        bg: wx.Colour,
        fg: wx.Colour,
    ) -> Tuple[bool, str, bool]:
        """Apply only color values that differ from the current control state.

        Re-applying the same colors and forcing Update on every event caused
        native controls to repaint repeatedly. That was especially visible when
        all top-level windows were targeted.
        """
        self._remember_original_state(window)
        errors = []
        changed = False

        current_bg = self._safe_get_bg(window)
        if not self._colors_equal(current_bg, bg):
            try:
                window.SetBackgroundColour(bg)
                changed = True
            except Exception as exc:
                errors.append(f"bg:{exc}")

        current_fg = self._safe_get_fg(window)
        if not self._colors_equal(current_fg, fg):
            try:
                window.SetForegroundColour(fg)
                changed = True
            except Exception as exc:
                errors.append(f"fg:{exc}")

        if changed:
            try:
                # Refresh schedules one normal repaint. Update forced an
                # immediate repaint for every control and amplified flicker.
                window.Refresh(False)
            except Exception:
                pass

        return not errors, "; ".join(errors), changed

    def _is_static_text_like(self, window: wx.Window) -> bool:
        """Return whether a control behaves like a static text label."""
        try:
            if isinstance(window, wx.StaticText):
                return True
        except Exception:
            pass
        return "statictext" in self._safe_class_name(window).lower()

    def _is_dark_mode_console(self, window: wx.Window) -> bool:
        """Return True for recognized plugin report and diagnostic consoles."""
        try:
            name = str(window.GetName() or "")
            return (
                name == LEGACY_CONSOLE_NAME
                or name == PLUGIN_CONSOLE_NAME_PREFIX
                or name.startswith(PLUGIN_CONSOLE_NAME_PREFIX + ":")
            )
        except Exception:
            return False

    def _semantic_dark_colors(self, window: wx.Window) -> Optional[Tuple[wx.Colour, wx.Colour]]:
        """Return semantic dark colors for recognized control roles."""
        role = None
        try:
            role = self._semantic_roles.get(window)
        except Exception:
            role = None

        if role is None:
            current_bg = self._safe_get_bg(window)
            original_bg = None
            try:
                if window in self._original_colors:
                    original_bg = self._original_colors[window][0]
            except Exception:
                original_bg = None

            class_name = self._safe_class_name(window).lower()
            label = self._safe_label(window).lower().strip()
            color_candidates = [current_bg, original_bg]
            is_label = self._is_static_text_like(window)

            is_green = any(self._color_close(bg, wx.Colour(160, 215, 145), 30) for bg in color_candidates)
            is_purple = any(self._color_close(bg, wx.Colour(150, 150, 215), 30) for bg in color_candidates)
            is_gray = any(self._color_close(bg, wx.Colour(150, 150, 150), 40) for bg in color_candidates)

            # Coordinate labels and coordinate value fields need separate roles.
            # The labels are identified by text. The input fields are identified
            # by their original color, not by nearby label text.
            if is_label and label in {"x1", "y1", "z1"}:
                role = "point1_label"
            elif is_label and label in {"x2", "y2", "z2"}:
                role = "point2_label"
            elif is_green and not is_label:
                role = "point1"
            elif is_purple and not is_label:
                role = "point2"
            elif is_gray and not is_label:
                role = "box"
            elif "point1" in class_name or "move point 1" in label or "point 1" in label:
                role = "point1"
            elif "point2" in class_name or "move point 2" in label or "point 2" in label:
                role = "point2"
            elif "selectionmovebutton" in class_name or "move box" in label:
                role = "box"

            if role is not None:
                try:
                    self._semantic_roles[window] = role
                except Exception:
                    pass

        # Preserve colors affects the actual Amulet selection fields / buttons.
        if self.preserve_selection_colors:
            if role == "point1":
                return self.DARK_POINT_1_BG, self.DARK_TEXT
            if role == "point2":
                return self.DARK_POINT_2_BG, self.DARK_TEXT
            if role == "box":
                return self.DARK_SELECTION_BOX_BG, self.DARK_TEXT

        # Coordinate labels are a separate optional visual hint. This lets users
        # turn preserve colors off so the value boxes become normal dark inputs,
        # while still keeping x1 / y1 / z1 and x2 / y2 / z2 easy to identify.
        if self.color_coordinate_labels:
            if role == "point1_label":
                return self.DARK_POINT_1_BG, self.DARK_TEXT
            if role == "point2_label":
                return self.DARK_POINT_2_BG, self.DARK_TEXT

        return None

    def _disabled_dark_colors(self, window: wx.Window) -> Optional[Tuple[wx.Colour, wx.Colour]]:
        """Return the disabled palette for one control, or None when enabled."""
        if self._safe_is_enabled(window):
            return None
        if self._is_button_like(window):
            return self.DARK_DISABLED_BUTTON_BG, self.DARK_DISABLED_BUTTON_TEXT
        try:
            if isinstance(window, (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListBox, wx.ListCtrl, wx.TreeCtrl, wx.SpinCtrl, wx.SpinCtrlDouble, wx.SpinButton)):
                return self.DARK_DISABLED_INPUT_BG, self.DARK_DISABLED_INPUT_TEXT
        except Exception:
            pass
        return self.DARK_PANEL_BG, self.DARK_DISABLED_INPUT_TEXT

    def _choose_dark_colors(self, window: wx.Window) -> Tuple[wx.Colour, wx.Colour]:
        """Choose the final dark foreground and background for one control."""
        if self._is_dark_mode_console(window):
            return self.DARK_CONSOLE_BG, self.DARK_CONSOLE_TEXT

        semantic = self._semantic_dark_colors(window)
        if semantic is not None:
            return semantic

        disabled = self._disabled_dark_colors(window)
        if disabled is not None:
            return disabled

        class_name = self._safe_class_name(window).lower()

        if isinstance(window, wx.TextCtrl):
            return self.DARK_INPUT_BG, self.DARK_TEXT

        if isinstance(window, wx.BitmapButton):
            return self.DARK_BITMAP_BUTTON_BG, self.DARK_BUTTON_NORMAL_TEXT

        if isinstance(window, (wx.Button, wx.ToggleButton)):
            return self.DARK_BUTTON_BG, self.DARK_BUTTON_NORMAL_TEXT

        if isinstance(window, (wx.Choice, wx.ComboBox, wx.ListBox, wx.ListCtrl, wx.TreeCtrl)):
            return self.DARK_INPUT_BG, self.DARK_TEXT

        if isinstance(window, (wx.SpinCtrl, wx.SpinCtrlDouble, wx.SpinButton)):
            return self.DARK_INPUT_BG, self.DARK_TEXT

        if isinstance(window, (wx.Gauge, wx.StaticLine)):
            return self.DARK_BORDER, self.DARK_TEXT

        if "notebook" in class_name:
            return self.DARK_PANEL_BG, self.DARK_TEXT

        if isinstance(window, (wx.Panel, wx.ScrolledWindow, wx.StaticBox)):
            return self.DARK_PANEL_BG, self.DARK_TEXT

        if isinstance(window, wx.StaticText):
            return self.DARK_PANEL_BG, self.DARK_TEXT

        return self.DARK_WINDOW_BG, self.DARK_TEXT

    def _apply_flatnotebook_dark(self, window: wx.Window) -> bool:
        """Apply dedicated colors to AGW FlatNotebook controls when enabled."""
        if not self.try_flatnotebook or flatnotebook is None:
            return False
        try:
            if not isinstance(window, flatnotebook.FlatNotebook):
                return False
        except Exception:
            return False
        touched = False
        calls = {
            "SetActiveTabColour": self.DARK_PANEL_BG,
            "SetActiveTabTextColour": self.DARK_TEXT,
            "SetNonActiveTabTextColour": self.DARK_MUTED_TEXT,
            "SetTabAreaColour": self.DARK_WINDOW_BG,
            "SetGradientColourFrom": self.DARK_PANEL_BG,
            "SetGradientColourTo": self.DARK_PANEL_BG,
            "SetBorderColour": self.DARK_BORDER,
        }
        for method_name, value in calls.items():
            try:
                method = getattr(window, method_name, None)
                if method is not None:
                    method(value)
                    touched = True
            except Exception:
                pass
        return touched

    def _bind_button_hover_readability(self, window: wx.Window) -> None:
        """Bind safe hover repaint handlers to native buttons once."""
        if not self.button_hover_safe or not self._is_button_like(window) or not self._safe_is_enabled(window):
            return
        try:
            if window in self._hover_bound_windows:
                return
            self._hover_bound_windows.add(window)
        except Exception:
            return

        def on_enter(event):
            if not self._theme_active:
                try:
                    event.Skip()
                except Exception:
                    pass
                return
            try:
                self._currently_hovered_buttons.add(window)
                current = self._safe_get_fg(window)
                if not self._colors_equal(
                    current,
                    self.DARK_BUTTON_FORCED_LIGHT_HOVER_TEXT,
                ):
                    window.SetForegroundColour(
                        self.DARK_BUTTON_FORCED_LIGHT_HOVER_TEXT
                    )
                    window.Refresh(False)
            except Exception:
                pass
            try:
                event.Skip()
            except Exception:
                pass

        def on_leave(event):
            if not self._theme_active:
                try:
                    event.Skip()
                except Exception:
                    pass
                return
            try:
                self._currently_hovered_buttons.discard(window)
                semantic = self._semantic_dark_colors(window)
                if semantic is not None:
                    bg, fg = semantic
                elif isinstance(window, wx.BitmapButton):
                    bg, fg = self.DARK_BITMAP_BUTTON_BG, self.DARK_BUTTON_NORMAL_TEXT
                else:
                    bg, fg = self.DARK_BUTTON_BG, self.DARK_BUTTON_NORMAL_TEXT
                self._set_window_colors(window, bg, fg)
            except Exception:
                pass
            try:
                event.Skip()
            except Exception:
                pass

        try:
            window.Bind(wx.EVT_ENTER_WINDOW, on_enter)
            window.Bind(wx.EVT_LEAVE_WINDOW, on_leave)
        except Exception:
            pass

    def apply(
        self,
        quiet: bool = False,
        from_watcher: bool = False,
        roots_override: Optional[Iterable[wx.Window]] = None,
    ) -> Dict[str, object]:
        """Apply the theme to all targets or to a small queued subtree.

        Manual and settings-driven applies still inspect the selected scope.
        Event-driven applies use roots_override so showing one panel does not
        repaint every control in every top-level window.
        """
        self._theme_active = True
        roots = (
            self._deduplicate_theme_roots(roots_override)
            if roots_override is not None
            else self.get_targets()
        )
        roots = [root for root in roots if root is not None]

        controls, truncated = self.walk_windows(roots, include_hidden=False)
        themed = changed = unchanged = skipped = failed = 0
        flatnotebook_touched = 0

        for _depth, window in controls:
            if self._is_within_theme_owned(window):
                skipped += 1
                continue
            if self.skip_canvas and self._looks_like_canvas(window):
                skipped += 1
                continue
            try:
                if quiet and self._is_button_like(window) and window in self._currently_hovered_buttons:
                    skipped += 1
                    continue
            except Exception:
                pass

            self._remember_original_state(window)
            bg, fg = self._choose_dark_colors(window)
            ok, errors, window_changed = self._set_window_colors(window, bg, fg)
            self._bind_button_hover_readability(window)
            if self._apply_flatnotebook_dark(window):
                flatnotebook_touched += 1
                window_changed = True

            if ok:
                themed += 1
                if window_changed:
                    changed += 1
                else:
                    unchanged += 1
            else:
                failed += 1
                if not quiet:
                    self.log(
                        f"Theme failed: {self._safe_class_name(window)} | {errors}"
                    )

        # A top-level root becomes known only after it is visible and included
        # in a theme pass. A dialog can be discoverable before wx reports it as
        # shown, so early registration could skip its outer frame background.
        for _depth, window in controls:
            try:
                if isinstance(window, wx.TopLevelWindow):
                    self._known_target_roots.add(window)
            except Exception:
                pass

        # Main-window roots use changed-only deferred refreshes. Secondary
        # dialogs receive one bounded background-erasing repaint because wx can
        # expose native client space after color properties are already set.
        refresh_roots = self._deduplicate_theme_roots(
            self._top_level_for_window(root) for root in roots
        )
        for root in refresh_roots:
            if self._is_secondary_top_level(root):
                self._repaint_secondary_dialog(root)
                continue
            if changed or flatnotebook_touched:
                try:
                    root.Layout()
                    root.Refresh(False)
                except Exception:
                    pass

        if self.watch_new_controls:
            # Include hidden descendants when installing watchers so an
            # existing hidden panel can be themed when it is later shown.
            watch_controls, _watch_truncated = self.walk_windows(
                roots,
                include_hidden=True,
            )
            self._bind_event_watchers(watch_controls)

        return {
            "controls": len(controls),
            "themed": themed,
            "changed": changed,
            "unchanged": unchanged,
            "skipped": skipped,
            "failed": failed,
            "flatnotebook_touched": flatnotebook_touched,
            "truncated": truncated,
        }

    # ------------------------------------------------------------
    # Event watcher for newly shown controls
    # ------------------------------------------------------------

    def _bind_event_watchers(self, controls: Iterable[Tuple[int, wx.Window]]) -> None:
        """Watch new / shown controls with bounded top-level fallbacks.

        Create and show events are the primary incremental path. Some Amulet
        operation hosts replace child controls without propagating those events
        to watched ancestors, so top-level activity queues one changed-only settle
        pass. Secondary dialogs also receive a root-only size watcher for newly
        exposed client space.
        """
        if not self._theme_active or not self.watch_new_controls:
            return

        create_event = getattr(wx, "EVT_WINDOW_CREATE", None)
        target_root_ids = {id(root) for root in self.get_targets() if root is not None}

        for _depth, window in controls:
            if window is None or self._is_within_theme_owned(window) or (
                self.skip_canvas and self._looks_like_canvas(window)
            ):
                continue

            try:
                already_bound = window in self._watch_bound_windows
            except Exception:
                already_bound = True

            if not already_bound:
                try:
                    self._watch_bound_windows.add(window)
                except Exception:
                    continue

                try:
                    window.Bind(wx.EVT_SHOW, self._on_theme_relevant_event)
                except Exception:
                    pass
                if create_event is not None:
                    try:
                        window.Bind(create_event, self._on_theme_relevant_event)
                    except Exception:
                        pass

            # Focus events are bound once on stable target roots. This catches
            # operation-panel replacement without per-control focus monitoring.
            if id(window) in target_root_ids:
                try:
                    root_bound = window in self._root_activity_bound_windows
                except Exception:
                    root_bound = True
                if not root_bound:
                    try:
                        self._root_activity_bound_windows.add(window)
                        window.Bind(wx.EVT_CHILD_FOCUS, self._on_root_activity_event)
                        activate_event = getattr(wx, "EVT_ACTIVATE", None)
                        if activate_event is not None:
                            window.Bind(activate_event, self._on_root_activity_event)
                        if self._is_secondary_top_level(window):
                            window.Bind(wx.EVT_SIZE, self._on_root_activity_event)
                    except Exception:
                        pass

    def _schedule_settle_retheme(self, window: Optional[wx.Window]) -> None:
        """Queue one debounced full-tree pass for the affected top-level root."""
        if window is None or not self._theme_active or not self.watch_new_controls:
            return
        if self._is_within_theme_owned(window):
            return
        root = self._top_level_for_window(window)
        if root is None or self._is_transient_top_level(root):
            return
        try:
            self._pending_settle_roots.add(root)
        except Exception:
            return

        pending = self._settle_retheme_call
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

        try:
            self._settle_retheme_call = wx.CallLater(
                EVENT_SETTLE_DELAY_MS,
                self._settle_retheme_once,
            )
        except Exception:
            self._settle_retheme_call = None

    def _on_root_activity_event(self, event) -> None:
        """Catch operation switches and newly reconstructed top-level dialogs."""
        try:
            event.Skip()
        except Exception:
            pass
        if not self._theme_active or not self.watch_new_controls:
            return

        window = self._event_window(event)
        root = self._top_level_for_window(window) if window is not None else None
        if root is None:
            try:
                event_object = event.GetEventObject()
                if isinstance(event_object, wx.Window):
                    root = self._top_level_for_window(event_object)
            except Exception:
                root = None
        if root is None or self._is_within_theme_owned(root):
            return

        now = monotonic()
        marker = id(root)
        previous = self._root_activity_last_queued.get(marker, 0.0)
        cooldown_ms = (
            SECONDARY_DIALOG_SIZE_COOLDOWN_MS
            if self._is_secondary_top_level(root)
            else ROOT_ACTIVITY_COOLDOWN_MS
        )
        if (now - previous) * 1000.0 < cooldown_ms:
            return
        self._root_activity_last_queued[marker] = now
        self._schedule_settle_retheme(root)

    def _event_window(self, event) -> Optional[wx.Window]:
        """Return the control most directly associated with a watcher event."""
        for method_name in ("GetWindow", "GetEventObject"):
            try:
                method = getattr(event, method_name, None)
                window = method() if method is not None else None
                if isinstance(window, wx.Window):
                    return window
            except Exception:
                pass
        return None

    def _unseen_target_roots(self) -> List[wx.Window]:
        """Return in-scope top-level windows not yet processed by the theme.

        The check is intentionally shallow. Existing roots are ignored, and only
        a newly discovered top-level root is scanned by the next event or settle
        pass. This keeps World Select discovery event-driven and bounded.
        """
        unseen = []
        for root in self.get_targets():
            try:
                if root in self._known_target_roots:
                    continue
            except Exception:
                pass
            unseen.append(root)
        return unseen

    def _on_theme_relevant_event(self, event) -> None:
        """Queue an incremental theme pass for a relevant wx event."""
        try:
            event.Skip()
        except Exception:
            pass

        if not self._theme_active or not self.watch_new_controls:
            return

        # A hide event does not require theming. The corresponding show event
        # will queue the control when it becomes visible again.
        try:
            if isinstance(event, wx.ShowEvent) and not event.IsShown():
                return
        except Exception:
            pass

        window = self._event_window(event)
        if window is not None:
            if self._is_within_theme_owned(window):
                return
            if self.skip_canvas and self._looks_like_canvas(window):
                return
            target = self._event_theme_target(window)
            try:
                self._pending_theme_windows.add(target)
            except Exception:
                pass
            # Main-window controls remain subtree-scoped. Controls inside a
            # separate dialog promote that dialog to one bounded root pass so
            # the outer client background is not left in the native light color.
            # The settle pass still catches controls attached moments later.
            self._schedule_settle_retheme(target)

        if self._event_retheme_pending:
            return

        self._event_retheme_pending = True
        try:
            self._event_retheme_call = wx.CallLater(
                EVENT_RETHEME_DELAY_MS,
                self._event_retheme_once,
            )
        except Exception:
            self._event_retheme_call = None
            self._event_retheme_pending = False

    def _event_retheme_once(self) -> None:
        """Apply one bounded incremental theme pass to queued roots."""
        self._event_retheme_call = None
        self._event_retheme_pending = False
        if not self._theme_active:
            return

        pending = list(self._pending_theme_windows)
        try:
            self._pending_theme_windows.clear()
        except Exception:
            self._pending_theme_windows = weakref.WeakSet()

        # Include only genuinely new in-scope top-level roots. This covers a
        # World Select instance created after Close World for either target scope
        # without rescanning top-level windows that were already themed.
        pending.extend(self._unseen_target_roots())

        roots = self._deduplicate_theme_roots(pending)
        if not roots:
            return

        try:
            result = self.apply(
                quiet=True,
                from_watcher=True,
                roots_override=roots,
            )
            self._event_batch_count += 1
            self._event_window_count += len(roots)

            # Normal no-change watcher passes stay silent. A concise line is
            # emitted only when the event actually changed a control or failed.
            if result["changed"] or result["failed"]:
                report = (
                    f"Event changed={result['changed']}, "
                    f"unchanged={result['unchanged']}, "
                    f"skipped={result['skipped']}, "
                    f"failed={result['failed']}, "
                    f"controls={result['controls']}"
                )
                if report != self._last_event_report:
                    self._last_event_report = report
                    self.log(report)
        except Exception as exc:
            self.log(f"Event re-theme failed: {exc}")

    def _settle_retheme_once(self) -> None:
        """Theme complete affected windows after staged UI construction settles."""
        self._settle_retheme_call = None
        if not self._theme_active or not self.watch_new_controls:
            return

        pending = list(self._pending_settle_roots)
        try:
            self._pending_settle_roots.clear()
        except Exception:
            self._pending_settle_roots = weakref.WeakSet()

        # Root activity can precede construction of a new dialog. Discovering
        # unseen roots here lets the delayed settle pass catch the completed
        # World Select window while leaving all existing top-level windows alone.
        pending.extend(self._unseen_target_roots())
        roots = self._deduplicate_theme_roots(pending)
        if not roots:
            return

        try:
            result = self.apply(
                quiet=True,
                from_watcher=True,
                roots_override=roots,
            )
            self._settle_batch_count += 1
            if result["changed"] or result["failed"]:
                report = (
                    f"Settle changed={result['changed']}, "
                    f"unchanged={result['unchanged']}, "
                    f"skipped={result['skipped']}, "
                    f"failed={result['failed']}, "
                    f"controls={result['controls']}"
                )
                if report != self._last_event_report:
                    self._last_event_report = report
                    self.log(report)
        except Exception as exc:
            self.log(f"Settle re-theme failed: {exc}")

    # ------------------------------------------------------------
    # Restore and lightweight diagnostics
    # ------------------------------------------------------------

    def restore(self) -> Dict[str, int]:
        """Restore recorded controls to their original visual state."""
        self._theme_active = False
        self._event_retheme_pending = False
        for call_name in ("_event_retheme_call", "_settle_retheme_call"):
            pending_call = getattr(self, call_name, None)
            setattr(self, call_name, None)
            if pending_call is not None:
                try:
                    pending_call.Stop()
                except Exception:
                    pass
        try:
            self._currently_hovered_buttons.clear()
            self._pending_theme_windows.clear()
            self._pending_settle_roots.clear()
        except Exception:
            pass
        # Watch handlers stay bound and become inert while the theme is off.
        # Keeping the WeakSet prevents duplicate Bind calls after re-applying.
        restored = failed = 0
        for window, colors in list(self._original_colors.items()):
            try:
                bg, fg = colors
                window.SetBackgroundColour(bg)
                window.SetForegroundColour(fg)
                window.Refresh(False)
                restored += 1
            except Exception:
                failed += 1
        for window, state in list(self._original_extra_state.items()):
            try:
                if flatnotebook is None or not isinstance(window, flatnotebook.FlatNotebook):
                    continue
                reverse_calls = {
                    "GetActiveTabColour": "SetActiveTabColour",
                    "GetActiveTabTextColour": "SetActiveTabTextColour",
                    "GetNonActiveTabTextColour": "SetNonActiveTabTextColour",
                    "GetTabAreaColour": "SetTabAreaColour",
                }
                for getter_name, setter_name in reverse_calls.items():
                    if getter_name in state:
                        setter = getattr(window, setter_name, None)
                        if setter is not None:
                            setter(state[getter_name])
            except Exception:
                pass
        for root in self.get_targets():
            try:
                root.Layout()
                root.Refresh()
            except Exception:
                pass
        return {"restored": restored, "failed": failed}

    def status_lines(self) -> List[str]:
        """Return human-readable controller status lines for the interface and reports."""
        owner = self.owner_ref()
        roots = self.get_targets()
        controls, truncated = self.walk_windows(roots, include_hidden=False)
        class_counts = collections.Counter(self._safe_class_name(window) for _, window in controls)
        lines = [
            "=== DARK MODE UI STATUS ===",
            f"Owner alive: {owner is not None}",
            f"Theme active: {self._theme_active}",
            f"Scope mode: {self.scope_mode}",
            f"Target roots: {len(roots)}",
            f"Visible controls: {len(controls)}",
            f"Truncated: {truncated}",
            f"Saved original colors: {len(list(self._original_colors.items()))}",
            f"Hover-bound buttons: {len(list(self._hover_bound_windows))}",
            f"Watch-bound windows: {len(list(self._watch_bound_windows))}",
            f"Root activity / dialog-size watchers: {len(list(self._root_activity_bound_windows))}",
            f"Known target roots: {len(list(self._known_target_roots))}",
            f"Queued event windows: {len(list(self._pending_theme_windows))}",
            f"Queued settle roots: {len(list(self._pending_settle_roots))}",
            f"Incremental event batches: {self._event_batch_count}",
            f"Incremental event roots themed: {self._event_window_count}",
            f"Settle passes: {self._settle_batch_count}",
            f"Config path: {_display_path(_config_path())}",
            f"Apply when editor loads: {bool(_load_config().get('enabled_on_editor_load', False))}",
            f"Preserve selection value colors: {self.preserve_selection_colors}",
            f"Color coordinate labels: {self.color_coordinate_labels}",
            f"Custom UI exclusion prefix: {CUSTOM_UI_NAME_PREFIX}",
            "Class counts:",
        ]
        for class_name, count in class_counts.most_common(20):
            lines.append(f"  {count:4d}  {class_name}")
        lines.append("=== END DARK MODE UI STATUS ===")
        return lines


# -----------------------------------------------------------------------------
# Self-themed Dark Mode UI foundation
# -----------------------------------------------------------------------------
# The Operations-panel host remains part of Amulet, while its Open Window
# button uses the same self-painted launcher control as the other utility
# plugins. The floating interface and all descendants use shared theme-
# ownership markers and are skipped by the controller.
FLOATING_DEFAULT_SIZE = (520, 760)
FLOATING_MIN_SIZE = (440, 580)
SETTINGS_VIEWPORT_HEIGHT = 300
SETTINGS_GROW_PROPORTION = 4
CONSOLE_GROW_PROPORTION = 1
CONSOLE_MIN_TEXT_HEIGHT = 150
CONSOLE_MIN_CARD_HEIGHT = 194
FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT = 720
MANAGE_DIALOG_DEFAULT_SIZE = (560, 460)
MANAGE_DIALOG_MIN_SIZE = (554, 410)
MAX_CONFIG_FILE_BYTES = 1024 * 1024

UI_CARD_MARGIN = 10
UI_CARD_PADDING = 12
UI_CONTROL_GAP = 7
UI_CHECKBOX_GAP = 2
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


# ModernChoice retains the shared selector implementation. Dark Mode UI uses
# the text-only path, while the optional icon path remains self-contained for
# compatibility with the common Amulet Utility Plugin control foundation.
CHOICE_POPUP_RADIUS = 12
CHOICE_SELECTOR_ICON_COLUMNS = 4
CHOICE_SELECTOR_VISIBLE_ROWS = 4
CHOICE_SELECTOR_TILE_HEIGHT = 104
CHOICE_SELECTOR_ICON_SIZE = 72
CHOICE_SELECTOR_MIN_WIDTH = 520
CHOICE_SELECTOR_GRID_GAP = 5
CHOICE_SELECTOR_POPUP_RADIUS = CHOICE_POPUP_RADIUS

# Matte black and deep graphite match the plugin's purpose. A restrained
# steel-gray accent distinguishes interactive controls without making the
# interface visually dominant.
DARK_MODE_UI_THEME = {
    "window": wx.Colour(8, 9, 11),
    "surface": wx.Colour(18, 20, 23),
    "surface_alt": wx.Colour(13, 15, 18),
    "surface_hover": wx.Colour(34, 37, 42),
    "surface_pressed": wx.Colour(48, 52, 59),
    "border": wx.Colour(62, 67, 75),
    "border_soft": wx.Colour(43, 47, 54),
    "text": wx.Colour(235, 237, 241),
    "muted": wx.Colour(156, 162, 173),
    "accent": wx.Colour(82, 91, 103),
    "accent_hover": wx.Colour(101, 112, 127),
    "accent_pressed": wx.Colour(65, 72, 82),
    "disabled": wx.Colour(78, 82, 90),
    "console_bg": wx.Colour(0, 0, 0),
    "console_text": wx.Colour(83, 224, 126),
}

# Tooltips use the same active / open control outline as this plugin.
# The two-pixel border is shared by the Windows layered renderer and
# the portable wx fallback so both paths retain the plugin identity.
TOOLTIP_BORDER_COLOUR = DARK_MODE_UI_THEME["accent_hover"]
TOOLTIP_BORDER_WIDTH = 2

# Expanded dropdown windows reserve one near-black colour for the pixels
# outside their rounded shell. Windows makes that exact colour transparent
# through a layered-window colour key, while other platforms clip the same
# integer scanline outline with wx.Region.
CHOICE_POPUP_TRANSPARENT_COLOUR = wx.Colour(1, 2, 3)


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
    """Apply native Windows dark styling to supported child scrollbars.

    Custom scroll areas use ModernScrollBar. Native editors such as wx.TextCtrl
    still own their platform scrollbars, so this requests the dark Explorer theme
    without changing the global application theme. Unsupported systems safely
    retain their existing native appearance.
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
    return DARK_MODE_UI_THEME["window"]


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
            DARK_MODE_UI_THEME["muted"] if muted else DARK_MODE_UI_THEME["text"]
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


# -----------------------------------------------------------------------------
# Layered and portable tooltip support
# -----------------------------------------------------------------------------

def _rounded_scanline_inset(width, height, radius, y):
    """Return the opaque left inset for one row of a rounded rectangle.

    Tooltip painting and the top-level window region use this exact same
    integer scanline calculation. Keeping both masks identical prevents the
    shaped window from exposing pixels that the painted card did not cover.
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
        self._fill = background or DARK_MODE_UI_THEME["surface"]
        self._border = border or DARK_MODE_UI_THEME["border_soft"]
        self._radius = radius
        # Dropdown and tooltip windows pass an explicit clear colour here.
        # Their scanline painter assigns every visible edge pixel directly
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
        # Busy is a visual and interaction state separate from the native wx
        # enabled flag, keeping custom painting and input behavior consistent.
        self._busy = False
        # Logical availability remains owned by the custom control while the
        # underlying wx window stays enabled for reliable custom interaction.
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
        return bool(self._available)

    def Enable(self, enable=True):
        # Protected buttons may ignore framework-side Disable calls when their
        # logical availability is managed by the custom control.
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
            return DARK_MODE_UI_THEME["surface_alt"], DARK_MODE_UI_THEME["disabled"], DARK_MODE_UI_THEME["border_soft"]
        if self._primary:
            if self._pressed:
                fill = DARK_MODE_UI_THEME["accent_pressed"]
            elif self._hovered:
                fill = DARK_MODE_UI_THEME["accent_hover"]
            else:
                fill = DARK_MODE_UI_THEME["accent"]
            return fill, DARK_MODE_UI_THEME["text"], fill
        if self._pressed:
            fill = DARK_MODE_UI_THEME["surface_pressed"]
        elif self._hovered:
            fill = DARK_MODE_UI_THEME["surface_hover"]
        else:
            fill = DARK_MODE_UI_THEME["surface_alt"]
        return fill, DARK_MODE_UI_THEME["text"], DARK_MODE_UI_THEME["border"]

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
            gc.SetPen(wx.Pen(DARK_MODE_UI_THEME["accent_hover"], 1))
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
        fill = DARK_MODE_UI_THEME["accent"] if self._value and enabled else DARK_MODE_UI_THEME["surface_alt"]
        if self._hovered and enabled and not self._value:
            fill = DARK_MODE_UI_THEME["surface_hover"]
        border = DARK_MODE_UI_THEME["accent_hover"] if self.HasFocus() and enabled else DARK_MODE_UI_THEME["border"]
        text_color = DARK_MODE_UI_THEME["text"] if enabled else DARK_MODE_UI_THEME["disabled"]
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetPen(wx.Pen(border, 1))
        gc.SetBrush(wx.Brush(fill))
        gc.DrawRoundedRectangle(box_x + 0.5, box_y + 0.5, box_size - 1, box_size - 1, _dip(self, 4))
        if self._value:
            gc.SetPen(wx.Pen(DARK_MODE_UI_THEME["text"], max(2, _dip(self, 2))))
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


class ModernScrollViewport(wx.Panel):
    """Manual clipped viewport for custom Dark Mode UI scrolling areas.

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
        self._background = background or DARK_MODE_UI_THEME["window"]
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
        gc.SetBrush(wx.Brush(DARK_MODE_UI_THEME["surface_alt"]))
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
            DARK_MODE_UI_THEME["accent_hover"]
            if self._dragging
            else DARK_MODE_UI_THEME["accent"]
            if self._hovered
            else DARK_MODE_UI_THEME["border"]
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
                DARK_MODE_UI_THEME["surface_alt"],
                DARK_MODE_UI_THEME["disabled"],
                DARK_MODE_UI_THEME["border_soft"],
            )
        if self._pressed:
            return (
                DARK_MODE_UI_THEME["accent_pressed"],
                DARK_MODE_UI_THEME["text"],
                DARK_MODE_UI_THEME["accent_pressed"],
            )
        if self._hovered:
            return (
                DARK_MODE_UI_THEME["surface_hover"],
                DARK_MODE_UI_THEME["text"],
                DARK_MODE_UI_THEME["accent_hover"],
            )
        if self._selected:
            return (
                DARK_MODE_UI_THEME["surface_pressed"],
                DARK_MODE_UI_THEME["text"],
                DARK_MODE_UI_THEME["accent"],
            )
        return (
            DARK_MODE_UI_THEME["surface_alt"],
            DARK_MODE_UI_THEME["text"],
            DARK_MODE_UI_THEME["border_soft"],
        )


class ModernIconChoiceOption(ModernChoiceOption):
    """One selectable tile with centered artwork and an overlaid label."""

    def __init__(self, parent, label, bitmap, selected=False):
        super().__init__(
            parent,
            label,
            selected=selected,
            row_height=CHOICE_SELECTOR_TILE_HEIGHT,
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

        # Center the complete icon canvas in the tile instead of reserving a
        # separate area below the label. The label is drawn afterward so long
        # names can safely overlay transparent or visible parts of the icon.
        bitmap = self._bitmap
        bitmap_ok = False
        try:
            bitmap_ok = bool(bitmap is not None and bitmap.IsOk())
        except Exception:
            bitmap_ok = False
        if bitmap_ok:
            bitmap_width = float(bitmap.GetWidth())
            bitmap_height = float(bitmap.GetHeight())
            gc.DrawBitmap(
                bitmap,
                (size.width - bitmap_width) / 2.0,
                (size.height - bitmap_height) / 2.0,
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
                gc.SetFont(placeholder_font, DARK_MODE_UI_THEME["muted"])
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
        shadow_color = DARK_MODE_UI_THEME["console_bg"]
        for line in lines:
            text_width, text_height = _graphics_text_size(gc, line)
            text_x = (size.width - text_width) / 2.0
            # A one-pixel dark shadow keeps the label readable when it overlaps
            # bright icon pixels without moving the icon away from the center.
            gc.SetFont(self.GetFont(), shadow_color)
            gc.DrawText(line, text_x + 1, line_y + 1)
            gc.SetFont(self.GetFont(), text_color)
            gc.DrawText(line, text_x, line_y)
            line_y += text_height + _dip(self, 1)

        if self.HasFocus() and self.IsAvailable() and not self.IsBusy():
            gc.SetPen(wx.Pen(DARK_MODE_UI_THEME["accent_hover"], 1))
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
            f"{CUSTOM_UI_NAME_PREFIX}:DarkModeUIChoicePopup",
        )
        self._owner_ref = weakref.ref(owner)
        self._buttons = []
        self._dismiss_notified = True
        self._closing = False
        self._popup_radius = CHOICE_SELECTOR_POPUP_RADIUS
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
            background=DARK_MODE_UI_THEME["surface"],
            border=DARK_MODE_UI_THEME["border"],
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
            background=DARK_MODE_UI_THEME["surface"],
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
        """Rebuild text rows or the scrollable four-column slab grid."""
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
                cols=CHOICE_SELECTOR_ICON_COLUMNS,
                vgap=_dip(self._list_content, CHOICE_SELECTOR_GRID_GAP),
                hgap=_dip(self._list_content, CHOICE_SELECTOR_GRID_GAP),
            )
            self._content.Add(grid, 0, wx.EXPAND)
            for index, label in enumerate(choices):
                button = ModernIconChoiceOption(
                    self._list_content,
                    label,
                    owner.GetIconBitmap(label, CHOICE_SELECTOR_ICON_SIZE),
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
                _dip(owner, CHOICE_SELECTOR_MIN_WIDTH),
            )
            rows = max(
                1,
                (
                    len(choices)
                    + CHOICE_SELECTOR_ICON_COLUMNS
                    - 1
                )
                // CHOICE_SELECTOR_ICON_COLUMNS,
            )
            visible_rows = min(rows, CHOICE_SELECTOR_VISIBLE_ROWS)
            tile_height = _dip(owner, CHOICE_SELECTOR_TILE_HEIGHT)
            grid_gap = _dip(owner, CHOICE_SELECTOR_GRID_GAP)
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

        # Use the side that can show the most content. A side that can satisfy
        # the normal minimum height is preferred, but the popup is allowed to
        # become shorter on small displays rather than extending off-screen.
        if available_below >= minimum_height:
            open_below = True
        elif available_above >= minimum_height:
            open_below = False
        else:
            open_below = available_below >= available_above

        available_height = available_below if open_below else available_above
        height = max(1, min(preferred_height, available_height or usable_height))

        # Center the popup on the selector while keeping the complete native
        # window inside the monitor work area. This remains safe on mixed-DPI
        # or multi-monitor layouts because the display is chosen from the
        # selector's screen-space center.
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

        # Windows may finalize a borderless frame at a slightly different
        # physical size after it becomes visible, especially with display
        # scaling. Re-clamp the realized window so no edge can remain beyond
        # the monitor's usable area.
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
        self._fill = DARK_MODE_UI_THEME["surface_alt"]
        self._radius = 9
        self._popup = None
        self._popup_open = False
        self._suppress_popup_until = 0.0
        self._icon_provider = icon_provider
        self._show_icons = bool(show_icons)

        self.SetBackgroundColour(self._fill)
        self.SetForegroundColour(DARK_MODE_UI_THEME["text"])
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
            child.SetForegroundColour(DARK_MODE_UI_THEME["text"])
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
            # Request the compact preview directly from the provider so the
            # original item texture is scaled only once for the closed field.
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
                DARK_MODE_UI_THEME["surface_alt"],
                DARK_MODE_UI_THEME["disabled"],
                DARK_MODE_UI_THEME["border_soft"],
            )
        if self._pressed:
            fill = DARK_MODE_UI_THEME["surface_pressed"]
        elif self._hovered or self._popup_open:
            fill = DARK_MODE_UI_THEME["surface_hover"]
        else:
            fill = DARK_MODE_UI_THEME["surface_alt"]
        border = (
            DARK_MODE_UI_THEME["accent_hover"]
            if self.HasFocus() or self._popup_open
            else DARK_MODE_UI_THEME["border"]
        )
        return fill, DARK_MODE_UI_THEME["text"], border

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
        # rounded focus border around the selected item artwork.
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


class ModernTextField(RoundedPanel):
    """Rounded wrapper around a native text editor for reliable keyboard input."""

    _FORWARDED_EVENTS = (wx.EVT_TEXT, wx.EVT_TEXT_ENTER, wx.EVT_KILL_FOCUS, wx.EVT_SET_FOCUS)

    def __init__(self, parent, value="", width=64):
        super().__init__(parent, background=DARK_MODE_UI_THEME["surface_alt"], border=DARK_MODE_UI_THEME["border"], radius=8)
        self.SetMinSize((_dip(self, width), _dip(self, 32)))
        sizer = wx.BoxSizer(wx.VERTICAL)
        self._text = wx.TextCtrl(
            self,
            value=str(value),
            style=wx.BORDER_NONE | wx.TE_CENTER | wx.TE_PROCESS_ENTER,
        )
        _mark_custom_ui_owned(self._text)
        self._text.SetBackgroundColour(DARK_MODE_UI_THEME["surface_alt"])
        self._text.SetForegroundColour(DARK_MODE_UI_THEME["text"])
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
        # visual center. This asymmetric spacing centers the enlarged number
        # without changing the outer field size.
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
        self._border = DARK_MODE_UI_THEME["accent_hover"] if self._text.HasFocus() else DARK_MODE_UI_THEME["border"]
        self.Refresh(False)
        event.Skip()


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
            background=DARK_MODE_UI_THEME["surface"],
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
            background=DARK_MODE_UI_THEME["surface"],
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
                DARK_MODE_UI_THEME["surface"],
            )
            text_rgba = _wx_colour_tuple(
                DARK_MODE_UI_THEME["text"],
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

class DarkMessageDialog(wx.Dialog):
    """Self-themed replacement for wx.MessageDialog."""

    def __init__(self, parent, message, caption, style=wx.OK | wx.CENTRE):
        dialog_style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        super().__init__(parent, title=str(caption), style=dialog_style)
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:DarkModeUIDialog",
        )
        self._message_style = int(style)
        self.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
        self.SetMinSize((_dip(self, 390), _dip(self, 190)))

        root = wx.Panel(self, style=wx.BORDER_NONE | wx.CLIP_CHILDREN)
        _mark_custom_ui_owned(root)
        root.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
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


class DarkActionPickerDialog(wx.Dialog):
    """Resizable self-themed action picker for Manage Plugin Files."""

    def __init__(
        self,
        parent,
        actions,
        initial_size=None,
        on_size_changed=None,
    ):
        super().__init__(
            parent,
            title="Manage Dark Mode UI settings",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:DarkModeUISettingsDialog",
        )
        self._actions = list(actions)
        self._selection = wx.NOT_FOUND
        self._on_size_changed = on_size_changed
        self.SetBackgroundColour(DARK_MODE_UI_THEME["window"])

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
        root.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
        outer = wx.BoxSizer(wx.VERTICAL)

        title = _make_text(
            root,
            "MANAGE PLUGIN FILES",
            point_size=14,
            bold=True,
        )
        outer.Add(
            title,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP,
            _dip(root, 18),
        )

        self._description = _make_text(
            root,
            "Choose what to do with Dark Mode UI.config.",
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
            background=DARK_MODE_UI_THEME["surface"],
            border=DARK_MODE_UI_THEME["border_soft"],
            radius=10,
        )
        card_sizer = wx.BoxSizer(wx.VERTICAL)

        self._scroll = ModernScrollViewport(
            list_card,
            background=DARK_MODE_UI_THEME["surface"],
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
        card_sizer.Add(
            list_row,
            1,
            wx.EXPAND | wx.ALL,
            _dip(list_card, 6),
        )
        list_card.SetSizer(card_sizer)
        outer.Add(
            list_card,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT,
            _dip(root, 18),
        )

        button_row = wx.BoxSizer(wx.HORIZONTAL)
        button_row.AddStretchSpacer(1)
        self._open_button = ModernButton(
            root,
            "Open",
            primary=True,
            compact=True,
        )
        self._open_button.Enable(False)
        self._open_button.SetMinSize((_dip(root, 96), _dip(root, 36)))
        self._open_button.Bind(
            wx.EVT_BUTTON,
            lambda _event: self._open(self._selection),
        )
        close_button = ModernButton(root, "Close", compact=True)
        close_button.SetMinSize((_dip(root, 96), _dip(root, 36)))
        close_button.Bind(
            wx.EVT_BUTTON,
            lambda _event: self.EndModal(wx.ID_CANCEL),
        )
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
        """Synchronize the action list and custom scrollbar."""
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

        if self._on_size_changed is not None:
            try:
                self._on_size_changed(self)
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
        self._description.Wrap(
            max(
                _dip(self, 320),
                self.GetClientSize().width - _dip(self, 70),
            )
        )
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
        if (
            key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
            and self._selection != wx.NOT_FOUND
        ):
            self.EndModal(wx.ID_OK)
            return
        event.Skip()


# -----------------------------------------------------------------------------
# Floating window and compact Amulet host
# -----------------------------------------------------------------------------
class DarkModeUIWindow(wx.Frame):
    """Single modeless Dark Mode UI window owned by the Amulet operation host."""

    def __init__(self, parent, host):
        style = wx.DEFAULT_FRAME_STYLE
        style |= getattr(wx, "FRAME_FLOAT_ON_PARENT", 0)
        super().__init__(
            parent,
            title="Dark Mode UI",
            size=FLOATING_DEFAULT_SIZE,
            style=style,
        )
        _mark_custom_ui_owned(
            self,
            f"{CUSTOM_UI_NAME_PREFIX}:DarkModeUIWindow",
        )
        self._host_ref = weakref.ref(host)
        self._allow_destroy = False
        self.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
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
        host = self._host_ref()
        if host is not None:
            host._remember_window_size()
            host._save_current_config()
            host._hide_control_help()
            host._hide_console_help()
        self.Hide()
        if host is not None:
            host._update_launcher_status()

    def _on_show(self, event):
        host = self._host_ref()
        if host is not None:
            host._update_launcher_status()
        event.Skip()


class PluginClassName(wx.Panel, DefaultOperationUI):
    """Persistent Amulet dark-mode controller with a self-themed floating UI."""

    CONSOLE_SEMANTIC_NAME = f"{PLUGIN_CONSOLE_NAME_PREFIX}:DarkModeUI"
    CONSOLE_TOOLTIP_DELAY_MS = 650
    CONTROL_TOOLTIP_DELAY_MS = 550

    def __init__(self, parent: wx.Window, canvas, world, options_path: str):
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)

        self._report_lines: List[str] = []
        self._loaded_config = _load_config()
        self._plugin_window = None
        self._window_has_been_shown = False
        self._destroying = False
        self._console_visible = bool(
            self._loaded_config.get("console_visible", True)
        )
        self._normal_window_size = self._validated_window_size(
            self._loaded_config.get("window_size", FLOATING_DEFAULT_SIZE)
        )
        self._manage_dialog_size = self._validated_manage_dialog_size(
            self._loaded_config.get(
                "manage_window_size",
                MANAGE_DIALOG_DEFAULT_SIZE,
            )
        )
        known_config_keys = set(_default_config())
        self._config_unknown_data = {
            key: value
            for key, value in self._loaded_config.items()
            if key not in known_config_keys
        }

        self._control_help_window = None
        self._control_help_call = None
        self._control_help_anchor_ref = None
        self._control_help_text = ""
        self._console_help_window = None
        self._console_help_call = None
        self._console_help_hovered = False
        self._console_help_text = (
            "Shows Dark Mode UI status, theme operations, diagnostics, and "
            "control scans. Click or focus the console to select and copy text."
        )

        self._build_launcher_ui()
        self._build_floating_ui()

        self.controller = self._get_controller()
        self.controller.add_logger(self._append_log_text_from_controller)

        self._set_tooltips()
        self._set_console_visibility(self._console_visible, save=False)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_host_destroy)

        self._log("Ready. Dark Mode UI")
        try:
            wx.CallAfter(self._show_plugin_window)
        except Exception:
            self._show_plugin_window()

    # ------------------------------------------------------------------
    # Launcher and window shell
    # ------------------------------------------------------------------

    def _build_launcher_ui(self) -> None:
        """Build the compact native host shown in Amulet's Operations tab."""
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)
        margin = 6

        title = wx.StaticText(self, label="Dark Mode UI")
        try:
            font = title.GetFont()
            font.SetPointSize(max(font.GetPointSize(), 10))
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            title.SetFont(font)
        except Exception:
            pass
        outer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, margin)

        description = wx.StaticText(self, label="Floating interface.")
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
        """Create one rounded settings card and return its vertical sizer."""
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
    ):
        label_control = _make_text(card, label, point_size=9, bold=True)
        sizer.Add(
            label_control,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CONTROL_GAP,
        )
        choice = ModernChoice(card, choices)
        self._set_control_tooltip(choice, tooltip)
        sizer.Add(
            choice,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        return label_control, choice

    def _build_labeled_number(
        self,
        card,
        sizer,
        label,
        value,
        tooltip,
        width=110,
    ):
        row = wx.BoxSizer(wx.HORIZONTAL)
        label_control = _make_text(card, label, point_size=9, bold=True)
        row.Add(
            label_control,
            1,
            wx.RIGHT | wx.ALIGN_CENTER_VERTICAL,
            _dip(card, 10),
        )
        field = ModernTextField(card, value=str(value), width=width)
        # Keep the tooltip on the descriptive label only. The number field is
        # primarily an editing target, so showing help while the user is trying
        # to change the value would be more distracting than useful.
        self._set_control_tooltip(label_control, tooltip)
        row.Add(field, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(
            row,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_PADDING,
        )
        return label_control, field

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

    def _build_floating_ui(self) -> None:
        """Build the complete matte-black Dark Mode UI interface."""
        owner = wx.GetTopLevelParent(self) or self
        self._plugin_window = DarkModeUIWindow(owner, self)
        self._plugin_window.SetSize(self._normal_window_size)
        self._plugin_window.Bind(wx.EVT_SIZE, self._on_window_size)

        root = wx.Panel(
            self._plugin_window,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(
            root,
            f"{CUSTOM_UI_NAME_PREFIX}:DarkModeUIRoot",
        )
        root.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
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
            f"{CUSTOM_UI_NAME_PREFIX}:DarkModeUIMainContent",
        )
        self._main_content_panel.SetBackgroundColour(
            DARK_MODE_UI_THEME["window"]
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
        header.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
        header_sizer = wx.BoxSizer(wx.VERTICAL)
        header.SetSizer(header_sizer)

        title = _make_text(header, "DARK MODE UI", point_size=18, bold=True)
        subtitle = _make_wrapped_text(
            header,
            "Reversible Amulet theming, compatibility controls, and diagnostics",
            point_size=9,
            muted=True,
        )
        header_sizer.Add(
            title,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            16,
        )
        header_sizer.Add(
            subtitle,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM | wx.EXPAND,
            16,
        )
        main_content_sizer.Add(header, 0, wx.EXPAND)
        self._floating_header = header

        settings_host = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(settings_host)
        settings_host.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
        settings_row = wx.BoxSizer(wx.HORIZONTAL)
        settings_host.SetSizer(settings_row)

        self.scroll = ModernScrollViewport(
            settings_host,
            background=DARK_MODE_UI_THEME["window"],
        )
        _mark_custom_ui_owned(
            self.scroll,
            f"{CUSTOM_UI_NAME_PREFIX}:DarkModeUISettings",
        )
        self.scroll.SetMinSize((-1, SETTINGS_VIEWPORT_HEIGHT))
        self.settings_content_panel = self.scroll.GetContentWindow()
        content = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetContentSizer(content)
        content.AddSpacer(_dip(self.scroll, 4))

        scope_card, scope_sizer = self._create_card(
            self.settings_content_panel,
            "Scope and Startup",
            "Choose which Amulet windows are themed and whether dark mode "
            "returns automatically when the editor loads.",
        )
        _, self.scope_choice = self._build_labeled_choice(
            scope_card,
            scope_sizer,
            "Target scope",
            ("This Amulet window", "All top-level wx windows"),
            "Theme only the active Amulet window and its owned dialogs, or all "
            "stable top-level wx windows such as World Select.",
        )
        self.scope_choice.SetSelection(
            1
            if str(self._loaded_config.get("scope_mode", "top")) == "all"
            else 0
        )

        self.apply_on_editor_load = ModernCheckBox(
            scope_card,
            "Apply dark mode when editor loads",
            bool(self._loaded_config.get("enabled_on_editor_load", False)),
        )
        _tighten_gap_before_checkbox(scope_sizer)
        scope_sizer.Add(
            self.apply_on_editor_load,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )
        scope_sizer.AddSpacer(UI_CHECKBOX_CONTROL_GAP)
        _add_checkbox_group_bottom_spacing(scope_sizer)
        content.Add(
            scope_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        compatibility_card, compatibility_sizer = self._create_card(
            self.settings_content_panel,
            "Compatibility",
            "These safeguards control incremental theming and preserve Amulet's "
            "specialized controls where appropriate.",
        )

        self.watch_new_controls = ModernCheckBox(
            compatibility_card,
            "Watch newly shown panels",
            bool(self._loaded_config.get("watch_new_controls", True)),
        )
        self.skip_canvas = ModernCheckBox(
            compatibility_card,
            "Skip OpenGL / canvas-like controls",
            bool(self._loaded_config.get("skip_canvas", True)),
        )
        self.button_hover_safe = ModernCheckBox(
            compatibility_card,
            "Keep button hover text readable",
            bool(self._loaded_config.get("button_hover_safe", True)),
        )
        self.preserve_selection_colors = ModernCheckBox(
            compatibility_card,
            "Preserve / darken selection value colors",
            bool(self._loaded_config.get("preserve_selection_colors", True)),
        )
        self.color_coordinate_labels = ModernCheckBox(
            compatibility_card,
            "Color coordinate labels",
            bool(self._loaded_config.get("color_coordinate_labels", False)),
        )
        self.try_flatnotebook = ModernCheckBox(
            compatibility_card,
            "Theme notebook / tab colors",
            bool(self._loaded_config.get("try_flatnotebook", True)),
        )

        compatibility_checkboxes = (
            self.watch_new_controls,
            self.skip_canvas,
            self.button_hover_safe,
            self.preserve_selection_colors,
            self.color_coordinate_labels,
            self.try_flatnotebook,
        )
        for index, checkbox in enumerate(compatibility_checkboxes):
            # Keep every check box on the same left and right alignment. wx
            # applies one border value to every flagged side, so the vertical
            # gap must be a separate spacer instead of changing the border.
            _tighten_gap_before_checkbox(compatibility_sizer)
            compatibility_sizer.Add(
                checkbox,
                0,
                wx.LEFT | wx.RIGHT | wx.EXPAND,
                UI_CARD_PADDING,
            )
            compatibility_sizer.AddSpacer(
                UI_CHECKBOX_CONTROL_GAP
                if index == len(compatibility_checkboxes) - 1
                else UI_CHECKBOX_GAP
            )
        _add_checkbox_group_bottom_spacing(compatibility_sizer)
        content.Add(
            compatibility_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        limits_card, limits_sizer = self._create_card(
            self.settings_content_panel,
            "Traversal Limits",
            "Bounded limits prevent unexpectedly deep or oversized UI scans.",
        )
        _, self.max_depth = self._build_labeled_number(
            limits_card,
            limits_sizer,
            "Maximum depth",
            int(self._loaded_config.get("max_depth", 18)),
            "Maximum number of parent / child UI levels inspected from each "
            "target window during theming and diagnostics. Lower values reduce "
            "work but may leave unusually deep controls untouched. Allowed "
            "range: 1 through 40.",
        )
        _, self.max_controls = self._build_labeled_number(
            limits_card,
            limits_sizer,
            "Maximum controls",
            int(self._loaded_config.get("max_controls", 1500)),
            "Maximum total controls inspected during one theme, status, or scan "
            "pass. The pass stops and reports truncation when this limit is "
            "reached. Allowed range: 100 through 5000.",
            width=130,
        )
        content.Add(
            limits_card,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_CARD_MARGIN,
        )

        tools_card, tools_sizer = self._create_card(
            self.settings_content_panel,
            "Tools and Diagnostics",
            "Save settings, inspect the controller, scan Amulet's current UI, "
            "or manage the plugin and its local config file.",
        )
        tools_grid = wx.GridSizer(rows=0, cols=2, vgap=8, hgap=8)

        self.save_settings_button = ModernButton(
            tools_card,
            "Save Settings",
            compact=True,
        )
        self.manage_plugin_files_button = ModernButton(
            tools_card,
            "Manage Plugin Files",
            compact=True,
        )
        self.status_button = ModernButton(
            tools_card,
            "Controller Status",
            compact=True,
        )
        self.scan_button = ModernButton(
            tools_card,
            "Scan UI",
            compact=True,
        )

        for button in (
            self.save_settings_button,
            self.manage_plugin_files_button,
            self.status_button,
            self.scan_button,
        ):
            tools_grid.Add(button, 1, wx.EXPAND)

        tools_sizer.Add(
            tools_grid,
            0,
            wx.LEFT | wx.RIGHT | wx.EXPAND,
            UI_CARD_PADDING,
        )

        self.clear_button = ModernButton(
            tools_card,
            "Clear Log",
            compact=True,
        )
        tools_sizer.Add(
            self.clear_button,
            0,
            wx.ALL | wx.EXPAND,
            UI_CARD_PADDING,
        )
        content.Add(
            tools_card,
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
        main_content_sizer.Add(
            settings_host,
            SETTINGS_GROW_PROPORTION,
            wx.EXPAND,
        )

        footer = wx.Panel(
            self._main_content_panel,
            style=wx.BORDER_NONE | wx.FULL_REPAINT_ON_RESIZE | wx.CLIP_CHILDREN,
        )
        _mark_custom_ui_owned(footer)
        footer.SetBackgroundColour(DARK_MODE_UI_THEME["window"])
        footer_sizer = wx.BoxSizer(wx.VERTICAL)
        footer.SetSizer(footer_sizer)

        status_card = RoundedPanel(
            footer,
            background=DARK_MODE_UI_THEME["surface_alt"],
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

        primary_row = wx.BoxSizer(wx.HORIZONTAL)
        self.apply_dark_button = ModernButton(
            footer,
            "Apply Dark Mode",
            primary=True,
        )
        self.restore_button = ModernButton(
            footer,
            "Restore Saved Colors",
        )
        primary_row.Add(
            self.apply_dark_button,
            1,
            wx.RIGHT | wx.EXPAND,
            _dip(footer, 8),
        )
        primary_row.Add(self.restore_button, 1, wx.EXPAND)
        footer_sizer.Add(
            primary_row,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND,
            UI_FOOTER_MARGIN,
        )

        report_row = wx.BoxSizer(wx.HORIZONTAL)
        self.save_report_button = ModernButton(
            footer,
            "Save Log",
            compact=True,
        )
        self.console_toggle_button = ModernButton(
            footer,
            "Hide Console",
            compact=True,
        )
        report_row.Add(
            self.save_report_button,
            1,
            wx.RIGHT | wx.EXPAND,
            _dip(footer, 8),
        )
        report_row.Add(self.console_toggle_button, 1, wx.EXPAND)
        footer_sizer.Add(
            report_row,
            0,
            wx.ALL | wx.EXPAND,
            UI_FOOTER_MARGIN,
        )
        main_content_sizer.Add(footer, 0, wx.EXPAND)
        self._floating_footer = footer

        self.console_card = RoundedPanel(
            self._main_content_panel,
            background=DARK_MODE_UI_THEME["console_bg"],
            border=DARK_MODE_UI_THEME["border"],
            radius=12,
        )
        console_sizer = wx.BoxSizer(wx.VERTICAL)
        self.console_card.SetSizer(console_sizer)
        console_title = _make_text(
            self.console_card,
            "DARK MODE LOG",
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
            size=(-1, CONSOLE_MIN_TEXT_HEIGHT),
        )
        _mark_custom_ui_owned(self.text, self.CONSOLE_SEMANTIC_NAME)
        self.text.SetForegroundColour(DARK_MODE_UI_THEME["console_text"])
        self.text.SetBackgroundColour(DARK_MODE_UI_THEME["console_bg"])
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
                _dip(self.console_card, CONSOLE_MIN_TEXT_HEIGHT),
            )
        )
        self.console_card.SetMinSize(
            (-1, _dip(root, CONSOLE_MIN_CARD_HEIGHT))
        )
        console_sizer.Add(
            self.text,
            1,
            wx.ALL | wx.EXPAND,
            _dip(self.console_card, 12),
        )
        main_content_sizer.Add(
            self.console_card,
            CONSOLE_GROW_PROPORTION,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            UI_FOOTER_MARGIN,
        )

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(root, 1, wx.EXPAND)
        self._plugin_window.SetSizer(frame_sizer)
        self._plugin_window.Layout()
        self._sync_main_content_width()

        # Settings and action bindings.
        for checkbox in (
            self.apply_on_editor_load,
            self.watch_new_controls,
            self.skip_canvas,
            self.button_hover_safe,
            self.preserve_selection_colors,
            self.color_coordinate_labels,
            self.try_flatnotebook,
        ):
            checkbox.Bind(wx.EVT_CHECKBOX, self._on_live_setting_changed)

        self.scope_choice.Bind(wx.EVT_CHOICE, self._on_live_setting_changed)
        for field in (self.max_depth, self.max_controls):
            field.Bind(wx.EVT_TEXT_ENTER, self._on_limit_field_commit)
            field.Bind(wx.EVT_KILL_FOCUS, self._on_limit_field_commit)

        self.apply_dark_button.Bind(
            wx.EVT_BUTTON,
            self._on_apply_dark_theme,
        )
        self.restore_button.Bind(
            wx.EVT_BUTTON,
            self._on_restore_colors,
        )
        self.save_settings_button.Bind(
            wx.EVT_BUTTON,
            self._on_save_settings,
        )
        self.status_button.Bind(
            wx.EVT_BUTTON,
            self._on_controller_status,
        )
        self.scan_button.Bind(
            wx.EVT_BUTTON,
            self._on_scan_controls,
        )
        self.save_report_button.Bind(
            wx.EVT_BUTTON,
            self._on_save_report,
        )
        self.manage_plugin_files_button.Bind(
            wx.EVT_BUTTON,
            self._manage_plugin_files,
        )
        self.clear_button.Bind(
            wx.EVT_BUTTON,
            self._on_clear_log,
        )
        self.console_toggle_button.Bind(
            wx.EVT_BUTTON,
            self._toggle_console,
        )

        self.console_card.Bind(
            wx.EVT_ENTER_WINDOW,
            self._on_console_help_enter,
        )
        self.console_card.Bind(
            wx.EVT_LEAVE_WINDOW,
            self._on_console_help_leave,
        )
        self.text.Bind(
            wx.EVT_LEFT_DOWN,
            self._hide_console_help_event,
        )
        self.text.Bind(
            wx.EVT_SET_FOCUS,
            self._hide_console_help_event,
        )

        try:
            wx.CallAfter(_try_apply_dark_native_theme, self.text)
            wx.CallAfter(self._refresh_scrolled_custom_controls)
        except Exception:
            pass

    def _show_plugin_window(self, _event=None) -> None:
        """Show, restore, raise, and focus the single floating window."""
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
            window.Layout()
            window.Refresh(False)
            try:
                wx.CallAfter(self._refresh_scrolled_custom_controls)
                wx.CallLater(75, self._refresh_scrolled_custom_controls)
            except Exception:
                pass
        except Exception:
            pass

    def _position_plugin_window_at_amulet_edge(self) -> None:
        """Place the window near Amulet's left edge and clamp it to the work area."""
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

    def _update_launcher_status(self) -> None:
        window = self._plugin_window
        shown = bool(window is not None and window.IsShown())
        self.launcher_status.SetLabel(
            "Status: Open" if shown else "Status: Closed"
        )
        self.open_window_button.SetLabel(
            "Focus Window" if shown else "Open Window"
        )
        try:
            self.Layout()
        except Exception:
            pass

    def _on_window_size(self, event) -> None:
        try:
            event.Skip()
        except Exception:
            pass
        self._remember_window_size()
        try:
            wx.CallAfter(self._refresh_scrolled_custom_controls)
        except Exception:
            pass

    def _remember_window_size(self) -> None:
        window = self._plugin_window
        if window is None:
            return
        try:
            if window.IsIconized() or window.IsMaximized():
                return
            size = window.GetSize()
            candidate = self._validated_window_size(
                (size.width, size.height)
            )
            self._normal_window_size = candidate
        except Exception:
            pass

    @staticmethod
    def _validated_window_size(value):
        try:
            width, height = value
            width = max(FLOATING_MIN_SIZE[0], min(int(width), 2400))
            height = max(FLOATING_MIN_SIZE[1], min(int(height), 1600))
            return width, height
        except Exception:
            return FLOATING_DEFAULT_SIZE

    def _visible_console_minimum_client_height(self):
        """Return the client height required to preserve the console minimum.

        The calculation includes only fixed visible sections, the intended
        settings viewport, and the 194-pixel console-card minimum. Excluding the
        complete root ``CalcMin`` keeps the window compact while protecting the
        console text area.
        """
        window = self._plugin_window
        if window is None:
            return FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT

        required = _dip(window, FLOATING_CONSOLE_VISIBLE_MIN_HEIGHT)
        try:
            header_height = int(self._floating_header.GetBestSize().height)
        except Exception:
            header_height = 0
        try:
            footer_height = int(self._floating_footer.GetBestSize().height)
        except Exception:
            footer_height = 0

        calculated = (
            header_height
            + _dip(window, SETTINGS_VIEWPORT_HEIGHT)
            + footer_height
            + _dip(window, CONSOLE_MIN_CARD_HEIGHT)
            + _dip(window, UI_FOOTER_MARGIN)
        )
        return max(required, calculated)

    def _current_floating_minimum_size(self):
        """Return the active outer-frame minimum for the console state."""
        window = self._plugin_window
        minimum_width = _dip(window, FLOATING_MIN_SIZE[0])
        if not self._console_visible:
            return minimum_width, _dip(window, FLOATING_MIN_SIZE[1])

        minimum_client_height = self._visible_console_minimum_client_height()
        try:
            frame_size = window.GetSize()
            client_size = window.GetClientSize()
            frame_extra_width = max(
                0,
                int(frame_size.width) - int(client_size.width),
            )
            frame_extra_height = max(
                0,
                int(frame_size.height) - int(client_size.height),
            )
        except Exception:
            frame_extra_width = 0
            frame_extra_height = 0

        return (
            minimum_width + frame_extra_width,
            minimum_client_height + frame_extra_height,
        )

    def _update_floating_min_size(self, resize_if_needed=True) -> None:
        """Keep the console card and text area at their required minima."""
        window = self._plugin_window
        if window is None:
            return

        minimum_width, minimum_height = self._current_floating_minimum_size()
        try:
            window.SetMinSize((minimum_width, minimum_height))
        except Exception:
            return

        if not resize_if_needed:
            return

        try:
            if window.IsIconized() or window.IsMaximized():
                return
            size = window.GetSize()
            width = max(int(size.width), int(minimum_width))
            height = max(int(size.height), int(minimum_height))
            if width != size.width or height != size.height:
                window.SetSize((width, height))
        except Exception:
            pass

    def _refresh_scrolled_custom_controls(self) -> None:
        try:
            self.scroll._modern_sync_layout()
        except Exception:
            pass
        try:
            self.settings_scrollbar.Refresh(False)
        except Exception:
            pass

    def _on_settings_scroll(self) -> None:
        try:
            self.settings_scrollbar.Refresh(False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Config and controller helpers
    # ------------------------------------------------------------------

    def _get_controller(self) -> DarkModeController:
        top = self.GetTopLevelParent()
        existing = None
        try:
            existing = getattr(top, CONTROLLER_ATTR_NAME, None)
            if isinstance(existing, DarkModeController):
                return existing
        except Exception:
            existing = None
        _deactivate_replaced_controller(existing)
        controller = DarkModeController(top)
        try:
            setattr(top, CONTROLLER_ATTR_NAME, controller)
        except Exception:
            pass
        return controller

    @staticmethod
    def _validated_manage_dialog_size(value):
        """Return a bounded Manage Plugin Files dialog size."""
        validated = _validated_size_pair(
            value,
            MANAGE_DIALOG_MIN_SIZE,
            MANAGE_DIALOG_DEFAULT_SIZE,
        )
        return tuple(validated)

    def _remember_manage_dialog_size(self, dialog) -> None:
        """Store the current normal Manage Plugin Files dialog size."""
        try:
            size = dialog.GetSize()
            self._manage_dialog_size = self._validated_manage_dialog_size(
                (size.width, size.height)
            )
        except Exception:
            pass

    def _apply_config_data(self, data, resize_window=True) -> None:
        """Apply normalized config values to the visible controls and controller."""
        normalized = _normalize_config_data(data)
        self._loaded_config = normalized
        known_keys = set(_default_config())
        self._config_unknown_data = {
            key: value
            for key, value in normalized.items()
            if key not in known_keys
        }

        self.apply_on_editor_load.SetValue(
            bool(normalized.get("enabled_on_editor_load", False))
        )
        self.scope_choice.SetSelection(
            1 if normalized.get("scope_mode") == "all" else 0
        )
        self.skip_canvas.SetValue(bool(normalized.get("skip_canvas", True)))
        self.try_flatnotebook.SetValue(
            bool(normalized.get("try_flatnotebook", True))
        )
        self.button_hover_safe.SetValue(
            bool(normalized.get("button_hover_safe", True))
        )
        self.preserve_selection_colors.SetValue(
            bool(normalized.get("preserve_selection_colors", True))
        )
        self.color_coordinate_labels.SetValue(
            bool(normalized.get("color_coordinate_labels", False))
        )
        self.watch_new_controls.SetValue(
            bool(normalized.get("watch_new_controls", True))
        )
        self.max_depth.ChangeValue(
            str(normalized.get("max_depth", 18))
        )
        self.max_controls.ChangeValue(
            str(normalized.get("max_controls", 1500))
        )

        self._normal_window_size = self._validated_window_size(
            normalized.get("window_size", FLOATING_DEFAULT_SIZE)
        )
        self._manage_dialog_size = self._validated_manage_dialog_size(
            normalized.get(
                "manage_window_size",
                MANAGE_DIALOG_DEFAULT_SIZE,
            )
        )

        # Apply console visibility before restoring dimensions so the active
        # frame minimum matches the saved layout.
        self._set_console_visibility(
            bool(normalized.get("console_visible", True)),
            save=False,
        )
        if resize_window and self._plugin_window is not None:
            try:
                self._plugin_window.SetSize(self._normal_window_size)
            except Exception:
                pass

        self._normalize_limit_fields()
        self._configure_controller()
        try:
            if self.controller._theme_active:
                self.controller.apply(quiet=True)
        except Exception:
            pass

    @staticmethod
    def _repair_json_missing_line_commas(content):
        """Add only clearly missing commas between adjacent object entries."""
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

    def _attempt_parse_repaired_config(self, content):
        """Attempt bounded data-only JSON repairs and report successful steps."""
        repairs = []

        def try_json(candidate, repair_name):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    if repair_name:
                        repairs.append(repair_name)
                    return parsed
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
        data = try_json(
            without_trailing_commas,
            "removed trailing commas",
        )
        if data is not None:
            return data, repairs

        with_line_commas = self._repair_json_missing_line_commas(
            without_trailing_commas
        )
        data = try_json(
            with_line_commas,
            "restored missing entry commas",
        )
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

    @staticmethod
    def _config_has_recognized_structure(data):
        """Return whether recovered data is empty or contains a known setting."""
        if not isinstance(data, dict):
            return False
        if not data:
            return True
        known = set(_default_config())
        known.update(
            {
                "preserve_selection_colours",
                "colour_coordinate_labels",
            }
        )
        return any(key in known for key in data)

    @staticmethod
    def _read_config_file(path):
        """Read one bounded JSON object and return data with an error string."""
        try:
            path = Path(path)
            if not path.is_file():
                return None, "The selected path is not a file."
            if path.stat().st_size > MAX_CONFIG_FILE_BYTES:
                return None, "The config exceeds the 1 MiB safety limit."
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                return None, "The config root must be a JSON object."
            if not PluginClassName._config_has_recognized_structure(data):
                return None, "The file does not contain recognized Dark Mode UI settings."
            return data, ""
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _bounded_int(value, minimum, maximum, fallback):
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = int(fallback)
        return max(int(minimum), min(int(maximum), parsed))

    def _normalize_limit_fields(self) -> None:
        depth = self._bounded_int(
            self.max_depth.GetValue(),
            1,
            40,
            18,
        )
        controls = self._bounded_int(
            self.max_controls.GetValue(),
            100,
            5000,
            1500,
        )
        self.max_depth.ChangeValue(str(depth))
        self.max_controls.ChangeValue(str(controls))

    def _current_config(
        self,
        enabled_on_editor_load: Optional[bool] = None,
    ) -> Dict[str, object]:
        """Collect the current interface settings into normalized configuration data."""
        if enabled_on_editor_load is None:
            enabled_on_editor_load = bool(
                self.apply_on_editor_load.GetValue()
            )
        self._remember_window_size()
        data = dict(self._config_unknown_data)
        data.update({
            "format_version": CONFIG_FORMAT_VERSION,
            "enabled_on_editor_load": bool(enabled_on_editor_load),
            "scope_mode": (
                "all" if self.scope_choice.GetSelection() == 1 else "top"
            ),
            "skip_canvas": bool(self.skip_canvas.GetValue()),
            "try_flatnotebook": bool(self.try_flatnotebook.GetValue()),
            "button_hover_safe": bool(self.button_hover_safe.GetValue()),
            "preserve_selection_colors": bool(
                self.preserve_selection_colors.GetValue()
            ),
            "color_coordinate_labels": bool(
                self.color_coordinate_labels.GetValue()
            ),
            "watch_new_controls": bool(
                self.watch_new_controls.GetValue()
            ),
            "max_depth": self._bounded_int(
                self.max_depth.GetValue(),
                1,
                40,
                18,
            ),
            "max_controls": self._bounded_int(
                self.max_controls.GetValue(),
                100,
                5000,
                1500,
            ),
            "window_size": list(self._normal_window_size),
            "manage_window_size": list(self._manage_dialog_size),
            "console_visible": bool(self._console_visible),
        })
        return data

    def _configure_controller(self) -> None:
        _configure_controller(self.controller, self._current_config())

    def _save_current_config(
        self,
        enabled_on_editor_load: Optional[bool] = None,
        log_result: bool = False,
    ) -> bool:
        ok, detail = _save_config(
            self._current_config(
                enabled_on_editor_load=enabled_on_editor_load
            )
        )
        if log_result:
            self._log(
                ("Saved settings: " if ok else "Failed to save settings: ")
                + detail
            )
        return ok

    # ------------------------------------------------------------------
    # Tooltips and console presentation
    # ------------------------------------------------------------------

    def _tooltip_targets(self, control):
        targets = [control]
        try:
            targets.extend(control.GetChildren())
        except Exception:
            pass
        return targets

    def _set_control_tooltip(self, control, text) -> None:
        """Attach delayed custom help behavior to a control and its child windows."""
        if control is None or not text:
            return
        anchor_ref = weakref.ref(control)
        for target in self._tooltip_targets(control):
            try:
                target.Bind(
                    wx.EVT_ENTER_WINDOW,
                    lambda event, ref=anchor_ref, help_text=str(text):
                    self._on_control_help_enter(event, ref, help_text),
                )
                target.Bind(
                    wx.EVT_LEAVE_WINDOW,
                    lambda event, ref=anchor_ref:
                    self._on_control_help_leave(event, ref),
                )
                target.Bind(
                    wx.EVT_LEFT_DOWN,
                    self._hide_control_help_event,
                )
                target.Bind(
                    wx.EVT_SET_FOCUS,
                    self._hide_control_help_event,
                )
            except Exception:
                pass

    def _cancel_control_help(self) -> None:
        pending = self._control_help_call
        self._control_help_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _hide_control_help_event(self, event) -> None:
        self._hide_control_help()
        try:
            event.Skip()
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

    def _cancel_console_help(self) -> None:
        pending = self._console_help_call
        self._console_help_call = None
        if pending is not None:
            try:
                pending.Stop()
            except Exception:
                pass

    def _hide_console_help(self) -> None:
        self._cancel_console_help()
        if self._console_help_window is not None:
            try:
                self._console_help_window.dismiss()
            except Exception:
                pass

    def _hide_console_help_event(self, event) -> None:
        self._console_help_hovered = False
        self._hide_console_help()
        try:
            event.Skip()
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

    def _on_console_help_leave(self, event) -> None:
        try:
            event.Skip()
        except Exception:
            pass
        try:
            if self.console_card.GetScreenRect().Contains(
                wx.GetMousePosition()
            ):
                return
        except Exception:
            pass
        self._console_help_hovered = False
        self._hide_console_help()

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

    def _set_console_visibility(self, visible, save=True) -> None:
        """Show or hide the report console and update the saved layout state."""
        self._console_visible = bool(visible)
        self.console_card.Show(self._console_visible)
        self.console_toggle_button.SetLabel(
            "Hide Console" if self._console_visible else "Show Console"
        )
        try:
            self._plugin_window.Layout()
        except Exception:
            pass
        self._update_floating_min_size(resize_if_needed=True)
        try:
            self._plugin_window.Layout()
            self._plugin_window.Refresh(False)
        except Exception:
            pass
        if not self._console_visible:
            self._hide_console_help()
        if save:
            self._save_current_config()

    def _toggle_console(self, _event) -> None:
        self._set_console_visibility(not self._console_visible)

    def _set_tooltips(self) -> None:
        """Attach the complete set of interface help descriptions."""
        tooltips = (
            (
                self.open_window_button,
                "Show, restore, and focus the existing Dark Mode UI window.",
            ),
            (
                self.apply_on_editor_load,
                "Automatically applies dark mode when Amulet loads the editor "
                "/ plugin system. This is not true app-start theming in the "
                "installed PyInstaller build.",
            ),
            (
                self.watch_new_controls,
                "Uses event-based incremental passes for newly created or "
                "shown controls. It does not use a constant polling timer.",
            ),
            (
                self.skip_canvas,
                "Skips OpenGL / canvas-like controls to avoid disturbing the "
                "3D viewport.",
            ),
            (
                self.button_hover_safe,
                "Improves text readability when Windows forces a light native "
                "hover appearance on buttons.",
            ),
            (
                self.preserve_selection_colors,
                "Keeps Amulet selection fields and Move Point buttons green, "
                "purple, or gray instead of converting them to normal inputs.",
            ),
            (
                self.color_coordinate_labels,
                "Colors only x1 / y1 / z1 and x2 / y2 / z2 labels when enabled.",
            ),
            (
                self.try_flatnotebook,
                "Applies additional dark styling to notebook and tab controls.",
            ),
            (
                self.save_settings_button,
                "Validates and saves all Dark Mode UI settings.",
            ),
            (
                self.status_button,
                "Prints persistent-controller status and watcher information.",
            ),
            (
                self.scan_button,
                "Prints the current target control tree for diagnosing "
                "compatibility with Amulet UI changes.",
            ),
            (
                self.manage_plugin_files_button,
                "Opens local plugin and config management, including reset, "
                "repair, import, export, and deletion options.",
            ),
            (
                self.clear_button,
                "Clears the visible log and the pending saved-log contents.",
            ),
            (
                self.apply_dark_button,
                "Applies the configured dark theme to the selected target scope.",
            ),
            (
                self.restore_button,
                "Restores colors saved before the current controller applied "
                "dark mode and disables automatic editor-load application.",
            ),
            (
                self.save_report_button,
                "Saves the current Dark Mode UI log as a text file.",
            ),
        )
        for control, tooltip in tooltips:
            self._set_control_tooltip(control, tooltip)

    # ------------------------------------------------------------------
    # Logging and status
    # ------------------------------------------------------------------

    def _set_status(self, text) -> None:
        try:
            self.status.SetLabel(str(text))
            self.status.GetParent().Layout()
        except Exception:
            pass

    def _append_log_text(self, message: str) -> None:
        try:
            self.text.AppendText(message + "\n")
        except Exception:
            pass

    def _append_log_text_from_controller(self, message: str) -> None:
        self._report_lines.append(message)
        self._append_log_text(message)

    def _log(self, message: str = "") -> None:
        print(message)
        self._report_lines.append(message)
        try:
            wx.CallAfter(self._append_log_text, message)
        except Exception:
            self._append_log_text(message)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_limit_field_commit(self, event) -> None:
        try:
            event.Skip()
        except Exception:
            pass
        self._normalize_limit_fields()
        self._on_live_setting_changed(None)

    def _on_live_setting_changed(self, event) -> None:
        """Apply a changed live setting and persist the interface state."""
        if event is not None:
            try:
                event.Skip()
            except Exception:
                pass
        self._configure_controller()
        self._save_current_config(
            enabled_on_editor_load=bool(
                self.apply_on_editor_load.GetValue()
            )
        )
        try:
            if self.controller._theme_active:
                result = self.controller.apply(quiet=True)
                self._log(
                    "Updated dark mode settings: "
                    f"changed={result['changed']}, "
                    f"unchanged={result['unchanged']}, "
                    f"skipped={result['skipped']}, "
                    f"failed={result['failed']}, "
                    f"controls={result['controls']}"
                )
                self._set_status("Settings applied")
            else:
                self._set_status("Settings saved")
        except Exception as exc:
            self._log(f"Live setting update failed: {exc}")
            self._set_status("Setting update failed")

    def _on_apply_dark_theme(self, _event) -> None:
        """Apply the current theme settings to the active Amulet window."""
        self._normalize_limit_fields()
        self._configure_controller()
        self._set_status("Applying dark mode...")
        self._log("\n=== APPLY DARK MODE ===")
        result = self.controller.apply(quiet=False)
        self._save_current_config(
            enabled_on_editor_load=bool(
                self.apply_on_editor_load.GetValue()
            )
        )
        self._log(f"Controls considered: {result['controls']}")
        self._log(f"Controls matching theme: {result['themed']}")
        self._log(f"Colors changed: {result['changed']}")
        self._log(f"Already correct: {result['unchanged']}")
        self._log(f"Skipped: {result['skipped']}")
        self._log(f"Failed: {result['failed']}")
        self._log(
            "Notebook controls styled: "
            f"{result['flatnotebook_touched']}"
        )
        self._log(f"Truncated: {result['truncated']}")
        self._log("=== END APPLY DARK MODE ===")
        self._set_status(
            f"Dark mode applied, {result['changed']} changed"
        )

    def _on_restore_colors(self, _event) -> None:
        self._configure_controller()
        self._set_status("Restoring saved colors...")
        self._log("\n=== RESTORE SAVED COLORS ===")
        result = self.controller.restore()
        self.apply_on_editor_load.SetValue(False)
        self._save_current_config(enabled_on_editor_load=False)
        self._log(f"Restored saved colors: {result['restored']}")
        self._log(f"Restore failures: {result['failed']}")
        self._log(
            "Persistent controller disabled until dark mode is applied again."
        )
        self._log("=== END RESTORE SAVED COLORS ===")
        self._set_status(
            f"Restored {result['restored']} controls"
        )

    def _on_save_settings(self, _event) -> None:
        self._normalize_limit_fields()
        self._configure_controller()
        ok = self._save_current_config(
            enabled_on_editor_load=bool(
                self.apply_on_editor_load.GetValue()
            ),
            log_result=True,
        )
        self._set_status("Settings saved" if ok else "Settings save failed")

    def _on_controller_status(self, _event) -> None:
        self._configure_controller()
        self._log("")
        for line in self.controller.status_lines():
            self._log(line)
        self._set_status("Controller status added to log")

    def _on_scan_controls(self, _event) -> None:
        """Scan the current window tree and report theme coverage."""
        self._configure_controller()
        self._set_status("Scanning UI...")
        self._log("\n=== UI CONTROL SCAN ===")
        roots = self.controller.get_targets()
        controls, truncated = self.controller.walk_windows(
            roots,
            include_hidden=False,
        )
        self._log(
            f"Started: {datetime.now().isoformat(timespec='seconds')}"
        )
        self._log(f"Target roots: {len(roots)}")
        for root in roots:
            self._log(
                "  Root: "
                f"{self.controller._safe_class_name(root)} | "
                f"label={self.controller._safe_label(root)!r} | "
                f"size={self.controller._safe_size(root)}"
            )
        self._log(f"Controls scanned: {len(controls)}")
        self._log(f"Truncated: {truncated}\n")

        class_counts = collections.Counter(
            self.controller._safe_class_name(window)
            for _, window in controls
        )
        self._log("Class counts:")
        for class_name, count in class_counts.most_common():
            self._log(f"  {count:4d}  {class_name}")

        self._log("\nControl tree:")
        for depth, window in controls:
            indent = "  " * depth
            class_name = self.controller._safe_class_name(window)
            label = self.controller._safe_label(window)
            bg = self.controller._safe_color_text(
                self.controller._safe_get_bg(window)
            )
            fg = self.controller._safe_color_text(
                self.controller._safe_get_fg(window)
            )
            shown = self.controller._safe_is_shown(window)
            size = self.controller._safe_size(window)
            children = len(self.controller._safe_children(window))
            canvas_note = (
                " | canvas-like"
                if self.controller._looks_like_canvas(window)
                else ""
            )
            label_text = f" | label={label!r}" if label else ""
            self._log(
                f"{indent}{class_name}{label_text} | "
                f"bg={bg} | fg={fg} | shown={shown} | "
                f"size={size} | children={children}{canvas_note}"
            )
        self._log("=== END UI CONTROL SCAN ===")
        self._set_status(
            f"Scanned {len(controls)} controls"
        )

    def _on_clear_log(self, _event) -> None:
        self._report_lines = []
        try:
            self.text.SetValue("")
        except Exception:
            pass
        self._set_status("Log cleared")

    def _show_manage_plugin_files_dialog(self, actions):
        """Show the Manage Plugin Files action picker and return its selection."""
        dialog = DarkActionPickerDialog(
            self._plugin_window,
            actions,
            initial_size=self._manage_dialog_size,
            on_size_changed=self._remember_manage_dialog_size,
        )
        try:
            result = dialog.ShowModal()
            self._remember_manage_dialog_size(dialog)
            self._save_current_config()
            if result != wx.ID_OK:
                return None
            selection = dialog.GetSelection()
            return selection if selection != wx.NOT_FOUND else None
        finally:
            dialog.Destroy()

    def _open_directory(self, directory, label):
        """Open a local directory and report any platform error."""
        try:
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            wx.LaunchDefaultApplication(str(directory))
            self._log(f"Opened {label}: {_display_path(directory)}")
            self._set_status(f"{label.capitalize()} opened")
            return True
        except Exception as exc:
            self._show_message(
                f"Could not open the {label}.\n\nReason: {exc}",
                "Open Failed",
                wx.OK,
            )
            self._set_status(f"Could not open {label}")
            return False

    def _reset_saved_settings(self) -> None:
        """Rewrite the active config with current plugin defaults."""
        if self._show_message(
            "Reset all Dark Mode UI settings to their current defaults?\n\n"
            "The active settings file will be rewritten.",
            "Reset saved settings?",
            wx.YES_NO | wx.NO_DEFAULT,
        ) != wx.ID_YES:
            return

        defaults = _default_config()
        ok, detail = _save_config(defaults)
        if not ok:
            self._show_message(
                f"The settings could not be reset.\n\nReason: {detail}",
                "Reset Failed",
                wx.OK,
            )
            self._set_status("Settings reset failed")
            return

        self._apply_config_data(defaults, resize_window=True)
        self._log(f"Reset settings: {detail}")
        self._set_status("Settings reset to defaults")
        self._show_message(
            "Dark Mode UI settings were reset successfully.",
            "Dark Mode UI",
            wx.OK,
        )

    def _repair_existing_config(self) -> None:
        """Conservatively repair and normalize the active config file."""
        path = _config_path()
        if not path.is_file():
            self._show_message(
                "No active Dark Mode UI settings file was found.",
                "Dark Mode UI",
                wx.OK,
            )
            return

        try:
            if path.stat().st_size > MAX_CONFIG_FILE_BYTES:
                raise ValueError("The config exceeds the 1 MiB safety limit.")
            content = path.read_text(
                encoding="utf-8-sig",
                errors="strict",
            )
        except Exception as exc:
            self._show_message(
                f"The settings file could not be read.\n\nReason: {exc}",
                "Repair Failed",
                wx.OK,
            )
            return

        recovered, repairs = self._attempt_parse_repaired_config(content)
        if (
            recovered is None
            or not self._config_has_recognized_structure(recovered)
        ):
            self._show_message(
                "The settings file could not be repaired safely.\n\n"
                "No changes were made. Correct the JSON manually or import a "
                "known-good Dark Mode UI config.",
                "Repair Failed",
                wx.OK,
            )
            return

        lines = [
            "Repair and normalize the active Dark Mode UI settings file?",
            "",
            "Recognized settings will be validated before they are applied.",
            "Unknown entries will be preserved.",
            "Missing current settings will be added with their defaults.",
            "The original file changes only after the repaired file is complete.",
        ]
        if repairs:
            lines.extend(
                ["", "Detected repairs:", *[f"• {item}" for item in repairs]]
            )
        else:
            lines.extend(
                [
                    "",
                    "The JSON is readable. It will be normalized and merged "
                    "with the current setting structure.",
                ]
            )

        if self._show_message(
            "\n".join(lines),
            "Repair settings config?",
            wx.YES_NO | wx.NO_DEFAULT,
        ) != wx.ID_YES:
            return

        normalized = _normalize_config_data(recovered)
        try:
            _write_text_atomically(
                path,
                json.dumps(
                    normalized,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                ) + "\n",
            )
        except Exception as exc:
            self._show_message(
                f"The repaired settings file could not be written.\n\n"
                f"Reason: {exc}",
                "Repair Failed",
                wx.OK,
            )
            return

        self._apply_config_data(normalized, resize_window=True)
        self._log(f"Repaired settings config: {_display_path(path)}")
        self._set_status("Settings config repaired")
        self._show_message(
            "The settings file was repaired and reloaded successfully.",
            "Dark Mode UI",
            wx.OK,
        )

    def _import_settings_config(self) -> None:
        """Import a valid config into the active stable config location."""
        dialog = wx.FileDialog(
            self._plugin_window,
            "Import Dark Mode UI settings",
            wildcard=(
                "Dark Mode UI config (*.config)|*.config|"
                "All files (*.*)|*.*"
            ),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            source_path = Path(dialog.GetPath())
        finally:
            dialog.Destroy()

        data, error = self._read_config_file(source_path)
        if data is None:
            self._show_message(
                f"The selected settings file could not be imported.\n\n"
                f"Reason: {error or 'Invalid file'}",
                "Import Failed",
                wx.OK,
            )
            return

        normalized = _normalize_config_data(data)
        try:
            _write_text_atomically(
                _config_path(),
                json.dumps(
                    normalized,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                ) + "\n",
            )
        except Exception as exc:
            self._show_message(
                "The selected settings were valid, but the active settings "
                f"file could not be written.\n\nReason: {exc}",
                "Import Failed",
                wx.OK,
            )
            return

        self._apply_config_data(normalized, resize_window=True)
        self._log(f"Imported settings: {_display_path(source_path)}")
        self._set_status("Settings imported")
        self._show_message(
            "Settings imported successfully.",
            "Dark Mode UI",
            wx.OK,
        )

    def _export_settings_config(self) -> None:
        """Export a backup without changing the active config location."""
        active_path = _config_path()
        existing = None
        if active_path.is_file():
            existing, error = self._read_config_file(active_path)
            if existing is None:
                self._show_message(
                    "The active settings file is malformed or unreadable.\n\n"
                    "Repair it before exporting so unknown saved entries are not "
                    f"silently lost.\n\nReason: {error}",
                    "Export Failed",
                    wx.OK,
                )
                return

        dialog = wx.FileDialog(
            self._plugin_window,
            "Export Dark Mode UI settings",
            defaultFile=CONFIG_FILE_NAME,
            wildcard=(
                "Dark Mode UI config (*.config)|*.config|"
                "All files (*.*)|*.*"
            ),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            destination = Path(dialog.GetPath())
        finally:
            dialog.Destroy()

        export_data = dict(existing) if isinstance(existing, dict) else {}
        export_data.update(self._current_config())
        export_data = _normalize_config_data(export_data)
        try:
            _write_text_atomically(
                destination,
                json.dumps(
                    export_data,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                ) + "\n",
            )
        except Exception as exc:
            self._show_message(
                f"Could not export the settings file.\n\nReason: {exc}",
                "Export Failed",
                wx.OK,
            )
            return

        self._log(f"Exported settings: {_display_path(destination)}")
        self._set_status("Settings exported")
        self._show_message(
            "Settings exported successfully.",
            "Dark Mode UI",
            wx.OK,
        )

    def _delete_settings_config(self) -> None:
        """Delete the active config and restore visible defaults."""
        if self._show_message(
            "Delete Dark Mode UI.config?\n\n"
            "The visible settings will return to defaults. The plugin file "
            "and Amulet installation will not be changed.",
            "Delete Dark Mode UI settings?",
            wx.YES_NO | wx.NO_DEFAULT,
        ) != wx.ID_YES:
            return

        path = _config_path()
        try:
            if path.is_file():
                path.unlink()
        except Exception as exc:
            self._show_message(
                f"The settings file could not be deleted.\n\nReason: {exc}",
                "Delete Failed",
                wx.OK,
            )
            return

        defaults = _default_config()
        self._apply_config_data(defaults, resize_window=True)
        self._log(f"Deleted settings config: {_display_path(path)}")
        self._set_status("Config deleted; defaults restored")
        self._show_message(
            "Dark Mode UI.config was deleted and visible settings were "
            "restored to defaults.",
            "Dark Mode UI",
            wx.OK,
        )

    def _manage_plugin_files(self, _event) -> None:
        """Provide local management for the plugin and its config file."""
        actions = [
            (
                "Open plugin folder",
                "Open the folder containing the loaded Dark Mode UI Python plugin.",
            ),
            (
                "Open settings folder",
                "Open the local Amulet edit-plugins settings folder containing "
                "Dark Mode UI.config and other plugin config files.",
            ),
            (
                "Reset saved settings to defaults",
                "Restore every Dark Mode UI option to the current plugin defaults "
                "and rewrite the active config file.",
            ),
            (
                "Attempt to repair existing settings config",
                "Try a conservative data-only repair when simple JSON damage "
                "prevents Dark Mode UI.config from loading. Unknown recovered "
                "entries are preserved where possible.",
            ),
            (
                "Import settings...",
                "Copy a selected Dark Mode UI config backup into the stable active "
                "config location and load its recognized values.",
            ),
            (
                "Export settings...",
                "Save a backup copy of the current Dark Mode UI settings without "
                "moving or changing the active config path.",
            ),
            (
                "Delete settings config",
                "Delete only Dark Mode UI.config and restore the visible controls "
                "to plugin defaults. The plugin file is not changed.",
            ),
        ]

        action = self._show_manage_plugin_files_dialog(actions)
        if action is None:
            return
        if action == 0:
            self._open_directory(Path(__file__).resolve().parent, "plugin folder")
        elif action == 1:
            self._open_directory(_config_path().parent, "settings folder")
        elif action == 2:
            self._reset_saved_settings()
        elif action == 3:
            self._repair_existing_config()
        elif action == 4:
            self._import_settings_config()
        elif action == 5:
            self._export_settings_config()
        else:
            self._delete_settings_config()

    def _on_save_report(self, _event) -> None:
        """Save the current report text through a user-selected path."""
        report = "\n".join(self._report_lines).strip()
        if not report:
            self._show_message(
                "No log is available yet.",
                "No Log",
                wx.OK,
            )
            return

        default_name = (
            "Dark Mode UI; "
            + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".txt"
        )
        with wx.FileDialog(
            self._plugin_window,
            message="Save Dark Mode UI log",
            defaultFile=default_name,
            wildcard=(
                "Text files (*.txt)|*.txt|All files (*.*)|*.*"
            ),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            try:
                Path(dialog.GetPath()).write_text(
                    report + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                self._log(f"Saved log: {dialog.GetPath()}")
                self._set_status("Log saved")
            except Exception as exc:
                self._show_message(
                    f"Failed to save log:\n{exc}",
                    "Save Failed",
                    wx.OK,
                )
                self._set_status("Log save failed")

    def _show_message(self, message, caption, style=wx.OK):
        dialog = DarkMessageDialog(
            self._plugin_window,
            message,
            caption,
            style,
        )
        try:
            return dialog.ShowModal()
        finally:
            try:
                dialog.Destroy()
            except Exception:
                pass

    def _on_host_destroy(self, event) -> None:
        """Close the floating window and detach host-owned state safely."""
        try:
            if event.GetEventObject() is not self:
                event.Skip()
                return
        except Exception:
            pass

        self._destroying = True
        self._hide_control_help()
        self._hide_console_help()
        self._remember_window_size()
        try:
            self._save_current_config()
        except Exception:
            pass

        for help_name in (
            "_control_help_window",
            "_console_help_window",
        ):
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


# Amulet discovers this module-level operation registration directly.
export = dict(name="Dark Mode UI", operation=PluginClassName)

# Editor-load theming is scheduled independently of opening the operation panel.
_schedule_editor_load_apply()
