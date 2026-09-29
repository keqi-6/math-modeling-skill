"""Cross-evaluate the published A196 Q3 strategy with the project evaluator.

This is an internal-regression diagnostic, not a formal Q3 candidate source.
The paper's table-5 coordinates are used to reconstruct the physical controls;
the inconsistent prose heading is evaluated separately instead of silently
choosing one of the two published values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q3"))
import selection_pilot as pilot  # noqa: E402


SOURCE = {
    "paper_id": "A196",
    "role": "internal_regression_candidate_hint",
    "official_display_url": "https://dxs.moe.gov.cn/zx/a/hd_sxjm_sxjmlw_2025qgdxssxjmjslwzs_2025atlw/251101/2022729.shtml?source=hd_sxjm_sxjmlw",
    "archive_pdf_url": "https://github.com/yushugulao/CUMCM-Archive/blob/main/%E7%AB%9E%E8%B5%9B%E8%B5%84%E6%96%99/2025/A/%E4%BC%98%E7%A7%80%E8%AE%BA%E6%96%87/A196.pdf",
    "location": "section 8.2.2, table 5, PDF page 24; appendix fr_third.m, PDF pages 50-63",
}

PUBLISHED = {
    "reported_joint_duration_s": 6.93586,
    "reported_heading_deg": 13.57377,
    "reported_speed_mps": 116.81318,
    "release_points_m": [
        [17800.0, 0.0, 1800.0],
        [17915.99463, 13.80460, 1800.0],
        [22048.21768, 505.58318, 1800.0],
    ],
    "explosion_points_m": [
        [17800.0, 0.0, 1800.0],
        [17915.99463, 13.80460, 1800.0],
        [23913.0268, 727.51534, 533.54687],
    ],
    "reported_effective_time_s": [0.79116, 1.0, 0.0],
    "reported_failure_time_s": [5.41117, 5.07793, 0.0],
    "reported_attributed_duration_s": [2.55600, 4.37985, 0.0],
    "paper_sampling": {
        "declared_sample_num": 250,
        "generated_heights": 5,
        "circumference_samples_per_height": 125,
        "generated_point_count": 625,
        "downstream_loop_point_count": 250,
        "effectively_checked_heights_m": [0.0, 2.5],
        "end_cap_interiors": False,
        "all_circumference_points_checked": True,
        "joint_logic": "intersection_over_points(union_over_three_clouds)",
        "implementation_defect": "The array grows to 625 points, but downstream loops retain sample_num=250 and therefore use only the first two height rings.",
    },
}

GEOMETRY_REDUCTION_PLAN = {
    "status": "working_design_not_frozen",
    "missile_x_speed_mps": 298.511157062997,
    "rigorous_safe_bounds": {
        "any_coverage_service_time_upper_s": 13.942236249791,
        "coverage_service_time_upper_when_cos_heading_nonnegative_s": 7.403408374226,
        "true_three_cloud_each_explosion_time_upper_s": 13.942236249791,
        "true_three_cloud_each_release_time_upper_s": 13.942236249791,
        "true_three_cloud_each_fuse_delay_upper_s": 13.942236249791,
        "essential_cloud_xy_box_at_service_time": [
            "-17 <= cloud_x <= missile_x(t)+10",
            "-10 <= cloud_y <= 217",
        ],
        "essential_cloud_z_box_at_service_time": "-10 <= cloud_z <= missile_z(t)+10",
        "true_three_negative_sine_heading_condition": "sin(theta) >= -1/14 for the third released bomb to be essential",
    },
    "recommended_candidate": "C5_GEOMETRY_ANCHORED_THREE_SET_COVER_PILOT",
    "recommended_sequence": [
        "add S_123 minus union(S_12,S_13,S_23) time-resolved diagnostic",
        "apply rigorous service/explosion/release/fuse bounds before candidate generation",
        "anchor on service time and build feasible single-cloud coverage masks from the sight-cone tube",
        "select triples whose union is full while every pair union is incomplete",
        "recover release/fuse variables and reject gap violations analytically",
        "send only surviving triples to the unchanged continuous full-surface evaluator and final J3 ranking",
    ],
    "formal_spec_changed": False,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reconstruct_from_table() -> tuple[pilot.Decision, dict]:
    p = pilot.base_parameters()
    release = np.asarray(PUBLISHED["release_points_m"], dtype=float)
    explosion = np.asarray(PUBLISHED["explosion_points_m"], dtype=float)
    initial = np.asarray(p.uav_initial, dtype=float)
    speed = float(PUBLISHED["reported_speed_mps"])

    # The third release has the longest horizontal lever arm and therefore the
    # least sensitivity to table rounding when reconstructing the heading.
    displacement = release[2, :2] - initial[:2]
    heading = math.atan2(float(displacement[1]), float(displacement[0])) % (2.0 * math.pi)
    direction = np.array([math.cos(heading), math.sin(heading)])

    release_times = []
    explosion_times = []
    for point in release:
        release_times.append(float(np.dot(point[:2] - initial[:2], direction) / speed))
    for point in explosion:
        explosion_times.append(float(np.dot(point[:2] - initial[:2], direction) / speed))
    fuse_delays = np.asarray(explosion_times) - np.asarray(release_times)

    decision = pilot.Decision(
        heading_rad=heading,
        speed_mps=speed,
        release_times_s=tuple(float(value) for value in release_times),
        fuse_delays_s=tuple(float(value) for value in fuse_delays),
        source="A196_table5_reconstructed",
        proposal_index=0,
    )
    reconstructed = pilot.decision_record(decision)
    release_residual = np.asarray(reconstructed["release_points_m"]) - release
    explosion_residual = np.asarray(reconstructed["explosion_points_m"]) - explosion
    consistency = {
        "coordinate_implied_heading_deg": math.degrees(heading),
        "prose_heading_deg": PUBLISHED["reported_heading_deg"],
        "prose_minus_coordinate_heading_deg": PUBLISHED["reported_heading_deg"] - math.degrees(heading),
        "release_coordinate_max_abs_residual_m": float(np.max(np.abs(release_residual))),
        "explosion_coordinate_max_abs_residual_m": float(np.max(np.abs(explosion_residual))),
        "third_explosion_height_residual_m": float(explosion_residual[2, 2]),
        "diagnosis": "The prose angle is almost exactly twice the coordinate-implied angle; table coordinates and appendix cos(theta), sin(theta) cannot both support the prose value.",
    }
    return decision, consistency


def prose_heading_variant(table_decision: pilot.Decision) -> pilot.Decision:
    return pilot.Decision(
        heading_rad=math.radians(float(PUBLISHED["reported_heading_deg"])),
        speed_mps=table_decision.speed_mps,
        release_times_s=table_decision.release_times_s,
        fuse_delays_s=table_decision.fuse_delays_s,
        source="A196_prose_heading_literal",
        proposal_index=1,
    )


def paper_side_mesh() -> pilot.SurfaceMesh:
    p = pilot.base_parameters()
    n_theta = int(PUBLISHED["paper_sampling"]["circumference_samples_per_height"])
    generated_levels = int(PUBLISHED["paper_sampling"]["generated_heights"])
    angles = np.linspace(0.0, 2.0 * math.pi, n_theta)
    heights = np.linspace(0.0, p.target_height, generated_levels)
    theta = np.tile(angles, generated_levels)
    z = np.repeat(heights, n_theta)
    points = np.column_stack((
        p.target_base_center[0] + p.target_radius * np.cos(theta),
        p.target_base_center[1] + p.target_radius * np.sin(theta),
        z,
    ))
    used = int(PUBLISHED["paper_sampling"]["downstream_loop_point_count"])
    points = points[:used]
    theta = theta[:used]
    z = z[:used]
    # Zero side normals make every actually used circumference sample visible.
    # This reproduces the appendix's all-point test without changing the
    # finite-segment distance computation.
    normals = np.zeros_like(points)
    return pilot.SurfaceMesh(
        points=points,
        point_normals=normals,
        kinds=np.zeros(len(points), dtype=np.int8),
        theta=theta,
        second=z,
        point_norm2=np.einsum("ij,ij->i", points, points),
        n_theta=n_theta,
        n_levels=len(PUBLISHED["paper_sampling"]["effectively_checked_heights_m"]),
    )


def compact_interval_result(result: dict) -> dict:
    return {
        "surface_point_count": result["surface_point_count"],
        "scan_count": result["scan_count"],
        "intervals_s": result["intervals_s"],
        "effective_duration_s": result["effective_duration_s"],
        "minimum_scan_margin_m": result["minimum_scan_margin_m"],
        "root_fallback_count": result.get("root_fallback_count", 0),
        "recovered_unsampled_interval_count": result.get("recovered_unsampled_interval_count", 0),
    }


def diagnostics(decision: pilot.Decision, paper_mesh: pilot.SurfaceMesh) -> dict:
    paper_settings = {
        "name": "A196_appendix_sampling_crosscheck",
        "scan_step_s": 0.005,
        "n_theta": paper_mesh.n_theta,
        "n_levels": paper_mesh.n_levels,
        "root_time_tolerance_s": 1e-9,
        "margin_tolerance_m": 1e-8,
        "surface_refinement": False,
    }
    paper = pilot.synergy_diagnostics(decision, paper_settings, paper_mesh)

    precise_mesh = pilot.surface_mesh(pilot.PRECISE["n_theta"], pilot.PRECISE["n_levels"])
    dense_mesh = pilot.surface_mesh(pilot.DENSIFIED["n_theta"], pilot.DENSIFIED["n_levels"])
    precise = pilot.synergy_diagnostics(decision, pilot.PRECISE, precise_mesh)
    dense = pilot.densified_synergy_diagnostics(decision, precise, dense_mesh)

    leave_one_out = []
    for omitted in range(3):
        kept = tuple(index for index in range(3) if index != omitted)
        item = pilot.solve_intervals(decision, pilot.PRECISE, cloud_indices=kept, mesh=precise_mesh)
        leave_one_out.append({
            "omitted_bomb": omitted + 1,
            "duration_s": item["effective_duration_s"],
            "marginal_contribution_s": precise["joint"]["effective_duration_s"] - item["effective_duration_s"],
        })

    def compact_synergy(value: dict) -> dict:
        return {
            "joint": compact_interval_result(value["joint"]),
            "individuals": [compact_interval_result(item) for item in value["individuals"]],
            "individual_union_intervals_s": value["individual_union_intervals_s"],
            "pure_synergy_intervals_s": value["pure_synergy_intervals_s"],
            "pure_synergy_duration_s": value["pure_synergy_duration_s"],
        }

    return {
        "decision": pilot.decision_record(decision),
        "paper_sample_model": compact_synergy(paper),
        "project_precise_model": compact_synergy(precise),
        "project_densified_model": compact_synergy(dense),
        "densified_joint_change_s": dense["joint"]["effective_duration_s"] - precise["joint"]["effective_duration_s"],
        "leave_one_out": leave_one_out,
    }


def current_summary() -> dict:
    path = ROOT / "docs" / "q3_result.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    final = value["final_diagnostics"]
    return {
        "result_sha256": sha256(path),
        "decision": value["formal_best"]["decision"],
        "joint": compact_interval_result(final["precise"]["joint"]),
        "individuals": [compact_interval_result(item) for item in final["precise"]["individuals"]],
        "pure_synergy_intervals_s": final["precise"]["pure_synergy_intervals_s"],
        "pure_synergy_duration_s": final["precise"]["pure_synergy_duration_s"],
        "densified_joint_duration_s": final["densified"]["joint"]["effective_duration_s"],
        "densified_joint_change_s": final["densified_joint_change_s"],
        "leave_one_out": [
            {
                "omitted_bomb": item["omitted_bomb"],
                "duration_s": item["duration_s"],
                "marginal_contribution_s": item["marginal_contribution_s"],
            }
            for item in final["leave_one_out"]
        ],
    }


def build_report(result: dict) -> str:
    table = result["a196_variants"]["table_reconstructed"]
    prose = result["a196_variants"]["prose_heading_literal"]
    current = result["current_project_result"]
    paper_model = table["paper_sample_model"]
    strict = table["project_precise_model"]
    individual = [item["effective_duration_s"] for item in strict["individuals"]]
    current_individual = [item["effective_duration_s"] for item in current["individuals"]]
    corrected_a196_gain = strict["joint"]["effective_duration_s"] - current["joint"]["effective_duration_s"]
    reported_gap = PUBLISHED["reported_joint_duration_s"] - paper_model["joint"]["effective_duration_s"]
    paper_individual = [item["effective_duration_s"] for item in paper_model["individuals"]]
    paper_overlap = sum(paper_individual) - paper_model["joint"]["effective_duration_s"]
    return f"""# Q3：A196 方案交叉复算与三弹联合可达性审计

