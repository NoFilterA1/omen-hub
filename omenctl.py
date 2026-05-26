#!/usr/bin/env python3
"""
omenctl — CLI for OMEN Hub daemon.

Usage:
  omenctl status
  omenctl mode silent | balanced | performance
  omenctl rgb <hex>          # e.g. omenctl rgb ff0000
  omenctl rgb preset <name>  # e.g. omenctl rgb preset Red
  omenctl rgb theme          # apply current DE accent color
  omenctl reload             # hot-reload daemon config
"""

import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.rgb import write_color, PRESETS, MODE_COLORS
from core.theme import get_accent_color

DEFAULT_SOCKET = "/tmp/omen-hub.sock"


# --- Daemon IPC ------------------------------------------------------------

def daemon_send(cmd: dict, socket_path: str = DEFAULT_SOCKET) -> dict | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect(socket_path)
            s.sendall(json.dumps(cmd).encode())
            data = s.recv(4096).decode()
            return json.loads(data)
    except (ConnectionRefusedError, FileNotFoundError):
        print("Error: daemon is not running. Start it with: systemctl start omen-hub-daemon")
        return None
    except OSError as e:
        print(f"Error: {e}")
        return None


# --- Commands --------------------------------------------------------------

def cmd_status() -> int:
    resp = daemon_send({"action": "status"})
    if not resp:
        return 1

    print(f"Mode:    {resp['mode']}")
    print(f"CPU:     {resp['cpu_temp']}°C")
    print(f"GPU:     {resp['gpu_temp']}°C")
    print(f"Fan 1:   {resp['fan1_pct']}%")
    print(f"Fan 2:   {resp['fan2_pct']}%")
    print(f"Control: {'BIOS' if resp['bios_owns_fans'] else 'omen-hub'}")
    return 0


def cmd_mode(mode: str) -> int:
    valid = ["silent", "balanced", "performance"]
    if mode not in valid:
        print(f"Error: unknown mode '{mode}'. Valid: {', '.join(valid)}")
        return 1

    # Apply power profile + RGB unconditionally — this fires the D-Bus signal
    # that Noctalia listens to for toast notifications, regardless of daemon state.
    from core.power import apply_profile
    apply_profile(mode)
    _apply_mode_rgb(mode)

    # Tell daemon to take over fan control too.
    resp = daemon_send({"action": "set_mode", "mode": mode})
    if not resp:
        print(f"Mode: {mode} (power profile applied; daemon offline — fan control unavailable)")
        return 0
    if not resp.get("ok"):
        print(f"Error: {resp.get('error')}")
        return 1

    print(f"Mode: {mode}")
    return 0


def cmd_rgb(args: list[str]) -> int:
    if not args:
        print("Usage: omenctl rgb <hex> | preset <name> | theme")
        return 1

    if args[0] == "theme":
        color = get_accent_color()
        if not color:
            print("Error: could not detect theme color (no supported DE found).")
            return 1
        write_color(color)
        print(f"RGB: #{color} (from theme)")
        return 0

    if args[0] == "preset":
        if len(args) < 2:
            print(f"Available presets: {', '.join(PRESETS)}")
            return 1
        name = args[1].capitalize()
        if name not in PRESETS:
            print(f"Error: unknown preset '{args[1]}'. Available: {', '.join(PRESETS)}")
            return 1
        write_color(PRESETS[name])
        print(f"RGB: {name} (#{PRESETS[name]})")
        return 0

    # Raw hex
    hex_color = args[0].lstrip("#")
    if len(hex_color) != 6 or not all(c in "0123456789abcdefABCDEF" for c in hex_color):
        print(f"Error: invalid hex color '{args[0]}'. Expected format: ff0000")
        return 1
    write_color(hex_color)
    print(f"RGB: #{hex_color}")
    return 0


def cmd_reload() -> int:
    resp = daemon_send({"action": "reload_config"})
    if not resp:
        return 1
    if not resp.get("ok"):
        print(f"Error: {resp.get('error')}")
        return 1
    print("Config reloaded.")
    return 0


def _apply_mode_rgb(mode: str) -> None:
    """Apply mode color to keyboard if rgb zone is accessible."""
    from core.rgb import is_available, write_color as _write
    if not is_available():
        return
    color = MODE_COLORS.get(mode)
    if color:
        try:
            _write(color)
        except PermissionError:
            pass  # udev rules not set up yet


# --- Entry point -----------------------------------------------------------

def main() -> int:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    cmd = args[0]

    if cmd == "status":
        return cmd_status()

    if cmd == "mode" and len(args) >= 2:
        return cmd_mode(args[1])

    if cmd == "rgb":
        return cmd_rgb(args[1:])

    if cmd == "reload":
        return cmd_reload()

    print(f"Error: unknown command '{cmd}'")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
