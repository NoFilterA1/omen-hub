"""
Direct hardware sensor reading — no root, no daemon required.
Used as fallback when daemon is offline.
"""

import glob
import subprocess

# Module-level cache for CPU load delta calculation
_cpu_stat_prev: tuple[int, int] | None = None  # (active, total)


def read_cpu_temp() -> int:
    """CPU temp in °C from k10temp/coretemp hwmon. No root needed."""
    for path in glob.glob("/sys/class/hwmon/hwmon*/"):
        try:
            name = open(path + "name").read().strip()
            if name in ("k10temp", "coretemp"):
                for t in sorted(glob.glob(path + "temp*_input")):
                    val = int(open(t).read().strip())
                    return val // 1000
        except OSError:
            continue
    return 0


def read_gpu_temp() -> int:
    """GPU temp in °C. Tries nvidia-smi then amdgpu hwmon."""
    # NVIDIA
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1
        )
        if out.returncode == 0:
            return int(out.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    # AMD
    for path in glob.glob("/sys/class/hwmon/hwmon*/"):
        try:
            if open(path + "name").read().strip() == "amdgpu":
                return int(open(path + "temp1_input").read().strip()) // 1000
        except OSError:
            continue
    return 0


def read_fan_rpms() -> tuple[int, int]:
    """Fan RPMs from hp-wmi hwmon. No root needed."""
    for path in glob.glob("/sys/class/hwmon/hwmon*/"):
        try:
            if open(path + "name").read().strip() == "hp":
                fan1 = int(open(path + "fan1_input").read().strip())
                fan2 = int(open(path + "fan2_input").read().strip())
                return fan1, fan2
        except OSError:
            continue
    return 0, 0


def read_cpu_load() -> int:
    """CPU load % since last call. First call always returns 0."""
    global _cpu_stat_prev
    try:
        parts = open("/proc/stat").readline().split()
        vals = list(map(int, parts[1:]))
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals)
        active = total - idle
        if _cpu_stat_prev is None:
            _cpu_stat_prev = (active, total)
            return 0
        da = active - _cpu_stat_prev[0]
        dt = total - _cpu_stat_prev[1]
        _cpu_stat_prev = (active, total)
        return max(0, min(100, int(da / dt * 100))) if dt > 0 else 0
    except OSError:
        return 0


def read_cpu_freq() -> int:
    """Current max CPU freq in MHz. No root needed."""
    try:
        freqs = [
            int(open(p).read().strip())
            for p in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq")
        ]
        return max(freqs) // 1000 if freqs else 0
    except OSError:
        return 0


def read_ram_usage() -> tuple[float, float]:
    """Returns (used_gb, total_gb). No root needed."""
    try:
        data: dict[str, int] = {}
        for line in open("/proc/meminfo"):
            key, val = line.split(":")
            data[key.strip()] = int(val.split()[0])
        total = data.get("MemTotal", 0) / 1024 / 1024
        available = data.get("MemAvailable", 0) / 1024 / 1024
        return round(total - available, 1), round(total, 1)
    except OSError:
        return 0.0, 0.0


def read_gpu_stats() -> dict:
    """NVIDIA GPU stats. Returns {load, freq_mhz, power_w} — all 0 if unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,clocks.current.graphics,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1,
        )
        if out.returncode == 0:
            parts = [x.strip() for x in out.stdout.strip().split(",")]
            load = int(parts[0])
            freq = int(parts[1])
            power = float(parts[2])
            # nvidia-smi reports bogus utilization at very low power states (P8 idle)
            if power < 5.0 and freq < 300:
                load = 0
            return {"load": load, "freq_mhz": freq, "power_w": power}
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    return {"load": 0, "freq_mhz": 0, "power_w": 0.0}


def read_system_info() -> dict:
    """Static hardware info — call once at startup."""
    import shutil
    info: dict[str, str] = {}

    try:
        info["product"] = open("/sys/class/dmi/id/product_name").read().strip()
    except OSError:
        info["product"] = "HP OMEN"

    try:
        for line in open("/proc/cpuinfo"):
            if "model name" in line:
                info["cpu"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        info["cpu"] = "Unknown"

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0:
            parts = out.stdout.strip().split(",")
            name = parts[0].strip()
            mem_mb = int(parts[1].strip()) if len(parts) > 1 else 0
            info["gpu"] = f"{name}  ({mem_mb // 1024} GB VRAM)" if mem_mb else name
    except Exception:
        info["gpu"] = "Unknown"

    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                kb = int(line.split()[1])
                info["ram"] = f"{kb // 1024 // 1024} GB"
                break
    except OSError:
        info["ram"] = "Unknown"

    try:
        du = shutil.disk_usage("/")
        info["disk"] = (f"{du.free // (1024**3)} GB free"
                        f" / {du.total // (1024**3)} GB total")
    except OSError:
        info["disk"] = "Unknown"

    try:
        info["kernel"] = open("/proc/version").read().split()[2]
    except OSError:
        import platform
        info["kernel"] = platform.release()

    try:
        for line in open("/etc/os-release"):
            if line.startswith("PRETTY_NAME="):
                info["os"] = line.split("=", 1)[1].strip().strip('"')
                break
    except OSError:
        info["os"] = "Linux"

    try:
        import platform
        info["arch"] = platform.machine()
    except Exception:
        info["arch"] = "x86_64"

    return info