本文件是 `internal_regression/candidate_hint`，不改变 Q3 的正式候选池、模型规格或阶段状态。

## 1. 论文数据一致性

- A196 报告联合时长 `{PUBLISHED['reported_joint_duration_s']:.5f} s`、航向 `{PUBLISHED['reported_heading_deg']:.5f}°`、速度 `{PUBLISHED['reported_speed_mps']:.5f} m/s`。
- 由表 5 三组坐标反推的实际航向为 `{result['source_consistency']['coordinate_implied_heading_deg']:.9f}°`，与正文相差 `{result['source_consistency']['prose_minus_coordinate_heading_deg']:.9f}°`。正文角度几乎恰好为坐标角度的两倍；附录又明确用 `cos(u(1)), sin(u(1))`，所以这不是同一条轨迹。
- 因此主复算采用表 5 坐标反推控制量，同时把正文角度按字面值作为独立敏感性分支，不静默择一。

## 2. 交叉复算结果

- 表 5 轨迹在论文附录**实际执行**口径下：联合 `{paper_model['joint']['effective_duration_s']:.9f} s`，纯协同 `{paper_model['pure_synergy_duration_s']:.9f} s`。代码虽生成 5 个高度 × 125 点，但后续仍只循环 `sample_num=250`，实际只检查 `z=0,2.5 m` 两圈，且无端盖内部。
- 该复算仍比论文声称的 `{PUBLISHED['reported_joint_duration_s']:.5f} s` 少 `{reported_gap:.9f} s`；三弹独立时长为 `{paper_individual}`，前两弹完整遮蔽区间重叠 `{paper_overlap:.9f} s`。论文总数实际等于独立时长之和（舍入误差内），没有扣除这段重叠。表 5 坐标重构残差小于 `{result['source_consistency']['explosion_coordinate_max_abs_residual_m']:.3e} m`，坐标舍入不足以解释这一级差异。
- 同一轨迹进入本项目完整可见圆柱表面高精度判据：联合 `{strict['joint']['effective_duration_s']:.9f} s`，三弹独立时长 `{individual}`，纯协同 `{strict['pure_synergy_duration_s']:.9f} s`。
- 两倍稠密表面复算：联合 `{table['project_densified_model']['joint']['effective_duration_s']:.9f} s`，相对变化 `{table['densified_joint_change_s']:.3e} s`。
- 把正文 `{PUBLISHED['reported_heading_deg']:.5f}°` 按字面代入、其余时序不变：论文采样模型联合 `{prose['paper_sample_model']['joint']['effective_duration_s']:.9f} s`，本项目高精度联合 `{prose['project_precise_model']['joint']['effective_duration_s']:.9f} s`。

