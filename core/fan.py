"""
Fan curve logic. No hardware access here — pure math + config.
Hardware writes happen in daemon/fand.py via core/ec.py.
"""

from bisect import bisect_left
from dataclasses import dataclass, field

FAN1_EC_MAX = 55
FAN2_EC_MAX = 57


@dataclass
class FanMode:
    temp_curve: list[int]
    speed_curve: list[float]   # % 0–100
    idle_speed: float          # % when below first threshold
    override_temp: int | None  # if set: above this temp, use 'balanced' instead

    slopes: list[float] = field(init=False, repr=False)

    def __post_init__(self):
        tc, sc = self.temp_curve, self.speed_curve
        self.slopes = [
            round((sc[i] - sc[i - 1]) / (tc[i] - tc[i - 1]), 4)
            for i in range(1, len(tc))
        ]

    def calc_speed_pct(self, temp: int) -> float:
        """Interpolate fan speed % for given temperature."""
        tc, sc = self.temp_curve, self.speed_curve
        if temp <= tc[0]:
            return float(self.idle_speed)
        if temp >= tc[-1]:
            return float(sc[-1])
        i = bisect_left(tc, temp)
        return sc[i - 1] + self.slopes[i - 1] * (temp - tc[i - 1])

    def pct_to_ec(self, pct: float) -> tuple[int, int]:
        """Convert speed % to EC units for both fans."""
        return (
            int(FAN1_EC_MAX * pct / 100),
            int(FAN2_EC_MAX * pct / 100),
        )


# Default modes — overridable via config.toml [fan.modes.*]
DEFAULT_MODES: dict[str, FanMode] = {
    "silent": FanMode(
        temp_curve=[65, 75, 83, 88, 93],
        speed_curve=[8, 20, 45, 75, 100],
        idle_speed=0,
        override_temp=88,  # above this → fall back to balanced
    ),
    "balanced": FanMode(
        temp_curve=[50, 60, 70, 80, 87, 93],
        speed_curve=[20, 40, 60, 70, 85, 100],
        idle_speed=0,
        override_temp=None,
    ),
    "performance": FanMode(
        temp_curve=[35, 45, 55, 62, 68, 75],
        speed_curve=[30, 50, 75, 90, 97, 100],
        idle_speed=30,
        override_temp=None,
    ),
}

VALID_MODES = list(DEFAULT_MODES.keys())


def resolve_effective_mode(requested: str, temp: int, modes: dict[str, FanMode]) -> str:
    """
    Return the mode that should actually be used.
    If requested mode has override_temp and temp >= it, fall back to balanced.
    """
    mode = modes.get(requested, modes["balanced"])
    if mode.override_temp and temp >= mode.override_temp:
        return "balanced"
    return requested


def modes_from_config(cfg: dict) -> dict[str, FanMode]:
    """
    Build FanMode dict from parsed config.toml.
    Falls back to DEFAULT_MODES for any missing mode.
    """
    result = dict(DEFAULT_MODES)
    fan_cfg = cfg.get("fan", {}).get("modes", {})
    for name, vals in fan_cfg.items():
        if "temp_curve" in vals and "speed_curve" in vals:
            result[name] = FanMode(
                temp_curve=list(vals["temp_curve"]),
                speed_curve=list(vals["speed_curve"]),
                idle_speed=float(vals.get("idle_speed", 0)),
                override_temp=vals.get("override_temp"),
            )
    return result
