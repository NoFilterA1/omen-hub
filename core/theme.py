"""
DE-agnostic accent color detection.
Tries each adapter in order, returns first result or None.
"""

import re
import subprocess
from pathlib import Path


def get_accent_color() -> str | None:
    """
    Returns hex color string (no #) from the current desktop theme, or None.
    """
    return (
        _from_noctalia()
        or _from_kde_globals()
        or _from_gsettings()
    )


def _from_noctalia() -> str | None:
    """Noctalia (QuickShell) — reads primary accent from generated color scheme."""
    path = Path.home() / ".config/noctalia/noctalia.colors"
    if not path.exists():
        return None
    try:
        text = path.read_text()
        # KDE color scheme format: "ForegroundActive=R,G,B" or similar accent key
        match = re.search(r"^DecorationFocus=(\d+),(\d+),(\d+)", text, re.MULTILINE)
        if not match:
            # Try accent background
            match = re.search(r"^BackgroundAlternate=(\d+),(\d+),(\d+)", text, re.MULTILINE)
        if match:
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{r:02x}{g:02x}{b:02x}"
    except OSError:
        pass
    return None


def _from_kde_globals() -> str | None:
    """KDE Plasma — reads accent from kdeglobals."""
    path = Path.home() / ".config/kdeglobals"
    if not path.exists():
        return None
    try:
        text = path.read_text()
        match = re.search(r"^AccentColor=(\d+),(\d+),(\d+)", text, re.MULTILINE)
        if match:
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{r:02x}{g:02x}{b:02x}"
    except OSError:
        pass
    return None


def _from_gsettings() -> str | None:
    """GNOME / Cinnamon — reads accent from gsettings."""
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "accent-color"],
            capture_output=True, text=True, timeout=2
        )
        # Returns something like "'blue'" or a hex string on some distros
        val = result.stdout.strip().strip("'\"")
        # Map named GNOME colors to hex
        gnome_colors = {
            "blue": "3584e4", "teal": "2190a4", "green": "3a944a",
            "yellow": "c88800", "orange": "ed5b00", "red": "e62d42",
            "pink": "d56199", "purple": "9141ac", "slate": "6f8396",
        }
        if val in gnome_colors:
            return gnome_colors[val]
        # Some distros return hex directly
        if re.fullmatch(r"[0-9a-fA-F]{6}", val):
            return val.lower()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None
