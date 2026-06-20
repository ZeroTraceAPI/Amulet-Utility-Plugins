r"""Dark Mode UI for Amulet Map Editor.

Applies a reversible dark theme to Amulet's wxPython UI.
The persistent controller is attached to the top-level Amulet window so the
appearance can survive switching away from this operation.

Settings are saved to:
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\Config\plugins\edit_plugins\Dark Mode UI.config

This plugin does not edit the world.
"""

import collections
import json
import os
import weakref
from time import monotonic
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import wx
from amulet_map_editor.programs.edit.api.operations import DefaultOperationUI

try:
    import wx.lib.agw.flatnotebook as flatnotebook
except Exception:
    flatnotebook = None


CONFIG_FORMAT_VERSION = 1
# Settings are stored in Amulet's normal per-user plugin config folder.
CONFIG_FILE_NAME = "Dark Mode UI.config"
CONTROLLER_ATTR_NAME = "_amulet_dark_mode_ui_controller"
EDITOR_LOAD_ATTEMPT_COUNT = 0
EDITOR_LOAD_MAX_ATTEMPTS = 40
EDITOR_LOAD_DELAY_MS = 250
# Newly created or shown controls are collected briefly so one UI action causes
# one small incremental theme pass instead of several full-window passes.
EVENT_RETHEME_DELAY_MS = 120
# Amulet can replace an operation panel in stages. The first show / create event
# may occur before its labels, buttons and choices have all been attached. A
# bounded follow-up pass themes the affected top-level window after the UI has
# settled without returning to continuous whole-application repainting.
EVENT_SETTLE_DELAY_MS = 320
# Child-focus is watched only on target top-level windows as a compatibility
# fallback for operation hosts that do not propagate create / show events.
ROOT_ACTIVITY_COOLDOWN_MS = 250
# Secondary dialogs may finish native sizing after their controls have already
# received dark colors. A root-only size watcher and one background-erasing
# repaint restore the complete dialog client area without returning to the old
# per-control size watcher or whole-application synchronous repaint behavior.
SECONDARY_DIALOG_SIZE_COOLDOWN_MS = 120

# Plugin consoles can opt into the black background and green text palette by
# assigning a shared semantic name. The legacy name remains recognized so
# previously released plugin consoles keep working without modification.
PLUGIN_CONSOLE_NAME_PREFIX = "AmuletPluginConsole"
LEGACY_CONSOLE_NAME = "DarkModeUIConsole"


def _config_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "AmuletTeam" / "AmuletMapEditor" / "Config" / "plugins" / "edit_plugins" / CONFIG_FILE_NAME


def _display_path(path: Path) -> str:
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
    }


def _load_config() -> Dict[str, object]:
    config = _default_config()
    path = _config_path()
    try:
        if path.exists() and path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
                if "preserve_selection_colours" in loaded:
                    config["preserve_selection_colors"] = bool(loaded.get("preserve_selection_colours", True))
                if "colour_coordinate_labels" in loaded:
                    config["color_coordinate_labels"] = bool(loaded.get("colour_coordinate_labels", False))
                config.pop("preserve_selection_colours", None)
                config.pop("colour_coordinate_labels", None)
                if "enabled_on_editor_load" not in loaded and "enabled_on_startup" in loaded:
                    config["enabled_on_editor_load"] = bool(loaded.get("enabled_on_startup", False))
    except Exception:
        pass
    return config


def _save_config(config: Dict[str, object]) -> Tuple[bool, str]:
    path = _config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _default_config()
        data.update(config)
        data["format_version"] = CONFIG_FORMAT_VERSION
        data["enabled_on_startup"] = False
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return True, _display_path(path)
    except Exception as exc:
        return False, str(exc)


def _open_config_folder() -> Tuple[bool, str]:
    """Open the folder that contains the Dark Mode UI config file."""
    folder = _config_path().parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))
        return True, _display_path(folder)
    except Exception as exc:
        return False, str(exc)


