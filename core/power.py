"""
Power profile and GPU TDP control.
"""

import subprocess
from dataclasses import dataclass


@dataclass
class PowerProfile:
    name: str                  # "silent" | "balanced" | "performance"
    pp_profile: str            # powerprofilesctl value
    epp: str                   # energy_performance_preference
    gpu_tdp_w: int | None      # nvidia-smi power limit (None = don't touch)
    gpu_freq_lock: tuple[int, int] | None  # (min, max) MHz, None = reset


PROFILES: dict[str, PowerProfile] = {
    "silent": PowerProfile(
        name="silent",
        pp_profile="power-saver",
        epp="power",
        gpu_tdp_w=30,
        gpu_freq_lock=None,
    ),
    "balanced": PowerProfile(
        name="balanced",
        pp_profile="balanced",
        epp="balance_power",
        gpu_tdp_w=80,
        gpu_freq_lock=None,
    ),
    "performance": PowerProfile(
        name="performance",
        pp_profile="performance",
        epp="performance",
        gpu_tdp_w=115,
        gpu_freq_lock=(2100, 2500),
    ),
}


def _run(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def apply_cpu_profile(profile: PowerProfile) -> None:
    _run(["powerprofilesctl", "set", profile.pp_profile])
    # EPP via sysfs — best-effort, not all kernels expose this
    try:
        import glob
        for path in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference"):
            with open(path, "w") as f:
                f.write(profile.epp)
    except OSError:
        pass


def apply_gpu_profile(profile: PowerProfile) -> None:
    if profile.gpu_tdp_w is None:
        return

    _run(["nvidia-smi", "-pm", "1"])
    _run(["nvidia-smi", "-pl", str(profile.gpu_tdp_w)])

    lock = profile.gpu_freq_lock
    if lock and len(lock) == 2:
        _run(["nvidia-smi", "-lgc", f"{lock[0]},{lock[1]}"])
    else:
        _run(["nvidia-smi", "-rgc"])


def apply_profile(name: str) -> bool:
    """Apply named power profile. Returns False if name unknown."""
    profile = PROFILES.get(name)
    if not profile:
        return False
    apply_cpu_profile(profile)
    apply_gpu_profile(profile)
    return True


def get_current_pp() -> str | None:
    """Read active powerprofilesctl profile."""
    try:
        result = subprocess.run(
            ["powerprofilesctl", "get"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
