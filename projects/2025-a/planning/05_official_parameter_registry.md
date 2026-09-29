# A 题统一参数登记表

> 用途：集中查找 A 题题面参数、正式建模约定和由其推导的 Q1 实例量。  
> 官方来源权威：`data/A题.pdf` 及题目随附的三个结果模板。  
> 消费者：`INPUTS`、`Q1`—`Q5` 的模型规格、代码配置、验证、结果表和论文。  
> 边界：本表是可检索的项目登记表，不取代原题；若本表与官方输入冲突，以官方输入为准并定向修订本表及其消费者。

## 1. 分类与使用规则

| 分类 | 含义 | 能否作为题面原值引用 |
|---|---|---|
| `O` | 官方题面或官方附件直接给定 | 可以 |
| `C` | 项目为消除歧义而确认的建模/数值约定 | 不可以冒充题面给定 |
| `D` | 由 `O` 和已声明的 `C` 计算得到 | 不可以冒充题面给定 |
| `B` | 外部讲评或预求解基准 | 只能作验证参照，不是输入参数 |

通用模型优先使用符号；代码通过单一参数对象或配置映射数值。题面固定量不得被优化器改写，推导量不得作为独立决策变量，禁止在多个函数中散落无来源的魔法数字。

稳定主张：

- `A.PARAMETERS.OFFICIAL.001`：本表 `O` 类逐项映射官方题面及附件中的坐标、速度、时间、几何和资源约束。
- `A.PARAMETERS.CLASSIFICATION.001`：`O/C/D/B` 分类阻止建模约定、推导值和基准值被误报为题面参数。

## 2. 坐标、时间与单位

| ID | 分类 | 符号/键 | 含义 | 值 | 单位/说明 | 适用范围 |
|---|---|---|---|---|---|---|
| `PAR-COORD-ORIGIN` | O | `O` | 假目标及坐标原点 | `(0,0,0)` | m | Q1–Q5 |
| `PAR-COORD-GROUND` | O | `ground_plane` | 地面 | `z=0` | `xy` 平面 | Q1–Q5 |
| `PAR-TIME-ZERO` | O | `t0` | 雷达发现来袭导弹并下达任务的时刻 | `0` | s | Q1–Q5 |
| `PAR-UNIT-POSITION` | O | `position_unit` | 位置/距离单位 | `m` | 米 | 全项目 |
| `PAR-UNIT-SPEED` | O | `speed_unit` | 速度单位 | `m/s` | 米每秒 | 全项目 |
| `PAR-UNIT-TIME` | O | `time_unit` | 时间单位 | `s` | 秒 | 全项目 |
| `PAR-UNIT-HEADING-TEMPLATE` | O | `heading_output_unit` | 结果模板航向角单位 | `degree` | 模型内部可用 rad，写表时转换 | Q3–Q5 |

## 3. 真实目标

| ID | 分类 | 符号/键 | 含义 | 值 | 单位 | 适用范围 |
|---|---|---|---|---|---|---|
| `PAR-TARGET-BASE-CENTER` | O | `target_base_center` | 真目标底面圆心 | `(0,200,0)` | m | Q1–Q5 |
| `PAR-TARGET-RADIUS` | O | `R_T` / `target_radius` | 真目标圆柱半径 | `7` | m | Q1–Q5 |
| `PAR-TARGET-HEIGHT` | O | `H_T` / `target_height` | 真目标圆柱高度 | `10` | m | Q1–Q5 |

目标集合统一表示为

`T={(x,y,z): x²+(y-200)²≤R_T², 0≤z≤H_T}`。

## 4. 导弹参数

| ID | 分类 | 符号/键 | 值 | 单位 | 适用范围 |
|---|---|---|---|---|---|
| `PAR-M1-INITIAL` | O | `M10` / `missile_initial.M1` | `(20000,0,2000)` | m | Q1–Q5 |
| `PAR-M2-INITIAL` | O | `M20` / `missile_initial.M2` | `(19000,600,2100)` | m | Q5 |
| `PAR-M3-INITIAL` | O | `M30` / `missile_initial.M3` | `(18000,-600,1900)` | m | Q5 |
| `PAR-MISSILE-SPEED` | O | `v_M` / `missile_speed` | `300` | m/s | Q1–Q5 |
| `PAR-MISSILE-DESTINATION` | O | `missile_destination` | `(0,0,0)` | m | Q1–Q5 |