def _delete_config_file() -> Tuple[bool, str]:
    """Delete the Dark Mode UI config file if it exists."""
    path = _config_path()
    try:
        if not path.exists():
            return True, f"Config file was not found: {_display_path(path)}"
        if not path.is_file():
            return False, f"Config path is not a file: {_display_path(path)}"
        path.unlink()
        return True, f"Deleted config file: {_display_path(path)}"
    except Exception as exc:
        return False, str(exc)


def _find_top_window() -> Optional[wx.Window]:
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
    """Make handlers from an older reloaded controller instance inert.

    wx event bindings keep bound-method owners alive. When a plugin file is
    reloaded without restarting Amulet, an older controller may therefore keep
    receiving events even after the top-level attribute is replaced.
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
    try:
        wx.CallLater(EDITOR_LOAD_DELAY_MS, _try_apply_on_editor_load)
    except Exception:
        try:
            wx.CallAfter(_try_apply_on_editor_load)
        except Exception:
            pass


class DarkModeController:
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
        try:
            self._log_callbacks.append(weakref.WeakMethod(logger))
        except TypeError:
            try:
                self._log_callbacks.append(weakref.ref(logger))
            except Exception:
                pass

    def log(self, message: str = "") -> None:
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
        try:
            return window.__class__.__module__ + "." + window.__class__.__name__
        except Exception:
            return type(window).__name__

    def _safe_label(self, window: wx.Window) -> str:
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
        try:
            if not color or not color.IsOk():
                return "invalid"
            return "#{:02X}{:02X}{:02X}".format(color.Red(), color.Green(), color.Blue())
        except Exception:
            return "unknown"

    def _safe_get_bg(self, window: wx.Window):
        try:
            return window.GetBackgroundColour()
        except Exception:
            return None

    def _safe_get_fg(self, window: wx.Window):
        try:
            return window.GetForegroundColour()
        except Exception:
            return None

    def _safe_is_shown(self, window: wx.Window) -> bool:
        try:
            return bool(window.IsShown())
        except Exception:
            return True

    def _safe_is_enabled(self, window: wx.Window) -> bool:
        try:
            return bool(window.IsEnabled())
        except Exception:
            return True

    def _safe_children(self, window: wx.Window) -> List[wx.Window]:
        try:
            return list(window.GetChildren())
        except Exception:
            return []

    def _safe_size(self, window: wx.Window) -> str:
        try:
            size = window.GetSize()
            return f"{size.width}x{size.height}"
        except Exception:
            return "unknown"

    def _color_close(self, color, target: wx.Colour, tolerance: int = 10) -> bool:
        try:
            return bool(color and color.IsOk() and abs(color.Red() - target.Red()) <= tolerance and abs(color.Green() - target.Green()) <= tolerance and abs(color.Blue() - target.Blue()) <= tolerance)
        except Exception:
            return False

    def _looks_like_canvas(self, window: wx.Window) -> bool:
        try:
            words = f"{type(window).__module__}.{self._safe_class_name(window)}".lower()
        except Exception:
            words = type(window).__name__.lower()
        return any(token in words for token in ("glcanvas", "opengl", "canvas", "renderer", "viewport"))

    def _is_button_like(self, window: wx.Window) -> bool:
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
                if window is not None and not self._is_transient_top_level(window)
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
        result: List[Tuple[int, wx.Window]] = []
        truncated = False
        seen = set()
        max_depth = self.max_depth if max_depth is None else int(max_depth)
        max_controls = self.max_controls if max_controls is None else int(max_controls)

        def walk(window: wx.Window, depth: int) -> None:
            nonlocal truncated
            if window is None or truncated:
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
        """Force one complete native repaint of a secondary dialog client area.

        The original release used ``Refresh`` and ``Update`` on every control.
        That reliably repainted blank dialog space, but later caused visible
        flicker when frequent focus and size events reapplied the entire theme.
        This bounded form repeats the useful behavior only for the dialog root.
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
            # One synchronous update per secondary dialog is bounded and avoids
            # the old per-control repaint loop that produced flicker.
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
        try:
            if isinstance(window, wx.StaticText):
                return True
        except Exception:
            pass
        return "statictext" in self._safe_class_name(window).lower()

    def _is_editable_value_like(self, window: wx.Window) -> bool:
        try:
            if isinstance(window, (wx.TextCtrl, wx.SpinCtrl, wx.SpinCtrlDouble, wx.SpinButton)):
                return True
        except Exception:
            pass
        class_name = self._safe_class_name(window).lower()
        return any(token in class_name for token in ("textctrl", "spinctrl", "spinbutton", "number", "input"))

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
            is_value = self._is_editable_value_like(window)

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

        # A top-level root becomes known only after it was actually visible and
        # included in this pass. A newly constructed dialog may be discoverable
        # before wx reports it as shown. Registering it earlier caused the frame
        # background to be skipped permanently while its visible children were
        # still themed by narrower events.
        for _depth, window in controls:
            try:
                if isinstance(window, wx.TopLevelWindow):
                    self._known_target_roots.add(window)
            except Exception:
                pass

        # Main-window roots retain changed-only deferred refreshes. Secondary
        # dialogs always receive one bounded background-erasing repaint because
        # wx can expose native light client space after the color properties were
        # already set, especially while a dialog completes its initial sizing.
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
        """Watch new / shown controls plus bounded top-level fallbacks.

        Create and show events remain the preferred incremental path. Some
        Amulet operation hosts replace child controls without propagating those
        events to already watched ancestors. Top-level child-focus and activation
        events therefore queue one changed-only settle pass. Secondary top-level
        dialogs also receive a root-only size watcher so newly exposed client
        space is repainted without restoring the old per-control focus / size
        watchers that caused flicker.
        """
        if not self._theme_active or not self.watch_new_controls:
            return

        create_event = getattr(wx, "EVT_WINDOW_CREATE", None)
        target_root_ids = {id(root) for root in self.get_targets() if root is not None}

        for _depth, window in controls:
            if window is None or (
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

            # Focus events are intentionally bound only once on stable target
            # roots. This catches operation-panel replacements without reviving
            # the old per-control focus watcher that caused flicker.
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
        if root is None:
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
            "Class counts:",
        ]
        for class_name, count in class_counts.most_common(20):
            lines.append(f"  {count:4d}  {class_name}")
        lines.append("=== END DARK MODE UI STATUS ===")
        return lines