以上结果说明 A196 的 `6.93586 s` 不能作为一组无歧义、可直接复现的控制向量；表 5、正文角度、附录循环上界和报告时长之间存在内部不一致。论文表 5 的三项“有效干扰时长”恰好求和为 `6.93585 s`，但按其附录写出的“逐点先并三弹、再对点取交”的联合逻辑复算并不等于这项和。A196 自己也明确说明第三弹始终没有发挥作用，所以它不是“每弹遮一部分、三弹合成完整圆柱”的实证样例。

## 3. 与本项目当前解对照

- 当前正式解联合 `{current['joint']['effective_duration_s']:.9f} s`，三弹独立时长 `{current_individual}`，纯协同 `{current['pure_synergy_duration_s']:.9f} s`。
- A196 表 5 轨迹按本项目完整判据仍比当前正式解高 `{corrected_a196_gain:.9f} s`。这是一条更好的两弹解，却没有被当前正式搜索找到，是“搜索覆盖不足”的直接反例。
- 当前解第三弹独立时长为 `0`，删除第三弹的边际贡献也近于 `0`；它同样是两弹时域拼接，不是真三弹联合。

## 4. 算法能否找到真正三弹联合

判据层面可以：实现计算的是 `max_P min_k(distance(segment(M,P), cloud_k)-R)`，即每个表面点可选择不同烟团，严格支持 `∀P∃k`。但现有 `pure_synergy_duration = S_123 \\ (S_1∪S_2∪S_3)` 只证明“至少需要两弹”，还不能证明三弹都不可缺。用户所说的真正三弹联合应另记 `S_123 \\ (S_12∪S_13∪S_23)`，即删掉任意一弹后该时刻都不再完整遮蔽。

