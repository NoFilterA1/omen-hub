"""Persistent user settings for the GUI (keyboard effects, appearance, etc.)."""

import json
from pathlib import Path

_PATH = Path.home() / ".config" / "omen-hub" / "settings.json"

_DEFAULTS: dict = {
    "keyboard": {
        "color":      "00cc66",
        "effect":     "static",
        "brightness": 100,
        "speed":      30,
    },
    "appearance": {
        "temp_unit":    "C",
        "accent_color": "5566ff",
        "theme":        "dark",
        "language":     "en",
    },
}

# Module-level cached state (updated on save, loaded at startup)
_temp_unit_f: bool = False
_accent_color: str = "5566ff"
_theme: str = "dark"
_language: str = "en"


def use_fahrenheit() -> bool:
    return _temp_unit_f


def set_temp_unit(fahrenheit: bool) -> None:
    global _temp_unit_f
    _temp_unit_f = fahrenheit
    save_section("appearance", {"temp_unit": "F" if fahrenheit else "C"})


def get_accent() -> str:
    return _accent_color


def set_accent(hex_color: str) -> None:
    global _accent_color
    _accent_color = hex_color
    save_section("appearance", {"accent_color": hex_color})


def get_theme() -> str:
    return _theme


def set_theme(name: str) -> None:
    global _theme
    _theme = name if name in ("dark", "light") else "dark"
    save_section("appearance", {"theme": _theme})


def get_language() -> str:
    return _language


def set_language(code: str) -> None:
    global _language
    _language = code
    save_section("appearance", {"language": code})


def load() -> dict:
    try:
        data = json.loads(_PATH.read_text())
        result = {}
        for section, defaults in _DEFAULTS.items():
            result[section] = {**defaults, **data.get(section, {})}
        return result
    except Exception:
        return {k: dict(v) for k, v in _DEFAULTS.items()}


def save(data: dict) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        try:
            existing = json.loads(_PATH.read_text())
        except Exception:
            pass
        existing.update(data)
        _PATH.write_text(json.dumps(existing, indent=2))
    except Exception:
        pass


def save_section(section: str, values: dict) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        try:
            existing = json.loads(_PATH.read_text())
        except Exception:
            pass
        existing.setdefault(section, {}).update(values)
        _PATH.write_text(json.dumps(existing, indent=2))
    except Exception:
        pass


# Load cached state at import time
_boot = load()
_temp_unit_f  = _boot.get("appearance", {}).get("temp_unit", "C") == "F"
_accent_color = _boot.get("appearance", {}).get("accent_color", "5566ff")
_theme        = _boot.get("appearance", {}).get("theme", "dark")
_language     = _boot.get("appearance", {}).get("language", "en")
