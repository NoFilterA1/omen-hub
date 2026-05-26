"""
RGB keyboard backlight control via hp-wmi sysfs.
HP OMEN 17 has one physical zone: zone00.
"""

import time
from pathlib import Path

ZONE_PATH = Path("/sys/devices/platform/hp-wmi/rgb_zones/zone00")


def is_available() -> bool:
    return ZONE_PATH.exists()


def write_color(hex_color: str) -> None:
    """Write color to keyboard. hex_color: 'ff0000' (no #)."""
    ZONE_PATH.write_text(hex_color.lower())


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"{r:02x}{g:02x}{b:02x}"


def transition_to(target_hex: str, current_hex: str | None, steps: int = 20, duration_ms: int = 100) -> None:
    """Smooth color transition. Skips if current is unknown or same."""
    if not current_hex or current_hex.lower() == target_hex.lower():
        write_color(target_hex)
        return

    r0, g0, b0 = hex_to_rgb(current_hex)
    r1, g1, b1 = hex_to_rgb(target_hex)
    delay = duration_ms / steps / 1000.0

    for i in range(1, steps + 1):
        t = i / steps
        write_color(rgb_to_hex(
            int(r0 + (r1 - r0) * t),
            int(g0 + (g1 - g0) * t),
            int(b0 + (b1 - b0) * t),
        ))
        time.sleep(delay)


# Color presets
PRESETS: dict[str, str] = {
    "Red":    "ff0000",
    "Green":  "00ff00",
    "Blue":   "0000ff",
    "Purple": "800080",
    "White":  "ffffff",
    "Orange": "ff7f00",
    "Cyan":   "00ffff",
}

# Colors for each performance mode — visual feedback of active mode
MODE_COLORS: dict[str, str] = {
    "silent":      "0040ff",
    "balanced":    "00ff80",
    "performance": "ff2000",
}

def _load_mode_colors_from_config() -> None:
    try:
        import tomlkit
        cfg = Path(__file__).parent.parent / "config.toml"
        doc = tomlkit.parse(cfg.read_text())
        saved = doc.get("rgb", {}).get("mode_colors", {})
        if saved:
            MODE_COLORS.update({k: str(v) for k, v in saved.items()})
    except Exception:
        pass

_load_mode_colors_from_config()
