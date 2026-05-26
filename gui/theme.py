"""
Central GUI palette + theme.

One muted, desaturated token set per theme (dark/light) so the UI reads as
"mature" rather than plasticine. Custom-painted widgets read tokens at paint
time via color()/qcolor(); QSS-styled widgets get a stylesheet built from the
same tokens. Theme choice is persisted through core.settings.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor

from core import settings as _settings

# ── Token sets ──────────────────────────────────────────────────────────────
# Neutral, slightly cool greys. Accent is injected from user settings at read
# time so it stays consistent with NavTab/title.

_DARK = {
    "bg":         "0f0f12",
    "surface":    "17171b",
    "surface_2":  "1d1d22",
    "border":     "28282f",
    "text":       "e7e7ec",
    "text_dim":   "9a9aa5",
    "text_mute":  "6a6a74",
    "text_faint": "474751",
    "danger":     "c25450",
}

_LIGHT = {
    "bg":         "eef0f3",
    "surface":    "ffffff",
    "surface_2":  "e7e9ed",
    "border":     "d4d6dc",
    "text":       "1a1c20",
    "text_dim":   "5b5e66",
    "text_mute":  "888c95",
    "text_faint": "aab0ba",
    "danger":     "c0433d",
}

_THEMES = {"dark": _DARK, "light": _LIGHT}


def _tokens() -> dict[str, str]:
    return _THEMES.get(_settings.get_theme(), _DARK)


def is_dark() -> bool:
    return _settings.get_theme() != "light"


def accent() -> str:
    """Accent hex without '#'."""
    return _settings.get_accent()


def shade(hex_color: str) -> str:
    """A color suitable for accents/lines on the CURRENT theme surface.

    Dark theme: returned unchanged. Light theme: darkened so a saturated accent
    or mode color reads clearly on a near-white background instead of glowing.
    """
    h = hex_color.lstrip("#")
    if is_dark():
        return f"#{h}"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    f = 0.56
    return f"#{int(r * f):02x}{int(g * f):02x}{int(b * f):02x}"


def color(name: str) -> str:
    """'#rrggbb' for the current theme. 'accent' resolves to the user accent,
    shaded to suit the current surface (see shade())."""
    if name == "accent":
        return shade(accent())
    return f"#{_tokens().get(name, 'ff00ff')}"


def qcolor(name: str, alpha: int = 255) -> QColor:
    c = QColor(color(name))
    if alpha != 255:
        c.setAlpha(alpha)
    return c


def temp_qcolor(value: int) -> QColor:
    """Muted cool->warm ramp for a temperature 0..100+ (°C)."""
    pct = max(0.0, min(value / 100.0, 1.0))
    cool = (0x6c, 0x93, 0xb8)   # calm blue
    warm = (0xc7, 0x9a, 0x4e)   # muted amber
    hot  = (0xc2, 0x5a, 0x52)   # muted red
    if pct <= 0.6:
        f = pct / 0.6
        a, b = cool, warm
    else:
        f = (pct - 0.6) / 0.4
        a, b = warm, hot
    r = int(a[0] + (b[0] - a[0]) * f)
    g = int(a[1] + (b[1] - a[1]) * f)
    bch = int(a[2] + (b[2] - a[2]) * f)
    return QColor(r, g, bch)


# ── Global stylesheet ─────────────────────────────────────────────────────────

def stylesheet() -> str:
    """App-wide QSS built from the current theme tokens.

    Role-based selectors (objectName) let surfaces re-theme live: rebuilding
    this string and re-setting it on the window restyles every tagged widget.
    """
    t = _tokens()
    ac = shade(accent())  # '#rrggbb', theme-appropriate
    return f"""
QWidget {{
    background: #{t['bg']};
    color: #{t['text']};
    font-family: "Inter", "Noto Sans", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QScrollBar:vertical {{
    background: #{t['surface_2']}; width: 5px; border-radius: 2px;
}}
QScrollBar::handle:vertical {{
    background: #{t['border']}; border-radius: 2px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{
    background: #{t['surface_2']}; color: #{t['text']};
    border: 1px solid #{t['border']}; border-radius: 4px; padding: 4px;
}}
QLabel, QCheckBox {{ background: transparent; }}

/* ── Role surfaces ─────────────────────────────────────────────── */
QFrame#card {{
    background: #{t['surface']};
    border-radius: 10px;
}}
QLabel#h {{
    color: #{t['text_mute']};
    font-size: 10px; font-weight: bold; letter-spacing: 1px;
}}
QLabel#note  {{ color: #{t['text_faint']}; font-size: 10px; }}
QLabel#dim   {{ color: #{t['text_dim']};   font-size: 12px; }}
QLabel#val   {{ color: #{t['text_dim']};   font-size: 11px; }}
QLabel#valdim {{ color: #{t['text_faint']}; font-size: 11px; }}

QPushButton#primary {{
    background: {ac}; color: #ffffff; border: none;
    border-radius: 6px; padding: 5px 18px; font-size: 12px;
}}
QPushButton#primary:hover {{ background: {ac}; }}

QCheckBox {{ color: #{t['text_dim']}; font-size: 12px; }}

QComboBox {{
    background: #{t['surface_2']}; color: #{t['text']};
    border: 1px solid #{t['border']}; border-radius: 6px;
    padding: 3px 10px; font-size: 12px;
}}
QComboBox:hover {{ border-color: {ac}; }}
QComboBox QAbstractItemView {{
    background: #{t['surface_2']}; color: #{t['text']};
    border: 1px solid #{t['border']};
    selection-background-color: {ac};
}}
"""