搜索层面目前不能给出可靠保证：C2/C3 能把真联合送进同一个联合判据，局部优化代理也是联合 max-min 的平滑分数，所以并非逻辑上找不到；但 C3 的起点强调走廊裕度，筛选预算很小。唯一显式构造点—时覆盖掩码三元组的 C4，排序键却把“各单弹已完整遮蔽时刻的并集”放在第一优先级，联合覆盖只排在后面；它在旧定额试验中未改善最优值且三次种子加密后最大纯协同仍为 `0`，于是又被移出正式种子池。目标函数是不连续的 max-min/区间长度，纯协同盆地很容易被零平台和单弹强解淹没。

结论：底层求值器“看得见”真联合，但现有诊断只直接标注到“两弹或以上协同”，正式搜索器也未被设计成稳定找到“三弹均不可缺”的联合。要提高找到它的概率，应先新增上述三弹必要区间诊断，再把 C4 改为协同优先的候选生成器，用互补覆盖缺口、三组两弹删减失败和三弹非零边际贡献作分层筛选/连续化引导；最终排名仍回到原始 `J3`，不改变题意。

## 5. 已记录的下一步：几何降维与安全剪枝

### 5.1 可以严格证明的搜索域

导弹横坐标为 `x_M(t)=20000-298.511157063t`。任一烟团若能遮住至少一个目标点，其球心横坐标必满足 `C_x(t)≤x_M(t)+10`。另一方面，烟团在爆炸后不再水平运动；爆炸时刻 `e≤t`、无人机速度不超过 `140 m/s`，故无论航向如何都有 `C_x(t)≥17800-140t`。两式合并得到：

