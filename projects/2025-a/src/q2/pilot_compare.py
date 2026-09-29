"""Frozen Q2 small-scale model-family selection experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.special import expit
from scipy.stats import qmc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
import model as q1  # noqa: E402

SPEC_PATH = Path("planning/10_q2_model_spec_and_selection.md")
SPEC_SHA = "262fd553e083d0ee19d737dcc2c09f48fcec77a147b27ae4f013e3f6053b2e8d"
INPUT_SHA = "a37f6aad30b16ea09da9cb320ce194b12d3a28874008cf9ff19549f6c6079447"
SEEDS = [250827, 250828, 250829]
N_PROPOSAL, N_SCREEN, N_PRECISE, C3_LIMIT = 256, 6, 1, 4096
HALF_WIDTH = 0.18
PROXY = {"time_count": 41, "n_theta": 64, "logistic_scale_m": 2.0}
SCREEN = {"scan_step_s": 0.02, "n_theta": 128}
PRECISE = {"scan_step_s": 0.005, "n_theta": 512}


class PilotError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Decision:
    heading_rad: float
    speed_mps: float
    release_time_s: float
    fuse_delay_s: float
    source_domain: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ready(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [ready(item) for item in value]
    return value


def arrival(p: q1.Q1Parameters) -> float:
    return float(np.linalg.norm(p.missile_initial) / p.missile_speed)


def parameters(x: Decision) -> q1.Q1Parameters:
    p = q1.default_parameters()
    direction = np.array([math.cos(x.heading_rad), math.sin(x.heading_rad), 0.0])
    return replace(p, uav_speed=x.speed_mps, uav_direction=direction,
                   release_time=x.release_time_s, fuse_delay=x.fuse_delay_s)


def decision_record(x: Decision) -> dict:
    p = parameters(x)
    info = q1.kinematics(p)
    return {
        **asdict(x), "heading_unit": p.uav_direction.tolist(),
        "release_point_m": ready(info["release_point_m"]),
        "explosion_time_s": float(info["explosion_time_s"]),
        "explosion_point_m": ready(info["explosion_point_m"]),
        "active_window_s": ready(info["active_window_s"]),
    }


def time_map(u_delta: float, u_time: float, p: q1.Q1Parameters) -> tuple[float, float]:
    delta_max = math.sqrt(2.0 * p.uav_initial[2] / p.gravity)
    delta = float(u_delta * delta_max)
    te = float(delta + u_time * (arrival(p) - delta))
    return te - delta, delta


def generate_c0(seed: int) -> tuple[list[Decision], dict]:
    p = q1.default_parameters()
    sample = qmc.LatinHypercube(d=4, seed=seed).random(N_PROPOSAL)
    values = []
    for row in sample:
        release, fuse = time_map(row[2], row[3], p)
        values.append(Decision(float(2 * math.pi * row[0]), float(70 + 70 * row[1]),
                               release, fuse, "full_domain"))
    return values, {"attempts": N_PROPOSAL, "inverse_failures": 0}


def generate_c2(seed: int) -> tuple[list[Decision], dict]:
    p = q1.default_parameters()
    sample = qmc.LatinHypercube(d=5, seed=seed).random(N_PROPOSAL)
    target = p.target_base_center[:2] - p.uav_initial[:2]
    missile = p.missile_initial[:2] - p.uav_initial[:2]
    a_target = math.atan2(float(target[1]), float(target[0]))
    a_missile = math.atan2(float(missile[1]), float(missile[0]))
    values, counts = [], {"target": 0, "missile": 0, "guard": 0}
    for row in sample:
        if row[0] < 0.45:
            domain, angle = "target", a_target + (2 * row[1] - 1) * HALF_WIDTH
        elif row[0] < 0.90:
            domain, angle = "missile", a_missile + (2 * row[1] - 1) * HALF_WIDTH
        else:
            domain, angle = "guard", 2 * math.pi * row[1]
        release, fuse = time_map(row[3], row[4], p)
        values.append(Decision(float(angle % (2 * math.pi)), float(70 + 70 * row[2]),
                               release, fuse, domain))
        counts[domain] += 1
    return values, {"attempts": N_PROPOSAL, "inverse_failures": 0,
                    "domain_counts": counts, "target_center_rad": a_target,
                    "missile_center_rad": a_missile, "half_width_rad": HALF_WIDTH}


def generate_c3(seed: int) -> tuple[list[Decision], dict]:
    p, rng = q1.default_parameters(), np.random.default_rng(seed)
    center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    values, attempts = [], 0
    reasons = {"bad_height": 0, "negative_release": 0, "bad_speed": 0,
               "zero_explosion_time": 0}
    while len(values) < N_PROPOSAL and attempts < C3_LIMIT:
        attempts += 1
        t_obs = float(rng.uniform(0.0, arrival(p)))
        age = float(rng.uniform(0.0, min(p.smoke_duration, t_obs)))
        te, fraction = t_obs - age, float(rng.uniform(0.0, 1.0))
        if te <= 1e-12:
            reasons["zero_explosion_time"] += 1
            continue
        missile = q1.missile_position(t_obs, p)
        cloud = missile + fraction * (center - missile)
        explosion = cloud + np.array([0.0, 0.0, p.smoke_sink_speed * age])
        if not 0.0 <= explosion[2] <= p.uav_initial[2]:
            reasons["bad_height"] += 1
            continue
        fuse = math.sqrt(2 * (p.uav_initial[2] - float(explosion[2])) / p.gravity)
        release = te - fuse
        if release < 0:
            reasons["negative_release"] += 1
            continue
        displacement = explosion[:2] - p.uav_initial[:2]
        speed = float(np.linalg.norm(displacement) / te)
        if not 70 <= speed <= 140:
            reasons["bad_speed"] += 1
            continue
        values.append(Decision(float(math.atan2(displacement[1], displacement[0]) % (2 * math.pi)),
                               speed, release, fuse, "explosion_state_inverse"))
    status = "pass" if len(values) == N_PROPOSAL else "Q2_PILOT_INVERSE_INSUFFICIENT"
    return values, {"attempts": attempts, "inverse_failures": attempts - len(values),
                    "failure_reasons": reasons, "inverse_success_rate": len(values) / attempts,
                    "status": status}


def proxy_score(x: Decision) -> float:
    p = parameters(x)
    start, stop = map(float, q1.kinematics(p)["active_window_s"])
    times = np.linspace(start, stop, PROXY["time_count"])
    margins = np.array([q1.dense_margin(float(t), p, PROXY["n_theta"])["margin_m"]
                        for t in times])
    return float(np.trapezoid(expit(-margins / PROXY["logistic_scale_m"]), times))


def evaluate(x: Decision, settings: dict) -> dict:
    try:
        result = q1.solve_intervals(parameters(x), scan_step=settings["scan_step_s"],
                                    n_theta=settings["n_theta"])
    except Exception as error:
        raise PilotError("Q2_PILOT_EVALUATOR_FAILURE", str(error)) from error
    duration = float(result["effective_duration_s"])
    if not math.isfinite(duration):
        raise PilotError("Q2_PILOT_EVALUATOR_FAILURE", "non-finite duration")
    return {"effective_duration_s": duration, "intervals_s": ready(result["intervals_s"]),
            "minimum_scan_margin_m": float(result["minimum_scan_margin_m"]),
            "root_residuals": ready(result["root_residuals"]), "settings": settings}


def run_one(method: str, seed: int) -> dict:
    started = time.perf_counter()
    candidates, generation = {"C0": generate_c0, "C2": generate_c2,
                              "C3": generate_c3}[method](seed)
    if len(candidates) < N_PROPOSAL:
        return {"method": method, "seed": seed, "status": "disqualified",
                "failure_code": "Q2_PILOT_INVERSE_INSUFFICIENT",
                "generation": generation, "proposal_count": len(candidates),
                "proxy_seconds": 0.0, "screen_calls": 0,
                "first_positive_screen_call": None, "positive_screen_count": 0,
                "screen_records": [], "precise_calls": 0, "precise_finalist": None,
                "elapsed_seconds": time.perf_counter() - started}
    proxy_started = time.perf_counter()
    scored = [(proxy_score(x), index, x) for index, x in enumerate(candidates)]
    proxy_seconds = time.perf_counter() - proxy_started
    finalists = sorted(scored, key=lambda item: (-item[0], item[1]))[:N_SCREEN]
    screen, first_positive = [], None
    for call, (score, index, x) in enumerate(finalists, 1):
        result = evaluate(x, SCREEN)
        if first_positive is None and result["effective_duration_s"] > 1e-9:
            first_positive = call
        screen.append({"call_index": call, "proposal_index": index, "proxy_score_s": score,
                       "decision": decision_record(x), "continuous_screen": result})
    best = max(screen, key=lambda item: (item["continuous_screen"]["effective_duration_s"],
                                         item["proxy_score_s"]))
    keys = ("heading_rad", "speed_mps", "release_time_s", "fuse_delay_s", "source_domain")
    winner = Decision(**{key: best["decision"][key] for key in keys})
    precise = evaluate(winner, PRECISE)
    return {"method": method, "seed": seed, "status": "completed", "generation": generation,
            "proposal_count": len(candidates), "proxy_seconds": proxy_seconds,
            "screen_calls": N_SCREEN, "first_positive_screen_call": first_positive,
            "positive_screen_count": sum(item["continuous_screen"]["effective_duration_s"] > 1e-9
                                         for item in screen), "screen_records": screen,
            "precise_calls": N_PRECISE,
            "precise_finalist": {"decision": best["decision"],
                                  "proxy_score_s": best["proxy_score_s"],
                                  "screen_duration_s": best["continuous_screen"]["effective_duration_s"],
                                  "precise": precise},
            "elapsed_seconds": time.perf_counter() - started}


def aggregate(records: list[dict]) -> dict:
    summary = {}
    for method in ("C0", "C2", "C3"):
        chosen = [item for item in records if item["method"] == method]
        completed = [item for item in chosen if item["status"] == "completed"]
        durations = np.array([item["precise_finalist"]["precise"]["effective_duration_s"]
                              for item in completed])
        positives = sum(item["positive_screen_count"] for item in chosen)
        screen_calls = sum(item["screen_calls"] for item in chosen)
        summary[method] = {
            "positive_seed_count": int(np.sum(durations > 1e-9)) if durations.size else 0,
            "precise_duration_median_s": float(np.median(durations)) if durations.size else 0.0,
            "precise_duration_best_s": float(np.max(durations)) if durations.size else 0.0,
            "precise_duration_std_s": float(np.std(durations)) if durations.size else 0.0,
            "precise_durations_s": durations.tolist(),
            "completed_seed_count": len(completed),
            "disqualified_seed_count": len(chosen) - len(completed),
            "positive_screen_count": int(positives),
            "screen_call_count": int(screen_calls),
            "screen_positive_rate": float(positives / screen_calls) if screen_calls else 0.0,
            "inverse_failures": int(sum(item["generation"]["inverse_failures"] for item in chosen)),
            "elapsed_seconds": float(sum(item["elapsed_seconds"] for item in chosen)),
        }
    return summary


def select(summary: dict) -> tuple[str, str]:
    ranking = sorted(summary, key=lambda key: (summary[key]["positive_seed_count"],
                     summary[key]["precise_duration_median_s"],
                     summary[key]["precise_duration_best_s"]), reverse=True)
    winner, second = ranking[:2]
    a, b = summary[winner], summary[second]
    status = "pass"
    if a["positive_seed_count"] == b["positive_seed_count"] and \
       a["precise_duration_median_s"] - b["precise_duration_median_s"] <= 1e-4 and \
       a["precise_duration_best_s"] - b["precise_duration_best_s"] <= 1e-4:
        status = "Q2_PILOT_INCONCLUSIVE"
    return winner, status


def report_text(result: dict) -> str:
    rows = []
    for method in ("C0", "C2", "C3"):
        item = result["aggregate"][method]
        rows.append(f"| {method} | {item['positive_seed_count']}/3 | "
                    f"{item['positive_screen_count']}/{item['screen_call_count']} | "
                    f"{item['precise_duration_median_s']:.9f} | "
                    f"{item['precise_duration_best_s']:.9f} | "
                    f"{item['precise_duration_std_s']:.3e} | {item['inverse_failures']} |")
    return f"""# Q2 小规模模型族选择试验

