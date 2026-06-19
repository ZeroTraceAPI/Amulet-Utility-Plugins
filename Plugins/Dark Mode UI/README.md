# Dark Mode UI

Dark Mode UI is an Amulet Map Editor operation plugin that applies a reversible dark theme to Amulet's wxPython interface. It changes interface colors only and does not edit the opened world.

## Main Features

* Applies a dark palette to supported Amulet windows and controls.
* Keeps a persistent controller attached to the main Amulet window so the theme can remain active when switching operations.
* Can theme newly created or newly shown controls and secondary windows.
* Supports either the current Amulet window or all top-level wxPython windows.
* Can preserve Amulet selection value colors and optionally color coordinate labels.
* Skips OpenGL and canvas-like controls by default to avoid disturbing the 3D viewport.
* Includes button-hover and notebook / tab compatibility options.
* Preserves the intended black background and green text of supported plugin consoles.
* Includes status, UI scanning, logging, and config-file tools for troubleshooting.

## Installation

1. Download one Dark Mode UI `.py` file from this folder or the repository's [Releases](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/releases) page.
2. Move the file into:

```text
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\plugins\operations
```

3. Restart Amulet Editor.
4. Open a world, open the Operations tab, and refresh the plugin list if needed.

## Commented and Uncommented Files

Some releases provide two versions of the plugin source:

* **Uncommented:** Recommended for normal use in Amulet. It contains the same plugin logic in a smaller, cleaner file with most explanatory comments and docstrings removed.
* **Commented:** Intended for people who want to read, study, review, modify, or navigate the code more easily. It includes explanatory comments and docstrings, so the file is larger.

Both versions work in Amulet and are intended to behave the same. Python ignores comments after reading the source, so the practical loading-speed difference is normally very small. The uncommented version mainly provides a smaller and cleaner normal-use file, while the commented version provides better code documentation.

Install only one version at a time. Installing both can create duplicate operation entries because each file registers the same plugin.


## Basic Use

1. Open **Dark Mode UI** from the Operations tab.
2. Choose the target scope and appearance options.
3. Select **Apply Dark Mode**.
4. Use **Save Settings** to keep the current configuration.
5. Select **Restore Saved Colors** when the dark theme should be removed.

The persistent controller can continue applying the theme after leaving the Dark Mode UI operation panel, depending on the saved settings.

## Settings

### Target Scope

* **This Amulet window** themes the main Amulet window and related dialogs owned by it.
* **All top-level wx windows** also targets separate wxPython windows such as World Select.

The broader option can improve consistency across secondary windows but affects more interface roots.

### Apply Dark Mode When Editor Loads

Applies the saved theme after Amulet has loaded enough of the editor and plugin system for the controls to exist.

This is not true earliest-startup theming. Some interface elements may appear in their normal colors briefly before the editor finishes loading and the theme is applied.

### Watch Newly Shown Panels

Themes newly created or newly shown controls through bounded event-based passes. This is intended for operation panels and dialogs that are created after the first theme application.

The watcher does not use a constant repaint timer and does not repeatedly rescan every control during ordinary focus or resize activity.

### Skip OpenGL / Canvas-Like Controls

Enabled by default. This avoids recoloring controls that appear to be part of the 3D viewport or another canvas surface.

### Button Hover Readability Fix

Improves text readability when Windows forces a lighter native hover state on buttons.

### Preserve / Darken Selection Value Colors

Keeps Amulet's selection coordinate fields and Move Point buttons visually distinct instead of converting them into ordinary dark inputs.

### Color Coordinate Labels

Optionally colors the `x1 / y1 / z1` and `x2 / y2 / z2` labels. This can be useful when selection value colors are not being preserved.

### Try Notebook / Tab Colors

Attempts additional dark styling for supported notebook and tab controls. Some native or custom tab implementations may still retain operating-system colors.

### Max Depth and Max Controls

These limits bound how much of the interface tree is scanned during a theme pass. Increase them only when controls are being missed in unusually deep or large interfaces.

## Controls and Diagnostics

* **Apply Dark Mode** applies the current settings and activates the persistent controller.
* **Restore Saved Colors** restores colors captured before theming and disables the persistent controller until dark mode is applied again.
* **Save Settings** writes the current configuration.
* **Status** reports controller state, watched windows, and incremental theme activity.
* **Scan UI** records the current target control tree for troubleshooting future Amulet or wxPython changes.
* **Save Log** saves the current log.
* **Open Config Folder** opens the saved-settings location.
* **Delete Config File** removes saved Dark Mode UI settings.
* **Clear Log** clears the visible diagnostic log.

UI scanning and status tools are diagnostic only. They do not modify world data.

## Settings Location

Settings are stored at:

```text
%LOCALAPPDATA%\AmuletTeam\AmuletMapEditor\Config\plugins\edit_plugins\Dark Mode UI.config
```

Deleting the config file resets saved behavior the next time the plugin loads. The plugin can also open the folder or delete the file through its own controls.

## Supported Plugin Consoles

Dark Mode UI recognizes the shared console naming used by Amulet Utility Plugins and preserves their intended black background and green text instead of treating them as normal text inputs.

The legacy console name is also recognized for compatibility.

## Things to Consider

* Dark Mode UI is currently tested and supported on Windows.
* Some native Windows or wxPython controls may remain partly light because their appearance is controlled by the operating system or the native widget implementation.
* Amulet or wxPython interface changes can require future theme adjustments.
* Newly created interfaces may need a short bounded follow-up pass before every control is themed.
* Restoring colors depends on the colors captured before or during the active controller session.
* Applying the theme to all top-level wx windows can affect secondary wxPython windows outside the main editor surface.
* The plugin changes UI colors only and does not edit the world.

## Screenshots

Screenshots and preview media are available in [`Media/Dark-Mode-UI`](Media/Dark-Mode-UI).

## Support and Contact

Report problems through [GitHub Issues](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins/issues) and include the Dark Mode UI version, Amulet version, Windows version, target scope, affected control or window, and a saved Scan UI log when relevant.

If you do not want to create a GitHub account, contact the maintainer at `ZeroTraceAPI@proton.me`. Email support is not guaranteed, but reasonable project-related messages are welcome.

The official source is the [Amulet Utility Plugins GitHub repository](https://github.com/ZeroTraceAPI/Amulet-Utility-Plugins).