题面运动关系为导弹始终以 300 m/s 指向假目标原点：

`M_j(t)=M_j0-v_M t M_j0/||M_j0||`，时间上限为到达原点的时刻。

## 5. 无人机参数

| ID | 分类 | 符号/键 | 值 | 单位 | 适用范围 |
|---|---|---|---|---|---|
| `PAR-FY1-INITIAL` | O | `U10` / `uav_initial.FY1` | `(17800,0,1800)` | m | Q1–Q5 |
| `PAR-FY2-INITIAL` | O | `U20` / `uav_initial.FY2` | `(12000,1400,1400)` | m | Q4–Q5 |
| `PAR-FY3-INITIAL` | O | `U30` / `uav_initial.FY3` | `(6000,-3000,700)` | m | Q4–Q5 |
| `PAR-FY4-INITIAL` | O | `U40` / `uav_initial.FY4` | `(11000,2000,1800)` | m | Q5 |
| `PAR-FY5-INITIAL` | O | `U50` / `uav_initial.FY5` | `(13000,-2000,1300)` | m | Q5 |
| `PAR-UAV-SPEED-MIN` | O | `v_U,min` / `uav_speed_min` | `70` | m/s | Q2–Q5 |
| `PAR-UAV-SPEED-MAX` | O | `v_U,max` / `uav_speed_max` | `140` | m/s | Q2–Q5 |

共同运动规则（O）：无人机接到任务后可以瞬时调整航向，之后以选定的固定航向和固定速度做等高度直线运动。符号表达为

`U_i(t)=U_i0+v_i t(cosθ_i,sinθ_i,0)`，其中 `θ_i∈[0,2π)`、`v_i∈[70,140]`。

## 6. 烟幕弹与烟幕云参数

| ID | 分类 | 符号/键 | 含义 | 值 | 单位 | 适用范围 |
|---|---|---|---|---|---|---|
| `PAR-SMOKE-RADIUS` | O | `R_s` / `smoke_radius` | 云团中心有效浓度范围半径 | `10` | m | Q1–Q5 |
| `PAR-SMOKE-SINK-SPEED` | O | `v_s` / `smoke_sink_speed` | 起爆后云团中心匀速下沉速度 | `3` | m/s | Q1–Q5 |
| `PAR-SMOKE-DURATION` | O | `T_s` / `smoke_duration` | 起爆后有效遮蔽时长 | `20` | s | Q1–Q5 |
| `PAR-RELEASE-GAP-MIN` | O | `Δτ_min` / `release_gap_min` | 同一无人机相邻两次投放最小间隔 | `1` | s | Q3、Q5 |
| `PAR-GRAVITY` | C | `g` / `gravity` | 正式数值计算采用的重力加速度 | `9.8` | m/s² | Q1–Q5 |

题面直接给出的运动语义（O）：烟幕弹离机后继承无人机水平速度，并在重力作用下运动；起爆延迟可控。`g=9.8` 是项目数值约定，不是题面直接给出的数值。

通用关系：

- 投放时刻：`τ_ik≥0`；
- 起爆延迟：`δ_ik≥0`；
- 起爆时刻：`t^e_ik=τ_ik+δ_ik`；
- 起爆点：`E_ik=(x_i+v_i t^e_ik cosθ_i, y_i+v_i t^e_ik sinθ_i, z_i-gδ_ik²/2)`；
- 云团球心：`C_ik(t)=E_ik-v_s(t-t^e_ik)e_z`，`t∈[t^e_ik,t^e_ik+T_s]`；
- 有效视线截断阈值：`d(C_ik(t), segment[M_j(t),P])≤R_s`。

## 7. 各问资源约束

| ID | 分类 | 问题 | 无人机 | 烟幕弹 | 导弹 | 决策性质 |
|---|---|---|---|---|---|---|
| `PAR-Q1-RESOURCE` | O | Q1 | FY1 | 1 枚 | M1 | 题面给定策略，只计算 |
| `PAR-Q2-RESOURCE` | O | Q2 | FY1 | 1 枚 | M1 | 优化航向、速度、投放与起爆 |
| `PAR-Q3-RESOURCE` | O | Q3 | FY1 | 3 枚 | M1 | 同航迹时序协同 |
| `PAR-Q4-RESOURCE` | O | Q4 | FY1、FY2、FY3 | 各 1 枚 | M1 | 多平台空间协同 |
| `PAR-Q5-RESOURCE` | O | Q5 | FY1—FY5 | 每机至多 3 枚，共至多 15 枚 | M1—M3 | 离散分配与连续优化 |