`t ≤ 2210/(298.511157063-140) = 13.942236250 s`。

因此，任何遮蔽、联合遮蔽和真三弹联合都不可能发生在 `13.94224 s` 之后。若 `cosθ≥0`，还有 `C_x≥17800`，上界进一步缩为 `t≤7.403408374 s`。这两条都是安全剪枝，不是经验范围。

若三弹在时刻 `t` 均不可缺，则每弹爆炸时刻 `e_k≤t`，且 `τ_k≤e_k`、`δ_k≤e_k`，所以三组释放、引信和爆炸时间都可安全限制到 `[0,13.942236250] s`。对每个必需烟团还可先检查必要包围盒：`-17≤C_x≤x_M(t)+10`、`-10≤C_y≤217`、`-10≤C_z≤z_M(t)+10`。第三枚按释放顺序有 `τ_3≥2 s`，由 `C_y=v e_3 sinθ≥-10` 还能安全排除 `sinθ<-1/14` 的航向。

### 5.2 候选方法比较

- **现有 8 维全域搜索（基线）**：不额外假设、最终判据正确；失败条件是窄协同盆地被大范围零平台和强单弹解淹没，且已经漏掉 A196 的较优两弹轨迹。
- **只加入上述严格界**：不会漏解，实现成本最低，预计首先把时间扫描与无效候选压到原来的约 1/5；但它只提高效率，不主动寻找互补覆盖。
- **固定经验航向/时间小盒**：会更快，但无法证明不漏掉朝目标方向飞行的晚期方案，只能作为种子域，不能作为正式硬边界。
- **推荐的 `C5_GEOMETRY_ANCHORED_THREE_SET_COVER_PILOT`**：外层搜索 `(θ,v,t*)`；在固定服务时刻 `t*`，先从导弹—圆柱视线锥的 `10 m` 膨胀管与无人机轨迹的交集生成单烟团状态，再用位集选择三张覆盖掩码，使三者并集覆盖全部表面、任意两张并集都不完整。其假设只用于候选生成；最终仍交回当前连续完整表面判据，因此稀疏候选库只会造成漏搜，不会制造错误正式解。
- **连续区间分支定界**：有希望给出更强的无解/上界证明，但对“圆柱表面被三个球投影并覆盖”的区间界实现复杂，适合作为 C5 找到候选后的局部认证，不适合作为第一步。

