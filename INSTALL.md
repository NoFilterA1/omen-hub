# Installation & Setup

## Quick Start

```bash
yay -S omen-hub
omen-hub
```

App works immediately for: temps, load, themes, modes.

## Enable GPU Switching (2 min setup)

```bash
omen-hub-setup
```

Or manually (if you prefer):

```bash
sudo visudo
# Add this line:
%wheel ALL=(ALL) NOPASSWD: /usr/bin/supergfxctl
```

Then test:
```bash
sudo -n supergfxctl -g
# Should print: Integrated or Hybrid (without password prompt)
```

## Enable Fan Control (optional)

```bash
sudo pacman -S omenctl-git
sudo systemctl enable --now omenctl
```

## Verify Everything Works

```bash
omen-hub-setup
# Will check all components and show what's working
```

## Troubleshooting

**"GPU switch button doesn't work"**
- Run `omen-hub-setup` and choose option 1

**"Fan RPM shows 0"**
- Install omenctl: `sudo pacman -S omenctl-git`
- Start daemon: `sudo systemctl enable --now omenctl`

**"PolicyKit error"**
- You're on minimal WM (good!). Use `omen-hub-setup` option 1 (NOPASSWD rule).
- Or install auth agent: `sudo pacman -S polkit-qt5`

## Post-Install

After `yay -S`:
- Run `omen-hub` to launch
- Appears in app menus (rofi, dmenu, etc)
- Settings saved to `~/.config/omen-hub/settings.json`

## Uninstall

```bash
yay -R omen-hub
rm -rf ~/.config/omen-hub
```

(sudo rule remains in `/etc/sudoers.d/omen-hub` if you used it)
