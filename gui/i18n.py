"""
Tiny translation layer. t(key) resolves against the language stored in
core.settings, falling back to English, then to the key itself.

Language is read live, so changing it and rebuilding labels is enough — no
process restart needed.
"""

from __future__ import annotations

from core import settings as _settings

_TR: dict[str, dict[str, str]] = {
    "en": {
        # nav
        "nav_info": "Control Center",
        "nav_fans": "Fan Curve",
        "nav_system": "System",
        "nav_keyboard": "Keyboard",
        "nav_settings": "Settings",
        # gpu / mux
        "gpu_mode": "GPU Mode",
        "mux_hybrid": "Hybrid",
        "mux_integrated": "Integrated",
        "mux_discrete": "Discrete",
        "gpu_switching": "Switching…",
        "gpu_logout": "log out to apply",
        "gpu_active": "Active:",
        "gpu_done": "Done — log out to apply the new GPU mode.",
        "gpu_failed": "Failed",
        "gpu_unknown_error": "unknown error",
        "gpu_logout_warn": "Switching GPU mode requires logout to take effect.",
        "gpu_switch_title": "Switch GPU Mode",
        "gpu_switch_body": "Switch to {mode} mode?\n\nYou will need to log out for the change to take effect.",
        "hw_hardware": "Hardware",
        "hw_software": "Software",
        "hw_product": "Product",
        "hw_cpu": "CPU",
        "hw_gpu": "GPU",
        "hw_ram": "RAM",
        "hw_disk": "Disk",
        "hw_uptime": "Uptime",
        "hw_battery": "Battery",
        "hw_os": "OS",
        "hw_kernel": "Kernel",
        "hw_arch": "Architecture",
        "idle_speed": "Idle speed",
        "reset_defaults": "Reset to defaults",
        "fan_curve_hint": "Left-click empty area to add point  ·  Right-click point to remove",
        "reset_to_defaults_hint": "Reset to defaults — click Save to persist",
        # info
        "performance_mode": "Performance Mode",
        "system": "System",
        "fan_curve": "Fan Curve",
        "silent": "Silent",
        "balanced": "Balanced",
        "performance": "Performance",
        "desc_silent": "Fans quiet. GPU 30W. CPU power-saver.",
        "desc_balanced": "Moderate fans. GPU 80W. CPU balanced.",
        "desc_performance": "Aggressive fans. GPU 115W. CPU max.",
        "control": "Control",
        # keyboard
        "preview": "Preview",
        "color": "Color",
        "effects": "Effects",
        "speed": "Speed",
        "brightness": "Brightness",
        "follow_mode": "Change color with performance mode",
        "fx_static": "Static",
        "fx_rainbow": "Rainbow",
        "fx_police": "Police",
        "fx_newyear": "New Year",
        "rgb_unavailable": "RGB not available.\nCheck that hp-omen-wmi-dkms is "
                           "installed and udev rules are set up.",
        # settings
        "appearance": "Appearance",
        "temperature_unit": "Temperature unit",
        "fahrenheit": "Fahrenheit (°F)",
        "accent_color": "Accent color",
        "theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "language": "Language",
        "rgb_mode_colors": "RGB Mode Colors",
        "rgb_mode_note": "Color applied to keyboard when switching performance mode.",
        "save": "Save",
        "saved": "Saved",
        "save_failed": "Save failed",
        "unsaved_changes": "Unsaved changes",
        "about": "About",
        "version": "Version",
        "device": "Device",
        "project": "Project",
        # status
        "connecting": "Connecting…",
        "daemon_offline": "omen-hub daemon not running",
    },
}


def t(key: str) -> str:
    lang = _settings.get_language()
    return _TR.get(lang, {}).get(key) or _TR["en"].get(key, key)


def available() -> list[tuple[str, str]]:
    """(code, label) pairs for a language selector."""
    return [("en", "English")]