class PluginClassName(wx.Panel, DefaultOperationUI):
    def __init__(self, parent: wx.Window, canvas, world, options_path: str):
        wx.Panel.__init__(self, parent)
        DefaultOperationUI.__init__(self, parent, canvas, world, options_path)
        self._report_lines: List[str] = []
        self._loaded_config = _load_config()
        self._sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(self, label="Dark Mode UI")
        try:
            font = title.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            title.SetFont(font)
        except Exception:
            pass
        self._sizer.Add(title, 0, wx.ALL | wx.EXPAND, 6)

        description = wx.StaticText(self, label="Applies a reversible dark theme to Amulet's UI. The persistent controller keeps the theme active when switching operations.")
        description.Wrap(380)
        self._sizer.Add(description, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 6)

        options_box = wx.StaticBox(self, label="Dark mode settings")
        options_sizer = wx.StaticBoxSizer(options_box, wx.VERTICAL)
        self.scope_choice = wx.Choice(self, choices=["This Amulet window", "All top-level wx windows"])
        self.scope_choice.SetSelection(1 if str(self._loaded_config.get("scope_mode", "top")) == "all" else 0)
        options_sizer.Add(wx.StaticText(self, label="Target scope"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        options_sizer.Add(self.scope_choice, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 6)

        self.apply_on_editor_load = wx.CheckBox(self, label="Apply dark mode when editor loads")
        self.apply_on_editor_load.SetValue(bool(self._loaded_config.get("enabled_on_editor_load", False)))
        options_sizer.Add(self.apply_on_editor_load, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.watch_new_controls = wx.CheckBox(self, label="Watch newly shown panels")
        self.watch_new_controls.SetValue(bool(self._loaded_config.get("watch_new_controls", True)))
        options_sizer.Add(self.watch_new_controls, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.skip_canvas = wx.CheckBox(self, label="Skip OpenGL / canvas-like controls")
        self.skip_canvas.SetValue(bool(self._loaded_config.get("skip_canvas", True)))
        options_sizer.Add(self.skip_canvas, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.button_hover_safe = wx.CheckBox(self, label="Button hover readability fix")
        self.button_hover_safe.SetValue(bool(self._loaded_config.get("button_hover_safe", True)))
        options_sizer.Add(self.button_hover_safe, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.preserve_selection_colors = wx.CheckBox(self, label="Preserve / darken selection value colors")
        self.preserve_selection_colors.SetValue(bool(self._loaded_config.get("preserve_selection_colors", True)))
        options_sizer.Add(self.preserve_selection_colors, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.color_coordinate_labels = wx.CheckBox(self, label="Color coordinate labels")
        self.color_coordinate_labels.SetValue(bool(self._loaded_config.get("color_coordinate_labels", False)))
        options_sizer.Add(self.color_coordinate_labels, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.try_flatnotebook = wx.CheckBox(self, label="Try notebook / tab colors")
        self.try_flatnotebook.SetValue(bool(self._loaded_config.get("try_flatnotebook", True)))
        options_sizer.Add(self.try_flatnotebook, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Max depth"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.max_depth = wx.SpinCtrl(self, min=1, max=40, initial=int(self._loaded_config.get("max_depth", 18)))
        row.Add(self.max_depth, 0, wx.RIGHT, 12)
        row.Add(wx.StaticText(self, label="Max controls"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.max_controls = wx.SpinCtrl(self, min=100, max=5000, initial=int(self._loaded_config.get("max_controls", 1500)))
        row.Add(self.max_controls, 0)
        options_sizer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 6)
        self._sizer.Add(options_sizer, 0, wx.ALL | wx.EXPAND, 6)

        button_grid = wx.GridSizer(0, 2, 6, 6)
        self.apply_dark_button = wx.Button(self, label="Apply Dark Mode")
        self.apply_dark_button.Bind(wx.EVT_BUTTON, self._on_apply_dark_theme)
        button_grid.Add(self.apply_dark_button, 0, wx.EXPAND)
        self.restore_button = wx.Button(self, label="Restore Saved Colors")
        self.restore_button.Bind(wx.EVT_BUTTON, self._on_restore_colors)
        button_grid.Add(self.restore_button, 0, wx.EXPAND)
        self.save_settings_button = wx.Button(self, label="Save Settings")
        self.save_settings_button.Bind(wx.EVT_BUTTON, self._on_save_settings)
        button_grid.Add(self.save_settings_button, 0, wx.EXPAND)
        self.status_button = wx.Button(self, label="Status")
        self.status_button.Bind(wx.EVT_BUTTON, self._on_controller_status)
        button_grid.Add(self.status_button, 0, wx.EXPAND)
        self.scan_button = wx.Button(self, label="Scan UI")
        self.scan_button.Bind(wx.EVT_BUTTON, self._on_scan_controls)
        button_grid.Add(self.scan_button, 0, wx.EXPAND)
        self.save_report_button = wx.Button(self, label="Save Log")
        self.save_report_button.Bind(wx.EVT_BUTTON, self._on_save_report)
        button_grid.Add(self.save_report_button, 0, wx.EXPAND)
        self.open_config_folder_button = wx.Button(self, label="Open Config Folder")
        self.open_config_folder_button.Bind(wx.EVT_BUTTON, self._on_open_config_folder)
        button_grid.Add(self.open_config_folder_button, 0, wx.EXPAND)
        self.delete_config_button = wx.Button(self, label="Delete Config File")
        self.delete_config_button.Bind(wx.EVT_BUTTON, self._on_delete_config_file)
        button_grid.Add(self.delete_config_button, 0, wx.EXPAND)
        self.clear_button = wx.Button(self, label="Clear Log")
        self.clear_button.Bind(wx.EVT_BUTTON, self._on_clear_log)
        button_grid.Add(self.clear_button, 0, wx.EXPAND)

        for checkbox in (
            self.apply_on_editor_load,
            self.watch_new_controls,
            self.skip_canvas,
            self.button_hover_safe,
            self.preserve_selection_colors,
            self.color_coordinate_labels,
            self.try_flatnotebook,
        ):
            try:
                checkbox.Bind(wx.EVT_CHECKBOX, self._on_live_setting_changed)
            except Exception:
                pass

        self._sizer.Add(button_grid, 0, wx.ALL | wx.EXPAND, 6)

        self.text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL, size=(-1, 520))
        # Shared semantic name lets the controller preserve the intended
        # console palette while distinguishing this console from other plugins.
        self.text.SetName(f"{PLUGIN_CONSOLE_NAME_PREFIX}:DarkModeUI")
        self.text.SetMinSize((360, 360))
        self.text.SetForegroundColour(wx.Colour(0, 255, 0))
        self.text.SetBackgroundColour(wx.Colour(0, 0, 0))
        self._sizer.Add(self.text, 1, wx.ALL | wx.EXPAND, 6)
        self.SetSizer(self._sizer)
        self.SetMinSize((440, 680))
        self.controller = self._get_controller()
        self.controller.add_logger(self._append_log_text_from_controller)
        self._set_tooltips()
        self._log("Ready. Dark Mode UI")

    # ------------------------------------------------------------
    # Controller / settings helpers
    # ------------------------------------------------------------

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

    def _current_config(self, enabled_on_editor_load: Optional[bool] = None) -> Dict[str, object]:
        if enabled_on_editor_load is None:
            enabled_on_editor_load = bool(self.apply_on_editor_load.GetValue())
        return {
            "format_version": CONFIG_FORMAT_VERSION,
            "enabled_on_editor_load": bool(enabled_on_editor_load),
            "scope_mode": "all" if self.scope_choice.GetSelection() == 1 else "top",
            "skip_canvas": bool(self.skip_canvas.GetValue()),
            "try_flatnotebook": bool(self.try_flatnotebook.GetValue()),
            "button_hover_safe": bool(self.button_hover_safe.GetValue()),
            "preserve_selection_colors": bool(self.preserve_selection_colors.GetValue()),
            "color_coordinate_labels": bool(self.color_coordinate_labels.GetValue()),
            "watch_new_controls": bool(self.watch_new_controls.GetValue()),
            "max_depth": int(self.max_depth.GetValue()),
            "max_controls": int(self.max_controls.GetValue()),
        }

    def _configure_controller(self) -> None:
        _configure_controller(self.controller, self._current_config())

    def _save_current_config(self, enabled_on_editor_load: Optional[bool] = None) -> None:
        ok, detail = _save_config(self._current_config(enabled_on_editor_load=enabled_on_editor_load))
        self._log(("Saved settings: " if ok else "Failed to save settings: ") + detail)

    # ------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------

    def _set_tooltip(self, window: wx.Window, text: str) -> None:
        try:
            window.SetToolTip(wx.ToolTip(text))
        except Exception:
            try:
                window.SetToolTip(text)
            except Exception:
                pass

    def _set_tooltips(self) -> None:
        self._set_tooltip(self.scope_choice, "Targets this Amulet window, or all top-level wx windows such as World Select.")
        self._set_tooltip(self.apply_on_editor_load, "Automatically applies dark mode when Amulet loads the editor / plugin system. This is not true app-start theming in the installed PyInstaller build.")
        self._set_tooltip(
            self.watch_new_controls,
            "Event-based watcher that themes only newly created or shown controls. "
            "It does not monitor ordinary focus or resize events and uses no constant timer.",
        )
        self._set_tooltip(self.skip_canvas, "Skips OpenGL / canvas-like controls to avoid disturbing the 3D viewport.")
        self._set_tooltip(self.button_hover_safe, "Improves readability when Windows forces a light hover state on native buttons.")
        self._set_tooltip(self.preserve_selection_colors, "Keeps the actual Amulet selection value fields and Move Point buttons green / purple / gray instead of making them normal dark inputs.")
        self._set_tooltip(self.color_coordinate_labels, "Optionally colors only the x1 / y1 / z1 and x2 / y2 / z2 labels. Useful if Preserve selection value colors is off.")
        self._set_tooltip(self.try_flatnotebook, "Attempts extra dark styling for notebook / tab controls.")
        self._set_tooltip(self.scan_button, "Prints the current target control tree for troubleshooting future Amulet updates.")
        self._set_tooltip(self.open_config_folder_button, "Opens the folder that contains the Dark Mode UI config file.")
        self._set_tooltip(self.delete_config_button, "Deletes the Dark Mode UI config file. Useful when uninstalling the plugin or resetting saved settings.")

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

    # ------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------

    def _on_clear_log(self, _event) -> None:
        self._report_lines = []
        try:
            self.text.SetValue("")
        except Exception:
            pass

    def _on_open_config_folder(self, _event) -> None:
        ok, detail = _open_config_folder()
        if ok:
            self._log(f"Opened config folder: {detail}")
        else:
            self._log(f"Failed to open config folder: {detail}")
            wx.MessageBox(f"Failed to open config folder:\n{detail}", "Open Failed", wx.OK | wx.ICON_ERROR)

    def _on_delete_config_file(self, _event) -> None:
        answer = wx.MessageBox(
            "Delete the Dark Mode UI config file?\n\n"
            "This resets saved Dark Mode UI settings. It does not delete the plugin file.",
            "Delete Config File",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        if answer != wx.YES:
            self._log("Delete config file cancelled.")
            return

        ok, detail = _delete_config_file()
        self._log(detail if ok else f"Failed to delete config file: {detail}")

        if ok:
            try:
                self._loaded_config = _load_config()
                self.apply_on_editor_load.SetValue(False)
                self.scope_choice.SetSelection(0)
                self.skip_canvas.SetValue(True)
                self.try_flatnotebook.SetValue(True)
                self.button_hover_safe.SetValue(True)
                self.preserve_selection_colors.SetValue(True)
                self.color_coordinate_labels.SetValue(False)
                self.watch_new_controls.SetValue(True)
                self.max_depth.SetValue(18)
                self.max_controls.SetValue(1500)
                self._configure_controller()
            except Exception as exc:
                self._log(f"Config was deleted, but UI reset failed: {exc}")
        else:
            wx.MessageBox(f"Failed to delete config file:\n{detail}", "Delete Failed", wx.OK | wx.ICON_ERROR)

    def _on_save_report(self, _event) -> None:
        report = "\n".join(self._report_lines).strip()
        if not report:
            wx.MessageBox("No log is available yet.", "No Log", wx.OK | wx.ICON_INFORMATION)
            return
        default_name = "Dark Mode UI; " + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"
        with wx.FileDialog(self, message="Save Dark Mode UI log", defaultFile=default_name, wildcard="Text files (*.txt)|*.txt|All files (*.*)|*.*", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            try:
                Path(dialog.GetPath()).write_text(report + "\n", encoding="utf-8", newline="\n")
                self._log(f"Saved log: {dialog.GetPath()}")
            except Exception as exc:
                wx.MessageBox(f"Failed to save log:\n{exc}", "Save Failed", wx.OK | wx.ICON_ERROR)

    def _on_live_setting_changed(self, event) -> None:
        try:
            event.Skip()
        except Exception:
            pass
        self._configure_controller()
        self._save_current_config(enabled_on_editor_load=bool(self.apply_on_editor_load.GetValue()))
        try:
            if self.controller._theme_active:
                result = self.controller.apply(quiet=True)
                self._log(
                    "Updated dark mode settings: "
                    f"changed={result['changed']}, "
                    f"unchanged={result['unchanged']}, "
                    f"skipped={result['skipped']}, "
                    f"failed={result['failed']}, controls={result['controls']}"
                )
        except Exception as exc:
            self._log(f"Live setting update failed: {exc}")

    def _on_apply_dark_theme(self, _event) -> None:
        self._configure_controller()
        self._log("\n=== APPLY DARK MODE ===")
        result = self.controller.apply(quiet=False)
        self._save_current_config(enabled_on_editor_load=bool(self.apply_on_editor_load.GetValue()))
        self._log(f"Controls considered: {result['controls']}")
        self._log(f"Controls matching theme: {result['themed']}")
        self._log(f"Colors changed: {result['changed']}")
        self._log(f"Already correct: {result['unchanged']}")
        self._log(f"Skipped: {result['skipped']}")
        self._log(f"Failed: {result['failed']}")
        self._log(f"Notebook extra styling attempts: {result['flatnotebook_touched']}")
        self._log(f"Truncated: {result['truncated']}")
        self._log("=== END APPLY DARK MODE ===")

    def _on_restore_colors(self, _event) -> None:
        self._configure_controller()
        self._log("\n=== RESTORE SAVED COLORS ===")
        result = self.controller.restore()
        try:
            self.apply_on_editor_load.SetValue(False)
        except Exception:
            pass
        self._save_current_config(enabled_on_editor_load=False)
        self._log(f"Restored saved colors: {result['restored']}")
        self._log(f"Restore failures: {result['failed']}")
        self._log("Persistent controller disabled until dark mode is applied again.")
        self._log("=== END RESTORE SAVED COLORS ===")

    def _on_save_settings(self, _event) -> None:
        self._save_current_config(enabled_on_editor_load=bool(self.apply_on_editor_load.GetValue()))

    def _on_controller_status(self, _event) -> None:
        self._configure_controller()
        self._log("")
        for line in self.controller.status_lines():
            self._log(line)

    def _on_scan_controls(self, _event) -> None:
        self._configure_controller()
        self._log("\n=== UI CONTROL SCAN ===")
        roots = self.controller.get_targets()
        controls, truncated = self.controller.walk_windows(roots, include_hidden=False)
        self._log(f"Started: {datetime.now().isoformat(timespec='seconds')}")
        self._log(f"Target roots: {len(roots)}")
        for root in roots:
            self._log(f"  Root: {self.controller._safe_class_name(root)} | label={self.controller._safe_label(root)!r} | size={self.controller._safe_size(root)}")
        self._log(f"Controls scanned: {len(controls)}")
        self._log(f"Truncated: {truncated}\n")
        class_counts = collections.Counter(self.controller._safe_class_name(window) for _, window in controls)
        self._log("Class counts:")
        for class_name, count in class_counts.most_common():
            self._log(f"  {count:4d}  {class_name}")
        self._log("\nControl tree:")
        for depth, window in controls:
            indent = "  " * depth
            class_name = self.controller._safe_class_name(window)
            label = self.controller._safe_label(window)
            bg = self.controller._safe_color_text(self.controller._safe_get_bg(window))
            fg = self.controller._safe_color_text(self.controller._safe_get_fg(window))
            shown = self.controller._safe_is_shown(window)
            size = self.controller._safe_size(window)
            children = len(self.controller._safe_children(window))
            canvas_note = " | canvas-like" if self.controller._looks_like_canvas(window) else ""
            label_text = f" | label={label!r}" if label else ""
            self._log(f"{indent}{class_name}{label_text} | bg={bg} | fg={fg} | shown={shown} | size={size} | children={children}{canvas_note}")
        self._log("=== END UI CONTROL SCAN ===")


export = dict(name="Dark Mode UI", operation=PluginClassName)

_schedule_editor_load_apply()
