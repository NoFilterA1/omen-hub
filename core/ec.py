"""
EC (Embedded Controller) low-level access.

Registers were reverse-engineered for HP OMEN 17 by monitoring EC changes via
ec_probe while using the official OMEN Gaming Hub on Windows. Should be the same
across OMEN 17 generations of the same platform, but may differ on other HP models.

Full register map (from docs/ec_registers.md):
  FANS (writable):
    0x34 — FAN1 speed set (EC units, max ≈55, units of 100 RPM)
    0x35 — FAN2 speed set (EC units, max ≈57, units of 100 RPM)
    0xEC — Fan Boost: 0x00=off, 0x0C=on
    0xF4 — Fan State: 0x00=enabled, 0x02=disabled

  FANS (read-only):
    0x2E — FAN1 speed % (0–100)
    0x2F — FAN2 speed % (0–100)
    0xB1 — FAN1 speed raw (0–0x16)
    0xB3 — FAN2 speed raw (0–0x16)

  TEMPERATURE (read-only):
    0x57 — CPU temperature (°C)
    0xB7 — GPU temperature (°C)

  BIOS CONTROL (writable):
    0x62 — BIOS fan control: 0x00=BIOS owns fans, 0x06=we own fans
    0x63 — Watchdog timer: counts down to 0, then BIOS reclaims fans.
             Set to 0x78 (120s) automatically on certain EC writes.
             Write 0x00 to disable.

  POWER (writable):
    0x95 — Performance mode: 0x31=performance (fixes throttling), other values for other modes
"""

import os

EC_PATH = "/sys/kernel/debug/ec/ec0/io"


def _open_write():
    return os.fdopen(os.open(EC_PATH, os.O_WRONLY), "wb")


def read_byte(offset: int) -> int:
    with open(EC_PATH, "rb") as f:
        f.seek(offset)
        return int.from_bytes(f.read(1), "big")


def write_byte(offset: int, value: int) -> None:
    with _open_write() as f:
        f.seek(offset)
        f.write(bytes([value]))


def read_temps() -> tuple[int, int]:
    """Returns (cpu_temp_c, gpu_temp_c)."""
    with open(EC_PATH, "rb") as f:
        f.seek(0x57)
        cpu = int.from_bytes(f.read(1), "big")
        f.seek(0xB7)
        gpu = int.from_bytes(f.read(1), "big")
    return cpu, gpu


def write_fan_speeds(fan1_ec: int, fan2_ec: int) -> None:
    """
    Write fan speeds directly to EC.
    fan1_ec: 0–55, fan2_ec: 0–57 (EC units, not %)
    """
    with _open_write() as f:
        f.seek(0x34)
        f.write(bytes([int(fan1_ec)]))
        f.seek(0x35)
        f.write(bytes([int(fan2_ec)]))


def bios_take_control() -> None:
    """Release fan control back to BIOS."""
    with _open_write() as f:
        f.seek(0x62)
        f.write(bytes([0]))
        f.seek(0x34)
        f.write(bytes([0]))
        f.seek(0x35)
        f.write(bytes([0]))


def bios_yield_control() -> None:
    """
    Take fan control away from BIOS.
    Must be called before writing fan speeds, and periodically to prevent
    BIOS from reclaiming control via its internal watchdog timer.
    """
    with _open_write() as f:
        f.seek(0x62)
        f.write(bytes([6]))
    # Small delay then disable the BIOS countdown timer
    import time; time.sleep(0.05)
    with _open_write() as f:
        f.seek(0x63)
        f.write(bytes([0]))


def keepalive() -> None:
    """
    Poke 0x62 + reset 0x63 watchdog to prevent BIOS reclaiming fan control.
    The watchdog at 0x63 counts down from 120s and resets BIOS control at 0.
    Call at least every 60 seconds while we own the fans.
    """
    try:
        with _open_write() as f:
            f.seek(0x62)
            f.write(bytes([6]))
            f.seek(0x63)
            f.write(bytes([0]))
    except OSError:
        pass


def read_fan_pcts() -> tuple[int, int]:
    """Read current fan speeds as % (0–100). Read-only registers 0x2E, 0x2F."""
    with open(EC_PATH, "rb") as f:
        f.seek(0x2E)
        fan1 = int.from_bytes(f.read(1), "big")
        f.seek(0x2F)
        fan2 = int.from_bytes(f.read(1), "big")
    return fan1, fan2


def set_performance_mode(perf: bool) -> None:
    """
    Write 0x95 performance register.
    0x31 = performance mode (fixes throttling on OMEN 17).
    0x10 = balanced/normal.
    """
    write_byte(0x95, 0x31 if perf else 0x10)