### 5.3 推荐执行顺序

1. 新增 `S_123 \\ (S_12∪S_13∪S_23)` 的逐时刻“三弹均必要”诊断。
2. 将 `13.94224 s`、正向航向 `7.40341 s` 以及逐烟团 `x/y/z` 必要条件接入候选生成前置剪枝。
3. 实现 C5 的定时刻几何单弹库和“三集合恰覆盖”位集选择，不再先奖励单弹完整遮蔽。
4. 用与 C2+C3 相同的种子数、表面网格和精确复算预算做准入试验。
5. 只有 C5 能稳定保留三弹必要区间，才申请修改正式种子池；最终目标仍是原始 `J3`。

本节是已记录的工作设计，不修改 `SPEC-Q3-1.0`，也不代表已执行新求解器。
"""


def run(output: Path, report: Path) -> dict:
    table_decision, consistency = reconstruct_from_table()
    paper_mesh = paper_side_mesh()
    result = {
        "schema_version": "1.0",
        "status": "ok",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Cross-evaluate A196 and audit whether the current Q3 algorithm can discover genuine partial-cover three-cloud synergy.",
        "source": SOURCE,
        "published": PUBLISHED,
        "source_consistency": consistency,
        "a196_variants": {
            "table_reconstructed": diagnostics(table_decision, paper_mesh),
            "prose_heading_literal": diagnostics(prose_heading_variant(table_decision), paper_mesh),
        },
        "current_project_result": current_summary(),
        "algorithm_audit": {
            "evaluator_supports_pointwise_cloud_identity_switching": True,
            "formal_objective_can_score_pure_synergy": True,
            "existing_pure_synergy_certifies": "at_least_two_clouds_needed",
            "existing_pure_synergy_set": "S_123 \\ (S_1 union S_2 union S_3)",
            "true_three_cloud_necessity_set_needed": "S_123 \\ (S_12 union S_13 union S_23)",
            "true_three_cloud_necessity_metric_currently_recorded": False,
            "formal_seed_sources": ["C2", "C3", "B0", "C1"],
            "dedicated_complementary_point_time_source": "C4",
            "c4_current_role": "internal_synergy_validator_only",
            "c4_has_formal_seed_quota": False,
            "c4_ranking_primary": "union_of_individually_complete_cover_times",
            "c4_joint_surface_coverage_priority": "secondary",
            "c4_pilot_maximum_precise_pure_synergy_s": 0.0,
            "c4_pilot_maximum_densified_pure_synergy_s": 0.0,
            "can_find_in_principle": True,
            "reliable_discovery_guarantee": False,
            "observed_current_pure_synergy_s": 0.0,
        },
        "geometry_reduction_plan": GEOMETRY_REDUCTION_PLAN,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pilot.ready(result), ensure_ascii=False, indent=2), encoding="utf-8")
    report.write_text(build_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "q3_a196_crosscheck.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "q3_a196_crosscheck.md")
    args = parser.parse_args()
    result = run(args.output, args.report)
    compact = {
        "status": result["status"],
        "table_paper_model_s": result["a196_variants"]["table_reconstructed"]["paper_sample_model"]["joint"]["effective_duration_s"],
        "table_project_precise_s": result["a196_variants"]["table_reconstructed"]["project_precise_model"]["joint"]["effective_duration_s"],
        "current_project_s": result["current_project_result"]["joint"]["effective_duration_s"],
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
