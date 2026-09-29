# Q5 独立几何—物理审计报告

状态：`pass`；规格：`SPEC-Q5-GEOMETRY-AUDIT-1.0`。

本报告只审计几何与运动学，没有执行全域优化，也没有替换正式 Q5 结果。

## 结论

- `finite_segment_distance`：`pass`
- `visible_surface_first_hit`：`pass`
- `kinematic_roundtrip`：`pass`
- `centreline_certificate_and_cloud_union`：`pass`
- `production_full_obscuration_quantifier`：`pass`
- `historical_geometry_mesh_convergence`：`diagnostic`

## 关键数值

- 圆柱中点包络半径：8.602325267 m，小于烟幕半径 10 m。
- 有限线段距离独立交叉最大误差：4.923e-11 m。
- 可见面非歧义不一致数：0。
- 生产全遮蔽余量与独立逐点参考最大差：3.848e-10 m。
- 历史方案最细两层选定时刻最大余量差：0.000567895 m。

## 反例边界

- 位于目标之后的烟团对无限直线距离为零，但对有限视线段距离为正，禁止使用无限直线替代。
- 导弹—圆柱底面中心线不具有无条件全圆柱遮蔽证书。
- 两个烟团可以各自不能全遮蔽，但按逐视线并集后实现全遮蔽；不能要求某一个烟团独立覆盖全部表面。

## 主张边界

通过表示当前离散实现与独立解析/逐点参考在所列检查中一致；不表示已证明连续圆柱上的全局最优，也不表示当前搜索库完整。