## 8. Q1 题面专用参数

| ID | 分类 | 符号/键 | 含义 | 值 | 单位 |
|---|---|---|---|---|---|
| `PAR-Q1-UAV` | O | `q1.uav_id` | 执行无人机 | `FY1` | — |
| `PAR-Q1-MISSILE` | O | `q1.missile_id` | 干扰对象 | `M1` | — |
| `PAR-Q1-UAV-SPEED` | O | `q1.uav_speed` | FY1 固定飞行速度 | `120` | m/s |
| `PAR-Q1-HEADING` | O | `q1.heading_rule` | FY1 航向 | 朝假目标 | 水平单位向量为 `(-1,0,0)` |
| `PAR-Q1-RELEASE-TIME` | O | `q1.release_time` | 接到任务后投弹时刻 | `1.5` | s |
| `PAR-Q1-FUSE-DELAY` | O | `q1.fuse_delay` | 投弹后起爆延迟 | `3.6` | s |

## 9. Q1 推导实例量

以下均为 `D` 类，不是题面直接给出的独立参数；涉及竖直位移的数值使用约定 `g=9.8 m/s²`。

| ID | 分类 | 符号/键 | 推导式 | 值 | 单位 |
|---|---|---|---|---|---|
| `DER-Q1-RELEASE-POINT` | D | `q1.release_point` | `U10+120×1.5×(-1,0,0)` | `(17620,0,1800)` | m |
| `DER-Q1-EXPLOSION-TIME` | D | `q1.explosion_time` | `1.5+3.6` | `5.1` | s |
| `DER-Q1-EXPLOSION-POINT` | D | `q1.explosion_point` | 水平推进至 `t=5.1`，竖直下降 `g×3.6²/2` | `(17188,0,1736.496)` | m |
| `DER-Q1-ACTIVE-WINDOW` | D | `q1.active_window` | `[5.1,5.1+20]` | `[5.1,25.1]` | s |

Q1 云团实例轨迹为

`C_1(t)=(17188,0,1736.496-3(t-5.1)),  t∈[5.1,25.1]`。

## 10. 不是输入参数的参照量

| ID | 分类 | 数值/内容 | 正确用途 |
|---|---|---|---|
| `BASE-Q1-CENTER` | B | 中心点简化约 `1.434 s` | 错误对照和调试，不进入正式答案 |
| `BASE-Q1-CYLINDER` | B | 完整圆柱约 `1.3916 s`；公开参考约 `1.391643 s` | 后续正式复算的回归目标，不是题面给定答案 |
| `NUM-TIME-TOL` | 未冻结 | 时间根求精容差 | S3→S4 模型规格确定 |
| `NUM-ANGLE-BUDGET` | 未冻结 | 圆周采样/连续极值预算 | S3→S4 模型规格确定 |

## 11. 附件输出槽位

| 官方附件 | 对应问题 | 预置槽位 | 主要参数字段 |
|---|---|---:|---|
| `data/附件/result1.xlsx` | Q3 | 3 | 航向、速度、弹号、投放点、起爆点、单弹有效时长 |
| `data/附件/result2.xlsx` | Q4 | 3 | 无人机号、航向、速度、投放点、起爆点、单弹有效时长 |
| `data/附件/result3.xlsx` | Q5 | 15 | 无人机号、航向、速度、弹号、投放点、起爆点、干扰导弹编号、单弹有效时长 |

## 12. 维护规则

1. 新发现的题面参数先核对官方输入，再以新 `PAR-*` ID 加入；不得静默覆盖旧值。
2. `O` 类变化必须检查 `INPUTS` 和 Q1—Q5 的直接消费者。
3. `C` 类变化必须记录授权或选择理由，并重算受影响的 `D` 类量。
4. `D` 类只保存推导链，不作为优化器的独立自由变量。
5. 代码、论文和结果表应引用本表符号/键；正式冻结时由模型规格记录精确版本身份。