> 内部技术证据；不是 Q2 正式最优解，不引用或展示外部数值结果。运行绑定 `SPEC-Q2-1.0-PILOT`。

## 公平条件

- 候选为 C0 原变量全域基线、C2 物理分域混合、C3 起爆状态几何反解。
- 固定种子 `{SEEDS}`；每族每种子 256 个代理候选、6 次连续目标筛选、1 次统一加密复算。
- 三类候选使用完全相同的代理与连续目标设置，比较量始终为完整圆柱连续遮蔽区间测度。

## 结果

| 候选 | 精算正值种子 | 筛选正值 | 精算中位时长/s | 精算最佳时长/s | 跨种子标准差/s | 回代失败 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

按冻结的“正值种子数→中位时长→最佳时长”顺序，本次建议为 **{result['recommendation']['method']}**，判定状态 `{result['recommendation']['status']}`。

## 解释边界

本试验只回答小而相同的预算下，哪种参数化更容易穿越零平台并产生稳定高质量点；不证明全局最优，也不替代正式多启动优化。完整未舍入参数、区间、余量残差和逐次调用保存在 `{result['output_path']}`。
"""


def run(output: Path, report: Path) -> dict:
    if sha256(ROOT / SPEC_PATH) != SPEC_SHA or sha256(ROOT / "data/A题.pdf") != INPUT_SHA:
        raise PilotError("Q2_PILOT_IDENTITY_MISMATCH", "frozen specification or input changed")
    records = []
    for seed in SEEDS:
        for method in ("C0", "C2", "C3"):
            print(json.dumps({"stage": "pilot", "method": method, "seed": seed,
                              "status": "started"}), flush=True)
            item = run_one(method, seed)
            records.append(item)
            print(json.dumps({"stage": "pilot", "method": method, "seed": seed,
                              "status": "completed",
                              "run_status": item["status"],
                              "precise_duration_s": (item["precise_finalist"]["precise"]["effective_duration_s"]
                                                     if item["precise_finalist"] else None),
                              "elapsed_seconds": item["elapsed_seconds"]}), flush=True)
    summary = aggregate(records)
    method, status = select(summary)
    if all(item["positive_seed_count"] == 0 for item in summary.values()):
        status = "Q2_PILOT_ALL_ZERO"
    script = ROOT / "src/q2/pilot_compare.py"
    result = {"schema_version": "1.0", "result_id": "Q2-SPEC-Q2-1.0-PILOT-SELECTION",
              "status": "ok" if status in {"pass", "Q2_PILOT_INCONCLUSIVE"} else "fail",
              "claim_id": "A.Q2.SELECTION_PILOT.001",
              "purpose": "internal_model_family_selection_not_formal_q2_solution",
              "spec_identity": SPEC_SHA, "official_input_identity": INPUT_SHA,
              "budget": {"seeds": SEEDS, "proposals_per_method_seed": N_PROPOSAL,
                         "screen_calls_per_method_seed": N_SCREEN,
                         "precise_calls_per_method_seed": N_PRECISE,
                         "c3_attempt_limit": C3_LIMIT, "proxy": PROXY,
                         "screen": SCREEN, "precise": PRECISE},
              "records": records, "aggregate": summary,
              "recommendation": {"method": method, "status": status},
              "limitations": ["Small fixed budget supports model-family selection only.",
                              "No strict global-optimality claim is made.",
                              "External numerical results were neither loaded nor compared."],
              "run_identity": {"executed_at": datetime.now(timezone.utc).isoformat(),
                               "execution_kind": "declared_stochastic_repeated_fixed_seeds",
                               "python": platform.python_version(), "numpy": np.__version__,
                               "scipy": scipy.__version__, "seeds": SEEDS,
                               "script_sha256": sha256(script),
                               "q1_model_sha256": sha256(ROOT / "src/q1/model.py"),
                               "spec_sha256": SPEC_SHA, "official_input_sha256": INPUT_SHA},
              "output_path": output.as_posix()}
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write_text(report_text(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(ROOT / args.output, ROOT / args.report)
    except PilotError as error:
        print(json.dumps({"status": "fail", "failure_code": error.code,
                          "message": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result["status"], "recommendation": result["recommendation"],
                      "aggregate": result["aggregate"], "output": args.output.as_posix(),
                      "report": args.report.as_posix()}, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
