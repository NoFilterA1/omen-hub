#!/usr/bin/env python3
"""
OMEN Hub fan daemon.
Runs as root via systemd. Controls fans via EC.
Listens on Unix socket for instant mode changes from GUI/CLI.
"""

import json
import os
import select
import signal
import socket
import sys
import time
from pathlib import Path

# Allow running from project root without install
sys.path.insert(0, str(Path(__file__).parent.parent))

import tomlkit

from core import ec
from core.fan import modes_from_config, resolve_effective_mode
from core.power import apply_profile

# --- Config ----------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent.parent / "config.toml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return tomlkit.loads(f.read())


cfg = load_config()
svc = cfg.get("service", {})

POLL_INTERVAL: float = float(svc.get("poll_interval", 1.0))
SOCKET_PATH: str = svc.get("socket_path", "/tmp/omen-hub.sock")

# Keepalive every N seconds — must be well under the 120s EC watchdog
KEEPALIVE_INTERVAL = 10.0

FAN_MODES = modes_from_config(cfg)

# --- State -----------------------------------------------------------------

from core.power import get_current_pp
pp = get_current_pp()
current_mode = "performance" if pp == "performance" else ("silent" if pp == "power-saver" else "balanced")
bios_owns_fans = True
last_keepalive = 0.0
speed_old = -1.0
mode_old = ""
iteration = 0

# --- Logging ---------------------------------------------------------------

def log(msg: str) -> None:
    print(f"  {msg}", flush=True)

# --- Signal handling -------------------------------------------------------

def shutdown(signum, frame):
    log("Shutting down — returning fan control to BIOS.")
    try:
        ec.bios_take_control()
    except OSError:
        pass
    _cleanup_socket()
    try:
        os.unlink("/tmp/omen-fand.PID")
    except OSError:
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

# --- Socket IPC ------------------------------------------------------------

def _cleanup_socket() -> None:
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass


def setup_socket() -> socket.socket:
    _cleanup_socket()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)  # allow non-root GUI/CLI to connect
    sock.listen(4)
    sock.setblocking(False)
    return sock


def handle_command(data: str) -> str:
    """
    Process a JSON command from GUI/CLI.
    Returns JSON response string.
    """
    global current_mode, speed_old, mode_old, cfg, FAN_MODES, POLL_INTERVAL

    try:
        cmd = json.loads(data.strip())
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "error": "invalid json"})

    action = cmd.get("action")

    if action == "set_mode":
        mode = cmd.get("mode", "")
        if mode not in FAN_MODES:
            return json.dumps({"ok": False, "error": f"unknown mode: {mode}"})
        current_mode = mode
        speed_old = -1.0
        last_ipc_change = time.monotonic()
        apply_profile(mode)
        log(f"Mode changed to '{mode}' via IPC.")
        return json.dumps({"ok": True})

    if action == "status":
        cpu, gpu = ec.read_temps()
        try:
            fan1_pct, fan2_pct = ec.read_fan_pcts()
        except OSError:
            fan1_pct, fan2_pct = 0, 0
        return json.dumps({
            "ok": True,
            "mode": current_mode,
            "cpu_temp": cpu,
            "gpu_temp": gpu,
            "fan1_pct": fan1_pct,
            "fan2_pct": fan2_pct,
            "bios_owns_fans": bios_owns_fans,
        })

    if action == "reload_config":
        cfg = load_config()
        FAN_MODES = modes_from_config(cfg)
        POLL_INTERVAL = float(cfg.get("service", {}).get("poll_interval", 1.0))
        log("Config reloaded.")
        return json.dumps({"ok": True})

    return json.dumps({"ok": False, "error": f"unknown action: {action}"})


def poll_socket(server: socket.socket) -> None:
    """Accept and handle any pending socket connections (non-blocking)."""
    while True:
        ready, _, _ = select.select([server], [], [], 0)
        if not ready:
            break
        try:
            conn, _ = server.accept()
        except OSError:
            break
        with conn:
            conn.settimeout(1.0)
            try:
                data = conn.recv(4096).decode()
                if data:
                    response = handle_command(data)
                    conn.sendall(response.encode())
            except OSError:
                pass

# --- Main loop -------------------------------------------------------------

def main() -> None:
    global current_mode, bios_owns_fans, last_keepalive, speed_old, mode_old, iteration

    if os.geteuid() != 0:
        print("Error: daemon must run as root (EC access requires root).")
        sys.exit(1)

    # Warn if old omen-fand is still running (they'd fight over EC)
    OLD_PID_FILE = "/tmp/omen-fand.PID"
    if os.path.exists(OLD_PID_FILE):
        try:
            old_pid = int(open(OLD_PID_FILE).read().strip())
            os.kill(old_pid, 0)
            log(f"WARNING: old omen-fand daemon (PID {old_pid}) is still running!")
            log("Stop it first: systemctl stop omen-fand.service")
        except (OSError, ValueError):
            pass

    # Write our PID to /tmp/omen-fand.PID so the fallback shell script
    # (omen-fan-control.sh) knows a daemon is active and yields to us.
    with open(OLD_PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    log(f"OMEN Hub daemon starting. Mode: {current_mode}, poll: {POLL_INTERVAL}s")

    server = setup_socket()
    apply_profile(current_mode)

    while True:
        iteration += 1
        now = time.monotonic()

        # Check socket for mode changes / status requests
        poll_socket(server)

        # Read hardware state
        try:
            cpu_temp, gpu_temp = ec.read_temps()
        except OSError as e:
            log(f"EC read failed: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        temp = max(cpu_temp, gpu_temp)

        # Resolve effective mode (silent → balanced override at high temp)
        effective_mode = resolve_effective_mode(current_mode, temp, FAN_MODES)
        if effective_mode != current_mode:
            log(f"Silent override active at {temp}°C — using balanced.")

        if effective_mode != mode_old:
            log(f"Mode → {effective_mode}")
            mode_old = effective_mode
            speed_old = -1.0

        mode = FAN_MODES[effective_mode]
        speed_pct = mode.calc_speed_pct(temp)
        target_pct = max(speed_pct, mode.idle_speed)

        # Hysteresis: only update fans if speed changed by ≥2%
        if abs(target_pct - speed_old) >= 2.0:
            speed_old = target_pct
            log(f"[{effective_mode}] {temp}°C → {target_pct:.0f}%")
        elif iteration % 30 == 0:
            log(f"[{effective_mode}] {temp}°C  {target_pct:.0f}%  (steady)")

        # Fan control
        if target_pct == 0:
            if not bios_owns_fans:
                ec.bios_take_control()
                bios_owns_fans = True
        else:
            if bios_owns_fans:
                ec.bios_yield_control()
                bios_owns_fans = False

            fan1_ec, fan2_ec = mode.pct_to_ec(target_pct)
            try:
                ec.write_fan_speeds(fan1_ec, fan2_ec)
            except OSError as e:
                log(f"Fan write failed: {e}")

            # Keepalive: poke EC watchdog so BIOS doesn't reclaim fans
            if now - last_keepalive >= KEEPALIVE_INTERVAL:
                ec.keepalive()
                last_keepalive = now

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
