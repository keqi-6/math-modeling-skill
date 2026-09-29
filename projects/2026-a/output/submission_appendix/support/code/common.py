"""Raw workbook inputs, units and portable numerical-result storage."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import numpy as np
import scipy
import openpyxl
from scipy.interpolate import PchipInterpolator

DATA = Path(__file__).resolve().parents[1] / "data"


def numeric_rows(path, columns):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(book.worksheets[0].iter_rows(min_row=2, max_col=columns, values_only=True))
        values = np.asarray(rows, dtype=float)
    finally:
        book.close()
    if values.ndim != 2 or values.shape[1] != columns or not np.isfinite(values).all():
        raise ValueError(f"Invalid numeric input: {Path(path).name}")
    return values


class Boundary:
    """Linear observed input; after four hours use the selected constant tail."""
    def __init__(self, path=DATA / "附件1.xlsx", scenario="mean_tail", *, q1=False):
        if scenario not in ("mean_tail", "last_value"):
            raise ValueError("Unknown boundary scenario")
        a = numeric_rows(path, 3)
        if a.shape != (241, 3) or not np.array_equal(a[:, 0], np.arange(0, 14401, 60)):
            raise ValueError("Expected 241 observations at 60-second intervals")
        if np.any(a[:, 1] <= -273.15) or np.any(a[:, 2] <= 0):
            raise ValueError("Invalid environmental temperature or moisture")
        self.scenario, self.q1 = scenario, q1
        # Trapezoidal integration of the final hour's linear interpolant.
        tail_values = a[180:241, 1:]
        mean = [float(sum((Decimal(str(x)) + Decimal(str(y))) * 30
                          for x, y in zip(tail_values[:-1, j], tail_values[1:, j]))
                      / Decimal(3600)) for j in range(2)]
        self.tail = tuple(map(float, mean if scenario == "mean_tail" else a[-1, 1:]))
        a = a[:31] if q1 else a
        self.times, self.temperature, self.moisture = (a[:, j].copy() for j in range(3))

    def evaluate(self, t):
        if not np.isscalar(t) or not np.isfinite(t) or t < 0:
            raise ValueError("Boundary time must be a finite nonnegative scalar")
        if self.q1 and t > 1800:
            raise ValueError("Q1 input is limited to 0--1800 seconds")
        if t <= self.times[-1]:
            return (float(np.interp(t, self.times, self.temperature)),
                    float(np.interp(t, self.times, self.moisture)))
        return self.tail

    def right_side(self):
        tail = self.tail
        class RightSide:
            def evaluate(self, t):
                if not np.isscalar(t) or not np.isfinite(t) or t < 14400:
                    raise ValueError("Right-side boundary requires t >= 14400 seconds")
                return tail
        return RightSide()


class RadiusInput:
    """Observed radius in metres; material equations do not require R-prime."""
    def __init__(self, path=DATA / "附件2.xlsx", method="linear", *,
                 tail="error", constant_radius_m=0.02):
        if method not in ("linear", "pchip", "constant") or tail not in ("error", "hold_last"):
            raise ValueError("Unknown radius interpolation or continuation")
        a = numeric_rows(path, 2)
        if a.shape != (145, 2) or not np.array_equal(a[:, 0], np.arange(0, 259201, 1800)):
            raise ValueError("Expected 145 radius observations at 1800-second intervals")
        self.times, self.radius_cm = a[:, 0].copy(), a[:, 1].copy()
        if (not np.isfinite(constant_radius_m) or constant_radius_m <= 0
                or np.any(self.radius_cm <= 0) or np.any(np.diff(self.radius_cm) > 0)
                or self.radius_cm[0] != 2.0 or self.radius_cm[-1] != 1.198):
            raise ValueError("Radius must be positive, nonincreasing and initially 0.02 m")
        self.method, self.tail, self.constant_radius_m = method, tail, float(constant_radius_m)
        self.breakpoints_s = self.times[1:].copy() if method != "constant" else np.empty(0)
        self.pchip = PchipInterpolator(self.times, self.radius_cm, extrapolate=False) if method == "pchip" else None

    def evaluate(self, t):
        a = np.asarray(t, dtype=float)
        if not np.isfinite(a).all() or np.any(a < 0):
            raise ValueError("Radius time must be finite and nonnegative")
        if self.method == "constant":
            values = np.full_like(a, self.constant_radius_m, dtype=float)
        else:
            if self.tail == "error" and np.any(a > self.times[-1]):
                raise ValueError("Radius requested beyond the observed interval")
            observed_t = np.minimum(a, self.times[-1])
            radius_cm = (np.interp(observed_t, self.times, self.radius_cm)
                         if self.method == "linear" else self.pchip(observed_t))
            values = radius_cm * 0.01
        if np.any(values <= 0) or not np.isfinite(values).all():
            raise ValueError("Invalid evaluated radius")
        return float(values) if np.ndim(values) == 0 else values

    def describe(self, end_time):
        return dict(method=self.method, observed_interval_s=[0, 259200],
                    continuation=self.tail,
                    continuation_used=bool(self.method != "constant" and end_time > 259200),
                    constant_radius_m=self.constant_radius_m if self.method == "constant" else None,
                    input_units="cm", internal_units="m", source_node_count=145)


def save_result(output_dir, name, payload, metadata):
    """Save unrounded fields and settings; never replace an existing calculation."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result, settings = output_dir / f"{name}.npz", output_dir / f"{name}.json"
    if result.exists() or settings.exists():
        raise FileExistsError("Choose a new output directory; results are not overwritten")
    metadata = dict(metadata, numpy=np.__version__, scipy=scipy.__version__)
    np.savez_compressed(result, **payload)
    settings.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
