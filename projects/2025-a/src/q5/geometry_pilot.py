"""Q5 common-time reachable-cloud set-cover candidate pilot.

This is S2 selection evidence, not a formal solver.  It compares the retired
centre-ray generator with surface-tube seeds under equal selected-library
budgets and checks the finite-library coverage pruning against enumeration.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.q3 import selection_pilot as q3  # noqa: E402

SPEC_ID = "Q5-GEOMETRY-CANDIDATE-PILOT-3.0"
MISSILES = np.array([[20000., 0., 2000.], [19000., 600., 2100.], [18000., -600., 1900.]])
ORIGINS = np.array([[17800., 0., 1800.], [12000., 1400., 1400.], [6000., -3000., 700.],
                    [11000., 2000., 1800.], [13000., -2000., 1300.]])
TIMES = np.arange(10., 32.01, 2.)
AGES = (0.5, 2., 5., 9., 14., 19.)
FRACTIONS = (.08, .20, .38, .58, .78, .92)
TRANSVERSE = (-8., 0., 8.)
TRACK_LIMIT = 18
EVENT_LIMIT = 9
PLAN_LIMIT = 36
BEAM_WIDTH = 1200
TOL = 1e-9


class PilotError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Event:
    platform: int
    heading: float
    speed: float
    age: float
    release: float
    fuse: float
    cloud: tuple[float, float, float]
    mask: int
    counts: tuple[int, int, int]
    label: int
    source: str


@dataclass(frozen=True)
class Track:
    platform: int
    heading: float
    speed: float
    source: str
    source_label: int
    source_surface: int


@dataclass(frozen=True)
class Plan:
    platform: int
    heading: float
    speed: float
    events: tuple[Event, ...]
    mask: int
    counts: tuple[int, int, int]
    source: str


def params():
    return q3.base_parameters()


def missile(j: int, t: float) -> np.ndarray:
    return (1. - params().missile_speed * t / np.linalg.norm(MISSILES[j])) * MISSILES[j]


def arrival(j: int) -> float:
    return float(np.linalg.norm(MISSILES[j]) / params().missile_speed)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ready(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [ready(item) for item in value]
    return value


def bits(values: np.ndarray) -> int:
    return int.from_bytes(np.packbits(values.astype(np.uint8), bitorder="little").tobytes(), "little")


class Slice:
    def __init__(self, t: float, mesh):
        self.t = t
        self.mesh = mesh
        self.missiles = np.array([missile(j, t) for j in range(3)])
        self.visible = q3.visibility_mask(self.missiles, mesh)
        self.n = len(mesh.points)
        joined = np.concatenate(self.visible)
        self.universe = bits(joined)
        self.universe_count = self.universe.bit_count()
        self.offsets = (0, self.n, 2 * self.n)

    def coverage(self, cloud: np.ndarray) -> tuple[int, tuple[int, int, int]]:
        chunks, counts = [], []
        for j in range(3):
            distance = q3._distance_to_segments(cloud.reshape(1, 3), self.missiles[j:j + 1], self.mesh)[0]
            hit = self.visible[j] & (distance <= params().smoke_radius + 1e-12)
            chunks.append(hit)
            counts.append(int(np.sum(hit)))
        return bits(np.concatenate(chunks)), tuple(counts)


def surface_representatives(mesh, method: str) -> list[tuple[int, np.ndarray]]:
    if method == "C1_center_ray":
        centre = params().target_base_center + np.array([0., 0., .5 * params().target_height])
        return [(-1, centre)]
    # Deterministic strata across side height/azimuth and top radius/azimuth.
    indices = []
    for kind in (0, 1):
        pool = np.flatnonzero(mesh.kinds == kind)
        if len(pool):
            indices.extend(pool[np.linspace(0, len(pool) - 1, 18, dtype=int)].tolist())
    return [(int(index), mesh.points[index]) for index in sorted(set(indices))]


def inverse_track(i: int, t: float, age: float, cloud: np.ndarray):
    te = t - age
    if te <= 0.:
        return None
    ez = cloud[2] + params().smoke_sink_speed * age
    low = max(0., ORIGINS[i, 2] - .5 * params().gravity * te * te)
    if not low - TOL <= ez <= ORIGINS[i, 2] + TOL:
        return None
    delta = math.sqrt(max(0., 2. * (ORIGINS[i, 2] - ez) / params().gravity))
    release = te - delta
    horizontal = cloud[:2] - ORIGINS[i, :2]
    speed = float(np.linalg.norm(horizontal) / te)
    if release < -TOL or not 70. - TOL <= speed <= 140. + TOL:
        return None
    heading = float(math.atan2(horizontal[1], horizontal[0]) % (2. * math.pi))
    return heading, min(140., max(70., speed)), max(0., release), delta


def seed_tracks(i: int, sl: Slice, method: str) -> tuple[list[Track], dict]:
    reps = surface_representatives(sl.mesh, method)
    raw, proposed, feasible = {}, 0, 0
    offsets = (0.,) if method == "C1_center_ray" else TRANSVERSE
    for j in range(3):
        m = sl.missiles[j]
        for surface_index, point in reps:
            vector = point - m
            normal_h = np.array([-vector[1], vector[0]])
            norm_h = np.linalg.norm(normal_h)
            normal_h = normal_h / norm_h if norm_h > 0. else np.zeros(2)
            for fraction, age, transverse in itertools.product(FRACTIONS, AGES, offsets):
                if age >= sl.t:
                    continue
                proposed += 1
                cloud = m + fraction * vector
                cloud[:2] += transverse * normal_h
                solved = inverse_track(i, sl.t, age, cloud)
                if solved is None:
                    continue
                feasible += 1
                heading, speed, _, _ = solved
                key = (round(heading / .004), round(speed / .5))
                candidate = Track(i, heading, speed, method, j, surface_index)
                # Round-robin source identity later preserves all missiles and surfaces.
                raw.setdefault(key, candidate)
    ordered = sorted(raw.values(), key=lambda x: (x.source_label, x.source_surface, x.heading, x.speed))
    chosen, used = [], set()
    for phase in range(3):
        for track in ordered:
            stratum = (track.source_label, track.source_surface % 6 if track.source_surface >= 0 else -1)
            if phase == 0 and stratum in used:
                continue
            chosen.append(track)
            used.add(stratum)
            if len(chosen) >= TRACK_LIMIT:
                break
        if len(chosen) >= TRACK_LIMIT:
            break
    return chosen, {"proposed": proposed, "kinematically_feasible": feasible,
                    "unique_tracks": len(raw), "selected_tracks": len(chosen)}


def event_library(track: Track, sl: Slice) -> tuple[list[Event], dict]:
    candidates = {}
    h = np.array([math.cos(track.heading), math.sin(track.heading)])
    surface_ids = np.linspace(0, len(sl.mesh.points) - 1, 16, dtype=int)
    proposed = 0
    for age in AGES:
        te = sl.t - age
        if te <= 0.:
            continue
        cloud_h = ORIGINS[track.platform, :2] + track.speed * te * h
        low_ez = max(0., ORIGINS[track.platform, 2] - .5 * params().gravity * te * te)
        for j in range(3):
            m = sl.missiles[j]
            for sid in surface_ids:
                point = sl.mesh.points[sid]
                dh = point[:2] - m[:2]
                den = float(dh @ dh)
                lam = float(np.clip(((cloud_h - m[:2]) @ dh) / den, 0., 1.)) if den > 0. else 0.
                horizontal_near = m[:2] + lam * dh
                if np.linalg.norm(cloud_h - horizontal_near) > params().smoke_radius + 2.:
                    continue
                line_z = float(m[2] + lam * (point[2] - m[2]))
                for dz in (-6., 0., 6.):
                    proposed += 1
                    cloud_z = line_z + dz
                    ez = cloud_z + params().smoke_sink_speed * age
                    if not low_ez - TOL <= ez <= ORIGINS[track.platform, 2] + TOL:
                        continue
                    delta = math.sqrt(max(0., 2. * (ORIGINS[track.platform, 2] - ez) / params().gravity))
                    release = te - delta
                    if release < -TOL:
                        continue
                    cloud = np.array([cloud_h[0], cloud_h[1], cloud_z])
                    mask, counts = sl.coverage(cloud)
                    if mask == 0:
                        continue
                    label = int(np.argmax(counts))
                    event = Event(track.platform, track.heading, track.speed, age, max(0., release), delta,
                                  tuple(float(v) for v in cloud), mask, counts, label, track.source)
                    key = (round(event.release / .05), round(event.fuse / .05))
                    old = candidates.get(key)
                    if old is None or event.mask.bit_count() > old.mask.bit_count():
                        candidates[key] = event
    ordered = sorted(candidates.values(), key=lambda e: (e.mask.bit_count(), min(e.counts), -e.release), reverse=True)
    selected, union = [], 0
    while ordered and len(selected) < EVENT_LIMIT:
        event = max(ordered, key=lambda e: ((e.mask & ~union).bit_count(), e.mask.bit_count(), min(e.counts)))
        selected.append(event)
        union |= event.mask
        ordered.remove(event)
    return selected, {"proposed_vertical_states": proposed, "useful_events": len(candidates),
                      "selected_events": len(selected)}


def plans_for_platform(i: int, sl: Slice, method: str) -> tuple[list[Plan], dict]:
    tracks, track_stats = seed_tracks(i, sl, method)
    plans, event_stats = [], []
    for track in tracks:
        events, stats = event_library(track, sl)
        event_stats.append(stats)
        for size in range(1, min(3, len(events)) + 1):
            for group in itertools.combinations(events, size):
                ordered = tuple(sorted(group, key=lambda e: e.release))
                if any(v.release - u.release < 1. - TOL for u, v in zip(ordered[:-1], ordered[1:])):
                    continue
                mask = 0
                counts = [0, 0, 0]
                for event in ordered:
                    mask |= event.mask
                for j in range(3):
                    lo, hi = j * sl.n, (j + 1) * sl.n
                    counts[j] = ((mask >> lo) & ((1 << sl.n) - 1)).bit_count()
                plans.append(Plan(i, track.heading, track.speed, ordered, mask, tuple(counts), method))
    # Keep strong and complementary plans; mask identity removes exact duplicates.
    best_by_mask = {}
    for plan in plans:
        old = best_by_mask.get(plan.mask)
        if old is None or len(plan.events) < len(old.events):
            best_by_mask[plan.mask] = plan
    pool = list(best_by_mask.values())
    selected, union = [], 0
    while pool and len(selected) < PLAN_LIMIT:
        plan = max(pool, key=lambda p: ((p.mask & ~union).bit_count(), p.mask.bit_count(), min(p.counts), -len(p.events)))
        selected.append(plan)
        union |= plan.mask
        pool.remove(plan)
    selected.append(Plan(i, 0., 70., (), 0, (0, 0, 0), method + "_empty"))
    return selected, {"track": track_stats, "event": event_stats, "raw_plans": len(plans),
                      "unique_plan_masks": len(best_by_mask), "selected_plans": len(selected)}


def combine(libraries: list[list[Plan]], universe: int):
    future = [0] * (len(libraries) + 1)
    for level in range(len(libraries) - 1, -1, -1):
        future[level] = future[level + 1]
        for plan in libraries[level]:
            future[level] |= plan.mask
    states = [(0, ())]
    pruned = 0
    for level, library in enumerate(libraries):
        expanded = []
        for mask, chosen in states:
            for plan in library:
                new = mask | plan.mask
                if ((new | future[level + 1]) & universe) != universe:
                    pruned += 1
                    continue
                expanded.append((new, chosen + (plan,)))
        dedup = {}
        for mask, chosen in expanded:
            old = dedup.get(mask)
            if old is None or sum(len(p.events) for p in chosen) < sum(len(p.events) for p in old):
                dedup[mask] = chosen
        states = [(mask, chosen) for mask, chosen in dedup.items()]
        states.sort(key=lambda x: (x[0] == universe, x[0].bit_count(), -sum(len(p.events) for p in x[1])), reverse=True)
        states = states[:BEAM_WIDTH]
        if not states:
            break
    complete = [(mask, chosen) for mask, chosen in states if (mask & universe) == universe]
    return complete, states[:5], pruned


def pruning_oracle() -> dict:
    libraries = [[1, 2, 4], [3, 8], [4, 8, 16]]
    universe = 15
    exhaustive = {choice for choice in itertools.product(*[range(len(x)) for x in libraries])
                  if ((libraries[0][choice[0]] | libraries[1][choice[1]] |
                       libraries[2][choice[2]]) & universe) == universe}
    suffix = [0] * 4
    for level in range(2, -1, -1):
        suffix[level] = suffix[level + 1]
        for mask in libraries[level]:
            suffix[level] |= mask
    kept = set()
    def visit(level, mask, choice):
        if ((mask | suffix[level]) & universe) != universe:
            return
        if level == 3:
            if (mask & universe) == universe:
                kept.add(choice)
            return
        for index, value in enumerate(libraries[level]):
            visit(level + 1, mask | value, choice + (index,))
    visit(0, 0, ())
    return {"exhaustive_complete": len(exhaustive), "pruned_complete": len(kept),
            "same_complete_set": exhaustive == kept}


def run(output: Path) -> dict:
    started = time.perf_counter()
    mesh = q3.surface_mesh(24, 5)
    comparison = {}
    for method in ("C1_center_ray", "C3_surface_tube"):
        slices, complete_records = [], []
        for t in TIMES:
            if t >= min(arrival(j) for j in range(3)):
                continue
            sl = Slice(float(t), mesh)
            libraries, stats = [], []
            for i in range(5):
                plans, record = plans_for_platform(i, sl, method)
                libraries.append(plans)
                stats.append(record)
            complete, near, pruned = combine(libraries, sl.universe)
            partial_events = {e for library in libraries for plan in library for e in plan.events
                              if all(count < int(np.sum(sl.visible[j])) for j, count in enumerate(e.counts))}
            record = {"time_s": float(t), "universe_bits": sl.universe_count,
                      "complete_combination_count_after_beam": len(complete),
                      "best_coverage_bits": complete[0][0].bit_count() if complete else (near[0][0].bit_count() if near else 0),
                      "pruned_branch_count": pruned, "partial_only_event_count": len(partial_events),
                      "platform_stats": stats}
            slices.append(record)
            if complete:
                complete_records.append({"time_s": float(t), "plans": [asdict(p) for p in complete[0][1]]})
        comparison[method] = {"slice_count": len(slices),
                              "complete_timeslice_hit_count": sum(r["complete_combination_count_after_beam"] > 0 for r in slices),
                              "partial_only_event_count": sum(r["partial_only_event_count"] for r in slices),
                              "best_coverage_ratio": max((r["best_coverage_bits"] / r["universe_bits"] for r in slices), default=0.),
                              "slices": slices, "complete_examples": complete_records[:3]}
    oracle = pruning_oracle()
    c1, c3 = comparison["C1_center_ray"], comparison["C3_surface_tube"]
    result = {"schema_version": "1.0", "spec_id": SPEC_ID, "status": "working_selection_evidence",
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "role": "S2 candidate comparison only; no formal Q5 result",
              "budget": {"times_s": TIMES, "mesh_theta": 24, "mesh_levels": 5, "track_limit": TRACK_LIMIT,
                         "event_limit": EVENT_LIMIT, "plan_limit": PLAN_LIMIT, "beam_width": BEAM_WIDTH},
              "comparison": comparison, "pruning_oracle": oracle,
              "admission": {"surface_tube_has_more_partial_candidates": c3["partial_only_event_count"] > c1["partial_only_event_count"],
                            "surface_tube_coverage_not_worse": c3["best_coverage_ratio"] + 1e-12 >= c1["best_coverage_ratio"],
                            "pruning_oracle_pass": oracle["same_complete_set"]},
              "identity": {"official_input_sha256": sha(ROOT / "data/A题.pdf"),
                           "candidate_document_sha256": sha(ROOT / "planning/29_q5_candidate_set.md"),
                           "pilot_source_sha256": sha(Path(__file__))},
              "software": {"python": platform.python_version(), "numpy": np.__version__},
              "elapsed_s": time.perf_counter() - started,
              "claims": {"formal_solution": False, "continuous_domain_complete": False,
                         "centre_ray_complete": False, "same_platform_release_gap_enforced": True}}
    if not all(result["admission"].values()):
        raise PilotError("Q5_GEOMETRY_CANDIDATE_ADMISSION_FAILURE", json.dumps(result["admission"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ready(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/q5_geometry_pilot.json")
    args = parser.parse_args()
    try:
        result = run(args.output.resolve())
    except PilotError as exc:
        print(json.dumps({"status": "fail", "code": exc.code, "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "pass", "admission": result["admission"],
                      "elapsed_s": result["elapsed_s"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
