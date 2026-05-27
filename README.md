<p align="center">
  <img src="images/logo.svg" width="120" alt="OMEN Hub Logo">
</p>

<h1 align="center">OMEN Hub for Linux</h1>

<p align="center">
  A modern, lightweight GUI replacement for HP OMEN Gaming Hub on Linux.<br>
  Control GPU modes, fan curves, RGB lighting, and monitor system thermals.
</p>

<p align="center">
  <b>Works on:</b> HP OMEN 16/17 (AMD Ryzen + RTX) · Arch Linux · CachyOS · NixOS
</p>

---

<p align="center">
  <img src="screenshots/control-center-dark.png" width="45%" alt="Control Center Dark">
  <img src="screenshots/control-center-light.png" width="45%" alt="Control Center Light">
</p>
<p align="center">
  <img src="screenshots/fan-curve-dark.png" width="45%" alt="Fan Curve Dark">
  <img src="screenshots/fan-curve-light.png" width="45%" alt="Fan Curve Light">
</p>
<p align="center">
  <img src="screenshots/system-dark.png" width="45%" alt="System Dark">
  <img src="screenshots/system-light.png" width="45%" alt="System Light">
</p>
<p align="center">
  <img src="screenshots/keyboard-dark.png" width="45%" alt="Keyboard Dark">
  <img src="screenshots/keyboard-light.png" width="45%" alt="Keyboard Light">
</p>
<p align="center">
  <img src="screenshots/settings-dark.png" width="45%" alt="Settings Dark">
  <img src="screenshots/settings-light.png" width="45%" alt="Settings Light">
</p>

---

## ✨ Features

- 🎮 **GPU Switching** — Integrated ↔ Hybrid mode without reboot (via `supergfxctl`)
- 🌡️ **Real-time Sensors** — CPU/GPU temps, fan RPM, live sparklines (CPU/GPU/RAM)
- 🎛️ **Fan Curves** — Balanced/Silent/Performance presets, live editing
- ⌨️ **Keyboard RGB** — Per-key backlight preview with mode-specific colors
- 🌙 **Dark/Light Theme** — Live switching, accent color customization
- 🌍 **Multilingual** — English, Dutch, Русский
- 📦 **Minimal** — PyQt6, no external daemons required

---

## 🚀 Installation

### Arch / AUR (recommended)
```bash
yay -S omen-hub
```

**Post-install (recommended):**
```bash
# For GPU switching + fans:
sudo pacman -S supergfxctl omenctl-git polkit
sudo systemctl enable --now omenctl

# For fan reading:
sudo usermod -aG wheel $USER  # then log out and back in
```

### Manual

**Dependencies:**
- `python` ≥ 3.10
- `python-pyqt6` ≥ 6.0
- `python-tomlkit`
- `supergfxctl` (required for GPU mode switching)
- `omenctl-git` (optional; for fan RPM readings and control daemon)

```bash
git clone https://github.com/yourusername/omen-hub.git
cd omen-hub
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m gui.app
```

---

## 📖 Usage

```bash
omen-hub              # launch from terminal or app menu
```

After AUR install:
- Binary: `/usr/bin/omen-hub`
- Config: `~/.config/omen-hub/settings.json`

Settings saved: theme, language, accent color, fan curve presets.

---

## 🏗️ Architecture

```
omen-hub/
├── core/              # Logic: sensors, fan control, GPU mode, settings
├── gui/               # PyQt6 UI
│   ├── theme.py       # Color palette + role-based QSS
│   ├── i18n.py        # Translations (en/ru)
│   ├── app.py         # Main window, navigation
│   ├── widgets.py     # Custom: TempGauge, FanWidget, Keyboard, etc.
│   └── pages/         # Info, System, Fans, Keyboard, Settings pages
├── config.toml        # Fan curve definitions
└── requirements.txt
```

---

## ⚙️ What Works / What Requires Setup

### ✓ Works out-of-the-box
- CPU/GPU temps, system load — no privileges needed
- Dark/light switching, language selection, accent colors
- Mode descriptions (Balanced/Silent/Performance)

### ⚠️ Requires additional setup

| Feature | Status | How to Fix |
|---------|--------|-----------|
| **GPU Mode Switch** | Needs `pkexec` | Install `polkit` + ensure PolicyKit agent running |
| **Fan RPM Reading** | Needs `omenctl` daemon | `sudo pacman -S omenctl-git && sudo systemctl enable --now omenctl` |
| **Fan Curve Control** | Needs `omenctl` daemon | Same as above |
| **Keyboard RGB** | Needs kernel support | See below |

### 🔧 Keyboard RGB Setup

**Option 1: Via kernel module**
```bash
lsmod | grep hp_wmi
sudo modprobe hp_wmi
```

**Option 2: Custom kernel** — Arch/CachyOS with `linux-zen` or `linux-cachyos` usually includes EC access.

---

## 🐛 Troubleshooting

**"authorization cancelled" on GPU switch:**
```bash
systemctl status polkit
groups | grep wheel   # if missing: sudo usermod -aG wheel $USER
```

**Fan RPM shows 0:**
```bash
systemctl status omenctl
sudo systemctl enable --now omenctl
```

**"ModuleNotFoundError: No module named 'PyQt6'":**
```bash
sudo pacman -S python-pyqt6 python-tomlkit
```

---

## 🤝 Contributing

1. **Bug fixes:** Create an issue first, then PR with description.
2. **Features:** Discuss in an issue before implementing.
3. **Code style:** Python 3.10+, PEP 8, theme-aware colors (`theme.color(role)`), minimal comments.
4. **Do NOT modify** `core/settings.py`, `gui/i18n.py`, `gui/theme.py` without coordination.
5. **Test offscreen before submitting:**
   ```bash
   HOME=/tmp/omenverify QT_QPA_PLATFORM=offscreen python -m gui.app
   ```

---

## 🌍 Translation

Edit `gui/i18n.py` — add a new dict to `_TR`. Keys follow pattern: `nav_*`, `hw_*`, `gpu_*`, etc.

---

## ⚖️ License

GPL-3.0 — See [LICENSE](LICENSE).

---

*Inspired by [OmenCtl](https://github.com/yunusemreyl/OmenCommandCenterforLinux) · Uses `supergfxctl` for GPU switching*
