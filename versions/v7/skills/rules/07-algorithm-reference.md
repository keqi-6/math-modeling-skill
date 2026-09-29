# 07 — 图网络与离散优化算法参考

> 来源：Hermes skill `mathmodel/contest-algorithm-reference`
> 司守奎《数学建模算法与应用》第3版 + 姜启源《数学模型》第4版

---

## 职责与强度

本文件提供算法候选的定义、适用条件和误用提醒，不是文献证据、选模权威或当前题目的
方法清单。正式选模须经 `08/12/15`。算法定义和成立条件为 A/B；接口为 C/D；方法
偏好和示例目标为 D。

## 第4章：图与网络模型

### Dijkstra 最短路径算法

对于图 G=(V,E,W)，从源点 v₀ 求到所有点的最短路径：

1. l(v₀) = 0, l(v) = ∞ for v ≠ v₀, S₀ = {v₀}
2. 对每个不在 S 中的 v：l(v) = min{l(v), l(u) + w(u,v)} where u ∈ S
3. 选 v_min = argmin{l(v)} for v ∉ S，加入 S
4. 重复直到所有点处理完

**关键性质**：最短路径的任意子路径也是最短路径（动态规划基础）。

**适用**：Dijkstra 要求边权非负。使用前还需核验有向性、连通性和权重单位：
```python
import networkx as nx
G = nx.Graph()
G.add_edges_from(edges)  # edges = [(u, v, {'weight': d}), ...]
dist = nx.shortest_path_length(G, source=u, target=v, weight='weight')
```

### 全源最短路径

非负边权稀疏图可对每个源点运行 Dijkstra：
```python
dist_matrix = dict(nx.all_pairs_dijkstra_path_length(G, weight='weight'))
```

这不是 Floyd–Warshall。Floyd–Warshall 是动态规划型稠密全源算法，典型复杂度为 \(O(|V|^3)\)，NetworkX 对应接口为 `nx.floyd_warshall`。

### 最小生成树

Prim/Kruskal 用于连通全部节点且总边权最小的网络设计，不用于一般最短路或设施选址。

---

## 第2章：整数规划

### 指派问题（Assignment Problem）

n 个任务分配给 n 个人，一人一任务，总成本最小。

**标准形式**：min Σ c_ij·x_ij, s.t. Σ_i x_ij = 1, Σ_j x_ij = 1, x_ij ∈ {0,1}

多对一分配、带容量分配和设施—需求联合分配不等同于经典一对一指派；必须按实际变量与约束重新建模。

### 0-1 规划

变量取 0/1 的整数规划。设施是否启用、边是否选择等“是/否”决策可用 0-1 变量表达。

---

## 第14章：综合评价与决策方法

### 多指标排序与多目标优化不可混用

TOPSIS 用于对既有候选方案排序，不负责生成可行最优方案。若指标具有明确优先级或硬阈值，优先采用词典序优化或 ε-约束法；不要用归一化加权掩盖硬约束。

**步骤**：
1. 向量归一化：b_ij = a_ij / sqrt(Σ a_kj²)
2. 加权：c_ij = w_j × b_ij
3. 确定正负理想解
4. 计算各方案到正负理想解的距离 s*_i, s⁰_i
5. 相对贴近度 f_i = s⁰_i / (s*_i + s⁰_i)，排序

### 熵权法

根据样本中各指标的离散程度生成权重。它减少了直接人工指定权重的环节，但权重仍受
样本、归一化和指标设计影响，不等于客观正确或现实重要性。

### 灰色关联分析

衡量序列变化形态的接近程度。它与 TOPSIS 是否互补取决于评价对象、指标语义和需要
回答的问题，不能因方法名称不同就默认信息增量。

---

## 第12章：现代优化算法

### 精确算法优先，启发式按需

适用于精确枚举或精确优化在资源限制内不可行的大规模组合优化。

**核心**：Metropolis 准则 — 以概率 exp(-ΔE/T) 接受更差的解，随温度下降概率减小。

是否采用模拟退火、遗传算法，应综合实例规模、时间限制、证明需求、可用精确基线和
所需解质量判断。参数必须通过预实验或文献确定，不能把经验区间当作通用默认值；
随机算法需报告多组种子、结果分布和可用的最优性界。

### 遗传算法（GA）

**适用**：离散组合空间可编码为染色体，但必须设计可行性修复、约束惩罚和精确小实例对照。

---

## 第16章：多目标规划

当问题同时包含成本、效率、公平或风险等冲突目标时，需要明确多目标处理规则。

**处理方法**：
1. **线性加权**：先处理量纲与尺度，说明归一化和权重依据，再对加权目标做权重扫描；
   不直接相加方差与最大时间等异量纲指标
2. **ε-约束法**：一个目标做主目标，另一个转为约束
3. **目标规划**：设各目标的期望值，最小化偏差

---

## 快速参考：Python 实现

```python
# 最短路径
import networkx as nx
path = nx.shortest_path(G, source, target, weight='weight')
length = nx.shortest_path_length(G, source, target, weight='weight')

# 整数规划
from scipy.optimize import linprog  # 连续线性规划
from scipy.optimize import milp     # 混合整数线性规划

# 模拟退火/遗传
# scipy.optimize.dual_annealing
# 或 deap 库
```
