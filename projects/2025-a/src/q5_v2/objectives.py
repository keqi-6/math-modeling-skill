"""Authoritative interval algebra and objective semantics for Q5_v2.

All durations are physical seconds except ``j_sum_missile_s``, which is the
sum of three per-missile union measures and therefore has unit missile-second.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence


Interval = tuple[float, float]


def normalize_intervals(
    intervals: Iterable[Sequence[float]], *, tolerance_s: float = 1e-10
) -> tuple[Interval, ...]:
    """Validate, sort, and union closed time intervals.

    Degenerate intervals have zero measure and are discarded.  Intervals whose
    gap is no larger than ``tolerance_s`` are merged; the tolerance is numerical
    only and is never added to the reported duration.
    """

    if not math.isfinite(tolerance_s) or tolerance_s < 0:
        raise ValueError("tolerance_s must be finite and nonnegative")
    checked: list[Interval] = []
    for raw in intervals:
        if len(raw) != 2:
            raise ValueError("each interval must contain exactly two endpoints")
        left, right = float(raw[0]), float(raw[1])
        if not math.isfinite(left) or not math.isfinite(right):
            raise ValueError("interval endpoints must be finite")
        if right < left - tolerance_s:
            raise ValueError(f"reversed interval: {(left, right)}")
        if right - left <= tolerance_s:
            continue
        checked.append((left, right))
    checked.sort()

    merged: list[list[float]] = []
    for left, right in checked:
        if not merged or left > merged[-1][1] + tolerance_s:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    return tuple((float(left), float(right)) for left, right in merged)


def interval_measure(intervals: Iterable[Sequence[float]]) -> float:
    """Return the measure of an interval union without double counting."""

    return float(sum(right - left for left, right in normalize_intervals(intervals)))


def intersect_two(
    left_intervals: Iterable[Sequence[float]],
    right_intervals: Iterable[Sequence[float]],
    *,
    tolerance_s: float = 1e-10,
) -> tuple[Interval, ...]:
    """Intersect two normalized interval unions."""

    left = normalize_intervals(left_intervals, tolerance_s=tolerance_s)
    right = normalize_intervals(right_intervals, tolerance_s=tolerance_s)
    out: list[Interval] = []
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if end - start > tolerance_s:
            out.append((start, end))
        if left[i][1] < right[j][1] - tolerance_s:
            i += 1
        elif right[j][1] < left[i][1] - tolerance_s:
            j += 1
        else:
            i += 1
            j += 1
    return normalize_intervals(out, tolerance_s=tolerance_s)


def intersect_many(
    interval_sets: Sequence[Iterable[Sequence[float]]],
    *,
    tolerance_s: float = 1e-10,
) -> tuple[Interval, ...]:
    """Intersect one or more interval unions."""

    if not interval_sets:
        raise ValueError("at least one interval set is required")
    common = normalize_intervals(interval_sets[0], tolerance_s=tolerance_s)
    for intervals in interval_sets[1:]:
        common = intersect_two(common, intervals, tolerance_s=tolerance_s)
        if not common:
            break
    return common


def _longest_component(intervals: Sequence[Interval]) -> tuple[Interval | None, float]:
    if not intervals:
        return None, 0.0
    longest = max(intervals, key=lambda interval: interval[1] - interval[0])
    return longest, float(longest[1] - longest[0])


@dataclass(frozen=True)
class ObjectiveMetrics:
    """The four Q5_v2 metrics computed from three strict interval unions."""

    per_missile_intervals_s: tuple[tuple[Interval, ...], ...]
    per_missile_duration_s: tuple[float, ...]
    intersection_intervals_s: tuple[Interval, ...]
    longest_all_interval_s: Interval | None
    j_sum_missile_s: float
    j_fair_s: float
    j_all_s: float
    l_all_s: float

    @property
    def official_lexicographic_key(self) -> tuple[float, float, float, float]:
        """Primary题意 hierarchy: J_sum, J_fair, J_all, then L_all."""

        return (self.j_sum_missile_s, self.j_fair_s, self.j_all_s, self.l_all_s)

    @property
    def pareto_vector(self) -> tuple[float, float, float, float]:
        return self.official_lexicographic_key

    def as_dict(self) -> dict[str, object]:
        return {
            "per_missile_intervals_s": [list(map(list, intervals)) for intervals in self.per_missile_intervals_s],
            "per_missile_duration_s": list(self.per_missile_duration_s),
            "intersection_intervals_s": list(map(list, self.intersection_intervals_s)),
            "longest_all_interval_s": None if self.longest_all_interval_s is None else list(self.longest_all_interval_s),
            "j_sum_missile_s": self.j_sum_missile_s,
            "j_fair_s": self.j_fair_s,
            "j_all_s": self.j_all_s,
            "l_all_s": self.l_all_s,
            "units": {
                "j_sum_missile_s": "missile*s",
                "j_fair_s": "s",
                "j_all_s": "s",
                "l_all_s": "s",
            },
        }


def from_interval_sets(
    by_missile: Sequence[Iterable[Sequence[float]]],
    *,
    tolerance_s: float = 1e-10,
) -> ObjectiveMetrics:
    """Compute all Q5_v2 objectives from exactly three missile interval sets."""

    if len(by_missile) != 3:
        raise ValueError("Q5_v2 requires exactly three missile interval sets")
    normalized = tuple(
        normalize_intervals(intervals, tolerance_s=tolerance_s) for intervals in by_missile
    )
    durations = tuple(float(sum(right - left for left, right in intervals)) for intervals in normalized)
    common = intersect_many(normalized, tolerance_s=tolerance_s)
    longest, longest_duration = _longest_component(common)
    return ObjectiveMetrics(
        per_missile_intervals_s=normalized,
        per_missile_duration_s=durations,
        intersection_intervals_s=common,
        longest_all_interval_s=longest,
        j_sum_missile_s=float(sum(durations)),
        j_fair_s=float(min(durations)),
        j_all_s=float(sum(right - left for left, right in common)),
        l_all_s=longest_duration,
    )


def from_q5_evaluation(
    evaluation: Mapping[str, object], *, consistency_tolerance_s: float = 2e-7
) -> ObjectiveMetrics:
    """Re-score an existing strict Q5 evaluation under Q5_v2 semantics.

    Existing aggregate fields, when present, are checked rather than trusted.
    This prevents an old ranking objective from silently redefining Q5_v2.
    """

    records = evaluation.get("by_missile")
    if not isinstance(records, Sequence) or len(records) != 3:
        raise ValueError("evaluation.by_missile must contain three records")
    interval_sets = []
    for record in records:
        if not isinstance(record, Mapping) or "intervals_s" not in record:
            raise ValueError("each missile record must contain intervals_s")
        interval_sets.append(record["intervals_s"])
    metrics = from_interval_sets(interval_sets)

    checks = {
        "sum_duration_missile_s": metrics.j_sum_missile_s,
        "minimum_missile_duration_s": metrics.j_fair_s,
        "total_intersection_s": metrics.j_all_s,
        "longest_continuous_s": metrics.l_all_s,
    }
    for field, expected in checks.items():
        if field in evaluation:
            observed = float(evaluation[field])
            if abs(observed - expected) > consistency_tolerance_s:
                raise ValueError(
                    f"inconsistent {field}: observed={observed}, recomputed={expected}"
                )
    return metrics


def lexicographic_better(
    candidate: ObjectiveMetrics,
    incumbent: ObjectiveMetrics,
    *,
    tolerance: float = 1e-9,
) -> bool:
    """Compare the official hierarchy without cumulative primary loss."""

    if tolerance < 0 or not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite and nonnegative")
    for candidate_value, incumbent_value in zip(
        candidate.official_lexicographic_key, incumbent.official_lexicographic_key
    ):
        if candidate_value > incumbent_value + tolerance:
            return True
        if candidate_value < incumbent_value - tolerance:
            return False
    return False


def pareto_dominates(
    candidate: ObjectiveMetrics,
    other: ObjectiveMetrics,
    *,
    tolerance: float = 1e-9,
) -> bool:
    """Return whether candidate weakly improves all four metrics and one strictly."""

    if tolerance < 0 or not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite and nonnegative")
    pairs = tuple(zip(candidate.pareto_vector, other.pareto_vector))
    return all(left >= right - tolerance for left, right in pairs) and any(
        left > right + tolerance for left, right in pairs
    )
